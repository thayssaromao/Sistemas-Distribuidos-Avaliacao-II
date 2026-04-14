import os
import time

from gateway import Gateway

CATEGORIAS_VALIDAS = ["livros", "jogos", "eletrônicos", "roupas", "alimentos"]


# ---------------------------------------------------------------------------
# Utilitários de terminal
# ---------------------------------------------------------------------------

def limpar_tela():
    os.system("clear" if os.name == "posix" else "cls")


def banner(titulo: str):
    largura = 52
    print("=" * largura)
    print(f"  {titulo}")
    print("=" * largura)


def pressione_enter():
    input("\n[Pressione ENTER para continuar...]")


# ---------------------------------------------------------------------------
# Fluxos da LOJA
# ---------------------------------------------------------------------------

def cadastrar_promocao(gateway: Gateway):
    limpar_tela()
    banner("CADASTRAR NOVA PROMOÇÃO")

    print("\nPreencha os dados da promoção:\n")

    titulo = input("  Título da promoção : ").strip()
    if not titulo:
        print("\n[AVISO] Título não pode ser vazio.")
        pressione_enter()
        return

    descricao = input("  Descrição          : ").strip()

    print(f"\n  Categorias disponíveis: {', '.join(CATEGORIAS_VALIDAS)}")
    categoria = input("  Categoria          : ").strip().lower()
    if categoria not in CATEGORIAS_VALIDAS:
        print(f"\n[AVISO] Categoria '{categoria}' inválida.")
        pressione_enter()
        return

    try:
        preco_orig = float(input("  Preço original (R$): ").replace(",", "."))
        preco_prom = float(input("  Preço promocional  : ").replace(",", "."))
    except ValueError:
        print("\n[AVISO] Valores de preço inválidos.")
        pressione_enter()
        return

    print("\n" + "-" * 52)
    print("  Publicando evento 'promotion.received'...")

    try:
        id_gerado, signature = gateway.cadastrar_promocao(
            titulo, descricao, categoria, preco_orig, preco_prom
        )
        print(f"\n  Evento publicado com sucesso!")
        print(f"    ID gerado   : {id_gerado}")
        print(f"    routing_key : promotion.received")
        print(f"    titulo      : {titulo}")
        print(f"    categoria   : {categoria}")
        print(f"    preço       : R$ {preco_prom:.2f}  (de R$ {preco_orig:.2f})")
        print(f"    assinatura  : {signature[:32]}...")
    except Exception as e:
        print(f"\n[ERRO] Falha ao publicar evento: {e}")

    print("-" * 52)
    pressione_enter()


def menu_loja(gateway: Gateway):
    while True:
        limpar_tela()
        banner("MENU — LOJA")
        print("\n  [1] Cadastrar nova promoção")
        print("  [0] Sair\n")

        opcao = input("  Opção: ").strip()

        if opcao == "1":
            cadastrar_promocao(gateway)
        elif opcao == "0":
            print("\n  Até logo!")
            time.sleep(1)
            break
        else:
            print("\n  [AVISO] Opção inválida.")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Fluxos do CLIENTE
# ---------------------------------------------------------------------------

def listar_promocoes(gateway: Gateway):
    limpar_tela()
    banner("PROMOÇÕES PUBLICADAS")

    promocoes = gateway.listar_promocoes()

    if not promocoes:
        print("\n  Nenhuma promoção disponível no momento.")
        print("  (Aguardando eventos 'promotion.published' do RabbitMQ)")
        pressione_enter()
        return

    print()
    for p in promocoes:
        preco_orig = p.get('preco_original', 0)
        preco_prom = p.get('preco_promocional', 0)
        desconto = 100 * (1 - preco_prom / preco_orig) if preco_orig else 0
        votos = p.get('votos', {})

        print(f"  [{p.get('id', '?')}] {p.get('titulo', '?')}")
        print(f"       Categoria : {p.get('categoria', '?')}")
        print(f"       Preço     : R$ {preco_prom:.2f}"
              f"  (de R$ {preco_orig:.2f}, -{desconto:.0f}%)")
        if votos:
            print(f"       Votos     : +{votos.get('positivos', 0)}"
                  f" / -{votos.get('negativos', 0)}")
        print(f"       Descrição : {p.get('descricao', '')}")
        print()

    pressione_enter()


def votar_promocao(gateway: Gateway):
    limpar_tela()
    banner("VOTAR EM PROMOÇÃO")

    promocoes = gateway.listar_promocoes()

    if not promocoes:
        print("\n  Nenhuma promoção disponível para votação.")
        pressione_enter()
        return

    ids_validos = [p.get('id', '') for p in promocoes if p.get('id')]
    print(f"\n  Promoções disponíveis: {', '.join(ids_validos)}")

    promocao_id = input("\n  ID da promoção : ").strip()
    if promocao_id not in ids_validos:
        print(f"\n[AVISO] ID '{promocao_id}' não encontrado.")
        pressione_enter()
        return

    voto_raw = input("  Voto [+/-]     : ").strip()
    if voto_raw not in ("+", "-"):
        print("\n[AVISO] Voto deve ser '+' ou '-'.")
        pressione_enter()
        return

    voto = "positivo" if voto_raw == "+" else "negativo"

    print("\n" + "-" * 52)
    print("  Publicando evento 'promotion.vote'...")

    try:
        signature = gateway.votar_promocao(promocao_id, voto)
        print(f"\n  Voto enviado com sucesso!")
        print(f"    routing_key  : promotion.vote")
        print(f"    promocao_id  : {promocao_id}")
        print(f"    voto         : {voto}")
        print(f"    assinatura   : {signature[:32]}...")
    except Exception as e:
        print(f"\n[ERRO] Falha ao publicar voto: {e}")

    print("-" * 52)
    pressione_enter()


def menu_cliente(gateway: Gateway):
    while True:
        limpar_tela()
        banner("MENU — CLIENTE")
        print("\n  [1] Listar promoções publicadas")
        print("  [2] Votar em uma promoção")
        print("  [0] Sair\n")

        opcao = input("  Opção: ").strip()

        if opcao == "1":
            listar_promocoes(gateway)
        elif opcao == "2":
            votar_promocao(gateway)
        elif opcao == "0":
            print("\n  Até logo!")
            time.sleep(1)
            break
        else:
            print("\n  [AVISO] Opção inválida.")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main():
    limpar_tela()
    banner("MS GATEWAY — Sistema de Promoções")
    print("\n  Conectando ao RabbitMQ...")

    try:
        gateway = Gateway()
    except Exception as e:
        print(f"\n[ERRO] Não foi possível iniciar o Gateway: {e}")
        print("  Verifique se o RabbitMQ está em execução e tente novamente.")
        return

    while True:
        limpar_tela()
        banner("MS GATEWAY — Sistema de Promoções")
        print("\n  Selecione o tipo de usuário:\n")
        print("  [1] Loja    (cadastrar promoções)")
        print("  [2] Cliente (listar e votar)")
        print("  [0] Encerrar\n")

        opcao = input("  Opção: ").strip()

        if opcao == "1":
            menu_loja(gateway)
        elif opcao == "2":
            menu_cliente(gateway)
        elif opcao == "0":
            gateway.fechar()
            limpar_tela()
            print("  Sistema encerrado.\n")
            break
        else:
            print("\n  [AVISO] Opção inválida.")
            time.sleep(1)


if __name__ == "__main__":
    main()