# ============================================================
# Dashboard Executivo Power BI Premium (Streamlit)
# Autor: Benevaldo + ChatGPT
# Objetivo: Dashboard Premium com KPIs, Filtros, Abas, Mapas, Curva ABC e Exportação
# ============================================================

import io
import math
import os
import unicodedata
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# =========================
# CONFIG GERAL
# =========================
st.set_page_config(
    page_title="Dashboard Executivo | Power BI Premium",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS (visual premium)
st.markdown(
    """
<style>
/* Layout mais clean (Power BI-like) */
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
h1, h2, h3 {letter-spacing: .2px;}
/* Cards KPI */
.kpi-card {
    background: #ffffff;
    border: 1px solid rgba(49,51,63,.08);
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0px 1px 10px rgba(0,0,0,.03);
}
.kpi-title {font-size: 0.90rem; color: rgba(49,51,63,.72); margin-bottom: 6px;}
.kpi-value {font-size: 1.55rem; font-weight: 700; color: rgba(49,51,63,.95); line-height: 1.2;}
.kpi-sub {font-size: 0.82rem; color: rgba(49,51,63,.70); margin-top: 6px;}
.badge {
    display:inline-block; padding: 4px 10px; border-radius: 100px;
    font-size: .78rem; background: rgba(17, 129, 255, .10); color: rgba(17, 129, 255, 1);
    border: 1px solid rgba(17, 129, 255, .15);
}
/* Barra lateral */
section[data-testid="stSidebar"] {
    background: rgba(250,250,252,1);
    border-right: 1px solid rgba(49,51,63,.08);
}
/* Ajuste do dataframe */
div[data-testid="stDataFrame"] {border-radius: 14px; overflow:hidden; border: 1px solid rgba(49,51,63,.10);}
</style>
""",
    unsafe_allow_html=True,
)


# =========================
# FUNÇÕES ÚTEIS
# =========================
def _strip_accents(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _norm_col(col: str) -> str:
    col = _strip_accents(col).lower().strip()
    col = col.replace(" ", "_").replace("-", "_").replace("/", "_")
    col = "".join(ch for ch in col if ch.isalnum() or ch == "_")
    while "__" in col:
        col = col.replace("__", "_")
    return col


def brl(x) -> str:
    try:
        x = float(x)
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def pct(x) -> str:
    try:
        return f"{x*100:.1f}%".replace(".", ",")
    except Exception:
        return "0,0%"


def safe_div(a, b):
    if b == 0 or pd.isna(b):
        return 0
    return a / b


def ensure_datetime(df: pd.DataFrame, col_data: str) -> pd.DataFrame:
    if col_data in df.columns:
        df[col_data] = pd.to_datetime(df[col_data], errors="coerce", dayfirst=True)
    return df


@st.cache_data(show_spinner=False)
def load_uploaded_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    if name.endswith(".csv"):
        # Tenta auto-detectar separador
        return pd.read_csv(io.BytesIO(raw), sep=None, engine="python")

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(raw))

    raise ValueError("Formato inválido. Envie CSV ou Excel (.xlsx/.xls).")


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia nomes variados para um esquema padrão:
    data, categoria, marca, uf, canal, produto, quantidade, preco_unitario, valor_total
    """
    df = df.copy()
    original_cols = df.columns.tolist()
    df.columns = [_norm_col(c) for c in df.columns]

    candidates = {
        "data": ["data", "dt", "date", "emissao", "data_emissao", "data_venda"],
        "categoria": ["categoria", "category", "grupo", "departamento", "secao"],
        "marca": ["marca", "brand", "fabricante"],
        "uf": ["uf", "estado", "state"],
        "canal": ["canal", "channel", "origem", "plataforma"],
        "produto": ["produto", "item", "descricao", "descricao_produto", "sku_nome", "nome_produto"],
        "quantidade": ["quantidade", "qtd", "qtde", "quant"],
        "preco_unitario": ["preco_unitario", "valor_unitario", "preco", "vl_unit", "unit_price"],
        "valor_total": ["valor_total", "total", "valor", "faturamento", "venda", "vl_total", "gross_sales"],
        "pedido": ["pedido", "order_id", "id_pedido", "numero_pedido", "nf", "nfe", "nota"],
        "custo_unitario": ["custo_unitario", "custo", "cost_unit", "unit_cost"],
        "custo_total": ["custo_total", "cost_total", "total_cost"],
    }

    def find_col(target):
        for c in candidates[target]:
            if c in df.columns:
                return c
        return None

    # Descobre colunas
    col_data = find_col("data")
    col_categoria = find_col("categoria")
    col_marca = find_col("marca")
    col_uf = find_col("uf")
    col_canal = find_col("canal")
    col_produto = find_col("produto")
    col_qtd = find_col("quantidade")
    col_pu = find_col("preco_unitario")
    col_total = find_col("valor_total")
    col_pedido = find_col("pedido")
    col_cu = find_col("custo_unitario")
    col_ct = find_col("custo_total")

    # Renomeia para padrão
    rename_map = {}
    if col_data: rename_map[col_data] = "data"
    if col_categoria: rename_map[col_categoria] = "categoria"
    if col_marca: rename_map[col_marca] = "marca"
    if col_uf: rename_map[col_uf] = "uf"
    if col_canal: rename_map[col_canal] = "canal"
    if col_produto: rename_map[col_produto] = "produto"
    if col_qtd: rename_map[col_qtd] = "quantidade"
    if col_pu: rename_map[col_pu] = "preco_unitario"
    if col_total: rename_map[col_total] = "valor_total"
    if col_pedido: rename_map[col_pedido] = "pedido"
    if col_cu: rename_map[col_cu] = "custo_unitario"
    if col_ct: rename_map[col_ct] = "custo_total"

    df = df.rename(columns=rename_map)

    # Garante colunas mínimas
    if "quantidade" not in df.columns:
        df["quantidade"] = 1

    # Converte numéricos
    for c in ["quantidade", "preco_unitario", "valor_total", "custo_unitario", "custo_total"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Valor total
    if "valor_total" not in df.columns:
        if "preco_unitario" in df.columns:
            df["valor_total"] = df["quantidade"].fillna(0) * df["preco_unitario"].fillna(0)
        else:
            df["valor_total"] = 0.0

    # Preço unitário
    if "preco_unitario" not in df.columns:
        df["preco_unitario"] = np.where(
            df["quantidade"].fillna(0) > 0,
            df["valor_total"].fillna(0) / df["quantidade"].fillna(1),
            0.0,
        )

    # Custos e margem (se houver)
    if "custo_total" not in df.columns and "custo_unitario" in df.columns:
        df["custo_total"] = df["quantidade"].fillna(0) * df["custo_unitario"].fillna(0)

    if "custo_total" in df.columns:
        df["margem_bruta"] = df["valor_total"].fillna(0) - df["custo_total"].fillna(0)
        df["margem_pct"] = np.where(
            df["valor_total"].fillna(0) > 0,
            df["margem_bruta"] / df["valor_total"],
            0.0,
        )

    # Data
    if "data" in df.columns:
        df = ensure_datetime(df, "data")

    # Campos texto
    for c in ["categoria", "marca", "uf", "canal", "produto"]:
        if c in df.columns:
            df[c] = df[c].astype(str).fillna("")

    # UF padronizada
    if "uf" in df.columns:
        df["uf"] = df["uf"].str.upper().str.strip()

    # Pedido
    if "pedido" not in df.columns:
        # cria um id básico por dia (se houver data)
        if "data" in df.columns and df["data"].notna().any():
            df["pedido"] = df["data"].dt.strftime("%Y%m%d") + "-" + (df.index.astype(str))
        else:
            df["pedido"] = df.index.astype(str)

    # Log de colunas originais (debug visual)
    df.attrs["original_cols"] = original_cols
    return df


@st.cache_data(show_spinner=False)
def demo_data(n=3500, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    datas = pd.date_range("2025-01-01", periods=365)
    categorias = ["INFORMÁTICA", "CELULARES", "GAMES", "ÁUDIO", "ACESSÓRIOS", "TV & VÍDEO"]
    marcas = ["Samsung", "Apple", "Xiaomi", "Dell", "Logitech", "Sony", "Lenovo", "Acer"]
    ufs = ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "PE", "CE", "GO", "ES", "DF"]
    canais = ["Loja Física", "E-commerce", "Marketplace", "B2B"]
    produtos = [f"Produto {i:03d}" for i in range(1, 320)]

    df = pd.DataFrame({
        "data": rng.choice(datas, n),
        "categoria": rng.choice(categorias, n),
        "marca": rng.choice(marcas, n),
        "uf": rng.choice(ufs, n),
        "canal": rng.choice(canais, n),
        "produto": rng.choice(produtos, n),
        "quantidade": rng.integers(1, 8, n),
        "preco_unitario": np.round(rng.uniform(25, 3200, n), 2),
    })
    df["valor_total"] = np.round(df["quantidade"] * df["preco_unitario"], 2)

    # custo fictício para margem
    df["custo_unitario"] = np.round(df["preco_unitario"] * rng.uniform(0.55, 0.85, n), 2)
    df["custo_total"] = np.round(df["quantidade"] * df["custo_unitario"], 2)
    df["margem_bruta"] = df["valor_total"] - df["custo_total"]
    df["margem_pct"] = np.where(df["valor_total"] > 0, df["margem_bruta"] / df["valor_total"], 0.0)

    df["pedido"] = df["data"].dt.strftime("%Y%m%d") + "-" + rng.integers(1000, 9999, n).astype(str)
    return df


def kpi_card(title: str, value: str, sub: str = ""):
    st.markdown(
        f"""
<div class="kpi-card">
  <div class="kpi-title">{title}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-sub">{sub}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def compute_period_delta(df: pd.DataFrame, date_col="data"):
    """
    Retorna (atual, anterior) considerando o range filtrado
    atual = soma do período do filtro
    anterior = soma do período imediatamente anterior com mesma duração
    """
    if date_col not in df.columns or df[date_col].isna().all():
        return None

    dmin = df[date_col].min()
    dmax = df[date_col].max()
    if pd.isna(dmin) or pd.isna(dmax):
        return None

    days = (dmax.date() - dmin.date()).days + 1
    prev_end = dmin - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=days - 1)

    cur = df[(df[date_col] >= dmin) & (df[date_col] <= dmax)]
    prev = df[(df[date_col] >= prev_start) & (df[date_col] <= prev_end)]
    return cur, prev


