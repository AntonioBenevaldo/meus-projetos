import io
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, date

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm


# ==========================================================
# CONFIG
# ==========================================================
st.set_page_config(
    page_title="Dashboard Executivo | Streamlit",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Dashboard Executivo (estilo Power BI) — Streamlit")
st.caption("Upload de CSV/Excel • Filtros avançados • KPIs • Gráficos • Exportação (CSV/Excel/PDF)")

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def _normalize_columns(cols):
    """Padroniza nomes de colunas (sem acentos simples, espaços -> underscore, etc.)."""
    new_cols = []
    for c in cols:
        c2 = str(c).strip()
        c2 = re.sub(r"\s+", "_", c2)
        c2 = c2.replace("-", "_")
        new_cols.append(c2)
    return new_cols


def _to_numeric_safe(series: pd.Series) -> pd.Series:
    """Converte texto numérico (com vírgula) para float, sem quebrar."""
    if series is None:
        return series
    s = series.astype(str).str.replace(".", "", regex=False)  # remove separador milhar comum
    s = s.str.replace(",", ".", regex=False)                 # decimal pt-BR -> padrão
    return pd.to_numeric(s, errors="coerce")


def _guess_date_column(df: pd.DataFrame):
    """Tenta adivinhar uma coluna de data."""
    candidates = []
    for c in df.columns:
        lc = c.lower()
        if lc in ["data", "date", "dt", "data_venda", "data_emissao", "emissao", "dtemissao"]:
            candidates.append(c)
    if candidates:
        return candidates[0]
    # fallback: achar coluna que parseia bem como data
    best_col = None
    best_rate = 0
    for c in df.columns:
        try:
            parsed = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
            rate = parsed.notna().mean()
            if rate > best_rate and rate > 0.60:
                best_rate = rate
                best_col = c
        except Exception:
            pass
    return best_col


def make_sample_data(n=2000, seed=42):
    """Gera base fictícia (bem realista para comércio)."""
    rng = np.random.default_rng(seed)
    categorias = ["INFORMÁTICA", "CELULARES", "GAMES", "ÁUDIO", "ACESSÓRIOS", "PERIFÉRICOS"]
    marcas = ["Samsung", "Apple", "Xiaomi", "Dell", "Logitech", "Kingston", "Sony", "JBL"]
    ufs = ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "PE", "CE", "GO"]
    canais = ["Loja Física", "E-commerce", "Marketplace", "B2B"]
    vendedores = ["Ana", "Bruno", "Carla", "Diego", "Elaine", "Felipe"]
    municipios = ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba", "Porto Alegre", "Salvador"]

    start = pd.Timestamp("2025-01-01")
    end = pd.Timestamp("2025-12-31")
    days = (end - start).days

    dt = start + pd.to_timedelta(rng.integers(0, days, size=n), unit="D")
    cat = rng.choice(categorias, size=n)
    brand = rng.choice(marcas, size=n)
    uf = rng.choice(ufs, size=n)
    mun = rng.choice(municipios, size=n)
    canal = rng.choice(canais, size=n)
    vend = rng.choice(vendedores, size=n)

    qtd = rng.integers(1, 8, size=n)
    preco = np.round(rng.uniform(20, 2500, size=n), 2)

    # custo (para margem) ~ 60% a 85% do preço
    custo = np.round(preco * rng.uniform(0.60, 0.85, size=n), 2)

    produtos = []
    for i in range(n):
        produtos.append(f"{cat[i]} - {brand[i]} (Modelo {rng.integers(1, 50)})")

    ean = rng.integers(7890000000000, 7899999999999, size=n).astype(str)
    sku = [f"{cat[i][:3]}-{rng.integers(10000, 99999)}" for i in range(n)]

    cliente = [f"Cliente {rng.integers(1, 500)}" for _ in range(n)]
    ncm = rng.choice(["8471.30.12", "8517.12.31", "8528.72.00", "8473.30.49"], size=n)
    cfop = rng.choice(["5102", "6102", "5405", "6405"], size=n)

    valor_total = np.round(qtd * preco, 2)
    lucro = np.round(qtd * (preco - custo), 2)

    df = pd.DataFrame({
        "Data": dt,
        "SKU": sku,
        "EAN": ean,
        "Produto": produtos,
        "Categoria": cat,
        "Marca": brand,
        "UF": uf,
        "Municipio": mun,
        "Canal": canal,
        "Vendedor": vend,
        "Cliente": cliente,
        "NCM": ncm,
        "CFOP": cfop,
        "Quantidade": qtd,
        "Preco_Unitario": preco,
        "Custo_Unitario": custo,
        "Valor_Total": valor_total,
        "Lucro": lucro
    })
    return df


