from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW = BASE_DIR / "data" / "raw"
OUT = BASE_DIR / "outputs" / "relatorios"
OUT.mkdir(parents=True, exist_ok=True)

def carregar_dados(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(caminho)
    else:
        df = pd.read_csv(caminho, sep=None, engine="python")  # tenta detectar separador
    return df

def limpar_padronizar(df: pd.DataFrame) -> pd.DataFrame:
    # padroniza nomes de colunas (ex.: útil em planilhas fiscais)
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    # exemplo de conversões comuns
    # ajuste os nomes conforme seu arquivo real
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)

    # valores monetários às vezes vêm com vírgula
    for col in ["valor", "total", "valor_total", "base_calculo", "icms"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

def relatorio_resumo(df: pd.DataFrame) -> pd.DataFrame:
    # exemplo fiscal: agrupar por CFOP/NCM se existirem
    chaves = [c for c in ["cfop", "ncm", "uf", "cst"] if c in df.columns]
    if not chaves:
        # fallback: resumo geral
        total_cols = [c for c in ["valor_total", "total", "valor"] if c in df.columns]
        if total_cols:
            return pd.DataFrame({"soma_total": [df[total_cols[0]].sum(skipna=True)]})
        return pd.DataFrame({"linhas": [len(df)]})

    # coluna de valor preferencial
    col_valor = next((c for c in ["valor_total", "total", "valor"] if c in df.columns), None)
    if col_valor is None:
        return df[chaves].value_counts().reset_index(name="qtde")

    resumo = (
        df.groupby(chaves, dropna=False)[col_valor]
        .sum(min_count=1)
        .reset_index()
        .sort_values(col_valor, ascending=False)
    )
    return resumo

def main():
    # troque aqui pelo arquivo que você colocar em data/raw
    # exemplo: data/raw/notas.xlsx ou data/raw/vendas.csv
    arquivo = next(RAW.glob("*.*"), None)
    if arquivo is None:
        raise FileNotFoundError(f"Coloque um arquivo em: {RAW}")

    df = carregar_dados(arquivo)
    df = limpar_padronizar(df)

    resumo = relatorio_resumo(df)

    # exporta relatório
    saida = OUT / "resumo.xlsx"
    with pd.ExcelWriter(saida, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="dados")
        resumo.to_excel(writer, index=False, sheet_name="resumo")

    print(f"OK: Relatório gerado em {saida}")

if __name__ == "__main__":
    main()

