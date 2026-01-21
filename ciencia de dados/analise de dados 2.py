import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dados"

clientes = pd.read_csv(DATA_DIR / "clientes.csv")
produtos = pd.read_csv(DATA_DIR / "produtos.csv")
vendas = pd.read_csv(DATA_DIR / "vendas.csv", parse_dates=["data"])
itens = pd.read_csv(DATA_DIR / "itens_venda.csv")

print("✅ Carregou tudo no analise de dados 2.py!")
print(clientes.shape, produtos.shape, vendas.shape, itens.shape)