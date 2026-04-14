import json
import os
import threading

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'
HIGHLIGHT_THRESHOLD = 5  # score mínimo para hot deal

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_PATH        = os.path.join(_BASE_DIR, 'private_key.der')
PUBLIC_KEY_PATH         = os.path.join(_BASE_DIR, 'public_key.der')
GATEWAY_PUBLIC_KEY_PATH = os.path.join(_BASE_DIR, '..', 'gateway', 'public_key.der')


def _ensure_gateway_key():
    if not os.path.exists(GATEWAY_PUBLIC_KEY_PATH):
        raise FileNotFoundError(
            "Chave pública do Gateway não encontrada. "
            "Certifique-se de que o Gateway foi iniciado antes do Ranking."
        )


def _ensure_keys():
    """Gera o par de chaves RSA do Ranking se ainda não existir."""
    # Chaves RSA próprias do Ranking     
    if not os.path.exists(PRIVATE_KEY_PATH):
        key = RSA.generate(2048)
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(key.export_key('DER'))
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(key.publickey().export_key('DER'))


class Ranking:
    def __init__(self):
        _ensure_gateway_key()
        _ensure_keys()

        with open(GATEWAY_PUBLIC_KEY_PATH, 'rb') as f:
            self._gateway_public_key = RSA.import_key(f.read())

        with open(PRIVATE_KEY_PATH, 'rb') as f:
            self._private_key = RSA.import_key(f.read())

        # { id_promocao: { 'positivos': int, 'negativos': int, 'score': int, 'highlight': bool } }
        self._votos: dict[str, dict] = {}

        # Conexão de publicação e consumo são criadas dentro da thread daemon
        # (pika BlockingConnection não é thread-safe)
        self._pub_ch = None

        # Canal de consumo (thread daemon separada)
        self._iniciar_consumer()

        print("Ranking iniciado com sucesso!")

    # ------------------------------------------------------------------
    # Assinatura e validação
    # ------------------------------------------------------------------
    # assina payloads com a chave privada do Ranking (para promotion.highlight)
    def _sign(self, payload: dict) -> str:
        """Assina o payload com a chave privada do Ranking. Retorna hex."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        return pkcs1_15.new(self._private_key).sign(h).hex()

    def _verify(self, payload: dict, signature_hex: str) -> bool:
        """Verifica a assinatura do Gateway sobre o payload."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        try:
            pkcs1_15.new(self._gateway_public_key).verify(h, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Publicação de eventos
    # ------------------------------------------------------------------

    def _publish_event(self, routing_key: str, payload: dict):
        signature = self._sign(payload)
        envelope = {
            'payload': payload,
            'signature': signature,
        }
        self._pub_ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(envelope, ensure_ascii=False),
        )

    # ------------------------------------------------------------------
    # Lógica de votos
    # ------------------------------------------------------------------

    def _processar_voto(self, id_promocao: str, voto: str):
        if id_promocao not in self._votos:
            self._votos[id_promocao] = {
                'positivos': 0,
                'negativos': 0,
                'score': 0,
                'highlight': False,
            }

        entry = self._votos[id_promocao]

        if voto == 'positivo':
            entry['positivos'] += 1
        elif voto == 'negativo':
            entry['negativos'] += 1
        else:
            print(f"[Ranking] Voto desconhecido '{voto}' ignorado.")
            return

        entry['score'] = entry['positivos'] - entry['negativos']

        print(
            f"[Ranking] Promoção {id_promocao} | "
            f"+{entry['positivos']} -{entry['negativos']} "
            f"(score={entry['score']})"
        )

        # Verifica se atingiu o limiar de destaque pela primeira vez
        if not entry['highlight'] and entry['score'] >= HIGHLIGHT_THRESHOLD:
            entry['highlight'] = True
            self._publicar_destaque(id_promocao, entry['score'])

    def _publicar_destaque(self, id_promocao: str, score: int):
        payload = {
            'id_promocao': id_promocao,
            'score': score,
            'hot_deal': True,
        }
        self._publish_event('promotion.highlight', payload)
        print(f"[Ranking] HOT DEAL publicado para promoção {id_promocao} (score={score})")

    # ------------------------------------------------------------------
    # Consumer de promotion.vote (thread daemon)
    # ------------------------------------------------------------------

    def _iniciar_consumer(self):
        def run():
            # Conexão de consumo
            conn = pika.BlockingConnection(
                pika.ConnectionParameters(host='localhost'))
            ch = conn.channel()
            ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

            # Conexão de publicação — separada e na mesma thread para ser thread-safe
            pub_conn = pika.BlockingConnection(
                pika.ConnectionParameters(host='localhost'))
            pub_ch = pub_conn.channel()
            pub_ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')
            self._pub_ch = pub_ch

            result = ch.queue_declare(queue='', exclusive=True)
            queue_name = result.method.queue

            ch.queue_bind(
                exchange=EXCHANGE,
                queue=queue_name,
                routing_key='promotion.vote',
            )

            def callback(ch_, method, properties, body):
                try:
                    envelope = json.loads(body)
                    payload   = envelope.get('payload', {})
                    signature = envelope.get('signature', '')

                    if not self._verify(payload, signature):
                        print("[Ranking] Assinatura inválida — mensagem descartada.")
                        return

                    id_promocao = payload.get('id_promocao')
                    voto        = payload.get('voto')

                    if not id_promocao or not voto:
                        print("[Ranking] Mensagem malformada — descartada.")
                        return

                    self._processar_voto(id_promocao, voto)

                except Exception as e:
                    print(f"[Ranking] Erro ao processar mensagem: {e}")

            ch.basic_consume(
                queue=queue_name,
                on_message_callback=callback,
                auto_ack=True,
            )
            ch.start_consuming()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def listar_ranking(self) -> list[dict]:
        """Retorna as promoções ordenadas por score decrescente."""
        return sorted(
            [{'id_promocao': k, **v} for k, v in self._votos.items()],
            key=lambda x: x['score'],
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Encerramento
    # ------------------------------------------------------------------

    def fechar(self):
        pass  # conexões são gerenciadas dentro da thread daemon


if __name__ == '__main__':
    ranking = Ranking()
    try:
        print("Aguardando eventos 'promotion.vote' no RabbitMQ... (Ctrl+C para encerrar)")
        # Mantém o processo vivo enquanto a thread daemon consome mensagens
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Ranking] Encerrando...")
    finally:
        ranking.fechar()
