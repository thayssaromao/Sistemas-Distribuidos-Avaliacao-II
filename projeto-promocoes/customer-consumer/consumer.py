import pika
import json

EXCHANGE = "promotion"

def callback(ch, method, properties, body):
    envelope = json.loads(body)
    payload = envelope.get('payload', {})

    print("\n" + "="*50)

    if method.routing_key == 'promotion.highlight':
        print(f"[DESTAQUE] Promoção{payload.get('id_promocao')} atingiu {payload.get('score')} pontos!")
    else:
        print(f"📢 [NOVA PROMOÇÃO] Categoria: {payload.get('categoria')}")
        print(f"Título: {payload.get('titulo')}")
        print(f"Preço: R$ {payload.get('preco_promocional'):.2f} (era R$ {payload.get('preco_original'):.2f})")
        print(f"Descrição: {payload.get('descricao')}")
        print("="*50)

def main():
    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = conn.channel()

    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic")

    #Fila exclusiva para o cliente
    result = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue

    categorias_interesse = ['eletronicos', 'livros', 'games']

    print(f"[*] Aguardando promoções para categorias: {', '.join(categorias_interesse)}. Pressione CTRL+C para sair.")

    # Bind da fila com as routing keys desejadas
    for cat in categorias_interesse:
        routing_key = f"promocao.{cat}"
        channel.queue_bind(exchange=EXCHANGE, queue=queue_name, routing_key=routing_key)

    #Binding para receber destaques (Hot deals)
    channel.queue_bind(exchange=EXCHANGE, queue=queue_name, routing_key="promotion.highlight")

    channel.basic_consume(queue=queue_name,
        on_message_callback=callback, auto_ack=True)
    
    channel.start_consuming()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaindo...")