def top_n_table(df, group_col, value_col="valor_total", n=10):
    if group_col not in df.columns:
        return pd.DataFrame()
    g = df.groupby(group_col, as_index=False)[value_col].sum()
    g = g.sort_values(value_col, ascending=False).head(n)
    return g


def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "data" in d.columns:
        d["data"] = pd.to_datetime(d["data"], errors="coerce")
    return d


def export_excel_multi_sheets(dfs: dict) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, data in dfs.items():
            data.to_excel(writer, index=False, sheet_name=name[:31])
    buffer.seek(0)
    return buffer.getvalue()


# =========================
# HEADER
# =========================
col_h1, col_h2 = st.columns([0.78, 0.22])
with col_h1:
    st.markdown("## 📊 Dashboard Executivo **(Power BI Premium)**")
    st.caption("CSV/Excel • Filtros • KPIs • Comparativos • Mapas • Curva ABC • Exportação Excel Multi-Abas")
with col_h2:
    st.markdown('<span class="badge">Modo Premium</span>', unsafe_allow_html=True)


# =========================
# SIDEBAR (CONFIG + UPLOAD)
# =========================
st.sidebar.markdown("## ⚙️ Configurações")
uploaded = st.sidebar.file_uploader("📤 Enviar CSV/Excel", type=["csv", "xlsx", "xls"])
usar_demo = st.sidebar.toggle("Usar base DEMO (recomendado)", value=(uploaded is None))

