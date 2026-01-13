import csv
import json
import re
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    QAbstractTableModel,
    QLocale,
    QModelIndex,
    QObject,
    Qt,
    QSortFilterProxyModel,
    QStandardPaths,
)
from PySide6.QtGui import QAction, QKeySequence
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
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


# -----------------------------
# Domínio / Persistência
# -----------------------------
def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    p = Path(base) / "MiniEstoquePySide6"
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_file_path() -> Path:
    return app_data_dir() / "produtos.json"


def normalize_prefix(category: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", category.strip().upper())
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


def validate_ncm(ncm: str) -> Tuple[bool, str]:
    ncm = ncm.strip()
    if not ncm:
        return True, ""  # opcional
    if not re.fullmatch(r"\d{8}", ncm):
        return False, "NCM deve ter exatamente 8 dígitos (ex.: 85176259)."
    return True, ""


def validate_ean(ean: str) -> Tuple[bool, str]:
    ean = ean.strip()
    if not ean:
        return True, ""  # opcional
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", ean):
        return False, "EAN deve ter 8, 12, 13 ou 14 dígitos (somente números)."
    return True, ""


@dataclass
class Product:
    id: str
    sku: str
    name: str
    category: str
    brand: str
    ncm: str
    ean: str
    price: float
    stock: int
    active: bool
    created_at: str
    updated_at: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Product":
        return Product(
            id=str(d.get("id", uuid.uuid4())),
            sku=str(d.get("sku", "")),
            name=str(d.get("name", "")),
            category=str(d.get("category", "")),
            brand=str(d.get("brand", "")),
            ncm=str(d.get("ncm", "")),
            ean=str(d.get("ean", "")),
            price=float(d.get("price", 0.0)),
            stock=int(d.get("stock", 0)),
            active=bool(d.get("active", True)),
            created_at=str(d.get("created_at", now_iso())),
            updated_at=str(d.get("updated_at", now_iso())),
        )


def load_products() -> List[Product]:
    path = data_file_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [Product.from_dict(x) for x in raw if isinstance(x, dict)]
    except Exception:
        return []


def save_products(products: List[Product]) -> None:
    path = data_file_path()
    payload = [asdict(p) for p in products]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# -----------------------------
# Model / Proxy (Tabela + Filtros)
# -----------------------------
COLUMNS = [
    ("SKU", "sku"),
    ("Nome", "name"),
    ("Categoria", "category"),
    ("Marca", "brand"),
    ("NCM", "ncm"),
    ("EAN", "ean"),
    ("Preço", "price"),
    ("Estoque", "stock"),
    ("Status", "active"),
    ("Atualizado", "updated_at"),
]


class ProductTableModel(QAbstractTableModel):
    def __init__(self, products: List[Product], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._products: List[Product] = products
        self._locale = QLocale(QLocale.Portuguese, QLocale.Brazil)

    def products(self) -> List[Product]:
        return self._products

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._products)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(COLUMNS):
            return COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if not (0 <= r < len(self._products) and 0 <= c < len(COLUMNS)):
            return None

        p = self._products[r]
        key = COLUMNS[c][1]

        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            val = getattr(p, key)
            if key == "price":
                # Formatação BR: 1.234,56 (aproximação via QLocale)
                return self._locale.toString(float(val), "f", 2)
            if key == "active":
                return "Ativo" if bool(val) else "Inativo"
            return str(val)

        if role == Qt.TextAlignmentRole:
            if key in ("price", "stock"):
                return int(Qt.AlignVCenter | Qt.AlignRight)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        if role == Qt.UserRole:
            # retorno “cru” para ordenação/filtros
            return getattr(p, key)

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def add_product(self, product: Product) -> None:
        self.beginInsertRows(QModelIndex(), len(self._products), len(self._products))
        self._products.append(product)
        self.endInsertRows()

    def update_product(self, row: int, updated: Product) -> None:
        if not (0 <= row < len(self._products)):
            return
        self._products[row] = updated
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.UserRole])

    def remove_rows(self, rows: List[int]) -> None:
        # Remoção “hard delete” (permanente)
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self._products):
                self.beginRemoveRows(QModelIndex(), row, row)
                self._products.pop(row)
                self.endRemoveRows()

    def categories(self) -> List[str]:
        cats = sorted({p.category.strip() for p in self._products if p.category.strip()})
        return cats

    def brands(self) -> List[str]:
        brs = sorted({p.brand.strip() for p in self._products if p.brand.strip()})
        return brs


class ProductFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._search = ""
        self._only_active = False
        self._category = "Todas"
        self._brand = "Todas"

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_search(self, text: str) -> None:
        self._search = (text or "").strip()
        self.invalidateFilter()

    def set_only_active(self, on: bool) -> None:
        self._only_active = bool(on)
        self.invalidateFilter()

    def set_category(self, category: str) -> None:
        self._category = category or "Todas"
        self.invalidateFilter()

    def set_brand(self, brand: str) -> None:
        self._brand = brand or "Todas"
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        def get_user(col_key: str) -> Any:
            col_idx = [k for _, k in COLUMNS].index(col_key)
            idx = model.index(source_row, col_idx, source_parent)
            return model.data(idx, Qt.UserRole)

        sku = str(get_user("sku") or "")
        name = str(get_user("name") or "")
        category = str(get_user("category") or "")
        brand = str(get_user("brand") or "")
        active = bool(get_user("active"))

        if self._only_active and not active:
            return False

        if self._category != "Todas" and category != self._category:
            return False

        if self._brand != "Todas" and brand != self._brand:
            return False

        if self._search:
            hay = f"{sku} {name} {category} {brand}".lower()
            if self._search.lower() not in hay:
                return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        # Ordenação usando o UserRole para comparar tipos corretamente
        l = self.sourceModel().data(left, Qt.UserRole)
        r = self.sourceModel().data(right, Qt.UserRole)

        try:
            # price/stock numérico
            if isinstance(l, (int, float)) and isinstance(r, (int, float)):
                return l < r
            # bool (active)
            if isinstance(l, bool) and isinstance(r, bool):
                return (1 if l else 0) < (1 if r else 0)
        except Exception:
            pass

        return str(l).lower() < str(r).lower()


