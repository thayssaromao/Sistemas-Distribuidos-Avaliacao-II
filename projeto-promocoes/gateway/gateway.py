import json
import os
import threading
import uuid

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_PATH          = os.path.join(_BASE_DIR, 'private_key.der')
PUBLIC_KEY_PATH           = os.path.join(_BASE_DIR, 'public_key.der')
PROMOTION_PUBLIC_KEY_PATH = os.path.join(_BASE_DIR, '..', 'promotion', 'public_key.der')


def _ensure_keys():
    """Gera o par de chaves RSA do Gateway se ainda não existir."""
    if not os.path.exists(PRIVATE_KEY_PATH):
        key = RSA.generate(2048)
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(key.export_key('DER'))
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(key.publickey().export_key('DER'))


class Gateway:
    def __init__(self):
        _ensure_keys()

        with open(PRIVATE_KEY_PATH, 'rb') as f:
            self._private_key = RSA.import_key(f.read())

        if not os.path.exists(PROMOTION_PUBLIC_KEY_PATH):
            raise FileNotFoundError(
                f"Chave pública do Promotion Service não encontrada em: {PROMOTION_PUBLIC_KEY_PATH}\n"
                "Certifique-se de que o Promotion Service foi iniciado antes do Gateway."
            )
        with open(PROMOTION_PUBLIC_KEY_PATH, 'rb') as f:
            self._promotion_public_key = RSA.import_key(f.read())

        self.promocoes_validas: list[dict] = []
        self._lock = threading.Lock()

        # Canal de publicação (thread principal)
        self._pub_conn = pika.BlockingConnection(
            pika.ConnectionParameters(host='localhost'))
        self._pub_ch = self._pub_conn.channel()
        self._pub_ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

        # Canal de consumo (thread daemon separada)
        self._iniciar_consumer()

        print("Gateway iniciado com sucesso!")

    # ------------------------------------------------------------------
    # Assinatura digital
    # ------------------------------------------------------------------

    def verify_promotion_signature(self, payload: dict, signature_hex: str) -> bool:
        """Valida a assinatura do Promotion Service sobre o payload."""
        try:
            data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
            h = SHA256.new(data)
            pkcs1_15.new(self._promotion_public_key).verify(h, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            return False

    def sign_message(self, payload: dict) -> str:
        """Assina o payload (serializado como JSON com chaves ordenadas)
        com a chave privada RSA do Gateway. Retorna a assinatura em hex."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        signature = pkcs1_15.new(self._private_key).sign(h)
        return signature.hex()

    # ------------------------------------------------------------------
    # Publicação de eventos
    # ------------------------------------------------------------------

    def publish_event(self, routing_key: str, payload: dict) -> str:
        """Assina e publica um evento no RabbitMQ.
        Retorna a assinatura gerada."""
        signature = self.sign_message(payload)
        envelope = {
            'payload': payload,
            'signature': signature,
        }
        self._pub_ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(envelope, ensure_ascii=False),
        )
        return signature

    def cadastrar_promocao(
        self,
        titulo: str,
        descricao: str,
        categoria: str,
        preco_original: float,
        preco_promocional: float,
    ) -> tuple[str, str]:
        """Publica promotion.received. Retorna (id_gerado, assinatura)."""
        payload = {
            'id': str(uuid.uuid4()),
            'titulo': titulo,
            'descricao': descricao,
            'categoria': categoria,
            'preco_original': preco_original,
            'preco_promocional': preco_promocional,
        }
        signature = self.publish_event('promotion.received', payload)
        return payload['id'], signature

    def votar_promocao(self, id_promocao: str, voto: str) -> str:
        """Publica promotion.vote. voto deve ser 'positivo' ou 'negativo'.
        Retorna a assinatura."""
        payload = {
            'id_promocao': id_promocao,
            'voto': voto,
        }
        signature = self.publish_event('promotion.vote', payload)

        # Atualiza contagem local para refletir na listagem
        with self._lock:
            for p in self.promocoes_validas:
                if p.get('id') == id_promocao:
                    votos = p.setdefault('votos', {'positivos': 0, 'negativos': 0})
                    if voto == 'positivo':
                        votos['positivos'] += 1
                    else:
                        votos['negativos'] += 1
                    break

        return signature

    def listar_promocoes(self) -> list[dict]:
        with self._lock:
            return list(self.promocoes_validas)

    # ------------------------------------------------------------------
    # Consumidor de promotion.published (thread daemon)
    # ------------------------------------------------------------------

    def _iniciar_consumer(self):
        def run():
            conn = pika.BlockingConnection(
                pika.ConnectionParameters(host='localhost'))
            ch = conn.channel()
            ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

            result = ch.queue_declare(queue='', exclusive=True)
            queue_name = result.method.queue

            ch.queue_bind(
                exchange=EXCHANGE,
                queue=queue_name,
                routing_key='promotion.published',
            )

            def callback(ch_, method, properties, body):
                try:
                    envelope = json.loads(body)
                except json.JSONDecodeError:
                    print("[Gateway] Mensagem recebida não é JSON válido — descartada.")
                    return

                payload   = envelope.get('payload')
                signature = envelope.get('signature')

                if not payload or not signature:
                    print("[Gateway] Envelope incompleto (payload ou signature ausente) — descartado.")
                    return

                if not self.verify_promotion_signature(payload, signature):
                    print("[Gateway] Assinatura do Promotion Service INVÁLIDA — mensagem descartada.")
                    return

                with self._lock:
                    self.promocoes_validas.append(payload)
                print(f"[Gateway] Promoção {payload.get('id')} aceita e listada.")

            ch.basic_consume(
                queue=queue_name,
                on_message_callback=callback,
                auto_ack=True,
            )
            ch.start_consuming()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Encerramento
    # ------------------------------------------------------------------

    def fechar(self):
        try:
            self._pub_conn.close()
        except Exception:
            pass