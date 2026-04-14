import json
import os
import sys

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTIFICATION_PUBLIC_KEY_PATH = os.path.join(_BASE_DIR, '..', 'notification', 'public_key.der')
RANKING_PUBLIC_KEY_PATH      = os.path.join(_BASE_DIR, '..', 'ranking',      'public_key.der')


def _load_key(path: str, nome: str):
    if not os.path.exists(path):
        print(f"[ERRO] Chave pública do {nome} não encontrada em: {path}")
        print(f"Certifique-se de que o {nome} foi iniciado antes do Consumer.")
        sys.exit(1)
    with open(path, 'rb') as f:
        return RSA.import_key(f.read())


def _verify(payload: dict, signature_hex: str, public_key) -> bool:
    """Verifica a assinatura RSA-SHA256 do payload."""
    try:
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        pkcs1_15.new(public_key).verify(h, bytes.fromhex(signature_hex))
        return True
    except (ValueError, TypeError):
        return False


def main():
    notification_pub_key = _load_key(NOTIFICATION_PUBLIC_KEY_PATH, 'Notification Service')
    ranking_pub_key      = _load_key(RANKING_PUBLIC_KEY_PATH,      'Ranking Service')

    conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = conn.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    # Categorias de interesse — devem coincidir com o que o Notification publica
    # (sem acentos, minúsculas, prefixo promotion.)
    categorias_interesse = ['livros', 'jogos', 'eletronicos']

    for cat in categorias_interesse:
        channel.queue_bind(exchange=EXCHANGE, queue=queue_name,
                           routing_key=f'promotion.{cat}')

    # Hot deals publicados pelo Ranking via Notification
    channel.queue_bind(exchange=EXCHANGE, queue=queue_name,
                       routing_key='promotion.destaque')

    print(f"[*] Aguardando promoções para: {', '.join(categorias_interesse)} + destaques.")
    print("[*] Pressione CTRL+C para sair.\n")

    def callback(ch, method, properties, body):
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError:
            print("[Consumer] Mensagem não é JSON válido — descartada.")
            return

        payload   = envelope.get('payload', {})
        signature = envelope.get('signature', '')

        if not payload or not signature:
            print("[Consumer] Envelope incompleto — descartado.")
            return

        # Destaques são assinados pelo Ranking; notificações de promoção pelo Notification
        if method.routing_key == 'promotion.destaque':
            pub_key = ranking_pub_key
        else:
            pub_key = notification_pub_key

        if not _verify(payload, signature, pub_key):
            print(f"[Consumer] Assinatura INVÁLIDA em '{method.routing_key}' — descartado.")
            return

        print("\n" + "=" * 50)
        if method.routing_key == 'promotion.destaque':
            print(f"[DESTAQUE] {payload.get('mensagem', payload)}")
        else:
            print(f"[NOVA PROMOCAO] {payload.get('mensagem', payload)}")
        print("=" * 50)

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
    channel.start_consuming()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaindo...")
