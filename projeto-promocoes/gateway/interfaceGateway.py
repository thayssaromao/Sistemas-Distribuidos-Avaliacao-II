import os
import time

# ---------------------------------------------------------------------------
# Dados fictícios – simulam a lista local de promoções validadas pelo
# MS Promocao (em produção, esta lista seria populada ao consumir eventos
# promocao.publicada do RabbitMQ).
# ---------------------------------------------------------------------------
MOCK_PROMOCOES_PUBLICADAS = [
    {
        "id": "P001",
        "titulo": "Notebook Gamer XZ Pro",
        "descricao": "Notebook com RTX 4060, 16 GB RAM, SSD 512 GB",
        "preco_original": 5999.00,
        "preco_promocional": 4299.00,
        "categoria": "eletrônicos",
        "votos": {"positivos": 42, "negativos": 3},
    },
    {
        "id": "P002",
        "titulo": "Combo 3 Livros de Python",
        "descricao": "Python Fluente + Automatize + Python Cookbook",
        "preco_original": 280.00,
        "preco_promocional": 159.90,
        "categoria": "livros",
        "votos": {"positivos": 18, "negativos": 1},
    },
    {
        "id": "P003",
        "titulo": "Elden Ring – Edição Completa",
        "descricao": "Jogo base + Shadow of the Erdtree DLC",
        "preco_original": 349.90,
        "preco_promocional": 199.90,
        "categoria": "jogos",
        "votos": {"positivos": 87, "negativos": 5},
    },
]

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

def cadastrar_promocao():
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

    # Monta o envelope do evento (placeholder)
    evento = {
        "routing_key": "promotion.received",
        "payload": {
            "titulo": titulo,
            "descricao": descricao,
            "categoria": categoria,
            "preco_original": preco_orig,
            "preco_promocional": preco_prom,
        },
        # Em produção: assinatura digital gerada com a chave privada do Gateway
        "signature": "<PLACEHOLDER: assinatura_digital_RSA>",
    }

    print("\n" + "-" * 52)
    print("  Resumo do evento a ser publicado:")
    print(f"    routing_key : {evento['routing_key']}")
    print(f"    titulo      : {evento['payload']['titulo']}")
    print(f"    categoria   : {evento['payload']['categoria']}")
    print(f"    preço       : R$ {evento['payload']['preco_promocional']:.2f}"
          f"  (de R$ {evento['payload']['preco_original']:.2f})")
    print(f"    signature   : {evento['signature']}")
    print("-" * 52)

    # TODO: publicar evento no RabbitMQ
    # channel.basic_publish(
    #     exchange="promocoes",
    #     routing_key="promotion.received",
    #     body=json.dumps(evento)
    # )
    print("\n[PLACEHOLDER] Evento 'promotion.received' seria publicado no RabbitMQ.")

    pressione_enter()


def menu_loja():
    while True:
        limpar_tela()
        banner("MENU — LOJA")
        print("\n  [1] Cadastrar nova promoção")
        print("  [0] Sair\n")

        opcao = input("  Opção: ").strip()

        if opcao == "1":
            cadastrar_promocao()
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

def listar_promocoes():
    limpar_tela()
    banner("PROMOÇÕES PUBLICADAS")

    if not MOCK_PROMOCOES_PUBLICADAS:
        print("\n  Nenhuma promoção disponível no momento.")
        # TODO: lista seria atualizada em tempo real ao consumir
        #       eventos 'promotion.published' do RabbitMQ.
        pressione_enter()
        return

    print()
    for p in MOCK_PROMOCOES_PUBLICADAS:
        desconto = 100 * (1 - p["preco_promocional"] / p["preco_original"])
        print(f"  [{p['id']}] {p['titulo']}")
        print(f"       Categoria : {p['categoria']}")
        print(f"       Preço     : R$ {p['preco_promocional']:.2f}"
              f"  (de R$ {p['preco_original']:.2f}, -{desconto:.0f}%)")
        print(f"       Votos     : +{p['votos']['positivos']} / -{p['votos']['negativos']}")
        print(f"       Descrição : {p['descricao']}")
        print()

    # TODO: esta lista é mantida localmente pelo Gateway ao consumir
    #       eventos 'promotion.published' do RabbitMQ.
    print("  [PLACEHOLDER] Lista populada a partir de eventos 'promotion.published' do RabbitMQ.")

    pressione_enter()


def votar_promocao():
    limpar_tela()
    banner("VOTAR EM PROMOÇÃO")

    ids_validos = [p["id"] for p in MOCK_PROMOCOES_PUBLICADAS]
    print(f"\n  Promoções disponíveis: {', '.join(ids_validos)}")

    promocao_id = input("\n  ID da promoção : ").strip().upper()
    if promocao_id not in ids_validos:
        print(f"\n[AVISO] ID '{promocao_id}' não encontrado.")
        pressione_enter()
        return

    voto = input("  Voto [+/-]     : ").strip()
    if voto not in ("+", "-"):
        print("\n[AVISO] Voto deve ser '+' ou '-'.")
        pressione_enter()
        return

    # Monta o envelope do evento (placeholder)
    evento = {
        "routing_key": "promotion.vote",
        "payload": {
            "promocao_id": promocao_id,
            "voto": "positivo" if voto == "+" else "negativo",
        },
        # Em produção: assinatura digital gerada com a chave privada do Gateway
        "signature": "<PLACEHOLDER: assinatura_digital_RSA>",
    }

    print("\n" + "-" * 52)
    print("  Resumo do evento a ser publicado:")
    print(f"    routing_key  : {evento['routing_key']}")
    print(f"    promocao_id  : {evento['payload']['promocao_id']}")
    print(f"    voto         : {evento['payload']['voto']}")
    print(f"    signature    : {evento['signature']}")
    print("-" * 52)

    # TODO: publicar evento no RabbitMQ
    # channel.basic_publish(
    #     exchange="promocoes",
    #     routing_key="promotion.vote",
    #     body=json.dumps(evento)
    # )
    print("\n[PLACEHOLDER] Evento 'promotion.vote' seria publicado no RabbitMQ.")

    pressione_enter()


def menu_cliente():
    while True:
        limpar_tela()
        banner("MENU — CLIENTE")
        print("\n  [1] Listar promoções publicadas")
        print("  [2] Votar em uma promoção")
        print("  [0] Sair\n")

        opcao = input("  Opção: ").strip()

        if opcao == "1":
            listar_promocoes()
        elif opcao == "2":
            votar_promocao()
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
    while True:
        limpar_tela()
        banner("MS GATEWAY — Sistema de Promoções")
        print("\n  Selecione o tipo de usuário:\n")
        print("  [1] Loja    (cadastrar promoções)")
        print("  [2] Cliente (listar e votar)")
        print("  [0] Encerrar\n")

        opcao = input("  Opção: ").strip()

        if opcao == "1":
            menu_loja()
        elif opcao == "2":
            menu_cliente()
        elif opcao == "0":
            limpar_tela()
            print("  Sistema encerrado.\n")
            break
        else:
            print("\n  [AVISO] Opção inválida.")
            time.sleep(1)


if __name__ == "__main__":
    main()
