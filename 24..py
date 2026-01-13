print ("ola mundo")
print ("quantos anos voce tem")

nome = input ('qual é o seu nome? ')
idade = input ('quantos anos voce tem?')
peso = input ('qual é o seu peso?')
print (nome , idade , peso)

# solicite o nome da pessoa
none = input("digite seu nome:")
# exibe uma mensagem de boas-vindas pessonalizada
print(f"seja bem-vinda(a), {nome}! ")

# solicite os dados de nacimento
dia = input("digite o dia do seu nascimento: ")
mes = input("digite o mês do seu nascimento: ")
ano = input("digite o ano do seu nascimento: ")
print(f"você nasceu em {dia} de {mes} de {ano}")

# exibe a data formatada
print("você nasceu em " + dia + "/" + mes + "/" + ano)

# solicite dois numero ao usuario

num1 = input("digite o seu primeiro numero: ")
num2 = input("digite o seu segundo numero: ")

# tenta converter os valores para numeros e calcular a soma
try:
    soma = float(num1) + float(num2)
    print(f"a soma entre {num1} e {num2} e {soma}. ")
except ValueError:
    print("por favor, digite apenas numero validos.")