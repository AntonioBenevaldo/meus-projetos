import sys
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTabWidget, QTableView, QMessageBox,
    QComboBox, QGroupBox, QFormLayout
)

# Matplotlib (gráficos)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# =========================
# Model do Pandas -> QTableView
# =========================
class PandasTableModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df.copy()

    def rowCount(self, parent=None):
        return len(self.df)

    def columnCount(self, parent=None):
        return len(self.df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            value = self.df.iloc[index.row(), index.column()]
            if pd.isna(value):
                return ""

            # Formatação simples (números com 2 casas)
            if isinstance(value, float):
                return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return str(value)

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self.df.columns[section])
        return str(section)

    def update(self, df: pd.DataFrame):
        self.beginResetModel()
        self.df = df.copy()
        self.endResetModel()


# =========================
# Helpers - carregar e montar base
# =========================
def carregar_base_erp(data_dir: Path) -> pd.DataFrame:
    """
    Dataset ERP:
    - clientes.csv
    - produtos.csv
    - vendas.csv
    - itens_venda.csv
    """
    clientes = pd.read_csv(data_dir / "clientes.csv")
    produtos = pd.read_csv(data_dir / "produtos.csv")
    vendas = pd.read_csv(data_dir / "vendas.csv", parse_dates=["data"])
    itens = pd.read_csv(data_dir / "itens_venda.csv")

    base = (itens
            .merge(vendas, on="venda_id", how="left")
            .merge(produtos, on="produto_id", how="left")
            .merge(clientes, on="cliente_id", how="left"))

    # Padronizar nome do produto (se vier como "descricao")
    if "produto" not in base.columns and "descricao" in base.columns:
        base.rename(columns={"descricao": "produto"}, inplace=True)

    # Padronizar colunas de valor (para suportar datasets parecidos)
    # faturamento_base: valor_total > v_prod
    if "valor_total" not in base.columns and "v_prod" in base.columns:
        base.rename(columns={"v_prod": "valor_total"}, inplace=True)

    # preco unitário: preco_unitario > v_un
    if "preco_unitario" not in base.columns and "v_un" in base.columns:
        base.rename(columns={"v_un": "preco_unitario"}, inplace=True)

    # data: data > dh_emissao
    if "data" not in base.columns and "dh_emissao" in base.columns:
        base.rename(columns={"dh_emissao": "data"}, inplace=True)
        base["data"] = pd.to_datetime(base["data"], errors="coerce")

    # Normalizar ean para string
    if "ean" in base.columns:
        base["ean"] = base["ean"].astype(str)

    return base


def checar_arquivos_erp(data_dir: Path):
    arquivos = ["clientes.csv", "produtos.csv", "vendas.csv", "itens_venda.csv"]
    faltando = [a for a in arquivos if not (data_dir / a).exists()]
    return faltando


