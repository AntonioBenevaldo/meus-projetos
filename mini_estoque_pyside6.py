import csv
import json
import re
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QSortFilterProxyModel,
    QStandardPaths,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

# ============================================================
# Utilitários
# ============================================================
UF_LIST = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO"
]

NATUREZA_LIST = [
    "Venda de mercadoria",
    "Prestação de serviço",
    "Devolução",
    "Transferência",
    "Bonificação/Brinde",
    "Ajuste/Inventário",
    "Outros",
]


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    p = Path(base) / "MiniERP_Reforma"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return app_data_dir() / "db.json"


def normalize_prefix(category: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", (category or "").strip().upper())
    s = s[:3]
    if len(s) < 3:
        s = (s + "XXX")[:3]
    return s


def generate_sku(category: str, existing_skus: List[str]) -> str:
    prefix = normalize_prefix(category)
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})$")
    max_n = 0
    for sku in existing_skus:
        m = pattern.match(sku)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}-{max_n + 1:04d}"


def clamp_rate(x: float) -> float:
    x = float(x)
    if x < 0:
        return 0.0
    if x > 100:
        return 100.0
    return x


def validate_cnpj(cnpj: str) -> Optional[str]:
    cnpj = (cnpj or "").strip()
    if not cnpj:
        return None
    if not re.fullmatch(r"\d{14}", cnpj):
        return "CNPJ deve ter 14 dígitos (somente números)."
    return None


def validate_ncm(ncm: str, required: bool) -> Optional[str]:
    ncm = (ncm or "").strip()
    if not ncm:
        return "NCM é obrigatório para 'Bem'." if required else None
    if not re.fullmatch(r"\d{8}", ncm):
        return "NCM deve ter 8 dígitos (somente números)."
    return None


def validate_nbs(nbs: str, required: bool) -> Optional[str]:
    nbs = (nbs or "").strip()
    if not nbs:
        return "NBS é obrigatório para 'Serviço'." if required else None
    if not re.fullmatch(r"\d{9}", nbs):
        return "NBS deve ter 9 dígitos (somente números)."
    return None


def ean13_checksum_ok(ean13: str) -> bool:
    if not re.fullmatch(r"\d{13}", ean13):
        return False
    digits = [int(c) for c in ean13]
    s = 0
    for i in range(12):
        s += digits[i] * (3 if (i % 2 == 1) else 1)
    check = (10 - (s % 10)) % 10
    return check == digits[12]


def validate_ean(ean: str) -> Optional[str]:
    ean = (ean or "").strip()
    if not ean:
        return None
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", ean):
        return "EAN deve ter 8, 12, 13 ou 14 dígitos (somente números)."
    if len(ean) == 13 and not ean13_checksum_ok(ean):
        return "EAN-13 inválido (dígito verificador não confere)."
    return None


def money(x: float) -> str:
    return f"{float(x):.2f}"


# ============================================================
# Regras didáticas (aplicação de tributos por tipo/natureza)
# ============================================================
def suggest_natureza(product_kind: str) -> str:
    return "Prestação de serviço" if product_kind == "Serviço" else "Venda de mercadoria"


def taxes_applicability(product_kind: str, natureza: str) -> Tuple[bool, bool, bool]:
    """
    Retorna flags (aplica_CBS, aplica_IBS, aplica_ISS) de forma didática.
    - Bens: CBS + IBS
    - Serviços: CBS + ISS
    - Natureza "Devolução" mantém a mesma lógica do item (apenas sinal pode ser tratado no futuro)
    """
    if product_kind == "Serviço":
        return True, False, True
    return True, True, False


# ============================================================
# Entidades
# ============================================================
@dataclass
class TaxDefaults:
    cbs_rate: float = 0.0
    ibs_rate: float = 0.0
    iss_rate: float = 0.0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TaxDefaults":
        return TaxDefaults(
            cbs_rate=float(d.get("cbs_rate", 0.0)),
            ibs_rate=float(d.get("ibs_rate", 0.0)),
            iss_rate=float(d.get("iss_rate", 0.0)),
        )


@dataclass
class Supplier:
    id: str
    name: str
    cnpj: str
    email: str
    phone: str
    city: str
    uf: str
    active: bool
    created_at: str
    updated_at: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Supplier":
        return Supplier(
            id=str(d.get("id", uuid.uuid4())),
            name=str(d.get("name", "")),
            cnpj=str(d.get("cnpj", "")),
            email=str(d.get("email", "")),
            phone=str(d.get("phone", "")),
            city=str(d.get("city", "")),
            uf=str(d.get("uf", "")),
            active=bool(d.get("active", True)),
            created_at=str(d.get("created_at", now_iso())),
            updated_at=str(d.get("updated_at", now_iso())),
        )


@dataclass
class Product:
    id: str
    sku: str
    name: str
    kind: str  # "Bem" | "Serviço"
    category: str
    brand: str
    ncm: str
    nbs: str
    ean: str
    supplier_id: str
    price: float
    stock: int
    active: bool
    cbs_rate: float
    ibs_rate: float
    iss_rate: float
    created_at: str
    updated_at: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Product":
        return Product(
            id=str(d.get("id", uuid.uuid4())),
            sku=str(d.get("sku", "")),
            name=str(d.get("name", "")),
            kind=str(d.get("kind", "Bem")),
            category=str(d.get("category", "")),
            brand=str(d.get("brand", "")),
            ncm=str(d.get("ncm", "")),
            nbs=str(d.get("nbs", "")),
            ean=str(d.get("ean", "")),
            supplier_id=str(d.get("supplier_id", "")),
            price=float(d.get("price", 0.0)),
            stock=int(d.get("stock", 0)),
            active=bool(d.get("active", True)),
            cbs_rate=float(d.get("cbs_rate", 0.0)),
            ibs_rate=float(d.get("ibs_rate", 0.0)),
            iss_rate=float(d.get("iss_rate", 0.0)),
            created_at=str(d.get("created_at", now_iso())),
            updated_at=str(d.get("updated_at", now_iso())),
        )


@dataclass
class Movement:
    id: str
    created_at: str
    product_id: str
    mov_type: str  # "Entrada" | "Saída" | "Ajuste"
    natureza: str  # Natureza da operação (didático)
    dest_uf: str
    dest_city: str
    dest_city_ibge: str
    qty: int
    unit_price: float
    base_value: float
    cbs_value: float
    ibs_value: float
    iss_value: float
    total_taxes: float
    total_value: float
    notes: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Movement":
        # Compatibilidade: se o DB antigo não tiver os novos campos, assume vazio
        return Movement(
            id=str(d.get("id", uuid.uuid4())),
            created_at=str(d.get("created_at", now_iso())),
            product_id=str(d.get("product_id", "")),
            mov_type=str(d.get("mov_type", "Entrada")),
            natureza=str(d.get("natureza", d.get("op_nature", "Outros"))),
            dest_uf=str(d.get("dest_uf", "")),
            dest_city=str(d.get("dest_city", "")),
            dest_city_ibge=str(d.get("dest_city_ibge", "")),
            qty=int(d.get("qty", 0)),
            unit_price=float(d.get("unit_price", 0.0)),
            base_value=float(d.get("base_value", 0.0)),
            cbs_value=float(d.get("cbs_value", 0.0)),
            ibs_value=float(d.get("ibs_value", 0.0)),
            iss_value=float(d.get("iss_value", 0.0)),
            total_taxes=float(d.get("total_taxes", 0.0)),
            total_value=float(d.get("total_value", 0.0)),
            notes=str(d.get("notes", "")),
        )


