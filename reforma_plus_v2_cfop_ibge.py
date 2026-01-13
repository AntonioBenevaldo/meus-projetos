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
# Constantes
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

FINALIDADE_LIST = [
    "Normal",
    "Devolução",
    "Ajuste",
    "Complementar",
    "Outros",
]

# ============================================================
# Utilitários
# ============================================================
def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    p = Path(base) / "MiniERP_Reforma"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return app_data_dir() / "db.json"


def municipios_path() -> Path:
    return app_data_dir() / "municipios.json"


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
# Municípios (IBGE) – importação e uso
# ============================================================
@dataclass
class Municipality:
    uf: str
    name: str
    ibge: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Municipality":
        return Municipality(
            uf=str(d.get("uf", "")).strip().upper(),
            name=str(d.get("name", "")).strip(),
            ibge=str(d.get("ibge", "")).strip(),
        )


def load_municipios() -> List[Municipality]:
    p = municipios_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [Municipality.from_dict(x) for x in raw if isinstance(x, dict)]
    except Exception:
        return []
    return []


def save_municipios(muns: List[Municipality]) -> None:
    municipios_path().write_text(
        json.dumps([asdict(m) for m in muns], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sniff_delimiter(sample: str) -> str:
    # tenta o sniffer; se falhar, usa heurística simples
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except Exception:
        if sample.count(";") >= sample.count(","):
            return ";"
        return ","


def normalize_header(h: str) -> str:
    h = (h or "").strip().lower()
    h = re.sub(r"\s+", "_", h)
    h = re.sub(r"[^a-z0-9_]", "", h)
    return h


def detect_col_indices(headers: List[str]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Detecta colunas UF, nome município, código ibge por heurística.
    Retorna (idx_uf, idx_name, idx_ibge)
    """
    norm = [normalize_header(x) for x in headers]
    idx_uf = None
    idx_name = None
    idx_ibge = None

    # UF
    for i, h in enumerate(norm):
        if h in ("uf", "sigla_uf", "estado", "sg_uf"):
            idx_uf = i
            break
    if idx_uf is None:
        for i, h in enumerate(norm):
            if "uf" == h or h.endswith("_uf") or h.startswith("uf_"):
                idx_uf = i
                break

    # Nome município
    for i, h in enumerate(norm):
        if h in ("municipio", "nome_municipio", "nm_municipio", "nome", "cidade", "nomecidade"):
            idx_name = i
            break
    if idx_name is None:
        for i, h in enumerate(norm):
            if "municip" in h or ("nome" in h and "mun" in h):
                idx_name = i
                break

    # IBGE
    for i, h in enumerate(norm):
        if h in ("ibge", "codigo_ibge", "cod_ibge", "codigo", "cod", "cd_municipio", "cod_municipio", "codigo_municipio"):
            idx_ibge = i
            break
    if idx_ibge is None:
        for i, h in enumerate(norm):
            if "ibge" in h or ("cod" in h and "mun" in h):
                idx_ibge = i
                break

    return idx_uf, idx_name, idx_ibge


def parse_municipios_csv(file_path: str) -> Tuple[List[Municipality], str]:
    """
    Importa municípios a partir de CSV.
    Aceita ; ou , (auto).
    Tenta detectar colunas por cabeçalho; se não encontrar, tenta inferir por conteúdo.
    """
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    sample = text[:5000]
    delim = sniff_delimiter(sample)

    muns: List[Municipality] = []
    warnings: List[str] = []

    with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f, delimiter=delim)
        header = next(reader, None)
        if header is None:
            return [], "Arquivo vazio."

        # se não parece cabeçalho, vamos tratar como dados e inferir posições
        looks_header = any(re.search(r"[A-Za-z]", c or "") for c in header)

        idx_uf = idx_name = idx_ibge = None
        if looks_header:
            idx_uf, idx_name, idx_ibge = detect_col_indices(header)

        if (idx_uf is None or idx_name is None or idx_ibge is None) and looks_header:
            warnings.append("Cabeçalho não reconhecido totalmente; tentando inferir por conteúdo.")
        if not looks_header:
            # header é na verdade a primeira linha de dados
            first_row = header
            rows_iter = [first_row]  # inclui a primeira linha como dado
            rows_iter.extend(list(reader))
            data_rows = rows_iter
        else:
            data_rows = list(reader)

        def infer_row(row: List[str]) -> Optional[Municipality]:
            row = [x.strip() for x in row]
            if not any(row):
                return None

            # se índices detectados, usa
            if looks_header and idx_uf is not None and idx_name is not None and idx_ibge is not None:
                uf = (row[idx_uf] if idx_uf < len(row) else "").strip().upper()
                name = (row[idx_name] if idx_name < len(row) else "").strip()
                ibge = (row[idx_ibge] if idx_ibge < len(row) else "").strip()
                if uf and name and ibge:
                    return Municipality(uf=uf, name=name, ibge=ibge)
                return None

            # inferência por conteúdo (fallback)
            uf = ""
            name = ""
            ibge = ""

            for v in row:
                vv = v.strip()
                if not uf and re.fullmatch(r"[A-Za-z]{2}", vv):
                    uf = vv.upper()
                    continue
                if not ibge and re.fullmatch(r"\d{6,8}", vv):
                    ibge = vv
                    continue

            # nome: primeira string que não é UF nem IBGE
            for v in row:
                vv = v.strip()
                if not vv:
                    continue
                if re.fullmatch(r"[A-Za-z]{2}", vv):
                    continue
                if re.fullmatch(r"\d{6,8}", vv):
                    continue
                name = vv
                break

            if uf and name and ibge:
                return Municipality(uf=uf, name=name, ibge=ibge)
            return None

        seen = set()
        for row in data_rows:
            m = infer_row(row)
            if not m:
                continue
            if m.uf not in UF_LIST:
                continue
            key = (m.uf, m.name.lower(), m.ibge)
            if key in seen:
                continue
            seen.add(key)
            muns.append(m)

    if not muns:
        msg = "Não foi possível importar municípios desse CSV."
        if warnings:
            msg += " " + " ".join(warnings)
        return [], msg

    return muns, "Importação concluída."


# ============================================================
# Regras didáticas: incidência e CFOP (didático)
# ============================================================
def suggest_natureza(product_kind: str) -> str:
    return "Prestação de serviço" if product_kind == "Serviço" else "Venda de mercadoria"


def taxes_applicability(product_kind: str, natureza: str) -> Tuple[bool, bool, bool]:
    """
    Didático:
    - Bens: CBS + IBS
    - Serviços: CBS + ISS
    """
    if product_kind == "Serviço":
        return True, False, True
    return True, True, False


def suggest_cfop(product_kind: str, natureza: str, uf_origem: str, uf_dest: str) -> str:
    """
    CFOP didático (não oficial):
    - Bens:
      Venda: 5102 (intra) / 6102 (inter)
      Transferência: 5152 / 6152
      Devolução: 5202 / 6202
      Bonificação: 5910 / 6910
    - Serviços:
      Prestação: 5933 / 6933 (didático)
      Outros: 5949 / 6949 (didático)
    """
    uo = (uf_origem or "").strip().upper()
    ud = (uf_dest or "").strip().upper()

    intra = bool(uo) and bool(ud) and (uo == ud)

    if product_kind == "Serviço":
        if natureza == "Prestação de serviço":
            return "5933" if intra else "6933"
        if natureza == "Devolução":
            return "5202" if intra else "6202"  # didático
        return "5949" if intra else "6949"

    # bens
    if natureza == "Venda de mercadoria":
        return "5102" if intra else "6102"
    if natureza == "Transferência":
        return "5152" if intra else "6152"
    if natureza == "Devolução":
        return "5202" if intra else "6202"
    if natureza == "Bonificação/Brinde":
        return "5910" if intra else "6910"
    if natureza == "Ajuste/Inventário":
        return "5999" if intra else "6999"
    return "5949" if intra else "6949"


# ============================================================
# Entidades
# ============================================================
@dataclass
class TaxDefaults:
    cbs_rate: float = 0.0
    ibs_rate: float = 0.0
    iss_rate: float = 0.0
    uf_origem: str = ""  # para CFOP didático

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TaxDefaults":
        return TaxDefaults(
            cbs_rate=float(d.get("cbs_rate", 0.0)),
            ibs_rate=float(d.get("ibs_rate", 0.0)),
            iss_rate=float(d.get("iss_rate", 0.0)),
            uf_origem=str(d.get("uf_origem", "")).strip().upper(),
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
    natureza: str
    finalidade: str
    cfop: str
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
        return Movement(
            id=str(d.get("id", uuid.uuid4())),
            created_at=str(d.get("created_at", now_iso())),
            product_id=str(d.get("product_id", "")),
            mov_type=str(d.get("mov_type", "Entrada")),
            natureza=str(d.get("natureza", d.get("op_nature", "Outros"))),
            finalidade=str(d.get("finalidade", "Normal")),
            cfop=str(d.get("cfop", "")),
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
        self.municipios: List[Municipality] = []

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

    def load_municipios(self) -> None:
        self.municipios = load_municipios()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": {"version": 3, "updated_at": now_iso()},
            "tax_defaults": asdict(self.tax_defaults),
            "suppliers": [asdict(s) for s in self.suppliers],
            "products": [asdict(p) for p in self.products],
            "movements": [asdict(m) for m in self.movements],
        }

    @staticmethod
    def load() -> "DataStore":
        ds = DataStore()
        ds.load_municipios()

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

    def municipios_by_uf(self, uf: str) -> List[Municipality]:
        uf = (uf or "").strip().upper()
        if not uf:
            return []
        return sorted([m for m in self.municipios if m.uf == uf], key=lambda x: x.name.lower())

    def find_municipio(self, uf: str, name: str) -> Optional[Municipality]:
        uf = (uf or "").strip().upper()
        name = (name or "").strip().lower()
        for m in self.municipios:
            if m.uf == uf and m.name.strip().lower() == name:
                return m
        return None


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
        ("Finalidade", "finalidade"),
        ("CFOP", "cfop"),
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
        self.setWindowTitle("Config Fiscal (Simulador) — IBS/CBS/ISS + UF Origem (CFOP didático)")
        self.setModal(True)

        self.cbs = QDoubleSpinBox()
        self.ibs = QDoubleSpinBox()
        self.iss = QDoubleSpinBox()
        for w in (self.cbs, self.ibs, self.iss):
            w.setDecimals(2)
            w.setRange(0.0, 100.0)

        self.uf_origem = QComboBox()
        self.uf_origem.addItem("")
        for uf in UF_LIST:
            self.uf_origem.addItem(uf)

        self.cbs.setValue(float(td.cbs_rate))
        self.ibs.setValue(float(td.ibs_rate))
        self.iss.setValue(float(td.iss_rate))
        if td.uf_origem:
            idx = self.uf_origem.findText(td.uf_origem)
            self.uf_origem.setCurrentIndex(idx if idx >= 0 else 0)

        form = QFormLayout()
        form.addRow("CBS padrão (%)", self.cbs)
        form.addRow("IBS padrão (%)", self.ibs)
        form.addRow("ISS padrão (%)", self.iss)
        form.addRow("UF origem (para CFOP)", self.uf_origem)

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
        self.resize(600, 240)

    def get_values(self) -> TaxDefaults:
        return TaxDefaults(
            cbs_rate=clamp_rate(float(self.cbs.value())),
            ibs_rate=clamp_rate(float(self.ibs.value())),
            iss_rate=clamp_rate(float(self.iss.value())),
            uf_origem=str(self.uf_origem.currentText() or "").strip().upper(),
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
        self.setWindowTitle("Movimentação — Incidência (UF/Município) + Natureza + Finalidade + CFOP (didático)")
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

        self.finalidade = QComboBox()
        self.finalidade.addItems(FINALIDADE_LIST)

        self.cfop = QLineEdit()
        self.cfop.setPlaceholderText("Sugestão automática (didático)")

        self.dest_uf = QComboBox()
        self.dest_uf.addItem("")
        for uf in UF_LIST:
            self.dest_uf.addItem(uf)

        # Município por lista (IBGE). Editável para permitir digitar.
        self.dest_city = QComboBox()
        self.dest_city.setEditable(True)
        self.dest_city.setInsertPolicy(QComboBox.NoInsert)
        self.dest_city.setMinimumContentsLength(28)

        self.dest_city_ibge = QLineEdit()
        self.dest_city_ibge.setPlaceholderText("Auto (se selecionado pela lista) ou manual")
        # deixa editável porque, se não tiver lista, usuário pode preencher
        self.dest_city_ibge.setReadOnly(False)

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
        form.addRow("Finalidade", self.finalidade)
        form.addRow("CFOP (didático)", self.cfop)
        form.addRow("UF destino (incidência)", self.dest_uf)
        form.addRow("Município destino (lista/IBGE)", self.dest_city)
        form.addRow("Município IBGE", self.dest_city_ibge)
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

        # eventos
        self.product.currentIndexChanged.connect(self._load_from_product)
        self.mov_type.currentTextChanged.connect(self._update_preview)
        self.natureza.currentTextChanged.connect(self._update_preview_and_cfop)
        self.finalidade.currentTextChanged.connect(self._update_preview)
        self.dest_uf.currentTextChanged.connect(self._reload_municipios_for_uf)
        self.dest_city.currentTextChanged.connect(self._sync_ibge_from_city)
        self.qty.valueChanged.connect(self._update_preview)
        self.unit_price.valueChanged.connect(self._update_preview)
        self.cbs.valueChanged.connect(self._update_preview)
        self.ibs.valueChanged.connect(self._update_preview)
        self.iss.valueChanged.connect(self._update_preview)

        self._load_from_product()
        self.resize(900, 560)

    def _load_from_product(self) -> None:
        pid = str(self.product.currentData() or "")
        p = self.ds.product_by_id(pid)
        if not p:
            return

        self.unit_price.setValue(float(p.price))
        self.cbs.setValue(float(p.cbs_rate) if p.cbs_rate else float(self.ds.tax_defaults.cbs_rate))
        self.ibs.setValue(float(p.ibs_rate) if p.ibs_rate else float(self.ds.tax_defaults.ibs_rate))
        self.iss.setValue(float(p.iss_rate) if p.iss_rate else float(self.ds.tax_defaults.iss_rate))

        sug_nat = suggest_natureza(p.kind)
        idx_nat = self.natureza.findText(sug_nat)
        if idx_nat >= 0:
            self.natureza.setCurrentIndex(idx_nat)

        self._update_preview_and_cfop()

    def _reload_municipios_for_uf(self) -> None:
        uf = (self.dest_uf.currentText() or "").strip().upper()
        self.dest_city.blockSignals(True)
        self.dest_city.clear()
        self.dest_city.addItem("")  # vazio

        if uf and self.ds.municipios:
            for m in self.ds.municipios_by_uf(uf):
                # itemData guarda IBGE
                self.dest_city.addItem(m.name, m.ibge)

        self.dest_city.blockSignals(False)
        self._sync_ibge_from_city()
        self._update_preview_and_cfop()

    def _sync_ibge_from_city(self) -> None:
        ibge = self.dest_city.currentData()
        if ibge:
            self.dest_city_ibge.setText(str(ibge))
        else:
            # se usuário digitou manualmente, tenta achar no cadastro
            uf = (self.dest_uf.currentText() or "").strip().upper()
            name = (self.dest_city.currentText() or "").strip()
            if uf and name and self.ds.municipios:
                m = self.ds.find_municipio(uf, name)
                if m:
                    self.dest_city_ibge.setText(m.ibge)

        self._update_preview_and_cfop()

    def _update_preview_and_cfop(self) -> None:
        pid = str(self.product.currentData() or "")
        p = self.ds.product_by_id(pid)
        if not p:
            self.preview.setText("")
            self.lbl_aplic.setText("")
            return

        natureza = (self.natureza.currentText() or "Outros").strip()
        uf_dest = (self.dest_uf.currentText() or "").strip().upper()
        uf_origem = (self.ds.tax_defaults.uf_origem or "").strip().upper()

        # sugere CFOP automaticamente quando:
        # - usuário não digitou CFOP manualmente OU está vazio
        if not self.cfop.text().strip():
            self.cfop.setText(suggest_cfop(p.kind, natureza, uf_origem, uf_dest))

        self._update_preview()

    def _update_preview(self) -> None:
        pid = str(self.product.currentData() or "")
        p = self.ds.product_by_id(pid)
        if not p:
            self.preview.setText("")
            self.lbl_aplic.setText("")
            return

        natureza = (self.natureza.currentText() or "Outros").strip()
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

        mov_type = (self.mov_type.currentText() or "Entrada").strip()
        natureza = (self.natureza.currentText() or "Outros").strip()
        finalidade = (self.finalidade.currentText() or "Normal").strip()
        cfop = (self.cfop.text() or "").strip()

        dest_uf = (self.dest_uf.currentText() or "").strip().upper()
        dest_city = (self.dest_city.currentText() or "").strip()
        dest_ibge = (self.dest_city_ibge.text() or "").strip()

        # Incidência didática: exige UF/Município para SAÍDA
        if mov_type == "Saída":
            if not dest_uf:
                QMessageBox.critical(self, "Validação", "Para SAÍDA, UF destino é obrigatório (incidência).")
                return None
            if not dest_city:
                QMessageBox.critical(self, "Validação", "Para SAÍDA, Município destino é obrigatório (incidência).")
                return None

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
            finalidade=finalidade,
            cfop=cfop,
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
            notes=(self.notes.text() or "").strip(),
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
        self.setWindowTitle("Mini-ERP (PySide6) — PLUS v2: IBS/CBS/ISS + IBGE Municípios + CFOP + Relatórios CSV")
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

        self.resize(1600, 800)

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

        btn_export_txt = QPushButton("Exportar relatório (TXT)")
        btn_export_txt.clicked.connect(self.export_report_txt)

        btn_export_csv = QPushButton("Exportar fiscal (CSV)")
        btn_export_csv.clicked.connect(self.export_fiscal_csv)

        top.addWidget(QLabel("Baixo estoque ≤"))
        top.addWidget(self.sp_low)
        top.addStretch(1)
        top.addWidget(btn)
        top.addWidget(btn_export_txt)
        top.addWidget(btn_export_csv)

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

        act_import_mun = QAction("Importar Municípios (IBGE CSV)", self)
        act_import_mun.triggered.connect(self.import_municipios_ibge)

        act_reload = QAction("Recarregar DB", self)
        act_reload.triggered.connect(self.reload_db)

        act_about = QAction("Sobre", self)
        act_about.triggered.connect(self.about)

        tb.addAction(act_tax)
        tb.addAction(act_import_mun)
        tb.addAction(act_reload)
        tb.addAction(act_about)

    # ----------------- Helpers -----------------
    def _update_status(self) -> None:
        total_p = len(self.ds.products)
        active_p = sum(1 for p in self.ds.products if p.active)
        total_s = len(self.ds.suppliers)
        total_m = len(self.ds.movements)
        showing = self.prod_proxy.rowCount()
        mun_count = len(self.ds.municipios)

        self.status.showMessage(
            f"Produtos: {total_p} (Ativos {active_p}) | Fornecedores: {total_s} | Movs: {total_m} | "
            f"Municípios(IBGE): {mun_count} | Exibindo produtos (filtro): {showing} | DB: {db_path()}"
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

    # ----------------- Fiscal / IBGE -----------------
    def configure_tax(self) -> None:
        dlg = TaxDefaultsDialog(self, self.ds.tax_defaults)
        if dlg.exec() != QDialog.Accepted:
            return
        self.ds.tax_defaults = dlg.get_values()
        self.ds.save()
        QMessageBox.information(self, "Fiscal", "Config fiscal atualizada (inclui UF origem para CFOP didático).")

    def import_municipios_ibge(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar Municípios (IBGE CSV)", str(Path.home()), "CSV (*.csv)")
        if not path:
            return

        try:
            muns, msg = parse_municipios_csv(path)
            if not muns:
                QMessageBox.critical(self, "Municípios", msg)
                return

            save_municipios(muns)
            self.ds.load_municipios()
            self._update_status()
            QMessageBox.information(self, "Municípios", f"{msg}\nRegistros: {len(muns)}")
        except Exception as e:
            QMessageBox.critical(self, "Municípios", f"Falha ao importar:\n{e}")

    # ----------------- Relatórios -----------------
    def _compute_fiscal_aggregates(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Retorna agregações para SAÍDAS:
        dims: UF, Município, Natureza, Finalidade, CFOP, Tipo, NCM, NBS
        Cada item: base, cbs, ibs, iss, taxes, total, count
        """
        pmap = {p.id: p for p in self.ds.products}
        sales = [m for m in self.ds.movements if m.mov_type == "Saída"]

        def new_bucket() -> Dict[str, float]:
            return {"base": 0.0, "cbs": 0.0, "ibs": 0.0, "iss": 0.0, "taxes": 0.0, "total": 0.0, "count": 0.0}

        aggs: Dict[str, Dict[str, Dict[str, float]]] = {
            "UF": defaultdict(new_bucket),
            "MUNICIPIO": defaultdict(new_bucket),
            "NATUREZA": defaultdict(new_bucket),
            "FINALIDADE": defaultdict(new_bucket),
            "CFOP": defaultdict(new_bucket),
            "TIPO": defaultdict(new_bucket),
            "NCM": defaultdict(new_bucket),
            "NBS": defaultdict(new_bucket),
        }

        for m in sales:
            p = pmap.get(m.product_id)
            kind = p.kind if p else "Desconhecido"

            uf = (m.dest_uf or "").strip().upper() or "(sem UF)"
            city = (m.dest_city or "").strip() or "(sem município)"
            key_city = f"{uf} - {city}"

            natureza = (m.natureza or "Outros").strip()
            finalidade = (m.finalidade or "Normal").strip()
            cfop = (m.cfop or "").strip() or "(sem CFOP)"

            def add(dim: str, key: str) -> None:
                b = aggs[dim][key]
                b["base"] += m.base_value
                b["cbs"] += m.cbs_value
                b["ibs"] += m.ibs_value
                b["iss"] += m.iss_value
                b["taxes"] += m.total_taxes
                b["total"] += m.total_value
                b["count"] += 1.0

            add("UF", uf)
            add("MUNICIPIO", key_city)
            add("NATUREZA", natureza)
            add("FINALIDADE", finalidade)
            add("CFOP", cfop)
            add("TIPO", kind)

            if p:
                if p.kind == "Bem":
                    add("NCM", p.ncm.strip() or "(sem NCM)")
                else:
                    add("NBS", p.nbs.strip() or "(sem NBS)")

        # convert defaultdict -> dict normal
        out: Dict[str, Dict[str, Dict[str, float]]] = {}
        for dim, mp in aggs.items():
            out[dim] = dict(mp)
        return out

    def generate_report(self) -> None:
        low = int(self.sp_low.value())
        lines: List[str] = []

        lines.append("RELATÓRIOS FISCAIS (DIDÁTICOS) — Mini-ERP PLUS v2")
        lines.append(f"Data/Hora: {now_iso()}")
        lines.append(f"DB: {db_path()}")
        lines.append(f"Municípios(IBGE): {len(self.ds.municipios)} (arquivo: {municipios_path()})")
        lines.append("")

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

        aggs = self._compute_fiscal_aggregates()

        def top_lines(dim: str, title: str, top_n: int = 15) -> None:
            lines.append("")
            lines.append(title)
            items = list(aggs.get(dim, {}).items())
            items.sort(key=lambda x: (-x[1]["base"], x[0]))
            for k, d in items[:top_n]:
                lines.append(
                    f"- {k}: qtd {int(d['count'])} | base {d['base']:.2f} | "
                    f"CBS {d['cbs']:.2f} | IBS {d['ibs']:.2f} | ISS {d['iss']:.2f} | impostos {d['taxes']:.2f}"
                )

        top_lines("UF", "Totais por UF destino (Saídas) — TOP 15 por Base")
        top_lines("MUNICIPIO", "Totais por Município (UF - Município) — TOP 15 por Base")
        top_lines("NATUREZA", "Totais por Natureza — TOP 15 por Base")
        top_lines("FINALIDADE", "Totais por Finalidade — TOP 15 por Base")
        top_lines("CFOP", "Totais por CFOP (didático) — TOP 15 por Base")
        top_lines("TIPO", "Totais por Tipo (Bem/Serviço) — TOP 15 por Base")
        top_lines("NCM", "Totais por NCM (Bens) — TOP 15 por Base")
        top_lines("NBS", "Totais por NBS (Serviços) — TOP 15 por Base")

        lines.append("")
        lines.append("Notas didáticas:")
        lines.append("- Incidência (UF/Município) é registrada por movimentação, principalmente em SAÍDAS.")
        lines.append("- CFOP aqui é sugestão didática (não substitui regra oficial).")
        lines.append("- Aplicação de tributos é didática: Bens -> CBS+IBS; Serviços -> CBS+ISS.")
        lines.append("- Para uso real, regras e alíquotas dependem de legislação/regulamentação.")

        self.txt_report.setPlainText("\n".join(lines))

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

    def export_fiscal_csv(self) -> None:
        """
        Exporta agregados fiscais didáticos em um CSV único:
        dimension;key;count;base;cbs;ibs;iss;taxes;total
        """
        suggested = str(Path.home() / "fiscal_agregado_saida.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Fiscal (CSV)", suggested, "CSV (*.csv)")
        if not path:
            return

        aggs = self._compute_fiscal_aggregates()
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["dimension", "key", "count", "base", "cbs", "ibs", "iss", "taxes", "total"])
                for dim in ["UF", "MUNICIPIO", "NATUREZA", "FINALIDADE", "CFOP", "TIPO", "NCM", "NBS"]:
                    items = list(aggs.get(dim, {}).items())
                    items.sort(key=lambda x: (-x[1]["base"], x[0]))
                    for k, d in items:
                        w.writerow([
                            dim,
                            k,
                            int(d["count"]),
                            f"{d['base']:.2f}",
                            f"{d['cbs']:.2f}",
                            f"{d['ibs']:.2f}",
                            f"{d['iss']:.2f}",
                            f"{d['taxes']:.2f}",
                            f"{d['total']:.2f}",
                        ])
            QMessageBox.information(self, "Exportar Fiscal", f"Exportado:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar Fiscal", f"Falha:\n{e}")

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
            "Mini-ERP PLUS v2 (PySide6) — versão didática\n\n"
            "Inclui:\n"
            "- Produtos (NCM/NBS) + Fornecedores\n"
            "- Movimentações com Incidência (UF/Município), Natureza, Finalidade e CFOP (didático)\n"
            "- Importação de Municípios (IBGE CSV)\n"
            "- Relatórios fiscais didáticos + Exportação CSV agregada\n\n"
            "Aviso: não é sistema fiscal oficial; é projeto de estudo/portfólio.",
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_product_filters()
        self._update_status()


def main() -> int:
    app = QApplication(sys.argv)
    QApplication.setOrganizationName("Benevaldo")
    QApplication.setApplicationName("MiniERP_Reforma_PLUS_v2")

    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
