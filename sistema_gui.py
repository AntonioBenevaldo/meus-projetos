import json
import re
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox


# =========================
# Config UI
# =========================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# =========================
# Persistência JSON
# =========================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

PRODUTOS_JSON = DATA_DIR / "produtos.json"
AUDIT_LOG = DATA_DIR / "audit.log"

DEFAULT_FILIAL = "001-Matriz"
DEFAULT_AMBIENTE = "Hom"  # Hom / Prod etc.


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_audit(msg: str) -> None:
    """Registra auditoria simples em arquivo texto."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_LOG.write_text(
            (AUDIT_LOG.read_text(encoding="utf-8") if AUDIT_LOG.exists() else "")
            + f"{now_ts()} - {msg}\n",
            encoding="utf-8",
        )
    except Exception:
        # log não pode quebrar o sistema
        pass


def read_last_audit(n: int = 6) -> list[str]:
    if not AUDIT_LOG.exists():
        return []
    try:
        lines = AUDIT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-n:]
    except Exception:
        return []


def load_produtos() -> list[dict]:
    """Carrega produtos do JSON. Se não existir, retorna lista vazia."""
    if not PRODUTOS_JSON.exists():
        return []

    try:
        data = json.loads(PRODUTOS_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # Backup do arquivo corrompido e retorna vazio
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        backup = DATA_DIR / f"produtos_corrompido_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup.write_text(
            PRODUTOS_JSON.read_text(encoding="utf-8", errors="ignore"),
            encoding="utf-8",
        )
        return []


def save_produtos(produtos: list[dict]) -> None:
    """Salva lista de produtos no JSON (write atômico)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / "produtos.tmp.json"
    tmp.write_text(json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PRODUTOS_JSON)


# =========================
# Helpers (validações/formatos)
# =========================
def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _is_nonneg_int(s: str) -> bool:
    if s is None or s.strip() == "":
        return True
    return s.isdigit() and int(s) >= 0


def _is_nonneg_float(s: str) -> bool:
    if s is None or s.strip() == "":
        return True
    try:
        return float(s.replace(".", "").replace(",", ".")) >= 0  # aceita 1.234,56
    except Exception:
        return False


def parse_money(s: str) -> float:
    if s is None or str(s).strip() == "":
        return 0.0
    return float(str(s).replace(".", "").replace(",", "."))


def fmt_money(v) -> str:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    # pt-BR simples sem locale
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def is_valid_gtin(gtin: str) -> bool:
    """
    Valida GTIN/EAN (8, 12, 13, 14) por dígito verificador.
    Regra: soma ponderada (3/1) a partir da direita (exclui DV).
    """
    gtin = _only_digits(gtin)
    if len(gtin) not in (8, 12, 13, 14):
        return False
    if not gtin.isdigit():
        return False

    digits = [int(c) for c in gtin]
    dv = digits[-1]
    body = digits[:-1]

    # pesos alternados 3 e 1, começando do fim do body
    total = 0
    weight = 3
    for d in reversed(body):
        total += d * weight
        weight = 1 if weight == 3 else 3

    calc_dv = (10 - (total % 10)) % 10
    return dv == calc_dv


# =========================
# UI Components
# =========================
class CollapsibleSection(ctk.CTkFrame):
    """Seção recolhível estilo accordion."""

    def __init__(self, master, title: str):
        super().__init__(master)
        self.title = title
        self.is_open = True

        self.grid_columnconfigure(0, weight=1)

        self.btn = ctk.CTkButton(self, text=f"{title} ▾", anchor="w", command=self.toggle, height=34)
        self.btn.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        self.body.grid_columnconfigure(0, weight=1)

    def toggle(self):
        self.is_open = not self.is_open
        if self.is_open:
            self.btn.configure(text=f"{self.title} ▾")
            self.body.grid()
        else:
            self.btn.configure(text=f"{self.title} ▸")
            self.body.grid_remove()

    def add_item(self, text: str, command):
        b = ctk.CTkButton(self.body, text=text, anchor="w", height=34, command=command)
        b.grid(sticky="ew", pady=4)
        return b


class ScreenManager(ctk.CTkFrame):
    """Troca telas no content. Se a tela tiver on_show(), chama ao exibir."""

    def __init__(self, master):
        super().__init__(master)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.screens: dict[str, ctk.CTkFrame] = {}
        self.current: str | None = None

    def register(self, name: str, screen_cls):
        screen = screen_cls(self)
        self.screens[name] = screen
        screen.grid(row=0, column=0, sticky="nsew")
        screen.grid_remove()

    def show(self, name: str):
        if self.current:
            self.screens[self.current].grid_remove()

        scr = self.screens[name]
        scr.grid()
        self.current = name

        if hasattr(scr, "on_show"):
            scr.on_show()


