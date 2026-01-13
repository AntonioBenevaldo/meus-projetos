# manipulando listas - list

# criando uma lista

nomes = ["ana", "pedro", "joao"]

print (f"lista origial: {nomes}")

# adicionando 2 novos nomes com for

for cont in range(1):
    novo_nome = input(f"digite um nome{cont}: ")
nomes.append(novo_nome)
print(f"lista adicionando 2 nomes: {nomes}")

# adicionando n quantidade de nomes com while

resp = "s"
while resp == "s":
     novo_nome = input(f"digite um nome: ")
     nomes.append(novo_nome) 
     resp = input ("deseja cadastrar mais um nome [s/n]")
     print(f"lista adicionando n nomes: {nomes}")

# listando elementos pela posiçao.

     print(nomes[0])

  # removendo o ultimo nome da lista
nomes.pop()
print (f"removendo o ultimo {nomes}")

# removendo um elemento qualquer
nomes.remove("pedro")
print (f"removendo um elemento: {nomes}")

# verificando a existencia de um elemento
nome_pesquisado = input ("digite um nome para pesquisar: ")
if nome_pesquisado in nomes:
     print ("nome cadastrado")
else: 
     print ("nome nao cadastrado")