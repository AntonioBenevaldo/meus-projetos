# ============================================
# Dashboard Executivo (Power BI Premium v2)
# Streamlit + Pandas + Plotly
# Autor: Benevaldo (com apoio ChatGPT)
# ============================================

from __future__ import annotations

import io
import re
import math
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------
# CONFIG (Power BI style)
# -----------------------------
st.set_page_config(
    page_title="Dashboard Executivo (Power BI Premium v2)",
    page_icon="📊",
    layout="wide",
)

PBI_CSS = """
<style>
/* Layout geral */
.block-container {padding-top: 1.0rem; padding-bottom: 2rem;}
/* Títulos */
h1, h2, h3 {letter-spacing: -0.5px;}
/* Sidebar estilo Power BI */
[data-testid="stSidebar"] {background: #fbfbfc;}
/* Cartões KPI */
.kpi-card{
    border: 1px solid rgba(49, 51, 63, 0.08);
    border-radius: 16px;
    padding: 14px 16px;
    background: #ffffff;
    box-shadow: 0 6px 18px rgba(0,0,0,0.04);
}
.kpi-title{font-size: 0.85rem; color: rgba(49, 51, 63, 0.75); margin-bottom: 6px;}
.kpi-value{font-size: 1.65rem; font-weight: 700; color: #111827; line-height: 1.2;}
.kpi-sub{font-size: 0.82rem; color: rgba(49, 51, 63, 0.65); margin-top: 6px;}
.hr-soft{height:1px;background:rgba(49,51,63,.08);border:0;margin:16px 0;}
.small-muted{font-size:0.85rem;color:rgba(49,51,63,.60);}
.badge{display:inline-block;padding:4px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:0.80rem;}
</style>
"""
st.markdown(PBI_CSS, unsafe_allow_html=True)


# -----------------------------
# UTIL: formatos (BR)
# -----------------------------
def fmt_brl(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "R$ 0,00"
    s = f"{x:,.2f}"
    # troca separadores US -> BR
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def fmt_int(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "0"
    return f"{int(round(x)):,}".replace(",", ".")

def fmt_pct(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "0,0%"
    return f"{x*100:.1f}%".replace(".", ",")


# -----------------------------
# UTIL: conversão BR para número
# -----------------------------
def to_number_br(series: pd.Series) -> pd.Series:
    """
    Converte coluna que pode ter:
    'R$ 1.234,56', '1.234,56', '1234,56', '1234.56', '', None...
    Retorna float seguro.
    """
    s = series.astype(str).str.strip()
    s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan})

    # remove "R$" e textos
    s = s.str.replace("R$", "", regex=False)
    s = s.str.replace(r"[^\d,.\-]", "", regex=True)

    # caso 1: tem '.' e ',' => '.' milhar e ',' decimal (1.234,56)
    mask = s.str.contains(r"\.") & s.str.contains(",")
    s.loc[mask] = s.loc[mask].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)

    # caso 2: só ',' => decimal BR (123,45)
    mask2 = s.str.contains(",") & (~s.str.contains(r"\."))
    s.loc[mask2] = s.loc[mask2].str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


# -----------------------------
# NORMALIZAÇÃO DE COLUNAS
# -----------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace("  ", " ")
        .str.replace("-", "_")
        .str.replace(" ", "_")
    )
    return df