# =========================
# Screens
# =========================
class DashboardScreen(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Dashboard", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 6)
        )
        ctk.CTkLabel(self, text="Resumo operacional e atalhos.", text_color="gray80").grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        # Cards
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1)

        self.card1 = self._mk_card(cards, 0, "Produtos cadastrados", "0")
        self.card2 = self._mk_card(cards, 1, "Produtos ativos", "0")
        self.card3 = self._mk_card(cards, 2, "Pendências fiscais", "0")

        # Atalhos
        at = ctk.CTkFrame(self, corner_radius=12)
        at.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        at.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(at, text="Atalhos Rápidos", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 8)
        )

        row_btn = ctk.CTkFrame(at, fg_color="transparent")
        row_btn.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        for i in range(4):
            row_btn.grid_columnconfigure(i, weight=1)

        ctk.CTkButton(row_btn, text="Cadastrar Produto", command=lambda: self._go("cad_produto")).grid(
            row=0, column=0, sticky="ew", padx=6
        )
        ctk.CTkButton(row_btn, text="Listar Produtos", command=lambda: self._go("listar_produtos")).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ctk.CTkButton(row_btn, text="Calcular NF (mock)", command=lambda: self._status("Função NF ainda não implementada.")).grid(
            row=0, column=2, sticky="ew", padx=6
        )
        ctk.CTkButton(row_btn, text="Emitir NF (mock)", command=lambda: self._status("Função NF ainda não implementada.")).grid(
            row=0, column=3, sticky="ew", padx=6
        )

        # Alertas / Pendências + Últimas Ações
        grid2 = ctk.CTkFrame(self, fg_color="transparent")
        grid2.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 16))
        grid2.grid_columnconfigure(0, weight=1)
        grid2.grid_columnconfigure(1, weight=1)

        self.box_alertas = ctk.CTkFrame(grid2, corner_radius=12)
        self.box_alertas.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.box_alertas.grid_rowconfigure(1, weight=1)
        self.box_alertas.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.box_alertas, text="Alertas / Pendências", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6)
        )
        self.txt_alertas = ctk.CTkTextbox(self.box_alertas, height=180)
        self.txt_alertas.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.txt_alertas.configure(state="disabled")

        self.box_acoes = ctk.CTkFrame(grid2, corner_radius=12)
        self.box_acoes.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.box_acoes.grid_rowconfigure(1, weight=1)
        self.box_acoes.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.box_acoes, text="Últimas Ações", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6)
        )
        self.txt_acoes = ctk.CTkTextbox(self.box_acoes, height=180)
        self.txt_acoes.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.txt_acoes.configure(state="disabled")

    def _mk_card(self, master, col: int, title: str, value: str):
        card = ctk.CTkFrame(master, corner_radius=12)
        card.grid(row=0, column=col, sticky="ew", padx=6)
        card.grid_columnconfigure(0, weight=1)

        lbl_title = ctk.CTkLabel(card, text=title, text_color="gray80")
        lbl_title.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 2))

        lbl_value = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=24, weight="bold"))
        lbl_value.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        return lbl_value

    def _go(self, screen: str):
        app = self.winfo_toplevel()
        if hasattr(app, "go"):
            app.go(screen)

    def _status(self, msg: str):
        app = self.winfo_toplevel()
        if hasattr(app, "set_status"):
            app.set_status(msg)
        if hasattr(app, "log_action"):
            app.log_action(msg)

    def on_show(self):
        produtos = load_produtos()
        total = len(produtos)
        ativos = sum(1 for p in produtos if bool(p.get("ativo", True)))

        sem_ncm = sum(1 for p in produtos if len(_only_digits(str(p.get("ncm", "")))) != 8)
        ean_invalid = 0
        for p in produtos:
            ean = _only_digits(str(p.get("ean", "")))
            if ean and not is_valid_gtin(ean):
                ean_invalid += 1

        pend = sem_ncm + ean_invalid

        self.card1.configure(text=str(total))
        self.card2.configure(text=str(ativos))
        self.card3.configure(text=str(pend))

        alert_lines = [
            f"• {sem_ncm} produtos sem NCM (8 dígitos).",
            f"• {ean_invalid} produtos com EAN/GTIN inválido (dígito verificador).",
            "• (mock) Faltam alíquotas/UF para regras de ICMS/ST/DIFAL.",
        ]
        self.txt_alertas.configure(state="normal")
        self.txt_alertas.delete("1.0", "end")
        self.txt_alertas.insert("end", "\n".join(alert_lines))
        self.txt_alertas.configure(state="disabled")

        last = read_last_audit(8)
        self.txt_acoes.configure(state="normal")
        self.txt_acoes.delete("1.0", "end")
        self.txt_acoes.insert("end", "\n".join(last) if last else "(sem ações registradas ainda)")
        self.txt_acoes.configure(state="disabled")


