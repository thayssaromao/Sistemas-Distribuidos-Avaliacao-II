import os
import re
import time
from datetime import datetime

from gateway import Gateway

CATEGORIAS_VALIDAS = ["livros", "jogos", "eletronicos", "roupas", "alimentos"]
LARGURA = 62
HIGHLIGHT_SCORE = 5


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

class C:
    RST  = '\033[0m'
    BOLD = '\033[1m'
    DIM  = '\033[2m'
    ITAL = '\033[3m'
    # Cores normais
    R = '\033[31m'; G = '\033[32m'; Y = '\033[33m'
    B = '\033[34m'; M = '\033[35m'; CY = '\033[36m'
    # Cores brilhantes
    BR = '\033[91m'; BG = '\033[92m'; BY = '\033[93m'
    BB = '\033[94m'; BM = '\033[95m'; BCY = '\033[96m'
    W  = '\033[97m'


def s(*estilos: str, text: str) -> str:
    """Aplica estilos ANSI e reseta ao final."""
    return ''.join(estilos) + text + C.RST


def vlen(texto: str) -> int:
    """Comprimento visual (ignora escapes ANSI)."""
    return len(re.sub(r'\033\[[0-9;]*m', '', texto))


def pad(texto: str, largura: int, alinhar: str = 'esq') -> str:
    """Padding respeitando comprimento visual."""
    diff = largura - vlen(texto)
    if diff <= 0:
        return texto
    return (' ' * diff + texto) if alinhar == 'dir' else (texto + ' ' * diff)


# ---------------------------------------------------------------------------
# Primitivas de UI
# ---------------------------------------------------------------------------

def limpar():
    os.system('clear' if os.name == 'posix' else 'cls')


def cabecalho(titulo: str, info: str = '', cor: str = C.BCY):
    borda = s(C.BOLD, cor, text='═' * (LARGURA - 2))
    print(s(C.BOLD, cor, text='╔') + borda + s(C.BOLD, cor, text='╗'))
    t = f'  {titulo}'
    espaço = LARGURA - 2 - len(t)
    print(
        s(C.BOLD, cor, text='║')
        + s(C.BOLD, C.W, text=t)
        + ' ' * espaço
        + s(C.BOLD, cor, text='║')
    )
    if info:
        i = f'  {info}'
        espaço2 = LARGURA - 2 - len(i)
        print(
            s(C.BOLD, cor, text='║')
            + s(C.DIM, text=i)
            + ' ' * espaço2
            + s(C.BOLD, cor, text='║')
        )
    print(s(C.BOLD, cor, text='╚') + borda + s(C.BOLD, cor, text='╝'))


def linha_sec(titulo: str = ''):
    if titulo:
        resto = '─' * (LARGURA - 5 - len(titulo))
        print('\n' + s(C.DIM, text=f'  ┄ {titulo} {resto}'))
    else:
        print(s(C.DIM, text='  ' + '─' * (LARGURA - 2)))


def tag_ok(msg: str):
    print(f'\n  {s(C.BG, C.BOLD, text="OK")}  {msg}')


def tag_erro(msg: str):
    print(f'\n  {s(C.BR, C.BOLD, text="ERRO")}  {s(C.BR, text=msg)}')


def tag_aviso(msg: str):
    print(f'\n  {s(C.BY, C.BOLD, text="AVISO")}  {s(C.BY, text=msg)}')


def enter():
    print()
    input(s(C.DIM, text='  Pressione ENTER para continuar... '))


def prompt(label: str) -> str:
    return input(f'  {s(C.DIM, text=label)} ').strip()


def rodape_evento(routing_key: str, id_: str, assinatura: str):
    linha_sec('Evento publicado')
    print(f'\n  {s(C.DIM, text="routing key")}  {s(C.BCY, text=routing_key)}')
    print(f'  {s(C.DIM, text="id         ")}  {s(C.DIM, text=id_)}')
    print(f'  {s(C.DIM, text="assinatura ")}  {s(C.DIM, text=assinatura[:48])}...')


# ---------------------------------------------------------------------------
# Exibição de promoções
# ---------------------------------------------------------------------------

def _badge_hot() -> str:
    return s(C.BM, C.BOLD, text=' HOT ')


def _score_bar(pos: int, neg: int) -> str:
    score = pos - neg
    cor = C.BG if score >= HIGHLIGHT_SCORE else (C.BY if score > 0 else C.BR if score < 0 else C.DIM)
    return (
        s(C.BG,  text=f'+{pos}')
        + s(C.DIM, text=' / ')
        + s(C.BR,  text=f'-{neg}')
        + s(C.DIM, text=f'  score ')
        + s(cor, C.BOLD, text=f'{score:+}')
    )


