import sys
import os
import pandas as pd
import numpy as np
from faker import Faker

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox, QLineEdit, QLabel,
    QSpinBox, QComboBox, QTabWidget, QTableView, QGroupBox,
    QTextEdit, QDateEdit, QCheckBox
)
from PySide6.QtCore import QAbstractTableModel, Qt, QDate

# Matplotlib embed (Qt)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ML
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier


# =========================
# GERADOR DE BASE FICTÍCIA
# =========================
def gerar_base_vendas(n=5000):
    fake = Faker("pt_BR")
    np.random.seed(42)

    ufs = ["SP", "RJ", "MG", "BA", "PR", "SC", "RS", "GO", "PE", "CE"]
    categorias = ["Eletrônicos", "Informática", "Acessórios", "Serviços"]
    formas_pgto = ["PIX", "Cartão", "Boleto", "Dinheiro"]

    dados = []
    for i in range(n):
        categoria = np.random.choice(categorias, p=[0.35, 0.30, 0.25, 0.10])
        uf = np.random.choice(ufs)
        data = fake.date_between(start_date="-180d", end_date="today")

        preco_base = {
            "Eletrônicos": np.random.uniform(200, 5000),
            "Informática": np.random.uniform(150, 8000),
            "Acessórios": np.random.uniform(20, 500),
            "Serviços": np.random.uniform(50, 800)
        }[categoria]

        qtd = np.random.randint(1, 6)
        desconto = np.random.choice([0, 0.05, 0.10, 0.15], p=[0.60, 0.20, 0.15, 0.05])
        total_bruto = preco_base * qtd
        total_liquido = total_bruto * (1 - desconto)

        aliquota = np.random.choice([0.07, 0.12, 0.18], p=[0.20, 0.30, 0.50])
        imposto_estimado = total_liquido * aliquota

        dados.append({
            "id_venda": i + 1,
            "data": str(data),  # string para exportar fácil
            "cliente": fake.name(),
            "cidade": fake.city(),
            "uf": uf,
            "categoria": categoria,
            "forma_pagamento": np.random.choice(formas_pgto),
            "preco_unitario": round(preco_base, 2),
            "quantidade": int(qtd),
            "desconto": float(desconto),
            "total_liquido": round(total_liquido, 2),
            "aliquota": float(aliquota),
            "imposto_estimado": round(imposto_estimado, 2),
        })

    df = pd.DataFrame(dados)
    return df


# =========================
# MODEL pandas -> QTableView
# =========================
class DataFrameModel(QAbstractTableModel):
    def __init__(self, df=pd.DataFrame()):
        super().__init__()
        self._df = df

    def set_dataframe(self, df):
        self.beginResetModel()
        self._df = df.copy() if df is not None else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=None):
        return 0 if self._df is None else self._df.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None
        if role == Qt.DisplayRole:
            value = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(value) else str(value)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if self._df is None:
            return None
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._df.columns[section])
            else:
                return str(section + 1)
        return None


# =========================
# CANVAS (Matplotlib)
# =========================
class MplCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)