class CadastroProdutoScreen(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self._produtos_cache = load_produtos()

        # modo edição
        self.editing_id: int | None = None
        self.editing_created_at: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Vars
        self.var_ativo = ctk.BooleanVar(value=True)
        self.var_categoria = ctk.StringVar(value="")
        self.var_sku = ctk.StringVar(value="")
        self.var_marca = ctk.StringVar(value="")
        self.var_unidade = ctk.StringVar(value="UN")
        self.var_estoque_ini = ctk.StringVar(value="0")
        self.var_preco_custo = ctk.StringVar(value="")
        self.var_preco_venda = ctk.StringVar(value="")

        self.var_ncm = ctk.StringVar(value="")
        self.var_ean = ctk.StringVar(value="")
        self.var_cest = ctk.StringVar(value="")
        self.var_origem = ctk.StringVar(value="0 - Nacional")
        self.var_cst = ctk.StringVar(value="")
        self.var_cfop = ctk.StringVar(value="")
        self.var_pis = ctk.StringVar(value="01")
        self.var_cofins = ctk.StringVar(value="01")
        self.var_ipi = ctk.StringVar(value="50")

        self._last_validation = {"ok": [], "warn": [], "err": []}

        self._build_header()
        self._build_cards()
        self._build_validation_footer()
        self._build_actions()

        self._bind_live_validation()
        self._generate_sku(force=True)
        self._run_validation()

    # ---------- UI ----------
    def _build_header(self):
        self.lbl_title = ctk.CTkLabel(self, text="Cadastro de Produto", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        self.lbl_sub = ctk.CTkLabel(
            self,
            text="Preencha os dados comerciais e fiscais. Campos com * são obrigatórios.",
            text_color="gray80",
        )
        self.lbl_sub.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

    def _build_cards(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)

        # Card principal
        card_main = ctk.CTkFrame(wrap, corner_radius=12)
        card_main.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        card_main.grid_columnconfigure(1, weight=1)
        card_main.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(card_main, text="Dados Principais", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 10)
        )

        ctk.CTkLabel(card_main, text="SKU (auto):").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.ent_sku = ctk.CTkEntry(card_main, textvariable=self.var_sku, state="readonly", width=160)
        self.ent_sku.grid(row=1, column=1, sticky="w", padx=12, pady=6)

        self.btn_regen = ctk.CTkButton(card_main, text="Gerar SKU", width=110, command=self._regen_sku_manual)
        self.btn_regen.grid(row=1, column=2, sticky="e", padx=12, pady=6)

        self.sw_ativo = ctk.CTkSwitch(card_main, text="Ativo", variable=self.var_ativo, command=self._run_validation)
        self.sw_ativo.grid(row=1, column=3, sticky="e", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Categoria *:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.ent_categoria = ctk.CTkEntry(card_main, textvariable=self.var_categoria, placeholder_text="Ex.: ELETRONICOS")
        self.ent_categoria.grid(row=2, column=1, columnspan=3, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Marca:").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        self.ent_marca = ctk.CTkEntry(card_main, textvariable=self.var_marca)
        self.ent_marca.grid(row=3, column=1, columnspan=3, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Descrição *:").grid(row=4, column=0, sticky="nw", padx=12, pady=6)
        self.txt_descricao = ctk.CTkTextbox(card_main, height=100)
        self.txt_descricao.grid(row=4, column=1, columnspan=3, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Unidade *:").grid(row=5, column=0, sticky="w", padx=12, pady=6)
        self.ent_unidade = ctk.CTkEntry(card_main, textvariable=self.var_unidade, width=80)
        self.ent_unidade.grid(row=5, column=1, sticky="w", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Estoque inicial:").grid(row=5, column=2, sticky="e", padx=12, pady=6)
        self.ent_estoque = ctk.CTkEntry(card_main, textvariable=self.var_estoque_ini, width=120)
        self.ent_estoque.grid(row=5, column=3, sticky="w", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Preço custo:").grid(row=6, column=0, sticky="w", padx=12, pady=6)
        self.ent_custo = ctk.CTkEntry(card_main, textvariable=self.var_preco_custo, placeholder_text="0,00")
        self.ent_custo.grid(row=6, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_main, text="Preço venda:").grid(row=6, column=2, sticky="e", padx=12, pady=6)
        self.ent_venda = ctk.CTkEntry(card_main, textvariable=self.var_preco_venda, placeholder_text="0,00")
        self.ent_venda.grid(row=6, column=3, sticky="ew", padx=12, pady=6)

        # Card fiscal
        card_fiscal = ctk.CTkFrame(wrap, corner_radius=12)
        card_fiscal.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card_fiscal.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card_fiscal, text="Dados Fiscais", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 10)
        )

        ctk.CTkLabel(card_fiscal, text="NCM * (8 díg.):").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.ent_ncm = ctk.CTkEntry(card_fiscal, textvariable=self.var_ncm, placeholder_text="Ex.: 85171231")
        self.ent_ncm.grid(row=1, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_fiscal, text="EAN/GTIN:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.ent_ean = ctk.CTkEntry(card_fiscal, textvariable=self.var_ean, placeholder_text="8/12/13/14 dígitos")
        self.ent_ean.grid(row=2, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_fiscal, text="CEST (7 díg.):").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        self.ent_cest = ctk.CTkEntry(card_fiscal, textvariable=self.var_cest, placeholder_text="Ex.: 0100100")
        self.ent_cest.grid(row=3, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_fiscal, text="Origem:").grid(row=4, column=0, sticky="w", padx=12, pady=6)
        self.opt_origem = ctk.CTkOptionMenu(
            card_fiscal,
            variable=self.var_origem,
            values=[
                "0 - Nacional",
                "1 - Estrangeira (Importação direta)",
                "2 - Estrangeira (Adquirida no mercado interno)",
            ],
            command=lambda _: self._run_validation(),
        )
        self.opt_origem.grid(row=4, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_fiscal, text="CST/CSOSN:").grid(row=5, column=0, sticky="w", padx=12, pady=6)
        self.ent_cst = ctk.CTkEntry(card_fiscal, textvariable=self.var_cst, placeholder_text="Ex.: 060 ou 102")
        self.ent_cst.grid(row=5, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(card_fiscal, text="CFOP padrão:").grid(row=6, column=0, sticky="w", padx=12, pady=6)
        self.ent_cfop = ctk.CTkEntry(card_fiscal, textvariable=self.var_cfop, placeholder_text="Ex.: 5102")
        self.ent_cfop.grid(row=6, column=1, sticky="ew", padx=12, pady=6)

        trib = ctk.CTkFrame(card_fiscal, fg_color="transparent")
        trib.grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 12))
        for col in (1, 3, 5):
            trib.grid_columnconfigure(col, weight=1)

        ctk.CTkLabel(trib, text="PIS:").grid(row=0, column=0, sticky="w", pady=4)
        ctk.CTkEntry(trib, textvariable=self.var_pis).grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=4)

        ctk.CTkLabel(trib, text="COFINS:").grid(row=0, column=2, sticky="w", pady=4)
        ctk.CTkEntry(trib, textvariable=self.var_cofins).grid(row=0, column=3, sticky="ew", padx=(6, 12), pady=4)

        ctk.CTkLabel(trib, text="IPI:").grid(row=0, column=4, sticky="w", pady=4)
        ctk.CTkEntry(trib, textvariable=self.var_ipi).grid(row=0, column=5, sticky="ew", padx=(6, 0), pady=4)

    def _build_validation_footer(self):
        block = ctk.CTkFrame(self, corner_radius=12)
        block.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 12))
        block.grid_rowconfigure(1, weight=1)
        block.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(block, text="Validações / Retorno", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6)
        )

        self.txt_valid = ctk.CTkTextbox(block, height=110)
        self.txt_valid.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.txt_valid.configure(state="disabled")

        self.lbl_resume = ctk.CTkLabel(block, text="Status: Pronto.", text_color="gray80")
        self.lbl_resume.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 12))

    def _build_actions(self):
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        actions.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(actions, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        self.btn_cancel_edit = ctk.CTkButton(left, text="Cancelar edição", width=160, command=self.cancel_edit)
        self.btn_cancel_edit.grid(row=0, column=0, padx=6)
        self.btn_cancel_edit.configure(state="disabled")

        right = ctk.CTkFrame(actions, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(right, text="Salvar", command=self.on_save, width=140).grid(row=0, column=0, padx=6)
        ctk.CTkButton(right, text="Salvar e novo", command=self.on_save_new, width=140).grid(row=0, column=1, padx=6)
        ctk.CTkButton(right, text="Limpar", command=self.on_clear, width=120).grid(row=0, column=2, padx=6)
        ctk.CTkButton(right, text="Voltar", command=self.on_back, width=120).grid(row=0, column=3, padx=6)

    # ---------- Lógica ----------
    def on_show(self):
        self._produtos_cache = load_produtos()
        if self.editing_id is None:
            self._generate_sku(force=True)
        self._run_validation()

    def start_edit(self, produto: dict):
        """Carrega um produto no formulário para edição."""
        self.editing_id = int(produto.get("id"))
        self.editing_created_at = str(produto.get("created_at") or "")

        self.var_ativo.set(bool(produto.get("ativo", True)))
        self.var_categoria.set(str(produto.get("categoria", "")))
        self.var_sku.set(str(produto.get("sku", "")))
        self.var_marca.set(str(produto.get("marca", "")))
        self.var_unidade.set(str(produto.get("unidade", "UN")).upper())
        self.var_estoque_ini.set(str(produto.get("estoque_inicial", 0)))
        self.var_preco_custo.set(fmt_money(produto.get("preco_custo", 0)))
        self.var_preco_venda.set(fmt_money(produto.get("preco_venda", 0)))

        self.var_ncm.set(str(produto.get("ncm", "")))
        self.var_ean.set(str(produto.get("ean", "")))
        self.var_cest.set(str(produto.get("cest", "")))
        self.var_origem.set(str(produto.get("origem", "0 - Nacional")))
        self.var_cst.set(str(produto.get("cst_csosn", "")))
        self.var_cfop.set(str(produto.get("cfop", "")))
        self.var_pis.set(str(produto.get("pis", "01")))
        self.var_cofins.set(str(produto.get("cofins", "01")))
        self.var_ipi.set(str(produto.get("ipi", "50")))

        self.txt_descricao.delete("1.0", "end")
        self.txt_descricao.insert("end", str(produto.get("descricao", "")))

        self.lbl_title.configure(text="Cadastro de Produto (Edição)")
        self.lbl_sub.configure(text="Você está editando um produto existente. SKU permanece o mesmo.")
        self.btn_cancel_edit.configure(state="normal")

        self._run_validation()
        self._set_app_status(f"Editando produto: {self.var_sku.get().strip()}")

    def cancel_edit(self):
        self.editing_id = None
        self.editing_created_at = None
        self.lbl_title.configure(text="Cadastro de Produto")
        self.lbl_sub.configure(text="Preencha os dados comerciais e fiscais. Campos com * são obrigatórios.")
        self.btn_cancel_edit.configure(state="disabled")
        self.on_clear(keep_category=False)

    def _bind_live_validation(self):
        # categoria: atualiza SKU apenas se não estiver editando
        def on_cat_change(*_):
            if self.editing_id is None:
                self._generate_sku(force=True)
            self._run_validation()

        self.var_categoria.trace_add("write", on_cat_change)

        # demais campos: valida
        for v in [
            self.var_marca, self.var_unidade, self.var_estoque_ini,
            self.var_preco_custo, self.var_preco_venda,
            self.var_ncm, self.var_ean, self.var_cest,
            self.var_cst, self.var_cfop, self.var_pis, self.var_cofins, self.var_ipi
        ]:
            v.trace_add("write", lambda *_: self._run_validation())

        self.txt_descricao.bind("<KeyRelease>", lambda e: self._run_validation())

    @staticmethod
    def _category_prefix(cat: str) -> str:
        cat = (cat or "").strip().upper()
        cat = re.sub(r"[^A-Z0-9]", "", cat)
        if not cat:
            return ""
        return cat[:6] if len(cat) >= 3 else cat

    def _next_id(self) -> int:
        max_id = 0
        for p in self._produtos_cache:
            try:
                max_id = max(max_id, int(p.get("id", 0)))
            except Exception:
                pass
        return max_id + 1

    def _next_seq_for_prefix(self, prefix: str) -> int:
        max_seq = 0
        needle = f"{prefix}-"
        for p in self._produtos_cache:
            sku = str(p.get("sku", ""))
            if sku.startswith(needle):
                suf = sku[len(needle):]
                if suf.isdigit():
                    max_seq = max(max_seq, int(suf))
        return max_seq + 1

    def _generate_sku(self, force: bool = False):
        # em edição, SKU não muda automaticamente
        if self.editing_id is not None:
            return

        cat = (self.var_categoria.get() or "").strip()
        prefix = self._category_prefix(cat)

        if not prefix:
            if force:
                self.var_sku.set("")
            return

        seq = self._next_seq_for_prefix(prefix)
        self.var_sku.set(f"{prefix}-{seq:06d}")

    def _regen_sku_manual(self):
        """Permite gerar SKU manualmente (se quiser refazer)."""
        if not self.var_categoria.get().strip():
            self._set_app_status("Informe a categoria antes de gerar SKU.")
            return
        # mesmo em edição, permite regenerar se a pessoa clicar
        if self.editing_id is not None:
            ok = messagebox.askyesno("Regenerar SKU", "Você está em edição. Deseja realmente gerar um novo SKU?")
            if not ok:
                return
            self.editing_id = None  # volta para modo 'novo' para gerar sequencia corretamente
            self.editing_created_at = None
            self.lbl_title.configure(text="Cadastro de Produto")
            self.lbl_sub.configure(text="Preencha os dados comerciais e fiscais. Campos com * são obrigatórios.")
            self.btn_cancel_edit.configure(state="disabled")

        self._produtos_cache = load_produtos()
        self._generate_sku(force=True)
        self._run_validation()
        self._set_app_status(f"SKU gerado: {self.var_sku.get().strip()}")

    def _get_descricao(self) -> str:
        return (self.txt_descricao.get("1.0", "end").strip() or "")

    def _collect_data(self, keep_created: bool = False) -> dict:
        created_at = self.editing_created_at if keep_created else None
        if not created_at:
            created_at = datetime.now().isoformat(timespec="seconds")

        return {
            "id": self.editing_id if self.editing_id is not None else self._next_id(),
            "ativo": bool(self.var_ativo.get()),
            "categoria": self.var_categoria.get().strip(),
            "sku": self.var_sku.get().strip(),
            "marca": self.var_marca.get().strip(),
            "descricao": self._get_descricao(),
            "unidade": self.var_unidade.get().strip().upper(),
            "estoque_inicial": int((self.var_estoque_ini.get().strip() or "0")),
            "preco_custo": parse_money(self.var_preco_custo.get().strip() or "0"),
            "preco_venda": parse_money(self.var_preco_venda.get().strip() or "0"),
            "ncm": _only_digits(self.var_ncm.get()),
            "ean": _only_digits(self.var_ean.get()),
            "cest": _only_digits(self.var_cest.get()),
            "origem": self.var_origem.get(),
            "cst_csosn": self.var_cst.get().strip(),
            "cfop": _only_digits(self.var_cfop.get()),
            "pis": self.var_pis.get().strip(),
            "cofins": self.var_cofins.get().strip(),
            "ipi": self.var_ipi.get().strip(),
            "created_at": created_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _ok(self, msg: str): self._last_validation["ok"].append(msg)
    def _warn(self, msg: str): self._last_validation["warn"].append(msg)
    def _err(self, msg: str): self._last_validation["err"].append(msg)

    def _run_validation(self):
        self._last_validation = {"ok": [], "warn": [], "err": []}

        if not self.var_categoria.get().strip():
            self._err("Categoria é obrigatória.")
        else:
            self._ok("Categoria: OK")

        desc = self._get_descricao()
        if not desc:
            self._err("Descrição é obrigatória.")
        else:
            self._ok("Descrição: OK")

        unidade = self.var_unidade.get().strip().upper()
        if not unidade:
            self._err("Unidade é obrigatória.")
        else:
            self._ok("Unidade: OK")

        if self.var_sku.get().strip():
            self._ok("SKU: OK.")
        else:
            self._warn("SKU: será gerado ao informar a categoria.")

        if not _is_nonneg_int(self.var_estoque_ini.get().strip()):
            self._err("Estoque inicial inválido (use inteiro ≥ 0).")
        else:
            self._ok("Estoque inicial: OK")

        if not _is_nonneg_float(self.var_preco_custo.get().strip()):
            self._err("Preço custo inválido (use número ≥ 0).")
        else:
            self._ok("Preço custo: OK")

        if not _is_nonneg_float(self.var_preco_venda.get().strip()):
            self._err("Preço venda inválido (use número ≥ 0).")
        else:
            self._ok("Preço venda: OK")

        ncm = _only_digits(self.var_ncm.get())
        if len(ncm) != 8:
            self._err("NCM inválido: deve ter exatamente 8 dígitos.")
        else:
            self._ok("NCM: OK (8 dígitos).")

        ean = _only_digits(self.var_ean.get())
        if ean:
            if len(ean) not in (8, 12, 13, 14):
                self._err("EAN inválido: use 8/12/13/14 dígitos.")
            elif not is_valid_gtin(ean):
                self._err("EAN inválido: dígito verificador não confere.")
            else:
                self._ok("EAN: OK (GTIN válido).")
        else:
            self._warn("EAN: não informado (ok se não aplicável).")

        cest = _only_digits(self.var_cest.get())
        if cest:
            if len(cest) != 7:
                self._err("CEST inválido: deve ter 7 dígitos.")
            else:
                self._ok("CEST: OK (7 dígitos).")
        else:
            self._warn("CEST: não informado (ok se não aplicável).")

        cfop = _only_digits(self.var_cfop.get())
        if cfop and len(cfop) != 4:
            self._warn("CFOP: geralmente 4 dígitos (verifique).")
        elif cfop:
            self._ok("CFOP: OK (4 dígitos).")

        self._render_validation()

    def _render_validation(self):
        lines = []
        for m in self._last_validation["ok"]:
            lines.append(f"[OK] {m}")
        for m in self._last_validation["warn"]:
            lines.append(f"[!!] {m}")
        for m in self._last_validation["err"]:
            lines.append(f"[ERRO] {m}")

        self.txt_valid.configure(state="normal")
        self.txt_valid.delete("1.0", "end")
        self.txt_valid.insert("end", "\n".join(lines) if lines else "Status: pronto.")
        self.txt_valid.configure(state="disabled")

        if self._last_validation["err"]:
            self.lbl_resume.configure(text=f"Status: {self._last_validation['err'][0]}", text_color="#ffb4b4")
        else:
            self.lbl_resume.configure(text="Status: Tudo certo para salvar.", text_color="gray80")

    # ---------- Ações ----------
    def on_save(self):
        self._run_validation()
        if self._last_validation["err"]:
            self._set_app_status("Falha ao salvar: corrija os erros.")
            return

        self._produtos_cache = load_produtos()

        if not self.var_sku.get().strip():
            self._generate_sku(force=True)

        produto = self._collect_data(keep_created=True)

        # unicidade do SKU (ignora o próprio id se estiver editando)
        for p in self._produtos_cache:
            if str(p.get("sku", "")).strip() == produto["sku"]:
                if self.editing_id is None or int(p.get("id")) != int(produto["id"]):
                    self._set_app_status(f"SKU já existe: {produto['sku']}")
                    messagebox.showwarning("SKU duplicado", f"Já existe um produto com SKU {produto['sku']}.")
                    return

        # update/insert
        updated = False
        if self.editing_id is not None:
            for i, p in enumerate(self._produtos_cache):
                if int(p.get("id", -1)) == int(self.editing_id):
                    self._produtos_cache[i] = produto
                    updated = True
                    break

        if not updated:
            self._produtos_cache.append(produto)

        save_produtos(self._produtos_cache)

        msg = f"Produto {'atualizado' if updated else 'salvo'}: {produto['sku']}"
        self._set_app_status(msg)
        self._log_action(msg)

        self.on_clear(keep_category=True)

    def on_save_new(self):
        self.on_save()

    def on_clear(self, keep_category: bool = False):
        cat = self.var_categoria.get() if keep_category else ""
        ativo = self.var_ativo.get()

        # se estiver editando, manter modo edição até cancelar explicitamente
        self.var_categoria.set(cat)
        self.var_marca.set("")
        self.var_unidade.set("UN")
        self.var_estoque_ini.set("0")
        self.var_preco_custo.set("")
        self.var_preco_venda.set("")

        self.var_ncm.set("")
        self.var_ean.set("")
        self.var_cest.set("")
        self.var_origem.set("0 - Nacional")
        self.var_cst.set("")
        self.var_cfop.set("")
        self.var_pis.set("01")
        self.var_cofins.set("01")
        self.var_ipi.set("50")

        self.var_ativo.set(ativo)
        self.txt_descricao.delete("1.0", "end")

        self._produtos_cache = load_produtos()
        if self.editing_id is None:
            self._generate_sku(force=True)
        self._run_validation()

        self._set_app_status("Formulário limpo.")

    def on_back(self):
        app = self.winfo_toplevel()
        if hasattr(app, "go"):
            app.go("dashboard")
        self._set_app_status("Voltou para Dashboard.")

    def _set_app_status(self, msg: str):
        app = self.winfo_toplevel()
        if hasattr(app, "set_status"):
            app.set_status(msg)

    def _log_action(self, msg: str):
        app = self.winfo_toplevel()
        if hasattr(app, "log_action"):
            app.log_action(msg)


class ListarProdutosScreen(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Listar Produtos", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 6)
        )

        # Filtros
        filtros = ctk.CTkFrame(self, corner_radius=12)
        filtros.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        filtros.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(filtros, text="Filtro:").grid(row=0, column=0, padx=12, pady=12, sticky="w")
        self.var_filtro = ctk.StringVar(value="")
        ent = ctk.CTkEntry(filtros, textvariable=self.var_filtro, placeholder_text="SKU, descrição, NCM, marca...")
        ent.grid(row=0, column=1, padx=12, pady=12, sticky="ew")

        self.var_only_active = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(filtros, text="Somente ativos", variable=self.var_only_active, command=self.reload).grid(
            row=0, column=2, padx=12, pady=12, sticky="e"
        )

        ctk.CTkButton(filtros, text="Aplicar", command=self.reload, width=120).grid(
            row=0, column=3, padx=12, pady=12
        )
        ctk.CTkButton(filtros, text="Recarregar", command=self.reload, width=120).grid(
            row=0, column=4, padx=(0, 12), pady=12
        )

        # Tabela (Treeview)
        table_wrap = ctk.CTkFrame(self, corner_radius=12)
        table_wrap.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)

        cols = ("id", "sku", "ativo", "categoria", "marca", "ncm", "preco_venda")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings", height=12)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.heading("id", text="ID")
        self.tree.heading("sku", text="SKU")
        self.tree.heading("ativo", text="Ativo")
        self.tree.heading("categoria", text="Categoria")
        self.tree.heading("marca", text="Marca")
        self.tree.heading("ncm", text="NCM")
        self.tree.heading("preco_venda", text="Preço Venda")

        self.tree.column("id", width=60, anchor="center")
        self.tree.column("sku", width=140, anchor="w")
        self.tree.column("ativo", width=80, anchor="center")
        self.tree.column("categoria", width=140, anchor="w")
        self.tree.column("marca", width=140, anchor="w")
        self.tree.column("ncm", width=100, anchor="center")
        self.tree.column("preco_venda", width=110, anchor="e")

        # Ações
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))
        actions.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(actions, text="Editar", width=120, command=self.on_edit_selected).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(actions, text="Ativar/Inativar", width=140, command=self.on_toggle_active).grid(row=0, column=1, padx=(0, 8))

        self.lbl_count = ctk.CTkLabel(actions, text="0 registros", text_color="gray80")
        self.lbl_count.grid(row=0, column=2, sticky="w")

        # Enter no filtro aplica
        ent.bind("<Return>", lambda e: self.reload())
        self.tree.bind("<Double-1>", lambda e: self.on_edit_selected())

    def on_show(self):
        self.reload()

    def _get_app(self):
        return self.winfo_toplevel()

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        try:
            return int(values[0])
        except Exception:
            return None

    def on_edit_selected(self):
        pid = self._selected_id()
        if pid is None:
            self._get_app().set_status("Selecione um produto para editar.")
            return

        app = self._get_app()
        if hasattr(app, "edit_product_by_id"):
            app.edit_product_by_id(pid)

    def on_toggle_active(self):
        pid = self._selected_id()
        if pid is None:
            self._get_app().set_status("Selecione um produto para ativar/inativar.")
            return

        produtos = load_produtos()
        found = None
        for p in produtos:
            try:
                if int(p.get("id", -1)) == int(pid):
                    found = p
                    break
            except Exception:
                pass

        if not found:
            self._get_app().set_status("Produto não encontrado.")
            return

        sku = str(found.get("sku", ""))
        ativo = bool(found.get("ativo", True))
        novo = not ativo

        ok = messagebox.askyesno(
            "Confirmar",
            f"Deseja {'ATIVAR' if novo else 'INATIVAR'} o produto {sku}?"
        )
        if not ok:
            return

        found["ativo"] = novo
        found["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if not novo:
            found["inativado_at"] = datetime.now().isoformat(timespec="seconds")
        else:
            found["inativado_at"] = ""

        save_produtos(produtos)
        self.reload()

        msg = f"Produto {'ativado' if novo else 'inativado'}: {sku}"
        self._get_app().set_status(msg)
        if hasattr(self._get_app(), "log_action"):
            self._get_app().log_action(msg)

    def reload(self):
        produtos = load_produtos()

        filtro = (self.var_filtro.get() or "").strip().lower()
        only_active = bool(self.var_only_active.get())

        def match(p: dict) -> bool:
            if only_active and not bool(p.get("ativo", True)):
                return False
            if not filtro:
                return True
            blob = " ".join([
                str(p.get("sku", "")),
                str(p.get("descricao", "")),
                str(p.get("ncm", "")),
                str(p.get("marca", "")),
                str(p.get("categoria", "")),
            ]).lower()
            return filtro in blob

        produtos_filtrados = [p for p in produtos if match(p)]

        # limpa tabela
        for item in self.tree.get_children():
            self.tree.delete(item)

        # popula
        for p in produtos_filtrados:
            ativo = "Sim" if bool(p.get("ativo", True)) else "Não"
            self.tree.insert("", "end", values=(
                p.get("id", ""),
                p.get("sku", ""),
                ativo,
                p.get("categoria", ""),
                p.get("marca", ""),
                p.get("ncm", ""),
                fmt_money(p.get("preco_venda", 0)),
            ))

        self.lbl_count.configure(text=f"{len(produtos_filtrados)} registros")


# =========================
# App
# =========================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sistema NFE")
        self.geometry("1280x720")

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # estado global (header/footer)
        self.filial_var = tk.StringVar(value=DEFAULT_FILIAL)
        self.amb_var = tk.StringVar(value=DEFAULT_AMBIENTE)
        self.db_var = tk.StringVar(value="Conectado")  # aqui é o "DB" do mock; no seu caso é JSON local

        self.search_var = tk.StringVar(value="")
        self.search_type_var = tk.StringVar(value="Produto")

        self.status_var = tk.StringVar(value="Status: Pronto.")
        self.last_action_var = tk.StringVar(value="Última ação: -")
        self.clock_var = tk.StringVar(value="00:00")

        self._build_header()
        self._build_sidebar()
        self._build_content()
        self._build_footer()

        # Telas
        self.content.register("dashboard", DashboardScreen)
        self.content.register("cad_produto", CadastroProdutoScreen)
        self.content.register("listar_produtos", ListarProdutosScreen)

        self.content.show("dashboard")
        self.log_action("Sistema iniciado.")
        self._tick_clock()

    def report_callback_exception(self, exc, val, tb):
        import traceback
        traceback.print_exception(exc, val, tb)
        self.set_status("Erro inesperado (veja o terminal).")
        self.log_action(f"Erro: {val}")

    def _build_header(self):
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # esquerda: título
        ctk.CTkLabel(header, text="Sistema NFE", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(10, 2)
        )

        # centro: busca
        mid = ctk.CTkFrame(header, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 2))
        mid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(mid, text="Buscar:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ent = ctk.CTkEntry(mid, textvariable=self.search_var, placeholder_text="NF / Produto / Pessoa")
        ent.grid(row=0, column=1, sticky="ew")

        opt = ctk.CTkOptionMenu(mid, variable=self.search_type_var, values=["NF", "Produto", "Pessoa"])
        opt.grid(row=0, column=2, padx=8)

        btn = ctk.CTkButton(mid, text="Ir", width=60, command=self.do_search)
        btn.grid(row=0, column=3)

        ent.bind("<Return>", lambda e: self.do_search())

        # direita: contexto
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=14, pady=(10, 2))

        ctk.CTkLabel(right, text=f"Filial: {self.filial_var.get()}").grid(row=0, column=0, padx=8)
        self.lbl_db = ctk.CTkLabel(right, text=f"DB: {self.db_var.get()}")
        self.lbl_db.grid(row=0, column=1, padx=8)
        ctk.CTkLabel(right, text=f"Amb: {self.amb_var.get()}").grid(row=0, column=2, padx=8)

        # linha inferior (opcional) para separar
        sep = ctk.CTkFrame(header, height=2, fg_color="#2b2b2b")
        sep.grid(row=1, column=0, columnspan=3, sticky="ew", padx=0, pady=(8, 0))

    def _build_sidebar(self):
        sidebar = ctk.CTkScrollableFrame(self, width=260)
        sidebar.grid(row=1, column=0, sticky="nsw", padx=10, pady=10)
        sidebar.grid_columnconfigure(0, weight=1)

        sec_inicio = CollapsibleSection(sidebar, "Início")
        sec_inicio.grid(sticky="ew", pady=(0, 6))
        sec_inicio.add_item("Dashboard", lambda: self.go("dashboard"))

        sec_cad = CollapsibleSection(sidebar, "Cadastros")
        sec_cad.grid(sticky="ew", pady=(0, 6))
        sec_cad.add_item("Produto", lambda: self.go("cad_produto"))
        sec_cad.add_item("Listar Produtos", lambda: self.go("listar_produtos"))

        sec_nf = CollapsibleSection(sidebar, "Notas Fiscais (mock)")
        sec_nf.grid(sticky="ew", pady=(0, 6))
        sec_nf.add_item("Criar Saída", lambda: self._mock("NF Saída ainda não implementada."))
        sec_nf.add_item("Criar Entrada", lambda: self._mock("NF Entrada ainda não implementada."))
        sec_nf.add_item("Listar NFs", lambda: self._mock("Listagem de NFs ainda não implementada."))

        sec_imp = CollapsibleSection(sidebar, "Impostos e Regras (mock)")
        sec_imp.grid(sticky="ew", pady=(0, 6))
        sec_imp.add_item("Calcular NF", lambda: self._mock("Cálculo fiscal ainda não implementado."))
        sec_imp.add_item("Auditar UFs", lambda: self._mock("Auditoria UF ainda não implementada."))

        sec_sys = CollapsibleSection(sidebar, "Sistema")
        sec_sys.grid(sticky="ew", pady=(0, 6))
        sec_sys.add_item("Sair", self.destroy)

    def _build_content(self):
        self.content = ScreenManager(self)
        self.content.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=10)

    def _build_footer(self):
        footer = ctk.CTkFrame(self)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(footer, textvariable=self.status_var, anchor="w", text_color="gray80").grid(
            row=0, column=0, sticky="ew", padx=12, pady=8
        )
        ctk.CTkLabel(footer, textvariable=self.last_action_var, anchor="center", text_color="gray80").grid(
            row=0, column=1, sticky="ew", padx=12, pady=8
        )
        ctk.CTkLabel(footer, textvariable=self.clock_var, anchor="e", text_color="gray80").grid(
            row=0, column=2, sticky="e", padx=12, pady=8
        )

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _mock(self, msg: str):
        self.set_status(msg)
        self.log_action(msg)

    def do_search(self):
        q = (self.search_var.get() or "").strip()
        t = (self.search_type_var.get() or "Produto").strip()

        if not q:
            self.set_status("Informe um termo para buscar.")
            return

        if t == "Produto":
            self.go("listar_produtos")
            scr = self.content.screens.get("listar_produtos")
            if scr and hasattr(scr, "var_filtro") and hasattr(scr, "reload"):
                scr.var_filtro.set(q)
                scr.reload()
            self.set_status(f"Busca em produtos: {q}")
            self.log_action(f"Busca produto: {q}")
        else:
            self.set_status(f"Busca {t} ainda não implementada.")
            self.log_action(f"Tentativa de busca ({t}): {q}")

    def go(self, screen_name: str):
        self.content.show(screen_name)
        self.set_status(f"Tela aberta: {screen_name}")
        self.log_action(f"Tela aberta: {screen_name}")

    def edit_product_by_id(self, pid: int):
        produtos = load_produtos()
        prod = None
        for p in produtos:
            try:
                if int(p.get("id", -1)) == int(pid):
                    prod = p
                    break
            except Exception:
                pass

        if not prod:
            self.set_status("Produto não encontrado para edição.")
            self.log_action(f"Falha edição produto id={pid}")
            return

        self.content.show("cad_produto")
        scr = self.content.screens.get("cad_produto")
        if scr and hasattr(scr, "start_edit"):
            scr.start_edit(prod)
            self.log_action(f"Edição produto: {prod.get('sku', '')}")

    def set_status(self, msg: str):
        self.status_var.set(f"Status: {msg}")

    def log_action(self, msg: str):
        self.last_action_var.set(f"Última ação: {msg}")
        append_audit(msg)


if __name__ == "__main__":
    App().mainloop()