# -----------------------------
# Dialog (Cadastro/Edição)
# -----------------------------
class ProductDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        existing_skus: List[str],
        product: Optional[Product] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Produto" if product else "Novo produto")
        self.setModal(True)

        self._existing_skus = existing_skus
        self._editing = product is not None
        self._product_in = product

        # Campos
        self.sku = QLineEdit()
        self.sku.setReadOnly(True)

        self.name = QLineEdit()
        self.category = QLineEdit()
        self.brand = QLineEdit()
        self.ncm = QLineEdit()
        self.ean = QLineEdit()

        self.price = QDoubleSpinBox()
        self.price.setMinimum(0.0)
        self.price.setMaximum(999999999.0)
        self.price.setDecimals(2)

        self.stock = QSpinBox()
        self.stock.setMinimum(0)
        self.stock.setMaximum(10**9)

        self.active = QCheckBox("Ativo")

        # Layout
        form = QFormLayout()
        form.addRow("SKU", self.sku)
        form.addRow("Nome *", self.name)
        form.addRow("Categoria *", self.category)
        form.addRow("Marca", self.brand)
        form.addRow("NCM (8 dígitos)", self.ncm)
        form.addRow("EAN", self.ean)
        form.addRow("Preço", self.price)
        form.addRow("Estoque", self.stock)
        form.addRow("", self.active)

        btn_ok = QPushButton("Salvar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(btns)
        self.setLayout(root)

        # Preencher se edição
        if product:
            self.sku.setText(product.sku)
            self.name.setText(product.name)
            self.category.setText(product.category)
            self.brand.setText(product.brand)
            self.ncm.setText(product.ncm)
            self.ean.setText(product.ean)
            self.price.setValue(float(product.price))
            self.stock.setValue(int(product.stock))
            self.active.setChecked(bool(product.active))
        else:
            self.active.setChecked(True)

        # Atualiza SKU automaticamente ao digitar categoria (apenas novo)
        self.category.textChanged.connect(self._maybe_update_sku)
        self._maybe_update_sku()

        self.resize(520, 260)

    def _maybe_update_sku(self) -> None:
        if self._editing:
            return
        cat = self.category.text().strip()
        if not cat:
            self.sku.setText("")
            return
        sku = generate_sku(cat, self._existing_skus)
        self.sku.setText(sku)

    def _error(self, msg: str) -> None:
        QMessageBox.critical(self, "Validação", msg)

    def get_product(self) -> Optional[Product]:
        name = self.name.text().strip()
        category = self.category.text().strip()
        brand = self.brand.text().strip()
        ncm = self.ncm.text().strip()
        ean = self.ean.text().strip()

        if not name:
            self._error("Nome é obrigatório.")
            return None
        if not category:
            self._error("Categoria é obrigatória.")
            return None

        ok, err = validate_ncm(ncm)
        if not ok:
            self._error(err)
            return None

        ok, err = validate_ean(ean)
        if not ok:
            self._error(err)
            return None

        if self._editing and self._product_in:
            pid = self._product_in.id
            sku = self._product_in.sku
            created_at = self._product_in.created_at
        else:
            pid = str(uuid.uuid4())
            sku = self.sku.text().strip()
            if not sku:
                sku = generate_sku(category, self._existing_skus)
            created_at = now_iso()

        p = Product(
            id=pid,
            sku=sku,
            name=name,
            category=category,
            brand=brand,
            ncm=ncm,
            ean=ean,
            price=float(self.price.value()),
            stock=int(self.stock.value()),
            active=bool(self.active.isChecked()),
            created_at=created_at,
            updated_at=now_iso(),
        )
        return p

    def accept(self) -> None:
        p = self.get_product()
        if p is None:
            return
        super().accept()


# -----------------------------
# Main Window
# -----------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mini-Estoque (PySide6) — Cadastro de Produtos")

        # Carrega dados
        self.model = ProductTableModel(load_products())
        self.proxy = ProductFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        # UI central
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.doubleClicked.connect(self.edit_selected)

        # Painel de filtros
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar (SKU, Nome, Categoria, Marca)…")
        self.search.textChanged.connect(self.proxy.set_search)

        self.only_active = QCheckBox("Somente ativos")
        self.only_active.stateChanged.connect(lambda _: self.proxy.set_only_active(self.only_active.isChecked()))

        self.cmb_category = QComboBox()
        self.cmb_category.currentTextChanged.connect(self.proxy.set_category)

        self.cmb_brand = QComboBox()
        self.cmb_brand.currentTextChanged.connect(self.proxy.set_brand)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Buscar:"))
        filters.addWidget(self.search, 2)
        filters.addSpacing(10)
        filters.addWidget(self.only_active)
        filters.addSpacing(10)
        filters.addWidget(QLabel("Categoria:"))
        filters.addWidget(self.cmb_category, 1)
        filters.addWidget(QLabel("Marca:"))
        filters.addWidget(self.cmb_brand, 1)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        central.setLayout(layout)
        self.setCentralWidget(central)

        # Barra de status
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Toolbar + actions
        self._build_actions()
        self._build_toolbar()

        # Atualiza combos e status
        self.refresh_filters()
        self.update_status()

        self.resize(1200, 640)

    # -------- Actions / Toolbar --------
    def _build_actions(self) -> None:
        self.act_new = QAction("Novo", self)
        self.act_new.setShortcut(QKeySequence.New)
        self.act_new.triggered.connect(self.new_product)

        self.act_edit = QAction("Editar", self)
        self.act_edit.setShortcut(QKeySequence(Qt.Key_Return))
        self.act_edit.triggered.connect(self.edit_selected)

        self.act_toggle = QAction("Ativar/Inativar", self)
        self.act_toggle.setShortcut(QKeySequence("Ctrl+I"))
        self.act_toggle.triggered.connect(self.toggle_active)

        self.act_delete = QAction("Excluir (permanente)", self)
        self.act_delete.setShortcut(QKeySequence.Delete)
        self.act_delete.triggered.connect(self.delete_selected)

        self.act_export = QAction("Exportar CSV", self)
        self.act_export.triggered.connect(self.export_csv)

        self.act_import = QAction("Importar CSV", self)
        self.act_import.triggered.connect(self.import_csv)

        self.act_about = QAction("Sobre", self)
        self.act_about.triggered.connect(self.about)

        self.act_refresh = QAction("Recarregar", self)
        self.act_refresh.setShortcut(QKeySequence.Refresh)
        self.act_refresh.triggered.connect(self.reload_from_disk)

        # Menu
        menu_file = self.menuBar().addMenu("Arquivo")
        menu_file.addAction(self.act_new)
        menu_file.addAction(self.act_edit)
        menu_file.addSeparator()
        menu_file.addAction(self.act_import)
        menu_file.addAction(self.act_export)
        menu_file.addSeparator()
        menu_file.addAction(self.act_refresh)

        menu_edit = self.menuBar().addMenu("Editar")
        menu_edit.addAction(self.act_toggle)
        menu_edit.addAction(self.act_delete)

        menu_help = self.menuBar().addMenu("Ajuda")
        menu_help.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Ações")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addAction(self.act_new)
        tb.addAction(self.act_edit)
        tb.addAction(self.act_toggle)
        tb.addAction(self.act_delete)
        tb.addSeparator()
        tb.addAction(self.act_import)
        tb.addAction(self.act_export)
        tb.addSeparator()
        tb.addAction(self.act_refresh)
        tb.addSeparator()
        tb.addAction(self.act_about)

    # -------- Helpers --------
    def selected_source_rows(self) -> List[int]:
        selection = self.table.selectionModel().selectedRows()
        rows_proxy = sorted({idx.row() for idx in selection})
        rows_source = []
        for r in rows_proxy:
            src = self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            rows_source.append(src)
        return sorted(set(rows_source))

    def current_source_row(self) -> Optional[int]:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        src = self.proxy.mapToSource(idx).row()
        return src

    def autosave(self) -> None:
        save_products(self.model.products())

    def refresh_filters(self) -> None:
        # Mantém seleção atual quando possível
        current_cat = self.cmb_category.currentText() or "Todas"
        current_brand = self.cmb_brand.currentText() or "Todas"

        self.cmb_category.blockSignals(True)
        self.cmb_brand.blockSignals(True)

        self.cmb_category.clear()
        self.cmb_brand.clear()

        self.cmb_category.addItem("Todas")
        for c in self.model.categories():
            self.cmb_category.addItem(c)

        self.cmb_brand.addItem("Todas")
        for b in self.model.brands():
            self.cmb_brand.addItem(b)

        # Restore
        idx = self.cmb_category.findText(current_cat)
        self.cmb_category.setCurrentIndex(idx if idx >= 0 else 0)

        idx = self.cmb_brand.findText(current_brand)
        self.cmb_brand.setCurrentIndex(idx if idx >= 0 else 0)

        self.cmb_category.blockSignals(False)
        self.cmb_brand.blockSignals(False)

    def update_status(self) -> None:
        total = len(self.model.products())
        active = sum(1 for p in self.model.products() if p.active)
        filtered = self.proxy.rowCount()
        self.status.showMessage(
            f"Total: {total} | Ativos: {active} | Exibindo (após filtros): {filtered} | Dados: {data_file_path()}"
        )

    # -------- CRUD --------
    def new_product(self) -> None:
        existing_skus = [p.sku for p in self.model.products()]
        dlg = ProductDialog(self, existing_skus, product=None)
        if dlg.exec() != QDialog.Accepted:
            return
        p = dlg.get_product()
        if p is None:
            return
        self.model.add_product(p)
        self.autosave()
        self.refresh_filters()
        self.update_status()

    def edit_selected(self) -> None:
        row = self.current_source_row()
        if row is None:
            QMessageBox.information(self, "Editar", "Selecione um produto na tabela.")
            return

        prod = self.model.products()[row]
        existing_skus = [p.sku for p in self.model.products() if p.id != prod.id]

        dlg = ProductDialog(self, existing_skus, product=prod)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.get_product()
        if updated is None:
            return

        # Proteção: SKU não pode colidir
        if updated.sku in existing_skus:
            QMessageBox.critical(self, "Validação", "SKU já existe. Ajuste a categoria ou revise os dados.")
            return

        self.model.update_product(row, updated)
        self.autosave()
        self.refresh_filters()
        self.update_status()

    def toggle_active(self) -> None:
        rows = self.selected_source_rows()
        if not rows:
            QMessageBox.information(self, "Ativar/Inativar", "Selecione um ou mais produtos.")
            return

        products = self.model.products()
        # Se a maioria está ativa, vamos inativar; senão ativar
        actives = sum(1 for r in rows if products[r].active)
        target_active = False if actives >= (len(rows) / 2) else True

        for r in rows:
            p = products[r]
            updated = Product(
                **{**asdict(p), "active": target_active, "updated_at": now_iso()}
            )
            self.model.update_product(r, updated)

        self.autosave()
        self.update_status()

    def delete_selected(self) -> None:
        rows = self.selected_source_rows()
        if not rows:
            QMessageBox.information(self, "Excluir", "Selecione um ou mais produtos.")
            return

        resp = QMessageBox.warning(
            self,
            "Excluir (permanente)",
            "Confirma excluir permanentemente os itens selecionados?\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        self.model.remove_rows(rows)
        self.autosave()
        self.refresh_filters()
        self.update_status()

    # -------- Import / Export --------
    def export_csv(self) -> None:
        suggested = str(Path.home() / "produtos_export.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar CSV", suggested, "CSV (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([k for k in Product.__annotations__.keys()])
                for p in self.model.products():
                    row = [getattr(p, k) for k in Product.__annotations__.keys()]
                    w.writerow(row)

            QMessageBox.information(self, "Exportar", f"Exportado com sucesso:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"Falha ao exportar CSV:\n{e}")

    def import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar CSV", str(Path.home()), "CSV (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                r = csv.reader(f, delimiter=";")
                header = next(r, None)
                if not header:
                    raise ValueError("CSV vazio.")

                expected = list(Product.__annotations__.keys())
                if header != expected:
                    raise ValueError(
                        "Cabeçalho do CSV não confere.\n"
                        f"Esperado:\n{expected}\nRecebido:\n{header}"
                    )

                products = []
                for row in r:
                    if not row:
                        continue
                    d = dict(zip(header, row))

                    # Tipos
                    d["price"] = float(str(d.get("price", "0")).replace(",", "."))
                    d["stock"] = int(float(d.get("stock", "0")))
                    d["active"] = str(d.get("active", "True")).strip().lower() in ("true", "1", "sim", "yes")

                    products.append(Product.from_dict(d))

            # Merge (evita duplicar por ID; se ID já existe, substitui)
            current = {p.id: p for p in self.model.products()}
            for p in products:
                current[p.id] = p

            self.model.beginResetModel()
            self.model._products = list(current.values())
            self.model.endResetModel()

            self.autosave()
            self.refresh_filters()
            self.update_status()
            QMessageBox.information(self, "Importar", f"Importação concluída:\n{path}")

        except Exception as e:
            QMessageBox.critical(self, "Importar", f"Falha ao importar CSV:\n{e}")

    # -------- Outros --------
    def about(self) -> None:
        QMessageBox.information(
            self,
            "Sobre",
            "Mini-Estoque (PySide6)\n\n"
            "Funcionalidades:\n"
            "- Cadastro/edição de produtos\n"
            "- Pesquisa e filtros\n"
            "- Ativar/Inativar (soft delete)\n"
            "- Exportar/Importar CSV\n"
            "- Persistência em JSON (AppData)\n",
        )

    def reload_from_disk(self) -> None:
        resp = QMessageBox.question(
            self,
            "Recarregar",
            "Recarregar dados do disco? Alterações não salvas serão perdidas.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        products = load_products()
        self.model.beginResetModel()
        self.model._products = products
        self.model.endResetModel()

        self.refresh_filters()
        self.update_status()

    def closeEvent(self, event) -> None:
        # Salva sempre ao fechar
        try:
            self.autosave()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main()