# =========================
# APP PRINCIPAL
# =========================
class MiniERP(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mini ERP de Dados (PySide6 + pandas + ML)")
        self.resize(1280, 720)

        # Dados
        self.df = pd.DataFrame()
        self.df_filtrado = pd.DataFrame()
        self.df_pagina = pd.DataFrame()

        # Paginação
        self.page_size = 200
        self.page = 1
        self.total_pages = 1

        # UI
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._build_tab_dados()
        self._build_tab_resumo()
        self._build_tab_graficos()
        self._build_tab_ml()

        self._set_status("Pronto. Gere uma base fictícia ou carregue um CSV.")

    # -------------------------
    # UTILITÁRIOS
    # -------------------------
    def _set_status(self, msg: str):
        self.statusBar().showMessage(msg)

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Padroniza colunas e cria coluna datetime para filtro por período."""
        df = df.copy()

        if "data" in df.columns:
            df["data_dt"] = pd.to_datetime(df["data"], errors="coerce")
        else:
            df["data_dt"] = pd.NaT

        # colunas alvo (se não existir)
        if "alto_valor" not in df.columns:
            # Venda "alto valor" fictícia: total > 2500
            if "total_liquido" in df.columns:
                df["alto_valor"] = (pd.to_numeric(df["total_liquido"], errors="coerce") > 2500).astype(int)
            else:
                df["alto_valor"] = 0

        if "fraude_simulada" not in df.columns:
            # Fraude fictícia didática: desconto alto + boleto + valor alto
            cond = (
                (pd.to_numeric(df.get("desconto", 0), errors="coerce") >= 0.10) &
                (df.get("forma_pagamento", "").astype(str).str.lower().str.contains("boleto", na=False)) &
                (pd.to_numeric(df.get("total_liquido", 0), errors="coerce") >= 2000)
            )
            df["fraude_simulada"] = cond.astype(int)

        return df

    def _refresh_filtros_combobox(self):
        """Atualiza combobox de UF/categoria com base no dataframe atual."""
        if self.df.empty:
            return

        # UF
        ufs = sorted(self.df["uf"].dropna().astype(str).unique().tolist()) if "uf" in self.df.columns else []
        self.cb_uf.blockSignals(True)
        self.cb_uf.clear()
        self.cb_uf.addItem("Todos")
        for uf in ufs:
            self.cb_uf.addItem(uf)
        self.cb_uf.blockSignals(False)

        # Categoria
        cats = sorted(self.df["categoria"].dropna().astype(str).unique().tolist()) if "categoria" in self.df.columns else []
        self.cb_categoria.blockSignals(True)
        self.cb_categoria.clear()
        self.cb_categoria.addItem("Todas")
        for c in cats:
            self.cb_categoria.addItem(c)
        self.cb_categoria.blockSignals(False)

    # -------------------------
    # TAB 1: DADOS
    # -------------------------
    def _build_tab_dados(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Barra superior (ações)
        top = QHBoxLayout()

        self.btn_gerar = QPushButton("Gerar Base Fictícia")
        self.btn_gerar.clicked.connect(self.acao_gerar)
        top.addWidget(self.btn_gerar)

        self.btn_load = QPushButton("Carregar CSV")
        self.btn_load.clicked.connect(self.acao_carregar_csv)
        top.addWidget(self.btn_load)

        self.btn_save = QPushButton("Salvar CSV")
        self.btn_save.clicked.connect(self.acao_salvar_csv)
        top.addWidget(self.btn_save)

        self.btn_xlsx = QPushButton("Exportar Excel (XLSX)")
        self.btn_xlsx.clicked.connect(self.acao_exportar_xlsx)
        top.addWidget(self.btn_xlsx)

        top.addStretch(1)

        layout.addLayout(top)

        # Grupo de filtros
        filtros = QGroupBox("Filtros / Busca / Paginação")
        fl = QHBoxLayout(filtros)

        fl.addWidget(QLabel("UF:"))
        self.cb_uf = QComboBox()
        self.cb_uf.addItem("Todos")
        self.cb_uf.currentTextChanged.connect(self.aplicar_filtros)
        fl.addWidget(self.cb_uf)

        fl.addWidget(QLabel("Categoria:"))
        self.cb_categoria = QComboBox()
        self.cb_categoria.addItem("Todas")
        self.cb_categoria.currentTextChanged.connect(self.aplicar_filtros)
        fl.addWidget(self.cb_categoria)

        fl.addWidget(QLabel("De:"))
        self.dt_ini = QDateEdit()
        self.dt_ini.setCalendarPopup(True)
        self.dt_ini.setDate(QDate.currentDate().addDays(-180))
        self.dt_ini.dateChanged.connect(self.aplicar_filtros)
        fl.addWidget(self.dt_ini)

        fl.addWidget(QLabel("Até:"))
        self.dt_fim = QDateEdit()
        self.dt_fim.setCalendarPopup(True)
        self.dt_fim.setDate(QDate.currentDate())
        self.dt_fim.dateChanged.connect(self.aplicar_filtros)
        fl.addWidget(self.dt_fim)

        fl.addWidget(QLabel("Busca:"))
        self.ed_busca = QLineEdit()
        self.ed_busca.setPlaceholderText("Ex.: SP, PIX, Eletrônicos, nome do cliente...")
        self.ed_busca.textChanged.connect(self.aplicar_filtros)
        fl.addWidget(self.ed_busca)

        fl.addSpacing(10)

        self.chk_usar_filtrado = QCheckBox("Usar filtrado nas abas (Resumo/Gráficos/ML)")
        self.chk_usar_filtrado.setChecked(True)
        self.chk_usar_filtrado.stateChanged.connect(self.atualizar_resumo_e_graficos)
        fl.addWidget(self.chk_usar_filtrado)

        layout.addWidget(filtros)

        # Paginação
        pag = QHBoxLayout()
        pag.addWidget(QLabel("Tamanho da página:"))
        self.sp_page = QSpinBox()
        self.sp_page.setRange(50, 5000)
        self.sp_page.setValue(200)
        self.sp_page.valueChanged.connect(self._on_change_page_size)
        pag.addWidget(self.sp_page)

        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_prev.clicked.connect(self.pagina_anterior)
        pag.addWidget(self.btn_prev)

        self.lb_page = QLabel("Página 1/1")
        pag.addWidget(self.lb_page)

        self.btn_next = QPushButton("Próxima ▶")
        self.btn_next.clicked.connect(self.proxima_pagina)
        pag.addWidget(self.btn_next)

        pag.addStretch(1)
        layout.addLayout(pag)

        # Tabela
        self.table = QTableView()
        self.model_table = DataFrameModel(pd.DataFrame())
        self.table.setModel(self.model_table)
        layout.addWidget(self.table)

        self.tabs.addTab(tab, "Dados")

    def acao_gerar(self):
        try:
            self.df = gerar_base_vendas(n=7000)
            self.df = self._prepare_dataframe(self.df)
            self._refresh_filtros_combobox()
            self.page = 1
            self.aplicar_filtros()
            self._set_status(f"Base gerada: {len(self.df)} linhas.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao gerar base:\n{e}")

    def acao_carregar_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar CSV", "", "CSV (*.csv);;Todos (*.*)")
        if not path:
            return
        try:
            df = pd.read_csv(path)
            self.df = self._prepare_dataframe(df)
            self._refresh_filtros_combobox()
            self.page = 1
            self.aplicar_filtros()
            self._set_status(f"CSV carregado: {os.path.basename(path)} ({len(self.df)} linhas).")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível carregar o CSV:\n{e}")

    def acao_salvar_csv(self):
        if self.df.empty:
            QMessageBox.warning(self, "Aviso", "Não há dados para salvar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar CSV", "base.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            # remove coluna auxiliar data_dt na exportação (opcional)
            df_out = self.df.drop(columns=["data_dt"], errors="ignore")
            df_out.to_csv(path, index=False)
            self._set_status(f"CSV salvo em: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar CSV:\n{e}")

    def acao_exportar_xlsx(self):
        if self.df.empty:
            QMessageBox.warning(self, "Aviso", "Não há dados para exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Excel", "base.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            df_out = self.df.drop(columns=["data_dt"], errors="ignore")
            df_out.to_excel(path, index=False)
            self._set_status(f"Excel exportado: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar Excel:\n{e}")

    def _on_change_page_size(self):
        self.page_size = int(self.sp_page.value())
        self.page = 1
        self._atualizar_paginacao()

    def pagina_anterior(self):
        if self.page > 1:
            self.page -= 1
            self._atualizar_paginacao()

    def proxima_pagina(self):
        if self.page < self.total_pages:
            self.page += 1
            self._atualizar_paginacao()

    def aplicar_filtros(self):
        if self.df.empty:
            self.model_table.set_dataframe(pd.DataFrame())
            return

        df = self.df.copy()

        # UF
        uf = self.cb_uf.currentText().strip()
        if uf and uf != "Todos" and "uf" in df.columns:
            df = df[df["uf"].astype(str) == uf]

        # Categoria
        cat = self.cb_categoria.currentText().strip()
        if cat and cat != "Todas" and "categoria" in df.columns:
            df = df[df["categoria"].astype(str) == cat]

        # Período
        ini = self.dt_ini.date().toPython()
        fim = self.dt_fim.date().toPython()
        if "data_dt" in df.columns:
            df = df[(df["data_dt"] >= pd.Timestamp(ini)) & (df["data_dt"] <= pd.Timestamp(fim))]

        # Busca geral (contém em qualquer coluna)
        termo = self.ed_busca.text().strip().lower()
        if termo:
            mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(termo, na=False))
            df = df[mask.any(axis=1)]

        self.df_filtrado = df
        self.page = 1
        self._atualizar_paginacao()
        self.atualizar_resumo_e_graficos()

    def _atualizar_paginacao(self):
        if self.df_filtrado.empty:
            self.model_table.set_dataframe(pd.DataFrame())
            self.lb_page.setText("Página 0/0")
            self.total_pages = 0
            return

        total_rows = len(self.df_filtrado)
        self.total_pages = int(np.ceil(total_rows / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        df_page = self.df_filtrado.iloc[start:end].copy()

        # não mostrar data_dt na tabela
        df_page = df_page.drop(columns=["data_dt"], errors="ignore")

        self.df_pagina = df_page
        self.model_table.set_dataframe(self.df_pagina)

        self.lb_page.setText(f"Página {self.page}/{self.total_pages}")

    # -------------------------
    # TAB 2: RESUMO
    # -------------------------
    def _build_tab_resumo(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.kpi_text = QTextEdit()
        self.kpi_text.setReadOnly(True)
        layout.addWidget(self.kpi_text)

        self.tabs.addTab(tab, "Resumo")

    def _get_df_analise(self) -> pd.DataFrame:
        if self.chk_usar_filtrado.isChecked():
            return self.df_filtrado.copy() if not self.df_filtrado.empty else pd.DataFrame()
        return self.df.copy() if not self.df.empty else pd.DataFrame()

    def atualizar_resumo_e_graficos(self):
        self.atualizar_resumo()
        self.atualizar_grafico()

    def atualizar_resumo(self):
        df = self._get_df_analise()
        if df.empty:
            self.kpi_text.setPlainText("Sem dados para resumo.")
            return

        total_vendas = pd.to_numeric(df.get("total_liquido", 0), errors="coerce").sum()
        total_imposto = pd.to_numeric(df.get("imposto_estimado", 0), errors="coerce").sum()
        qtd_vendas = len(df)
        ticket_medio = total_vendas / qtd_vendas if qtd_vendas else 0

        top_cat = ""
        if "categoria" in df.columns and "total_liquido" in df.columns:
            g = df.groupby("categoria")["total_liquido"].sum().sort_values(ascending=False)
            if len(g) > 0:
                top_cat = f"{g.index[0]} (R$ {g.iloc[0]:,.2f})".replace(",", "X").replace(".", ",").replace("X", ".")

        # qualidade de dados
        nulos = df.isna().sum().sum()

        texto = []
        texto.append("==== KPIs (Resumo) ====")
        texto.append(f"Linhas analisadas: {qtd_vendas}")
        texto.append(f"Total de vendas (líquido): R$ {total_vendas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        texto.append(f"Total de imposto estimado: R$ {total_imposto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        texto.append(f"Ticket médio: R$ {ticket_medio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        if top_cat:
            texto.append(f"Categoria líder: {top_cat}")
        texto.append(f"Total de valores nulos (todas colunas): {int(nulos)}")
        texto.append("")
        texto.append("Dica: use os filtros na aba 'Dados' para analisar por UF/categoria/período.")

        self.kpi_text.setPlainText("\n".join(texto))

    # -------------------------
    # TAB 3: GRÁFICOS
    # -------------------------
    def _build_tab_graficos(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Gráfico:"))
        self.cb_grafico = QComboBox()
        self.cb_grafico.addItems([
            "Vendas por Categoria (Barra)",
            "Vendas por UF (Barra)",
            "Série temporal (Vendas por Dia)",
            "Top 10 Clientes (Vendas)"
        ])
        self.cb_grafico.currentTextChanged.connect(self.atualizar_grafico)
        bar.addWidget(self.cb_grafico)

        self.btn_atualizar_graf = QPushButton("Atualizar")
        self.btn_atualizar_graf.clicked.connect(self.atualizar_grafico)
        bar.addWidget(self.btn_atualizar_graf)

        bar.addStretch(1)
        layout.addLayout(bar)

        self.canvas = MplCanvas()
        layout.addWidget(self.canvas)

        self.tabs.addTab(tab, "Gráficos")

    def atualizar_grafico(self):
        df = self._get_df_analise()
        self.canvas.ax.clear()

        if df.empty:
            self.canvas.ax.set_title("Sem dados para gráfico")
            self.canvas.draw()
            return

        tipo = self.cb_grafico.currentText()

        try:
            if tipo == "Vendas por Categoria (Barra)":
                g = df.groupby("categoria")["total_liquido"].sum().sort_values(ascending=False)
                self.canvas.ax.bar(g.index.astype(str), g.values)
                self.canvas.ax.set_title("Total de Vendas por Categoria")
                self.canvas.ax.set_xlabel("Categoria")
                self.canvas.ax.set_ylabel("Total (R$)")
                self.canvas.ax.tick_params(axis="x", rotation=20)

            elif tipo == "Vendas por UF (Barra)":
                g = df.groupby("uf")["total_liquido"].sum().sort_values(ascending=False)
                self.canvas.ax.bar(g.index.astype(str), g.values)
                self.canvas.ax.set_title("Total de Vendas por UF")
                self.canvas.ax.set_xlabel("UF")
                self.canvas.ax.set_ylabel("Total (R$)")

            elif tipo == "Série temporal (Vendas por Dia)":
                if "data_dt" not in df.columns:
                    df["data_dt"] = pd.to_datetime(df["data"], errors="coerce")
                g = df.dropna(subset=["data_dt"]).groupby(df["data_dt"].dt.date)["total_liquido"].sum()
                self.canvas.ax.plot(list(g.index), g.values)
                self.canvas.ax.set_title("Vendas por Dia")
                self.canvas.ax.set_xlabel("Data")
                self.canvas.ax.set_ylabel("Total (R$)")
                self.canvas.ax.tick_params(axis="x", rotation=25)

            elif tipo == "Top 10 Clientes (Vendas)":
                g = df.groupby("cliente")["total_liquido"].sum().sort_values(ascending=False).head(10)
                self.canvas.ax.barh(g.index.astype(str), g.values)
                self.canvas.ax.set_title("Top 10 Clientes por Vendas")
                self.canvas.ax.set_xlabel("Total (R$)")
                self.canvas.ax.invert_yaxis()

            self.canvas.fig.tight_layout()
            self.canvas.draw()

        except Exception as e:
            self.canvas.ax.set_title(f"Erro ao gerar gráfico: {e}")
            self.canvas.draw()

    # -------------------------
    # TAB 4: ML (Treinar Modelo)
    # -------------------------
    def _build_tab_ml(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controles
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("Target (classe):"))
        self.cb_target = QComboBox()
        self.cb_target.addItems(["alto_valor", "fraude_simulada"])
        ctrl.addWidget(self.cb_target)

        ctrl.addSpacing(10)

        ctrl.addWidget(QLabel("Algoritmo:"))
        self.cb_alg = QComboBox()
        self.cb_alg.addItems(["LogisticRegression", "RandomForest"])
        ctrl.addWidget(self.cb_alg)

        ctrl.addSpacing(10)

        self.btn_train = QPushButton("Treinar Modelo")
        self.btn_train.clicked.connect(self.treinar_modelo)
        ctrl.addWidget(self.btn_train)

        ctrl.addStretch(1)
        layout.addLayout(ctrl)

        # Resultado texto
        self.ml_out = QTextEdit()
        self.ml_out.setReadOnly(True)
        layout.addWidget(self.ml_out)

        # Confusion Matrix plot
        self.canvas_cm = MplCanvas()
        layout.addWidget(self.canvas_cm)

        self.tabs.addTab(tab, "Treinar ML")

    def treinar_modelo(self):
        df = self._get_df_analise()
        if df.empty:
            QMessageBox.warning(self, "Aviso", "Sem dados para treinar.")
            return

        target = self.cb_target.currentText().strip()
        if target not in df.columns:
            QMessageBox.warning(self, "Aviso", f"A coluna target '{target}' não existe no dataset.")
            return

        # Features candidatas
        col_num = [c for c in ["preco_unitario", "quantidade", "desconto", "aliquota", "imposto_estimado", "total_liquido"] if c in df.columns]
        col_cat = [c for c in ["uf", "categoria", "forma_pagamento"] if c in df.columns]

        if not col_num and not col_cat:
            QMessageBox.warning(self, "Aviso", "Não há colunas suficientes para treinar o modelo.")
            return

        # Preparar X e y
        X = df[col_num + col_cat].copy()
        y = pd.to_numeric(df[target], errors="coerce").fillna(0).astype(int)

        # Pré-processamento
        preprocessor = ColumnTransformer(
            transformers=[
                ("num", "passthrough", col_num),
                ("cat", OneHotEncoder(handle_unknown="ignore"), col_cat)
            ],
            remainder="drop"
        )

        alg = self.cb_alg.currentText()

        if alg == "LogisticRegression":
            clf = LogisticRegression(max_iter=200)
        else:
            clf = RandomForestClassifier(
                n_estimators=200,
                random_state=42,
                class_weight="balanced"
            )

        model = Pipeline(steps=[
            ("prep", preprocessor),
            ("clf", clf)
        ])

        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.25, random_state=42, stratify=y if y.nunique() > 1 else None
            )

            model.fit(X_train, y_train)
            pred = model.predict(X_test)

            acc = accuracy_score(y_test, pred)
            rep = classification_report(y_test, pred, digits=4)

            # Confusion matrix
            cm = confusion_matrix(y_test, pred)

            self.ml_out.setPlainText(
                f"=== Treinamento concluído ===\n"
                f"Target: {target}\n"
                f"Algoritmo: {alg}\n"
                f"Acurácia: {acc:.4f}\n\n"
                f"=== Classification Report ===\n{rep}"
            )

            # Plot CM
            self.canvas_cm.ax.clear()
            self.canvas_cm.ax.set_title("Confusion Matrix")
            im = self.canvas_cm.ax.imshow(cm)
            self.canvas_cm.ax.set_xlabel("Predito")
            self.canvas_cm.ax.set_ylabel("Real")

            for i in range(cm.shape[0]):
                for j in range(cm.shape[1]):
                    self.canvas_cm.ax.text(j, i, str(cm[i, j]), ha="center", va="center")

            self.canvas_cm.fig.tight_layout()
            self.canvas_cm.draw()

            self._set_status("Modelo treinado com sucesso.")

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao treinar modelo:\n{e}")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MiniERP()
    w.show()
    sys.exit(app.exec())