def format_brl(valor: float) -> str:
    # Formata BRL simples sem locale
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# =========================
# Dashboard v3
# =========================
class DashboardV3(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard v3 - Ciência de Dados (ERP / Fiscal)")
        self.resize(1300, 750)

        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "dados"

        self.base = pd.DataFrame()
        self.base_filtrada = pd.DataFrame()

        # -------------------------
        # Layout principal
        # -------------------------
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # -------------------------
        # Barra superior
        # -------------------------
        top_bar = QHBoxLayout()

        self.btn_carregar = QPushButton("Carregar (pasta dados/)")
        self.btn_carregar.clicked.connect(self.on_carregar)

        self.btn_escolher_pasta = QPushButton("Escolher pasta...")
        self.btn_escolher_pasta.clicked.connect(self.on_escolher_pasta)

        self.btn_limpar = QPushButton("Limpar filtros")
        self.btn_limpar.clicked.connect(self.on_limpar_filtros)
        self.btn_limpar.setEnabled(False)

        self.btn_exportar = QPushButton("Exportar Excel (abas)")
        self.btn_exportar.clicked.connect(self.on_exportar_excel)
        self.btn_exportar.setEnabled(False)

        self.lbl_status = QLabel("Status: aguardando...")
        self.lbl_status.setStyleSheet("font-weight: bold;")

        top_bar.addWidget(self.btn_carregar)
        top_bar.addWidget(self.btn_escolher_pasta)
        top_bar.addWidget(self.btn_limpar)
        top_bar.addWidget(self.btn_exportar)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_status)

        main_layout.addLayout(top_bar)

        # -------------------------
        # Área de filtros (busca + combos)
        # -------------------------
        filtros_box = QGroupBox("Filtros")
        filtros_layout = QHBoxLayout(filtros_box)

        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Buscar (produto, EAN, UF, canal, cliente, CFOP...)")
        self.input_busca.textChanged.connect(self.aplicar_filtros)

        self.combo_uf = QComboBox()
        self.combo_uf.currentIndexChanged.connect(self.aplicar_filtros)

        self.combo_canal = QComboBox()
        self.combo_canal.currentIndexChanged.connect(self.aplicar_filtros)

        self.combo_categoria = QComboBox()
        self.combo_categoria.currentIndexChanged.connect(self.aplicar_filtros)

        self.combo_status = QComboBox()
        self.combo_status.currentIndexChanged.connect(self.aplicar_filtros)

        self.lbl_linhas = QLabel("Linhas: 0")
        self.lbl_linhas.setStyleSheet("font-weight: bold;")

        filtros_layout.addWidget(QLabel("Texto:"))
        filtros_layout.addWidget(self.input_busca, 2)
        filtros_layout.addWidget(self.combo_uf)
        filtros_layout.addWidget(self.combo_canal)
        filtros_layout.addWidget(self.combo_categoria)
        filtros_layout.addWidget(self.combo_status)
        filtros_layout.addWidget(self.lbl_linhas)

        main_layout.addWidget(filtros_box)

        # -------------------------
        # Tabs
        # -------------------------
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # TAB 1 - Tabela
        self.tab_tabela = QWidget()
        self.tabs.addTab(self.tab_tabela, "Tabela")

        tab1_layout = QVBoxLayout(self.tab_tabela)

        self.table = QTableView()
        self.table.setSortingEnabled(True)
        tab1_layout.addWidget(self.table)

        self.model = PandasTableModel(pd.DataFrame())
        self.table.setModel(self.model)

        # TAB 2 - KPIs
        self.tab_kpis = QWidget()
        self.tabs.addTab(self.tab_kpis, "KPIs")

        tab2_layout = QHBoxLayout(self.tab_kpis)

        kpi_box = QGroupBox("KPIs (dinâmicos)")
        kpi_form = QFormLayout(kpi_box)

        self.lbl_kpi_faturamento = QLabel("-")
        self.lbl_kpi_ticket = QLabel("-")
        self.lbl_kpi_vendas = QLabel("-")
        self.lbl_kpi_itens = QLabel("-")
        self.lbl_kpi_margem = QLabel("-")

        kpi_form.addRow("Faturamento:", self.lbl_kpi_faturamento)
        kpi_form.addRow("Ticket médio:", self.lbl_kpi_ticket)
        kpi_form.addRow("Qtd vendas:", self.lbl_kpi_vendas)
        kpi_form.addRow("Qtd itens:", self.lbl_kpi_itens)
        kpi_form.addRow("Margem bruta:", self.lbl_kpi_margem)

        tab2_layout.addWidget(kpi_box, 1)

        # TAB 3 - Gráficos
        self.tab_graficos = QWidget()
        self.tabs.addTab(self.tab_graficos, "Gráficos")

        tab3_layout = QVBoxLayout(self.tab_graficos)
        self.tabs_graficos = QTabWidget()
        tab3_layout.addWidget(self.tabs_graficos)

        # Gráfico Top Produtos
        self.graf_top_prod = QWidget()
        self.tabs_graficos.addTab(self.graf_top_prod, "Top Produtos")
        g1_layout = QVBoxLayout(self.graf_top_prod)
        self.fig_top = Figure(figsize=(6, 4))
        self.canvas_top = FigureCanvas(self.fig_top)
        g1_layout.addWidget(self.canvas_top)

        # Gráfico Faturamento Mensal
        self.graf_mensal = QWidget()
        self.tabs_graficos.addTab(self.graf_mensal, "Faturamento Mensal")
        g2_layout = QVBoxLayout(self.graf_mensal)
        self.fig_mes = Figure(figsize=(6, 4))
        self.canvas_mes = FigureCanvas(self.fig_mes)
        g2_layout.addWidget(self.canvas_mes)

        # Gráfico Faturamento por Canal
        self.graf_canal = QWidget()
        self.tabs_graficos.addTab(self.graf_canal, "Por Canal")
        g3_layout = QVBoxLayout(self.graf_canal)
        self.fig_canal = Figure(figsize=(6, 4))
        self.canvas_canal = FigureCanvas(self.fig_canal)
        g3_layout.addWidget(self.canvas_canal)

        # TAB 4 - Qualidade
        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade de Dados")

        tab4_layout = QVBoxLayout(self.tab_quality)

        self.lbl_quality = QLabel("Carregue os dados para ver a qualidade.")
        self.lbl_quality.setStyleSheet("font-size: 13px;")
        self.lbl_quality.setTextInteractionFlags(Qt.TextSelectableByMouse)

        tab4_layout.addWidget(self.lbl_quality)

        # Autoload se existir
        if self.data_dir.exists():
            self.on_carregar()

    # =========================
    # Ações
    # =========================
    def on_escolher_pasta(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecione a pasta dos CSVs")
        if folder:
            self.data_dir = Path(folder)
            self.on_carregar()

    def on_carregar(self):
        try:
            faltando = checar_arquivos_erp(self.data_dir)
            if faltando:
                raise FileNotFoundError(f"Arquivos faltando em {self.data_dir}: {faltando}")

            self.base = carregar_base_erp(self.data_dir)
            self.base_filtrada = self.base.copy()

            self.preencher_combos()
            self.atualizar_tabela()
            self.atualizar_kpis()
            self.atualizar_graficos()
            self.atualizar_quality()

            self.btn_exportar.setEnabled(True)
            self.btn_limpar.setEnabled(True)

            self.lbl_status.setText(f"Status: OK | Base: {self.base.shape[0]} linhas / {self.base.shape[1]} colunas")

        except Exception as e:
            QMessageBox.critical(self, "Erro ao carregar", str(e))
            self.lbl_status.setText("Status: ERRO ao carregar")

    def on_limpar_filtros(self):
        self.input_busca.setText("")

        # reset combos
        self.combo_uf.setCurrentIndex(0)
        self.combo_canal.setCurrentIndex(0)
        self.combo_categoria.setCurrentIndex(0)
        self.combo_status.setCurrentIndex(0)

        self.base_filtrada = self.base.copy()
        self.atualizar_tabela()
        self.atualizar_kpis()
        self.atualizar_graficos()
        self.atualizar_quality()

    def on_exportar_excel(self):
        if self.base.empty:
            return

        df_export = self.base_filtrada if not self.base_filtrada.empty else self.base

        arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar relatório Excel",
            str(self.base_dir / "relatorio_dashboard_v3.xlsx"),
            "Excel (*.xlsx)"
        )
        if not arquivo:
            return

        try:
            # Tabelas auxiliares para abas
            kpis = self.calcular_kpis(df_export)
            top_prod = self.calcular_top_produtos(df_export)
            serie_mes = self.calcular_serie_mensal(df_export)
            quality = self.calcular_quality(df_export)

            with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
                df_export.to_excel(writer, sheet_name="Base_Filtrada", index=False)

                pd.DataFrame([kpis]).to_excel(writer, sheet_name="KPIs", index=False)

                top_prod.to_frame("faturamento").reset_index().rename(columns={"index": "produto"}).to_excel(
                    writer, sheet_name="Top_Produtos", index=False
                )

                serie_mes.reset_index().rename(columns={"index": "mes", 0: "faturamento"}).to_excel(
                    writer, sheet_name="Faturamento_Mensal", index=False
                )

                quality.to_excel(writer, sheet_name="Qualidade", index=False)

            QMessageBox.information(self, "Exportado", f"✅ Excel salvo com sucesso:\n{arquivo}")

        except Exception as e:
            QMessageBox.critical(self, "Erro ao exportar", str(e))

    # =========================
    # Filtros
    # =========================
    def preencher_combos(self):
        # bloquear sinais para não disparar filtro durante preenchimento
        self.combo_uf.blockSignals(True)
        self.combo_canal.blockSignals(True)
        self.combo_categoria.blockSignals(True)
        self.combo_status.blockSignals(True)

        self.combo_uf.clear()
        self.combo_canal.clear()
        self.combo_categoria.clear()
        self.combo_status.clear()

        self.combo_uf.addItem("UF: Todas")
        self.combo_canal.addItem("Canal: Todos")
        self.combo_categoria.addItem("Categoria: Todas")
        self.combo_status.addItem("Status: Todos")

        if "uf_destino" in self.base.columns:
            for u in sorted(self.base["uf_destino"].dropna().unique().tolist()):
                self.combo_uf.addItem(f"UF: {u}")

        if "canal" in self.base.columns:
            for c in sorted(self.base["canal"].dropna().unique().tolist()):
                self.combo_canal.addItem(f"Canal: {c}")

        if "categoria" in self.base.columns:
            for cat in sorted(self.base["categoria"].dropna().unique().tolist()):
                self.combo_categoria.addItem(f"Categoria: {cat}")

        if "status" in self.base.columns:
            for st in sorted(self.base["status"].dropna().unique().tolist()):
                self.combo_status.addItem(f"Status: {st}")

        self.combo_uf.blockSignals(False)
        self.combo_canal.blockSignals(False)
        self.combo_categoria.blockSignals(False)
        self.combo_status.blockSignals(False)

    def aplicar_filtros(self):
        if self.base.empty:
            return

        df = self.base.copy()

        # 1) Texto
        termo = self.input_busca.text().strip().lower()
        if termo:
            # melhora performance: procurar em um subconjunto de colunas mais úteis
            cols_busca = [c for c in df.columns if c.lower() in [
                "produto", "ean", "uf_destino", "canal", "categoria",
                "cfop", "cst_icms", "nome", "documento", "marca"
            ]]
            if not cols_busca:
                cols_busca = df.columns.tolist()

            mask = df[cols_busca].astype(str).apply(
                lambda col: col.str.lower().str.contains(termo, na=False)
            ).any(axis=1)
            df = df[mask]

        # 2) UF
        uf_sel = self.combo_uf.currentText().replace("UF: ", "")
        if uf_sel != "Todas" and "uf_destino" in df.columns:
            df = df[df["uf_destino"] == uf_sel]

        # 3) Canal
        canal_sel = self.combo_canal.currentText().replace("Canal: ", "")
        if canal_sel != "Todos" and "canal" in df.columns:
            df = df[df["canal"] == canal_sel]

        # 4) Categoria
        cat_sel = self.combo_categoria.currentText().replace("Categoria: ", "")
        if cat_sel != "Todas" and "categoria" in df.columns:
            df = df[df["categoria"] == cat_sel]

        # 5) Status
        st_sel = self.combo_status.currentText().replace("Status: ", "")
        if st_sel != "Todos" and "status" in df.columns:
            df = df[df["status"] == st_sel]

        self.base_filtrada = df.copy()

        self.atualizar_tabela()
        self.atualizar_kpis()
        self.atualizar_graficos()
        self.atualizar_quality()

    # =========================
    # Atualizações UI
    # =========================
    def atualizar_tabela(self):
        df = self.base_filtrada if not self.base_filtrada.empty else self.base
        self.model.update(df)
        self.lbl_linhas.setText(f"Linhas: {len(df):,}".replace(",", "."))

    # =========================
    # KPIs / Cálculos
    # =========================
    def calcular_kpis(self, df: pd.DataFrame) -> dict:
        base = df.copy()

        # faturamento base
        if "valor_total" not in base.columns:
            raise ValueError("Coluna de faturamento não encontrada (valor_total).")

        base["faturamento"] = base["valor_total"]

        faturamento_total = float(base["faturamento"].sum())
        qtd_vendas = int(base["venda_id"].nunique()) if "venda_id" in base.columns else int(base.shape[0])
        ticket_medio = float(base.groupby("venda_id")["faturamento"].sum().mean()) if "venda_id" in base.columns else faturamento_total

        qtd_itens = int(base.shape[0])

        # margem bruta (se tiver custo_total)
        margem = None
        if "custo_total" in base.columns:
            lucro = base["faturamento"].sum() - base["custo_total"].sum()
            margem = float((lucro / base["faturamento"].sum()) * 100) if base["faturamento"].sum() != 0 else 0.0

        return {
            "faturamento_total": faturamento_total,
            "qtd_vendas": qtd_vendas,
            "ticket_medio": ticket_medio,
            "qtd_itens": qtd_itens,
            "margem_bruta_pct": margem
        }

    def calcular_top_produtos(self, df: pd.DataFrame) -> pd.Series:
        base = df.copy()
        base["faturamento"] = base["valor_total"]

        if "produto" in base.columns:
            return (base.groupby("produto")["faturamento"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(10))
        else:
            return pd.Series(dtype=float)

    def calcular_serie_mensal(self, df: pd.DataFrame) -> pd.Series:
        base = df.copy()
        base["faturamento"] = base["valor_total"]

        if "data" not in base.columns:
            return pd.Series(dtype=float)

        # converter para datetime
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
        base = base.dropna(subset=["data"])

        serie = (base.groupby(base["data"].dt.to_period("M"))["faturamento"]
                 .sum()
                 .sort_index())

        # Series index é Period; vamos manter
        return serie

    def calcular_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        base = df.copy()

        # Nulos (top)
        nulos = base.isna().sum().sort_values(ascending=False)
        nulos_top = nulos.head(15)

        # EAN inválido
        ean_invalidos = 0
        ean_duplicados = 0
        if "ean" in base.columns:
            ean_len = base["ean"].astype(str).str.len()
            ean_invalidos = int((ean_len != 13).sum())

            dup = base[base.duplicated(subset=["ean"], keep=False)]
            ean_duplicados = int(dup["ean"].nunique())

        # Outliers de preço unitário (IQR)
        outliers = 0
        if "preco_unitario" in base.columns:
            q1 = base["preco_unitario"].quantile(0.25)
            q3 = base["preco_unitario"].quantile(0.75)
            iqr = q3 - q1
            lim_sup = q3 + 1.5 * iqr
            outliers = int((base["preco_unitario"] > lim_sup).sum())

        # Tabela resumo
        resumo = [
            ("linhas", base.shape[0]),
            ("colunas", base.shape[1]),
            ("ean_invalidos(len!=13)", ean_invalidos),
            ("ean_duplicados(distintos)", ean_duplicados),
            ("outliers_preco_unitario(IQR)", outliers),
        ]

        df_resumo = pd.DataFrame(resumo, columns=["metrica", "valor"])
        df_nulos = pd.DataFrame({"coluna": nulos_top.index, "nulos": nulos_top.values})

        return pd.concat([df_resumo, df_nulos], ignore_index=True)

    def atualizar_kpis(self):
        if self.base.empty:
            return

        df = self.base_filtrada if not self.base_filtrada.empty else self.base
        kpis = self.calcular_kpis(df)

        self.lbl_kpi_faturamento.setText(format_brl(kpis["faturamento_total"]))
        self.lbl_kpi_ticket.setText(format_brl(kpis["ticket_medio"]))
        self.lbl_kpi_vendas.setText(str(kpis["qtd_vendas"]))
        self.lbl_kpi_itens.setText(str(kpis["qtd_itens"]))

        if kpis["margem_bruta_pct"] is None:
            self.lbl_kpi_margem.setText("—")
        else:
            self.lbl_kpi_margem.setText(f"{kpis['margem_bruta_pct']:.2f}%".replace(".", ","))

    def atualizar_graficos(self):
        if self.base.empty:
            return

        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        # -------- Top Produtos --------
        top = self.calcular_top_produtos(df)
        self.fig_top.clear()
        ax1 = self.fig_top.add_subplot(111)
        ax1.set_title("Top 10 Produtos por Faturamento")
        if len(top) > 0:
            ax1.bar(top.index.astype(str), top.values)
            ax1.tick_params(axis="x", rotation=45)
        else:
            ax1.text(0.5, 0.5, "Coluna 'produto' não disponível.", ha="center", va="center")
        self.fig_top.tight_layout()
        self.canvas_top.draw()

        # -------- Faturamento Mensal --------
        serie = self.calcular_serie_mensal(df)
        self.fig_mes.clear()
        ax2 = self.fig_mes.add_subplot(111)
        ax2.set_title("Faturamento Mensal")
        if len(serie) > 0:
            # converter PeriodIndex para string
            x = [str(p) for p in serie.index]
            ax2.plot(x, serie.values, marker="o")
            ax2.tick_params(axis="x", rotation=45)
        else:
            ax2.text(0.5, 0.5, "Coluna 'data' não disponível.", ha="center", va="center")
        self.fig_mes.tight_layout()
        self.canvas_mes.draw()

        # -------- Faturamento por Canal --------
        self.fig_canal.clear()
        ax3 = self.fig_canal.add_subplot(111)
        ax3.set_title("Faturamento por Canal")

        if "canal" in df.columns:
            tmp = df.copy()
            tmp["faturamento"] = tmp["valor_total"]
            fat_canal = tmp.groupby("canal")["faturamento"].sum().sort_values(ascending=False)
            if len(fat_canal) > 0:
                ax3.bar(fat_canal.index.astype(str), fat_canal.values)
            else:
                ax3.text(0.5, 0.5, "Sem dados para canal.", ha="center", va="center")
        else:
            ax3.text(0.5, 0.5, "Coluna 'canal' não disponível.", ha="center", va="center")

        self.fig_canal.tight_layout()
        self.canvas_canal.draw()

    def atualizar_quality(self):
        if self.base.empty:
            return

        df = self.base_filtrada if not self.base_filtrada.empty else self.base
        quality_df = self.calcular_quality(df)

        # Montar texto da qualidade
        linhas = []
        for _, row in quality_df.head(25).iterrows():
            col1 = str(row.get("metrica", "")) if "metrica" in quality_df.columns else ""
            if col1 and col1 != "nan":
                linhas.append(f"- {row['metrica']}: {row['valor']}")
            else:
                # seção nulos
                if "coluna" in row and "nulos" in row:
                    linhas.append(f"  • nulos -> {row['coluna']}: {int(row['nulos'])}")

        texto = "🧪 Qualidade de Dados (recorte filtrado)\n\n" + "\n".join(linhas)
        self.lbl_quality.setText(texto)


def main():
    app = QApplication(sys.argv)
    w = DashboardV3()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
