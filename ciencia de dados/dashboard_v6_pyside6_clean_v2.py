# dashboard_v6_pyside6_clean.py
# Dashboard v6 (Power BI Style) - PySide6 + Matplotlib (QtAgg)
# Compatível com Python 3.14 (Windows)
#
# Estrutura esperada:
#   ./dashboard_v6_pyside6_clean.py
#   ./dados/
#       clientes.csv
#       produtos.csv
#       vendas.csv
#       itens_venda.csv
#
# Instalação:
#   python -m pip install -U pyside6 pandas numpy matplotlib openpyxl

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QDate
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QTabWidget, QTableView, QMessageBox, QFrame,
    QGroupBox, QDateEdit, QTextEdit, QSizePolicy
)

# IMPORTANTÍSSIMO: definir backend Qt antes de importar FigureCanvas
import matplotlib
matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter


# =========================================================
# Utilidades
# =========================================================
def brl(v: float) -> str:
    try:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def brl_axis(x, _pos):
    try:
        return f"R$ {x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0"


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def invalid_status_mask(df: pd.DataFrame) -> pd.Series:
    """Marca status que devem ser excluídos do faturamento líquido."""
    if "status" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    st = df["status"].astype(str).str.upper()
    return st.str.contains("CANCEL") | st.str.contains("DENEG") | st.str.contains("INUTIL")


