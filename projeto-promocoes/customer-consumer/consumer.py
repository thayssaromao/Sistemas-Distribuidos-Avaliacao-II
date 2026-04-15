import json
import os
import re
from datetime import datetime

import pika

EXCHANGE = 'promotion'
LARGURA  = 60

# Categorias de interesse — altere conforme necessário
CATEGORIAS_INTERESSE = ['livros', 'jogos', 'eletronicos']


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

class C:
    RST  = '\033[0m'
    BOLD = '\033[1m'
    DIM  = '\033[2m'
    R = '\033[31m'; G = '\033[32m'; Y = '\033[33m'
    B = '\033[34m'; M = '\033[35m'; CY = '\033[36m'
    BR = '\033[91m'; BG = '\033[92m'; BY = '\033[93m'
    BB = '\033[94m'; BM = '\033[95m'; BCY = '\033[96m'
    W  = '\033[97m'


def s(*estilos: str, text: str) -> str:
    return ''.join(estilos) + text + C.RST


def vlen(texto: str) -> int:
    return len(re.sub(r'\033\[[0-9;]*m', '', texto))


def limpar():
    os.system('clear' if os.name == 'posix' else 'cls')


# ---------------------------------------------------------------------------
# Componentes visuais
# ---------------------------------------------------------------------------

def cabecalho_inicial():
    limpar()
    borda = '═' * (LARGURA - 2)
    print(s(C.BOLD, C.BCY, text=f'╔{borda}╗'))
    titulo = '  CONSUMER — NOTIFICACOES DE PROMOCOES'
    espaço = LARGURA - 2 - len(titulo)
    print(s(C.BOLD, C.BCY, text='║') + s(C.BOLD, C.W, text=titulo) + ' ' * espaço + s(C.BOLD, C.BCY, text='║'))
    cats = f'  Categorias: {", ".join(CATEGORIAS_INTERESSE)} + destaques'
    espaço2 = LARGURA - 2 - len(cats)
    print(s(C.BOLD, C.BCY, text='║') + s(C.DIM, text=cats) + ' ' * espaço2 + s(C.BOLD, C.BCY, text='║'))
    print(s(C.BOLD, C.BCY, text=f'╚{borda}╝'))
    print()


def notificacao_nova_promocao(mensagem: str, categoria: str, hora: str):
    """Card para uma nova promoção publicada."""
    in_w = LARGURA - 4
    cor  = C.BCY

    cab = f'  NOVA PROMOCAO  ·  {categoria.upper()}'
    espaço_cab = LARGURA - 2 - len(cab) - len(hora) - 2
    print()
    print(s(C.BOLD, cor, text='╔' + '═' * (LARGURA - 2) + '╗'))
    print(
        s(C.BOLD, cor, text='║')
        + s(C.BOLD, C.W,  text=f'  NOVA PROMOCAO')
        + s(C.DIM, text=f'  ·  {categoria.upper()}')
        + ' ' * espaço_cab
        + s(C.DIM, text=hora)
        + ' '
        + s(C.BOLD, cor, text='║')
    )
    print(s(C.BOLD, cor, text='╠' + '═' * (LARGURA - 2) + '╣'))

    msg = mensagem
    linhas = []
    while len(msg) > in_w:
        linhas.append(msg[:in_w])
        msg = msg[in_w:]
    linhas.append(msg)

    for linha in linhas:
        espaço = in_w - len(linha)
        print(
            s(C.BOLD, cor, text='║')
            + '  '
            + linha
            + ' ' * espaço
            + '  '
            + s(C.BOLD, cor, text='║')
        )

    print(s(C.BOLD, cor, text='╚' + '═' * (LARGURA - 2) + '╝'))


def notificacao_destaque(mensagem: str, hora: str):
    """Card para promoção em destaque (hot deal)."""
    in_w = LARGURA - 4
    cor  = C.BM

    cab_label = '  *** HOT DEAL ***'
    espaço_cab = LARGURA - 2 - len(cab_label) - len(hora) - 2
    print()
    print(s(C.BOLD, cor, text='╔' + '═' * (LARGURA - 2) + '╗'))
    print(
        s(C.BOLD, cor, text='║')
        + s(C.BOLD, C.BM, text=cab_label)
        + ' ' * espaço_cab
        + s(C.DIM, text=hora)
        + ' '
        + s(C.BOLD, cor, text='║')
    )
    print(s(C.BOLD, cor, text='╠' + '═' * (LARGURA - 2) + '╣'))

    msg = mensagem
    linhas = []
    while len(msg) > in_w:
        linhas.append(msg[:in_w])
        msg = msg[in_w:]
    linhas.append(msg)

    for linha in linhas:
        espaço = in_w - len(linha)
        print(
            s(C.BOLD, cor, text='║')
            + '  '
            + s(C.BY, text=linha)
            + ' ' * espaço
            + '  '
            + s(C.BOLD, cor, text='║')
        )

    print(s(C.BOLD, cor, text='╚' + '═' * (LARGURA - 2) + '╝'))


def _linha_status(total_recebidas: int, total_hot: int):
    """Reimprime a linha de status no topo sem limpar a tela."""
    status = (
        f'  {s(C.DIM, text="Recebidas:")} {s(C.BG, C.BOLD, text=str(total_recebidas))}'
        f'  {s(C.DIM, text="Hot deals:")} {s(C.BM, C.BOLD, text=str(total_hot))}'
        f'  {s(C.DIM, text="Ctrl+C para sair")}'
    )
    print(status)
    print(s(C.DIM, text='  ' + '─' * (LARGURA - 2)))


# ---------------------------------------------------------------------------
# Consumer principal
# ---------------------------------------------------------------------------

def main():
    cabecalho_inicial()

    conn    = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = conn.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type='topic')

    result     = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    for cat in CATEGORIAS_INTERESSE:
        channel.queue_bind(exchange=EXCHANGE, queue=queue_name,
                           routing_key=f'promotion.{cat}')
    channel.queue_bind(exchange=EXCHANGE, queue=queue_name,
                       routing_key='promotion.destaque')

    print(s(C.BG, C.BOLD, text='  Conectado.'))
    print(s(C.DIM, text=f'  Inscrito em: {", ".join(f"promotion.{c}" for c in CATEGORIAS_INTERESSE)}, promotion.destaque'))
    print(s(C.DIM, text='  Aguardando notificacoes...\n'))
    print(s(C.DIM, text='  ' + '─' * (LARGURA - 2)))

    contadores = {'total': 0, 'hot': 0}

    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        hora      = datetime.now().strftime('%H:%M:%S')
        mensagem  = payload.get('mensagem', str(payload))
        categoria = payload.get('categoria', method.routing_key.split('.')[-1])
        eh_destaque = method.routing_key == 'promotion.destaque'

        contadores['total'] += 1
        if eh_destaque:
            contadores['hot'] += 1
            notificacao_destaque(mensagem, hora)
        else:
            notificacao_nova_promocao(mensagem, categoria, hora)

        _linha_status(contadores['total'], contadores['hot'])
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print()
        print(s(C.DIM, text='\n  Encerrando consumer...'))
        channel.stop_consuming()
    finally:
        conn.close()
        print(s(C.DIM, text=f'  Total recebidas: {contadores["total"]}  |  Hot deals: {contadores["hot"]}'))
        print()


if __name__ == '__main__':
    main()
