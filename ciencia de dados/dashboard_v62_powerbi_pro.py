import sys
import tempfile
from pathlib import Path
from datetime import datetime, date

import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTabWidget, QTableView, QMessageBox,
    QComboBox, QGroupBox, QDateEdit,
    QFrame, QGridLayout, QSizePolicy, QTextEdit,
    QDoubleSpinBox, QSpinBox
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdf_canvas


# =========================================================
# Utils
# =========================================================
def format_brl(valor: float) -> str:
    try:
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


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


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()

    # Produto
    if "produto" not in base.columns and "descricao" in base.columns:
        base.rename(columns={"descricao": "produto"}, inplace=True)

    # Canal
    if "canal" not in base.columns and "canal_aquisicao" in base.columns:
        base.rename(columns={"canal_aquisicao": "canal"}, inplace=True)

    # Data
    if "data" not in base.columns and "dh_emissao" in base.columns:
        base.rename(columns={"dh_emissao": "data"}, inplace=True)

    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")

    # Valores
    if "valor_total" not in base.columns and "v_prod" in base.columns:
        base.rename(columns={"v_prod": "valor_total"}, inplace=True)

    if "preco_unitario" not in base.columns and "v_un" in base.columns:
        base.rename(columns={"v_un": "preco_unitario"}, inplace=True)

    # EAN
    if "ean" in base.columns:
        base["ean"] = base["ean"].astype(str)

    # Nome cliente
    if "nome" not in base.columns:
        for cand in ["razao_social", "cliente", "destinatario_nome"]:
            if cand in base.columns:
                base.rename(columns={cand: "nome"}, inplace=True)
                break

    return base


def checar_arquivos_erp(data_dir: Path):
    arquivos = ["clientes.csv", "produtos.csv", "vendas.csv", "itens_venda.csv"]
    return [a for a in arquivos if not (data_dir / a).exists()]


def carregar_base_erp(data_dir: Path) -> pd.DataFrame:
    clientes = pd.read_csv(data_dir / "clientes.csv")
    produtos = pd.read_csv(data_dir / "produtos.csv")
    vendas = pd.read_csv(data_dir / "vendas.csv", parse_dates=["data"])
    itens = pd.read_csv(data_dir / "itens_venda.csv")

    base = (itens
            .merge(vendas, on="venda_id", how="left")
            .merge(produtos, on="produto_id", how="left")
            .merge(clientes, on="cliente_id", how="left"))

    return normalize_cols(base)


def compute_outlier_mask(series: pd.Series) -> pd.Series:
    if series is None or series.empty:
        return pd.Series([False] * 0)

    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return pd.Series([False] * len(series), index=series.index)

    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    lim_sup = q3 + 1.5 * iqr
    return pd.to_numeric(series, errors="coerce") > lim_sup


def invalid_status_mask(df: pd.DataFrame) -> pd.Series:
    if "status" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    st = df["status"].astype(str).str.upper()
    return st.str.contains("CANCEL") | st.str.contains("DENEG") | st.str.contains("INUTIL")


def donut(ax, labels, values, title=""):
    ax.clear()
    ax.set_title(title, fontsize=10, fontweight="bold")
    total = safe_float(sum(values))
    if total <= 0:
        ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        return
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct=lambda p: f"{p:.0f}%",
        pctdistance=0.78
    )
    # efeito donut
    from matplotlib.patches import Circle
    centre_circle = Circle((0, 0), 0.55, fc="white")
    ax.add_artist(centre_circle)
    ax.axis("equal")


# =========================================================
# Tabela (Model)
# =========================================================
class PandasTableModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df.copy()
        self.flag_outlier = pd.Series([False] * len(df))
        self.flag_ean_invalid = pd.Series([False] * len(df))
        self.flag_cancel = pd.Series([False] * len(df))

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
            if isinstance(value, float):
                return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return str(value)

        if role == Qt.BackgroundRole:
            try:
                if len(self.flag_cancel) > 0 and bool(self.flag_cancel.iloc[r]):
                    return QColor(255, 220, 220)  # vermelho claro
                if len(self.flag_outlier) > 0 and bool(self.flag_outlier.iloc[r]):
                    return QColor(255, 245, 204)  # amarelo claro
                if len(self.flag_ean_invalid) > 0 and bool(self.flag_ean_invalid.iloc[r]):
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
        self.flag_outlier = flag_outlier if flag_outlier is not None else pd.Series([False] * n)
        self.flag_ean_invalid = flag_ean_invalid if flag_ean_invalid is not None else pd.Series([False] * n)
        self.flag_cancel = flag_cancel if flag_cancel is not None else pd.Series([False] * n)

        self.flag_outlier = self.flag_outlier.reindex(df.index, fill_value=False)
        self.flag_ean_invalid = self.flag_ean_invalid.reindex(df.index, fill_value=False)
        self.flag_cancel = self.flag_cancel.reindex(df.index, fill_value=False)

        self.endResetModel()


# =========================================================
# KPI Card (meta + semáforo)
# =========================================================
class KpiCardPro(QFrame):
    """
    Card estilo Power BI:
    - Valor principal
    - Tendência vs mês anterior
    - Meta + Atingimento
    - Semáforo por regra:
      verde: >= meta
      amarelo: >= 90% meta
      vermelho: < 90% meta
    """
    def __init__(self, titulo: str):
        super().__init__()
        self.setObjectName("KpiCardPro")
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._status_color = "#9CA3AF"  # cinza neutro

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.lbl_dot = QLabel("●")
        self.lbl_dot.setStyleSheet(f"color: {self._status_color}; font-size: 14px; font-weight: 900;")
        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setStyleSheet("font-size: 12px; color: #5A5A5A; font-weight: 800;")
        top.addWidget(self.lbl_dot)
        top.addWidget(self.lbl_titulo)
        top.addStretch()
        layout.addLayout(top)

        self.lbl_valor = QLabel("-")
        self.lbl_valor.setStyleSheet("font-size: 22px; font-weight: 900; color: #111111;")
        layout.addWidget(self.lbl_valor)

        self.lbl_trend = QLabel("—")
        self.lbl_trend.setStyleSheet("font-size: 11px; color: #6B7280; font-weight: 700;")
        layout.addWidget(self.lbl_trend)

        self.lbl_meta = QLabel("Meta: — | Ating: —")
        self.lbl_meta.setStyleSheet("font-size: 11px; color: #374151; font-weight: 700;")
        layout.addWidget(self.lbl_meta)

        self.setStyleSheet("""
            QFrame#KpiCardPro {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
            }
        """)

    def set_state(self, valor_text: str, trend_text: str, meta_text: str, status: str):
        self.lbl_valor.setText(valor_text)
        self.lbl_trend.setText(trend_text)
        self.lbl_meta.setText(meta_text)

        if status == "green":
            self._status_color = "#1B9E77"
        elif status == "yellow":
            self._status_color = "#F59E0B"
        elif status == "red":
            self._status_color = "#D62728"
        else:
            self._status_color = "#9CA3AF"

        self.lbl_dot.setStyleSheet(f"color: {self._status_color}; font-size: 14px; font-weight: 900;")