def normalize_base(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza algumas colunas comuns para o dashboard funcionar."""
    base = df.copy()

    # Canal
    if "canal" not in base.columns and "canal_aquisicao" in base.columns:
        base.rename(columns={"canal_aquisicao": "canal"}, inplace=True)

    # Produto
    if "produto" not in base.columns:
        for cand in ["descricao", "descricao_produto", "nome_produto"]:
            if cand in base.columns:
                base.rename(columns={cand: "produto"}, inplace=True)
                break

    # Cliente
    if "cliente" not in base.columns:
        for cand in ["nome", "razao_social", "destinatario_nome"]:
            if cand in base.columns:
                base.rename(columns={cand: "cliente"}, inplace=True)
                break

    # Data
    if "data" not in base.columns:
        for cand in ["dh_emissao", "data_emissao", "data_venda", "data_cadastro"]:
            if cand in base.columns:
                base.rename(columns={cand: "data"}, inplace=True)
                break
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")

    # EAN
    if "ean" in base.columns:
        base["ean"] = base["ean"].astype(str).str.replace(".0", "", regex=False)

    # Numéricas
    for c in ["quantidade", "preco_unitario", "valor_total", "custo_total"]:
        if c in base.columns:
            base[c] = to_num(base[c])

    # Se não existir valor_total, tenta montar
    if "valor_total" not in base.columns:
        q = base["quantidade"] if "quantidade" in base.columns else 0
        pu = base["preco_unitario"] if "preco_unitario" in base.columns else 0
        base["valor_total"] = to_num(q) * to_num(pu)

    return base


def load_erp_base(data_dir: Path) -> pd.DataFrame:
    """Carrega os 4 CSVs e consolida em uma base só (itens + vendas + produtos + clientes)."""
    required = ["clientes.csv", "produtos.csv", "vendas.csv", "itens_venda.csv"]
    missing = [f for f in required if not (data_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Arquivos faltando em: {data_dir}\n{missing}")

    clientes = pd.read_csv(data_dir / "clientes.csv")
    produtos = pd.read_csv(data_dir / "produtos.csv")
    vendas = pd.read_csv(data_dir / "vendas.csv")
    itens = pd.read_csv(data_dir / "itens_venda.csv")

    # Tenta padronizar data antes
    for col in ["data", "dh_emissao", "data_emissao", "data_venda"]:
        if col in vendas.columns:
            vendas[col] = pd.to_datetime(vendas[col], errors="coerce")

    base = itens.merge(vendas, on="venda_id", how="left")
    base = base.merge(produtos, on="produto_id", how="left")
    base = base.merge(clientes, on="cliente_id", how="left")

    return normalize_base(base)


def serie_mensal(df: pd.DataFrame, liquido=True) -> pd.Series:
    if df.empty or "data" not in df.columns or "valor_total" not in df.columns:
        return pd.Series(dtype=float)
    tmp = df.dropna(subset=["data"]).copy()
    if liquido:
        tmp = tmp.loc[~invalid_status_mask(tmp)].copy()
    return tmp.groupby(tmp["data"].dt.to_period("M"))["valor_total"].sum().sort_index()


# =========================================================
# Table Model
# =========================================================
class PandasModel(QAbstractTableModel):
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
        r, c = index.row(), index.column()

        if role == Qt.DisplayRole:
            v = self.df.iloc[r, c]
            if pd.isna(v):
                return ""
            if isinstance(v, (float, np.floating)):
                return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return str(v)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self.df.columns[section])
        return str(section)

    def set_df(self, df: pd.DataFrame):
        self.beginResetModel()
        self.df = df.copy()
        self.endResetModel()


# =========================================================
# KPI Card
# =========================================================
class KpiCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("KpiCard")
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size:12px; font-weight:900; color:#6B7280;")
        layout.addWidget(self.lbl_title)

        self.lbl_value = QLabel("—")
        self.lbl_value.setStyleSheet("font-size:22px; font-weight:900; color:#111111;")
        layout.addWidget(self.lbl_value)

        self.lbl_sub = QLabel("")
        self.lbl_sub.setStyleSheet("font-size:11px; font-weight:700; color:#4B5563;")
        layout.addWidget(self.lbl_sub)

    def set_value(self, value: str, sub: str = ""):
        self.lbl_value.setText(value)
        self.lbl_sub.setText(sub)


# =========================================================
# Main Dashboard
# =========================================================
class DashboardV6(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard v6 - Power BI Style (PySide6) | Portfólio")
        self.resize(1600, 900)

        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "dados"

        self.base = pd.DataFrame()
        self.df = pd.DataFrame()

        self._build_ui()
        self._apply_styles()

        # Autoload se existir pasta dados
        if self.data_dir.exists():
            try:
                self.load_data()
            except Exception:
                pass

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(360)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(14, 14, 14, 14)
        sb.setSpacing(10)

        sb.addWidget(QLabel("<b>Painel de Filtros (Slicers)</b>"))

        self.lbl_status = QLabel("Status: aguardando dados...")
        self.lbl_status.setStyleSheet("font-weight:900; color:#1F4E79;")
        sb.addWidget(self.lbl_status)

        row_btn = QHBoxLayout()
        self.btn_load = QPushButton("Carregar")
        self.btn_load.clicked.connect(self.load_data)
        self.btn_folder = QPushButton("Pasta...")
        self.btn_folder.clicked.connect(self.choose_folder)
        row_btn.addWidget(self.btn_load)
        row_btn.addWidget(self.btn_folder)
        sb.addLayout(row_btn)

        row_btn2 = QHBoxLayout()
        self.btn_clear = QPushButton("Limpar")
        self.btn_clear.clicked.connect(self.clear_filters)
        self.btn_clear.setEnabled(False)
        self.btn_export = QPushButton("Export Excel")
        self.btn_export.clicked.connect(self.export_excel)
        self.btn_export.setEnabled(False)
        row_btn2.addWidget(self.btn_clear)
        row_btn2.addWidget(self.btn_export)
        sb.addLayout(row_btn2)

        self.input_text = QLineEdit()
        self.input_text.setPlaceholderText("Buscar (produto, EAN, cliente, CFOP...)")
        self.input_text.textChanged.connect(self.apply_filters)

        self.cb_uf = QComboBox()
        self.cb_uf.currentIndexChanged.connect(self.apply_filters)
        self.cb_canal = QComboBox()
        self.cb_canal.currentIndexChanged.connect(self.apply_filters)
        self.cb_cat = QComboBox()
        self.cb_cat.currentIndexChanged.connect(self.apply_filters)
        self.cb_status = QComboBox()
        self.cb_status.currentIndexChanged.connect(self.apply_filters)

        self.dt_ini = QDateEdit()
        self.dt_ini.setCalendarPopup(True)
        self.dt_ini.dateChanged.connect(self.apply_filters)
        self.dt_fim = QDateEdit()
        self.dt_fim.setCalendarPopup(True)
        self.dt_fim.dateChanged.connect(self.apply_filters)

        sb.addWidget(self._box("Texto", self.input_text))
        sb.addWidget(self._box("UF", self.cb_uf))
        sb.addWidget(self._box("Canal", self.cb_canal))
        sb.addWidget(self._box("Categoria", self.cb_cat))
        sb.addWidget(self._box("Status", self.cb_status))

        periodo = QGroupBox("Período")
        hp = QHBoxLayout(periodo)
        hp.setContentsMargins(10, 8, 10, 8)
        hp.addWidget(QLabel("De:"))
        hp.addWidget(self.dt_ini)
        hp.addWidget(QLabel("Até:"))
        hp.addWidget(self.dt_fim)
        sb.addWidget(periodo)

        self.lbl_rows = QLabel("Linhas: 0")
        self.lbl_rows.setStyleSheet("font-weight:900;")
        sb.addWidget(self.lbl_rows)

        sb.addStretch()

        # Content
        self.content = QFrame()
        self.content.setObjectName("Content")
        ct = QVBoxLayout(self.content)
        ct.setContentsMargins(14, 14, 14, 14)
        ct.setSpacing(10)

        header = QLabel("<b>Resumo Executivo (Power BI Style)</b> — Dinâmico com filtros")
        header.setStyleSheet("font-size:15px;")
        ct.addWidget(header)

        self.tabs = QTabWidget()
        ct.addWidget(self.tabs)

        # Tab Exec
        self.tab_exec = QWidget()
        self.tabs.addTab(self.tab_exec, "Resumo Executivo")
        self._build_exec_tab()

        # Tab Table
        self.tab_table = QWidget()
        self.tabs.addTab(self.tab_table, "Tabela")
        lt = QVBoxLayout(self.tab_table)
        self.table = QTableView()
        self.model = PandasModel(pd.DataFrame())
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        lt.addWidget(self.table)

        # Tab Quality
        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade")
        lq = QVBoxLayout(self.tab_quality)
        self.txt_quality = QTextEdit()
        self.txt_quality.setReadOnly(True)
        lq.addWidget(self.txt_quality)

        root.addWidget(self.sidebar)
        root.addWidget(self.content, 1)

    def _box(self, title: str, widget: QWidget):
        g = QGroupBox(title)
        g.setStyleSheet("QGroupBox{font-weight:900;}")
        l = QVBoxLayout(g)
        l.setContentsMargins(10, 8, 10, 8)
        l.addWidget(widget)
        return g

    def _build_exec_tab(self):
        layout = QVBoxLayout(self.tab_exec)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.k_fat_liq = KpiCard("Faturamento Líquido")
        self.k_fat_bruto = KpiCard("Faturamento Bruto")
        self.k_ticket = KpiCard("Ticket Médio")
        self.k_vendas = KpiCard("Qtd Vendas")
        self.k_itens = KpiCard("Qtd Itens")
        self.k_margem = KpiCard("Margem Bruta")

        grid.addWidget(self.k_fat_liq, 0, 0)
        grid.addWidget(self.k_fat_bruto, 0, 1)
        grid.addWidget(self.k_ticket, 0, 2)
        grid.addWidget(self.k_vendas, 1, 0)
        grid.addWidget(self.k_itens, 1, 1)
        grid.addWidget(self.k_margem, 1, 2)

        layout.addLayout(grid)

        charts = QGridLayout()
        charts.setHorizontalSpacing(12)
        charts.setVerticalSpacing(12)

        self.card_line, self.canvas_line, self.fig_line = self._chart("Faturamento Mensal (linha)")
        self.card_top, self.canvas_top, self.fig_top = self._chart("Top Produtos (barras)")
        self.card_canal, self.canvas_canal, self.fig_canal = self._chart("Faturamento por Canal (barras)")
        self.card_donut, self.canvas_donut, self.fig_donut = self._chart("Participação por Canal (donut)")

        charts.addWidget(self.card_line, 0, 0)
        charts.addWidget(self.card_top, 0, 1)
        charts.addWidget(self.card_canal, 1, 0)
        charts.addWidget(self.card_donut, 1, 1)

        layout.addLayout(charts)

        self.txt_exec = QTextEdit()
        self.txt_exec.setReadOnly(True)
        self.txt_exec.setMinimumHeight(160)
        layout.addWidget(self.txt_exec)

    def _chart(self, title: str):
        frame = QFrame()
        frame.setObjectName("ChartFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        lbl = QLabel(f"<b>{title}</b>")
        lbl.setStyleSheet("font-size:12px;")
        lay.addWidget(lbl)

        fig = Figure(figsize=(5, 3))
        canvas = FigureCanvas(fig)
        lay.addWidget(canvas)

        return frame, canvas, fig

    def _apply_styles(self):
        self.setStyleSheet("""
            QFrame#Sidebar {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
            }
            QFrame#Content {
                background:#F8FAFC;
                border:1px solid #E6E6E6;
                border-radius:14px;
            }
            QFrame#ChartFrame {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
            }
            QFrame#KpiCard {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
            }
            QPushButton {
                background:#1F4E79;
                color:white;
                border:none;
                padding:7px 10px;
                border-radius:10px;
                font-weight:900;
            }
            QPushButton:disabled {
                background:#B0B8C1;
            }
            QLineEdit, QComboBox, QDateEdit {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                padding:6px;
                border-radius:10px;
                font-weight:700;
            }
            QTabWidget::pane {
                border:1px solid #E6E6E6;
                border-radius:12px;
                background:#FFFFFF;
            }
            QTabBar::tab {
                background:#EEF2F7;
                padding:8px 12px;
                border-top-left-radius:10px;
                border-top-right-radius:10px;
                font-weight:900;
            }
            QTabBar::tab:selected {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-bottom:none;
            }
        """)

    # ---------------- Actions ----------------
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolha a pasta dos CSVs")
        if folder:
            self.data_dir = Path(folder)
            self.load_data()

    def load_data(self):
        try:
            self.base = load_erp_base(self.data_dir)
            self.df = self.base.copy()

            self._fill_filters()
            self._fill_dates()

            self.btn_clear.setEnabled(True)
            self.btn_export.setEnabled(True)

            self.lbl_status.setText(f"Status: OK | Base: {self.base.shape[0]} linhas / {self.base.shape[1]} colunas")
            self.apply_filters()

        except Exception as e:
            QMessageBox.critical(self, "Erro ao carregar", str(e))
            self.lbl_status.setText("Status: ERRO ao carregar")

    def _fill_filters(self):
        self.cb_uf.blockSignals(True)
        self.cb_canal.blockSignals(True)
        self.cb_cat.blockSignals(True)
        self.cb_status.blockSignals(True)

        self.cb_uf.clear(); self.cb_canal.clear(); self.cb_cat.clear(); self.cb_status.clear()

        self.cb_uf.addItem("Todas as UFs")
        self.cb_canal.addItem("Todos os Canais")
        self.cb_cat.addItem("Todas as Categorias")
        self.cb_status.addItem("Todos os Status")

        if "uf_destino" in self.base.columns:
            for v in sorted(self.base["uf_destino"].dropna().astype(str).unique()):
                self.cb_uf.addItem(v)

        if "canal" in self.base.columns:
            for v in sorted(self.base["canal"].dropna().astype(str).unique()):
                self.cb_canal.addItem(v)

        if "categoria" in self.base.columns:
            for v in sorted(self.base["categoria"].dropna().astype(str).unique()):
                self.cb_cat.addItem(v)

        if "status" in self.base.columns:
            for v in sorted(self.base["status"].dropna().astype(str).unique()):
                self.cb_status.addItem(v)

        self.cb_uf.blockSignals(False)
        self.cb_canal.blockSignals(False)
        self.cb_cat.blockSignals(False)
        self.cb_status.blockSignals(False)

    def _fill_dates(self):
        if "data" not in self.base.columns:
            hoje = QDate.currentDate()
            self.dt_ini.setDate(hoje.addMonths(-6))
            self.dt_fim.setDate(hoje)
            return

        d = self.base["data"].dropna()
        if d.empty:
            hoje = QDate.currentDate()
            self.dt_ini.setDate(hoje.addMonths(-6))
            self.dt_fim.setDate(hoje)
            return

        mi = d.min().date()
        ma = d.max().date()

        self.dt_ini.blockSignals(True)
        self.dt_fim.blockSignals(True)
        self.dt_ini.setDate(QDate(mi.year, mi.month, mi.day))
        self.dt_fim.setDate(QDate(ma.year, ma.month, ma.day))
        self.dt_ini.blockSignals(False)
        self.dt_fim.blockSignals(False)

    def clear_filters(self):
        self.input_text.setText("")
        self.cb_uf.setCurrentIndex(0)
        self.cb_canal.setCurrentIndex(0)
        self.cb_cat.setCurrentIndex(0)
        self.cb_status.setCurrentIndex(0)
        self._fill_dates()
        self.df = self.base.copy()
        self.refresh_all()

    def apply_filters(self):
        if self.base.empty:
            return
        df = self.base.copy()

        # período
        if "data" in df.columns:
            di = self.dt_ini.date().toPython()
            dfim = self.dt_fim.date().toPython()
            df = df.dropna(subset=["data"])
            df = df[(df["data"].dt.date >= di) & (df["data"].dt.date <= dfim)]

        # texto
        termo = self.input_text.text().strip().lower()
        if termo:
            cols = [c for c in df.columns if c in ["produto", "ean", "cliente", "cfop", "cst_icms", "uf_destino", "canal", "categoria"]]
            if not cols:
                cols = df.columns.tolist()
            mask = df[cols].astype(str).apply(lambda s: s.str.lower().str.contains(termo, na=False)).any(axis=1)
            df = df[mask]

        # UF
        uf = self.cb_uf.currentText()
        if uf != "Todas as UFs" and "uf_destino" in df.columns:
            df = df[df["uf_destino"].astype(str) == uf]

        # Canal
        canal = self.cb_canal.currentText()
        if canal != "Todos os Canais" and "canal" in df.columns:
            df = df[df["canal"].astype(str) == canal]

        # Categoria
        cat = self.cb_cat.currentText()
        if cat != "Todas as Categorias" and "categoria" in df.columns:
            df = df[df["categoria"].astype(str) == cat]

        # Status
        st = self.cb_status.currentText()
        if st != "Todos os Status" and "status" in df.columns:
            df = df[df["status"].astype(str) == st]

        self.df = df.copy()
        self.refresh_all()

    # ---------------- Metrics ----------------
    def fat_bruto(self, df):
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        return float(df["valor_total"].sum(skipna=True))

    def fat_liq(self, df):
        if df.empty or "valor_total" not in df.columns:
            return 0.0, 0.0
        bruto = float(df["valor_total"].sum(skipna=True))
        inv = invalid_status_mask(df)
        liq = float(df.loc[~inv, "valor_total"].sum(skipna=True))
        return liq, (bruto - liq)

    def qtd_vendas(self, df):
        if df.empty:
            return 0
        if "venda_id" in df.columns:
            return int(df["venda_id"].nunique())
        return int(len(df))

    def ticket_medio(self, df):
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        if "venda_id" in df.columns:
            s = df.groupby("venda_id")["valor_total"].sum()
            return float(s.mean()) if len(s) else 0.0
        return float(df["valor_total"].mean())

    def margem_bruta(self, df):
        if df.empty or "valor_total" not in df.columns or "custo_total" not in df.columns:
            return None
        fat = float(df["valor_total"].sum(skipna=True))
        custo = float(df["custo_total"].sum(skipna=True))
        if fat <= 0:
            return 0.0
        return (fat - custo) / fat

    # ---------------- Refresh UI ----------------
    def refresh_all(self):
        df = self.df.copy()

        self.lbl_rows.setText(f"Linhas: {len(df):,}".replace(",", "."))

        # tabela
        self.model.set_df(df)

        # KPIs
        fat_liq, impacto = self.fat_liq(df)
        fat_bruto = self.fat_bruto(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)
        margem = self.margem_bruta(df)

        self.k_fat_liq.set_value(brl(fat_liq), f"Impacto cancel/deneg: {brl(impacto)}")
        self.k_fat_bruto.set_value(brl(fat_bruto), "Total bruto no recorte")
        self.k_ticket.set_value(brl(ticket), "Média por venda")
        self.k_vendas.set_value(str(vendas), "Vendas distintas")
        self.k_itens.set_value(str(int(df.shape[0])), "Itens no recorte")
        self.k_margem.set_value("—" if margem is None else f"{margem*100:.2f}%".replace(".", ","), "Lucro bruto / faturamento")

        # charts + texto executivo
        self.update_charts(df)
        self.txt_quality.setPlainText(self.quality_report(df))
        self.txt_exec.setPlainText(self.exec_report(df))

    def update_charts(self, df):
        # linha mensal
        self.fig_line.clear()
        ax = self.fig_line.add_subplot(111)
        ax.set_title("Faturamento Líquido Mensal", fontsize=10, fontweight="bold")
        s = serie_mensal(df, liquido=True)
        if len(s):
            x = [str(p) for p in s.index]
            ax.plot(x, s.values, marker="o")
            ax.tick_params(axis="x", rotation=45, labelsize=8)
            ax.yaxis.set_major_formatter(FuncFormatter(brl_axis)) 
        else:
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_line.tight_layout()
        self.canvas_line.draw()

        # top produtos
        self.fig_top.clear()
        ax2 = self.fig_top.add_subplot(111)
        ax2.set_title("Top Produtos (Faturamento)", fontsize=10, fontweight="bold")
        if not df.empty and "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(top):
                top = top.sort_values()
                ax2.barh(top.index.astype(str), top.values)
                ax2.xaxis.set_major_formatter(FuncFormatter(brl_axis)) 
            else:
                ax2.text(0.5, 0.5, "Sem top", ha="center", va="center")
        else:
            ax2.text(0.5, 0.5, "Sem colunas", ha="center", va="center")
        self.fig_top.tight_layout()
        self.canvas_top.draw()

        # faturamento por canal
        self.fig_canal.clear()
        ax3 = self.fig_canal.add_subplot(111)
        ax3.set_title("Faturamento por Canal", fontsize=10, fontweight="bold")
        if not df.empty and "canal" in df.columns and "valor_total" in df.columns:
            c = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)
            if len(c):
                ax3.bar(c.index.astype(str), c.values)
                ax3.yaxis.set_major_formatter(FuncFormatter(brl_axis)) 
            else:
                ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        else:
            ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        self.fig_canal.tight_layout()
        self.canvas_canal.draw()

        # donut
        self.fig_donut.clear()
        ax4 = self.fig_donut.add_subplot(111)
        ax4.set_title("Participação por Canal", fontsize=10, fontweight="bold")
        if not df.empty and "canal" in df.columns and "valor_total" in df.columns:
            c = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False).head(6)
            tot = float(c.sum()) if len(c) else 0.0
            if tot > 0:
                values = c.values
                labels = c.index.astype(str).tolist()
                ax4.pie(values, labels=labels, autopct=lambda p: f"{p:.0f}%", pctdistance=0.78)
                # donut hole
                from matplotlib.patches import Circle
                ax4.add_artist(Circle((0, 0), 0.55, fc="white"))
                ax4.axis("equal")
            else:
                ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_donut.tight_layout()
        self.canvas_donut.draw()

    def exec_report(self, df):
        if df.empty:
            return "Sem dados no recorte atual."
        fat_liq, impacto = self.fat_liq(df)
        fat_bruto = self.fat_bruto(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)
        margem = self.margem_bruta(df)

        lines = []
        lines.append("Resumo interpretável do recorte atual:\n")
        lines.append(f"- Faturamento líquido: {brl(fat_liq)}")
        lines.append(f"- Faturamento bruto:  {brl(fat_bruto)}")
        lines.append(f"- Impacto cancel/deneg: {brl(impacto)}")
        lines.append(f"- Qtd vendas: {vendas}")
        lines.append(f"- Ticket médio: {brl(ticket)}")
        lines.append(f"- Margem bruta: {'—' if margem is None else (str(round(margem*100,2)).replace('.',',')+'%')}\n")

        if "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(3)
            if len(top):
                lines.append("Top 3 produtos por faturamento:")
                for p, v in top.items():
                    lines.append(f"• {p}: {brl(float(v))}")

        return "\n".join(lines)

    def quality_report(self, df):
        lines = []
        lines.append("Qualidade de Dados (recorte atual)\n")
        lines.append(f"- Linhas: {df.shape[0]}")
        lines.append(f"- Colunas: {df.shape[1]}")

        nulos = df.isna().sum().sort_values(ascending=False).head(10)
        lines.append("\nTop colunas com nulos:")
        for col, qtd in nulos.items():
            if int(qtd) > 0:
                lines.append(f"• {col}: {int(qtd)}")

        if "ean" in df.columns:
            inv = int(df["ean"].astype(str).str.len().ne(13).sum())
            dup = int(df[df.duplicated(subset=["ean"], keep=False)]["ean"].nunique())
            lines.append(f"\nEAN inválidos (len != 13): {inv}")
            lines.append(f"EAN duplicados (distintos): {dup}")

        if "status" in df.columns:
            invs = int(invalid_status_mask(df).sum())
            lines.append(f"\nStatus inválidos (cancel/deneg/inutil): {invs}")

        return "\n".join(lines)

    # ---------------- Export ----------------
    def export_excel(self):
        if self.df.empty:
            QMessageBox.warning(self, "Export", "Não há dados para exportar.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Excel", str(self.base_dir / "relatorio_dashboard_v6.xlsx"), "Excel (*.xlsx)"
        )
        if not file_path:
            return

        try:
            df = self.df.copy()
            fat_liq, impacto = self.fat_liq(df)
            resumo = pd.DataFrame([{
                "faturamento_liquido": fat_liq,
                "impacto_cancel_deneg": impacto,
                "ticket_medio": self.ticket_medio(df),
                "qtd_vendas": self.qtd_vendas(df),
                "qtd_itens": int(df.shape[0]),
                "data_export": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }])

            mensal = serie_mensal(df, liquido=True).reset_index()
            if not mensal.empty:
                mensal.columns = ["mes", "faturamento_liquido"]

            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                resumo.to_excel(writer, sheet_name="Resumo_Executivo", index=False)
                df.to_excel(writer, sheet_name="Base_Filtrada", index=False)
                (mensal if not mensal.empty else pd.DataFrame({"info": ["Sem série mensal"]})).to_excel(writer, sheet_name="Faturamento_Mensal", index=False)

            QMessageBox.information(self, "Excel", f"✅ Excel exportado com sucesso:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))


# =========================================================
# MAIN
# =========================================================
def main():
    app = QApplication(sys.argv)
    w = DashboardV6()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
