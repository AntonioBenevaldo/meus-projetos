import sys
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTabWidget, QTableView, QMessageBox
)

# Matplotlib (gráfico dentro do PySide6)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# =========================
# Model do Pandas para QTableView
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
            # Formatação básica
            if pd.isna(value):
                return ""
            if isinstance(value, (float, int)):
                return f"{value}"
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
# Função: carregar e montar base
# =========================
def carregar_base(data_dir: Path) -> pd.DataFrame:
    clientes = pd.read_csv(data_dir / "clientes.csv")
    produtos = pd.read_csv(data_dir / "produtos.csv")
    vendas = pd.read_csv(data_dir / "vendas.csv", parse_dates=["data"])
    itens = pd.read_csv(data_dir / "itens_venda.csv")

    base = (itens
            .merge(vendas, on="venda_id", how="left")
            .merge(produtos, on="produto_id", how="left")
            .merge(clientes, on="cliente_id", how="left"))

    # Ajuste automático: se dataset for Fiscal/NFe e tiver "descricao" e não "produto"
    if "produto" not in base.columns and "descricao" in base.columns:
        base.rename(columns={"descricao": "produto"}, inplace=True)

    return base


# =========================
# Main Window
# =========================
class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard - Ciência de Dados (ERP/Fiscal)")
        self.resize(1200, 700)

        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "dados"

        self.base = pd.DataFrame()
        self.base_filtrada = pd.DataFrame()

        # UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top bar
        top_bar = QHBoxLayout()
        self.lbl_status = QLabel("Status: aguardando carregar dados...")
        self.lbl_status.setStyleSheet("font-weight: bold;")

        self.btn_carregar = QPushButton("Carregar dados (pasta dados/)")
        self.btn_carregar.clicked.connect(self.on_carregar)

        self.btn_escolher_pasta = QPushButton("Escolher pasta...")
        self.btn_escolher_pasta.clicked.connect(self.on_escolher_pasta)

        self.btn_exportar = QPushButton("Exportar Excel")
        self.btn_exportar.clicked.connect(self.on_exportar_excel)
        self.btn_exportar.setEnabled(False)

        top_bar.addWidget(self.btn_carregar)
        top_bar.addWidget(self.btn_escolher_pasta)
        top_bar.addWidget(self.btn_exportar)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_status)

        layout.addLayout(top_bar)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # TAB 1: Tabela
        self.tab_tabela = QWidget()
        self.tabs.addTab(self.tab_tabela, "Tabela (Base)")

        tab1_layout = QVBoxLayout(self.tab_tabela)

        filtros_layout = QHBoxLayout()
        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Buscar (produto, EAN, UF, canal, etc.)...")
        self.input_busca.textChanged.connect(self.on_filtrar)

        self.lbl_qtd = QLabel("Linhas: 0")
        filtros_layout.addWidget(QLabel("Filtro:"))
        filtros_layout.addWidget(self.input_busca)
        filtros_layout.addWidget(self.lbl_qtd)

        tab1_layout.addLayout(filtros_layout)

        self.table = QTableView()
        self.table.setSortingEnabled(True)
        tab1_layout.addWidget(self.table)

        # TAB 2: KPIs + Gráfico
        self.tab_kpis = QWidget()
        self.tabs.addTab(self.tab_kpis, "KPIs + Top Produtos")

        tab2_layout = QVBoxLayout(self.tab_kpis)

        self.lbl_kpis = QLabel("KPIs aparecerão aqui após carregar os dados.")
        self.lbl_kpis.setStyleSheet("font-size: 14px;")
        tab2_layout.addWidget(self.lbl_kpis)

        self.fig = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.fig)
        tab2_layout.addWidget(self.canvas)

        # TAB 3: Qualidade de Dados
        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade de Dados")

        tab3_layout = QVBoxLayout(self.tab_quality)
        self.lbl_quality = QLabel("Análises de qualidade aparecerão aqui.")
        self.lbl_quality.setStyleSheet("font-size: 14px;")
        tab3_layout.addWidget(self.lbl_quality)

        # Model inicial vazio
        self.model = PandasTableModel(pd.DataFrame())
        self.table.setModel(self.model)

        # Auto-load se existir pasta dados
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
            # Checar arquivos
            arquivos = ["clientes.csv", "produtos.csv", "vendas.csv", "itens_venda.csv"]
            faltando = [a for a in arquivos if not (self.data_dir / a).exists()]
            if faltando:
                raise FileNotFoundError(f"Arquivos faltando em {self.data_dir}: {faltando}")

            self.base = carregar_base(self.data_dir)
            self.base_filtrada = self.base.copy()

            # Atualiza tabela
            self.model.update(self.base_filtrada)
            self.lbl_qtd.setText(f"Linhas: {len(self.base_filtrada):,}".replace(",", "."))

            self.lbl_status.setText(f"Status: OK | Base: {self.base.shape[0]} linhas / {self.base.shape[1]} colunas")
            self.btn_exportar.setEnabled(True)

            # Atualiza KPIs e gráficos
            self.atualizar_kpis()
            self.atualizar_quality()

        except Exception as e:
            QMessageBox.critical(self, "Erro ao carregar", str(e))
            self.lbl_status.setText("Status: ERRO ao carregar dados")

    def on_filtrar(self):
        if self.base.empty:
            return

        termo = self.input_busca.text().strip().lower()

        if termo == "":
            self.base_filtrada = self.base.copy()
        else:
            # filtro simples procurando termo em qualquer coluna (cuidado: pode ser mais lento em bases gigantes)
            mask = self.base.astype(str).apply(
                lambda col: col.str.lower().str.contains(termo, na=False)
            ).any(axis=1)

            self.base_filtrada = self.base[mask].copy()

        self.model.update(self.base_filtrada)
        self.lbl_qtd.setText(f"Linhas: {len(self.base_filtrada):,}".replace(",", "."))

    def on_exportar_excel(self):
        if self.base.empty:
            return

        arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Excel",
            str(self.base_dir / "relatorio_base_consolidada.xlsx"),
            "Excel (*.xlsx)"
        )
        if not arquivo:
            return

        try:
            self.base.to_excel(arquivo, index=False)
            QMessageBox.information(self, "Exportado", f"Arquivo salvo com sucesso:\n{arquivo}")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao exportar", str(e))

    # =========================
    # KPI / Charts / Quality
    # =========================
    def atualizar_kpis(self):
        base = self.base.copy()

        # KPI
        base["faturamento"] = base["valor_total"]

        faturamento_total = base["faturamento"].sum()
        qtd_vendas = base["venda_id"].nunique()
        ticket_medio = base.groupby("venda_id")["faturamento"].sum().mean()

        texto = (
            f"📊 KPIs principais\n"
            f"- Faturamento total: R$ {faturamento_total:,.2f}\n"
            f"- Qtde de vendas: {qtd_vendas}\n"
            f"- Ticket médio: R$ {ticket_medio:,.2f}\n"
        )
        self.lbl_kpis.setText(texto)

        # Top 10 produtos (se existir coluna produto)
        if "produto" in base.columns:
            top_prod = (base.groupby("produto")["faturamento"]
                        .sum()
                        .sort_values(ascending=False)
                        .head(10))
        else:
            top_prod = pd.Series(dtype=float)

        # Plot
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_title("Top 10 Produtos por Faturamento")

        if len(top_prod) > 0:
            ax.bar(top_prod.index.astype(str), top_prod.values)
            ax.tick_params(axis="x", rotation=45)
        else:
            ax.text(0.5, 0.5, "Coluna 'produto' não encontrada.", ha="center", va="center")

        self.fig.tight_layout()
        self.canvas.draw()

    def atualizar_quality(self):
        base = self.base.copy()

        # Nulos
        nulos_top = base.isna().sum().sort_values(ascending=False).head(10)

        # EAN inválido
        if "ean" in base.columns:
            ean_len = base["ean"].astype(str).str.len()
            qtd_ean_invalidos = int((ean_len != 13).sum())
        else:
            qtd_ean_invalidos = 0

        # Duplicidade EAN
        if "ean" in base.columns:
            dup_ean = base[base.duplicated(subset=["ean"], keep=False)]
            qtd_ean_duplicados = dup_ean["ean"].nunique()
        else:
            qtd_ean_duplicados = 0

        texto = (
            "🧪 Qualidade de Dados\n"
            f"- Linhas: {base.shape[0]}\n"
            f"- Colunas: {base.shape[1]}\n"
            f"- EAN inválidos (len != 13): {qtd_ean_invalidos}\n"
            f"- EAN duplicados (distintos): {qtd_ean_duplicados}\n\n"
            "Top 10 colunas com nulos:\n"
            f"{nulos_top.to_string()}"
        )
        self.lbl_quality.setText(texto)


def main():
    app = QApplication(sys.argv)
    w = Dashboard()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()