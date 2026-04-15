import json

import pika

EXCHANGE = 'promotion'


def main():
    conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = conn.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    # Categorias de interesse
    categorias_interesse = ['livros', 'jogos', 'eletronicos']

    for cat in categorias_interesse:
        channel.queue_bind(exchange=EXCHANGE, queue=queue_name,
                           routing_key=f'promotion.{cat}')

    # Hot deals publicados pelo Notification (promotion.destaque)
    channel.queue_bind(exchange=EXCHANGE, queue=queue_name,
                       routing_key='promotion.destaque')

    print(f"[*] Aguardando promoções para: {', '.join(categorias_interesse)} + destaques.")
    print("[*] Pressione CTRL+C para sair.\n")

    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            print("[Consumer] Mensagem não é JSON válido — descartada.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        print("\n" + "=" * 50)
        if method.routing_key == 'promotion.destaque':
            print(f"[DESTAQUE] {payload.get('mensagem', payload)}")
        else:
            print(f"[NOVA PROMOCAO] {payload.get('mensagem', payload)}")
        print("=" * 50)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)
    channel.start_consuming()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaindo...")