def _linha_tabela(num: str, titulo: str, categoria: str,
                  preco: str, desconto: str, votos: str, hot: bool) -> str:
    n   = pad(s(C.BOLD, C.W, text=num),    4)
    t   = pad(s(C.W if hot else C.RST, text=titulo[:28]), 28 + (len(s(C.W, text='')) if hot else 0))
    cat = pad(s(C.BCY, text=categoria[:10]), 10 + len(s(C.BCY, text='')))
    prc = pad(s(C.BG,  text=preco),  11 + len(s(C.BG, text='')), 'dir')
    dsc = pad(s(C.BY,  text=desconto), 5 + len(s(C.BY, text='')), 'dir')
    v   = votos
    h   = ('  ' + _badge_hot()) if hot else ''
    return f'  {n} {t}  {cat}  {prc}  {dsc}  {v}{h}'


def tabela_promocoes(promocoes: list, mostrar_descricao: bool = False):
    cab = (
        f'  {pad("  #", 4)} {pad("Titulo", 28)}  {pad("Categoria", 10)}  '
        f'{pad("Preco", 11, "dir")}  {pad("Desc.", 5, "dir")}  Votos'
    )
    print(s(C.DIM, text=cab))
    print(s(C.DIM, text='  ' + '─' * (LARGURA - 2)))

    for i, p in enumerate(promocoes, 1):
        preco_orig = p.get('preco_original', 0)
        preco_prom = p.get('preco_promocional', 0)
        desconto   = 100 * (1 - preco_prom / preco_orig) if preco_orig else 0
        votos      = p.get('votos', {})
        pos        = votos.get('positivos', 0)
        neg        = votos.get('negativos', 0)
        hot        = (pos - neg) >= HIGHLIGHT_SCORE

        vt = s(C.BG, text=f'+{pos}') + s(C.DIM, text='/') + s(C.BR, text=f'-{neg}')

        print(_linha_tabela(
            num=str(i),
            titulo=p.get('titulo', '?'),
            categoria=p.get('categoria', '?'),
            preco=f'R${preco_prom:>8.2f}',
            desconto=f'-{desconto:>3.0f}%',
            votos=vt,
            hot=hot,
        ))

        if mostrar_descricao and p.get('descricao'):
            desc = p['descricao']
            if len(desc) > LARGURA - 12:
                desc = desc[:LARGURA - 15] + '...'
            print(s(C.DIM, text=f'        {desc}'))

    print()


def card_promocao(p: dict, numero: int):
    preco_orig = p.get('preco_original', 0)
    preco_prom = p.get('preco_promocional', 0)
    desconto   = 100 * (1 - preco_prom / preco_orig) if preco_orig else 0
    votos      = p.get('votos', {})
    pos        = votos.get('positivos', 0)
    neg        = votos.get('negativos', 0)
    hot        = (pos - neg) >= HIGHLIGHT_SCORE

    cor = C.BM if hot else C.BCY
    in_w = LARGURA - 6  # largura interna do card

    def linha_card(conteudo: str):
        vis = vlen(conteudo)
        espaço = in_w - vis
        print(s(C.BOLD, cor, text='  │') + ' ' + conteudo + ' ' * max(0, espaço) + s(C.BOLD, cor, text=' │'))

    titulo_card = f'  Promocao #{numero}'
    print(s(C.BOLD, cor, text=f'  ╭─ {titulo_card} ' + '─' * (LARGURA - 8 - len(titulo_card)) + '╮'))

    linha_card(s(C.BOLD, C.W, text=p.get('titulo', '?')))
    linha_card(
        s(C.BCY, text=p.get('categoria', '?'))
        + s(C.DIM, text='  ·  ')
        + s(C.BG, text=f"R$ {preco_prom:.2f}")
        + s(C.DIM, text=f"  (de R$ {preco_orig:.2f},")
        + s(C.BY, text=f" -{desconto:.0f}%")
        + s(C.DIM, text=")")
    )
    linha_card(_score_bar(pos, neg))
    if p.get('descricao'):
        desc = p['descricao']
        if len(desc) > in_w - 2:
            desc = desc[:in_w - 5] + '...'
        linha_card(s(C.DIM, text=desc))
    if hot:
        linha_card(s(C.BM, C.BOLD, text='*** PROMOCAO EM DESTAQUE (HOT DEAL) ***'))

    print(s(C.BOLD, cor, text='  ╰' + '─' * (LARGURA - 4) + '╯'))


# ---------------------------------------------------------------------------
# Fluxo LOJA — Cadastrar promoção
# ---------------------------------------------------------------------------

