# modulo de fatorial

def fatorial(n):
    f = 1
    for c in range(1, n+1):
        f *= c
    return f

def dobro(n):
    return n* 2


num = int(input('digite um valor:'))
fat = fatorial(num)
print(f'0 fatorial de {num} é {fat}.')
print(f'0 dobro de {num} é {dobro(num)}')