import json
import os

import pika
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

EXCHANGE = 'promotion'
PRIVATE_KEY_PATH = os.path.join(os.path.dirname(__file__), 'private_key.der')
PUBLIC_KEY_PATH  = os.path.join(os.path.dirname(__file__), 'public_key.der')

GATEWAY_PUBLIC_KEY_PATH = os.path.join(BASE_DIR, '..', 'gateway', 'public_key.der')

def _ensure_keys():
    """Gera o par de chaves RSA do Gateway se ainda não existir."""
    if not os.path.exists(PRIVATE_KEY_PATH):
        key = RSA.generate(2048)
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(key.export_key('DER'))
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(key.publickey().export_key('DER'))

class PromotionService:  

    def __init__(self):
        _ensure_keys()

        with open(PRIVATE_KEY_PATH, 'rb') as f:
            self._private_key = RSA.import_key(f.read())

        with open(GATEWAY_PUBLIC_KEY_PATH, 'rb') as f:
            self._gateway_public_key = RSA.import_key(f.read())

        self.promocoes = {}

        # Canal de publicação (thread principal)
        self._conn = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        self._ch = self._conn.channel()
        self._ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

        print("Promotion iniciado com sucesso!")

    # ---------------------------------------------------------------
    # Segurança
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
    # Publicação
    # ---------------------------------------------------------------

    def publish_event(self, routing_key: str, payload: dict) -> str:
        """Assina e publica um evento."""
        signature = self.sign_message(payload)

        envelope = {
            'payload': payload,
            'signature': signature,
            'producer': 'promotion',
        }

        self._ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(envelope, ensure_ascii=False),
        )

        return signature
    
    # ---------------------------------------------------------------
    # Lógica principal
    # ---------------------------------------------------------------
    def registrar_promocao(self, payload: dict) -> dict:
        """
        Registra a promoção localmente e devolve a promoção publicada.
        """
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
            """Processa um evento promotion.received."""
            payload = envelope.get('payload')
            signature = envelope.get('signature')
            producer = envelope.get('producer')

            if not payload or not signature:
                print("[AVISO] Evento inválido: envelope incompleto.")
                return

            if producer != 'gateway':
                print("[AVISO] Evento descartado: produtor inesperado.")
                return

            if not self.verify_signature(payload, signature):
                print("[AVISO] Assinatura inválida. Evento descartado.")
                return

            promocao_id = payload.get('id')
            if not promocao_id:
                print("[AVISO] Promoção sem ID. Evento descartado.")
                return

            if promocao_id in self.promocoes:
                print(f"[AVISO] Promoção {promocao_id} já registrada. Ignorando duplicata.")
                return

            promocao_publicada = self.registrar_promocao(payload)
            published_signature = self.publish_event(
                'promotion.published',
                promocao_publicada
            )

            print(f"[OK] Promoção registrada e publicada:")
            print(f"     id         : {promocao_publicada['id']}")
            print(f"     titulo     : {promocao_publicada['titulo']}")
            print(f"     categoria  : {promocao_publicada['categoria']}")
            print(f"     assinatura : {published_signature[:32]}...")

# ---------------------------------------------------------------
# Consumo
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
                print(f"[ERRO] Falha ao processar promoção: {e}")

        self._ch.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=True,
        )

        print("Aguardando eventos 'promotion.received'...")
        self._ch.start_consuming()

# ---------------------------------------------------------------
# Utilidade
# ---------------------------------------------------------------

    def listar_promocoes_registradas(self) -> list[dict]:
        return list(self.promocoes.values())

    def fechar(self):
        try:
            if self._conn and self._conn.is_open:
                self._conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    service = PromotionService()
    try:
        service.iniciar_consumer()
    finally:
        service.fechar()