# ============================================================
# DataStore
# ============================================================
class DataStore:
    def __init__(self) -> None:
        self.tax_defaults = TaxDefaults()
        self.suppliers: List[Supplier] = []
        self.products: List[Product] = []
        self.movements: List[Movement] = []

    def supplier_name(self, supplier_id: str) -> str:
        for s in self.suppliers:
            if s.id == supplier_id:
                return s.name
        return ""

    def product_by_id(self, pid: str) -> Optional[Product]:
        for p in self.products:
            if p.id == pid:
                return p
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": {"version": 2, "updated_at": now_iso()},
            "tax_defaults": asdict(self.tax_defaults),
            "suppliers": [asdict(s) for s in self.suppliers],
            "products": [asdict(p) for p in self.products],
            "movements": [asdict(m) for m in self.movements],
        }

    @staticmethod
    def load() -> "DataStore":
        ds = DataStore()
        path = db_path()
        if not path.exists():
            ds.save()
            return ds

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            ds.tax_defaults = TaxDefaults.from_dict(raw.get("tax_defaults", {}))
            ds.suppliers = [Supplier.from_dict(x) for x in raw.get("suppliers", []) if isinstance(x, dict)]
            ds.products = [Product.from_dict(x) for x in raw.get("products", []) if isinstance(x, dict)]
            ds.movements = [Movement.from_dict(x) for x in raw.get("movements", []) if isinstance(x, dict)]
        except Exception:
            pass

        return ds

    def save(self) -> None:
        db_path().write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# Table Models
# ============================================================
class SuppliersModel(QAbstractTableModel):
    COLS = [
        ("Nome", "name"),
        ("CNPJ", "cnpj"),
        ("Email", "email"),
        ("Telefone", "phone"),
        ("Cidade", "city"),
        ("UF", "uf"),
        ("Status", "active"),
        ("Atualizado", "updated_at"),
    ]

    def __init__(self, ds: DataStore) -> None:
        super().__init__()
        self.ds = ds

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ds.suppliers)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        s = self.ds.suppliers[index.row()]
        key = self.COLS[index.column()][1]

        if role == Qt.DisplayRole:
            val = getattr(s, key)
            if key == "active":
                return "Ativo" if bool(val) else "Inativo"
            return str(val)

        if role == Qt.UserRole:
            return getattr(s, key)

        return None

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()


class ProductsModel(QAbstractTableModel):
    COLS = [
        ("SKU", "sku"),
        ("Nome", "name"),
        ("Tipo", "kind"),
        ("Categoria", "category"),
        ("Marca", "brand"),
        ("NCM", "ncm"),
        ("NBS", "nbs"),
        ("EAN", "ean"),
        ("Fornecedor", "supplier_id"),
        ("Preço", "price"),
        ("Estoque", "stock"),
        ("CBS %", "cbs_rate"),
        ("IBS %", "ibs_rate"),
        ("ISS %", "iss_rate"),
        ("Status", "active"),
        ("Atualizado", "updated_at"),
    ]

    def __init__(self, ds: DataStore) -> None:
        super().__init__()
        self.ds = ds

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ds.products)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        p = self.ds.products[index.row()]
        key = self.COLS[index.column()][1]

        if role == Qt.DisplayRole:
            if key == "supplier_id":
                return self.ds.supplier_name(p.supplier_id)
            val = getattr(p, key)
            if key == "active":
                return "Ativo" if bool(val) else "Inativo"
            if key in ("price", "cbs_rate", "ibs_rate", "iss_rate"):
                return money(val)
            return str(val)

        if role == Qt.UserRole:
            if key == "supplier_id":
                return self.ds.supplier_name(p.supplier_id)
            return getattr(p, key)

        if role == Qt.TextAlignmentRole:
            if key in ("price", "stock", "cbs_rate", "ibs_rate", "iss_rate"):
                return int(Qt.AlignVCenter | Qt.AlignRight)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        return None

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def categories(self) -> List[str]:
        return sorted({p.category.strip() for p in self.ds.products if p.category.strip()})

    def brands(self) -> List[str]:
        return sorted({p.brand.strip() for p in self.ds.products if p.brand.strip()})

    def kinds(self) -> List[str]:
        return sorted({p.kind.strip() for p in self.ds.products if p.kind.strip()})


class MovementsModel(QAbstractTableModel):
    COLS = [
        ("Data", "created_at"),
        ("Mov", "mov_type"),
        ("Natureza", "natureza"),
        ("UF", "dest_uf"),
        ("Município", "dest_city"),
        ("IBGE", "dest_city_ibge"),
        ("Produto", "product_id"),
        ("Qtd", "qty"),
        ("Unit", "unit_price"),
        ("Base", "base_value"),
        ("CBS", "cbs_value"),
        ("IBS", "ibs_value"),
        ("ISS", "iss_value"),
        ("Impostos", "total_taxes"),
        ("Total", "total_value"),
        ("Obs", "notes"),
    ]

    def __init__(self, ds: DataStore) -> None:
        super().__init__()
        self.ds = ds

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ds.movements)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        m = self.ds.movements[index.row()]
        key = self.COLS[index.column()][1]

        if role == Qt.DisplayRole:
            if key == "product_id":
                p = self.ds.product_by_id(m.product_id)
                return f"{p.sku} - {p.name}" if p else "(produto removido)"
            val = getattr(m, key)
            if key in ("unit_price", "base_value", "cbs_value", "ibs_value", "iss_value", "total_taxes", "total_value"):
                return money(val)
            return str(val)

        if role == Qt.UserRole:
            return getattr(m, key)

        if role == Qt.TextAlignmentRole:
            if key in ("qty", "unit_price", "base_value", "cbs_value", "ibs_value", "iss_value", "total_taxes", "total_value"):
                return int(Qt.AlignVCenter | Qt.AlignRight)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        return None

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()


# ============================================================
# Proxy de Filtro (Produtos)
# ============================================================
class ProductsFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._search = ""
        self._only_active = False
        self._kind = "Todos"
        self._category = "Todas"
        self._brand = "Todas"

    def set_search(self, text: str) -> None:
        self._search = (text or "").strip().lower()
        self.invalidateFilter()

    def set_only_active(self, on: bool) -> None:
        self._only_active = bool(on)
        self.invalidateFilter()

    def set_kind(self, kind: str) -> None:
        self._kind = kind or "Todos"
        self.invalidateFilter()

    def set_category(self, cat: str) -> None:
        self._category = cat or "Todas"
        self.invalidateFilter()

    def set_brand(self, brand: str) -> None:
        self._brand = brand or "Todas"
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        def get_user(col_key: str) -> Any:
            col_idx = [k for _, k in model.COLS].index(col_key)
            idx = model.index(source_row, col_idx, source_parent)
            return model.data(idx, Qt.UserRole)

        active = bool(get_user("active"))
        kind = str(get_user("kind") or "")
        category = str(get_user("category") or "")
        brand = str(get_user("brand") or "")

        if self._only_active and not active:
            return False
        if self._kind != "Todos" and kind != self._kind:
            return False
        if self._category != "Todas" and category != self._category:
            return False
        if self._brand != "Todas" and brand != self._brand:
            return False

        if self._search:
            sku = str(get_user("sku") or "")
            name = str(get_user("name") or "")
            supplier = str(get_user("supplier_id") or "")
            ncm = str(get_user("ncm") or "")
            nbs = str(get_user("nbs") or "")
            ean = str(get_user("ean") or "")

            hay = f"{sku} {name} {kind} {category} {brand} {supplier} {ncm} {nbs} {ean}".lower()
            if self._search not in hay:
                return False

        return True


