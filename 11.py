# manipulando conjuntos - sete

usuarios = {"ana" , "aria" , "ana"}
usuarios.add("felipe")
print (usuarios)

usuario_digitado = input("digite seu usuario: ")
if usuario_digitado in usuarios:
    print (f"usuario cadastrado!")
else:
    print(f"usuario nao cadastrado!")

novos_usuarios = {"felipe" , "pedro" , "marcos"}

print(usuarios)
print(novos_usuarios)

todos_usuarios = usuarios.union(novos_usuarios)

print(f"union: {todos_usuarios}")

usuarios_comuns = usuarios.intersection(novos_usuarios)
print(f"interseçao: {usuarios_comuns}")

usuarios_diferentes = usuarios.difference(novos_usuarios)
print(f"diferença: {usuarios_diferentes}")