st.sidebar.divider()
st.sidebar.markdown("## 🧩 Modelo de Colunas")
st.sidebar.caption(
    "Ideal: Data, Categoria, Marca, UF, Canal, Produto, Quantidade, Preço Unitário, Valor Total."
)

# Carrega base
if usar_demo:
    df_raw = demo_data()
else:
    try:
        df_raw = load_uploaded_file(uploaded)
    except Exception as e:
        st.error(f"Erro ao carregar arquivo: {e}")
        st.stop()

# Mapeia para padrão
df = map_columns(df_raw)

# Checagens básicas
if "valor_total" not in df.columns:
    st.error("Não consegui identificar 'valor_total' e não foi possível calcular.")
    st.stop()

# =========================
# SIDEBAR (FILTROS POWER BI)
# =========================
st.sidebar.divider()
st.sidebar.markdown("## 🎛️ Filtros (Slicers)")

# Filtro Data
df_f = df.copy()
has_date = "data" in df_f.columns and df_f["data"].notna().any()

if has_date:
    dmin = df_f["data"].min().date()
    dmax = df_f["data"].max().date()
    ini, fim = st.sidebar.date_input("📅 Intervalo de datas", value=(dmin, dmax))
    df_f = df_f[(df_f["data"].dt.date >= ini) & (df_f["data"].dt.date <= fim)]
