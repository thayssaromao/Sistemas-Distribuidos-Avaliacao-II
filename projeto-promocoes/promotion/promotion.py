import json
import os
import sys

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Chaves próprias do serviço
PRIVATE_KEY_PATH = os.path.join(BASE_DIR, 'private_key.der')
PUBLIC_KEY_PATH  = os.path.join(BASE_DIR, 'public_key.der')

# Chave pública do produtor (Gateway) - Deve ser copiada manualmente para esta pasta
GATEWAY_PUBLIC_KEY_PATH = os.path.join(BASE_DIR, 'gateway_public_key.der')

def _ensure_keys():
    """Gera o par de chaves RSA do Promotion se ainda não existir."""
    if not os.path.exists(PRIVATE_KEY_PATH):
        print("[INFO] Gerando novas chaves RSA para o Promotion Service...")
        key = RSA.generate(2048)
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(key.export_key('DER'))
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(key.publickey().export_key('DER'))

class PromotionService:  

    def __init__(self):
        _ensure_keys()

        # Carregar chave privada própria
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                self._private_key = RSA.import_key(f.read())
        except Exception as e:
            print(f"[ERRO] Falha ao carregar chave privada: {e}")
            sys.exit(1)

        # Carregar chave pública do Gateway (necessária para validar promotion.received)
        if not os.path.exists(GATEWAY_PUBLIC_KEY_PATH):
            print(f"\n[ERRO CRÍTICO] Chave pública do Gateway não encontrada!")
            print(f"Caminho esperado: {GATEWAY_PUBLIC_KEY_PATH}")
            print("-" * 60)
            print("COMO RESOLVER:")
            print("1. Inicie o Gateway para gerar as chaves dele.")
            print("2. Copie 'gateway/public_key.der' para 'promotion/gateway_public_key.der'.")
            print("-" * 60)
            sys.exit(1)

        with open(GATEWAY_PUBLIC_KEY_PATH, 'rb') as f:
            self._gateway_public_key = RSA.import_key(f.read())

        self.promocoes = {}

        # Conexão com RabbitMQ
        try:
            self._conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            self._ch = self._conn.channel()
            self._ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao RabbitMQ: {e}")
            sys.exit(1)

        print("Promotion Service iniciado com sucesso!")

    # ---------------------------------------------------------------
    # Segurança (RSA-SHA256)
    # ---------------------------------------------------------------

    def sign_message(self, payload: dict) -> str:
        """Assina um payload com a chave privada do Promotion."""
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        h = SHA256.new(data)
        signature = pkcs1_15.new(self._private_key).sign(h)
        return signature.hex()

    def verify_signature(self, payload: dict, signature_hex: str) -> bool:
        """Valida a assinatura do payload usando a chave pública do Gateway."""
        try:
            data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
            h = SHA256.new(data)
            signature = bytes.fromhex(signature_hex)
            pkcs1_15.new(self._gateway_public_key).verify(h, signature)
            return True
        except (ValueError, TypeError):
            return False
        
    # ---------------------------------------------------------------
    # Publicação de Eventos
    # ---------------------------------------------------------------

    def publish_event(self, routing_key: str, payload: dict) -> str:
        """Assina e publica um evento conforme o padrão do README."""
        signature = self.sign_message(payload)

        envelope = {
            'payload': payload,
            'signature': signature,  # Voltando para minúsculo para compatibilidade
        }

        self._ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(envelope, ensure_ascii=False),
        )

        return signature
    
    # ---------------------------------------------------------------
    # Lógica de Negócio
    # ---------------------------------------------------------------
    def registrar_promocao(self, payload: dict) -> dict:
        """Registra a promoção localmente."""
        promocao = {
            'id': payload['id'],
            'titulo': payload['titulo'],
            'descricao': payload['descricao'],
            'categoria': payload['categoria'],
            'preco_original': payload['preco_original'],
            'preco_promocional': payload['preco_promocional'],
            'votos': {
                'positivos': 0,
                'negativos': 0,
            }
        }

        self.promocoes[promocao['id']] = promocao
        return promocao

    def processar_promocao_recebida(self, envelope: dict):
            """Processa um evento 'promotion.received' do Gateway."""
            payload = envelope.get('payload')
            signature = envelope.get('signature') # Voltando para minúsculo

            if not payload or not signature:
                print("[AVISO] Evento inválido: envelope incompleto (Payload ou Signature ausente).")
                return

            # Validação obrigatória por README
            if not self.verify_signature(payload, signature):
                print("[AVISO] Assinatura do Gateway INVÁLIDA. Evento descartado.")
                return

            promocao_id = payload.get('id')
            if not promocao_id:
                print("[AVISO] Promoção sem ID. Evento descartado.")
                return

            if promocao_id in self.promocoes:
                print(f"[AVISO] Promoção {promocao_id} já registrada. Ignorando duplicata.")
                return

            # Se válido, registra e publica que está pronta
            promocao_publicada = self.registrar_promocao(payload)
            published_signature = self.publish_event(
                'promotion.published',
                promocao_publicada
            )

            print(f"[OK] Promoção Validada e Publicada:")
            print(f"     ID: {promocao_publicada['id']}")
            print(f"     Título: {promocao_publicada['titulo']}")
            print(f"     Assinatura Gerada: {published_signature[:16]}...")

# ---------------------------------------------------------------
# Consumo de Eventos
# ---------------------------------------------------------------

    def iniciar_consumer(self):
        result = self._ch.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue

        self._ch.queue_bind(
            exchange=EXCHANGE,
            queue=queue_name,
            routing_key='promotion.received',
        )

        def callback(ch, method, properties, body):
            try:
                envelope = json.loads(body)
                self.processar_promocao_recebida(envelope)
            except json.JSONDecodeError:
                print("[ERRO] Mensagem recebida não é um JSON válido.")
            except Exception as e:
                print(f"[ERRO] Falha ao processar evento: {e}")

        self._ch.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=True,
        )

        print("Aguardando eventos 'promotion.received' no RabbitMQ...")
        self._ch.start_consuming()

    def fechar(self):
        try:
            if hasattr(self, '_conn') and self._conn.is_open:
                self._conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    service = PromotionService()
    try:
        service.iniciar_consumer()
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando Promotion Service...")
    finally:
        service.fechar()
