# Sistema de Controle de Estoque Loja de Eletrônicos

class Produto:
    def __init__(self, nome, preco, quantidade):
        self.nome = nome              # Nome do produto
        self.preco = preco            # Preço do produto
        self.quantidade = quantidade  # Quantidade em estoque

    def atualizar(self, preco, quantidade):
        self.preco = preco
        self.quantidade = quantidade

    def __str__(self):
        return f"{self.nome} - Preço: R${self.preco:.2f}, Quantidade: {self.quantidade}"


# Classe Estoque
class Estoque:
    def __init__(self):
        self.produtos = {}

    #  Adicionar produto
    def adicionar_produto(self, nome, preco, quantidade):
        if nome in self.produtos:
            print("Produto já existe no estoque!")
        else:
            self.produtos[nome] = Produto(nome, preco, quantidade)
            print("Produto adicionado com sucesso!")

    #  Atualizar produto
    def atualizar_produto(self, nome, preco, quantidade):
        if nome in self.produtos:
            self.produtos[nome].atualizar(preco, quantidade)
            print("Produto atualizado com sucesso!")
        else:
            print("Produto não encontrado no estoque.")

    #  Excluir produto
    def excluir_produto(self, nome):
        if nome in self.produtos:
            del self.produtos[nome]
            print("Produto excluído com sucesso!")
        else:
            print("Produto não encontrado no estoque.")

    #  Visualizar estoque
    def visualizar_estoque(self):
        if self.produtos:
            print("\n--- Estoque Atual ---")
            for produto in self.produtos.values():
                print(produto)
        else:
            print("Estoque vazio.")


# Classe SistemaControleEstoque
class SistemaControleEstoque:
    def __init__(self):
        self.estoque = Estoque()

    #  Menu de opções
    def menu(self):
        print("\n--- Sistema de Controle de Estoque Loja de Eletrônicos ---")
        print("1. Adicionar produto")
        print("2. Atualizar produto")
        print("3. Excluir produto")
        print("4. Visualizar estoque")
        print("5. Sair do sistema")

    #  Executar sistema
    def executar(self):
        while True:
            self.menu()
            opcao = input("Escolha uma opção: ")

            if opcao == "1":  #  Adicionar produto
                nome = input("Nome do produto: ")
                preco = float(input("Preço do produto: "))
                quantidade = int(input("Quantidade em estoque: "))
                self.estoque.adicionar_produto(nome, preco, quantidade)

            elif opcao == "2":  #  Atualizar produto
                nome = input("Nome do produto a atualizar: ")
                preco = float(input("Novo preço: "))
                quantidade = int(input("Nova quantidade: "))
                self.estoque.atualizar_produto(nome, preco, quantidade)

            elif opcao == "3":  #  Excluir produto
                nome = input("Nome do produto a excluir: ")
                self.estoque.excluir_produto(nome)

            elif opcao == "4":  #  Visualizar estoque
                self.estoque.visualizar_estoque()

            elif opcao == "5":  #  Sair do sistema
                print("Encerrando o sistema... Até logo!")
                break

            else:
                print("Opção inválida! Tente novamente.")


# Programa Principal
if __name__ == "__main__":
    sistema = SistemaControleEstoque()
    sistema.executar()