else:
    st.sidebar.info("Sem coluna de data para filtros temporais.")

# Função filtro multi
def sidebar_multiselect(label, col):
    global df_f
    if col not in df_f.columns:
        return
    opts = sorted(df_f[col].dropna().astype(str).unique().tolist())
    sel = st.sidebar.multiselect(label, opts, default=[])
    if sel:
        df_f = df_f[df_f[col].astype(str).isin(sel)]

sidebar_multiselect("Categoria", "categoria")
sidebar_multiselect("Marca", "marca")
sidebar_multiselect("UF", "uf")
sidebar_multiselect("Canal", "canal")

# Busca Produto (Power BI search)
busca = st.sidebar.text_input("🔎 Buscar Produto", "").strip()
if busca and "produto" in df_f.columns:
    df_f = df_f[df_f["produto"].astype(str).str.contains(busca, case=False, na=False)]

# Controle Top N
st.sidebar.divider()
topn = st.sidebar.slider("Top N (Rankings)", min_value=5, max_value=30, value=10, step=1)

# =========================
# KPIs PREMIUM (com comparativo)
# =========================
total_regs = len(df_f)
total_vlr = float(df_f["valor_total"].sum())
qtd_total = float(df_f["quantidade"].sum()) if "quantidade" in df_f.columns else 0.0
ticket = float(df_f["valor_total"].mean()) if total_regs else 0.0
pedidos = df_f["pedido"].nunique() if "pedido" in df_f.columns else total_regs

margem_bruta = float(df_f["margem_bruta"].sum()) if "margem_bruta" in df_f.columns else None
margem_pct = float(df_f["margem_pct"].mean()) if "margem_pct" in df_f.columns else None

# Comparativo período anterior (mesma duração)
delta_info = compute_period_delta(df_f, "data") if has_date else None
if delta_info:
    cur, prev = delta_info
    prev_total = float(prev["valor_total"].sum()) if len(prev) else 0.0
    delta_sales = safe_div((total_vlr - prev_total), prev_total) if prev_total > 0 else 0.0
else:
    delta_sales = None

st.markdown("### 📌 Resumo Executivo (KPIs)")
k1, k2, k3, k4, k5 = st.columns([1, 1, 1, 1, 1])
with k1:
    kpi_card("Faturamento", brl(total_vlr), f"Registros: {total_regs:,}".replace(",", "."))
with k2:
    kpi_card("Pedidos", f"{pedidos:,}".replace(",", "."), "Pedidos únicos")
with k3:
    kpi_card("Quantidade", f"{int(qtd_total):,}".replace(",", "."), "Unidades vendidas")
with k4:
    kpi_card("Ticket Médio", brl(ticket), "Média por registro")
with k5:
    if margem_bruta is not None:
        kpi_card("Margem Bruta", brl(margem_bruta), f"Margem %: {pct(margem_pct)}")
    else:
        if delta_sales is not None:
            kpi_card("Δ vs Período Anterior", pct(delta_sales), "Mesmo tamanho de janela")
        else:
            kpi_card("Status", "OK", "Base carregada e filtrada")


# =========================
# ABAS PREMIUM (Power BI)
# =========================
tabs = st.tabs([
    "🏠 Visão Geral",
    "📈 Vendas & Tendência",
    "🧱 Produtos & ABC",
    "🗺️ Geografia (UF)",
    "🧪 Qualidade de Dados",
    "📦 Exportação",
])