def cadastrar_promocao(gw: Gateway):
    limpar()
    cabecalho('CADASTRAR NOVA PROMOCAO', 'Preencha os dados abaixo', C.BCY)

    # --- Titulo ---
    linha_sec('Identificacao')
    print()
    while True:
        titulo = prompt('Titulo           :')
        if titulo:
            break
        tag_aviso('Titulo nao pode ser vazio.')

    descricao = prompt('Descricao        :')

    # --- Categoria ---
    linha_sec('Categoria')
    print()
    for i, cat in enumerate(CATEGORIAS_VALIDAS, 1):
        print(f'    {s(C.BCY, C.BOLD, text=f"[{i}]")}  {cat}')
    print()

    while True:
        raw = prompt(f'Escolha [1-{len(CATEGORIAS_VALIDAS)}] ou digite :')
        if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIAS_VALIDAS):
            categoria = CATEGORIAS_VALIDAS[int(raw) - 1]
            break
        if raw.lower() in CATEGORIAS_VALIDAS:
            categoria = raw.lower()
            break
        tag_aviso(f"'{raw}' invalida. Escolha um numero ou digite a categoria.")

    # --- Precos ---
    linha_sec('Precos')
    print()
    while True:
        try:
            preco_orig = float(prompt('Preco original (R$) :').replace(',', '.'))
            preco_prom = float(prompt('Preco promocional   :').replace(',', '.'))
            if preco_orig <= 0 or preco_prom <= 0:
                tag_aviso('Precos devem ser maiores que zero.')
                continue
            if preco_prom >= preco_orig:
                tag_aviso('Preco promocional deve ser menor que o original.')
                continue
            break
        except ValueError:
            tag_aviso('Valor invalido — use ponto ou virgula como separador.')

    desconto = 100 * (1 - preco_prom / preco_orig)

    # --- Confirmação ---
    linha_sec('Confirmacao')
    print()
    print(f'  {s(C.DIM, text="Titulo    :")}  {s(C.BOLD, C.W, text=titulo)}')
    print(f'  {s(C.DIM, text="Categoria :")}  {s(C.BCY, text=categoria)}')
    print(f'  {s(C.DIM, text="Preco     :")}  {s(C.BG, text=f"R$ {preco_prom:.2f}")}  '
          f'{s(C.DIM, text=f"(de R$ {preco_orig:.2f}, -{desconto:.0f}%)")}')
    print(f'  {s(C.DIM, text="Descricao :")}  '
          + (descricao or s(C.DIM, text='(sem descricao)')))
    print()
    confirmar = prompt('Publicar promoção? [s/N] :').lower()
    if confirmar != 's':
        tag_aviso('Operacao cancelada.')
        enter()
        return

    print()
    print(s(C.DIM, text='  Assinando e publicando evento...'))

    try:
        id_gerado, assinatura = gw.cadastrar_promocao(
            titulo, descricao, categoria, preco_orig, preco_prom
        )
        tag_ok('Promocao publicada com sucesso!')
        rodape_evento('promotion.received', id_gerado, assinatura)
    except Exception as e:
        tag_erro(f'Falha ao publicar: {e}')

    enter()


# ---------------------------------------------------------------------------
# Fluxo CLIENTE — Listar promoções
# ---------------------------------------------------------------------------

def listar_promocoes(gw: Gateway):
    limpar()
    promocoes = gw.listar_promocoes()
    qtd = len(promocoes)
    cabecalho(
        'PROMOCOES PUBLICADAS',
        f'{qtd} promocao(oes) disponivel(eis)',
        C.BCY,
    )

    if not promocoes:
        print()
        tag_aviso('Nenhuma promocao disponivel no momento.')
        print(s(C.DIM, text='\n  Aguardando eventos promotion.published do MS Promotion...'))
        enter()
        return

    print()
    tabela_promocoes(promocoes, mostrar_descricao=True)
    enter()


# ---------------------------------------------------------------------------
# Fluxo CLIENTE — Votar
# ---------------------------------------------------------------------------

def votar_promocao(gw: Gateway):
    while True:
        limpar()
        cabecalho('VOTAR EM PROMOCAO', 'Escolha uma promocao e registre seu voto', C.BCY)

        promocoes = gw.listar_promocoes()
        if not promocoes:
            tag_aviso('Nenhuma promocao disponivel.')
            print(s(C.DIM, text='\n  Aguardando eventos promotion.published...'))
            enter()
            return

        print()
        tabela_promocoes(promocoes)

        raw = prompt(f'Numero da promocao [1-{len(promocoes)}] ou 0 para cancelar :')
        if raw == '0':
            return
        if not raw.isdigit() or not (1 <= int(raw) <= len(promocoes)):
            tag_aviso('Numero invalido.')
            time.sleep(0.8)
            continue

        idx = int(raw) - 1
        p   = promocoes[idx]
        print()
        card_promocao(p, idx + 1)

        # --- Escolha do voto ---
        print()
        print(f'  {s(C.BG, C.BOLD, text="[+]")}  Voto positivo  — apoiar esta promocao')
        print(f'  {s(C.BR, C.BOLD, text="[-]")}  Voto negativo  — reprovar esta promocao')
        print(f'  {s(C.DIM,       text="[0]")}  Cancelar')
        print()

        voto_raw = prompt('Seu voto [+/-/0] :')
        if voto_raw == '0':
            tag_aviso('Voto cancelado.')
            enter()
            return
        if voto_raw not in ('+', '-'):
            tag_aviso("Opcao invalida. Use '+', '-' ou '0'.")
            time.sleep(0.8)
            continue

        voto = 'positivo' if voto_raw == '+' else 'negativo'
        emoji_voto = s(C.BG, C.BOLD, text='+1') if voto == 'positivo' else s(C.BR, C.BOLD, text='-1')
        print()
        print(s(C.DIM, text='  Assinando e publicando voto...'))

        try:
            assinatura = gw.votar_promocao(p['id'], voto)
            tag_ok(f'Voto {emoji_voto} registrado com sucesso!')
            rodape_evento('promotion.vote', p['id'], assinatura)
        except Exception as e:
            tag_erro(f'Falha ao publicar voto: {e}')

        enter()
        return


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------

