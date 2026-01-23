import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="Dashboard OK", layout="wide")

st.title("✅ Dashboard Streamlit funcionando")
st.caption("Se você está vendo isso, então está renderizando normal.")

# dados fictícios
np.random.seed(7)
df = pd.DataFrame({
    "Dia": pd.date_range("2025-01-01", periods=30),
    "Vendas": np.random.randint(1000, 9000, 30),
    "UF": np.random.choice(["SP", "RJ", "MG", "PR"], 30)
})

st.sidebar.header("Filtros")
ufs = st.sidebar.multiselect("UF", sorted(df["UF"].unique()), default=sorted(df["UF"].unique()))
df_f = df[df["UF"].isin(ufs)]

c1, c2 = st.columns(2)
c1.metric("Total de Vendas", f"{int(df_f['Vendas'].sum()):,}".replace(",", "."))
c2.metric("Média Diária", f"{int(df_f['Vendas'].mean()):,}".replace(",", "."))

fig = px.line(df_f, x="Dia", y="Vendas", title="Vendas por Dia", markers=True)
st.plotly_chart(fig, use_container_width=True)

st.dataframe(df_f, use_container_width=True)