# ------------------------------------------------------------
# ABA 1 - VISÃO GERAL
# ------------------------------------------------------------
with tabs[0]:
    st.markdown("### 📌 Visão Geral")
    c1, c2 = st.columns([0.58, 0.42])

    # Série temporal
    with c1:
        if has_date:
            df_ts = df_f.dropna(subset=["data"]).copy()
            df_ts["dia"] = df_ts["data"].dt.date
            ts = df_ts.groupby("dia", as_index=False)["valor_total"].sum().sort_values("dia")

            # Média móvel 7 dias
            ts["mm7"] = ts["valor_total"].rolling(7, min_periods=1).mean()

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ts["dia"], y=ts["valor_total"], mode="lines", name="Total Diário"))
            fig.add_trace(go.Scatter(x=ts["dia"], y=ts["mm7"], mode="lines", name="Média Móvel (7d)"))
            fig.update_layout(
                title="Evolução do Faturamento",
                margin=dict(l=10, r=10, t=50, b=10),
                height=360,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem coluna de data para gerar evolução temporal.")

    # Top categorias e canais
    with c2:
        st.markdown("#### Rankings (Top N)")
        if "categoria" in df_f.columns:
            top_cat = top_n_table(df_f, "categoria", "valor_total", n=topn)
            fig = px.bar(top_cat, x="valor_total", y="categoria", orientation="h", title="Top Categorias")
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=240)
            st.plotly_chart(fig, use_container_width=True)
        if "canal" in df_f.columns:
            top_canal = df_f.groupby("canal", as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False)
            fig2 = px.pie(top_canal, values="valor_total", names="canal", title="Participação por Canal")
            fig2.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=240)
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("### 📋 Detalhes (Tabela)")
    st.dataframe(format_df_for_display(df_f), use_container_width=True, height=420)


# ------------------------------------------------------------
# ABA 2 - VENDAS & TENDÊNCIA
# ------------------------------------------------------------
with tabs[1]:
    st.markdown("### 📈 Vendas & Tendência")

    left, right = st.columns([0.62, 0.38])

    with left:
        if has_date:
            df_tmp = df_f.dropna(subset=["data"]).copy()
            agg = st.selectbox("Granularidade", ["Diário", "Semanal", "Mensal"], index=2)

            if agg == "Diário":
                df_tmp["t"] = df_tmp["data"].dt.date
            elif agg == "Semanal":
                df_tmp["t"] = df_tmp["data"].dt.to_period("W").astype(str)
            else:
                df_tmp["t"] = df_tmp["data"].dt.to_period("M").astype(str)

            ts = df_tmp.groupby("t", as_index=False)["valor_total"].sum()

            fig = px.area(ts, x="t", y="valor_total", title=f"Faturamento ({agg})")
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=380)
            st.plotly_chart(fig, use_container_width=True)

            # Comparativo simples (último vs penúltimo período)
            if len(ts) >= 2:
                last = float(ts["valor_total"].iloc[-1])
                prev = float(ts["valor_total"].iloc[-2])
                st.info(f"Último período: **{brl(last)}** | Anterior: **{brl(prev)}** | Δ: **{pct(safe_div(last-prev, prev))}**")
        else:
            st.info("Sem data para tendência.")

    with right:
        st.markdown("#### 🔥 Mix de Vendas")
        dims = []
        for col in ["categoria", "marca", "uf", "canal"]:
            if col in df_f.columns:
                dims.append(col)

        dim_sel = st.selectbox("Quebrar por", dims if dims else ["(Sem dimensões)"])
        if dim_sel in df_f.columns:
            mix = df_f.groupby(dim_sel, as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False).head(topn)
            fig = px.bar(mix, x=dim_sel, y="valor_total", title=f"Top {topn} - {dim_sel.title()}")
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=380)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("### 📌 Heatmap (Dia da Semana)")
    if has_date:
        df_h = df_f.dropna(subset=["data"]).copy()
        df_h["dia_semana"] = df_h["data"].dt.day_name()
        order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        df_h["dia_semana"] = pd.Categorical(df_h["dia_semana"], categories=order, ordered=True)
        h = df_h.groupby("dia_semana", as_index=False)["valor_total"].sum().sort_values("dia_semana")

        fig = px.bar(h, x="dia_semana", y="valor_total", title="Faturamento por Dia da Semana")
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem data para dia da semana.")


