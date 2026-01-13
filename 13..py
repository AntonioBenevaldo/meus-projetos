# funcoes

def mensagem():
    print("ola mundo!")

def calcular_desconto(preco, desconto=0.2):
    """Calcula o preço final aplicando um desconto percentual."""
    return preco * (1 - desconto)

def soma(a, b):
    return a + b

# Executando funções
mensagem()

valor_pagar = calcular_desconto(100)  # desconto padrão de 20%
print(f"{valor_pagar:.2f}")

total = soma(4, 90)
print(total)

# Lista de valores para aplicar desconto
valores = [100, 200, 300, 400]

print("### valores com desconto ###")
for valor in valores:
    valor_desconto = calcular_desconto(valor)
    print(f"{valor_desconto:.2f}")