def smart_rename(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia nomes comuns para o padrão do dashboard:
    data, categoria, marca, uf, canal, produto, quantidade, preco_unitario, valor_total, custo_unitario
    """
    df = df.copy()
    cols = set(df.columns)

    ren = {}

    # data
    if "data" not in cols:
        for c in cols:
            if c in {"dt", "date", "data_venda", "data_movimento"}:
                ren[c] = "data"
                break

    # produto
    if "produto" not in cols:
        for c in cols:
            if c in {"item", "descricao", "descricao_produto", "produto_nome"}:
                ren[c] = "produto"
                break

    # categoria
    if "categoria" not in cols:
        for c in cols:
            if c in {"grupo", "familia", "departamento"}:
                ren[c] = "categoria"
                break

    # marca
    if "marca" not in cols:
        for c in cols:
            if c in {"brand"}:
                ren[c] = "marca"
                break

    # uf
    if "uf" not in cols:
        for c in cols:
            if c in {"estado", "sigla_uf"}:
                ren[c] = "uf"
                break

    # canal
    if "canal" not in cols:
        for c in cols:
            if c in {"channel"}:
                ren[c] = "canal"
                break

    # quantidade
    if "quantidade" not in cols:
        for c in cols:
            if c in {"qtd", "qtde", "qnt", "quantity"}:
                ren[c] = "quantidade"
                break

    # preço unitário
    if "preco_unitario" not in cols:
        for c in cols:
            if c in {"preco", "preco_unit", "valor_unitario", "preco_un", "unit_price"}:
                ren[c] = "preco_unitario"
                break

    # valor total
    if "valor_total" not in cols:
        for c in cols:
            if c in {"total", "valor", "faturamento", "venda_total"}:
                ren[c] = "valor_total"
                break

    # custo unitário (opcional)
    if "custo_unitario" not in cols:
        for c in cols:
            if c in {"custo", "cost", "custo_un", "custo_unit"}:
                ren[c] = "custo_unitario"
                break

    if ren:
        df = df.rename(columns=ren)

    return df


def prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    df = smart_rename(df)

    # DATA
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)

    # NUMÉRICOS (seguros)
    for col in ["quantidade", "preco_unitario", "valor_total", "custo_unitario"]:
        if col in df.columns:
            df[col] = to_number_br(df[col])

    # defaults e cálculos
    if "quantidade" in df.columns:
        df["quantidade"] = df["quantidade"].fillna(0)

    if "preco_unitario" in df.columns:
        df["preco_unitario"] = df["preco_unitario"].fillna(0)

    # se não existir valor_total, tenta calcular
    if "valor_total" not in df.columns and ("quantidade" in df.columns and "preco_unitario" in df.columns):
        df["valor_total"] = df["quantidade"] * df["preco_unitario"]

    if "valor_total" in df.columns:
        df["valor_total"] = df["valor_total"].fillna(0)

    # custo (se não existir, estima 70% do preço)
    if "custo_unitario" not in df.columns:
        if "preco_unitario" in df.columns:
            df["custo_unitario"] = df["preco_unitario"] * 0.70
        else:
            df["custo_unitario"] = 0.0

    df["custo_unitario"] = df["custo_unitario"].fillna(0)

    # garante strings em dimensões
    for col in ["categoria", "marca", "uf", "canal", "produto"]:
        if col in df.columns:
            df[col] = df[col].astype(str).replace({"nan": ""}).fillna("")

    # derivadas
    if "data" in df.columns:
        df["dia"] = df["data"].dt.floor("D")
        df["ano"] = df["data"].dt.year
        df["mes"] = df["data"].dt.to_period("M").astype(str)
        df["dow"] = df["data"].dt.day_name()

    # valores calculados
    df["custo_total"] = df.get("quantidade", 0) * df.get("custo_unitario", 0)
    df["lucro_bruto"] = df.get("valor_total", 0) - df["custo_total"]

    return df


# -----------------------------
# DEMO (base fake)
# -----------------------------
def make_demo(n=3500, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    categorias = ["CELULARES", "TV & VÍDEO", "ACESSÓRIOS", "INFORMÁTICA", "GAMES", "ÁUDIO"]
    marcas = ["SAMSUNG", "APPLE", "LG", "SONY", "XIAOMI", "MOTOROLA", "DELL", "HP", "LOGITECH"]
    canais = ["Loja Física", "E-commerce", "Marketplace", "Atacado"]
    ufs = ["SP", "RJ", "MG", "BA", "PR", "RS", "SC", "PE", "CE", "GO", "DF", "ES"]

    datas = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    df = pd.DataFrame({
        "data": rng.choice(datas, size=n),
        "categoria": rng.choice(categorias, size=n, p=[0.20, 0.15, 0.18, 0.17, 0.15, 0.15]),
        "marca": rng.choice(marcas, size=n),
        "uf": rng.choice(ufs, size=n),
        "canal": rng.choice(canais, size=n, p=[0.42, 0.30, 0.18, 0.10]),
    })

    # produtos por categoria
    def prod(cat):
        base = {
            "CELULARES": ["Smartphone A12", "Smartphone X9", "Smartphone Pro Max", "Smartphone Lite"],
            "TV & VÍDEO": ["TV 50 4K", "TV 65 OLED", "Soundbar 2.1", "Projetor Mini"],
            "ACESSÓRIOS": ["Cabo USB-C", "Carregador 20W", "Capinha Premium", "Fone Bluetooth"],
            "INFORMÁTICA": ["Notebook i5", "Notebook i7", "Mouse Gamer", "Teclado Mecânico"],
            "GAMES": ["Console Z", "Controle Pro", "Headset RGB", "Assinatura GamePass"],
            "ÁUDIO": ["Caixa Bluetooth", "Fone In-Ear", "Microfone USB", "Home Theater"],
        }
        return base.get(cat, ["Produto"])

    df["produto"] = df["categoria"].apply(prod).apply(lambda lst: rng.choice(lst))

    # quantidade e preços
    df["quantidade"] = np.clip(rng.normal(4.0, 2.2, size=n), 1, 30).round(0)

    # preço por categoria
    price_map = {
        "CELULARES": (900, 4200),
        "TV & VÍDEO": (800, 6500),
        "ACESSÓRIOS": (30, 400),
        "INFORMÁTICA": (200, 6500),
        "GAMES": (80, 4500),
        "ÁUDIO": (50, 2500),
    }
    low = df["categoria"].map(lambda c: price_map[c][0]).astype(float)
    high = df["categoria"].map(lambda c: price_map[c][1]).astype(float)
    df["preco_unitario"] = (low + (high - low) * rng.random(n)).round(2)

    df["valor_total"] = (df["quantidade"] * df["preco_unitario"]).round(2)
    df["custo_unitario"] = (df["preco_unitario"] * (0.62 + 0.12 * rng.random(n))).round(2)

    return prepare_df(df)


# -----------------------------
# LOAD (CSV/Excel)
# -----------------------------
@st.cache_data(show_spinner=False)
def load_file(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    return prepare_df(df)


# -----------------------------
# SIDEBAR (Config + Upload)
# -----------------------------
st.sidebar.markdown("## ⚙️ Configurações")
uploaded = st.sidebar.file_uploader(
    "📥 Enviar CSV/Excel",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=False,
)

use_demo = st.sidebar.toggle("Usar base DEMO (recomendado)", value=(uploaded is None))

st.sidebar.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)
st.sidebar.markdown("### 🧩 Modelo de Colunas")
st.sidebar.caption("Ideal: Data, Categoria, Marca, UF, Canal, Produto, Quantidade, Preço Unitário, Valor Total.")

# -----------------------------
# DATA
# -----------------------------
if use_demo:
    df = make_demo()
else:
    if uploaded is None:
        st.warning("Envie um arquivo CSV/Excel ou habilite a base DEMO na lateral.")
        st.stop()
    df = load_file(uploaded)

# valida mínimo
if "valor_total" not in df.columns:
    st.error("Não encontrei/gerou a coluna 'valor_total'. Inclua Valor Total ou Quantidade + Preço Unitário.")
    st.stop()

# -----------------------------
# FILTROS (Slicers)
# -----------------------------
st.sidebar.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)
st.sidebar.markdown("## 🧷 Filtros (Slicers)")

# intervalo de datas
if "data" in df.columns and df["data"].notna().any():
    dmin = df["data"].min().date()
    dmax = df["data"].max().date()
    d1, d2 = st.sidebar.date_input("📅 Intervalo de datas", value=(dmin, dmax), min_value=dmin, max_value=dmax)
else:
    d1, d2 = None, None

def multiselect_filter(label, col):
    if col not in df.columns:
        return []
    vals = sorted([v for v in df[col].dropna().unique().tolist() if str(v).strip() != ""])
    return st.sidebar.multiselect(label, vals, default=[])

f_cat = multiselect_filter("📌 Categoria", "categoria")
f_marca = multiselect_filter("🏷️ Marca", "marca")
f_uf = multiselect_filter("🗺️ UF", "uf")
f_canal = multiselect_filter("🧾 Canal", "canal")

# aplica filtros
df_f = df.copy()

if d1 and d2 and "data" in df_f.columns:
    df_f = df_f[(df_f["data"].dt.date >= d1) & (df_f["data"].dt.date <= d2)]

if f_cat and "categoria" in df_f.columns:
    df_f = df_f[df_f["categoria"].isin(f_cat)]

if f_marca and "marca" in df_f.columns:
    df_f = df_f[df_f["marca"].isin(f_marca)]

if f_uf and "uf" in df_f.columns:
    df_f = df_f[df_f["uf"].isin(f_uf)]

if f_canal and "canal" in df_f.columns:
    df_f = df_f[df_f["canal"].isin(f_canal)]

# -----------------------------
# HEADER
# -----------------------------
st.markdown("## 📊 Dashboard Executivo (Power BI Premium v2)")
st.markdown(
    "<span class='small-muted'>CSV/Excel • Filtros • KPIs • Tendência • ABC • Qualidade • Exportação Excel Multi-Abas</span>",
    unsafe_allow_html=True,
)
st.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)

# -----------------------------
# KPI CÁLCULOS (sempre numéricos)
# -----------------------------
faturamento = float(df_f["valor_total"].sum())

qtd_total = float(df_f["quantidade"].sum()) if "quantidade" in df_f.columns else float(len(df_f))

# "Pedidos": se existir id_pedido/pedido, usa unique; senão usa linhas
if "pedido" in df_f.columns:
    pedidos = float(df_f["pedido"].nunique())
elif "id_pedido" in df_f.columns:
    pedidos = float(df_f["id_pedido"].nunique())
else:
    pedidos = float(len(df_f))

ticket_medio = faturamento / pedidos if pedidos > 0 else 0.0

margem_bruta_val = float(df_f["lucro_bruto"].sum()) if "lucro_bruto" in df_f.columns else 0.0
margem_pct = (margem_bruta_val / faturamento) if faturamento > 0 else 0.0


# -----------------------------
# KPI CARDS
# -----------------------------
c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 1, 1.2], gap="small")

with c1:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">Faturamento</div>
            <div class="kpi-value">{fmt_brl(faturamento)}</div>
            <div class="kpi-sub">Registros: {fmt_int(len(df_f))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">Pedidos</div>
            <div class="kpi-value">{fmt_int(pedidos)}</div>
            <div class="kpi-sub">Pedidos únicos</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">Quantidade</div>
            <div class="kpi-value">{fmt_int(qtd_total)}</div>
            <div class="kpi-sub">Unidades vendidas</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">Ticket Médio</div>
            <div class="kpi-value">{fmt_brl(ticket_medio)}</div>
            <div class="kpi-sub">Média por pedido</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c5:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">Margem Bruta</div>
            <div class="kpi-value">{fmt_brl(margem_bruta_val)}</div>
            <div class="kpi-sub">Margem %: {fmt_pct(margem_pct)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)

# -----------------------------
# TABS (Power BI-like)
# -----------------------------
tabs = st.tabs([
    "🏠 Visão Geral",
    "📈 Vendas & Tendência",
    "🧾 Produtos & ABC",
    "🗺️ Geografia (UF)",
    "🧪 Qualidade de Dados",
    "📤 Exportação",
])

# =============================
# TAB 1 - VISÃO GERAL
# =============================
with tabs[0]:
    st.markdown("### 📌 Visão Geral")

    left, right = st.columns([1.4, 1.0], gap="large")

    # tendência (linha)
    with left:
        if "dia" in df_f.columns and df_f["dia"].notna().any():
            ts = (
                df_f.groupby("dia", as_index=False)["valor_total"].sum()
                    .sort_values("dia")
                    .reset_index(drop=True)
            )
            ts["media_movel_7d"] = ts["valor_total"].rolling(7, min_periods=1).mean()

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ts["dia"], y=ts["valor_total"], mode="lines", name="Total Diário"))
            fig.add_trace(go.Scatter(x=ts["dia"], y=ts["media_movel_7d"], mode="lines", name="Média Móvel (7d)"))
            fig.update_layout(
                title="Evolução do Faturamento",
                height=360,
                margin=dict(l=10, r=10, t=50, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem coluna de data para gerar tendência.")

    # ranking (barras)
    with right:
        if "categoria" in df_f.columns:
            top_cat = (
                df_f.groupby("categoria", as_index=False)["valor_total"].sum()
                    .sort_values("valor_total", ascending=False)
                    .head(10)
            )
            fig2 = px.bar(top_cat, x="valor_total", y="categoria", orientation="h", title="Top Categorias (R$)")
            fig2.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem coluna categoria para ranking.")

    st.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)

    cA, cB, cC = st.columns([1.2, 1.2, 1.0], gap="large")
    with cA:
        if "canal" in df_f.columns:
            canal = (
                df_f.groupby("canal", as_index=False)["valor_total"].sum()
                    .sort_values("valor_total", ascending=False)
            )
            fig = px.pie(canal, names="canal", values="valor_total", title="Participação por Canal")
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem coluna canal.")

    with cB:
        if "marca" in df_f.columns:
            marca = (
                df_f.groupby("marca", as_index=False)["valor_total"].sum()
                    .sort_values("valor_total", ascending=False)
                    .head(10)
            )
            fig = px.bar(marca, x="marca", y="valor_total", title="Top Marcas (R$)")
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem coluna marca.")

    with cC:
        st.markdown("#### 🧠 Insights Automáticos")
        st.markdown(f"- **Faturamento:** {fmt_brl(faturamento)}")
        st.markdown(f"- **Ticket Médio:** {fmt_brl(ticket_medio)}")
        st.markdown(f"- **Margem %:** {fmt_pct(margem_pct)}")

        if "categoria" in df_f.columns:
            best = (
                df_f.groupby("categoria")["valor_total"].sum().sort_values(ascending=False).head(1)
            )
            if len(best) > 0:
                st.markdown(f"- **Categoria líder:** `{best.index[0]}`")

        st.markdown("<span class='badge'>Power BI Premium v2</span>", unsafe_allow_html=True)

# =============================
# TAB 2 - VENDAS & TENDÊNCIA
# =============================
with tabs[1]:
    st.markdown("### 📈 Vendas & Tendência")

    c1, c2 = st.columns([1.4, 1.0], gap="large")

    with c1:
        if "mes" in df_f.columns:
            ts_m = (
                df_f.groupby("mes", as_index=False)["valor_total"].sum()
                    .sort_values("mes")
            )
            fig = px.area(ts_m, x="mes", y="valor_total", title="Faturamento por Mês")
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem coluna mês.")

    with c2:
        if "dow" in df_f.columns:
            dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            dow = (
                df_f.groupby("dow", as_index=False)["valor_total"].sum()
            )
            # tenta ordenar melhor
            if set(dow["dow"]) & set(dow_order):
                dow["ord"] = dow["dow"].apply(lambda x: dow_order.index(x) if x in dow_order else 99)
                dow = dow.sort_values("ord")
            fig = px.bar(dow, x="dow", y="valor_total", title="Faturamento por Dia da Semana")
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem coluna de dia da semana.")

    st.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)

    st.markdown("#### 🔎 Detalhamento")
    st.dataframe(
        df_f.sort_values("valor_total", ascending=False).head(30),
        use_container_width=True,
        height=340,
    )

# =============================
# TAB 3 - PRODUTOS & ABC
# =============================
with tabs[2]:
    st.markdown("### 🧾 Produtos & Curva ABC")

    if "produto" not in df_f.columns:
        st.info("Sem coluna 'produto' para ABC.")
        st.stop()

    prod = (
        df_f.groupby("produto", as_index=False)
            .agg(valor_total=("valor_total", "sum"), quantidade=("quantidade", "sum"))
            .sort_values("valor_total", ascending=False)
            .reset_index(drop=True)
    )

    total = float(prod["valor_total"].sum())
    prod["share"] = prod["valor_total"] / total if total > 0 else 0
    prod["acumulado"] = prod["share"].cumsum()

    def abc_class(x):
        if x <= 0.80:
            return "A"
        elif x <= 0.95:
            return "B"
        else:
            return "C"

    prod["classe_abc"] = prod["acumulado"].apply(abc_class)

    c1, c2 = st.columns([1.2, 1.0], gap="large")

    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=np.arange(1, len(prod)+1),
            y=prod["acumulado"],
            mode="lines",
            name="Acumulado",
        ))
        fig.add_hline(y=0.80, line_dash="dash")
        fig.add_hline(y=0.95, line_dash="dash")
        fig.update_layout(
            title="Curva ABC (acumulado de faturamento)",
            height=380,
            margin=dict(l=10, r=10, t=50, b=10),
            yaxis_tickformat=".0%",
            xaxis_title="Produtos (ordenados por faturamento)",
            yaxis_title="Acumulado",
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        abc = prod.groupby("classe_abc", as_index=False)["valor_total"].sum()
        fig2 = px.bar(abc, x="classe_abc", y="valor_total", title="Faturamento por Classe ABC")
        fig2.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)

    st.markdown("#### 🏆 Top Produtos")
    show = prod.copy()
    show["valor_total_fmt"] = show["valor_total"].apply(fmt_brl)
    show["share_fmt"] = show["share"].apply(fmt_pct)
    show["acumulado_fmt"] = show["acumulado"].apply(fmt_pct)

    st.dataframe(
        show[["produto", "valor_total_fmt", "quantidade", "share_fmt", "acumulado_fmt", "classe_abc"]].head(50),
        use_container_width=True,
        height=360,
    )

# =============================
# TAB 4 - GEOGRAFIA (UF)
# =============================
with tabs[3]:
    st.markdown("### 🗺️ Geografia (UF)")

    if "uf" not in df_f.columns:
        st.info("Sem coluna UF.")
    else:
        geo = (
            df_f.groupby("uf", as_index=False)["valor_total"].sum()
                .sort_values("valor_total", ascending=False)
        )

        c1, c2 = st.columns([1.1, 1.0], gap="large")

        with c1:
            fig = px.bar(geo, x="valor_total", y="uf", orientation="h", title="Faturamento por UF (R$)")
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            fig2 = px.treemap(geo, path=["uf"], values="valor_total", title="Distribuição por UF (Treemap)")
            fig2.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig2, use_container_width=True)

        st.caption("Obs.: mapa real por UF (choropleth) exige GeoJSON do Brasil. Aqui usamos ranking + treemap (estável).")

# =============================
# TAB 5 - QUALIDADE DE DADOS
# =============================
with tabs[4]:
    st.markdown("### 🧪 Qualidade de Dados")

    colA, colB = st.columns([1.2, 1.0], gap="large")

    with colA:
        st.markdown("#### ✅ Checagens")
        total_rows = len(df_f)
        missing = df_f.isna().mean().sort_values(ascending=False).head(12)
        miss_df = pd.DataFrame({
            "coluna": missing.index,
            "missing_%": (missing.values * 100).round(1)
        })
        st.dataframe(miss_df, use_container_width=True, height=320)

    with colB:
        st.markdown("#### 🔁 Duplicidades")
        if ("produto" in df_f.columns) and ("data" in df_f.columns):
            dd = df_f.copy()
            dd["data_dia"] = pd.to_datetime(dd["data"], errors="coerce").dt.date
            dup_count = int(dd.duplicated(subset=["produto", "data_dia"], keep=False).sum())
            st.metric("Linhas potencialmente duplicadas (Produto + Data)", f"{dup_count:,}".replace(",", "."))
        else:
            st.info("Sem produto/data para checar duplicidade.")

        st.markdown("#### ⚠️ Regras rápidas")
        neg_qtd = int((df_f["quantidade"] < 0).sum()) if "quantidade" in df_f.columns else 0
        zero_total = int((df_f["valor_total"] <= 0).sum())
        st.write(f"- Quantidade negativa: **{neg_qtd}**")
        st.write(f"- Valor total zerado/negativo: **{zero_total}**")

# =============================
# TAB 6 - EXPORTAÇÃO
# =============================
with tabs[5]:
    st.markdown("### 📤 Exportação (Excel Multi-Abas)")

    st.caption("Você pode exportar os dados filtrados e os principais resumos em um único Excel.")

    # resumos
    resumo_kpi = pd.DataFrame([
        {"Indicador": "Faturamento", "Valor_num": faturamento, "Valor_fmt": fmt_brl(faturamento)},
        {"Indicador": "Pedidos", "Valor_num": pedidos, "Valor_fmt": fmt_int(pedidos)},
        {"Indicador": "Quantidade", "Valor_num": qtd_total, "Valor_fmt": fmt_int(qtd_total)},
        {"Indicador": "Ticket Médio", "Valor_num": ticket_medio, "Valor_fmt": fmt_brl(ticket_medio)},
        {"Indicador": "Margem Bruta", "Valor_num": margem_bruta_val, "Valor_fmt": fmt_brl(margem_bruta_val)},
        {"Indicador": "Margem %", "Valor_num": margem_pct, "Valor_fmt": fmt_pct(margem_pct)},
    ])

    # top categoria
    top_cat = None
    if "categoria" in df_f.columns:
        top_cat = (
            df_f.groupby("categoria", as_index=False)["valor_total"].sum()
                .sort_values("valor_total", ascending=False)
                .head(20)
        )

    # top uf
    top_uf = None
    if "uf" in df_f.columns:
        top_uf = (
            df_f.groupby("uf", as_index=False)["valor_total"].sum()
                .sort_values("valor_total", ascending=False)
        )

    def to_excel_bytes() -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            resumo_kpi.to_excel(writer, sheet_name="KPIs", index=False)
            df_f.to_excel(writer, sheet_name="Dados_Filtrados", index=False)

            if top_cat is not None:
                top_cat.to_excel(writer, sheet_name="Top_Categorias", index=False)

            if top_uf is not None:
                top_uf.to_excel(writer, sheet_name="UF", index=False)

        return output.getvalue()

    excel_bytes = to_excel_bytes()
    st.download_button(
        "📥 Baixar Excel (Multi-Abas)",
        data=excel_bytes,
        file_name="dashboard_powerbi_premium_v2.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("<hr class='hr-soft'/>", unsafe_allow_html=True)
    st.markdown("#### Prévia (dados filtrados)")
    st.dataframe(df_f.head(50), use_container_width=True, height=300)