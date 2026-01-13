import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableView, QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QCheckBox, QDoubleSpinBox, QComboBox
)


# ============================================
# Dados (Model)
# ============================================

@dataclass
class Product:
    id: int
    sku: str
    name: str
    category: str
    brand: str
    ncm: str
    nbs: str
    ean: str
    price: float

    # Reforma Tributária (parâmetros por item)
    iva_regime: str            # ex.: PADRAO / REDUCAO_60 / ALIQUOTA_ZERO / REGIME_ESPECIFICO / MANUAL
    cbs_rate: float            # %
    ibs_rate: float            # %
    is_rate: float             # % (Imposto Seletivo)
    allow_credit: bool         # permite crédito IBS/CBS
    notes: str                 # observações fiscais internas

    active: bool


@dataclass
class TaxParams:
    default_regime: str = "PADRAO"
    default_allow_credit: bool = True
    default_cbs_rate: float = 0.0
    default_ibs_rate: float = 0.0
    default_is_rate: float = 0.0


# ============================================
# Persistência (SQLite)
# ============================================

class ProductRepository:
    def __init__(self, db_path: str = "app.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        # timeout para reduzir "database is locked" em casos de uso intenso
        return sqlite3.connect(self.db_path, timeout=30)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_columns(self, con: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
        """
        columns: {col_name: "TYPE ... DEFAULT ..."}
        """
        cur = con.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        existing = {r[1] for r in cur.fetchall()}
        for col, ddl in columns.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    def _init_db(self):
        with self._connect() as con:
            cur = con.cursor()

            # Tabela principal (produtos)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    brand TEXT NOT NULL DEFAULT '',
                    ncm TEXT NOT NULL DEFAULT '',
                    nbs TEXT NOT NULL DEFAULT '',
                    ean TEXT NOT NULL DEFAULT '',
                    price REAL NOT NULL DEFAULT 0,

                    iva_regime TEXT NOT NULL DEFAULT 'PADRAO',
                    cbs_rate REAL NOT NULL DEFAULT 0,
                    ibs_rate REAL NOT NULL DEFAULT 0,
                    is_rate REAL NOT NULL DEFAULT 0,
                    allow_credit INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',

                    active INTEGER NOT NULL DEFAULT 1
                )
            """)

            # Migração leve para bases antigas (adiciona colunas se faltarem)
            self._ensure_columns(con, "products", {
                "nbs": "TEXT NOT NULL DEFAULT ''",
                "iva_regime": "TEXT NOT NULL DEFAULT 'PADRAO'",
                "cbs_rate": "REAL NOT NULL DEFAULT 0",
                "ibs_rate": "REAL NOT NULL DEFAULT 0",
                "is_rate": "REAL NOT NULL DEFAULT 0",
                "allow_credit": "INTEGER NOT NULL DEFAULT 1",
                "notes": "TEXT NOT NULL DEFAULT ''",
            })

            # Tabela de parâmetros globais (única linha id=1)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tax_params (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    default_regime TEXT NOT NULL DEFAULT 'PADRAO',
                    default_allow_credit INTEGER NOT NULL DEFAULT 1,
                    default_cbs_rate REAL NOT NULL DEFAULT 0,
                    default_ibs_rate REAL NOT NULL DEFAULT 0,
                    default_is_rate REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                )
            """)

            # Migração leve (caso você evolua a tabela no futuro)
            self._ensure_columns(con, "tax_params", {
                "default_regime": "TEXT NOT NULL DEFAULT 'PADRAO'",
                "default_allow_credit": "INTEGER NOT NULL DEFAULT 1",
                "default_cbs_rate": "REAL NOT NULL DEFAULT 0",
                "default_ibs_rate": "REAL NOT NULL DEFAULT 0",
                "default_is_rate": "REAL NOT NULL DEFAULT 0",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            })

            # Garante a linha id=1
            cur.execute("INSERT OR IGNORE INTO tax_params (id, updated_at) VALUES (1, ?)", (self._now_iso(),))

            con.commit()

    # ----------------------------
    # Parâmetros globais
    # ----------------------------

    def get_tax_params(self) -> TaxParams:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT default_regime, default_allow_credit, default_cbs_rate, default_ibs_rate, default_is_rate
                FROM tax_params
                WHERE id=1
            """)
            row = cur.fetchone()

        if not row:
            return TaxParams()

        return TaxParams(
            default_regime=(row[0] or "PADRAO"),
            default_allow_credit=bool(int(row[1] or 0)),
            default_cbs_rate=float(row[2] or 0.0),
            default_ibs_rate=float(row[3] or 0.0),
            default_is_rate=float(row[4] or 0.0),
        )

    def save_tax_params(self, params: TaxParams) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE tax_params
                SET default_regime=?,
                    default_allow_credit=?,
                    default_cbs_rate=?,
                    default_ibs_rate=?,
                    default_is_rate=?,
                    updated_at=?
                WHERE id=1
            """, (
                (params.default_regime or "PADRAO").strip().upper(),
                1 if params.default_allow_credit else 0,
                float(params.default_cbs_rate),
                float(params.default_ibs_rate),
                float(params.default_is_rate),
                self._now_iso(),
            ))
            con.commit()

    # ----------------------------
    # CRUD de produtos
    # ----------------------------

    def list(self, query: str = "", include_inactive: bool = False) -> List[Product]:
        q = f"%{query.strip()}%"
        where = "WHERE (name LIKE ? OR category LIKE ? OR brand LIKE ? OR sku LIKE ?)"
        params = [q, q, q, q]
        if not include_inactive:
            where += " AND active = 1"

        with self._connect() as con:
            cur = con.cursor()
            cur.execute(f"""
                SELECT
                    id, sku, name, category, brand, ncm, nbs, ean, price,
                    iva_regime, cbs_rate, ibs_rate, is_rate, allow_credit, notes,
                    active
                FROM products
                {where}
                ORDER BY id DESC
            """, params)
            rows = cur.fetchall()

        items: List[Product] = []
        for r in rows:
            items.append(Product(
                id=int(r[0]),
                sku=str(r[1] or ""),
                name=str(r[2] or ""),
                category=str(r[3] or ""),
                brand=str(r[4] or ""),
                ncm=str(r[5] or ""),
                nbs=str(r[6] or ""),
                ean=str(r[7] or ""),
                price=float(r[8] or 0.0),

                iva_regime=str(r[9] or "PADRAO"),
                cbs_rate=float(r[10] or 0.0),
                ibs_rate=float(r[11] or 0.0),
                is_rate=float(r[12] or 0.0),
                allow_credit=bool(int(r[13] or 0)),
                notes=str(r[14] or ""),

                active=bool(int(r[15] or 0)),
            ))
        return items

    def insert(self, p: Product) -> int:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO products (
                    sku, name, category, brand, ncm, nbs, ean, price,
                    iva_regime, cbs_rate, ibs_rate, is_rate, allow_credit, notes,
                    active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p.sku, p.name, p.category, p.brand, p.ncm, p.nbs, p.ean, p.price,
                p.iva_regime, p.cbs_rate, p.ibs_rate, p.is_rate, 1 if p.allow_credit else 0, p.notes,
                1 if p.active else 0
            ))
            new_id = cur.lastrowid
            con.commit()
            return int(new_id)

    def update(self, p: Product) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE products
                SET
                    sku=?,
                    name=?,
                    category=?,
                    brand=?,
                    ncm=?,
                    nbs=?,
                    ean=?,
                    price=?,
                    iva_regime=?,
                    cbs_rate=?,
                    ibs_rate=?,
                    is_rate=?,
                    allow_credit=?,
                    notes=?,
                    active=?
                WHERE id=?
            """, (
                p.sku,
                p.name, p.category, p.brand, p.ncm, p.nbs, p.ean, p.price,
                p.iva_regime, p.cbs_rate, p.ibs_rate, p.is_rate, 1 if p.allow_credit else 0, p.notes,
                1 if p.active else 0,
                p.id
            ))
            con.commit()

    def deactivate(self, product_id: int) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))
            con.commit()


# ============================================
# Regras / validações
# ============================================

class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    @staticmethod
    def _cat_prefix(category: str) -> str:
        # prefixo simples: 3 primeiros caracteres alfanuméricos em maiúsculo
        clean = re.sub(r"[^A-Za-z0-9]", "", (category or "").upper())
        return (clean[:3] if clean else "CAT")

    @staticmethod
    def validate(
        name: str,
        category: str,
        ncm: str,
        nbs: str,
        ean: str,
        price: float,
        iva_regime: str,
        cbs_rate: float,
        ibs_rate: float,
        is_rate: float,
        notes: str
    ) -> None:
        if not name.strip():
            raise ValueError("Nome é obrigatório.")
        if not category.strip():
            raise ValueError("Categoria é obrigatória.")

        ncm = (ncm or "").strip()
        if ncm and (not ncm.isdigit() or len(ncm) != 8):
            raise ValueError("NCM inválido. Use 8 dígitos (somente números).")

        nbs = (nbs or "").strip()
        # Validação conservadora: permite números e ponto (algumas referências publicam NBS com separadores).
        if nbs and (not re.fullmatch(r"[0-9.]{4,20}", nbs)):
            raise ValueError("NBS inválida. Use apenas números e ponto (ex.: 1.03.01.00).")

        ean = (ean or "").strip()
        if ean and (not ean.isdigit() or len(ean) not in (8, 12, 13, 14)):
            raise ValueError("EAN inválido. Use 8/12/13/14 dígitos (somente números).")

        if price < 0:
            raise ValueError("Preço não pode ser negativo.")

        iva_regime = (iva_regime or "").strip()
        if iva_regime and len(iva_regime) > 40:
            raise ValueError("Regime (IBS/CBS) muito longo (máx. 40 caracteres).")

        for label, v in (("CBS", cbs_rate), ("IBS", ibs_rate), ("IS", is_rate)):
            if v < 0 or v > 100:
                raise ValueError(f"{label} (%) deve estar entre 0 e 100.")

        if notes and len(notes) > 300:
            raise ValueError("Observações muito longas (máx. 300 caracteres).")

    def generate_sku(self, category: str, new_id: int) -> str:
        # SKU = PREFIXO + ID com zeros (ex.: ELE000123)
        return f"{self._cat_prefix(category)}{new_id:06d}"


# ============================================
# Qt Model/View (Tabela)
# ============================================

class ProductTableModel(QAbstractTableModel):
    HEADERS = [
        "ID", "SKU", "Nome", "Categoria", "Marca", "NCM", "NBS", "EAN", "Preço",
        "IBS %", "CBS %", "IS %", "Regime", "Crédito", "Ativo"
    ]

    def __init__(self):
        super().__init__()
        self._items: List[Product] = []

    def set_items(self, items: List[Product]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        p = self._items[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0: return p.id
            if col == 1: return p.sku
            if col == 2: return p.name
            if col == 3: return p.category
            if col == 4: return p.brand
            if col == 5: return p.ncm
            if col == 6: return p.nbs
            if col == 7: return p.ean
            if col == 8: return f"{p.price:.2f}"
            if col == 9: return f"{p.ibs_rate:.4f}"
            if col == 10: return f"{p.cbs_rate:.4f}"
            if col == 11: return f"{p.is_rate:.4f}"
            if col == 12: return (p.iva_regime or "").upper()
            if col == 13: return "Sim" if p.allow_credit else "Não"
            if col == 14: return "Sim" if p.active else "Não"

        if role == Qt.TextAlignmentRole:
            if col in (0, 8, 9, 10, 11):
                return Qt.AlignRight | Qt.AlignVCenter

        return None

    def get(self, row: int) -> Optional[Product]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


# ============================================
# Dialogs
# ============================================

class GlobalParamsDialog(QDialog):
    def __init__(self, parent=None, initial: Optional[TaxParams] = None):
        super().__init__(parent)
        self.setWindowTitle("Parâmetros Globais - IBS/CBS/IS")
        self.setModal(True)

        self.regime = QComboBox()
        self.regime.setEditable(True)
        self.regime.addItems([
            "PADRAO",
            "REDUCAO_60",
            "REDUCAO_30",
            "ALIQUOTA_ZERO",
            "REGIME_ESPECIFICO",
            "MANUAL",
        ])

        self.allow_credit = QCheckBox("Permite crédito (padrão)")

        self.cbs = QDoubleSpinBox()
        self.cbs.setRange(0, 100)
        self.cbs.setDecimals(4)

        self.ibs = QDoubleSpinBox()
        self.ibs.setRange(0, 100)
        self.ibs.setDecimals(4)

        self.is_ = QDoubleSpinBox()
        self.is_.setRange(0, 100)
        self.is_.setDecimals(4)

        form = QFormLayout()
        form.addRow("Regime padrão (IBS/CBS)", self.regime)
        form.addRow("", self.allow_credit)
        form.addRow("CBS padrão (%)", self.cbs)
        form.addRow("IBS padrão (%)", self.ibs)
        form.addRow("IS padrão (%)", self.is_)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

        if initial is not None:
            self.set_values(initial)

    def set_values(self, p: TaxParams):
        self.regime.setCurrentText((p.default_regime or "PADRAO").strip().upper())
        self.allow_credit.setChecked(bool(p.default_allow_credit))
        self.cbs.setValue(float(p.default_cbs_rate))
        self.ibs.setValue(float(p.default_ibs_rate))
        self.is_.setValue(float(p.default_is_rate))

    def get_values(self) -> TaxParams:
        return TaxParams(
            default_regime=(self.regime.currentText() or "PADRAO").strip().upper(),
            default_allow_credit=bool(self.allow_credit.isChecked()),
            default_cbs_rate=float(self.cbs.value()),
            default_ibs_rate=float(self.ibs.value()),
            default_is_rate=float(self.is_.value()),
        )


class ProductDialog(QDialog):
    def __init__(self, parent=None, initial: Optional[Product] = None, defaults: Optional[TaxParams] = None):
        super().__init__(parent)
        self.setWindowTitle("Produto")
        self.setModal(True)

        self.name = QLineEdit()
        self.category = QLineEdit()
        self.brand = QLineEdit()
        self.ncm = QLineEdit()
        self.nbs = QLineEdit()
        self.ean = QLineEdit()

        self.price = QDoubleSpinBox()
        self.price.setRange(0, 10_000_000)
        self.price.setDecimals(2)

        self.regime = QComboBox()
        self.regime.setEditable(True)
        self.regime.addItems([
            "PADRAO",
            "REDUCAO_60",
            "REDUCAO_30",
            "ALIQUOTA_ZERO",
            "REGIME_ESPECIFICO",
            "MANUAL",
        ])

        self.cbs = QDoubleSpinBox()
        self.cbs.setRange(0, 100)
        self.cbs.setDecimals(4)

        self.ibs = QDoubleSpinBox()
        self.ibs.setRange(0, 100)
        self.ibs.setDecimals(4)

        self.is_ = QDoubleSpinBox()
        self.is_.setRange(0, 100)
        self.is_.setDecimals(4)

        self.allow_credit = QCheckBox("Permite crédito (IBS/CBS)")

        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Observações fiscais internas (opcional)")

        self.active = QCheckBox("Ativo")

        form = QFormLayout()
        form.addRow("Nome*", self.name)
        form.addRow("Categoria*", self.category)
        form.addRow("Marca", self.brand)
        form.addRow("NCM (8 dígitos)", self.ncm)
        form.addRow("NBS (opcional)", self.nbs)
        form.addRow("EAN", self.ean)
        form.addRow("Preço (R$)", self.price)

        form.addRow("Regime IBS/CBS", self.regime)
        form.addRow("CBS (%)", self.cbs)
        form.addRow("IBS (%)", self.ibs)
        form.addRow("IS (%)", self.is_)
        form.addRow("", self.allow_credit)
        form.addRow("Observações", self.notes)

        form.addRow("", self.active)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

        # Defaults para novo cadastro
        if initial is None and defaults is not None:
            self.regime.setCurrentText((defaults.default_regime or "PADRAO").strip().upper())
            self.allow_credit.setChecked(bool(defaults.default_allow_credit))
            self.cbs.setValue(float(defaults.default_cbs_rate))
            self.ibs.setValue(float(defaults.default_ibs_rate))
            self.is_.setValue(float(defaults.default_is_rate))
            self.active.setChecked(True)

        # Valores ao editar
        if initial is not None:
            self.name.setText(initial.name)
            self.category.setText(initial.category)
            self.brand.setText(initial.brand)
            self.ncm.setText(initial.ncm)
            self.nbs.setText(initial.nbs)
            self.ean.setText(initial.ean)
            self.price.setValue(float(initial.price))

            self.regime.setCurrentText((initial.iva_regime or "PADRAO").strip().upper())
            self.cbs.setValue(float(initial.cbs_rate))
            self.ibs.setValue(float(initial.ibs_rate))
            self.is_.setValue(float(initial.is_rate))
            self.allow_credit.setChecked(bool(initial.allow_credit))
            self.notes.setText(initial.notes or "")

            self.active.setChecked(bool(initial.active))

    def get_values(self) -> Dict[str, Any]:
        return {
            "name": self.name.text(),
            "category": self.category.text(),
            "brand": self.brand.text(),
            "ncm": self.ncm.text(),
            "nbs": self.nbs.text(),
            "ean": self.ean.text(),
            "price": float(self.price.value()),

            "iva_regime": self.regime.currentText(),
            "cbs_rate": float(self.cbs.value()),
            "ibs_rate": float(self.ibs.value()),
            "is_rate": float(self.is_.value()),
            "allow_credit": bool(self.allow_credit.isChecked()),
            "notes": self.notes.text(),

            "active": bool(self.active.isChecked()),
        }


# ============================================
# Main Window (UI + Controller)
# ============================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERP - Cadastro de Produtos (Reforma Tributária + Parâmetros Globais)")
        self.resize(1300, 650)

        self.repo = ProductRepository()
        self.service = ProductService(self.repo)

        self.model = ProductTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setSortingEnabled(False)

        # Filtros
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nome, categoria, marca ou SKU...")
        self.include_inactive = QCheckBox("Incluir inativos")

        # Botões
        self.btn_add = QPushButton("Adicionar")
        self.btn_edit = QPushButton("Editar")
        self.btn_deactivate = QPushButton("Inativar")
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_params = QPushButton("Parâmetros Globais")

        self.btn_add.clicked.connect(self.add_product)
        self.btn_edit.clicked.connect(self.edit_product)
        self.btn_deactivate.clicked.connect(self.deactivate_product)
        self.btn_refresh.clicked.connect(self.load_data)
        self.btn_params.clicked.connect(self.open_global_params)

        self.search.textChanged.connect(self.load_data)
        self.include_inactive.stateChanged.connect(self.load_data)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.include_inactive)
        top.addWidget(self.btn_params)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_deactivate)
        top.addWidget(self.btn_refresh)

        root = QVBoxLayout()
        root.addLayout(top)
        root.addWidget(self.table, 1)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        self.load_data()

    def load_data(self):
        items = self.repo.list(self.search.text(), include_inactive=self.include_inactive.isChecked())
        self.model.set_items(items)
        self.table.resizeColumnsToContents()

    def _selected_product(self) -> Optional[Product]:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        return self.model.get(row)

    def open_global_params(self):
        current = self.repo.get_tax_params()
        dlg = GlobalParamsDialog(self, initial=current)
        if dlg.exec() != QDialog.Accepted:
            return

        p = dlg.get_values()

        # validação mínima (0..100 já é garantido pelo SpinBox)
        if not (p.default_regime or "").strip():
            QMessageBox.warning(self, "Validação", "Regime padrão não pode ficar em branco.")
            return

        self.repo.save_tax_params(p)
        QMessageBox.information(self, "Salvo", "Parâmetros globais atualizados.")
        # não precisa atualizar tabela; afeta principalmente novos cadastros

    def add_product(self):
        defaults = self.repo.get_tax_params()
        dlg = ProductDialog(self, initial=None, defaults=defaults)
        if dlg.exec() != QDialog.Accepted:
            return

        v = dlg.get_values()
        try:
            self.service.validate(
                v["name"], v["category"], v["ncm"], v["nbs"], v["ean"], v["price"],
                v["iva_regime"], v["cbs_rate"], v["ibs_rate"], v["is_rate"], v["notes"]
            )

            # Primeiro insere sem SKU e depois atualiza com SKU gerado pelo ID
            p = Product(
                id=0,
                sku="",
                name=v["name"].strip(),
                category=v["category"].strip(),
                brand=v["brand"].strip(),
                ncm=v["ncm"].strip(),
                nbs=v["nbs"].strip(),
                ean=v["ean"].strip(),
                price=v["price"],

                iva_regime=(v["iva_regime"] or "PADRAO").strip().upper(),
                cbs_rate=v["cbs_rate"],
                ibs_rate=v["ibs_rate"],
                is_rate=v["is_rate"],
                allow_credit=v["allow_credit"],
                notes=(v["notes"] or "").strip(),

                active=v["active"]
            )

            new_id = self.repo.insert(p)
            sku = self.service.generate_sku(p.category, new_id)

            p.id = new_id
            p.sku = sku
            self.repo.update(p)

            self.load_data()
        except ValueError as e:
            QMessageBox.warning(self, "Validação", str(e))

    def edit_product(self):
        p = self._selected_product()
        if not p:
            QMessageBox.information(self, "Seleção", "Selecione um produto na tabela.")
            return

        dlg = ProductDialog(self, initial=p, defaults=None)
        if dlg.exec() != QDialog.Accepted:
            return

        v = dlg.get_values()
        try:
            self.service.validate(
                v["name"], v["category"], v["ncm"], v["nbs"], v["ean"], v["price"],
                v["iva_regime"], v["cbs_rate"], v["ibs_rate"], v["is_rate"], v["notes"]
            )

            updated = Product(
                id=p.id,
                sku=p.sku,  # mantém SKU
                name=v["name"].strip(),
                category=v["category"].strip(),
                brand=v["brand"].strip(),
                ncm=v["ncm"].strip(),
                nbs=v["nbs"].strip(),
                ean=v["ean"].strip(),
                price=v["price"],

                iva_regime=(v["iva_regime"] or "PADRAO").strip().upper(),
                cbs_rate=v["cbs_rate"],
                ibs_rate=v["ibs_rate"],
                is_rate=v["is_rate"],
                allow_credit=v["allow_credit"],
                notes=(v["notes"] or "").strip(),

                active=v["active"]
            )
            self.repo.update(updated)
            self.load_data()
        except ValueError as e:
            QMessageBox.warning(self, "Validação", str(e))

    def deactivate_product(self):
        p = self._selected_product()
        if not p:
            QMessageBox.information(self, "Seleção", "Selecione um produto na tabela.")
            return

        resp = QMessageBox.question(
            self,
            "Confirmar",
            f"Inativar o produto:\n\n{p.name} (SKU {p.sku}) ?"
        )
        if resp != QMessageBox.Yes:
            return

        self.repo.deactivate(p.id)
        self.load_data()


if __name__ == "__main__":
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()
