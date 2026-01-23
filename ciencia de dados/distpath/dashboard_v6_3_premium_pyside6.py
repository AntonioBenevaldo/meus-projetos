# dashboard_v6_3_premium_pyside6.py
# Dashboard v6.3 Premium (Power BI Style) - PySide6 + Matplotlib (QtAgg)
#
# Estrutura:
#   ./dashboard_v6_3_premium_pyside6.py
#   ./dados/{clientes.csv, produtos.csv, vendas.csv, itens_venda.csv}
#
# Instalar:
#   python -m pip install -U pyside6 pandas numpy matplotlib openpyxl

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QDate
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QTabWidget, QTableView, QMessageBox, QFrame,
    QGroupBox, QDateEdit, QTextEdit, QSizePolicy, QSplitter
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter


# -----------------------------
# Helpers
# -----------------------------
def brl(v: float) -> str:
    try:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def pct(v: float) -> str:
    try:
        return f"{v*100:.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"


def fmt_axis_brl(x, _pos):
    try:
        return f"R$ {x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0"


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def invalid_status_mask(df: pd.DataFrame) -> pd.Series:
    if "status" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    st = df["status"].astype(str).str.upper()
    return st.str.contains("CANCEL") | st.str.contains("DENEG") | st.str.contains("INUTIL")