@st.cache_data(show_spinner=False)
def load_data_from_bytes(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """Carrega CSV/XLSX com cache baseado em bytes."""
    if file_name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python")
    elif file_name.lower().endswith(".xlsx") or file_name.lower().endswith(".xls"):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        raise ValueError("Formato não suportado. Envie CSV ou Excel (.xlsx).")
    return df


def format_brl(x):
    try:
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return x


def generate_pdf_report(kpis: dict, top_produtos: pd.DataFrame, top_categorias: pd.DataFrame) -> bytes:
    """Gera um PDF simples com KPIs e Top rankings."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, height - 2 * cm, "Relatório Executivo — Dashboard (Streamlit)")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, height - 2.6 * cm, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # KPI section
    y = height - 4 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Resumo (KPIs)")
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)

    for k, v in kpis.items():
        c.drawString(2 * cm, y, f"- {k}: {v}")
        y -= 0.5 * cm
        if y < 4 * cm:
            c.showPage()
            y = height - 2 * cm

    # Top Produtos
    y -= 0.3 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Top 10 Produtos (por Valor Total)")
    y -= 0.7 * cm
    c.setFont("Helvetica", 9)

    for i, row in top_produtos.head(10).iterrows():
        line = f"{i+1:02d}. {str(row['Produto'])[:55]} — {format_brl(row['Valor_Total'])}"
        c.drawString(2 * cm, y, line)
        y -= 0.45 * cm
        if y < 4 * cm:
            c.showPage()
            y = height - 2 * cm

    # Top Categorias
    y -= 0.3 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Top Categorias (por Valor Total)")
    y -= 0.7 * cm
    c.setFont("Helvetica", 9)

    for i, row in top_categorias.head(10).iterrows():
        line = f"{i+1:02d}. {str(row['Categoria'])[:55]} — {format_brl(row['Valor_Total'])}"
        c.drawString(2 * cm, y, line)
        y -= 0.45 * cm
        if y < 4 * cm:
            c.showPage()
            y = height - 2 * cm

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# ==========================================================
# SIDEBAR — Upload + Config
# ==========================================================
st.sidebar.header("⚙️ Configurações")

uploaded = st.sidebar.file_uploader("📤 Enviar CSV ou Excel", type=["csv", "xlsx", "xls"])
use_sample = st.sidebar.toggle("Usar base fictícia (demo)", value=(uploaded is None))

if use_sample:
    df_raw = make_sample_data(n=3000)
else:
    if uploaded is None:
        st.info("Envie um arquivo ou ative a base fictícia (demo) na barra lateral.")
        st.stop()

    file_bytes = uploaded.getvalue()
    df_raw = load_data_from_bytes(uploaded.name, file_bytes)

# Padroniza colunas
df_raw.columns = _normalize_columns(df_raw.columns)

# Sugestão de coluna data
suggested_date_col = _guess_date_column(df_raw)

st.sidebar.subheader("🧭 Mapeamento de Colunas")
date_col = st.sidebar.selectbox(
    "Coluna de data",
    options=[None] + list(df_raw.columns),
    index=(list([None] + list(df_raw.columns)).index(suggested_date_col)
           if suggested_date_col in df_raw.columns else 0),
    help="Escolha a coluna que representa a data (ex.: Data, Data_Emissao)."
)

# Tenta converter data (se selecionada)
df = df_raw.copy()

if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)

# Sugere colunas úteis
def pick_col(options):
    for name in options:
        if name in df.columns:
            return name
    return None

col_categoria = pick_col(["Categoria", "categoria"])
col_marca = pick_col(["Marca", "marca"])
col_uf = pick_col(["UF", "uf"])
col_produto = pick_col(["Produto", "produto", "Descricao", "descricao"])
col_cliente = pick_col(["Cliente", "cliente"])
col_qtd = pick_col(["Quantidade", "qtd", "Qtde", "quantidade"])
col_valor = pick_col(["Valor_Total", "Total", "valor_total", "Valor"])
col_preco_unit = pick_col(["Preco_Unitario", "Preco", "preco_unitario", "Valor_Unitario"])
col_custo_unit = pick_col(["Custo_Unitario", "custo_unitario"])
col_lucro = pick_col(["Lucro", "lucro"])
col_vendedor = pick_col(["Vendedor", "vendedor"])
col_canal = pick_col(["Canal", "canal"])

# Converte numéricos se existirem
for c in [col_qtd, col_valor, col_preco_unit, col_custo_unit, col_lucro]:
    if c and c in df.columns:
        df[c] = _to_numeric_safe(df[c])

# Se não houver valor total, tenta calcular
if (col_valor is None) and (col_qtd in df.columns) and (col_preco_unit in df.columns):
    df["Valor_Total"] = df[col_qtd] * df[col_preco_unit]
    col_valor = "Valor_Total"

if (col_lucro is None) and (col_qtd in df.columns) and (col_preco_unit in df.columns) and (col_custo_unit in df.columns):
    df["Lucro"] = df[col_qtd] * (df[col_preco_unit] - df[col_custo_unit])
    col_lucro = "Lucro"


# ==========================================================
# SIDEBAR — Filters
# ==========================================================
st.sidebar.divider()
st.sidebar.subheader("🎛️ Filtros")

df_f = df.copy()

# Filtro por data
if date_col and date_col in df_f.columns and df_f[date_col].notna().any():
    min_dt = df_f[date_col].min().date()
    max_dt = df_f[date_col].max().date()

    dt_ini, dt_fim = st.sidebar.date_input(
        "Intervalo de datas",
        value=(min_dt, max_dt),
        min_value=min_dt,
        max_value=max_dt
    )
    if isinstance(dt_ini, date) and isinstance(dt_fim, date):
        df_f = df_f[(df_f[date_col].dt.date >= dt_ini) & (df_f[date_col].dt.date <= dt_fim)]

# Filtros por campos (se existirem)
def multiselect_filter(label, colname):
    global df_f
    if colname and colname in df_f.columns:
        options = sorted(df_f[colname].dropna().astype(str).unique().tolist())
        selected = st.sidebar.multiselect(label, options, default=[])
        if selected:
            df_f = df_f[df_f[colname].astype(str).isin(selected)]

multiselect_filter("Categoria", col_categoria)
multiselect_filter("Marca", col_marca)
multiselect_filter("UF", col_uf)
multiselect_filter("Canal", col_canal)
multiselect_filter("Vendedor", col_vendedor)

# Busca textual (Produto/Cliente)
search_text = st.sidebar.text_input("🔎 Buscar (Produto/Cliente)", value="").strip()
if search_text:
    mask = pd.Series([False] * len(df_f), index=df_f.index)
    if col_produto and col_produto in df_f.columns:
        mask = mask | df_f[col_produto].astype(str).str.contains(search_text, case=False, na=False)
    if col_cliente and col_cliente in df_f.columns:
        mask = mask | df_f[col_cliente].astype(str).str.contains(search_text, case=False, na=False)
    df_f = df_f[mask]

# Slider de valor total (se existir)
if col_valor and col_valor in df_f.columns and df_f[col_valor].notna().any():
    vmin = float(np.nanmin(df_f[col_valor].values))
    vmax = float(np.nanmax(df_f[col_valor].values))
    if vmin != vmax:
        rmin, rmax = st.sidebar.slider(
            "Faixa de Valor Total",
            min_value=float(vmin),
            max_value=float(vmax),
            value=(float(vmin), float(vmax))
        )
        df_f = df_f[(df_f[col_valor] >= rmin) & (df_f[col_valor] <= rmax)]


# ==========================================================
# KPIs
# ==========================================================
st.subheader("📌 Resumo Executivo")

total_registros = len(df_f)
total_valor = float(df_f[col_valor].sum()) if col_valor in df_f.columns else 0.0
total_qtd = float(df_f[col_qtd].sum()) if col_qtd and col_qtd in df_f.columns else np.nan
ticket_medio = float(df_f[col_valor].mean()) if col_valor in df_f.columns and len(df_f) > 0 else 0.0

qtd_produtos_unicos = int(df_f[col_produto].nunique()) if col_produto and col_produto in df_f.columns else 0
qtd_clientes_unicos = int(df_f[col_cliente].nunique()) if col_cliente and col_cliente in df_f.columns else 0

total_lucro = float(df_f[col_lucro].sum()) if col_lucro and col_lucro in df_f.columns else None
margem = None
if total_lucro is not None and total_valor > 0:
    margem = total_lucro / total_valor

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric("Registros", f"{total_registros:,}".replace(",", "."))
c2.metric("Valor Total", format_brl(total_valor))
c3.metric("Ticket Médio", format_brl(ticket_medio))
c4.metric("Produtos únicos", f"{qtd_produtos_unicos:,}".replace(",", "."))
c5.metric("Clientes únicos", f"{qtd_clientes_unicos:,}".replace(",", "."))
if margem is not None:
    c6.metric("Lucro / Margem", f"{format_brl(total_lucro)} | {margem*100:.1f}%")
else:
    c6.metric("Quantidade Total", "-" if np.isnan(total_qtd) else f"{int(total_qtd):,}".replace(",", "."))


# ==========================================================
# GRÁFICOS (Plotly)
# ==========================================================
st.divider()
st.subheader("📈 Análises Visuais")

colA, colB = st.columns(2)

# Série temporal (se tiver data e valor)
if date_col and col_valor and date_col in df_f.columns and df_f[date_col].notna().any():
    df_ts = df_f.dropna(subset=[date_col]).copy()
    df_ts["Dia"] = df_ts[date_col].dt.date
    df_ts = df_ts.groupby("Dia", as_index=False)[col_valor].sum().sort_values("Dia")

    fig_ts = px.line(
        df_ts,
        x="Dia",
        y=col_valor,
        title="Evolução do Valor Total (por dia)",
        markers=True
    )
    colA.plotly_chart(fig_ts, use_container_width=True)
else:
    colA.info("Gráfico temporal: selecione uma coluna de data válida para visualizar a evolução diária.")

# Top 10 Produtos
if col_produto and col_valor and col_produto in df_f.columns:
    top_prod = (
        df_f.groupby(col_produto, as_index=False)[col_valor]
        .sum()
        .sort_values(col_valor, ascending=False)
        .head(10)
    )
    fig_top_prod = px.bar(
        top_prod,
        x=col_valor,
        y=col_produto,
        orientation="h",
        title="Top 10 Produtos (por Valor Total)"
    )
    colB.plotly_chart(fig_top_prod, use_container_width=True)
else:
    colB.info("Top Produtos: colunas de Produto e Valor Total não encontradas.")

colC, colD = st.columns(2)

# Por Categoria
if col_categoria and col_valor and col_categoria in df_f.columns:
    by_cat = (
        df_f.groupby(col_categoria, as_index=False)[col_valor]
        .sum()
        .sort_values(col_valor, ascending=False)
    )
    fig_cat = px.bar(by_cat.head(15), x=col_categoria, y=col_valor, title="Valor Total por Categoria (Top 15)")
    colC.plotly_chart(fig_cat, use_container_width=True)
else:
    colC.info("Categoria: coluna não encontrada para agrupar.")

# Por UF (Pizza)
if col_uf and col_valor and col_uf in df_f.columns:
    by_uf = (
        df_f.groupby(col_uf, as_index=False)[col_valor]
        .sum()
        .sort_values(col_valor, ascending=False)
    )
    fig_uf = px.pie(by_uf.head(12), names=col_uf, values=col_valor, title="Distribuição do Valor Total por UF")
    colD.plotly_chart(fig_uf, use_container_width=True)
else:
    colD.info("UF: coluna não encontrada para agrupar.")


# ==========================================================
# TABELA DETALHADA
# ==========================================================
st.divider()
st.subheader("📋 Tabela Detalhada (com filtros aplicados)")

# Ordenação
order_options = []
if col_valor and col_valor in df_f.columns:
    order_options.append(col_valor)
if date_col and date_col in df_f.columns:
    order_options.append(date_col)
if col_produto and col_produto in df_f.columns:
    order_options.append(col_produto)

order_by = st.selectbox("Ordenar por", options=order_options if order_options else df_f.columns.tolist())

ascending = st.toggle("Ordem crescente", value=False)
df_show = df_f.sort_values(order_by, ascending=ascending)

# Mostra dataframe
st.dataframe(df_show, use_container_width=True, height=420)


# ==========================================================
# EXPORTAÇÕES: CSV / EXCEL / PDF
# ==========================================================
st.divider()
st.subheader("📦 Exportações")

col1, col2, col3 = st.columns(3)

# CSV
csv_bytes = df_show.to_csv(index=False).encode("utf-8")
col1.download_button(
    label="⬇️ Baixar CSV (filtrado)",
    data=csv_bytes,
    file_name="dados_filtrados.csv",
    mime="text/csv"
)

# Excel
excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    df_show.to_excel(writer, index=False, sheet_name="Filtrado")
excel_buffer.seek(0)

col2.download_button(
    label="⬇️ Baixar Excel (filtrado)",
    data=excel_buffer.getvalue(),
    file_name="dados_filtrados.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# PDF Resumo Executivo
# Monta tabelas top para o PDF
top_produtos_pdf = pd.DataFrame({"Produto": [], "Valor_Total": []})
top_categorias_pdf = pd.DataFrame({"Categoria": [], "Valor_Total": []})

if col_produto and col_valor and col_produto in df_show.columns:
    top_produtos_pdf = (
        df_show.groupby(col_produto, as_index=False)[col_valor]
        .sum()
        .sort_values(col_valor, ascending=False)
        .head(10)
        .rename(columns={col_produto: "Produto", col_valor: "Valor_Total"})
    )

if col_categoria and col_valor and col_categoria in df_show.columns:
    top_categorias_pdf = (
        df_show.groupby(col_categoria, as_index=False)[col_valor]
        .sum()
        .sort_values(col_valor, ascending=False)
        .head(10)
        .rename(columns={col_categoria: "Categoria", col_valor: "Valor_Total"})
    )

kpis_pdf = {
    "Registros": f"{total_registros:,}".replace(",", "."),
    "Valor Total": format_brl(total_valor),
    "Ticket Médio": format_brl(ticket_medio),
    "Produtos únicos": f"{qtd_produtos_unicos:,}".replace(",", "."),
    "Clientes únicos": f"{qtd_clientes_unicos:,}".replace(",", "."),
}

if margem is not None:
    kpis_pdf["Lucro Total"] = format_brl(total_lucro)
    kpis_pdf["Margem"] = f"{margem*100:.1f}%"

pdf_bytes = generate_pdf_report(kpis_pdf, top_produtos_pdf, top_categorias_pdf)

col3.download_button(
    label="⬇️ Baixar PDF (Resumo Executivo)",
    data=pdf_bytes,
    file_name="relatorio_executivo.pdf",
    mime="application/pdf"
)


# ==========================================================
# MODELO / TEMPLATE
# ==========================================================
st.divider()
st.subheader("🧩 Modelo de Arquivo (CSV) para você preencher")

template = make_sample_data(n=50, seed=7)
template_bytes = template.to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇️ Baixar modelo CSV (exemplo)",
    data=template_bytes,
    file_name="modelo_dashboard.csv",
    mime="text/csv"
)

st.caption("Dica: se sua base tiver nomes diferentes de colunas, você pode renomear no Excel/CSV ou adaptar o mapeamento no código.")
