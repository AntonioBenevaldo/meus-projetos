import sys
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTabWidget, QTableView, QMessageBox,
    QComboBox, QGroupBox, QDateEdit,
    QFrame, QGridLayout, QSizePolicy, QTextEdit
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# =========================================================
# Utils
# =========================================================
def format_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def safe_float(x) -> float:
    try:
        if pd.isna(x):
            return 0.0
        return float(x)
    except Exception:
        return 0.0


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


def is_invalid_status(df: pd.DataFrame) -> pd.Series:
    """Retorna máscara para status inválido (cancel/deneg/inutil)."""
    if "status" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    st = df["status"].astype(str).str.upper()
    return st.str.contains("CANCEL") | st.str.contains("DENEG") | st.str.contains("INUTIL")


def month_label(period) -> str:
    try:
        return str(period)
    except Exception:
        return ""


# =========================================================
# Table Model com destaque (tipo Power BI)
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

        # Destaque de linha (suspeitas)
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
# KPI Card com tendência (Power BI style)
# =========================================================
class KpiCard(QFrame):
    def __init__(self, titulo: str):
        super().__init__()
        self.setObjectName("KpiCard")
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._accent = "#1F4E79"
        self._mode = "neutral"  # up/down/neutral

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setStyleSheet("font-size: 12px; color: #5A5A5A; font-weight: 700;")

        self.lbl_valor = QLabel("-")
        self.lbl_valor.setStyleSheet("font-size: 22px; font-weight: 900; color: #111111;")

        self.lbl_trend = QLabel("—")
        self.lbl_trend.setStyleSheet("font-size: 11px; color: #6B7280; font-weight: 600;")

        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_valor)
        layout.addWidget(self.lbl_trend)

        self.apply_style()

    def apply_style(self):
        border = self._accent
        if self._mode == "up":
            border = "#1B9E77"   # verde
        elif self._mode == "down":
            border = "#D62728"   # vermelho

        self.setStyleSheet(f"""
            QFrame#KpiCard {{
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-left: 6px solid {border};
                border-radius: 14px;
            }}
        """)

    def set_value(self, valor: str, trend_text: str = "—", trend_mode: str = "neutral"):
        self.lbl_valor.setText(valor)
        self.lbl_trend.setText(trend_text)
        self._mode = trend_mode
        self.apply_style()


