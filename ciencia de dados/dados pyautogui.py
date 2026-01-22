import pandas as pd
import os
from openpyxl import load_workbook

# Nome do arquivo
arquivo_excel = "dados.xlsx"

# 1. Verifica se o arquivo existe. Se não, cria com dados de exemplo
if not os.path.exists(arquivo_excel):
    dados = {
        "Nome": ["Antonio", "Maria", "João"],
        "Idade": [30, 25, 40],
        "Cidade": ["Belo Horizonte", "São Paulo", "Rio de Janeiro"]
    }
    df = pd.DataFrame(dados)
    df.to_excel(arquivo_excel, sheet_name="Pessoas", index=False, engine="openpyxl")
    print("Arquivo 'dados.xlsx' criado com dados de exemplo.")

# 2. Lê os dados da aba 'Pessoas'
df = pd.read_excel(arquivo_excel, sheet_name="Pessoas", engine="openpyxl")
print("\nDados lidos:")
print(df)

# 3. Faz a análise
media_idade = df["Idade"].mean()
max_idade = df["Idade"].max()
min_idade = df["Idade"].min()

analise = pd.DataFrame({
    "Métrica": ["Média de Idade", "Idade Máxima", "Idade Mínima"],
    "Valor": [media_idade, max_idade, min_idade]
})

print("\nResultados da análise:")
print(analise)

# 4. Escreve os resultados em uma nova aba chamada 'Análise'
with pd.ExcelWriter(arquivo_excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    analise.to_excel(writer, sheet_name="Análise", index=False)

print("\nAnálise salva na aba 'Análise' do arquivo Excel.")






