from pathlib import Path

code = r'''# dashboard_v6_pyside6.py
# Dashboard v6 (Power BI Style) - PySide6 + Matplotlib (QtAgg)
# Autor: Benevaldo (portfólio) | Assistente: ChatGPT
#
# Estrutura esperada:
#   ./dashboard_v6_pyside6.py
#   ./dados/
#       clientes.csv
#       produtos.csv
#       vendas.csv
#       itens_venda.csv
#
# Requisitos:
#   pip install -U pyside6 pandas numpy matplotlib openpyxl

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTabWidget, QTableView, QMessageBox,
    QComboBox, QGroupBox, QDateEdit, QFrame, QGridLayout,
    QSizePolicy, QTextEdit
)

# Matplotlib (QtAgg / PySide6)
import matplotlib
matplotlib.use("QtAgg")  # força backend Qt compatível com PySide6

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter


# =========================================================
# Helpers
# =========================================================
def brl(x: float) -> str:
    try:
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def brl_axis(x, _pos):
    try:
        return f"R$ {x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0"


def safe_float(x) -> float:
    try:
        if pd.isna(x):
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def safe_int(x) -> int:
    try:
        if pd.isna(x):
            return 0
        return int(x)
    except Exception:
        return 0


def invalid_status_mask(df: pd.DataFrame) -> pd.Series:
    """Marca status que não devem entrar em faturamento líquido."""
    if "status" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    st = df["status"].astype(str).str.upper()
    return st.str.contains("CANCEL") | st.str.contains("DENEG") | st.str.contains("INUTIL")


def compute_outlier_mask(series: pd.Series) -> pd.Series:
    """Outliers via IQR (preço unitário)."""
    if series is None or series.empty:
        return pd.Series([False] * 0)
    s = pd.to_numeric(series, errors="coerce")
    s_valid = s.dropna()
    if s_valid.empty:
        return pd.Series([False] * len(series), index=series.index)
    q1 = s_valid.quantile(0.25)
    q3 = s_valid.quantile(0.75)
    iqr = q3 - q1
    lim_sup = q3 + 1.5 * iqr
    return s > lim_sup


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza nomes de colunas para o dashboard funcionar."""
    base = df.copy()

    # Data
    if "data" not in base.columns:
        for cand in ["dh_emissao", "data_emissao", "data_venda", "data_cadastro"]:
            if cand in base.columns:
                base.rename(columns={cand: "data"}, inplace=True)
                break
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")

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

    # EAN
    if "ean" in base.columns:
        base["ean"] = base["ean"].astype(str).str.replace(".0", "", regex=False)

    # Valores (garantia)
    for c in ["valor_total", "preco_unitario", "custo_total", "quantidade"]:
        if c in base.columns:
            base[c] = pd.to_numeric(base[c], errors="coerce")

    # Se não existir valor_total, tenta construir
    if "valor_total" not in base.columns:
        q = base["quantidade"] if "quantidade" in base.columns else 0
        pu = base["preco_unitario"] if "preco_unitario" in base.columns else 0
        base["valor_total"] = pd.to_numeric(q, errors="coerce") * pd.to_numeric(pu, errors="coerce")

    return base


def checar_arquivos_erp(data_dir: Path) -> list[str]:
    arquivos = ["clientes.csv", "produtos.csv", "vendas.csv", "itens_venda.csv"]
    return [a for a in arquivos if not (data_dir / a).exists()]


def carregar_base_erp(data_dir: Path) -> pd.DataFrame:
    """Carrega e consolida base (itens + vendas + produtos + clientes)."""
    clientes = pd.read_csv(data_dir / "clientes.csv")
    produtos = pd.read_csv(data_dir / "produtos.csv")

    # vendas: tenta parsear data em qualquer coluna plausível
    vendas = pd.read_csv(data_dir / "vendas.csv")
    if "data" in vendas.columns:
        vendas["data"] = pd.to_datetime(vendas["data"], errors="coerce")
    elif "dh_emissao" in vendas.columns:
        vendas["dh_emissao"] = pd.to_datetime(vendas["dh_emissao"], errors="coerce")

    itens = pd.read_csv(data_dir / "itens_venda.csv")

    # merges com chaves padrão
    base = itens.merge(vendas, on="venda_id", how="left")
    base = base.merge(produtos, on="produto_id", how="left")
    base = base.merge(clientes, on="cliente_id", how="left")

    return normalize_cols(base)


# =========================================================
# Model para QTableView
# =========================================================
class PandasTableModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df.copy()
        self.flag_outlier = pd.Series(dtype=bool)
        self.flag_ean_invalid = pd.Series(dtype=bool)
        self.flag_cancel = pd.Series(dtype=bool)

    def rowCount(self, parent=None):
        return len(self.df)

    def columnCount(self, parent=None):
        return len(self.df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        r = index.row()
        c = index.column()

        if role == Qt.DisplayRole:
            value = self.df.iloc[r, c]
            if pd.isna(value):
                return ""
            if isinstance(value, (float, np.floating)):
                return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return str(value)

        if role == Qt.BackgroundRole:
            try:
                if len(self.flag_cancel) and bool(self.flag_cancel.iloc[r]):
                    return QColor(255, 220, 220)  # vermelho claro
                if len(self.flag_outlier) and bool(self.flag_outlier.iloc[r]):
                    return QColor(255, 245, 204)  # amarelo claro
                if len(self.flag_ean_invalid) and bool(self.flag_ean_invalid.iloc[r]):
                    return QColor(220, 235, 255)  # azul claro
            except Exception:
                return None

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self.df.columns[section])
        return str(section)

    def update(self, df: pd.DataFrame, flag_outlier=None, flag_ean_invalid=None, flag_cancel=None):
        self.beginResetModel()
        self.df = df.copy()

        n = len(df)
        self.flag_outlier = flag_outlier if flag_outlier is not None else pd.Series([False] * n, index=df.index)
        self.flag_ean_invalid = flag_ean_invalid if flag_ean_invalid is not None else pd.Series([False] * n, index=df.index)
        self.flag_cancel = flag_cancel if flag_cancel is not None else pd.Series([False] * n, index=df.index)

        self.flag_outlier = self.flag_outlier.reindex(df.index, fill_value=False)
        self.flag_ean_invalid = self.flag_ean_invalid.reindex(df.index, fill_value=False)
        self.flag_cancel = self.flag_cancel.reindex(df.index, fill_value=False)
        self.endResetModel()


# =========================================================
# KPI Card (Power BI style)
# =========================================================
class KpiCard(QFrame):
    def __init__(self, titulo: str):
        super().__init__()
        self.setObjectName("KpiCard")
        self.setMinimumHeight(108)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #9CA3AF; font-size: 14px; font-weight: 900;")
        self.title = QLabel(titulo)
        self.title.setStyleSheet("font-size: 12px; color: #5A5A5A; font-weight: 900;")
        top.addWidget(self.dot)
        top.addWidget(self.title)
        top.addStretch()
        layout.addLayout(top)

        self.value = QLabel("-")
        self.value.setStyleSheet("font-size: 22px; font-weight: 900; color: #111111;")
        layout.addWidget(self.value)

        self.sub = QLabel("—")
        self.sub.setStyleSheet("font-size: 11px; color: #6B7280; font-weight: 700;")
        layout.addWidget(self.sub)

        self.meta = QLabel("")
        self.meta.setStyleSheet("font-size: 11px; color: #374151; font-weight: 700;")
        layout.addWidget(self.meta)

        self.setStyleSheet("""
            QFrame#KpiCard {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
            }
        """)

    def set_state(self, value_text: str, sub_text: str, meta_text: str = "", status: str = "neutral"):
        self.value.setText(value_text)
        self.sub.setText(sub_text)
        self.meta.setText(meta_text)

        if status == "green":
            color = "#1B9E77"
        elif status == "yellow":
            color = "#F59E0B"
        elif status == "red":
            color = "#D62728"
        else:
            color = "#9CA3AF"
        self.dot.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 900;")


# =========================================================
# Dashboard v6 - PySide6
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

        # Metas (você pode ajustar depois)
        self.meta_fat_liq = 300000.0
        self.meta_ticket = 450.0
        self.meta_vendas = 1000

        self._build_ui()
        self._apply_theme()

        # Autoload se existir "dados/"
        if self.data_dir.exists():
            self.on_carregar()

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # ===== Sidebar =====
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(360)
        self.sidebar.setObjectName("Sidebar")
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(14, 14, 14, 14)
        sb.setSpacing(10)

        title = QLabel("Painel de Filtros (Slicers)")
        title.setStyleSheet("font-size: 14px; font-weight: 900; color:#111111;")
        sb.addWidget(title)

        self.lbl_status = QLabel("Status: aguardando...")
        self.lbl_status.setStyleSheet("font-weight:900; color:#1F4E79;")
        sb.addWidget(self.lbl_status)

        row_btn1 = QHBoxLayout()
        self.btn_carregar = QPushButton("Carregar")
        self.btn_carregar.clicked.connect(self.on_carregar)
        self.btn_pasta = QPushButton("Pasta...")
        self.btn_pasta.clicked.connect(self.on_escolher_pasta)
        row_btn1.addWidget(self.btn_carregar)
        row_btn1.addWidget(self.btn_pasta)
        sb.addLayout(row_btn1)

        row_btn2 = QHBoxLayout()
        self.btn_limpar = QPushButton("Limpar")
        self.btn_limpar.clicked.connect(self.on_limpar)
        self.btn_limpar.setEnabled(False)
        self.btn_excel = QPushButton("Export Excel")
        self.btn_excel.clicked.connect(self.on_export_excel)
        self.btn_excel.setEnabled(False)
        row_btn2.addWidget(self.btn_limpar)
        row_btn2.addWidget(self.btn_excel)
        sb.addLayout(row_btn2)

        # filtros
        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Buscar texto (produto, EAN, cliente...)")
        self.input_busca.textChanged.connect(self.aplicar_filtros)

        self.combo_uf = QComboBox()
        self.combo_uf.currentIndexChanged.connect(self.aplicar_filtros)

        self.combo_canal = QComboBox()
        self.combo_canal.currentIndexChanged.connect(self.aplicar_filtros)

        self.combo_categoria = QComboBox()
        self.combo_categoria.currentIndexChanged.connect(self.aplicar_filtros)

        self.combo_status = QComboBox()
        self.combo_status.currentIndexChanged.connect(self.aplicar_filtros)

        self.date_ini = QDateEdit()
        self.date_ini.setCalendarPopup(True)
        self.date_ini.dateChanged.connect(self.aplicar_filtros)

        self.date_fim = QDateEdit()
        self.date_fim.setCalendarPopup(True)
        self.date_fim.dateChanged.connect(self.aplicar_filtros)

        def box(t, w):
            g = QGroupBox(t)
            g.setStyleSheet("QGroupBox{font-weight:900;}")
            l = QVBoxLayout(g)
            l.setContentsMargins(10, 8, 10, 8)
            l.addWidget(w)
            return g

        sb.addWidget(box("Texto", self.input_busca))
        sb.addWidget(box("UF", self.combo_uf))
        sb.addWidget(box("Canal", self.combo_canal))
        sb.addWidget(box("Categoria", self.combo_categoria))
        sb.addWidget(box("Status", self.combo_status))

        periodo = QGroupBox("Período")
        periodo.setStyleSheet("QGroupBox{font-weight:900;}")
        hp = QHBoxLayout(periodo)
        hp.setContentsMargins(10, 8, 10, 8)
        hp.addWidget(QLabel("De:"))
        hp.addWidget(self.date_ini)
        hp.addWidget(QLabel("Até:"))
        hp.addWidget(self.date_fim)
        sb.addWidget(periodo)

        self.lbl_linhas = QLabel("Linhas: 0")
        self.lbl_linhas.setStyleSheet("font-weight:900; color:#111111;")
        sb.addWidget(self.lbl_linhas)

        sb.addStretch()

        # ===== Content =====
        self.content = QFrame()
        self.content.setObjectName("Content")
        ct = QVBoxLayout(self.content)
        ct.setContentsMargins(14, 14, 14, 14)
        ct.setSpacing(10)

        header = QLabel("Resumo Executivo (Power BI Style) — Dinâmico com Filtros")
        header.setStyleSheet("font-size: 15px; font-weight: 900; color:#111111;")
        ct.addWidget(header)

        self.tabs = QTabWidget()
        ct.addWidget(self.tabs)

        # Tab: Resumo
        self.tab_exec = QWidget()
        self.tabs.addTab(self.tab_exec, "Resumo Executivo")
        self._build_tab_exec()

        # Tab: Tabela
        self.tab_table = QWidget()
        self.tabs.addTab(self.tab_table, "Tabela")
        ltb = QVBoxLayout(self.tab_table)
        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.model = PandasTableModel(pd.DataFrame())
        self.table.setModel(self.model)
        ltb.addWidget(self.table)

        # Tab: Alertas
        self.tab_alert = QWidget()
        self.tabs.addTab(self.tab_alert, "Alertas")
        la = QVBoxLayout(self.tab_alert)
        self.lbl_alert = QLabel("Carregue os dados para ver alertas.")
        self.lbl_alert.setTextInteractionFlags(Qt.TextSelectableByMouse)
        la.addWidget(self.lbl_alert)
        self.table_alert = QTableView()
        self.table_alert.setSortingEnabled(True)
        self.model_alert = PandasTableModel(pd.DataFrame())
        self.table_alert.setModel(self.model_alert)
        la.addWidget(self.table_alert)

        # Tab: Qualidade
        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade de Dados")
        lq = QVBoxLayout(self.tab_quality)
        self.txt_quality = QTextEdit()
        self.txt_quality.setReadOnly(True)
        lq.addWidget(self.txt_quality)

        root.addWidget(self.sidebar)
        root.addWidget(self.content, 1)

    def _build_tab_exec(self):
        layout = QVBoxLayout(self.tab_exec)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.kpi_fat_liq = KpiCard("Faturamento Líquido")
        self.kpi_fat_bruto = KpiCard("Faturamento Bruto")
        self.kpi_ticket = KpiCard("Ticket Médio")
        self.kpi_vendas = KpiCard("Qtd Vendas")
        self.kpi_itens = KpiCard("Qtd Itens")
        self.kpi_margem = KpiCard("Margem Bruta")

        grid.addWidget(self.kpi_fat_liq, 0, 0)
        grid.addWidget(self.kpi_fat_bruto, 0, 1)
        grid.addWidget(self.kpi_ticket, 0, 2)
        grid.addWidget(self.kpi_vendas, 1, 0)
        grid.addWidget(self.kpi_itens, 1, 1)
        grid.addWidget(self.kpi_margem, 1, 2)

        layout.addLayout(grid)

        vis = QGridLayout()
        vis.setHorizontalSpacing(12)
        vis.setVerticalSpacing(12)

        self.frame_mes, self.canvas_mes, self.fig_mes = self._make_chart("Faturamento Mensal (linha)")
        self.frame_top, self.canvas_top, self.fig_top = self._make_chart("Top Produtos (barras)")
        self.frame_canal, self.canvas_canal, self.fig_canal = self._make_chart("Faturamento por Canal (barras)")
        self.frame_donut, self.canvas_donut, self.fig_donut = self._make_chart("Participação por Canal (donut)")

        vis.addWidget(self.frame_mes, 0, 0)
        vis.addWidget(self.frame_top, 0, 1)
        vis.addWidget(self.frame_canal, 1, 0)
        vis.addWidget(self.frame_donut, 1, 1)

        layout.addLayout(vis)

        self.txt_insights = QTextEdit()
        self.txt_insights.setReadOnly(True)
        self.txt_insights.setMinimumHeight(170)
        self.txt_insights.setObjectName("Insights")
        layout.addWidget(self.txt_insights)

    def _make_chart(self, title: str):
        frame = QFrame()
        frame.setObjectName("ChartFrame")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 12px; font-weight: 900; color:#111111;")
        outer.addWidget(lbl)

        fig = Figure(figsize=(5, 3))
        canvas = FigureCanvas(fig)
        outer.addWidget(canvas)

        return frame, canvas, fig

    def _apply_theme(self):
        self.setStyleSheet("""
            QFrame#Sidebar {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
            }
            QFrame#Content {
                background: #F8FAFC;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
            }
            QFrame#ChartFrame {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
            }
            QPushButton {
                background: #1F4E79;
                color: white;
                border: none;
                padding: 7px 10px;
                border-radius: 10px;
                font-weight: 900;
            }
            QPushButton:disabled {
                background: #B0B8C1;
                color: #ffffff;
            }
            QLineEdit, QComboBox, QDateEdit {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                padding: 6px;
                border-radius: 10px;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: 1px solid #E6E6E6;
                border-radius: 12px;
                background: #FFFFFF;
            }
            QTabBar::tab {
                background: #EEF2F7;
                padding: 8px 12px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-weight: 900;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-bottom: none;
            }
            QTextEdit#Insights {
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
                padding:10px;
                font-size:12px;
            }
        """)

    # ---------------- Load / Filters ----------------
    def on_escolher_pasta(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecione a pasta dos CSVs")
        if folder:
            self.data_dir = Path(folder)
            self.on_carregar()

    def on_carregar(self):
        try:
            faltando = checar_arquivos_erp(self.data_dir)
            if faltando:
                raise FileNotFoundError(f"Arquivos faltando em {self.data_dir}:\n{faltando}")

            self.base = carregar_base_erp(self.data_dir)
            self.df = self.base.copy()

            self.preencher_combos()
            self.preencher_periodo()

            self.btn_limpar.setEnabled(True)
            self.btn_excel.setEnabled(True)

            self.lbl_status.setText(f"Status: OK | Base: {self.base.shape[0]} linhas / {self.base.shape[1]} colunas")
            self.aplicar_filtros()

        except Exception as e:
            QMessageBox.critical(self, "Erro ao carregar", str(e))
            self.lbl_status.setText("Status: ERRO ao carregar")

    def preencher_combos(self):
        self.combo_uf.blockSignals(True)
        self.combo_canal.blockSignals(True)
        self.combo_categoria.blockSignals(True)
        self.combo_status.blockSignals(True)

        self.combo_uf.clear()
        self.combo_canal.clear()
        self.combo_categoria.clear()
        self.combo_status.clear()

        self.combo_uf.addItem("Todas as UFs")
        self.combo_canal.addItem("Todos os Canais")
        self.combo_categoria.addItem("Todas as Categorias")
        self.combo_status.addItem("Todos os Status")

        if "uf_destino" in self.base.columns:
            for u in sorted(self.base["uf_destino"].dropna().unique().tolist()):
                self.combo_uf.addItem(str(u))

        if "canal" in self.base.columns:
            for c in sorted(self.base["canal"].dropna().unique().tolist()):
                self.combo_canal.addItem(str(c))

        if "categoria" in self.base.columns:
            for cat in sorted(self.base["categoria"].dropna().unique().tolist()):
                self.combo_categoria.addItem(str(cat))

        if "status" in self.base.columns:
            for st in sorted(self.base["status"].dropna().unique().tolist()):
                self.combo_status.addItem(str(st))

        self.combo_uf.blockSignals(False)
        self.combo_canal.blockSignals(False)
        self.combo_categoria.blockSignals(False)
        self.combo_status.blockSignals(False)

    def preencher_periodo(self):
        if "data" not in self.base.columns:
            hoje = QDate.currentDate()
            self.date_ini.setDate(hoje.addMonths(-6))
            self.date_fim.setDate(hoje)
            return

        d = self.base["data"].dropna()
        if d.empty:
            hoje = QDate.currentDate()
            self.date_ini.setDate(hoje.addMonths(-6))
            self.date_fim.setDate(hoje)
            return

        min_dt = d.min().date()
        max_dt = d.max().date()

        self.date_ini.blockSignals(True)
        self.date_fim.blockSignals(True)
        self.date_ini.setDate(QDate(min_dt.year, min_dt.month, min_dt.day))
        self.date_fim.setDate(QDate(max_dt.year, max_dt.month, max_dt.day))
        self.date_ini.blockSignals(False)
        self.date_fim.blockSignals(False)

    def on_limpar(self):
        self.input_busca.setText("")
        self.combo_uf.setCurrentIndex(0)
        self.combo_canal.setCurrentIndex(0)
        self.combo_categoria.setCurrentIndex(0)
        self.combo_status.setCurrentIndex(0)
        self.preencher_periodo()
        self.df = self.base.copy()
        self.update_all()

    def aplicar_filtros(self):
        if self.base.empty:
            return

        df = self.base.copy()

        # período
        if "data" in df.columns:
            di = self.date_ini.date().toPython()
            dfim = self.date_fim.date().toPython()
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df = df.dropna(subset=["data"])
            df = df[(df["data"].dt.date >= di) & (df["data"].dt.date <= dfim)]

        # texto
        termo = self.input_busca.text().strip().lower()
        if termo:
            cols = [c for c in df.columns if c.lower() in [
                "produto", "ean", "uf_destino", "canal", "categoria",
                "cfop", "cst_icms", "cliente", "marca"
            ]]
            if not cols:
                cols = df.columns.tolist()

            mask = df[cols].astype(str).apply(
                lambda col: col.str.lower().str.contains(termo, na=False)
            ).any(axis=1)
            df = df[mask]

        # UF
        uf_sel = self.combo_uf.currentText()
        if uf_sel != "Todas as UFs" and "uf_destino" in df.columns:
            df = df[df["uf_destino"].astype(str) == uf_sel]

        # Canal
        canal_sel = self.combo_canal.currentText()
        if canal_sel != "Todos os Canais" and "canal" in df.columns:
            df = df[df["canal"].astype(str) == canal_sel]

        # Categoria
        cat_sel = self.combo_categoria.currentText()
        if cat_sel != "Todas as Categorias" and "categoria" in df.columns:
            df = df[df["categoria"].astype(str) == cat_sel]

        # Status
        st_sel = self.combo_status.currentText()
        if st_sel != "Todos os Status" and "status" in df.columns:
            df = df[df["status"].astype(str) == st_sel]

        self.df = df.copy()
        self.update_all()

    # ---------------- KPIs / Charts / Quality ----------------
    def fat_bruto(self, df: pd.DataFrame) -> float:
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        return safe_float(df["valor_total"].sum())

    def fat_liq(self, df: pd.DataFrame) -> tuple[float, float]:
        if df.empty or "valor_total" not in df.columns:
            return 0.0, 0.0
        bruto = safe_float(df["valor_total"].sum())
        inv = invalid_status_mask(df)
        liq = safe_float(df.loc[~inv, "valor_total"].sum())
        return liq, (bruto - liq)

    def qtd_vendas(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        if "venda_id" in df.columns:
            return safe_int(df["venda_id"].nunique())
        return safe_int(len(df))

    def ticket(self, df: pd.DataFrame) -> float:
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        if "venda_id" in df.columns:
            s = df.groupby("venda_id")["valor_total"].sum()
            return safe_float(s.mean())
        return safe_float(df["valor_total"].mean())

    def margem_pct(self, df: pd.DataFrame):
        if df.empty or "valor_total" not in df.columns or "custo_total" not in df.columns:
            return None
        fat = safe_float(df["valor_total"].sum())
        custo = safe_float(df["custo_total"].sum())
        if fat == 0:
            return 0.0
        return (fat - custo) / fat

    def serie_mensal(self, df: pd.DataFrame, liquida=True) -> pd.Series:
        if df.empty or "data" not in df.columns or "valor_total" not in df.columns:
            return pd.Series(dtype=float)
        tmp = df.dropna(subset=["data"]).copy()
        if liquida:
            tmp = tmp.loc[~invalid_status_mask(tmp)].copy()
        return tmp.groupby(tmp["data"].dt.to_period("M"))["valor_total"].sum().sort_index()

    def semaforo(self, atual: float, meta: float):
        if meta <= 0:
            return "neutral", 0.0
        ating = atual / meta
        if ating >= 1.0:
            return "green", ating
        if ating >= 0.9:
            return "yellow", ating
        return "red", ating

    def gerar_flags(self, df: pd.DataFrame):
        n = len(df)
        if n == 0:
            return pd.Series(dtype=bool), pd.Series(dtype=bool), pd.Series(dtype=bool)

        out = pd.Series([False] * n, index=df.index)
        if "preco_unitario" in df.columns:
            out = compute_outlier_mask(df["preco_unitario"]).fillna(False)

        ean_inv = pd.Series([False] * n, index=df.index)
        if "ean" in df.columns:
            ean_inv = df["ean"].astype(str).str.len().ne(13)

        canc = invalid_status_mask(df)
        return out, ean_inv, canc

    def update_all(self):
        df = self.df.copy()
        self.lbl_linhas.setText(f"Linhas: {len(df):,}".replace(",", "."))

        # tabela com flags
        out, ean_inv, canc = self.gerar_flags(df)
        self.model.update(df, flag_outlier=out, flag_ean_invalid=ean_inv, flag_cancel=canc)

        # KPIs
        fat_liq, impacto = self.fat_liq(df)
        fat_bruto = self.fat_bruto(df)
        qtd_v = self.qtd_vendas(df)
        qtd_it = int(df.shape[0])
        ticket = self.ticket(df)
        margem = self.margem_pct(df)

        st_f, at_f = self.semaforo(fat_liq, self.meta_fat_liq)
        self.kpi_fat_liq.set_state(brl(fat_liq), f"Impacto cancel/deneg: {brl(impacto)}", f"Meta: {brl(self.meta_fat_liq)} | Ating: {at_f*100:.1f}%", st_f)

        self.kpi_fat_bruto.set_state(brl(fat_bruto), "Valor total bruto no recorte", "", "neutral")

        st_t, at_t = self.semaforo(ticket, self.meta_ticket)
        self.kpi_ticket.set_state(brl(ticket), "Média por venda", f"Meta: {brl(self.meta_ticket)} | Ating: {at_t*100:.1f}%", st_t)

        st_v, at_v = self.semaforo(qtd_v, self.meta_vendas)
        self.kpi_vendas.set_state(str(qtd_v), "Vendas distintas", f"Meta: {self.meta_vendas} | Ating: {at_v*100:.1f}%", st_v)

        self.kpi_itens.set_state(str(qtd_it), "Itens no recorte", "", "neutral")

        if margem is None:
            self.kpi_margem.set_state("—", "custo_total não encontrado", "", "neutral")
        else:
            self.kpi_margem.set_state(f"{margem*100:.2f}%".replace(".", ","), "lucro bruto / faturamento", "", "neutral")

        # gráficos
        self.update_charts(df)

        # alertas + qualidade + insights
        self.update_alertas(df)
        self.txt_quality.setPlainText(self.quality_text(df))
        self.txt_insights.setPlainText(self.insights_text(df))

    def update_charts(self, df: pd.DataFrame):
        # mensal
        self.fig_mes.clear()
        ax = self.fig_mes.add_subplot(111)
        ax.set_title("Faturamento Líquido Mensal", fontsize=10, fontweight="bold")
        serie = self.serie_mensal(df, liquida=True)

        if len(serie) > 0:
            x = [str(p) for p in serie.index]
            ax.plot(x, serie.values, marker="o")
            ax.tick_params(axis="x", rotation=45, labelsize=8)
            ax.yaxis.set_major_formatter(FuncFormatter(brl_axis))
            ax.ticklabel_format(style="plain", axis="y")
        else:
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")

        self.fig_mes.tight_layout()
        self.canvas_mes.draw()

        # top produtos (horizontal BI style)
        self.fig_top.clear()
        ax2 = self.fig_top.add_subplot(111)
        ax2.set_title("Top Produtos (Faturamento)", fontsize=10, fontweight="bold")

        if "produto" in df.columns and "valor_total" in df.columns and not df.empty:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(top) > 0:
                top = top.sort_values()  # menor -> maior (barh fica bonito)
                ax2.barh(top.index.astype(str), top.values)
                ax2.xaxis.set_major_formatter(FuncFormatter(brl_axis))
                ax2.ticklabel_format(style="plain", axis="x")
            else:
                ax2.text(0.5, 0.5, "Sem top produtos", ha="center", va="center")
        else:
            ax2.text(0.5, 0.5, "Coluna produto/valor_total ausente", ha="center", va="center")

        self.fig_top.tight_layout()
        self.canvas_top.draw()

        # canal
        self.fig_canal.clear()
        ax3 = self.fig_canal.add_subplot(111)
        ax3.set_title("Faturamento por Canal", fontsize=10, fontweight="bold")

        if "canal" in df.columns and "valor_total" in df.columns and not df.empty:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)
            if len(canal) > 0:
                ax3.bar(canal.index.astype(str), canal.values)
                ax3.yaxis.set_major_formatter(FuncFormatter(brl_axis))
                ax3.ticklabel_format(style="plain", axis="y")
            else:
                ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        else:
            ax3.text(0.5, 0.5, "Coluna canal ausente", ha="center", va="center")

        self.fig_canal.tight_layout()
        self.canvas_canal.draw()

        # donut participação
        self.fig_donut.clear()
        ax4 = self.fig_donut.add_subplot(111)
        ax4.set_title("Participação por Canal", fontsize=10, fontweight="bold")

        if "canal" in df.columns and "valor_total" in df.columns and not df.empty:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False).head(6)
            total = safe_float(canal.sum())
            if total > 0:
                labels = canal.index.astype(str).tolist()
                values = canal.values.tolist()
                wedges, texts, autotexts = ax4.pie(
                    values,
                    labels=labels,
                    autopct=lambda p: f"{p:.0f}%",
                    pctdistance=0.78
                )
                # efeito donut
                from matplotlib.patches import Circle
                centre_circle = Circle((0, 0), 0.55, fc="white")
                ax4.add_artist(centre_circle)
                ax4.axis("equal")
            else:
                ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")

        self.fig_donut.tight_layout()
        self.canvas_donut.draw()

    def update_alertas(self, df: pd.DataFrame):
        if df.empty:
            self.lbl_alert.setText("Sem dados no recorte.")
            self.model_alert.update(pd.DataFrame())
            return

        alerts = []

        inv = invalid_status_mask(df)
        if inv.any():
            a = df[inv].copy()
            a["tipo_alerta"] = "STATUS_CANCEL_DENEG"
            alerts.append(a)

        if "ean" in df.columns:
            mask_ean = df["ean"].astype(str).str.len().ne(13)
            if mask_ean.any():
                a = df[mask_ean].copy()
                a["tipo_alerta"] = "EAN_INVALIDO_LEN"
                alerts.append(a)

            dup = df[df.duplicated(subset=["ean"], keep=False)].copy()
            if not dup.empty:
                dup["tipo_alerta"] = "EAN_DUPLICADO"
                alerts.append(dup)

        if "preco_unitario" in df.columns:
            mask_out = compute_outlier_mask(df["preco_unitario"])
            if mask_out.any():
                a = df[mask_out].copy()
                a["tipo_alerta"] = "OUTLIER_PRECO_UNITARIO"
                alerts.append(a)

        if not alerts:
            self.lbl_alert.setText("✅ Nenhum alerta relevante no recorte atual.")
            self.model_alert.update(pd.DataFrame())
            return

        final = pd.concat(alerts, ignore_index=True)

        # colunas mais úteis
        cols_show = []
        for c in ["tipo_alerta", "data", "venda_id", "produto", "ean", "quantidade",
                  "preco_unitario", "valor_total", "uf_destino", "cfop", "status", "cliente"]:
            if c in final.columns:
                cols_show.append(c)
        if cols_show:
            final = final[cols_show]

        resumo = final["tipo_alerta"].value_counts()
        texto = "🚨 Alertas (recorte atual)\n\n" + "\n".join([f"- {k}: {int(v)}" for k, v in resumo.items()])
        texto += "\n\nDica: na aba Tabela, linhas com alerta são destacadas por cor."
        self.lbl_alert.setText(texto)

        self.model_alert.update(final.head(1000))

    def quality_text(self, df: pd.DataFrame) -> str:
        linhas = []
        linhas.append("🧪 Qualidade de Dados (recorte atual)\n")
        linhas.append(f"- Linhas: {df.shape[0]}")
        linhas.append(f"- Colunas: {df.shape[1]}")

        # nulos
        nulos = df.isna().sum().sort_values(ascending=False).head(12)
        linhas.append("\nTop colunas com nulos:")
        for col, qtd in nulos.items():
            if qtd > 0:
                linhas.append(f"  • {col}: {int(qtd)}")

        # EAN
        if "ean" in df.columns:
            inv = int(df["ean"].astype(str).str.len().ne(13).sum())
            dup = int(df[df.duplicated(subset=["ean"], keep=False)]["ean"].nunique())
            linhas.append(f"\nEAN inválidos (len != 13): {inv}")
            linhas.append(f"EAN duplicados (distintos): {dup}")

        # outliers
        if "preco_unitario" in df.columns:
            out = int(compute_outlier_mask(df["preco_unitario"]).sum())
            linhas.append(f"\nOutliers preco_unitario (IQR): {out}")

        # status inválido
        invst = int(invalid_status_mask(df).sum()) if "status" in df.columns else 0
        linhas.append(f"\nStatus inválido (cancel/deneg/inutil): {invst}")

        return "\n".join(linhas)

    def insights_text(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "Sem dados suficientes para gerar insights."

        fat_liq, impacto = self.fat_liq(df)
        fat_bruto = self.fat_bruto(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket(df)
        margem = self.margem_pct(df)

        lines = []
        lines.append("Resumo interpretável do recorte atual:\n")
        lines.append(f"- Faturamento líquido: {brl(fat_liq)}")
        lines.append(f"- Faturamento bruto: {brl(fat_bruto)}")
        lines.append(f"- Impacto por cancel/deneg: {brl(impacto)}")
        lines.append(f"- Qtd vendas: {vendas}")
        lines.append(f"- Ticket médio: {brl(ticket)}")
        if margem is not None:
            lines.append(f"- Margem bruta: {(margem*100):.2f}%".replace(".", ","))
        else:
            lines.append("- Margem bruta: indisponível (sem custo_total)")

        # recomendações
        lines.append("\nPontos de atenção / recomendações:")
        if impacto > 0:
            lines.append("• Existe perda por status inválido. Recomendado separar documentos cancel/deneg no relatório executivo.")
        else:
            lines.append("• Sem perdas relevantes por status inválido no recorte.")

        if "ean" in df.columns:
            inv_ean = int(df["ean"].astype(str).str.len().ne(13).sum())
            if inv_ean > 0:
                lines.append(f"• EAN inválidos detectados: {inv_ean}. Corrigir melhora rastreabilidade e BI.")
            dup_ean = int(df[df.duplicated(subset=["ean"], keep=False)]["ean"].nunique())
            if dup_ean > 0:
                lines.append(f"• EAN duplicados: {dup_ean}. Verificar cadastro de produtos.")

        # top produto
        if "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(3)
            if len(top) > 0:
                lines.append("\nTop 3 produtos por faturamento:")
                for p, v in top.items():
                    lines.append(f"• {p}: {brl(v)}")

        # canal dominante
        if "canal" in df.columns and "valor_total" in df.columns:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)
            if len(canal) > 0 and safe_float(canal.sum()) > 0:
                share = canal.iloc[0] / canal.sum()
                lines.append(f"\nCanal dominante: {canal.index[0]} ({(share*100):.1f}%)".replace(".", ","))

        return "\n".join(lines)

    # ---------------- Export Excel ----------------
    def on_export_excel(self):
        if self.base.empty:
            return

        df = self.df.copy()

        arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Excel",
            str(self.base_dir / "relatorio_dashboard_v6.xlsx"),
            "Excel (*.xlsx)"
        )
        if not arquivo:
            return

        try:
            fat_liq, impacto = self.fat_liq(df)
            fat_bruto = self.fat_bruto(df)
            vendas = self.qtd_vendas(df)
            ticket = self.ticket(df)
            margem = self.margem_pct(df)

            resumo = pd.DataFrame([{
                "faturamento_liquido": fat_liq,
                "faturamento_bruto": fat_bruto,
                "impacto_cancel_deneg": impacto,
                "ticket_medio": ticket,
                "qtd_vendas": vendas,
                "qtd_itens": int(df.shape[0]),
                "margem_bruta_pct": margem,
                "data_export": datetime.now().strftime("%Y-%m-%d %H:%M")
            }])

            mensal = self.serie_mensal(df, liquida=True).reset_index()
            if not mensal.empty:
                mensal.columns = ["mes", "faturamento_liquido"]

            top = pd.DataFrame()
            if "produto" in df.columns and "valor_total" in df.columns:
                top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(30).reset_index()
                top.columns = ["produto", "faturamento"]

            canal = pd.DataFrame()
            if "canal" in df.columns and "valor_total" in df.columns:
                canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False).reset_index()
                canal.columns = ["canal", "faturamento"]

            # alertas
            # reutiliza lógica: só pega a tabela visível
            alerts_df = self.model_alert.df.copy() if hasattr(self.model_alert, "df") else pd.DataFrame()

            with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
                resumo.to_excel(writer, sheet_name="Resumo_Executivo", index=False)
                df.to_excel(writer, sheet_name="Base_Filtrada", index=False)
                (mensal if not mensal.empty else pd.DataFrame({"info": ["Sem série mensal"]})).to_excel(writer, sheet_name="Faturamento_Mensal", index=False)
                (top if not top.empty else pd.DataFrame({"info": ["Sem top produtos"]})).to_excel(writer, sheet_name="Top_Produtos", index=False)
                (canal if not canal.empty else pd.DataFrame({"info": ["Sem canal"]})).to_excel(writer, sheet_name="Faturamento_Canal", index=False)
                (alerts_df if not alerts_df.empty else pd.DataFrame({"info": ["Sem alertas"]})).to_excel(writer, sheet_name="Alertas", index=False)

            QMessageBox.information(self, "Excel", f"✅ Excel exportado com sucesso:\n{arquivo}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))


def main():
    app = QApplication(sys.argv)
    w = DashboardV6()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
'''
outpath = Path("/mnt/data/dashboard_v6_pyside6.py")
outpath.write_text(code, encoding="utf-8")
str(outpath)