# ------------------------------------------------------------
# ABA 3 - PRODUTOS & ABC
# ------------------------------------------------------------
with tabs[2]:
    st.markdown("### 🧱 Produtos & Curva ABC (Power BI)")

    colA, colB = st.columns([0.55, 0.45])

    with colA:
        if "produto" in df_f.columns:
            top_prod = df_f.groupby("produto", as_index=False).agg(
                faturamento=("valor_total", "sum"),
                qtd=("quantidade", "sum"),
                ticket=("valor_total", "mean"),
                pedidos=("pedido", "nunique"),
            ).sort_values("faturamento", ascending=False)

            st.markdown("#### 🏆 Top Produtos")
            st.dataframe(top_prod.head(topn), use_container_width=True, height=340)
        else:
            st.info("Sem coluna produto.")

    with colB:
        st.markdown("#### 📌 Curva ABC (por faturamento)")
        if "produto" in df_f.columns:
            abc = df_f.groupby("produto", as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False)
            abc["share"] = abc["valor_total"] / abc["valor_total"].sum()
            abc["share_acum"] = abc["share"].cumsum()

            def class_abc(x):
                if x <= 0.80:
                    return "A"
                if x <= 0.95:
                    return "B"
                return "C"

            abc["classe"] = abc["share_acum"].apply(class_abc)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=np.arange(1, len(abc) + 1),
                y=abc["share_acum"],
                mode="lines",
                name="Acumulado",
            ))
            fig.add_hline(y=0.80, line_dash="dash")
            fig.add_hline(y=0.95, line_dash="dash")
            fig.update_layout(
                title="Curva ABC (Acumulado de Faturamento)",
                xaxis_title="Ranking de Produtos",
                yaxis_title="Participação Acumulada",
                margin=dict(l=10, r=10, t=50, b=10),
                height=360,
            )
            st.plotly_chart(fig, use_container_width=True)

            resumo_abc = abc.groupby("classe", as_index=False)["valor_total"].sum()
            resumo_abc["pct"] = resumo_abc["valor_total"] / resumo_abc["valor_total"].sum()
            st.markdown("#### ✅ Resumo ABC")
            st.dataframe(resumo_abc.assign(
                valor_total=resumo_abc["valor_total"].map(brl),
                pct=resumo_abc["pct"].map(lambda x: f"{x*100:.1f}%".replace(".", ",")),
            ), use_container_width=True, height=210)
        else:
            st.info("Sem coluna produto para Curva ABC.")

    st.divider()
    st.markdown("### 🧠 Treemap (Mix por Categoria/Marca)")
    if "categoria" in df_f.columns and "marca" in df_f.columns:
        tm = df_f.groupby(["categoria", "marca"], as_index=False)["valor_total"].sum()
        fig = px.treemap(tm, path=["categoria", "marca"], values="valor_total", title="Treemap de Faturamento")
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=420)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem categoria/marca para treemap.")


# ------------------------------------------------------------
# ABA 4 - GEOGRAFIA (UF)
# ------------------------------------------------------------
with tabs[3]:
    st.markdown("### 🗺️ Geografia (UF)")

    if "uf" not in df_f.columns:
        st.info("Sem coluna UF para geografia.")
    else:
        geo = (
            df_f.groupby("uf", as_index=False)["valor_total"]
            .sum()
            .sort_values("valor_total", ascending=False)
        )

        # Centróides aproximados das UFs (Lat/Lon)
        UF_CENTROIDS = {
            "AC": (-9.98, -67.81), "AL": (-9.62, -35.73), "AP": (0.03, -51.07),
            "AM": (-3.12, -60.02), "BA": (-12.97, -38.50), "CE": (-3.73, -38.52),
            "DF": (-15.79, -47.88), "ES": (-20.32, -40.33), "GO": (-16.68, -49.25),
            "MA": (-2.53, -44.30), "MT": (-15.60, -56.10), "MS": (-20.45, -54.62),
            "MG": (-19.92, -43.94), "PA": (-1.45, -48.50), "PB": (-7.12, -34.86),
            "PR": (-25.43, -49.27), "PE": (-8.05, -34.88), "PI": (-5.09, -42.80),
            "RJ": (-22.91, -43.17), "RN": (-5.79, -35.21), "RS": (-30.03, -51.23),
            "RO": (-8.76, -63.90), "RR": (2.82, -60.67), "SC": (-27.59, -48.55),
            "SP": (-23.55, -46.63), "SE": (-10.91, -37.07), "TO": (-10.25, -48.33),
        }

        geo["lat"] = geo["uf"].astype(str).str.upper().map(lambda x: UF_CENTROIDS.get(x, (None, None))[0])
        geo["lon"] = geo["uf"].astype(str).str.upper().map(lambda x: UF_CENTROIDS.get(x, (None, None))[1])
        geo = geo.dropna(subset=["lat", "lon"])

        st.markdown("#### 🧭 Mapa por UF (Bolhas) — Estável e Premium")

        fig_map = px.scatter_geo(
            geo,
            lat="lat",
            lon="lon",
            size="valor_total",
            color="valor_total",
            hover_name="uf",
            size_max=45,
            projection="natural earth",
            title="Faturamento por UF (Mapa Premium)",
        )

        fig_map.update_geos(
            scope="south america",
            center=dict(lat=-14.0, lon=-52.0),
            projection_scale=3.2,
            visible=False
        )

        fig_map.update_layout(
            margin=dict(l=10, r=10, t=50, b=10),
            height=480
        )

        st.plotly_chart(fig_map, use_container_width=True)

        col1, col2 = st.columns([0.5, 0.5])

        with col1:
            fig_bar = px.bar(
                geo.sort_values("valor_total", ascending=False).head(topn),
                x="uf",
                y="valor_total",
                title=f"Top {topn} UFs"
            )
            fig_bar.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=340)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col2:
            st.markdown("#### 📌 Detalhes por UF")
            view = geo[["uf", "valor_total"]].copy()
            view["valor_total"] = view["valor_total"].map(brl)
            st.dataframe(view, use_container_width=True, height=340)
