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


def _normalizar_categoria(categoria: str) -> str:
    """Remove acentos e converte para minúsculas para uso em routing keys."""
    nfkd = unicodedata.normalize('NFKD', categoria)
    sem_acento = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


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

        self._ids_notificados: set[str] = set()
        # Mapa id_promocao → categoria, necessário para publicar hot deals na categoria correta
        self._categorias: dict[str, str] = {}

        print("Notification Service iniciado com sucesso!")

    # ------------------------------------------------------------------
    # Validação de assinaturas dos produtores upstream
    # ------------------------------------------------------------------

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
        """Publica a notificação na routing key da categoria (sem assinatura — README isenta Notification)."""
        routing_key = f"promotion.{_normalizar_categoria(categoria)}"
        payload = {"mensagem": mensagem, "categoria": categoria}
        self._pub_ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload, ensure_ascii=False),
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

        promo_id = payload.get('id')
        if promo_id in self._ids_notificados:
            print(f"[Notificação] Promoção {promo_id} já notificada — duplicata descartada.")
            return
        self._ids_notificados.add(promo_id)

        categoria = payload.get('categoria', 'geral')
        titulo    = payload.get('titulo', 'Nova Promoção')
        preco     = payload.get('preco_promocional', 0)

        # Armazena categoria para uso posterior ao receber hot deal desta promoção
        if promo_id:
            self._categorias[promo_id] = categoria

        msg = f"Nova oferta: {titulo} por apenas R$ {preco:.2f}!"
        self._publish_notification(categoria, msg)

    def processar_destaque(self, envelope: dict):
        """Processa hot deals (vindos do MS Ranking)."""
        payload   = envelope.get('payload', {})
        signature = envelope.get('signature', '')

        if not self._verify(payload, signature, self._ranking_public_key):
            print("[Notificação] Assinatura do Ranking INVÁLIDA — descartado.")
            return

        id_promo  = payload.get('id_promocao', '?')
        destaque_key = f"highlight:{id_promo}"
        if destaque_key in self._ids_notificados:
            print(f"[Notificação] Destaque de {id_promo} já notificado — duplicata descartada.")
            return
        self._ids_notificados.add(destaque_key)

        score = payload.get('score', 0)
        msg = f"HOT DEAL! Promocao {id_promo} esta em destaque com score {score}!"

        # Publica na categoria original da promoção com "hot deal" — conforme README
        categoria = self._categorias.get(id_promo)
        if categoria:
            self._publish_notification(categoria, msg)

        # Publica também em 'destaque' para clientes inscritos em todas as promoções em destaque
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
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                print(f"[ERRO] Falha ao processar mensagem: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        self._ch.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)
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