# ============================================================
# Dialogs
# ============================================================
class TaxDefaultsDialog(QDialog):
    def __init__(self, parent: QWidget, td: TaxDefaults) -> None:
        super().__init__(parent)
        self.setWindowTitle("Config Fiscal (Simulador) — IBS/CBS/ISS")
        self.setModal(True)

        self.cbs = QDoubleSpinBox()
        self.ibs = QDoubleSpinBox()
        self.iss = QDoubleSpinBox()
        for w in (self.cbs, self.ibs, self.iss):
            w.setDecimals(2)
            w.setRange(0.0, 100.0)

        self.cbs.setValue(float(td.cbs_rate))
        self.ibs.setValue(float(td.ibs_rate))
        self.iss.setValue(float(td.iss_rate))

        form = QFormLayout()
        form.addRow("CBS padrão (%)", self.cbs)
        form.addRow("IBS padrão (%)", self.ibs)
        form.addRow("ISS padrão (%)", self.iss)

        btn_ok = QPushButton("Salvar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(row)
        self.setLayout(root)
        self.resize(520, 200)

    def get_values(self) -> TaxDefaults:
        return TaxDefaults(
            cbs_rate=clamp_rate(float(self.cbs.value())),
            ibs_rate=clamp_rate(float(self.ibs.value())),
            iss_rate=clamp_rate(float(self.iss.value())),
        )


class SupplierDialog(QDialog):
    def __init__(self, parent: QWidget, supplier: Optional[Supplier] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fornecedor" if supplier else "Novo fornecedor")
        self.setModal(True)
        self._supplier_in = supplier

        self.name = QLineEdit()
        self.cnpj = QLineEdit()
        self.email = QLineEdit()
        self.phone = QLineEdit()
        self.city = QLineEdit()
        self.uf = QLineEdit()
        self.active = QCheckBox("Ativo")

        form = QFormLayout()
        form.addRow("Nome *", self.name)
        form.addRow("CNPJ (14 dígitos)", self.cnpj)
        form.addRow("Email", self.email)
        form.addRow("Telefone", self.phone)
        form.addRow("Cidade", self.city)
        form.addRow("UF", self.uf)
        form.addRow("", self.active)

        btn_ok = QPushButton("Salvar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(row)
        self.setLayout(root)

        if supplier:
            self.name.setText(supplier.name)
            self.cnpj.setText(supplier.cnpj)
            self.email.setText(supplier.email)
            self.phone.setText(supplier.phone)
            self.city.setText(supplier.city)
            self.uf.setText(supplier.uf)
            self.active.setChecked(bool(supplier.active))
        else:
            self.active.setChecked(True)

        self.resize(600, 260)

    def get_supplier(self) -> Optional[Supplier]:
        name = self.name.text().strip()
        if not name:
            QMessageBox.critical(self, "Validação", "Nome é obrigatório.")
            return None

        err = validate_cnpj(self.cnpj.text().strip())
        if err:
            QMessageBox.critical(self, "Validação", err)
            return None

        if self._supplier_in:
            sid = self._supplier_in.id
            created_at = self._supplier_in.created_at
        else:
            sid = str(uuid.uuid4())
            created_at = now_iso()

        return Supplier(
            id=sid,
            name=name,
            cnpj=self.cnpj.text().strip(),
            email=self.email.text().strip(),
            phone=self.phone.text().strip(),
            city=self.city.text().strip(),
            uf=self.uf.text().strip().upper(),
            active=bool(self.active.isChecked()),
            created_at=created_at,
            updated_at=now_iso(),
        )

    def accept(self) -> None:
        if self.get_supplier() is None:
            return
        super().accept()


class ProductDialog(QDialog):
    def __init__(self, parent: QWidget, ds: DataStore, product: Optional[Product] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Produto" if product else "Novo produto")
        self.setModal(True)
        self.ds = ds
        self._product_in = product

        self.sku = QLineEdit()
        self.sku.setReadOnly(True)

        self.name = QLineEdit()
        self.kind = QComboBox()
        self.kind.addItems(["Bem", "Serviço"])

        self.category = QLineEdit()
        self.brand = QLineEdit()
        self.ncm = QLineEdit()
        self.nbs = QLineEdit()
        self.ean = QLineEdit()

        self.supplier = QComboBox()
        self._reload_supplier_combo()

        self.price = QDoubleSpinBox()
        self.price.setRange(0.0, 999999999.0)
        self.price.setDecimals(2)

        self.stock = QSpinBox()
        self.stock.setRange(0, 10**9)

        self.cbs = QDoubleSpinBox()
        self.ibs = QDoubleSpinBox()
        self.iss = QDoubleSpinBox()
        for w in (self.cbs, self.ibs, self.iss):
            w.setRange(0.0, 100.0)
            w.setDecimals(2)

        self.active = QCheckBox("Ativo")

        form = QFormLayout()
        form.addRow("SKU", self.sku)
        form.addRow("Nome *", self.name)
        form.addRow("Tipo (Bem/Serviço) *", self.kind)
        form.addRow("Categoria *", self.category)
        form.addRow("Marca", self.brand)
        form.addRow("NCM (Bem)", self.ncm)
        form.addRow("NBS (Serviço)", self.nbs)
        form.addRow("EAN", self.ean)
        form.addRow("Fornecedor", self.supplier)
        form.addRow("Preço", self.price)
        form.addRow("Estoque", self.stock)
        form.addRow("CBS (%)", self.cbs)
        form.addRow("IBS (%)", self.ibs)
        form.addRow("ISS (%)", self.iss)
        form.addRow("", self.active)

        btn_ok = QPushButton("Salvar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(row)
        self.setLayout(root)

        self.cbs.setValue(float(ds.tax_defaults.cbs_rate))
        self.ibs.setValue(float(ds.tax_defaults.ibs_rate))
        self.iss.setValue(float(ds.tax_defaults.iss_rate))

        if product:
            self.sku.setText(product.sku)
            self.name.setText(product.name)
            self.kind.setCurrentText(product.kind)
            self.category.setText(product.category)
            self.brand.setText(product.brand)
            self.ncm.setText(product.ncm)
            self.nbs.setText(product.nbs)
            self.ean.setText(product.ean)
            self._select_supplier(product.supplier_id)
            self.price.setValue(float(product.price))
            self.stock.setValue(int(product.stock))
            self.cbs.setValue(float(product.cbs_rate))
            self.ibs.setValue(float(product.ibs_rate))
            self.iss.setValue(float(product.iss_rate))
            self.active.setChecked(bool(product.active))
        else:
            self.active.setChecked(True)

        self.kind.currentTextChanged.connect(self._toggle_fields_by_kind)
        self.category.textChanged.connect(self._maybe_update_sku)

        self._toggle_fields_by_kind(self.kind.currentText())
        self._maybe_update_sku()

        self.resize(650, 520)

    def _reload_supplier_combo(self) -> None:
        self.supplier.clear()
        self.supplier.addItem("(sem fornecedor)", "")
        for s in sorted(self.ds.suppliers, key=lambda x: x.name.lower()):
            if s.active:
                self.supplier.addItem(s.name, s.id)

    def _select_supplier(self, supplier_id: str) -> None:
        idx = self.supplier.findData(supplier_id)
        self.supplier.setCurrentIndex(idx if idx >= 0 else 0)

    def _toggle_fields_by_kind(self, kind: str) -> None:
        is_bem = (kind == "Bem")
        self.ncm.setEnabled(is_bem)
        self.nbs.setEnabled(not is_bem)

    def _maybe_update_sku(self) -> None:
        if self._product_in:
            return
        cat = self.category.text().strip()
        if not cat:
            self.sku.setText("")
            return
        existing = [p.sku for p in self.ds.products]
        self.sku.setText(generate_sku(cat, existing))

    def get_product(self) -> Optional[Product]:
        name = self.name.text().strip()
        kind = self.kind.currentText().strip()
        category = self.category.text().strip()

        if not name:
            QMessageBox.critical(self, "Validação", "Nome é obrigatório.")
            return None
        if not category:
            QMessageBox.critical(self, "Validação", "Categoria é obrigatória.")
            return None
        if kind not in ("Bem", "Serviço"):
            QMessageBox.critical(self, "Validação", "Tipo inválido.")
            return None

        ncm = self.ncm.text().strip()
        nbs = self.nbs.text().strip()

        err = validate_ncm(ncm, required=(kind == "Bem"))
        if err:
            QMessageBox.critical(self, "Validação", err)
            return None

        err = validate_nbs(nbs, required=(kind == "Serviço"))
        if err:
            QMessageBox.critical(self, "Validação", err)
            return None

        err = validate_ean(self.ean.text().strip())
        if err:
            QMessageBox.critical(self, "Validação", err)
            return None

        if self._product_in:
            pid = self._product_in.id
            sku = self._product_in.sku
            created_at = self._product_in.created_at
        else:
            pid = str(uuid.uuid4())
            sku = self.sku.text().strip()
            if not sku:
                sku = generate_sku(category, [p.sku for p in self.ds.products])
            created_at = now_iso()

        return Product(
            id=pid,
            sku=sku,
            name=name,
            kind=kind,
            category=category,
            brand=self.brand.text().strip(),
            ncm=ncm,
            nbs=nbs,
            ean=self.ean.text().strip(),
            supplier_id=str(self.supplier.currentData() or ""),
            price=float(self.price.value()),
            stock=int(self.stock.value()),
            active=bool(self.active.isChecked()),
            cbs_rate=clamp_rate(float(self.cbs.value())),
            ibs_rate=clamp_rate(float(self.ibs.value())),
            iss_rate=clamp_rate(float(self.iss.value())),
            created_at=created_at,
            updated_at=now_iso(),
        )

    def accept(self) -> None:
        if self.get_product() is None:
            return
        super().accept()


class MovementDialog(QDialog):
    def __init__(self, parent: QWidget, ds: DataStore) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nova movimentação — Incidência (UF/Município) + Natureza + IBS/CBS/ISS (didático)")
        self.setModal(True)
        self.ds = ds

        self.product = QComboBox()
        for p in sorted(ds.products, key=lambda x: x.name.lower()):
            if p.active:
                self.product.addItem(f"{p.sku} - {p.name}", p.id)

        self.mov_type = QComboBox()
        self.mov_type.addItems(["Entrada", "Saída", "Ajuste"])

        self.natureza = QComboBox()
        self.natureza.addItems(NATUREZA_LIST)

        self.dest_uf = QComboBox()
        self.dest_uf.addItem("")  # vazio
        for uf in UF_LIST:
            self.dest_uf.addItem(uf)

        self.dest_city = QLineEdit()
        self.dest_city.setPlaceholderText("Ex.: São Paulo")

        self.dest_city_ibge = QLineEdit()
        self.dest_city_ibge.setPlaceholderText("Opcional (código IBGE do município)")

        self.qty = QSpinBox()
        self.qty.setRange(0, 10**9)
        self.qty.setValue(1)

        self.unit_price = QDoubleSpinBox()
        self.unit_price.setRange(0.0, 999999999.0)
        self.unit_price.setDecimals(2)

        self.cbs = QDoubleSpinBox()
        self.ibs = QDoubleSpinBox()
        self.iss = QDoubleSpinBox()
        for w in (self.cbs, self.ibs, self.iss):
            w.setRange(0.0, 100.0)
            w.setDecimals(2)

        self.notes = QLineEdit()
        self.preview = QLabel("")
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.lbl_aplic = QLabel("")
        self.lbl_aplic.setTextInteractionFlags(Qt.TextSelectableByMouse)

        form = QFormLayout()
        form.addRow("Produto", self.product)
        form.addRow("Movimentação (Entrada/Saída/Ajuste)", self.mov_type)
        form.addRow("Natureza da operação", self.natureza)
        form.addRow("UF destino (incidência)", self.dest_uf)
        form.addRow("Município destino (incidência)", self.dest_city)
        form.addRow("Município IBGE (opcional)", self.dest_city_ibge)
        form.addRow("Quantidade", self.qty)
        form.addRow("Valor unitário (referência)", self.unit_price)
        form.addRow("CBS (%)", self.cbs)
        form.addRow("IBS (%)", self.ibs)
        form.addRow("ISS (%)", self.iss)
        form.addRow("Observação", self.notes)
        form.addRow("Aplicação (didático)", self.lbl_aplic)
        form.addRow("Prévia", self.preview)

        btn_ok = QPushButton("Salvar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(row)
        self.setLayout(root)

        # events
        self.product.currentIndexChanged.connect(self._load_from_product)
        self.mov_type.currentTextChanged.connect(self._update_preview)
        self.natureza.currentTextChanged.connect(self._update_preview)
        self.qty.valueChanged.connect(self._update_preview)
        self.unit_price.valueChanged.connect(self._update_preview)
        self.cbs.valueChanged.connect(self._update_preview)
        self.ibs.valueChanged.connect(self._update_preview)
        self.iss.valueChanged.connect(self._update_preview)

        self._load_from_product()
        self.resize(820, 520)

    def _load_from_product(self) -> None:
        pid = str(self.product.currentData() or "")
        p = self.ds.product_by_id(pid)
        if not p:
            return

        # unit price inicial: preço do produto
        self.unit_price.setValue(float(p.price))

        # taxas iniciais: do produto (se tiver) senão padrão
        self.cbs.setValue(float(p.cbs_rate) if p.cbs_rate else float(self.ds.tax_defaults.cbs_rate))
        self.ibs.setValue(float(p.ibs_rate) if p.ibs_rate else float(self.ds.tax_defaults.ibs_rate))
        self.iss.setValue(float(p.iss_rate) if p.iss_rate else float(self.ds.tax_defaults.iss_rate))

        # natureza sugerida
        sug = suggest_natureza(p.kind)
        idx = self.natureza.findText(sug)
        if idx >= 0:
            self.natureza.setCurrentIndex(idx)

        self._update_preview()

    def _update_preview(self) -> None:
        pid = str(self.product.currentData() or "")
        p = self.ds.product_by_id(pid)
        if not p:
            self.preview.setText("")
            self.lbl_aplic.setText("")
            return

        natureza = self.natureza.currentText()
        aplica_cbs, aplica_ibs, aplica_iss = taxes_applicability(p.kind, natureza)

        qty = int(self.qty.value())
        unit = float(self.unit_price.value())
        base = qty * unit

        cbs_rate = clamp_rate(float(self.cbs.value()))
        ibs_rate = clamp_rate(float(self.ibs.value()))
        iss_rate = clamp_rate(float(self.iss.value()))

        cbs_v = base * (cbs_rate / 100.0) if aplica_cbs else 0.0
        ibs_v = base * (ibs_rate / 100.0) if aplica_ibs else 0.0
        iss_v = base * (iss_rate / 100.0) if aplica_iss else 0.0

        taxes = cbs_v + ibs_v + iss_v
        total = base + taxes

        self.lbl_aplic.setText(
            f"Tipo: {p.kind} | Natureza: {natureza} | Aplica: "
            f"{'CBS' if aplica_cbs else ''} "
            f"{'IBS' if aplica_ibs else ''} "
            f"{'ISS' if aplica_iss else ''}".strip()
        )

        self.preview.setText(
            f"Base: {base:.2f} | CBS: {cbs_v:.2f} | IBS: {ibs_v:.2f} | ISS: {iss_v:.2f} | "
            f"Impostos: {taxes:.2f} | Total: {total:.2f}"
        )

    def get_movement(self) -> Optional[Movement]:
        pid = str(self.product.currentData() or "")
        p = self.ds.product_by_id(pid)
        if not p:
            QMessageBox.critical(self, "Validação", "Produto inválido.")
            return None

        mov_type = self.mov_type.currentText()
        natureza = self.natureza.currentText().strip() or "Outros"

        # Incidência: exigimos UF/Município para Saída (didático)
        dest_uf = self.dest_uf.currentText().strip().upper()
        dest_city = self.dest_city.text().strip()
        dest_ibge = self.dest_city_ibge.text().strip()

        if mov_type == "Saída":
            if not dest_uf:
                QMessageBox.critical(self, "Validação", "Para SAÍDA, UF destino é obrigatório (incidência).")
                return None
            if not dest_city:
                QMessageBox.critical(self, "Validação", "Para SAÍDA, Município destino é obrigatório (incidência).")
                return None
        else:
            # Entrada/Ajuste podem ficar em branco
            if dest_uf and dest_uf not in UF_LIST:
                QMessageBox.critical(self, "Validação", "UF inválida.")
                return None

        qty = int(self.qty.value())
        if mov_type in ("Entrada", "Saída") and qty <= 0:
            QMessageBox.critical(self, "Validação", "Quantidade deve ser > 0.")
            return None

        unit = float(self.unit_price.value())
        base = qty * unit

        aplica_cbs, aplica_ibs, aplica_iss = taxes_applicability(p.kind, natureza)

        cbs_rate = clamp_rate(float(self.cbs.value()))
        ibs_rate = clamp_rate(float(self.ibs.value()))
        iss_rate = clamp_rate(float(self.iss.value()))

        cbs_v = base * (cbs_rate / 100.0) if aplica_cbs else 0.0
        ibs_v = base * (ibs_rate / 100.0) if aplica_ibs else 0.0
        iss_v = base * (iss_rate / 100.0) if aplica_iss else 0.0

        taxes = cbs_v + ibs_v + iss_v
        total = base + taxes

        return Movement(
            id=str(uuid.uuid4()),
            created_at=now_iso(),
            product_id=pid,
            mov_type=mov_type,
            natureza=natureza,
            dest_uf=dest_uf,
            dest_city=dest_city,
            dest_city_ibge=dest_ibge,
            qty=qty,
            unit_price=unit,
            base_value=base,
            cbs_value=cbs_v,
            ibs_value=ibs_v,
            iss_value=iss_v,
            total_taxes=taxes,
            total_value=total,
            notes=self.notes.text().strip(),
        )

    def accept(self) -> None:
        if self.get_movement() is None:
            return
        super().accept()


# ============================================================
# Main Window
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mini-ERP (PySide6) — Reforma (didático): IBS/CBS/ISS + Incidência + Natureza + Relatórios")
        self.ds = DataStore.load()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.sup_model = SuppliersModel(self.ds)
        self.prod_model = ProductsModel(self.ds)
        self.mov_model = MovementsModel(self.ds)

        self.prod_proxy = ProductsFilterProxy()
        self.prod_proxy.setSourceModel(self.prod_model)

        self._build_products_tab()
        self._build_suppliers_tab()
        self._build_movements_tab()
        self._build_reports_tab()
        self._build_toolbar()

        self._refresh_product_filters()
        self._update_status()

        self.resize(1500, 760)

    # ----------------- Tabs -----------------
    def _build_products_tab(self) -> None:
        w = QWidget()
        layout = QVBoxLayout()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Pesquisar (SKU, Nome, Tipo, Categoria, Marca, Fornecedor, NCM/NBS/EAN)...")
        self.txt_search.textChanged.connect(self.prod_proxy.set_search)

        self.chk_only_active = QCheckBox("Somente ativos")
        self.chk_only_active.stateChanged.connect(lambda _: self.prod_proxy.set_only_active(self.chk_only_active.isChecked()))

        self.cmb_kind = QComboBox()
        self.cmb_kind.currentTextChanged.connect(self.prod_proxy.set_kind)

        self.cmb_category = QComboBox()
        self.cmb_category.currentTextChanged.connect(self.prod_proxy.set_category)

        self.cmb_brand = QComboBox()
        self.cmb_brand.currentTextChanged.connect(self.prod_proxy.set_brand)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Buscar:"))
        filter_row.addWidget(self.txt_search, 2)
        filter_row.addSpacing(10)
        filter_row.addWidget(self.chk_only_active)
        filter_row.addSpacing(10)
        filter_row.addWidget(QLabel("Tipo:"))
        filter_row.addWidget(self.cmb_kind)
        filter_row.addWidget(QLabel("Categoria:"))
        filter_row.addWidget(self.cmb_category)
        filter_row.addWidget(QLabel("Marca:"))
        filter_row.addWidget(self.cmb_brand)

        btn_row = QHBoxLayout()
        btn_new = QPushButton("Novo")
        btn_edit = QPushButton("Editar")
        btn_toggle = QPushButton("Ativar/Inativar")
        btn_del = QPushButton("Excluir")
        btn_imp = QPushButton("Importar CSV")
        btn_exp = QPushButton("Exportar CSV")

        btn_new.clicked.connect(self.new_product)
        btn_edit.clicked.connect(self.edit_product)
        btn_toggle.clicked.connect(self.toggle_product)
        btn_del.clicked.connect(self.delete_product)
        btn_imp.clicked.connect(self.import_products_csv)
        btn_exp.clicked.connect(self.export_products_csv)

        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_toggle)
        btn_row.addWidget(btn_del)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_imp)
        btn_row.addWidget(btn_exp)

        self.tbl_products = QTableView()
        self.tbl_products.setModel(self.prod_proxy)
        self.tbl_products.setSortingEnabled(True)
        self.tbl_products.setSelectionBehavior(QTableView.SelectRows)
        self.tbl_products.setSelectionMode(QTableView.ExtendedSelection)
        self.tbl_products.doubleClicked.connect(self.edit_product)

        layout.addLayout(filter_row)
        layout.addLayout(btn_row)
        layout.addWidget(self.tbl_products, 1)
        w.setLayout(layout)
        self.tabs.addTab(w, "Produtos")

    def _build_suppliers_tab(self) -> None:
        w = QWidget()
        layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        btn_new = QPushButton("Novo")
        btn_edit = QPushButton("Editar")
        btn_toggle = QPushButton("Ativar/Inativar")
        btn_del = QPushButton("Excluir")

        btn_new.clicked.connect(self.new_supplier)
        btn_edit.clicked.connect(self.edit_supplier)
        btn_toggle.clicked.connect(self.toggle_supplier)
        btn_del.clicked.connect(self.delete_supplier)

        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_toggle)
        btn_row.addWidget(btn_del)
        btn_row.addStretch(1)

        self.tbl_suppliers = QTableView()
        self.tbl_suppliers.setModel(self.sup_model)
        self.tbl_suppliers.setSortingEnabled(True)
        self.tbl_suppliers.setSelectionBehavior(QTableView.SelectRows)
        self.tbl_suppliers.setSelectionMode(QTableView.ExtendedSelection)
        self.tbl_suppliers.doubleClicked.connect(self.edit_supplier)

        layout.addLayout(btn_row)
        layout.addWidget(self.tbl_suppliers, 1)
        w.setLayout(layout)
        self.tabs.addTab(w, "Fornecedores")

    def _build_movements_tab(self) -> None:
        w = QWidget()
        layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        btn_new = QPushButton("Nova movimentação")
        btn_export = QPushButton("Exportar CSV")
        btn_new.clicked.connect(self.new_movement)
        btn_export.clicked.connect(self.export_movements_csv)

        btn_row.addWidget(btn_new)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_export)

        self.tbl_mov = QTableView()
        self.tbl_mov.setModel(self.mov_model)
        self.tbl_mov.setSortingEnabled(True)
        self.tbl_mov.setSelectionBehavior(QTableView.SelectRows)
        self.tbl_mov.setSelectionMode(QTableView.ExtendedSelection)

        layout.addLayout(btn_row)
        layout.addWidget(self.tbl_mov, 1)
        w.setLayout(layout)
        self.tabs.addTab(w, "Movimentações")

    def _build_reports_tab(self) -> None:
        w = QWidget()
        layout = QVBoxLayout()

        top = QHBoxLayout()
        self.sp_low = QSpinBox()
        self.sp_low.setRange(0, 10**9)
        self.sp_low.setValue(5)

        btn = QPushButton("Gerar relatórios fiscais (didático)")
        btn.clicked.connect(self.generate_report)

        btn_export = QPushButton("Exportar relatório (TXT)")
        btn_export.clicked.connect(self.export_report_txt)

        top.addWidget(QLabel("Baixo estoque ≤"))
        top.addWidget(self.sp_low)
        top.addStretch(1)
        top.addWidget(btn)
        top.addWidget(btn_export)

        self.txt_report = QPlainTextEdit()
        self.txt_report.setReadOnly(True)

        layout.addLayout(top)
        layout.addWidget(self.txt_report, 1)
        w.setLayout(layout)
        self.tabs.addTab(w, "Relatórios")

    def _build_toolbar(self) -> None:
        tb = QToolBar("Ações")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_tax = QAction("Config Fiscal", self)
        act_tax.triggered.connect(self.configure_tax)

        act_reload = QAction("Recarregar DB", self)
        act_reload.triggered.connect(self.reload_db)

        act_about = QAction("Sobre", self)
        act_about.triggered.connect(self.about)

        tb.addAction(act_tax)
        tb.addAction(act_reload)
        tb.addAction(act_about)

    # ----------------- Helpers -----------------
    def _update_status(self) -> None:
        total_p = len(self.ds.products)
        active_p = sum(1 for p in self.ds.products if p.active)
        total_s = len(self.ds.suppliers)
        total_m = len(self.ds.movements)
        showing = self.prod_proxy.rowCount()

        self.status.showMessage(
            f"Produtos: {total_p} (Ativos {active_p}) | Fornecedores: {total_s} | Movs: {total_m} | "
            f"Exibindo produtos (filtro): {showing} | DB: {db_path()}"
        )

    def _refresh_product_filters(self) -> None:
        cur_kind = self.cmb_kind.currentText() or "Todos"
        cur_cat = self.cmb_category.currentText() or "Todas"
        cur_brand = self.cmb_brand.currentText() or "Todas"

        self.cmb_kind.blockSignals(True)
        self.cmb_category.blockSignals(True)
        self.cmb_brand.blockSignals(True)

        self.cmb_kind.clear()
        self.cmb_kind.addItem("Todos")
        for k in self.prod_model.kinds():
            self.cmb_kind.addItem(k)

        self.cmb_category.clear()
        self.cmb_category.addItem("Todas")
        for c in self.prod_model.categories():
            self.cmb_category.addItem(c)

        self.cmb_brand.clear()
        self.cmb_brand.addItem("Todas")
        for b in self.prod_model.brands():
            self.cmb_brand.addItem(b)

        def restore(combo: QComboBox, val: str) -> None:
            idx = combo.findText(val)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

        restore(self.cmb_kind, cur_kind)
        restore(self.cmb_category, cur_cat)
        restore(self.cmb_brand, cur_brand)

        self.cmb_kind.blockSignals(False)
        self.cmb_category.blockSignals(False)
        self.cmb_brand.blockSignals(False)

    def _selected_product_source_rows(self) -> List[int]:
        sel = self.tbl_products.selectionModel().selectedRows()
        proxy_rows = sorted({i.row() for i in sel})
        src_rows: List[int] = []
        for r in proxy_rows:
            src = self.prod_proxy.mapToSource(self.prod_proxy.index(r, 0)).row()
            src_rows.append(src)
        return sorted(set(src_rows))

    def _current_product_source_row(self) -> Optional[int]:
        idx = self.tbl_products.currentIndex()
        if not idx.isValid():
            return None
        return self.prod_proxy.mapToSource(idx).row()

    def _selected_supplier_rows(self) -> List[int]:
        sel = self.tbl_suppliers.selectionModel().selectedRows()
        return sorted({i.row() for i in sel})

    def _current_supplier_row(self) -> Optional[int]:
        idx = self.tbl_suppliers.currentIndex()
        return idx.row() if idx.isValid() else None

    # ----------------- Produtos -----------------
    def new_product(self) -> None:
        dlg = ProductDialog(self, self.ds, product=None)
        if dlg.exec() != QDialog.Accepted:
            return
        p = dlg.get_product()
        if not p:
            return

        self.ds.products.append(p)
        self.ds.save()
        self.prod_model.refresh()
        self._refresh_product_filters()
        self._update_status()

    def edit_product(self) -> None:
        row = self._current_product_source_row()
        if row is None:
            QMessageBox.information(self, "Editar", "Selecione um produto.")
            return
        prod = self.ds.products[row]

        dlg = ProductDialog(self, self.ds, product=prod)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.get_product()
        if not updated:
            return

        self.ds.products[row] = updated
        self.ds.save()
        self.prod_model.refresh()
        self._refresh_product_filters()
        self._update_status()

    def toggle_product(self) -> None:
        rows = self._selected_product_source_rows()
        if not rows:
            QMessageBox.information(self, "Ativar/Inativar", "Selecione um ou mais produtos.")
            return

        actives = sum(1 for r in rows if self.ds.products[r].active)
        target = False if actives >= (len(rows) / 2) else True

        for r in rows:
            p = self.ds.products[r]
            self.ds.products[r] = Product(**{**asdict(p), "active": target, "updated_at": now_iso()})

        self.ds.save()
        self.prod_model.refresh()
        self._update_status()

    def delete_product(self) -> None:
        rows = self._selected_product_source_rows()
        if not rows:
            QMessageBox.information(self, "Excluir", "Selecione um ou mais produtos.")
            return

        resp = QMessageBox.warning(
            self,
            "Excluir Produto (permanente)",
            "Confirma excluir permanentemente os produtos selecionados?\n"
            "Movimentações relacionadas também serão removidas.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        for r in sorted(set(rows), reverse=True):
            pid = self.ds.products[r].id
            self.ds.movements = [m for m in self.ds.movements if m.product_id != pid]
            self.ds.products.pop(r)

        self.ds.save()
        self.prod_model.refresh()
        self.mov_model.refresh()
        self._refresh_product_filters()
        self._update_status()

    # ----------------- CSV Produtos -----------------
    def export_products_csv(self) -> None:
        suggested = str(Path.home() / "produtos_export.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Produtos (CSV)", suggested, "CSV (*.csv)")
        if not path:
            return

        cols = list(Product.__annotations__.keys())
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(cols)
                for p in self.ds.products:
                    w.writerow([getattr(p, k) for k in cols])
            QMessageBox.information(self, "Exportar", f"Exportado:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"Falha:\n{e}")

    def import_products_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar Produtos (CSV)", str(Path.home()), "CSV (*.csv)")
        if not path:
            return

        cols = list(Product.__annotations__.keys())
        try:
            imported: List[Product] = []
            with open(path, "r", newline="", encoding="utf-8") as f:
                r = csv.reader(f, delimiter=";")
                header = next(r, None)
                if header != cols:
                    raise ValueError("Cabeçalho do CSV não confere com o modelo atual.")
                for row in r:
                    if not row:
                        continue
                    d = dict(zip(header, row))
                    d["price"] = float(str(d.get("price", "0")).replace(",", "."))
                    d["stock"] = int(float(d.get("stock", "0")))
                    d["active"] = str(d.get("active", "true")).strip().lower() in ("true", "1", "sim", "yes")
                    d["cbs_rate"] = float(str(d.get("cbs_rate", "0")).replace(",", "."))
                    d["ibs_rate"] = float(str(d.get("ibs_rate", "0")).replace(",", "."))
                    d["iss_rate"] = float(str(d.get("iss_rate", "0")).replace(",", "."))
                    imported.append(Product.from_dict(d))

            cur = {p.id: p for p in self.ds.products}
            for p in imported:
                cur[p.id] = p
            self.ds.products = list(cur.values())

            self.ds.save()
            self.prod_model.refresh()
            self._refresh_product_filters()
            self._update_status()
            QMessageBox.information(self, "Importar", "Importação concluída.")
        except Exception as e:
            QMessageBox.critical(self, "Importar", f"Falha:\n{e}")

    # ----------------- Fornecedores -----------------
    def new_supplier(self) -> None:
        dlg = SupplierDialog(self, supplier=None)
        if dlg.exec() != QDialog.Accepted:
            return
        s = dlg.get_supplier()
        if not s:
            return

        self.ds.suppliers.append(s)
        self.ds.save()
        self.sup_model.refresh()
        self.prod_model.refresh()
        self._update_status()

    def edit_supplier(self) -> None:
        row = self._current_supplier_row()
        if row is None:
            QMessageBox.information(self, "Editar", "Selecione um fornecedor.")
            return
        sup = self.ds.suppliers[row]

        dlg = SupplierDialog(self, supplier=sup)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.get_supplier()
        if not updated:
            return

        self.ds.suppliers[row] = updated
        self.ds.save()
        self.sup_model.refresh()
        self.prod_model.refresh()
        self._update_status()

    def toggle_supplier(self) -> None:
        rows = self._selected_supplier_rows()
        if not rows:
            QMessageBox.information(self, "Ativar/Inativar", "Selecione um ou mais fornecedores.")
            return

        actives = sum(1 for r in rows if self.ds.suppliers[r].active)
        target = False if actives >= (len(rows) / 2) else True

        for r in rows:
            s = self.ds.suppliers[r]
            self.ds.suppliers[r] = Supplier(**{**asdict(s), "active": target, "updated_at": now_iso()})

        self.ds.save()
        self.sup_model.refresh()
        self.prod_model.refresh()
        self._update_status()

    def delete_supplier(self) -> None:
        rows = self._selected_supplier_rows()
        if not rows:
            QMessageBox.information(self, "Excluir", "Selecione um ou mais fornecedores.")
            return

        resp = QMessageBox.warning(
            self,
            "Excluir Fornecedor (permanente)",
            "Confirma excluir permanentemente?\nProdutos vinculados ficarão sem fornecedor.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        for r in sorted(set(rows), reverse=True):
            sid = self.ds.suppliers[r].id
            for i, p in enumerate(self.ds.products):
                if p.supplier_id == sid:
                    self.ds.products[i] = Product(**{**asdict(p), "supplier_id": "", "updated_at": now_iso()})
            self.ds.suppliers.pop(r)

        self.ds.save()
        self.sup_model.refresh()
        self.prod_model.refresh()
        self._update_status()

    # ----------------- Movimentações -----------------
    def new_movement(self) -> None:
        if not any(p.active for p in self.ds.products):
            QMessageBox.information(self, "Movimentação", "Cadastre ao menos 1 produto ativo.")
            return

        dlg = MovementDialog(self, self.ds)
        if dlg.exec() != QDialog.Accepted:
            return
        m = dlg.get_movement()
        if not m:
            return

        p = self.ds.product_by_id(m.product_id)
        if not p:
            QMessageBox.critical(self, "Erro", "Produto não encontrado.")
            return

        # impacto no estoque
        if m.mov_type == "Entrada":
            new_stock = p.stock + m.qty
        elif m.mov_type == "Saída":
            if p.stock < m.qty:
                QMessageBox.critical(self, "Validação", "Estoque insuficiente para saída.")
                return
            new_stock = p.stock - m.qty
        else:
            new_stock = m.qty  # Ajuste

        for i, px in enumerate(self.ds.products):
            if px.id == p.id:
                self.ds.products[i] = Product(**{**asdict(px), "stock": int(new_stock), "updated_at": now_iso()})
                break

        self.ds.movements.append(m)
        self.ds.save()

        self.prod_model.refresh()
        self.mov_model.refresh()
        self._update_status()

    def export_movements_csv(self) -> None:
        suggested = str(Path.home() / "movimentacoes_export.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Movimentações (CSV)", suggested, "CSV (*.csv)")
        if not path:
            return

        cols = list(Movement.__annotations__.keys())
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(cols)
                for m in self.ds.movements:
                    w.writerow([getattr(m, k) for k in cols])
            QMessageBox.information(self, "Exportar", f"Exportado:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"Falha:\n{e}")

    # ----------------- Fiscal -----------------
    def configure_tax(self) -> None:
        dlg = TaxDefaultsDialog(self, self.ds.tax_defaults)
        if dlg.exec() != QDialog.Accepted:
            return
        self.ds.tax_defaults = dlg.get_values()
        self.ds.save()
        QMessageBox.information(self, "Fiscal", "Alíquotas padrão atualizadas.")

    # ----------------- Relatórios -----------------
    def generate_report(self) -> None:
        low = int(self.sp_low.value())
        lines: List[str] = []

        lines.append("RELATÓRIOS FISCAIS (DIDÁTICOS) — Mini-ERP PLUS")
        lines.append(f"Data/Hora: {now_iso()}")
        lines.append(f"DB: {db_path()}")
        lines.append("")

        # Estoque / base
        total_p = len(self.ds.products)
        active_p = sum(1 for p in self.ds.products if p.active)
        lines.append(f"Produtos: {total_p} | Ativos: {active_p}")

        low_list = [p for p in self.ds.products if p.active and p.stock <= low]
        lines.append("")
        lines.append(f"Baixo estoque (≤ {low}): {len(low_list)} item(ns)")
        for p in sorted(low_list, key=lambda x: x.stock):
            lines.append(f"- {p.sku} | {p.name} | Estoque: {p.stock}")

        inv_value = sum(float(p.price) * int(p.stock) for p in self.ds.products if p.active)
        lines.append("")
        lines.append(f"Valor de estoque (referência): {inv_value:.2f}")

        # Movimentações: foco fiscal em SAÍDAS
        sales = [m for m in self.ds.movements if m.mov_type == "Saída"]
        lines.append("")
        lines.append(f"Saídas registradas: {len(sales)}")

        base_total = sum(m.base_value for m in sales)
        cbs_total = sum(m.cbs_value for m in sales)
        ibs_total = sum(m.ibs_value for m in sales)
        iss_total = sum(m.iss_value for m in sales)
        taxes_total = sum(m.total_taxes for m in sales)
        total_total = sum(m.total_value for m in sales)

        lines.append("")
        lines.append("Totais (Saídas)")
        lines.append(f"- Base: {base_total:.2f}")
        lines.append(f"- CBS:  {cbs_total:.2f}")
        lines.append(f"- IBS:  {ibs_total:.2f}")
        lines.append(f"- ISS:  {iss_total:.2f}")
        lines.append(f"- Impostos: {taxes_total:.2f}")
        lines.append(f"- Total (Base+Impostos): {total_total:.2f}")

        # Index auxiliar: produto por id
        pmap = {p.id: p for p in self.ds.products}

        # Totais por Tipo (Bem/Serviço)
        by_kind = defaultdict(lambda: {"base": 0.0, "cbs": 0.0, "ibs": 0.0, "iss": 0.0, "tax": 0.0, "tot": 0.0, "count": 0})
        for m in sales:
            pk = pmap.get(m.product_id)
            kind = pk.kind if pk else "Desconhecido"
            by_kind[kind]["base"] += m.base_value
            by_kind[kind]["cbs"] += m.cbs_value
            by_kind[kind]["ibs"] += m.ibs_value
            by_kind[kind]["iss"] += m.iss_value
            by_kind[kind]["tax"] += m.total_taxes
            by_kind[kind]["tot"] += m.total_value
            by_kind[kind]["count"] += 1

        lines.append("")
        lines.append("Totais por Tipo (Saídas)")
        for kind, d in sorted(by_kind.items(), key=lambda x: x[0]):
            lines.append(
                f"- {kind}: qtd {d['count']} | base {d['base']:.2f} | CBS {d['cbs']:.2f} | IBS {d['ibs']:.2f} | "
                f"ISS {d['iss']:.2f} | impostos {d['tax']:.2f}"
            )

        # Totais por Natureza
        by_nat = defaultdict(lambda: {"base": 0.0, "tax": 0.0, "count": 0})
        for m in sales:
            by_nat[m.natureza]["base"] += m.base_value
            by_nat[m.natureza]["tax"] += m.total_taxes
            by_nat[m.natureza]["count"] += 1

        lines.append("")
        lines.append("Totais por Natureza (Saídas)")
        for nat, d in sorted(by_nat.items(), key=lambda x: (-x[1]["base"], x[0])):
            lines.append(f"- {nat}: qtd {d['count']} | base {d['base']:.2f} | impostos {d['tax']:.2f}")

        # Totais por UF/Município
        by_uf = defaultdict(lambda: {"base": 0.0, "tax": 0.0, "count": 0})
        by_city = defaultdict(lambda: {"base": 0.0, "tax": 0.0, "count": 0})
        for m in sales:
            uf = (m.dest_uf or "").strip().upper() or "(sem UF)"
            city = (m.dest_city or "").strip() or "(sem município)"
            key_city = f"{uf} - {city}"
            by_uf[uf]["base"] += m.base_value
            by_uf[uf]["tax"] += m.total_taxes
            by_uf[uf]["count"] += 1
            by_city[key_city]["base"] += m.base_value
            by_city[key_city]["tax"] += m.total_taxes
            by_city[key_city]["count"] += 1

        lines.append("")
        lines.append("Totais por UF destino (Saídas)")
        for uf, d in sorted(by_uf.items(), key=lambda x: (-x[1]["base"], x[0])):
            lines.append(f"- {uf}: qtd {d['count']} | base {d['base']:.2f} | impostos {d['tax']:.2f}")

        lines.append("")
        lines.append("Top Municípios (UF - Município) por Base (Saídas) — TOP 15")
        for city, d in sorted(by_city.items(), key=lambda x: (-x[1]["base"], x[0]))[:15]:
            lines.append(f"- {city}: qtd {d['count']} | base {d['base']:.2f} | impostos {d['tax']:.2f}")

        # Totais por NCM e por NBS (usando classificação do produto)
        by_ncm = defaultdict(lambda: {"base": 0.0, "tax": 0.0, "count": 0})
        by_nbs = defaultdict(lambda: {"base": 0.0, "tax": 0.0, "count": 0})

        for m in sales:
            p = pmap.get(m.product_id)
            if not p:
                continue
            if p.kind == "Bem":
                k = p.ncm.strip() or "(sem NCM)"
                by_ncm[k]["base"] += m.base_value
                by_ncm[k]["tax"] += m.total_taxes
                by_ncm[k]["count"] += 1
            else:
                k = p.nbs.strip() or "(sem NBS)"
                by_nbs[k]["base"] += m.base_value
                by_nbs[k]["tax"] += m.total_taxes
                by_nbs[k]["count"] += 1

        lines.append("")
        lines.append("Totais por NCM (Bens) — TOP 15 por Base")
        for ncm, d in sorted(by_ncm.items(), key=lambda x: (-x[1]["base"], x[0]))[:15]:
            lines.append(f"- NCM {ncm}: qtd {d['count']} | base {d['base']:.2f} | impostos {d['tax']:.2f}")

        lines.append("")
        lines.append("Totais por NBS (Serviços) — TOP 15 por Base")
        for nbs, d in sorted(by_nbs.items(), key=lambda x: (-x[1]["base"], x[0]))[:15]:
            lines.append(f"- NBS {nbs}: qtd {d['count']} | base {d['base']:.2f} | impostos {d['tax']:.2f}")

        lines.append("")
        lines.append("Notas didáticas:")
        lines.append("- Incidência (UF/Município) é registrada por movimentação, principalmente em SAÍDAS.")
        lines.append("- Aplicação de tributos é didática: Bens -> CBS+IBS; Serviços -> CBS+ISS (IBS/ISS zerados conforme o tipo).")
        lines.append("- Para uso real, regras e alíquotas dependem de legislação/regulamentação e enquadramentos.")

        report = "\n".join(lines)
        self.txt_report.setPlainText(report)

    def export_report_txt(self) -> None:
        content = self.txt_report.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "Exportar relatório", "Gere o relatório antes de exportar.")
            return
        suggested = str(Path.home() / "relatorio_fiscal_didatico.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar relatório (TXT)", suggested, "TXT (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(content, encoding="utf-8")
            QMessageBox.information(self, "Exportar relatório", f"Exportado:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar relatório", f"Falha:\n{e}")

    # ----------------- Geral -----------------
    def reload_db(self) -> None:
        self.ds = DataStore.load()
        self.sup_model.ds = self.ds
        self.prod_model.ds = self.ds
        self.mov_model.ds = self.ds
        self.sup_model.refresh()
        self.prod_model.refresh()
        self.mov_model.refresh()
        self._refresh_product_filters()
        self._update_status()

    def about(self) -> None:
        QMessageBox.information(
            self,
            "Sobre",
            "Mini-ERP PLUS (PySide6) — versão didática\n\n"
            "Inclui:\n"
            "- Produtos (NCM/NBS) + Fornecedores\n"
            "- Movimentações com Incidência (UF/Município) e Natureza da Operação\n"
            "- Relatórios fiscais didáticos (por NCM, NBS, UF, Município, Natureza, Tipo)\n\n"
            "Aviso: não é sistema fiscal oficial; é projeto de estudo/portfólio.",
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_product_filters()
        self._update_status()


def main() -> int:
    app = QApplication(sys.argv)
    QApplication.setOrganizationName("Benevaldo")
    QApplication.setApplicationName("MiniERP_Reforma_PLUS")

    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