def normalize_base(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()

    if "canal" not in base.columns and "canal_aquisicao" in base.columns:
        base.rename(columns={"canal_aquisicao": "canal"}, inplace=True)

    if "produto" not in base.columns:
        for cand in ["descricao", "descricao_produto", "nome_produto"]:
            if cand in base.columns:
                base.rename(columns={cand: "produto"}, inplace=True)
                break

    if "cliente" not in base.columns:
        for cand in ["nome", "razao_social", "destinatario_nome"]:
            if cand in base.columns:
                base.rename(columns={cand: "cliente"}, inplace=True)
                break

    if "data" not in base.columns:
        for cand in ["dh_emissao", "data_emissao", "data_venda", "data_cadastro"]:
            if cand in base.columns:
                base.rename(columns={cand: "data"}, inplace=True)
                break

    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")

    if "ean" in base.columns:
        base["ean"] = base["ean"].astype(str).str.replace(".0", "", regex=False)

    for c in ["quantidade", "preco_unitario", "valor_total", "custo_total",
              "valor_icms", "valor_pis", "valor_cofins",
              "aliq_icms", "aliq_pis", "aliq_cofins"]:
        if c in base.columns:
            base[c] = to_num(base[c])

    if "valor_total" not in base.columns:
        q = base["quantidade"] if "quantidade" in base.columns else 0
        pu = base["preco_unitario"] if "preco_unitario" in base.columns else 0
        base["valor_total"] = to_num(q) * to_num(pu)

    return base


def load_erp_base(data_dir: Path) -> pd.DataFrame:
    required = ["clientes.csv", "produtos.csv", "vendas.csv", "itens_venda.csv"]
    missing = [f for f in required if not (data_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Arquivos faltando em: {data_dir}\n{missing}")

    clientes = pd.read_csv(data_dir / "clientes.csv")
    produtos = pd.read_csv(data_dir / "produtos.csv")
    vendas = pd.read_csv(data_dir / "vendas.csv")
    itens = pd.read_csv(data_dir / "itens_venda.csv")

    for col in ["data", "dh_emissao", "data_emissao", "data_venda"]:
        if col in vendas.columns:
            vendas[col] = pd.to_datetime(vendas[col], errors="coerce")

    base = itens.merge(vendas, on="venda_id", how="left")
    base = base.merge(produtos, on="produto_id", how="left")
    base = base.merge(clientes, on="cliente_id", how="left")
    return normalize_base(base)


def group_period(df: pd.DataFrame, level: str) -> pd.Series:
    if df.empty or "data" not in df.columns:
        return pd.Series(dtype="object")
    d = df["data"]
    if level == "Diário":
        return d.dt.date
    return d.dt.to_period("M").astype(str)


def safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(df[col].sum(skipna=True))


# -----------------------------
# Pandas -> Qt Model
# -----------------------------
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
        if role == Qt.DisplayRole:
            v = self.df.iloc[index.row(), index.column()]
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


# -----------------------------
# KPI Card Premium
# -----------------------------
class KpiCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("KpiCard")
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("KpiTitle")
        lay.addWidget(self.lbl_title)

        self.lbl_value = QLabel("—")
        self.lbl_value.setObjectName("KpiValue")
        lay.addWidget(self.lbl_value)

        self.lbl_delta = QLabel("")
        self.lbl_delta.setObjectName("KpiDelta")
        lay.addWidget(self.lbl_delta)

        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("KpiSub")
        lay.addWidget(self.lbl_sub)

    def set_value(self, value: str, sub: str = "", delta_text: str = "", delta_kind: str = "neutral"):
        self.lbl_value.setText(value)
        self.lbl_sub.setText(sub)
        self.lbl_delta.setText(delta_text)

        if delta_kind == "up":
            self.lbl_delta.setStyleSheet("color:#16A34A; font-weight:900;")
        elif delta_kind == "down":
            self.lbl_delta.setStyleSheet("color:#DC2626; font-weight:900;")
        else:
            self.lbl_delta.setStyleSheet("color:#6B7280; font-weight:900;")


# -----------------------------
# Dashboard
# -----------------------------
class DashboardV63(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard v6.3 Premium - Power BI Style (PySide6) | Portfólio Premium")
        self.resize(1700, 950)

        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "dados"

        self.base = pd.DataFrame()
        self.df = pd.DataFrame()
        self.dark = False

        self._build_ui()
        self.apply_theme()

        if self.data_dir.exists():
            try:
                self.load_data()
            except Exception:
                pass

    # UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(380)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(14, 14, 14, 14)
        sb.setSpacing(10)

        sb.addWidget(QLabel("<b>Painel de Filtros (Slicers)</b>"))
        self.lbl_status = QLabel("Status: aguardando dados…")
        self.lbl_status.setObjectName("StatusLabel")
        sb.addWidget(self.lbl_status)

        row1 = QHBoxLayout()
        self.btn_load = QPushButton("Carregar")
        self.btn_load.clicked.connect(self.load_data)
        self.btn_folder = QPushButton("Pasta…")
        self.btn_folder.clicked.connect(self.choose_folder)
        row1.addWidget(self.btn_load)
        row1.addWidget(self.btn_folder)
        sb.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_clear = QPushButton("Limpar")
        self.btn_clear.clicked.connect(self.clear_filters)
        self.btn_clear.setEnabled(False)
        self.btn_export = QPushButton("Export Excel")
        self.btn_export.clicked.connect(self.export_excel)
        self.btn_export.setEnabled(False)
        row2.addWidget(self.btn_clear)
        row2.addWidget(self.btn_export)
        sb.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_theme = QPushButton("Tema: Claro")
        self.btn_theme.clicked.connect(self.toggle_theme)
        row3.addWidget(self.btn_theme)
        sb.addLayout(row3)

        self.cb_drill = QComboBox()
        self.cb_drill.addItems(["Mensal", "Diário"])
        self.cb_drill.currentIndexChanged.connect(self.refresh_all)
        sb.addWidget(self._box("Drill-down (Gráfico Linha)", self.cb_drill))

        # filtros
        self.input_text = QLineEdit()
        self.input_text.setPlaceholderText("Buscar (produto, EAN, cliente, CFOP, CST...)")
        self.input_text.textChanged.connect(self.apply_filters)

        self.cb_uf = QComboBox(); self.cb_uf.currentIndexChanged.connect(self.apply_filters)
        self.cb_canal = QComboBox(); self.cb_canal.currentIndexChanged.connect(self.apply_filters)
        self.cb_cat = QComboBox(); self.cb_cat.currentIndexChanged.connect(self.apply_filters)
        self.cb_status = QComboBox(); self.cb_status.currentIndexChanged.connect(self.apply_filters)

        sb.addWidget(self._box("Texto", self.input_text))
        sb.addWidget(self._box("UF", self.cb_uf))
        sb.addWidget(self._box("Canal", self.cb_canal))
        sb.addWidget(self._box("Categoria", self.cb_cat))
        sb.addWidget(self._box("Status", self.cb_status))

        periodo = QGroupBox("Período")
        hp = QHBoxLayout(periodo)
        hp.setContentsMargins(10, 8, 10, 8)
        hp.addWidget(QLabel("De:"))
        self.dt_ini = QDateEdit(); self.dt_ini.setCalendarPopup(True); self.dt_ini.dateChanged.connect(self.apply_filters)
        hp.addWidget(self.dt_ini)
        hp.addWidget(QLabel("Até:"))
        self.dt_fim = QDateEdit(); self.dt_fim.setCalendarPopup(True); self.dt_fim.dateChanged.connect(self.apply_filters)
        hp.addWidget(self.dt_fim)
        sb.addWidget(periodo)

        self.lbl_rows = QLabel("Linhas: 0")
        self.lbl_rows.setObjectName("RowsLabel")
        sb.addWidget(self.lbl_rows)
        sb.addStretch()

        # Content
        self.content = QFrame()
        self.content.setObjectName("Content")
        ct = QVBoxLayout(self.content)
        ct.setContentsMargins(14, 14, 14, 14)
        ct.setSpacing(10)

        header = QLabel("<b>Resumo Executivo (Power BI Style)</b> — Premium com KPIs + Drill-down + Fiscal BI")
        header.setObjectName("HeaderLabel")
        ct.addWidget(header)

        self.tabs = QTabWidget()
        ct.addWidget(self.tabs)

        self.tab_exec = QWidget()
        self.tabs.addTab(self.tab_exec, "Resumo Executivo")
        self._build_exec_tab()

        self.tab_table = QWidget()
        self.tabs.addTab(self.tab_table, "Tabela")
        lt = QVBoxLayout(self.tab_table)
        self.table = QTableView()
        self.model = PandasModel(pd.DataFrame())
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        lt.addWidget(self.table)

        self.tab_fiscal = QWidget()
        self.tabs.addTab(self.tab_fiscal, "Fiscal BI")
        self._build_fiscal_tab()

        self.tab_alert = QWidget()
        self.tabs.addTab(self.tab_alert, "Alertas")
        la = QVBoxLayout(self.tab_alert)
        self.txt_alertas = QTextEdit(); self.txt_alertas.setReadOnly(True)
        la.addWidget(self.txt_alertas)

        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade")
        lq = QVBoxLayout(self.tab_quality)
        self.txt_quality = QTextEdit(); self.txt_quality.setReadOnly(True)
        lq.addWidget(self.txt_quality)

        root.addWidget(self.sidebar)
        root.addWidget(self.content, 1)

        act_reload = QAction("Recarregar", self)
        act_reload.triggered.connect(self.load_data)
        self.menuBar().addAction(act_reload)

    def _box(self, title: str, widget: QWidget):
        g = QGroupBox(title)
        l = QVBoxLayout(g)
        l.setContentsMargins(10, 8, 10, 8)
        l.addWidget(widget)
        return g

    def _chart(self, title: str):
        frame = QFrame()
        frame.setObjectName("ChartFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        fig = Figure(figsize=(5, 3))
        canvas = FigureCanvas(fig)
        lay.addWidget(canvas)
        return frame, canvas, fig

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
        self.k_icms = KpiCard("ICMS (Total)")
        self.k_pis = KpiCard("PIS (Total)")
        self.k_cofins = KpiCard("COFINS (Total)")

        cards = [
            self.k_fat_liq, self.k_fat_bruto, self.k_ticket,
            self.k_vendas, self.k_itens, self.k_margem,
            self.k_icms, self.k_pis, self.k_cofins,
        ]
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 3, i % 3)

        layout.addLayout(grid)

        charts = QGridLayout()
        charts.setHorizontalSpacing(12)
        charts.setVerticalSpacing(12)

        self.card_line, self.canvas_line, self.fig_line = self._chart("Faturamento (linha) — com Drill-down")
        self.card_top, self.canvas_top, self.fig_top = self._chart("Top Produtos (Power Bar)")
        self.card_canal, self.canvas_canal, self.fig_canal = self._chart("Faturamento por Canal")
        self.card_donut, self.canvas_donut, self.fig_donut = self._chart("Participação por Canal (donut)")

        charts.addWidget(self.card_line, 0, 0)
        charts.addWidget(self.card_top, 0, 1)
        charts.addWidget(self.card_canal, 1, 0)
        charts.addWidget(self.card_donut, 1, 1)

        layout.addLayout(charts)

        self.txt_exec = QTextEdit()
        self.txt_exec.setReadOnly(True)
        self.txt_exec.setMinimumHeight(170)
        layout.addWidget(self.txt_exec)

    def _build_fiscal_tab(self):
        layout = QHBoxLayout(self.tab_fiscal)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        l = QVBoxLayout(left); l.setSpacing(12)
        self.card_cfop, self.canvas_cfop, self.fig_cfop = self._chart("Top CFOP (Faturamento)")
        self.card_uf_icms, self.canvas_uf_icms, self.fig_uf_icms = self._chart("ICMS por UF (barras)")
        l.addWidget(self.card_cfop)
        l.addWidget(self.card_uf_icms)

        right = QWidget()
        r = QVBoxLayout(right); r.setSpacing(10)
        r.addWidget(QLabel("<b>Tabela Fiscal (agrupada)</b>"))
        self.fiscal_table = QTableView()
        self.fiscal_model = PandasModel(pd.DataFrame())
        self.fiscal_table.setModel(self.fiscal_model)
        self.fiscal_table.setSortingEnabled(True)
        r.addWidget(self.fiscal_table)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    # Theme
    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()
        self.refresh_all()

    def apply_theme(self):
        if self.dark:
            self.btn_theme.setText("Tema: Escuro")
            self.setStyleSheet(DARK_QSS)
        else:
            self.btn_theme.setText("Tema: Claro")
            self.setStyleSheet(LIGHT_QSS)

    # Data
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

    def _fill_filters(self):
        def fill(cb: QComboBox, title: str, col: str):
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(title)
            if col in self.base.columns:
                vals = sorted(self.base[col].dropna().astype(str).unique())
                cb.addItems(vals)
            cb.blockSignals(False)

        fill(self.cb_uf, "Todas as UFs", "uf_destino")
        fill(self.cb_canal, "Todos os Canais", "canal")
        fill(self.cb_cat, "Todas as Categorias", "categoria")
        fill(self.cb_status, "Todos os Status", "status")

    def _fill_dates(self):
        hoje = QDate.currentDate()
        if "data" not in self.base.columns or self.base["data"].dropna().empty:
            self.dt_ini.setDate(hoje.addMonths(-6))
            self.dt_fim.setDate(hoje)
            return
        d = self.base["data"].dropna()
        mi = d.min().date()
        ma = d.max().date()
        self.dt_ini.blockSignals(True); self.dt_fim.blockSignals(True)
        self.dt_ini.setDate(QDate(mi.year, mi.month, mi.day))
        self.dt_fim.setDate(QDate(ma.year, ma.month, ma.day))
        self.dt_ini.blockSignals(False); self.dt_fim.blockSignals(False)

    # Filters
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

        if "data" in df.columns:
            di = self.dt_ini.date().toPython()
            dfim = self.dt_fim.date().toPython()
            df = df.dropna(subset=["data"])
            df = df[(df["data"].dt.date >= di) & (df["data"].dt.date <= dfim)]

        termo = self.input_text.text().strip().lower()
        if termo:
            cols = [c for c in ["produto", "ean", "cliente", "cfop", "cst_icms", "uf_destino", "canal", "categoria"] if c in df.columns]
            if not cols:
                cols = df.columns.tolist()
            mask = df[cols].astype(str).apply(lambda s: s.str.lower().str.contains(termo, na=False)).any(axis=1)
            df = df[mask]

        uf = self.cb_uf.currentText()
        if uf != "Todas as UFs" and "uf_destino" in df.columns:
            df = df[df["uf_destino"].astype(str) == uf]

        canal = self.cb_canal.currentText()
        if canal != "Todos os Canais" and "canal" in df.columns:
            df = df[df["canal"].astype(str) == canal]

        cat = self.cb_cat.currentText()
        if cat != "Todas as Categorias" and "categoria" in df.columns:
            df = df[df["categoria"].astype(str) == cat]

        st = self.cb_status.currentText()
        if st != "Todos os Status" and "status" in df.columns:
            df = df[df["status"].astype(str) == st]

        self.df = df.copy()
        self.refresh_all()

    # Metrics
    def fat_liq(self, df) -> tuple[float, float]:
        if df.empty or "valor_total" not in df.columns:
            return 0.0, 0.0
        bruto = float(df["valor_total"].sum(skipna=True))
        inv = invalid_status_mask(df)
        liq = float(df.loc[~inv, "valor_total"].sum(skipna=True))
        return liq, (bruto - liq)

    def fat_bruto(self, df) -> float:
        return safe_sum(df, "valor_total")

    def qtd_vendas(self, df) -> int:
        if df.empty:
            return 0
        return int(df["venda_id"].nunique()) if "venda_id" in df.columns else int(len(df))

    def ticket_medio(self, df) -> float:
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

    def delta_mom(self, df, measure: str):
        if df.empty or "data" not in df.columns:
            return None
        tmp = df.dropna(subset=["data"]).copy()
        key = tmp["data"].dt.to_period("M")

        if measure == "fat_liq":
            tmp2 = tmp.loc[~invalid_status_mask(tmp)]
            s = tmp2.groupby(key)["valor_total"].sum().sort_index()
        elif measure == "ticket":
            if "venda_id" in tmp.columns:
                fat = tmp.groupby(key)["valor_total"].sum()
                vendas = tmp.groupby(key)["venda_id"].nunique().replace(0, np.nan)
                s = (fat / vendas).sort_index()
            else:
                s = tmp.groupby(key)["valor_total"].mean().sort_index()
        else:
            col = {"icms": "valor_icms", "pis": "valor_pis", "cofins": "valor_cofins"}.get(measure)
            if not col or col not in tmp.columns:
                return None
            s = tmp.groupby(key)[col].sum().sort_index()

        if len(s) < 2 or pd.isna(s.iloc[-2]) or float(s.iloc[-2]) == 0:
            return None
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        return (last - prev) / prev

    # Refresh
    def refresh_all(self):
        df = self.df.copy()
        self.lbl_rows.setText(f"Linhas: {len(df):,}".replace(",", "."))

        self.model.set_df(df)

        fat_liq, impacto = self.fat_liq(df)
        fat_bruto = self.fat_bruto(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)
        margem = self.margem_bruta(df)

        icms = safe_sum(df, "valor_icms")
        pis = safe_sum(df, "valor_pis")
        cofins = safe_sum(df, "valor_cofins")

        d_fat = self.delta_mom(df, "fat_liq")
        d_ticket = self.delta_mom(df, "ticket")
        d_icms = self.delta_mom(df, "icms")
        d_pis = self.delta_mom(df, "pis")
        d_cofins = self.delta_mom(df, "cofins")

        self.k_fat_liq.set_value(brl(fat_liq), f"Impacto cancel/deneg: {brl(impacto)}", self._delta_txt(d_fat), self._delta_kind(d_fat))
        self.k_fat_bruto.set_value(brl(fat_bruto), "Total bruto no recorte", "", "neutral")
        self.k_ticket.set_value(brl(ticket), "Média por venda", self._delta_txt(d_ticket), self._delta_kind(d_ticket))
        self.k_vendas.set_value(str(vendas), "Vendas distintas", "", "neutral")
        self.k_itens.set_value(str(int(df.shape[0])), "Itens no recorte", "", "neutral")
        self.k_margem.set_value("—" if margem is None else pct(margem), "Lucro bruto / faturamento", "", "neutral")
        self.k_icms.set_value(brl(icms), "Soma no recorte", self._delta_txt(d_icms), self._delta_kind(d_icms))
        self.k_pis.set_value(brl(pis), "Soma no recorte", self._delta_txt(d_pis), self._delta_kind(d_pis))
        self.k_cofins.set_value(brl(cofins), "Soma no recorte", self._delta_txt(d_cofins), self._delta_kind(d_cofins))

        self.update_charts(df)
        self.update_fiscal(df)
        self.txt_quality.setPlainText(self.quality_report(df))
        self.txt_alertas.setPlainText(self.alerts_report(df))
        self.txt_exec.setPlainText(self.exec_report(df))

    def _delta_txt(self, d):
        if d is None or pd.isna(d):
            return ""
        return f"{'↑' if d >= 0 else '↓'} {pct(abs(d))} vs M-1"

    def _delta_kind(self, d):
        if d is None or pd.isna(d):
            return "neutral"
        return "up" if d >= 0 else "down"

    # Charts
    def _fig_style(self, fig: Figure):
        fig.patch.set_facecolor("#0B1220" if self.dark else "#FFFFFF")

    def update_charts(self, df):
        # Linha
        self.fig_line.clear()
        self._fig_style(self.fig_line)
        ax = self.fig_line.add_subplot(111)
        ax.set_title("Faturamento Líquido", fontsize=10, fontweight="bold")
        ax.yaxis.set_major_formatter(FuncFormatter(fmt_axis_brl))

        level = self.cb_drill.currentText()
        if not df.empty and "data" in df.columns:
            tmp = df.dropna(subset=["data"]).copy()
            tmp = tmp.loc[~invalid_status_mask(tmp)]
            key = group_period(tmp, level)
            s = tmp.groupby(key)["valor_total"].sum().sort_index()
            if len(s):
                x = [str(i) for i in s.index]
                y = s.values
                if level == "Diário" and len(x) > 60:
                    x = x[-60:]; y = y[-60:]
                ax.plot(x, y, marker="o")
                ax.tick_params(axis="x", rotation=45, labelsize=8)
                ax.grid(True, linestyle="--", alpha=0.25)
            else:
                ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_line.tight_layout()
        self.canvas_line.draw()

        # Top produtos Power Bar
        self.fig_top.clear()
        self._fig_style(self.fig_top)
        ax2 = self.fig_top.add_subplot(111)
        ax2.set_title("Top Produtos (Faturamento)", fontsize=10, fontweight="bold")
        ax2.xaxis.set_major_formatter(FuncFormatter(fmt_axis_brl))

        if not df.empty and "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(top):
                top = top.sort_values()
                labels = top.index.astype(str).tolist()
                vals = top.values
                vmax = float(np.max(vals)) if len(vals) else 1.0
                ax2.barh(labels, [vmax] * len(vals), alpha=0.15)
                ax2.barh(labels, vals)
                ax2.grid(True, axis="x", linestyle="--", alpha=0.25)
            else:
                ax2.text(0.5, 0.5, "Sem top", ha="center", va="center")
        else:
            ax2.text(0.5, 0.5, "Sem colunas", ha="center", va="center")
        self.fig_top.tight_layout()
        self.canvas_top.draw()

        # Canal
        self.fig_canal.clear()
        self._fig_style(self.fig_canal)
        ax3 = self.fig_canal.add_subplot(111)
        ax3.set_title("Faturamento por Canal", fontsize=10, fontweight="bold")
        ax3.yaxis.set_major_formatter(FuncFormatter(fmt_axis_brl))

        if not df.empty and "canal" in df.columns and "valor_total" in df.columns:
            c = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)
            if len(c):
                ax3.bar(c.index.astype(str), c.values)
                ax3.grid(True, axis="y", linestyle="--", alpha=0.25)
            else:
                ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        else:
            ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        self.fig_canal.tight_layout()
        self.canvas_canal.draw()

        # Donut
        self.fig_donut.clear()
        self._fig_style(self.fig_donut)
        ax4 = self.fig_donut.add_subplot(111)
        ax4.set_title("Participação por Canal", fontsize=10, fontweight="bold")

        if not df.empty and "canal" in df.columns and "valor_total" in df.columns:
            c = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False).head(6)
            tot = float(c.sum()) if len(c) else 0.0
            if tot > 0:
                ax4.pie(c.values, labels=c.index.astype(str).tolist(),
                        autopct=lambda p: f"{p:.0f}%", pctdistance=0.78)
                from matplotlib.patches import Circle
                ax4.add_artist(Circle((0, 0), 0.55, fc=("#0B1220" if self.dark else "#FFFFFF")))
                ax4.axis("equal")
            else:
                ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_donut.tight_layout()
        self.canvas_donut.draw()

    # Fiscal
    def update_fiscal(self, df):
        # Tabela fiscal
        if df.empty or "valor_total" not in df.columns:
            self.fiscal_model.set_df(pd.DataFrame())
        else:
            group_cols = [c for c in ["cfop", "cst_icms"] if c in df.columns]
            if not group_cols:
                self.fiscal_model.set_df(pd.DataFrame({"info": ["Base sem colunas fiscais (cfop/cst_icms)."]}))
            else:
                agg = df.groupby(group_cols).agg(
                    faturamento=("valor_total", "sum"),
                    itens=("valor_total", "size"),
                    icms=("valor_icms", "sum") if "valor_icms" in df.columns else ("valor_total", "sum"),
                    pis=("valor_pis", "sum") if "valor_pis" in df.columns else ("valor_total", "sum"),
                    cofins=("valor_cofins", "sum") if "valor_cofins" in df.columns else ("valor_total", "sum"),
                ).reset_index()
                self.fiscal_model.set_df(agg.sort_values("faturamento", ascending=False).head(200))

        # Top CFOP
        self.fig_cfop.clear()
        self._fig_style(self.fig_cfop)
        ax = self.fig_cfop.add_subplot(111)
        ax.set_title("Top CFOP (Faturamento)", fontsize=10, fontweight="bold")
        ax.xaxis.set_major_formatter(FuncFormatter(fmt_axis_brl))

        if not df.empty and "cfop" in df.columns and "valor_total" in df.columns:
            t = df.groupby("cfop")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(t):
                t = t.sort_values()
                ax.barh(t.index.astype(str), t.values)
                ax.grid(True, axis="x", linestyle="--", alpha=0.25)
            else:
                ax.text(0.5, 0.5, "Sem CFOP", ha="center", va="center")
        else:
            ax.text(0.5, 0.5, "Sem CFOP", ha="center", va="center")
        self.fig_cfop.tight_layout()
        self.canvas_cfop.draw()

        # ICMS por UF
        self.fig_uf_icms.clear()
        self._fig_style(self.fig_uf_icms)
        ax2 = self.fig_uf_icms.add_subplot(111)
        ax2.set_title("ICMS por UF", fontsize=10, fontweight="bold")
        ax2.yaxis.set_major_formatter(FuncFormatter(fmt_axis_brl))

        if not df.empty and "uf_destino" in df.columns and "valor_icms" in df.columns:
            u = df.groupby("uf_destino")["valor_icms"].sum().sort_values(ascending=False).head(12)
            if len(u):
                ax2.bar(u.index.astype(str), u.values)
                ax2.grid(True, axis="y", linestyle="--", alpha=0.25)
            else:
                ax2.text(0.5, 0.5, "Sem ICMS", ha="center", va="center")
        else:
            ax2.text(0.5, 0.5, "Sem ICMS", ha="center", va="center")
        self.fig_uf_icms.tight_layout()
        self.canvas_uf_icms.draw()

    # Reports
    def exec_report(self, df):
        if df.empty:
            return "Sem dados no recorte atual."

        fat_liq, impacto = self.fat_liq(df)
        fat_bruto = self.fat_bruto(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)
        margem = self.margem_bruta(df)

        impostos = safe_sum(df, "valor_icms") + safe_sum(df, "valor_pis") + safe_sum(df, "valor_cofins")
        carga = (impostos / fat_bruto) if fat_bruto > 0 else 0.0

        lines = [
            "Resumo interpretável do recorte atual:\n",
            f"- Faturamento líquido: {brl(fat_liq)}",
            f"- Faturamento bruto:  {brl(fat_bruto)}",
            f"- Impacto cancel/deneg: {brl(impacto)}",
            f"- Qtd vendas: {vendas}",
            f"- Ticket médio: {brl(ticket)}",
            f"- Margem bruta: {'—' if margem is None else pct(margem)}",
        ]
        if impostos > 0:
            lines.append(f"- Impostos (ICMS+PIS+COFINS): {brl(impostos)} | Carga: {pct(carga)}")

        if "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(3)
            if len(top):
                lines.append("\nTop 3 produtos por faturamento:")
                for p, v in top.items():
                    lines.append(f"• {p}: {brl(float(v))}")

        return "\n".join(lines)

    def quality_report(self, df):
        lines = [
            "Qualidade de Dados (recorte atual)\n",
            f"- Linhas: {df.shape[0]}",
            f"- Colunas: {df.shape[1]}",
        ]
        if df.empty:
            return "\n".join(lines)

        nulos = df.isna().sum().sort_values(ascending=False).head(12)
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

    def alerts_report(self, df):
        lines = ["Alertas (Auditoria / Risco) — recorte atual\n"]
        if df.empty:
            lines.append("- Sem dados.")
            return "\n".join(lines)

        if "status" in df.columns:
            invs = int(invalid_status_mask(df).sum())
            if invs > 0:
                lines.append(f"⚠️ {invs} itens com status cancel/deneg/inutil (impactam faturamento líquido).")

        if "ean" in df.columns:
            dup = int(df[df.duplicated(subset=["ean"], keep=False)]["ean"].nunique())
            if dup > 0:
                lines.append(f"⚠️ {dup} EANs duplicados (distintos) — revisar cadastro.")

        if "cfop" in df.columns:
            miss_cfop = int(df["cfop"].isna().sum())
            if miss_cfop > 0:
                lines.append(f"⚠️ {miss_cfop} registros sem CFOP (risco fiscal).")

        if "cst_icms" in df.columns:
            miss_cst = int(df["cst_icms"].isna().sum())
            if miss_cst > 0:
                lines.append(f"⚠️ {miss_cst} registros sem CST ICMS (atenção compliance).")

        if "aliq_icms" in df.columns and "valor_total" in df.columns:
            zero = int((df["aliq_icms"].fillna(0) == 0).sum())
            if zero > 0:
                lines.append(f"ℹ️ {zero} itens com alíquota ICMS = 0 (pode ser isento / revisar).")

        fat = safe_sum(df, "valor_total")
        imp = safe_sum(df, "valor_icms") + safe_sum(df, "valor_pis") + safe_sum(df, "valor_cofins")
        if fat > 0 and imp > 0:
            carga = imp / fat
            if carga >= 0.18:
                lines.append(f"⚠️ Carga tributária alta no recorte: {pct(carga)}")

        if len(lines) == 1:
            lines.append("- Sem alertas relevantes no recorte.")
        return "\n".join(lines)

    # Export
    def export_excel(self):
        if self.df.empty:
            QMessageBox.warning(self, "Export", "Não há dados para exportar.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Excel", str(self.base_dir / "relatorio_dashboard_v6_3.xlsx"), "Excel (*.xlsx)"
        )
        if not file_path:
            return

        try:
            df = self.df.copy()
            fat_liq, impacto = self.fat_liq(df)
            fat_bruto = self.fat_bruto(df)
            impostos = safe_sum(df, "valor_icms") + safe_sum(df, "valor_pis") + safe_sum(df, "valor_cofins")

            resumo = pd.DataFrame([{
                "faturamento_liquido": fat_liq,
                "faturamento_bruto": fat_bruto,
                "impacto_cancel_deneg": impacto,
                "ticket_medio": self.ticket_medio(df),
                "qtd_vendas": self.qtd_vendas(df),
                "qtd_itens": int(df.shape[0]),
                "icms_total": safe_sum(df, "valor_icms"),
                "pis_total": safe_sum(df, "valor_pis"),
                "cofins_total": safe_sum(df, "valor_cofins"),
                "impostos_total": impostos,
                "data_export": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }])

            mensal = pd.DataFrame()
            if not df.empty and "data" in df.columns:
                tmp = df.dropna(subset=["data"]).copy()
                tmp = tmp.loc[~invalid_status_mask(tmp)]
                mensal = tmp.groupby(tmp["data"].dt.to_period("M"))["valor_total"].sum().reset_index()
                if not mensal.empty:
                    mensal.columns = ["mes", "faturamento_liquido"]

            fiscal = pd.DataFrame()
            group_cols = [c for c in ["cfop", "cst_icms"] if c in df.columns]
            if group_cols and "valor_total" in df.columns:
                fiscal = df.groupby(group_cols).agg(
                    faturamento=("valor_total", "sum"),
                    itens=("valor_total", "size"),
                    icms=("valor_icms", "sum") if "valor_icms" in df.columns else ("valor_total", "sum"),
                    pis=("valor_pis", "sum") if "valor_pis" in df.columns else ("valor_total", "sum"),
                    cofins=("valor_cofins", "sum") if "valor_cofins" in df.columns else ("valor_total", "sum"),
                ).reset_index().sort_values("faturamento", ascending=False)

            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                resumo.to_excel(writer, sheet_name="Resumo_Executivo", index=False)
                df.to_excel(writer, sheet_name="Base_Filtrada", index=False)
                (mensal if not mensal.empty else pd.DataFrame({"info": ["Sem série mensal"]})).to_excel(writer, sheet_name="Faturamento_Mensal", index=False)
                (fiscal if not fiscal.empty else pd.DataFrame({"info": ["Sem colunas fiscais"]})).to_excel(writer, sheet_name="Fiscal_Agregado", index=False)

            QMessageBox.information(self, "Excel", f"✅ Excel exportado com sucesso:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))


# QSS
LIGHT_QSS = """
QMainWindow { background:#F3F4F6; }
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
QLabel#StatusLabel { font-weight:900; color:#1F4E79; }
QLabel#RowsLabel { font-weight:900; }
QLabel#HeaderLabel { font-size:15px; }
QLabel#KpiTitle { font-size:12px; font-weight:900; color:#6B7280; }
QLabel#KpiValue { font-size:20px; font-weight:900; color:#111111; }
QLabel#KpiDelta { font-size:12px; font-weight:900; color:#6B7280; }
QLabel#KpiSub { font-size:11px; font-weight:700; color:#4B5563; }

QPushButton {
    background:#1F4E79;
    color:white;
    border:none;
    padding:7px 10px;
    border-radius:10px;
    font-weight:900;
}
QPushButton:disabled { background:#B0B8C1; }

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
"""

DARK_QSS = """
QMainWindow { background:#0B1220; }
QFrame#Sidebar {
    background:#111827;
    border:1px solid #1F2937;
    border-radius:14px;
}
QFrame#Content {
    background:#0F172A;
    border:1px solid #1F2937;
    border-radius:14px;
}
QFrame#ChartFrame {
    background:#111827;
    border:1px solid #1F2937;
    border-radius:14px;
}
QFrame#KpiCard {
    background:#111827;
    border:1px solid #1F2937;
    border-radius:14px;
}
QLabel { color:#E5E7EB; }
QLabel#StatusLabel { font-weight:900; color:#60A5FA; }
QLabel#RowsLabel { font-weight:900; color:#E5E7EB; }
QLabel#HeaderLabel { font-size:15px; color:#E5E7EB; }
QLabel#KpiTitle { font-size:12px; font-weight:900; color:#9CA3AF; }
QLabel#KpiValue { font-size:20px; font-weight:900; color:#F9FAFB; }
QLabel#KpiDelta { font-size:12px; font-weight:900; color:#9CA3AF; }
QLabel#KpiSub { font-size:11px; font-weight:700; color:#9CA3AF; }

QPushButton {
    background:#2563EB;
    color:white;
    border:none;
    padding:7px 10px;
    border-radius:10px;
    font-weight:900;
}
QPushButton:disabled { background:#334155; }

QLineEdit, QComboBox, QDateEdit {
    background:#0B1220;
    color:#E5E7EB;
    border:1px solid #1F2937;
    padding:6px;
    border-radius:10px;
    font-weight:700;
}

QTabWidget::pane {
    border:1px solid #1F2937;
    border-radius:12px;
    background:#111827;
}
QTabBar::tab {
    background:#0B1220;
    padding:8px 12px;
    border-top-left-radius:10px;
    border-top-right-radius:10px;
    font-weight:900;
    color:#E5E7EB;
}
QTabBar::tab:selected {
    background:#111827;
    border:1px solid #1F2937;
    border-bottom:none;
}
"""

def main():
    app = QApplication(sys.argv)
    w = DashboardV63()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
