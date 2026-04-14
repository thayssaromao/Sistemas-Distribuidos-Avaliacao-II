import json
import os
import sys
import unicodedata

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMOTION_PUBLIC_KEY_PATH = os.path.join(_BASE_DIR, '..', 'promotion', 'public_key.der')
RANKING_PUBLIC_KEY_PATH   = os.path.join(_BASE_DIR, '..', 'ranking',   'public_key.der')
PRIVATE_KEY_PATH          = os.path.join(_BASE_DIR, 'private_key.der')
PUBLIC_KEY_PATH           = os.path.join(_BASE_DIR, 'public_key.der')


def _ensure_keys():
    """Gera o par de chaves RSA do Notification Service se ainda não existir."""
    if not os.path.exists(PRIVATE_KEY_PATH):
        key = RSA.generate(2048)
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(key.export_key('DER'))
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(key.publickey().export_key('DER'))


def _normalizar_categoria(categoria: str) -> str:
    """Remove acentos e converte para minúsculas para uso em routing keys."""
    nfkd = unicodedata.normalize('NFKD', categoria)
    sem_acento = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


class NotificationService:
    def __init__(self):
        _ensure_keys()

        with open(PRIVATE_KEY_PATH, 'rb') as f:
            self._private_key = RSA.import_key(f.read())

        # Carregar chaves públicas para validação
        try:
            with open(PROMOTION_PUBLIC_KEY_PATH, 'rb') as f:
                self._promotion_public_key = RSA.import_key(f.read())

            with open(RANKING_PUBLIC_KEY_PATH, 'rb') as f:
                self._ranking_public_key = RSA.import_key(f.read())
        except FileNotFoundError as e:
            print(f"[ERRO] Chave pública não encontrada: {e}")
            print("Certifique-se de que os serviços Promotion e Ranking foram iniciados.")
            sys.exit(1)

        # Conexão de consumo
        try:
            self._conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            self._ch = self._conn.channel()
            self._ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao RabbitMQ (consumo): {e}")
            sys.exit(1)

        # Conexão separada para publicação — obrigatório com BlockingConnection
        # (publicar dentro de um callback de consumo no mesmo canal causa deadlock)
        try:
            self._pub_conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            self._pub_ch = self._pub_conn.channel()
            self._pub_ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao RabbitMQ (publicação): {e}")
            sys.exit(1)

        print("Notification Service iniciado com sucesso!")

    # ------------------------------------------------------------------
    # Assinatura e validação
    # ------------------------------------------------------------------

    def _sign(self, payload: dict) -> str:
        """Assina o payload com a chave privada do Notification Service."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        return pkcs1_15.new(self._private_key).sign(h).hex()

    def _verify(self, payload: dict, signature_hex: str, public_key) -> bool:
        """Verifica a assinatura digital do payload."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        try:
            pkcs1_15.new(public_key).verify(h, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Publicação de notificações
    # ------------------------------------------------------------------

    def _publish_notification(self, categoria: str, mensagem: str):
        """Assina e publica a notificação na routing key da categoria."""
        routing_key = f"promotion.{_normalizar_categoria(categoria)}"
        payload = {"mensagem": mensagem, "categoria": categoria}
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
        print(f"[Notificação] Publicado em '{routing_key}': {mensagem}")

    # ------------------------------------------------------------------
    # Processadores de eventos recebidos
    # ------------------------------------------------------------------

    def processar_publicacao(self, envelope: dict):
        """Processa novas promoções (vindas do MS Promotion)."""
        payload   = envelope.get('payload', {})
        signature = envelope.get('signature', '')

        if not self._verify(payload, signature, self._promotion_public_key):
            print("[Notificação] Assinatura do Promotion INVÁLIDA — descartado.")
            return

        categoria = payload.get('categoria', 'geral')
        titulo    = payload.get('titulo', 'Nova Promoção')
        preco     = payload.get('preco_promocional', 0)

        msg = f"Nova oferta: {titulo} por apenas R$ {preco:.2f}!"
        self._publish_notification(categoria, msg)

    def processar_destaque(self, envelope: dict):
        """Processa hot deals (vindos do MS Ranking)."""
        payload   = envelope.get('payload', {})
        signature = envelope.get('signature', '')

        if not self._verify(payload, signature, self._ranking_public_key):
            print("[Notificação] Assinatura do Ranking INVÁLIDA — descartado.")
            return

        id_promo = payload.get('id_promocao', '?')
        score    = payload.get('score', 0)
        msg = f"HOT DEAL! Promocao {id_promo} esta em destaque com score {score}!"
        self._publish_notification("destaque", msg)

    # ------------------------------------------------------------------
    # Loop de consumo
    # ------------------------------------------------------------------

    def iniciar(self):
        result = self._ch.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue

        self._ch.queue_bind(exchange=EXCHANGE, queue=queue_name, routing_key='promotion.published')
        self._ch.queue_bind(exchange=EXCHANGE, queue=queue_name, routing_key='promotion.highlight')

        def callback(ch, method, properties, body):
            try:
                envelope = json.loads(body)
                if method.routing_key == 'promotion.published':
                    self.processar_publicacao(envelope)
                elif method.routing_key == 'promotion.highlight':
                    self.processar_destaque(envelope)
            except Exception as e:
                print(f"[ERRO] Falha ao processar mensagem: {e}")

        self._ch.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
        print("Aguardando 'promotion.published' e 'promotion.highlight'...")
        self._ch.start_consuming()

    def fechar(self):
        for conn in (self._conn, self._pub_conn):
            try:
                if hasattr(self, '_conn') and conn.is_open:
                    conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    service = NotificationService()
    try:
        service.iniciar()
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando Notificações...")
    finally:
        service.fechar()