# =========================================================
# Dashboard v6.1 (Mais Power BI)
# =========================================================
class DashboardV61(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard v6.1 - Power BI Style | Portfólio Premium")
        self.resize(1550, 880)

        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "dados"

        self.base = pd.DataFrame()
        self.base_filtrada = pd.DataFrame()

        # -------------------------
        # Layout raiz (SIDEBAR + CONTEÚDO)
        # -------------------------
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # SIDEBAR
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(330)
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

        lbl_logo = QLabel("Painel de Filtros (Slicers)")
        lbl_logo.setStyleSheet("font-size: 14px; font-weight: 900; color: #111111;")
        sb.addWidget(lbl_logo)

        self.lbl_status = QLabel("Status: aguardando...")
        self.lbl_status.setStyleSheet("font-weight:700; color:#1F4E79;")
        sb.addWidget(self.lbl_status)

        # Botões
        btns = QHBoxLayout()
        self.btn_carregar = QPushButton("Carregar")
        self.btn_carregar.clicked.connect(self.on_carregar)

        self.btn_escolher = QPushButton("Pasta...")
        self.btn_escolher.clicked.connect(self.on_escolher_pasta)

        btns.addWidget(self.btn_carregar)
        btns.addWidget(self.btn_escolher)
        sb.addLayout(btns)

        btns2 = QHBoxLayout()
        self.btn_limpar = QPushButton("Limpar")
        self.btn_limpar.clicked.connect(self.on_limpar)
        self.btn_limpar.setEnabled(False)

        self.btn_exportar = QPushButton("Export Excel")
        self.btn_exportar.clicked.connect(self.on_exportar)
        self.btn_exportar.setEnabled(False)

        btns2.addWidget(self.btn_limpar)
        btns2.addWidget(self.btn_exportar)
        sb.addLayout(btns2)

        # Filtros (slicers)
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

        def box(title, widget):
            b = QGroupBox(title)
            b.setStyleSheet("QGroupBox{font-weight:800;}")
            lay = QVBoxLayout(b)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.addWidget(widget)
            return b

        sb.addWidget(box("Texto", self.input_busca))
        sb.addWidget(box("UF", self.combo_uf))
        sb.addWidget(box("Canal", self.combo_canal))
        sb.addWidget(box("Categoria", self.combo_categoria))
        sb.addWidget(box("Status", self.combo_status))

        periodo = QGroupBox("Período")
        periodo.setStyleSheet("QGroupBox{font-weight:800;}")
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

        sb.addStretch()

        # CONTEÚDO PRINCIPAL (Tabs)
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

        header = QLabel("Resumo Executivo (Power BI Style) — Dinâmico com Filtros")
        header.setStyleSheet("font-size: 15px; font-weight: 900; color: #111111;")
        ct.addWidget(header)

        self.tabs = QTabWidget()
        ct.addWidget(self.tabs)

        # Aba Resumo Executivo
        self.tab_exec = QWidget()
        self.tabs.addTab(self.tab_exec, "Resumo Executivo")
        self.build_exec_tab()

        # Aba Tabela
        self.tab_tabela = QWidget()
        self.tabs.addTab(self.tab_tabela, "Tabela")
        t1 = QVBoxLayout(self.tab_tabela)
        self.table_base = QTableView()
        self.table_base.setSortingEnabled(True)
        self.model_base = PandasTableModel(pd.DataFrame())
        self.table_base.setModel(self.model_base)
        t1.addWidget(self.table_base)

        # Aba Alertas
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

        # Aba Qualidade
        self.tab_quality = QWidget()
        self.tabs.addTab(self.tab_quality, "Qualidade de Dados")
        tq = QVBoxLayout(self.tab_quality)
        self.lbl_quality = QLabel("Carregue os dados para ver a auditoria.")
        self.lbl_quality.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tq.addWidget(self.lbl_quality)

        root.addWidget(self.sidebar)
        root.addWidget(self.content, 1)

        # Tema (mais Power BI)
        self.apply_theme()

        # Autoload
        if self.data_dir.exists():
            self.on_carregar()

    def apply_theme(self):
        self.setStyleSheet("""
            QPushButton {
                background: #1F4E79;
                color: white;
                border: none;
                padding: 7px 10px;
                border-radius: 10px;
                font-weight: 800;
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
                font-weight: 600;
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
                font-weight: 800;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-bottom: none;
            }
        """)

    # =========================================================
    # Exec Tab (cards + visuais + insights)
    # =========================================================
    def build_exec_tab(self):
        layout = QVBoxLayout(self.tab_exec)
        layout.setSpacing(12)

        # Cards
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.card_fat_liq = KpiCard("Faturamento Líquido")
        self.card_fat_bruto = KpiCard("Faturamento Bruto")
        self.card_ticket = KpiCard("Ticket Médio")
        self.card_vendas = KpiCard("Qtd Vendas")
        self.card_itens = KpiCard("Qtd Itens")
        self.card_margem = KpiCard("Margem Bruta")
        self.card_impacto = KpiCard("Impacto Cancel/Deneg")

        grid.addWidget(self.card_fat_liq, 0, 0)
        grid.addWidget(self.card_fat_bruto, 0, 1)
        grid.addWidget(self.card_ticket, 0, 2)
        grid.addWidget(self.card_vendas, 1, 0)
        grid.addWidget(self.card_itens, 1, 1)
        grid.addWidget(self.card_margem, 1, 2)
        grid.addWidget(self.card_impacto, 2, 0, 1, 3)

        layout.addLayout(grid)

        # Visuais
        vis = QGridLayout()
        vis.setHorizontalSpacing(12)
        vis.setVerticalSpacing(12)

        self.frame_mes, self.canvas_mes, self.fig_mes = self.make_chart("Faturamento Mensal (linha)")
        self.frame_top, self.canvas_top, self.fig_top = self.make_chart("Top Produtos (barras)")
        self.frame_canal, self.canvas_canal, self.fig_canal = self.make_chart("Faturamento por Canal (barras)")
        self.frame_donut, self.canvas_donut, self.fig_donut = self.make_chart("Participação por Canal (donut)")

        vis.addWidget(self.frame_mes, 0, 0)
        vis.addWidget(self.frame_top, 0, 1)
        vis.addWidget(self.frame_canal, 1, 0)
        vis.addWidget(self.frame_donut, 1, 1)

        layout.addLayout(vis)

        # Insights
        self.txt_insights = QTextEdit()
        self.txt_insights.setReadOnly(True)
        self.txt_insights.setMinimumHeight(140)
        self.txt_insights.setStyleSheet("""
            QTextEdit {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-radius: 14px;
                padding: 10px;
                font-size: 12px;
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
    # Load
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
            self.btn_exportar.setEnabled(True)

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

        self.combo_uf.addItem("Todas as UFs")
        self.combo_canal.addItem("Todos os Canais")
        self.combo_categoria.addItem("Todas as Categorias")
        self.combo_status.addItem("Todos os Status")

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
    # Filters
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

        # UF
        uf_sel = self.combo_uf.currentText()
        if uf_sel != "Todas as UFs" and "uf_destino" in df.columns:
            df = df[df["uf_destino"] == uf_sel]

        # Canal
        canal_sel = self.combo_canal.currentText()
        if canal_sel != "Todos os Canais" and "canal" in df.columns:
            df = df[df["canal"] == canal_sel]

        # Categoria
        cat_sel = self.combo_categoria.currentText()
        if cat_sel != "Todas as Categorias" and "categoria" in df.columns:
            df = df[df["categoria"] == cat_sel]

        # Status
        st_sel = self.combo_status.currentText()
        if st_sel != "Todos os Status" and "status" in df.columns:
            df = df[df["status"] == st_sel]

        self.base_filtrada = df.copy()
        self.atualizar_tudo()

    # =========================================================
    # Metrics / Trends
    # =========================================================
    def faturamento_bruto(self, df: pd.DataFrame) -> float:
        if "valor_total" not in df.columns:
            return 0.0
        return safe_float(df["valor_total"].sum())

    def faturamento_liquido(self, df: pd.DataFrame) -> tuple[float, float]:
        """Retorna (fat_liq, impacto)."""
        if "valor_total" not in df.columns:
            return 0.0, 0.0
        inv = is_invalid_status(df)
        fat_bruto = safe_float(df["valor_total"].sum())
        fat_liq = safe_float(df.loc[~inv, "valor_total"].sum())
        return fat_liq, (fat_bruto - fat_liq)

    def ticket_medio(self, df: pd.DataFrame) -> float:
        if df.empty or "valor_total" not in df.columns:
            return 0.0
        if "venda_id" in df.columns:
            s = df.groupby("venda_id")["valor_total"].sum()
            return safe_float(s.mean())
        return safe_float(df["valor_total"].mean())

    def qtd_vendas(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        if "venda_id" in df.columns:
            return int(df["venda_id"].nunique())
        return int(df.shape[0])

    def margem_pct(self, df: pd.DataFrame) -> float | None:
        if df.empty or "valor_total" not in df.columns or "custo_total" not in df.columns:
            return None
        fat = safe_float(df["valor_total"].sum())
        custo = safe_float(df["custo_total"].sum())
        if fat == 0:
            return 0.0
        return (fat - custo) / fat

    def series_mensal(self, df: pd.DataFrame, col_val="valor_total", liquido=False) -> pd.Series:
        if df.empty or "data" not in df.columns or col_val not in df.columns:
            return pd.Series(dtype=float)
        tmp = df.dropna(subset=["data"]).copy()
        if tmp.empty:
            return pd.Series(dtype=float)

        if liquido:
            inv = is_invalid_status(tmp)
            tmp = tmp.loc[~inv].copy()

        return tmp.groupby(tmp["data"].dt.to_period("M"))[col_val].sum().sort_index()

    def vendas_mensal(self, df: pd.DataFrame) -> pd.Series:
        if df.empty or "data" not in df.columns:
            return pd.Series(dtype=float)
        tmp = df.dropna(subset=["data"]).copy()
        if tmp.empty:
            return pd.Series(dtype=float)
        if "venda_id" not in tmp.columns:
            return tmp.groupby(tmp["data"].dt.to_period("M")).size()
        return tmp.groupby(tmp["data"].dt.to_period("M"))["venda_id"].nunique().sort_index()

    def ticket_mensal(self, df: pd.DataFrame) -> pd.Series:
        if df.empty or "data" not in df.columns or "valor_total" not in df.columns:
            return pd.Series(dtype=float)
        tmp = df.dropna(subset=["data"]).copy()
        if tmp.empty:
            return pd.Series(dtype=float)

        if "venda_id" in tmp.columns:
            tmp2 = tmp.groupby(["venda_id", tmp["data"].dt.to_period("M")])["valor_total"].sum().reset_index()
            tmp2.columns = ["venda_id", "mes", "valor_total"]
            return tmp2.groupby("mes")["valor_total"].mean().sort_index()

        return tmp.groupby(tmp["data"].dt.to_period("M"))["valor_total"].mean().sort_index()

    def delta_last_month(self, serie: pd.Series) -> tuple[float | None, float | None, str, str]:
        """
        Retorna (delta_abs, delta_pct, ultimo_mes, mes_anterior)
        """
        if serie is None or len(serie) < 2:
            return None, None, "", ""
        serie = serie.dropna()
        if len(serie) < 2:
            return None, None, "", ""

        last = serie.iloc[-1]
        prev = serie.iloc[-2]
        delta_abs = safe_float(last - prev)
        delta_pct = None
        if safe_float(prev) != 0:
            delta_pct = safe_float((last - prev) / prev)

        return delta_abs, delta_pct, month_label(serie.index[-1]), month_label(serie.index[-2])

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

        flag_cancel = is_invalid_status(df)

        return flag_out, flag_ean, flag_cancel

    def gerar_alertas(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        alerts = []

        # status
        inv = is_invalid_status(df)
        if inv.any():
            a = df[inv].copy()
            a["tipo_alerta"] = "STATUS_CANCEL_DENEG"
            alerts.append(a)

        # EAN inválido / duplicado
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

        # outlier preço
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
        if df.empty or "valor_total" not in df.columns:
            return "Sem dados suficientes para gerar insights."

        fat_bruto = self.faturamento_bruto(df)
        fat_liq, impacto = self.faturamento_liquido(df)
        qtdv = self.qtd_vendas(df)
        ticket = self.ticket_medio(df)

        top_prod = pd.Series(dtype=float)
        if "produto" in df.columns:
            top_prod = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(5)

        canal = pd.Series(dtype=float)
        if "canal" in df.columns:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)

        linhas = []
        linhas.append("Resumo interpretável do recorte atual:")
        linhas.append("")
        linhas.append(f"- Faturamento líquido: {format_brl(fat_liq)}")
        linhas.append(f"- Faturamento bruto: {format_brl(fat_bruto)}")
        linhas.append(f"- Impacto por cancel/deneg: {format_brl(impacto)}")
        linhas.append(f"- Qtd vendas: {qtdv} | Ticket médio: {format_brl(ticket)}")

        mp = self.margem_pct(df)
        if mp is not None:
            linhas.append(f"- Margem bruta: {(mp*100):.2f}%".replace(".", ","))
            if mp < 0.10:
                linhas.append("  • Margem baixa: revise descontos e custos por produto/categoria.")
            elif mp > 0.30:
                linhas.append("  • Margem alta: ótimo, confirme consistência do custo_total.")

        linhas.append("")
        if len(top_prod) > 0:
            linhas.append("Top produtos (faturamento):")
            for p, v in top_prod.items():
                linhas.append(f"  • {p}: {format_brl(v)}")

        if len(canal) > 0:
            total = canal.sum() if canal.sum() != 0 else 1
            canal_top = canal.index[0]
            share = safe_float(canal.iloc[0] / total)
            linhas.append("")
            linhas.append(f"Canal dominante: {canal_top} ({(share*100):.2f}%)".replace(".", ","))
            if share > 0.60:
                linhas.append("  • Dependência alta de 1 canal: considere diversificação.")

        alerts = self.gerar_alertas(df)
        if not alerts.empty:
            vc = alerts["tipo_alerta"].value_counts()
            linhas.append("")
            linhas.append("Alertas detectados:")
            for t, v in vc.items():
                linhas.append(f"  • {t}: {int(v)} ocorrências")
            linhas.append("Sugestão: corrija inconsistências antes de modelagem/ML.")

        return "\n".join(linhas)

    # =========================================================
    # Update UI
    # =========================================================
    def atualizar_tudo(self):
        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        flag_out, flag_ean, flag_cancel = self.gerar_flags_tabela(df)
        self.model_base.update(df, flag_outlier=flag_out, flag_ean_invalid=flag_ean, flag_cancel=flag_cancel)

        self.lbl_linhas.setText(f"Linhas: {len(df):,}".replace(",", "."))

        self.update_cards(df)
        self.update_charts(df)
        self.update_alertas(df)
        self.lbl_quality.setText(self.quality_text(df))
        self.txt_insights.setPlainText(self.insights_text(df))

    def update_cards(self, df: pd.DataFrame):
        fat_bruto = self.faturamento_bruto(df)
        fat_liq, impacto = self.faturamento_liquido(df)
        ticket = self.ticket_medio(df)
        vendas = self.qtd_vendas(df)
        itens = int(df.shape[0]) if not df.empty else 0
        mp = self.margem_pct(df)

        # tendências (vs mês anterior)
        serie_liq = self.series_mensal(df, liquido=True)
        d_abs, d_pct, last_m, prev_m = self.delta_last_month(serie_liq)
        if d_pct is not None:
            arrow = "↑" if d_pct >= 0 else "↓"
            mode = "up" if d_pct >= 0 else "down"
            trend_text = f"{arrow} {(d_pct*100):.2f}% vs {prev_m} → {last_m}".replace(".", ",")
        else:
            mode = "neutral"
            trend_text = "— tendência indisponível (poucos meses)"

        self.card_fat_liq.set_value(format_brl(fat_liq), trend_text, mode)

        # bruto
        serie_bruto = self.series_mensal(df, liquido=False)
        d_abs2, d_pct2, last_m2, prev_m2 = self.delta_last_month(serie_bruto)
        if d_pct2 is not None:
            arrow2 = "↑" if d_pct2 >= 0 else "↓"
            mode2 = "up" if d_pct2 >= 0 else "down"
            t2 = f"{arrow2} {(d_pct2*100):.2f}% vs {prev_m2} → {last_m2}".replace(".", ",")
        else:
            mode2 = "neutral"
            t2 = "—"

        self.card_fat_bruto.set_value(format_brl(fat_bruto), t2, mode2)

        # ticket
        serie_ticket = self.ticket_mensal(df)
        d_abst, d_pctt, last_mt, prev_mt = self.delta_last_month(serie_ticket)
        if d_pctt is not None:
            a = "↑" if d_pctt >= 0 else "↓"
            m = "up" if d_pctt >= 0 else "down"
            tt = f"{a} {(d_pctt*100):.2f}% vs {prev_mt} → {last_mt}".replace(".", ",")
        else:
            m = "neutral"
            tt = "—"
        self.card_ticket.set_value(format_brl(ticket), tt, m)

        # vendas
        serie_v = self.vendas_mensal(df)
        d_absv, d_pctv, last_mv, prev_mv = self.delta_last_month(serie_v)
        if d_pctv is not None:
            a = "↑" if d_pctv >= 0 else "↓"
            m = "up" if d_pctv >= 0 else "down"
            tv = f"{a} {(d_pctv*100):.2f}% vs {prev_mv} → {last_mv}".replace(".", ",")
        else:
            m = "neutral"
            tv = "—"
        self.card_vendas.set_value(str(vendas), tv, m)

        # itens
        self.card_itens.set_value(str(itens), "itens no recorte", "neutral")

        # margem
        if mp is None:
            self.card_margem.set_value("—", "necessário custo_total", "neutral")
        else:
            self.card_margem.set_value(f"{(mp*100):.2f}%".replace(".", ","), "lucro bruto / faturamento", "neutral")

        # impacto
        self.card_impacto.set_value(format_brl(impacto), "perdas por status inválido", "neutral")

    def update_charts(self, df: pd.DataFrame):
        # mensal
        self.fig_mes.clear()
        ax = self.fig_mes.add_subplot(111)
        serie = self.series_mensal(df, liquido=True)
        ax.set_title("Faturamento Líquido Mensal", fontsize=10, fontweight="bold")
        if len(serie) > 0:
            x = [str(p) for p in serie.index]
            ax.plot(x, serie.values, marker="o")
            ax.tick_params(axis="x", rotation=45, labelsize=8)
        else:
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        self.fig_mes.tight_layout()
        self.canvas_mes.draw()

        # top produtos
        self.fig_top.clear()
        ax2 = self.fig_top.add_subplot(111)
        ax2.set_title("Top 10 Produtos", fontsize=10, fontweight="bold")
        if "produto" in df.columns and "valor_total" in df.columns:
            top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(10)
            if len(top) > 0:
                ax2.bar(top.index.astype(str), top.values)
                ax2.tick_params(axis="x", rotation=45, labelsize=8)
            else:
                ax2.text(0.5, 0.5, "Sem top", ha="center", va="center")
        else:
            ax2.text(0.5, 0.5, "Sem coluna produto", ha="center", va="center")
        self.fig_top.tight_layout()
        self.canvas_top.draw()

        # canal
        self.fig_canal.clear()
        ax3 = self.fig_canal.add_subplot(111)
        ax3.set_title("Faturamento por Canal", fontsize=10, fontweight="bold")
        if "canal" in df.columns and "valor_total" in df.columns:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False)
            if len(canal) > 0:
                ax3.bar(canal.index.astype(str), canal.values)
                ax3.tick_params(axis="x", rotation=0, labelsize=8)
            else:
                ax3.text(0.5, 0.5, "Sem canal", ha="center", va="center")
        else:
            ax3.text(0.5, 0.5, "Sem coluna canal", ha="center", va="center")
        self.fig_canal.tight_layout()
        self.canvas_canal.draw()

        # donut canal
        self.fig_donut.clear()
        ax4 = self.fig_donut.add_subplot(111)
        ax4.set_title("Participação por Canal", fontsize=10, fontweight="bold")
        if "canal" in df.columns and "valor_total" in df.columns:
            canal = df.groupby("canal")["valor_total"].sum().sort_values(ascending=False).head(6)
            if len(canal) > 0 and canal.sum() != 0:
                vals = canal.values
                labels = canal.index.astype(str).tolist()
                ax4.pie(vals, labels=labels, autopct="%1.0f%%", pctdistance=0.78)
                # donut effect
                centre_circle = ax4.figure.gca().add_artist(plt_circle())
            else:
                ax4.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        else:
            ax4.text(0.5, 0.5, "Sem coluna canal", ha="center", va="center")

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
    # Export simples (v6.1)
    # =========================================================
    def on_exportar(self):
        if self.base.empty:
            return

        df = self.base_filtrada if not self.base_filtrada.empty else self.base

        arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Excel v6.1",
            str(self.base_dir / "relatorio_dashboard_v61.xlsx"),
            "Excel (*.xlsx)"
        )
        if not arquivo:
            return

        try:
            fat_bruto = self.faturamento_bruto(df)
            fat_liq, impacto = self.faturamento_liquido(df)
            ticket = self.ticket_medio(df)
            vendas = self.qtd_vendas(df)
            itens = int(df.shape[0])
            mp = self.margem_pct(df)

            resumo_exec = pd.DataFrame([{
                "faturamento_liquido": fat_liq,
                "faturamento_bruto": fat_bruto,
                "impacto_cancel_deneg": impacto,
                "ticket_medio": ticket,
                "qtd_vendas": vendas,
                "qtd_itens": itens,
                "margem_bruta_pct": mp
            }])

            top = pd.DataFrame()
            if "produto" in df.columns and "valor_total" in df.columns:
                top = df.groupby("produto")["valor_total"].sum().sort_values(ascending=False).head(15).reset_index()
                top.columns = ["produto", "faturamento"]

            mensal = self.series_mensal(df, liquido=True).reset_index()
            if not mensal.empty:
                mensal.columns = ["mes", "faturamento_liquido"]

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
                (top if not top.empty else pd.DataFrame({"info": ["Sem top produtos"]})).to_excel(writer, sheet_name="Top_Produtos", index=False)
                (mensal if not mensal.empty else pd.DataFrame({"info": ["Sem série mensal"]})).to_excel(writer, sheet_name="Faturamento_Mensal", index=False)
                (canal if not canal.empty else pd.DataFrame({"info": ["Sem canal"]})).to_excel(writer, sheet_name="Faturamento_Canal", index=False)
                (alerts if not alerts.empty else pd.DataFrame({"info": ["Sem alertas"]})).to_excel(writer, sheet_name="Alertas", index=False)
                quality.to_excel(writer, sheet_name="Qualidade", index=False)
                insights.to_excel(writer, sheet_name="Insights", index=False)

            QMessageBox.information(self, "Exportado", f"✅ Excel salvo:\n{arquivo}")

        except Exception as e:
            QMessageBox.critical(self, "Erro ao exportar", str(e))


# donut helper (sem depender de libs externas)
def plt_circle():
    from matplotlib.patches import Circle
    return Circle((0, 0), 0.55, fc="white")


def main():
    app = QApplication(sys.argv)
    w = DashboardV61()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()