import pandas as pd
from pathlib import Path

# =========================
# 1) CARREGAMENTO DOS DADOS
# =========================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dados"

clientes = pd.read_csv(DATA_DIR / "clientes.csv")
produtos = pd.read_csv(DATA_DIR / "produtos.csv")
vendas = pd.read_csv(DATA_DIR / "vendas.csv", parse_dates=["data"])
itens = pd.read_csv(DATA_DIR / "itens_venda.csv")

print("✅ Arquivos carregados!")
print("clientes:", clientes.shape)
print("produtos:", produtos.shape)
print("vendas:", vendas.shape)
print("itens:", itens.shape)

# =================================
# 2) MONTAR A BASE CONSOLIDADA (JOIN)
# =================================
base = (itens
        .merge(vendas, on="venda_id", how="left")
        .merge(produtos, on="produto_id", how="left")
        .merge(clientes, on="cliente_id", how="left"))

print("\n✅ Base consolidada:", base.shape)
print(base.head())

# =========================
# 3) KPI PRINCIPAIS
# =========================
base["faturamento"] = base["valor_total"]

faturamento_total = base["faturamento"].sum()
qtd_vendas = base["venda_id"].nunique()
ticket_medio = base.groupby("venda_id")["faturamento"].sum().mean()

print("\n📊 KPIs principais")
print(f"Faturamento total: R$ {faturamento_total:,.2f}")
print(f"Qtd. vendas: {qtd_vendas}")
print(f"Ticket médio: R$ {ticket_medio:,.2f}")

# =========================
# 4) TOP 10 PRODUTOS
# =========================
top_prod = (base.groupby("produto")["faturamento"]
            .sum()
            .sort_values(ascending=False)
            .head(10))

print("\n🏆 Top 10 Produtos por faturamento:")
print(top_prod)

# =========================
# 5) FATURAMENTO POR CANAL
# =========================
fat_canal = base.groupby("canal")["faturamento"].sum().sort_values(ascending=False)

print("\n🛒 Faturamento por canal:")
print(fat_canal)

# =========================
# 6) FATURAMENTO POR MÊS
# =========================
fat_mes = (base.groupby(base["data"].dt.to_period("M"))["faturamento"]
           .sum()
           .sort_index())

print("\n📅 Faturamento por mês:")
print(fat_mes.tail(12))