# ------------------------------------------------------------
# ABA 5 - QUALIDADE DE DADOS
# ------------------------------------------------------------
with tabs[4]:
    st.markdown("### 🧪 Qualidade de Dados (Data Quality)")

    q1, q2 = st.columns([0.55, 0.45])

    with q1:
        st.markdown("#### Colunas detectadas")
        cols_info = pd.DataFrame({
            "coluna": df.columns,
            "tipo": [str(df[c].dtype) for c in df.columns],
            "nulos": [int(df[c].isna().sum()) for c in df.columns],
            "percent_nulos": [safe_div(df[c].isna().sum(), len(df)) for c in df.columns],
        })
        cols_info["percent_nulos"] = cols_info["percent_nulos"].map(lambda x: f"{x*100:.1f}%".replace(".", ","))
        st.dataframe(cols_info, use_container_width=True, height=360)

    with q2:
        st.markdown("#### Duplicidades (Produto + Data)")
        if "produto" in df.columns and "data" in df.columns:
            dd = df.copy()
            dd["data_dia"] = pd.to_datetime(dd["data"], errors="coerce").dt.date
            dup = dd.duplicated(subset=["produto", "data_dia"], keep=False).sum()
            st.metric("Linhas potencialmente duplicadas", f"{dup:,}".replace(",", "."))
        else:
            st.info("Sem produto/data para checar duplicidade.")

        st.markdown("#### Colunas originais (do arquivo)")
        st.write(df.attrs.get("original_cols", []))

    st.divider()
    st.markdown("### 📌 Preview (base filtrada)")
    st.dataframe(format_df_for_display(df_f).head(500), use_container_width=True, height=420)


# ------------------------------------------------------------
# ABA 6 - EXPORTAÇÃO
# ------------------------------------------------------------
with tabs[5]:
    st.markdown("### 📦 Exportação (Power BI Style)")

    st.markdown("#### ✅ Exportar base filtrada")
    csv_bytes = df_f.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV (Filtrado)",
        data=csv_bytes,
        file_name="base_filtrada.csv",
        mime="text/csv",
    )

    st.markdown("#### ✅ Exportar Excel Multi-Abas")
    # Agregações úteis
    sheets = {}

    sheets["Base_Filtrada"] = df_f.copy()

    if "categoria" in df_f.columns:
        sheets["Por_Categoria"] = df_f.groupby("categoria", as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False)
    if "marca" in df_f.columns:
        sheets["Por_Marca"] = df_f.groupby("marca", as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False)
    if "uf" in df_f.columns:
        sheets["Por_UF"] = df_f.groupby("uf", as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False)
    if has_date:
        tmp = df_f.dropna(subset=["data"]).copy()
        tmp["mes"] = tmp["data"].dt.to_period("M").astype(str)
        sheets["Serie_Mensal"] = tmp.groupby("mes", as_index=False)["valor_total"].sum().sort_values("mes")

    excel_bytes = export_excel_multi_sheets(sheets)

    st.download_button(
        "⬇️ Baixar Excel (Multi-Abas)",
        data=excel_bytes,
        file_name="dashboard_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.info("Dica: você pode enviar seu CSV/Excel no sidebar e exportar a base filtrada já pronta para relatório.")
