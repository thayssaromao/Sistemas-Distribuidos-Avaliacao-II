import pika
import json
import os

from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA


def __init__(self):
    self.connection = pika.BlockingConnection(
        pika.ConnectionParameters(host='localhost'))
    self.channel = self.connection.channel()

    self.exchange = 'promocoes' #exchange central do sistema

    self.channel.exchange_declare(exchange= self.exchange, exchange_type='topic')

    #carregar a private key:
    with open('private_key.der', 'rb') as f:
        self.private_key = RSA.import_key(f.read())

    self.promocoes_validas = []

    print("Gateway iniciado com sucesso!!")


#def sign_message(self, message: str) -> str:
        
    
#def publish_event(self, routing_key: str, payload: dict):
        
    
def cadastrar_promocao(self, id_promocao, nome, categoria, preco):
    mensagem = {
        "id": id_promocao,
        "nome": nome,
        "categoria": categoria,
        "preço": preco
    }

    self.channel.basic_publish(
        exchange= self.exchange, 
        routing_key='promocao.recebida', 
        body=json.dumps(mensagem))
    
    print(f"promoção enviada para validação")      
    
def votar_promocao(self, id_promocao, voto): 
    #lembrar de colocar uma verificação para voto inválido
    mensagem = {
        "id": id_promocao,
        "voto": voto
    }

    self.channel.basic_publish(
    exchange= self.exchange, 
    routing_key='promocao.voto', 
    body=json.dumps(mensagem))
    
    print(f"Voto enviado para processamento")  
         
def consumir_promocoes_publicadas(self):
    result = self.channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    self.channel.queue.bind(
        exchange=self.exchange,
        queue=queue_name,
        routing_key='promocao.publicada'
    )

    def callback(ch, method, properties, body):
        mensagem = json.loads(body)
        self.promocoes_validas.append(mensagem)
        print("Promoção validada recebida:", mensagem)

    self.channel.basic_consume(
        queue=queue_name,
        on_message_callback=callback,
        auto_ack=True
    )

    print("Aguardando promções publicadas")
    self.channel.start_consuming()        
    
def listar_promocoes(self):
    return self.promocoes_validas        