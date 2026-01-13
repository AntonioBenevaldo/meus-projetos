def _garantir_quebra_linha(texto: str) -> str:
    """Garante que o texto termine com '\n' (se estiver vazio, mantém vazio)."""
    if texto == "":
        return ""
    return texto if texto.endswith("\n") else texto + "\n"


def ler_arquivo(nome_arquivo):
    try:
        with open(nome_arquivo, "r", encoding="utf-8") as arquivo:
            conteudo = arquivo.read()
        print(f"Lendo arquivo: {nome_arquivo}")
        print(conteudo)
    except FileNotFoundError:
        print(f"Arquivo {nome_arquivo} não encontrado.")


def escrever_arquivo(nome_arquivo, conteudo):
    conteudo = _garantir_quebra_linha(conteudo)
    with open(nome_arquivo, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)


def adicionar_arquivo(nome_arquivo, conteudo):
    conteudo = _garantir_quebra_linha(conteudo)
    with open(nome_arquivo, "a", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)


def ler_linha_arquivo(nome_arquivo):
    try:
        print(f"Lendo o arquivo linha a linha: {nome_arquivo}")
        with open(nome_arquivo, "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                print(linha.rstrip("\n"))
    except FileNotFoundError:
        print(f"Arquivo {nome_arquivo} não encontrado.")


# Fluxo de teste (agora SEM \n manual)
escrever_arquivo("cidades.txt", "Carapicuíba")
ler_arquivo("cidades.txt")

adicionar_arquivo("cidades.txt", "Sobral")
adicionar_arquivo("cidades.txt", "Jandira")
ler_arquivo("cidades.txt")

ler_linha_arquivo("cidades.txt")
