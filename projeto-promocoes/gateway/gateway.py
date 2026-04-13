import pika
import sys

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

exchange = 'promocoes'

channel.exchange_declare(exchange= exchange, exchange_type='topic')

severity = sys.argv[1] if len(sys.argv) > 1 else 'info'
message = ' '.join(sys.argv[2:]) or 'Hello World!'

# exemplo: cadastrar promoção
routing_key = 'promocao.recebida'
message = 'Promoção: Livro Python por R$50'

channel.basic_publish(
    exchange= exchange, routing_key=severity, body=message)
print(f" [x] Sent {severity}:{message}")
connection.close()