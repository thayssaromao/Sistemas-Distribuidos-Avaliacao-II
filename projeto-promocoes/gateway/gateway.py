import json
import os
import threading
import uuid

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'
PRIVATE_KEY_PATH = os.path.join(os.path.dirname(__file__), 'private_key.der')
PUBLIC_KEY_PATH  = os.path.join(os.path.dirname(__file__), 'public_key.der')


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

        self.promocoes_validas: list[dict] = []

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
                envelope = json.loads(body)
                payload = envelope.get('payload', envelope)
                self.promocoes_validas.append(payload)

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