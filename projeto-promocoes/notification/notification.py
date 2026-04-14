import json
import os
import sys
import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'

# Caminhos das chaves (simulação direta via os.path)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMOTION_PUBLIC_KEY_PATH = os.path.join(_BASE_DIR, '..', 'promotion', 'public_key.der')
RANKING_PUBLIC_KEY_PATH   = os.path.join(_BASE_DIR, '..', 'ranking', 'public_key.der')

class NotificationService:
    def __init__(self):
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
        
        # Conexão com RabbitMQ
        try:
            self._conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            self._ch = self._conn.channel()
            self._ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao RabbitMQ: {e}")
            sys.exit(1)

        print("Notification Service iniciado com sucesso!")

    def _verify(self, payload: dict, signature_hex: str, public_key) -> bool:
        """Verifica a assinatura digital do payload."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        try:
            pkcs1_15.new(public_key).verify(h, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            return False

    def _publish_notification(self, categoria: str, mensagem: str):
        """Publica a notificação na routing key da categoria."""
        routing_key = f"promotion.{categoria}"
        payload = {"mensagem": mensagem}

        self._ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload, ensure_ascii=False)
        )
        print(f"[Notificação] Publicado em '{routing_key}': {mensagem}")

    def processar_publicacao(self, envelope: dict):
        """Processa novas promoções (vindas do MS Promotion)."""
        payload = envelope.get('payload', {})
        signature = envelope.get('signature', '')

        if self._verify(payload, signature, self._promotion_public_key):
            categoria = payload.get('category', payload.get('categoria', 'geral'))
            titulo = payload.get('titulo', 'Nova Promoção')
            preco = payload.get('preco_promocional', 0)

            msg = f"Nova oferta: {titulo} por apenas R$ {preco:.2f}!"
            self._publish_notification(categoria, msg)
        else:
            print("[Notificação] Assinatura do Promotion INVÁLIDA.")

    def processar_destaque(self, envelope: dict):
        """Processa hot deals (vindos do MS Ranking)."""
        payload = envelope.get('payload', {}) # Corrigido de 'Payload' para 'payload'
        signature = envelope.get('signature', '') # Corrigido de 'singature' para 'signature'

        if self._verify(payload, signature, self._ranking_public_key):
            id_promo = payload.get('id_promocao', '?')
            msg = f"🔥 HOT DEAL! Promoção {id_promo} está em destaque!"
            self._publish_notification("destaque", msg)
        else:
            print("[Notificação] Assinatura do Ranking INVÁLIDA.")

    def iniciar(self):
        result = self._ch.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue

        # Ouve os dois tipos de eventos necessários
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

if __name__ == '__main__':
    service = NotificationService()
    try:
        service.iniciar()
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando Notificações...")
    finally:
        if hasattr(service, '_conn') and service._conn.is_open:
            service._conn.close()