def menu_loja(gw: Gateway):
    while True:
        limpar()
        cabecalho('MENU  LOJA', 'Gerencie suas promocoes', C.BY)
        print()
        print(f'  {s(C.BCY, C.BOLD, text="[1]")}  Cadastrar nova promocao')
        print(f'  {s(C.DIM,        text="[0]")}  Voltar')
        print()

        op = prompt('Opcao :')
        if op == '1':
            cadastrar_promocao(gw)
        elif op == '0':
            break
        else:
            tag_aviso('Opcao invalida.')
            time.sleep(0.7)


def menu_cliente(gw: Gateway):
    while True:
        limpar()
        cabecalho('MENU  CLIENTE', 'Explore e vote nas promocoes', C.BCY)
        print()
        print(f'  {s(C.BCY, C.BOLD, text="[1]")}  Listar promocoes publicadas')
        print(f'  {s(C.BCY, C.BOLD, text="[2]")}  Votar em uma promocao')
        print(f'  {s(C.DIM,        text="[0]")}  Voltar')
        print()

        op = prompt('Opcao :')
        if op == '1':
            listar_promocoes(gw)
        elif op == '2':
            votar_promocao(gw)
        elif op == '0':
            break
        else:
            tag_aviso('Opcao invalida.')
            time.sleep(0.7)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def _animacao_conectando():
    frames = ['   ', '.  ', '.. ', '...']
    for _ in range(6):
        for f in frames:
            print(f'\r  {s(C.DIM, text="Conectando ao RabbitMQ")}{s(C.BCY, text=f)}', end='', flush=True)
            time.sleep(0.1)
    print()


def main():
    limpar()
    cabecalho('SISTEMA DE PROMOCOES', 'MS Gateway  ·  RabbitMQ  ·  RSA-SHA256', C.BCY)
    print()
    _animacao_conectando()

    try:
        gw = Gateway()
    except FileNotFoundError as e:
        tag_erro(str(e))
        print(s(C.DIM, text='\n  Inicie o MS Promotion antes do Gateway.'))
        print()
        return
    except Exception as e:
        tag_erro(f'Nao foi possivel iniciar o Gateway: {e}')
        print(s(C.DIM, text='\n  Verifique se o RabbitMQ esta em execucao.'))
        print()
        return

    tag_ok('Conectado. Consumer de promotion.published iniciado.')
    time.sleep(0.9)

    while True:
        limpar()
        cabecalho('SISTEMA DE PROMOCOES', 'MS Gateway  ·  RabbitMQ  ·  RSA-SHA256', C.BCY)
        hora = datetime.now().strftime('%H:%M:%S')
        total = len(gw.listar_promocoes())
        print()
        print(
            f'  {s(C.DIM, text="Promocoes validadas:")}  {s(C.BG, C.BOLD, text=str(total))}'
            f'  {s(C.DIM, text=f"· {hora}")}'
        )
        print()
        linha_sec()
        print()
        print(f'  {s(C.BY, C.BOLD, text="[1]")}  Loja     {s(C.DIM, text="— cadastrar promocoes")}')
        print(f'  {s(C.BCY, C.BOLD, text="[2]")}  Cliente  {s(C.DIM, text="— ver e votar em promocoes")}')
        print(f'  {s(C.DIM,        text="[0]")}  Encerrar')
        print()

        op = prompt('Opcao :')

        if op == '1':
            menu_loja(gw)
        elif op == '2':
            menu_cliente(gw)
        elif op == '0':
            gw.fechar()
            limpar()
            cabecalho('ATE LOGO', 'Sistema encerrado', C.DIM)
            print()
            break
        else:
            tag_aviso('Opcao invalida.')
            time.sleep(0.7)


if __name__ == '__main__':
    main()