# =========================================================
# Dashboard v6.2 PRO
# =========================================================
class DashboardV62(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard v6.2 PRO - 100% Power BI Style (Metas + PDF + Drilldown)")
        self.resize(1600, 900)

        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "dados"

        self.base = pd.DataFrame()
        self.base_filtrada = pd.DataFrame()

        # Metas (padrão)
        self.meta_fat_liq = 300000.0
        self.meta_margem_pct = 0.20
        self.meta_ticket = 450.0
        self.meta_vendas = 1000

        # =========================
        # Layout raiz (Sidebar + Conteúdo)
        # =========================
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(360)
        self.sidebar.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
            }
        """)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(14, 14, 14, 14)
        sb.setSpacing(10)

        lbl_title = QLabel("Slicers (Filtros) + Metas")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 900; color: #111111;")
        sb.addWidget(lbl_title)

        self.lbl_status = QLabel("Status: aguardando...")
        self.lbl_status.setStyleSheet("font-weight:800; color:#1F4E79;")
        sb.addWidget(self.lbl_status)

        # Botões topo
        hb = QHBoxLayout()
        self.btn_carregar = QPushButton("Carregar")
        self.btn_carregar.clicked.connect(self.on_carregar)

        self.btn_escolher = QPushButton("Pasta...")
        self.btn_escolher.clicked.connect(self.on_escolher_pasta)

        hb.addWidget(self.btn_carregar)
        hb.addWidget(self.btn_escolher)
        sb.addLayout(hb)

        hb2 = QHBoxLayout()
        self.btn_limpar = QPushButton("Limpar")
        self.btn_limpar.clicked.connect(self.on_limpar)
        self.btn_limpar.setEnabled(False)

        self.btn_excel = QPushButton("Excel PRO")
        self.btn_excel.clicked.connect(self.on_exportar_excel)
        self.btn_excel.setEnabled(False)

        hb2.addWidget(self.btn_limpar)
        hb2.addWidget(self.btn_excel)
        sb.addLayout(hb2)

        hb3 = QHBoxLayout()
        self.btn_pdf = QPushButton("PDF Executivo")
        self.btn_pdf.clicked.connect(self.on_exportar_pdf)
        self.btn_pdf.setEnabled(False)

        hb3.addWidget(self.btn_pdf)
        sb.addLayout(hb3)

        # Filtros (slicers)
        self.input_busca = QLineEdit()
        self.input_busca.setPlaceholderText("Buscar (produto, EAN, cliente...)")
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

        def slicer_box(title, widget):
            b = QGroupBox(title)
            b.setStyleSheet("QGroupBox{font-weight:900;}")
            lay = QVBoxLayout(b)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.addWidget(widget)
            return b

        sb.addWidget(slicer_box("Texto", self.input_busca))
        sb.addWidget(slicer_box("UF", self.combo_uf))
        sb.addWidget(slicer_box("Canal", self.combo_canal))
        sb.addWidget(slicer_box("Categoria", self.combo_categoria))
        sb.addWidget(slicer_box("Status", self.combo_status))

        periodo = QGroupBox("Período")
        periodo.setStyleSheet("QGroupBox{font-weight:900;}")
        lp = QHBoxLayout(periodo)
        lp.setContentsMargins(10, 8, 10, 8)
        lp.addWidget(QLabel("De:"))
        lp.addWidget(self.date_ini)
        lp.addWidget(QLabel("Até:"))
        lp.addWidget(self.date_fim)
        sb.addWidget(periodo)

        self.lbl_linhas = QLabel("Linhas: 0")
        self.lbl_linhas.setStyleSheet("font-weight:900; color:#111111;")
        sb.addWidget(self.lbl_linhas)

        # Metas (Power BI - cards com semáforo)
        metas = QGroupBox("Metas (KPIs)")
        metas.setStyleSheet("QGroupBox{font-weight:900;}")
        fm = QGridLayout(metas)
        fm.setContentsMargins(10, 8, 10, 8)
        fm.setHorizontalSpacing(8)
        fm.setVerticalSpacing(6)

        self.spin_meta_fat = QDoubleSpinBox()
        self.spin_meta_fat.setMaximum(1e12)
        self.spin_meta_fat.setValue(self.meta_fat_liq)
        self.spin_meta_fat.setPrefix("R$ ")
        self.spin_meta_fat.valueChanged.connect(self.on_update_metas)

        self.spin_meta_margem = QDoubleSpinBox()
        self.spin_meta_margem.setRange(0, 100)
        self.spin_meta_margem.setValue(self.meta_margem_pct * 100)
        self.spin_meta_margem.setSuffix(" %")
        self.spin_meta_margem.valueChanged.connect(self.on_update_metas)

        self.spin_meta_ticket = QDoubleSpinBox()
        self.spin_meta_ticket.setMaximum(1e12)
        self.spin_meta_ticket.setValue(self.meta_ticket)
        self.spin_meta_ticket.setPrefix("R$ ")
        self.spin_meta_ticket.valueChanged.connect(self.on_update_metas)

        self.spin_meta_vendas = QSpinBox()
        self.spin_meta_vendas.setMaximum(10_000_000)
        self.spin_meta_vendas.setValue(self.meta_vendas)
        self.spin_meta_vendas.valueChanged.connect(self.on_update_metas)

        fm.addWidget(QLabel("Meta Fat. Líquido:"), 0, 0)
        fm.addWidget(self.spin_meta_fat, 0, 1)
        fm.addWidget(QLabel("Meta Margem:"), 1, 0)
        fm.addWidget(self.spin_meta_margem, 1, 1)
        fm.addWidget(QLabel("Meta Ticket:"), 2, 0)
        fm.addWidget(self.spin_meta_ticket, 2, 1)
        fm.addWidget(QLabel("Meta Vendas:"), 3, 0)
        fm.addWidget(self.spin_meta_vendas, 3, 1)

        sb.addWidget(metas)
        sb.addStretch()

        # =========================
        # Conteúdo (tabs)
        # =========================
        self.content = QFrame()
        self.content.setStyleSheet("""
            QFrame {
                background: #F8FAFC;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
            }
        """)
        ct = QVBoxLayout(self.content)
        ct.setContentsMargins(14, 14, 14, 14)
        ct.setSpacing(10)

        header = QLabel("Resumo Executivo — Power BI PRO (Metas + Tendência + Drilldown + PDF)")
        header.setStyleSheet("font-size: 15px; font-weight: 900; color: #111111;")
        ct.addWidget(header)

        self.tabs = QTabWidget()
        ct.addWidget(self.tabs)

        # Aba 1: Resumo
        self.tab_exec = QWidget()
        self.tabs.addTab(self.tab_exec, "Resumo Executivo")
        self.build_tab_exec()

        # Aba 2: Drilldown
        self.tab_drill = QWidget()
        self.tabs.addTab(self.tab_drill, "Drilldown")
        self.build_tab_drilldown()

        # Aba 3: Tabela
        self.tab_tabela = QWidget()
        self.tabs.addTab(self.tab_tabela, "Tabela")
        t1 = QVBoxLayout(self.tab_tabela)
        self.table_base = QTableView()
        self.table_base.setSortingEnabled(True)
        self.model_base = PandasTableModel(pd.DataFrame())
        self.table_base.setModel(self.model_base)
        t1.addWidget(self.table_base)

        # Aba 4: Alertas
        self.tab_alertas = QWidget()
        self.tabs.addTab(self.tab_alertas, "Alertas")
        ta = QVBoxLayout(self.tab_alertas)
        self.lbl_alertas = QLabel("Carregue os dados para ver os alertas.")
        self.lbl_alertas.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ta.addWidget(self.lbl_alertas)
        self.table_alertas = QTableView()
        self.table_alertas.setSortingEnabled(True)
        self.model_alertas = PandasTableModel(pd.DataFrame())
        self.table_alertas.setModel(self.model_alertas)
        ta.addWidget(self.table_alertas)

        # Aba 5: Qualidade
        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade de Dados")
        tq = QVBoxLayout(self.tab_quality)
        self.lbl_quality = QLabel("Carregue os dados para ver a auditoria.")
        self.lbl_quality.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tq.addWidget(self.lbl_quality)

        root.addWidget(self.sidebar)
        root.addWidget(self.content, 1)

        # Tema
        self.apply_theme()

        # Autoload se existir "dados/"
        if self.data_dir.exists():
            self.on_carregar()

    # =========================================================
    # Layout Resumo Executivo
    # =========================================================
    def apply_theme(self):
        self.setStyleSheet("""
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
            QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {
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
        """)

    def build_tab_exec(self):
        layout = QVBoxLayout(self.tab_exec)
        layout.setSpacing(12)

        # Cards KPI
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.kpi_fat_liq = KpiCardPro("Faturamento Líquido")
        self.kpi_margem = KpiCardPro("Margem Bruta")
        self.kpi_ticket = KpiCardPro("Ticket Médio")
        self.kpi_vendas = KpiCardPro("Qtd Vendas")
        self.kpi_impacto = KpiCardPro("Impacto Cancel/Deneg")
        self.kpi_itens = KpiCardPro("Qtd Itens")

        grid.addWidget(self.kpi_fat_liq, 0, 0)
        grid.addWidget(self.kpi_margem, 0, 1)
        grid.addWidget(self.kpi_ticket, 0, 2)
        grid.addWidget(self.kpi_vendas, 1, 0)
        grid.addWidget(self.kpi_itens, 1, 1)
        grid.addWidget(self.kpi_impacto, 1, 2)

        layout.addLayout(grid)

        # Comparativo mês atual x anterior (executivo)
        self.box_comp = QGroupBox("Comparativo Executivo — Último mês vs Mês anterior")
        self.box_comp.setStyleSheet("QGroupBox{font-weight:900;}")
        comp_layout = QGridLayout(self.box_comp)
        comp_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_comp_period = QLabel("Período: —")
        self.lbl_comp_period.setStyleSheet("font-weight:900; color:#111111;")
        comp_layout.addWidget(self.lbl_comp_period, 0, 0, 1, 4)

        self.lbl_comp_fat = QLabel("Fat. Líq: —")
        self.lbl_comp_ticket = QLabel("Ticket: —")
        self.lbl_comp_vendas = QLabel("Vendas: —")
        self.lbl_comp_margem = QLabel("Margem: —")

        for i, w in enumerate([self.lbl_comp_fat, self.lbl_comp_ticket, self.lbl_comp_vendas, self.lbl_comp_margem]):
            w.setStyleSheet("font-weight:800; color:#111111;")
            comp_layout.addWidget(w, 1 + i // 2, i % 2)

        layout.addWidget(self.box_comp)

        # Visuais
        vis = QGridLayout()
        vis.setHorizontalSpacing(12)
        vis.setVerticalSpacing(12)

        self.frame_mes, self.canvas_mes, self.fig_mes = self.make_chart("Faturamento Mensal (líquido)")
        self.frame_top, self.canvas_top, self.fig_top = self.make_chart("Top Produtos (faturamento)")
        self.frame_canal, self.canvas_canal, self.fig_canal = self.make_chart("Faturamento por Canal")
        self.frame_donut, self.canvas_donut, self.fig_donut = self.make_chart("Participação por Canal (donut)")

        vis.addWidget(self.frame_mes, 0, 0)
        vis.addWidget(self.frame_top, 0, 1)
        vis.addWidget(self.frame_canal, 1, 0)
        vis.addWidget(self.frame_donut, 1, 1)

        layout.addLayout(vis)

        # Insights
        self.txt_insights = QTextEdit()
        self.txt_insights.setReadOnly(True)
        self.txt_insights.setMinimumHeight(160)
        self.txt_insights.setStyleSheet("""
            QTextEdit{
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
                padding:10px;
                font-size:12px;
            }
        """)
        layout.addWidget(self.txt_insights)

    def make_chart(self, title: str):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame{
                background:#FFFFFF;
                border:1px solid #E6E6E6;
                border-radius:14px;
            }
        """)
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

    # =========================================================
    # Drilldown
    # =========================================================
    def build_tab_drilldown(self):
        layout = QVBoxLayout(self.tab_drill)
        layout.setSpacing(10)

        top = QHBoxLayout()

        self.combo_dim = QComboBox()
        self.combo_dim.addItems(["Canal", "UF", "Categoria"])
        self.combo_dim.currentIndexChanged.connect(self.update_drilldown)

        self.combo_val = QComboBox()
        self.combo_val.currentIndexChanged.connect(self.update_drilldown)

        top.addWidget(QLabel("Dimensão:"))
        top.addWidget(self.combo_dim)
        top.addWidget(QLabel("Valor:"))
        top.addWidget(self.combo_val)
        top.addStretch()

        layout.addLayout(top)

        # gráficos do drilldown
        drill_grid = QGridLayout()
        drill_grid.setHorizontalSpacing(12)
        drill_grid.setVerticalSpacing(12)

        self.frame_drill_top, self.canvas_drill_top, self.fig_drill_top = self.make_chart("Top Produtos (recorte drilldown)")
        self.frame_drill_mes, self.canvas_drill_mes, self.fig_drill_mes = self.make_chart("Série Mensal (recorte drilldown)")

        drill_grid.addWidget(self.frame_drill_top, 0, 0)
        drill_grid.addWidget(self.frame_drill_mes, 0, 1)

        layout.addLayout(drill_grid)

        # tabela drilldown
        self.table_drill = QTableView()
        self.table_drill.setSortingEnabled(True)
        self.model_drill = PandasTableModel(pd.DataFrame())
        self.table_drill.setModel(self.model_drill)
        layout.addWidget(self.table_drill)

        self.lbl_drill_info = QLabel("Selecione uma dimensão e valor.")
        self.lbl_drill_info.setStyleSheet("font-weight:800;")
        layout.addWidget(self.lbl_drill_info)

    # =========================================================
    # Metas
    # =========================================================
    def on_update_metas(self):
        self.meta_fat_liq = float(self.spin_meta_fat.value())
        self.meta_margem_pct = float(self.spin_meta_margem.value()) / 100.0
        self.meta_ticket = float(self.spin_meta_ticket.value())
        self.meta_vendas = int(self.spin_meta_vendas.value())

        self.atualizar_tudo()

    # =========================================================
    # Load / Combos / Período
    # =========================================================
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
            self.preencher_periodo()
            self.atualizar_tudo()

            self.btn_limpar.setEnabled(True)
            self.btn_excel.setEnabled(True)
            self.btn_pdf.setEnabled(True)

            self.lbl_status.setText(f"Status: OK | Base: {self.base.shape[0]} linhas / {self.base.shape[1]} colunas")

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

        self.combo_uf.addItem("Todas")
        self.combo_canal.addItem("Todos")
        self.combo_categoria.addItem("Todas")
        self.combo_status.addItem("Todos")

        if "uf_destino" in self.base.columns:
            for u in sorted(self.base["uf_destino"].dropna().unique().tolist()):
                self.combo_uf.addItem(u)

        if "canal" in self.base.columns:
            for c in sorted(self.base["canal"].dropna().unique().tolist()):
                self.combo_canal.addItem(c)

        if "categoria" in self.base.columns:
            for cat in sorted(self.base["categoria"].dropna().unique().tolist()):
                self.combo_categoria.addItem(cat)

        if "status" in self.base.columns:
            for st in sorted(self.base["status"].dropna().unique().tolist()):
                self.combo_status.addItem(st)

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

    # =========================================================
    # Filtros
    # =========================================================
    def on_limpar(self):
        self.input_busca.setText("")
        self.combo_uf.setCurrentIndex(0)
        self.combo_canal.setCurrentIndex(0)
        self.combo_categoria.setCurrentIndex(0)
        self.combo_status.setCurrentIndex(0)
        self.preencher_periodo()

        self.base_filtrada = self.base.copy()
        self.atualizar_tudo()

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
            cols_preferidas = [c for c in df.columns if c.lower() in [
                "produto", "ean", "uf_destino", "canal", "categoria", "cfop",
                "cst_icms", "nome", "marca"
            ]]
            if not cols_preferidas:
                cols_preferidas = df.columns.tolist()

            mask = df[cols_preferidas].astype(str).apply(
                lambda col: col.str.lower().str.contains(termo, na=False)
            ).any(axis=1)
            df = df[mask]

        # uf
        uf_sel = self.combo_uf.currentText()
        if uf_sel != "Todas" and "uf_destino" in df.columns:
            df = df[df["uf_destino"] == uf_sel]

        # canal
        canal_sel = self.combo_canal.currentText()
        if canal_sel != "Todos" and "canal" in df.columns:
            df = df[df["canal"] == canal_sel]

        # categoria
        cat_sel = self.combo_categoria.currentText()
        if cat_sel != "Todas" and "categoria" in df.columns:
            df = df[df["categoria"] == cat_sel]

        # status
        st_sel = self.combo_status.currentText()
        if st_sel != "Todos" and "status" in df.columns:
            df = df[df["status"] == st_sel]

        self.base_filtrada = df.copy()
        self.atualizar_tudo()

    # =========================================================
    # KPIs / Séries / Tendência
    # =========================================================
    def faturamento_bruto(self, df: pd.DataFrame) -> float:
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        return safe_float(df["valor_total"].sum())

    def faturamento_liquido(self, df: pd.DataFrame) -> tuple[float, float]:
        """(fat_liq, impacto_cancel_deneg)"""
        if df.empty or "valor_total" not in df.columns:
            return 0.0, 0.0
        fat_bruto = safe_float(df["valor_total"].sum())
        inv = invalid_status_mask(df)
        fat_liq = safe_float(df.loc[~inv, "valor_total"].sum())
        return fat_liq, (fat_bruto - fat_liq)

    def qtd_vendas(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        if "venda_id" in df.columns:
            return safe_int(df["venda_id"].nunique())
        return safe_int(len(df))

    def ticket_medio(self, df: pd.DataFrame) -> float:
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        if "venda_id" in df.columns:
            s = df.groupby("venda_id")["valor_total"].sum()
            return safe_float(s.mean())
        return safe_float(df["valor_total"].mean())

    def margem_pct(self, df: pd.DataFrame) -> float | None:
        if df.empty or "valor_total" not in df.columns or "custo_total" not in df.columns:
            return None
        fat = safe_float(df["valor_total"].sum())
        custo = safe_float(df["custo_total"].sum())
        if fat == 0:
            return 0.0
        return (fat - custo) / fat

    def serie_mensal(self, df: pd.DataFrame, liquido=True) -> pd.Series:
        if df.empty or "data" not in df.columns or "valor_total" not in df.columns:
            return pd.Series(dtype=float)
        tmp = df.dropna(subset=["data"]).copy()
        if tmp.empty:
            return pd.Series(dtype=float)
        if liquido:
            inv = invalid_status_mask(tmp)
            tmp = tmp.loc[~inv].copy()
        return tmp.groupby(tmp["data"].dt.to_period("M"))["valor_total"].sum().sort_index()

    def serie_vendas_mensal(self, df: pd.DataFrame) -> pd.Series:
        if df.empty or "data" not in df.columns:
            return pd.Series(dtype=float)
        tmp = df.dropna(subset=["data"]).copy()
        if tmp.empty:
            return pd.Series(dtype=float)
        if "venda_id" in tmp.columns:
            return tmp.groupby(tmp["data"].dt.to_period("M"))["venda_id"].nunique().sort_index()
        return tmp.groupby(tmp["data"].dt.to_period("M")).size().sort_index()

    def delta_last_month(self, serie: pd.Series):
        """(delta_abs, delta_pct, last_label, prev_label)"""
        if serie is None:
            return None, None, "", ""
        serie = serie.dropna()
        if len(serie) < 2:
            return None, None, "", ""
        last = safe_float(serie.iloc[-1])
        prev = safe_float(serie.iloc[-2])
        delta_abs = last - prev
        delta_pct = (delta_abs / prev) if prev != 0 else None
        last_label = str(serie.index[-1])
        prev_label = str(serie.index[-2])
        return delta_abs, delta_pct, last_label, prev_label

    def semaforo(self, atual: float, meta: float) -> tuple[str, float]:
        """Retorna status e atingimento em % (0..1)."""
        if meta <= 0:
            return "neutral", 0.0
        ating = atual / meta
        if ating >= 1.0:
            return "green", ating
        if ating >= 0.90:
            return "yellow", ating
        return "red", ating

    # =========================================================
    # Alertas / Qualidade / Insights
    # =========================================================
    def gerar_flags_tabela(self, df: pd.DataFrame):
        n = len(df)
        if n == 0:
            return pd.Series([], dtype=bool), pd.Series([], dtype=bool), pd.Series([], dtype=bool)

        flag_out = pd.Series([False] * n, index=df.index)
        if "preco_unitario" in df.columns:
            flag_out = compute_outlier_mask(df["preco_unitario"]).fillna(False)

        flag_ean = pd.Series([False] * n, index=df.index)
        if "ean" in df.columns:
            flag_ean = df["ean"].astype(str).str.len().ne(13)

        flag_cancel = invalid_status_mask(df)

        return flag_out, flag_ean, flag_cancel

    def gerar_alertas(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

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
            return pd.DataFrame()

        final = pd.concat(alerts, ignore_index=True)

        cols_show = []
        for c in ["tipo_alerta", "data", "venda_id", "produto", "ean", "quantidade",
                  "preco_unitario", "valor_total", "uf_destino", "cfop", "status", "nome"]:
            if c in final.columns:
                cols_show.append(c)

        if cols_show:
            final = final[cols_show]

        return final.head(1000)

    def quality_text(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "🧪 Qualidade de Dados\n\nSem dados no recorte atual."

        linhas = []
        linhas.append(f"- Linhas: {df.shape[0]}")
        linhas.append(f"- Colunas: {df.shape[1]}")

        nulos = df.isna().sum().sort_values(ascending=False).head(12)
        linhas.append("\nTop colunas com nulos:")
        for col, qtd in nulos.items():
            if qtd > 0:
                linhas.append(f"  • {col}: {int(qtd)}")

        if "ean" in df.columns:
            inv = int(df["ean"].astype(str).str.len().ne(13).sum())
            dup = int(df[df.duplicated(subset=["ean"], keep=False)]["ean"].nunique())
            linhas.append(f"\nEAN inválidos (len != 13): {inv}")
            linhas.append(f"EAN duplicados (distintos): {dup}")

        if "preco_unitario" in df.columns:
            out = int(compute_outlier_mask(df["preco_unitario"]).sum())
            linhas.append(f"\nOutliers preco_unitario (IQR): {out}")

        return "🧪 Qualidade de Dados (recorte atual)\n\n" + "\n".join(linhas)

    def insights_text(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "Sem dados suficientes para gerar insights."

        fat_liq, impacto = self.faturamento_liquido(df)
        fat_bruto = self.faturamento_bruto(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)
        mp = self.margem_pct(df)

        # metas
        st_fat, at_fat = self.semaforo(fat_liq, self.meta_fat_liq)
        st_ticket, at_ticket = self.semaforo(ticket, self.meta_ticket)
        st_vendas, at_vendas = self.semaforo(vendas, self.meta_vendas)
        st_margem, at_margem = ("neutral", 0.0)
        if mp is not None:
            st_margem, at_margem = self.semaforo(mp, self.meta_margem_pct)

        lines = []
        lines.append("Resumo Executivo (interpretação automática):")
        lines.append("")
        lines.append(f"- Faturamento líquido: {format_brl(fat_liq)} | Ating meta: {(at_fat*100):.1f}%")
        lines.append(f"- Faturamento bruto: {format_brl(fat_bruto)} | Impacto cancel/deneg: {format_brl(impacto)}")
        lines.append(f"- Vendas: {vendas} | Ticket médio: {format_brl(ticket)}")
        if mp is not None:
            lines.append(f"- Margem bruta: {(mp*100):.2f}%".replace(".", ","))
        else:
            lines.append("- Margem bruta: indisponível (custo_total não encontrado)")

        lines.append("")
        # recomendações estilo executivo
        if impacto > 0:
            lines.append("Pontos de atenção:")
            lines.append("• Existe impacto por documentos inválidos (cancel/deneg/inutil). Considere separar do faturamento de performance.")
        else:
            lines.append("Pontos de atenção:")
            lines.append("• Sem impacto relevante por status inválido no recorte atual.")

        if mp is not None and mp < 0.10:
            lines.append("• Margem baixa: revisar descontos, custo_total e mix de produtos.")
        if "ean" in df.columns:
            inv_ean = int(df["ean"].astype(str).str.len().ne(13).sum())
            if inv_ean > 0:
                lines.append(f"• EAN inválidos detectados: {inv_ean}. Isso prejudica rastreabilidade e análises.")

        # top 3 produtos e canal dominante
        if "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(3)
            if len(top) > 0:
                lines.append("")
                lines.append("Top 3 produtos por faturamento:")
                for p, v in top.items():
                    lines.append(f"• {p}: {format_brl(v)}")

        if "canal" in df.columns and "valor_total" in df.columns:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)
            if len(canal) > 0 and canal.sum() > 0:
                share = canal.iloc[0] / canal.sum()
                lines.append("")
                lines.append(f"Canal dominante: {canal.index[0]} ({(share*100):.1f}%)".replace(".", ","))

        return "\n".join(lines)

    # =========================================================
    # Update geral
    # =========================================================
    def atualizar_tudo(self):
        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        # tabela principal
        flag_out, flag_ean, flag_cancel = self.gerar_flags_tabela(df)
        self.model_base.update(df, flag_outlier=flag_out, flag_ean_invalid=flag_ean, flag_cancel=flag_cancel)
        self.lbl_linhas.setText(f"Linhas: {len(df):,}".replace(",", "."))

        # cards + comparativo + visuais
        self.update_kpis(df)
        self.update_comparativo(df)
        self.update_charts(df)

        # alertas + qualidade + insights
        self.update_alertas(df)
        self.lbl_quality.setText(self.quality_text(df))
        self.txt_insights.setPlainText(self.insights_text(df))

        # drilldown combos
        self.update_drilldown_values()
        self.update_drilldown()

    def update_kpis(self, df: pd.DataFrame):
        fat_liq, impacto = self.faturamento_liquido(df)
        vendas = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)
        itens = safe_int(df.shape[0]) if not df.empty else 0
        mp = self.margem_pct(df)

        # tendência mensal (fat líquido)
        serie_f = self.serie_mensal(df, liquido=True)
        d_abs, d_pct, last_m, prev_m = self.delta_last_month(serie_f)
        if d_pct is not None:
            arrow = "↑" if d_pct >= 0 else "↓"
            trend_f = f"{arrow} {(d_pct*100):.2f}% vs {prev_m} → {last_m}".replace(".", ",")
        else:
            trend_f = "— (tendência indisponível)"

        status_f, at_f = self.semaforo(fat_liq, self.meta_fat_liq)
        meta_f = f"Meta: {format_brl(self.meta_fat_liq)} | Ating: {(at_f*100):.1f}%"
        self.kpi_fat_liq.set_state(format_brl(fat_liq), trend_f, meta_f, status_f)

        # margem
        if mp is None:
            self.kpi_margem.set_state("—", "—", "Meta: — | Ating: —", "neutral")
        else:
            status_m, at_m = self.semaforo(mp, self.meta_margem_pct)
            meta_m = f"Meta: {(self.meta_margem_pct*100):.1f}% | Ating: {(at_m*100):.1f}%".replace(".", ",")
            self.kpi_margem.set_state(f"{(mp*100):.2f}%".replace(".", ","), "—", meta_m, status_m)

        # ticket
        status_t, at_t = self.semaforo(ticket, self.meta_ticket)
        meta_t = f"Meta: {format_brl(self.meta_ticket)} | Ating: {(at_t*100):.1f}%"
        self.kpi_ticket.set_state(format_brl(ticket), "—", meta_t, status_t)

        # vendas
        status_v, at_v = self.semaforo(vendas, self.meta_vendas)
        meta_v = f"Meta: {self.meta_vendas} | Ating: {(at_v*100):.1f}%"
        self.kpi_vendas.set_state(str(vendas), "—", meta_v, status_v)

        # itens
        self.kpi_itens.set_state(str(itens), "—", "Meta: — | Ating: —", "neutral")

        # impacto
        self.kpi_impacto.set_state(format_brl(impacto), "—", "Meta: — | Ating: —", "neutral")

    def update_comparativo(self, df: pd.DataFrame):
        serie_f = self.serie_mensal(df, liquido=True)
        if serie_f is None or len(serie_f) < 2:
            self.lbl_comp_period.setText("Período: — (precisa de ≥ 2 meses)")
            self.lbl_comp_fat.setText("Fat. Líq: —")
            self.lbl_comp_ticket.setText("Ticket: —")
            self.lbl_comp_vendas.setText("Vendas: —")
            self.lbl_comp_margem.setText("Margem: —")
            return

        last_m = str(serie_f.index[-1])
        prev_m = str(serie_f.index[-2])

        # recortes por mês
        df_tmp = df.copy()
        if "data" not in df_tmp.columns:
            return

        df_tmp["mes"] = df_tmp["data"].dt.to_period("M")
        df_last = df_tmp[df_tmp["mes"] == serie_f.index[-1]].copy()
        df_prev = df_tmp[df_tmp["mes"] == serie_f.index[-2]].copy()

        fat_last, _ = self.faturamento_liquido(df_last)
        fat_prev, _ = self.faturamento_liquido(df_prev)

        ticket_last = self.ticket_medio(df_last)
        ticket_prev = self.ticket_medio(df_prev)

        vendas_last = self.qtd_vendas(df_last)
        vendas_prev = self.qtd_vendas(df_prev)

        mp_last = self.margem_pct(df_last)
        mp_prev = self.margem_pct(df_prev)

        def delta_str(a, b, money=False):
            d = a - b
            pct = (d / b) if b != 0 else None
            arrow = "↑" if d >= 0 else "↓"
            if money:
                base = f"{format_brl(a)} ({arrow} {format_brl(abs(d))}"
            else:
                base = f"{a} ({arrow} {abs(d)}"

            if pct is not None:
                base += f" | {(abs(pct)*100):.1f}%"
            base += ")"
            return base.replace(".", ",")

        self.lbl_comp_period.setText(f"Período: {prev_m} → {last_m}")
        self.lbl_comp_fat.setText(f"Fat. Líq: {delta_str(fat_last, fat_prev, money=True)}")
        self.lbl_comp_ticket.setText(f"Ticket: {delta_str(ticket_last, ticket_prev, money=True)}")
        self.lbl_comp_vendas.setText(f"Vendas: {delta_str(vendas_last, vendas_prev, money=False)}")

        if mp_last is None or mp_prev is None:
            self.lbl_comp_margem.setText("Margem: — (sem custo_total)")
        else:
            self.lbl_comp_margem.setText(f"Margem: {delta_str(round(mp_last*100,2), round(mp_prev*100,2), money=False)}%")

    def update_charts(self, df: pd.DataFrame):
        # mensal (líquido)
        self.fig_mes.clear()
        ax1 = self.fig_mes.add_subplot(111)
        ax1.set_title("Faturamento Líquido Mensal", fontsize=10, fontweight="bold")
        serie = self.serie_mensal(df, liquido=True)
        if len(serie) > 0:
            x = [str(p) for p in serie.index]
            ax1.plot(x, serie.values, marker="o")
            ax1.tick_params(axis="x", rotation=45, labelsize=8)
        else:
            ax1.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_mes.tight_layout()
        self.canvas_mes.draw()

        # top produtos
        self.fig_top.clear()
        ax2 = self.fig_top.add_subplot(111)
        ax2.set_title("Top Produtos", fontsize=10, fontweight="bold")
        if "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(top) > 0:
                ax2.bar(top.index.astype(str), top.values)
                ax2.tick_params(axis="x", rotation=45, labelsize=8)
            else:
                ax2.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax2.text(0.5, 0.5, "Coluna produto não encontrada", ha="center", va="center")
        self.fig_top.tight_layout()
        self.canvas_top.draw()

        # canal barras + donut
        canal = None
        if "canal" in df.columns and "valor_total" in df.columns:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)

        self.fig_canal.clear()
        ax3 = self.fig_canal.add_subplot(111)
        ax3.set_title("Faturamento por Canal", fontsize=10, fontweight="bold")
        if canal is not None and len(canal) > 0:
            ax3.bar(canal.index.astype(str), canal.values)
            ax3.tick_params(axis="x", rotation=0, labelsize=8)
        else:
            ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        self.fig_canal.tight_layout()
        self.canvas_canal.draw()

        self.fig_donut.clear()
        ax4 = self.fig_donut.add_subplot(111)
        if canal is not None and len(canal) > 0:
            s = canal.head(6)
            donut(ax4, s.index.astype(str).tolist(), s.values.tolist(), title="Participação por Canal")
        else:
            ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_donut.tight_layout()
        self.canvas_donut.draw()

    def update_alertas(self, df: pd.DataFrame):
        alerts = self.gerar_alertas(df)
        self.model_alertas.update(alerts)

        if alerts.empty:
            self.lbl_alertas.setText("✅ Nenhum alerta relevante no recorte atual.")
            return

        resumo = alerts["tipo_alerta"].value_counts()
        texto = "🚨 Alertas (recorte atual)\n\n" + "\n".join([f"- {k}: {int(v)}" for k, v in resumo.items()])
        texto += "\n\nObs.: Linhas com alerta aparecem destacadas na aba Tabela."
        self.lbl_alertas.setText(texto)

    # =========================================================
    # Drilldown update
    # =========================================================
    def update_drilldown_values(self):
        if self.base.empty:
            return
        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        dim = self.combo_dim.currentText()
        if dim == "Canal":
            col = "canal"
        elif dim == "UF":
            col = "uf_destino"
        else:
            col = "categoria"

        self.combo_val.blockSignals(True)
        self.combo_val.clear()

        if col in df.columns:
            valores = sorted(df[col].dropna().unique().tolist())
            self.combo_val.addItem("Todos")
            for v in valores:
                self.combo_val.addItem(str(v))
        else:
            self.combo_val.addItem("Indisponível")

        self.combo_val.blockSignals(False)

    def update_drilldown(self):
        if self.base.empty:
            return

        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        dim = self.combo_dim.currentText()
        if dim == "Canal":
            col = "canal"
        elif dim == "UF":
            col = "uf_destino"
        else:
            col = "categoria"

        val = self.combo_val.currentText()

        if col not in df.columns or val == "Indisponível":
            self.lbl_drill_info.setText("Dimensão indisponível na base.")
            self.model_drill.update(pd.DataFrame())
            return

        df_drill = df.copy()
        if val != "Todos":
            df_drill = df_drill[df_drill[col].astype(str) == str(val)]

        # tabela drill
        self.model_drill.update(df_drill.head(500))

        # gráficos drill
        self.fig_drill_top.clear()
        ax1 = self.fig_drill_top.add_subplot(111)
        ax1.set_title("Top Produtos (drilldown)", fontsize=10, fontweight="bold")
        if "produto" in df_drill.columns and "valor_total" in df_drill.columns and not df_drill.empty:
            top = df_drill.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(top) > 0:
                ax1.bar(top.index.astype(str), top.values)
                ax1.tick_params(axis="x", rotation=45, labelsize=8)
            else:
                ax1.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax1.text(0.5, 0.5, "Sem colunas necessárias", ha="center", va="center")
        self.fig_drill_top.tight_layout()
        self.canvas_drill_top.draw()

        self.fig_drill_mes.clear()
        ax2 = self.fig_drill_mes.add_subplot(111)
        ax2.set_title("Faturamento mensal (drilldown)", fontsize=10, fontweight="bold")
        serie = self.serie_mensal(df_drill, liquido=True)
        if len(serie) > 0:
            x = [str(p) for p in serie.index]
            ax2.plot(x, serie.values, marker="o")
            ax2.tick_params(axis="x", rotation=45, labelsize=8)
        else:
            ax2.text(0.5, 0.5, "Sem série", ha="center", va="center")
        self.fig_drill_mes.tight_layout()
        self.canvas_drill_mes.draw()

        self.lbl_drill_info.setText(f"Drilldown: {dim} = {val} | Linhas: {len(df_drill):,}".replace(",", "."))

    # =========================================================
    # Export Excel PRO
    # =========================================================
    def on_exportar_excel(self):
        if self.base.empty:
            return
        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Excel PRO",
            str(self.base_dir / "relatorio_dashboard_v62_pro.xlsx"),
            "Excel (*.xlsx)"
        )
        if not arquivo:
            return

        try:
            fat_liq, impacto = self.faturamento_liquido(df)
            fat_bruto = self.faturamento_bruto(df)
            vendas = self.qtd_vendas(df)
            ticket = self.ticket_medio(df)
            mp = self.margem_pct(df)

            resumo_exec = pd.DataFrame([{
                "faturamento_liquido": fat_liq,
                "faturamento_bruto": fat_bruto,
                "impacto_cancel_deneg": impacto,
                "ticket_medio": ticket,
                "qtd_vendas": vendas,
                "qtd_itens": int(df.shape[0]),
                "margem_bruta_pct": mp,
                "meta_fat_liq": self.meta_fat_liq,
                "meta_ticket": self.meta_ticket,
                "meta_vendas": self.meta_vendas,
                "meta_margem_pct": self.meta_margem_pct
            }])

            mensal = self.serie_mensal(df, liquido=True).reset_index()
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

            alerts = self.gerar_alertas(df)
            quality = pd.DataFrame({"texto": [self.quality_text(df)]})
            insights = pd.DataFrame({"insights": [self.insights_text(df)]})

            with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
                resumo_exec.to_excel(writer, sheet_name="Resumo_Executivo", index=False)
                df.to_excel(writer, sheet_name="Base_Filtrada", index=False)
                (mensal if not mensal.empty else pd.DataFrame({"info": ["Sem série mensal"]})).to_excel(writer, sheet_name="Faturamento_Mensal", index=False)
                (top if not top.empty else pd.DataFrame({"info": ["Sem top produtos"]})).to_excel(writer, sheet_name="Top_Produtos", index=False)
                (canal if not canal.empty else pd.DataFrame({"info": ["Sem canal"]})).to_excel(writer, sheet_name="Faturamento_Canal", index=False)
                (alerts if not alerts.empty else pd.DataFrame({"info": ["Sem alertas"]})).to_excel(writer, sheet_name="Alertas", index=False)
                quality.to_excel(writer, sheet_name="Qualidade", index=False)
                insights.to_excel(writer, sheet_name="Insights", index=False)

            QMessageBox.information(self, "Excel", f"✅ Excel PRO salvo:\n{arquivo}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    # =========================================================
    # Export PDF Executivo (Power BI)
    # =========================================================
    def on_exportar_pdf(self):
        if self.base.empty:
            return
        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar PDF Executivo",
            str(self.base_dir / "relatorio_executivo_v62.pdf"),
            "PDF (*.pdf)"
        )
        if not arquivo:
            return

        try:
            # gerar imagens temporárias dos gráficos
            tmp_dir = Path(tempfile.mkdtemp())

            img1 = tmp_dir / "mensal.png"
            img2 = tmp_dir / "top.png"
            img3 = tmp_dir / "canal.png"
            img4 = tmp_dir / "donut.png"

            self.fig_mes.savefig(img1, dpi=160, bbox_inches="tight")
            self.fig_top.savefig(img2, dpi=160, bbox_inches="tight")
            self.fig_canal.savefig(img3, dpi=160, bbox_inches="tight")
            self.fig_donut.savefig(img4, dpi=160, bbox_inches="tight")

            # KPIs
            fat_liq, impacto = self.faturamento_liquido(df)
            fat_bruto = self.faturamento_bruto(df)
            vendas = self.qtd_vendas(df)
            ticket = self.ticket_medio(df)
            mp = self.margem_pct(df)

            st_f, at_f = self.semaforo(fat_liq, self.meta_fat_liq)
            st_t, at_t = self.semaforo(ticket, self.meta_ticket)
            st_v, at_v = self.semaforo(vendas, self.meta_vendas)
            st_m, at_m = ("neutral", 0.0)
            if mp is not None:
                st_m, at_m = self.semaforo(mp, self.meta_margem_pct)

            # PDF
            c = pdf_canvas.Canvas(arquivo, pagesize=A4)
            width, height = A4

            # Cabeçalho
            c.setFillColor(colors.HexColor("#1F4E79"))
            c.rect(0, height - 2.2*cm, width, 2.2*cm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(1.2*cm, height - 1.35*cm, "Relatório Executivo - Dashboard v6.2 PRO (Power BI Style)")
            c.setFont("Helvetica", 10)
            c.drawString(1.2*cm, height - 1.9*cm, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

            # Corpo
            y = height - 3.0*cm
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(1.2*cm, y, "KPIs do Recorte Atual")
            y -= 0.6*cm

            # tabela KPI
            c.setFont("Helvetica", 10)
            kpi_rows = [
                ("Faturamento Líquido", format_brl(fat_liq), f"Meta: {format_brl(self.meta_fat_liq)} | Ating: {at_f*100:.1f}%", st_f),
                ("Faturamento Bruto", format_brl(fat_bruto), "—", "neutral"),
                ("Ticket Médio", format_brl(ticket), f"Meta: {format_brl(self.meta_ticket)} | Ating: {at_t*100:.1f}%", st_t),
                ("Qtd Vendas", f"{vendas}", f"Meta: {self.meta_vendas} | Ating: {at_v*100:.1f}%", st_v),
                ("Margem Bruta", ("—" if mp is None else f"{mp*100:.2f}%".replace(".", ",")),
                 (f"Meta: {self.meta_margem_pct*100:.1f}% | Ating: {at_m*100:.1f}%" if mp is not None else "Sem custo_total"), st_m),
                ("Impacto Cancel/Deneg", format_brl(impacto), "—", "neutral"),
            ]

            def status_color(st):
                if st == "green":
                    return colors.HexColor("#1B9E77")
                if st == "yellow":
                    return colors.HexColor("#F59E0B")
                if st == "red":
                    return colors.HexColor("#D62728")
                return colors.HexColor("#9CA3AF")

            x0 = 1.2*cm
            col1 = 5.2*cm
            col2 = 4.2*cm
            col3 = 8.0*cm

            for nome, valor, meta, st in kpi_rows:
                c.setFillColor(status_color(st))
                c.setFont("Helvetica-Bold", 10)
                c.drawString(x0, y, "●")
                c.setFillColor(colors.black)
                c.drawString(x0 + 0.4*cm, y, nome)

                c.setFont("Helvetica-Bold", 10)
                c.drawString(x0 + col1, y, valor)

                c.setFont("Helvetica", 9)
                c.setFillColor(colors.HexColor("#374151"))
                c.drawString(x0 + col1 + col2, y, meta)

                c.setFillColor(colors.black)
                y -= 0.55*cm

            y -= 0.2*cm
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(1.2*cm, y, "Visuais (Power BI)")
            y -= 0.5*cm

            # Inserir imagens (2 por página)
            img_w = (width - 3.0*cm) / 2
            img_h = 6.2*cm

            c.drawImage(str(img1), 1.2*cm, y - img_h, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')
            c.drawImage(str(img2), 1.2*cm + img_w + 0.6*cm, y - img_h, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')
            y -= img_h + 0.7*cm

            c.drawImage(str(img3), 1.2*cm, y - img_h, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')
            c.drawImage(str(img4), 1.2*cm + img_w + 0.6*cm, y - img_h, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')
            y -= img_h + 0.7*cm

            # Insights
            c.setFont("Helvetica-Bold", 12)
            c.drawString(1.2*cm, y, "Insights Automáticos")
            y -= 0.5*cm

            c.setFont("Helvetica", 9)
            insight = self.insights_text(df)
            for line in insight.split("\n")[:18]:
                c.drawString(1.2*cm, y, line[:120])
                y -= 0.38*cm
                if y < 2.0*cm:
                    c.showPage()
                    y = height - 2.0*cm
                    c.setFont("Helvetica", 9)

            c.save()
            QMessageBox.information(self, "PDF", f"✅ PDF Executivo salvo:\n{arquivo}")

        except Exception as e:
            QMessageBox.critical(self, "Erro PDF", str(e))


# =========================================================
# Main
# =========================================================
def main():
    app = QApplication(sys.argv)
    w = DashboardV62()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()