# Sistema_nfe

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =========================================================
# CONFIG / PATHS
# =========================================================
APP_NAME = "Sistema Python - Lançamento de Notas Fiscais (sem MySQL)"
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

FILE_FILIAIS = DATA_DIR / "filiais.json"
FILE_PESSOAS = DATA_DIR / "pessoas.json"
FILE_PRODUTOS = DATA_DIR / "produtos.json"
FILE_ESTOQUE = DATA_DIR / "estoque.json"
FILE_NFS = DATA_DIR / "nfs.json"

FILE_TBL_UF = DATA_DIR / "tabela_uf_aliquotas.json"
FILE_TBL_ST = DATA_DIR / "tabela_st_regras.json"

FILE_UF_PADRAO_CSV = DATA_DIR / "uf_aliquotas_padrao.csv"
FILE_ST_PADRAO_CSV = DATA_DIR / "st_regras_padrao.csv"

ALLOW_NEGATIVE_STOCK = False

UFS_BRASIL = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS",
    "MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"
]

# =========================================================
# REGIÕES / ICMS INTERESTADUAL (4/7/12)
# =========================================================
REGIOES = {
    "N": {"AC","AP","AM","PA","RO","RR","TO"},
    "NE": {"AL","BA","CE","MA","PB","PE","PI","RN","SE"},
    "CO": {"DF","GO","MT","MS"},
    "SE": {"ES","MG","RJ","SP"},
    "S": {"PR","RS","SC"},
}

def uf_regiao(uf: str) -> str:
    uf = (uf or "").strip().upper()
    for reg, ufs in REGIOES.items():
        if uf in ufs:
            return reg
    return "SE"

def aliq_interestadual(uf_origem: str, uf_destino: str, flag_importado: int) -> float:
    """
    Regra geral:
      - Importado (RSF 13/2012): 4%
      - Origem S/SE -> Destino N/NE/CO: 7%
      - demais: 12%
    """
    if int(flag_importado) == 1:
        return 4.0
    ro = uf_regiao(uf_origem)
    rd = uf_regiao(uf_destino)
    if (ro in ("S","SE")) and (rd in ("N","NE","CO")):
        return 7.0
    return 12.0

# =========================================================
# MODELOS (JSON-friendly)
# =========================================================
@dataclass
class Filial:
    id: int
    nome: str
    uf: str
    ativo: int = 1

@dataclass
class Pessoa:
    id: int
    nome: str
    tipo: str  # C, F, A
    documento: str
    uf: str
    ind_ie_dest: int  # 1,2,9
    ativo: int = 1

@dataclass
class Produto:
    id: int
    sku: str
    descricao: str
    ncm: str
    cest: str
    preco_venda: float
    flag_importado: int = 0
    ativo: int = 1

@dataclass
class NFItem:
    id: int
    produto_id: int
    sku: str
    descricao: str
    ncm: str
    cest: str
    cfop: str
    qtd: float
    v_unit: float
    desconto: float = 0.0
    frete: float = 0.0
    seguro: float = 0.0
    outras: float = 0.0
    v_bruto: float = 0.0
    v_total: float = 0.0
    impostos: Optional[Dict[str, Any]] = None

@dataclass
class NF:
    id: int
    tipo_operacao: str  # ENTRADA | SAIDA
    filial_id: int
    emitente_id: int
    destinatario_id: int
    uf_origem: str
    uf_destino: str
    ind_final: int  # 1/0
    modelo: str = "55"
    serie: int = 1
    numero: int = 0
    data_emissao: str = ""
    status: str = "RASCUNHO"  # RASCUNHO/EMITIDA/CANCELADA
    estoque_postado: int = 0  # 0/1
    itens: Optional[List[Dict[str, Any]]] = None
    totais: Optional[Dict[str, Any]] = None

# =========================================================
# UTIL: IO / VALIDATION
# =========================================================
def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def title(s: str) -> None:
    print("\n" + "=" * 80)
    print(s)
    print("=" * 80)

def money(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def ask_str(msg: str, required: bool = True) -> str:
    while True:
        v = input(msg).strip()
        if not v and not required:
            return ""
        if required and not v:
            print("Campo obrigatório.")
            continue
        return v

def ask_int(msg: str, required: bool = True, min_v: Optional[int] = None) -> Optional[int]:
    while True:
        v = input(msg).strip()
        if not v and not required:
            return None
        try:
            n = int(v)
            if min_v is not None and n < min_v:
                print(f"Informe um número >= {min_v}.")
                continue
            return n
        except ValueError:
            print("Número inteiro inválido.")

def ask_float(msg: str, required: bool = True, min_v: Optional[float] = None) -> Optional[float]:
    while True:
        v = input(msg).strip()
        if not v and not required:
            return None
        v = v.replace("%","").replace(" ","").replace(",",".")
        try:
            f = float(v)
            if min_v is not None and f < min_v:
                print(f"Informe um valor >= {min_v}.")
                continue
            return f
        except ValueError:
            print("Número inválido.")

def ask_uf(msg: str) -> str:
    while True:
        uf = input(msg).strip().upper()
        if uf in UFS_BRASIL:
            return uf
        print("UF inválida. Ex.: SP, MG, RJ. (Use siglas oficiais)")

def ask_date_yyyy_mm_dd(msg: str, required: bool = False, default_today: bool = True) -> str:
    while True:
        v = input(msg).strip()
        if not v and not required:
            return date.today().strftime("%Y-%m-%d") if default_today else ""
        try:
            d = datetime.strptime(v, "%Y-%m-%d").date()
            return d.strftime("%Y-%m-%d")
        except ValueError:
            print("Data inválida. Use YYYY-MM-DD.")

def normalize_digits(s: str, width: int) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = "".join(c for c in s if c.isdigit())
    return s.zfill(width)

def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def parse_uf_list(s: str) -> List[str]:
    """
    Aceita:
      - "TODAS"
      - "SP,MG,RJ"
      - "sp mg rj"
    """
    s = (s or "").strip().upper()
    if not s:
        return []
    if s in ("TODAS", "ALL", "*"):
        return list(UFS_BRASIL)
    for ch in [";", "|", " "]:
        s = s.replace(ch, ",")
    parts = [p.strip().upper() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        if p in UFS_BRASIL and p not in out:
            out.append(p)
    return out

# =========================================================
# STORAGE: JSON atomic
# =========================================================
def read_json(path: Path, default: Any) -> Any:
    ensure_data_dir()
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: Path, data: Any) -> None:
    ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def load_store(path: Path) -> Dict[str, Any]:
    return read_json(path, {"seq": 0, "items": []})

def save_store(path: Path, store: Dict[str, Any]) -> None:
    write_json(path, store)

def next_id(store: Dict[str, Any]) -> int:
    store["seq"] = int(store.get("seq", 0)) + 1
    return int(store["seq"])

def find_by_id(store: Dict[str, Any], _id: int) -> Optional[Dict[str, Any]]:
    for it in store.get("items", []):
        if int(it.get("id", 0)) == int(_id):
            return it
    return None

# =========================================================
# (1) UF TABLE: bootstrap + import
# =========================================================
def load_tabela_uf() -> Dict[str, Dict[str, Any]]:
    data = read_json(FILE_TBL_UF, {"updated_at":"", "ufs": {}})
    return data.get("ufs", {})

def save_tabela_uf(ufs: Dict[str, Dict[str, Any]]) -> None:
    write_json(FILE_TBL_UF, {"updated_at": datetime.now().isoformat(timespec="seconds"), "ufs": ufs})

def bootstrap_ufs_generic() -> None:
    """
    Preenche as 27 UFs com valores demonstrativos para não travar.
    """
    ufs = load_tabela_uf()
    changed = False
    for uf in UFS_BRASIL:
        if uf not in ufs:
            ufs[uf] = {"aliq_icms_interna": 18.0, "aliq_fcp": 2.0}
            changed = True
    if changed:
        save_tabela_uf(ufs)

def import_uf_aliquotas_csv(path: str) -> None:
    title("Importar UF Alíquotas (CSV)")
    if not os.path.exists(path):
        print("Arquivo não encontrado.")
        return

    tabela: Dict[str, Any] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {"uf", "aliq_icms_interna", "aliq_fcp"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            print(f"CSV inválido. Cabeçalho esperado: {sorted(required)}")
            return

        for row in reader:
            uf = (row.get("uf") or "").strip().upper()
            if not uf:
                continue
            icms = float(str(row.get("aliq_icms_interna") or "0").replace(",", "."))
            fcp = float(str(row.get("aliq_fcp") or "0").replace(",", "."))
            tabela[uf] = {"aliq_icms_interna": icms, "aliq_fcp": fcp}

    for uf in UFS_BRASIL:
        tabela.setdefault(uf, {"aliq_icms_interna": 0.0, "aliq_fcp": 0.0})

    save_tabela_uf(tabela)
    print(f"Importação concluída. UFs carregadas: {len(tabela)}")

# =========================================================
# ST TABLE: load/save compat + ids + import + match
# =========================================================
def _normalize_st_file(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backward compatible:
      - antigo: {"updated_at":"", "regras":[...]}
      - novo:   {"updated_at":"", "seq": N, "regras":[...]}
    """
    regras = data.get("regras", [])
    if not isinstance(regras, list):
        regras = []
    if "seq" not in data:
        max_id = 0
        for r in regras:
            try:
                max_id = max(max_id, int(r.get("id", 0)))
            except Exception:
                pass
        data["seq"] = max_id
    # garante id em cada regra
    max_id = int(data.get("seq", 0) or 0)
    changed = False
    for r in regras:
        if not r.get("id"):
            max_id += 1
            r["id"] = max_id
            changed = True
    if changed:
        data["seq"] = max_id
    data["regras"] = regras
    data.setdefault("updated_at", "")
    return data

def load_tabela_st_data() -> Dict[str, Any]:
    data = read_json(FILE_TBL_ST, {"updated_at":"", "seq": 0, "regras": []})
    data = _normalize_st_file(data)
    return data

def save_tabela_st_data(data: Dict[str, Any]) -> None:
    data = _normalize_st_file(data)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(FILE_TBL_ST, data)

def load_tabela_st() -> List[Dict[str, Any]]:
    return load_tabela_st_data().get("regras", [])

def import_st_regras_csv(path: str) -> None:
    title("Importar Regras ST (CSV)")
    if not os.path.exists(path):
        print("Arquivo não encontrado.")
        return

    data = load_tabela_st_data()
    regras: List[Dict[str, Any]] = data.get("regras", [])
    seq = int(data.get("seq", 0) or 0)

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {
            "uf_origem","uf_destino","ncm","cest","cfop",
            "mva","red_bc_st","aliq_icms_interna_dest","aliq_fcp_dest",
            "vig_ini","vig_fim","prioridade","ativo"
        }
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            print(f"CSV inválido. Cabeçalho esperado: {sorted(required)}")
            return

        count = 0
        for row in reader:
            uf_or = (row.get("uf_origem") or "").strip().upper()
            uf_de = (row.get("uf_destino") or "").strip().upper()
            if not uf_or or not uf_de:
                continue

            seq += 1
            r = {
                "id": seq,
                "uf_origem": uf_or,
                "uf_destino": uf_de,
                "ncm": normalize_digits(str(row.get("ncm") or "").strip(), 8),
                "cest": normalize_digits(str(row.get("cest") or "").strip(), 7),
                "cfop": normalize_digits(str(row.get("cfop") or "").strip(), 4),
                "mva": float(str(row.get("mva") or "0").replace(",", ".")),
                "red_bc_st": float(str(row.get("red_bc_st") or "0").replace(",", ".")),
                "aliq_icms_interna_dest": str(row.get("aliq_icms_interna_dest") or "").strip(),
                "aliq_fcp_dest": str(row.get("aliq_fcp_dest") or "").strip(),
                "vig_ini": str(row.get("vig_ini") or "").strip(),
                "vig_fim": str(row.get("vig_fim") or "").strip(),
                "prioridade": int(str(row.get("prioridade") or "0").strip() or "0"),
                "ativo": int(str(row.get("ativo") or "1").strip() or "1"),
            }
            if not r["vig_ini"]:
                r["vig_ini"] = date.today().strftime("%Y-%m-%d")

            if r["aliq_icms_interna_dest"] != "":
                r["aliq_icms_interna_dest"] = float(r["aliq_icms_interna_dest"].replace(",", "."))
            else:
                r["aliq_icms_interna_dest"] = None

            if r["aliq_fcp_dest"] != "":
                r["aliq_fcp_dest"] = float(r["aliq_fcp_dest"].replace(",", "."))
            else:
                r["aliq_fcp_dest"] = None

            regras.append(r)
            count += 1

    data["seq"] = seq
    data["regras"] = regras
    save_tabela_st_data(data)
    print(f"Importação concluída. Regras ST importadas: {count} | Total no sistema: {len(regras)}")

def in_vigencia(vig_ini: str, vig_fim: str, dt: str) -> bool:
    d = parse_date(dt)
    ini = parse_date(vig_ini)
    if d < ini:
        return False
    if vig_fim:
        fim = parse_date(vig_fim)
        return d <= fim
    return True

def spec_score(rule: Dict[str, Any]) -> int:
    score = 0
    if rule.get("ncm"): score += 4
    if rule.get("cest"): score += 2
    if rule.get("cfop"): score += 1
    return score

def escolher_regra_st(
    regras: List[Dict[str, Any]],
    uf_origem: str,
    uf_destino: str,
    ncm: str,
    cest: str,
    cfop: str,
    data_emissao: str
) -> Optional[Dict[str, Any]]:
    uf_origem = (uf_origem or "").upper()
    uf_destino = (uf_destino or "").upper()
    ncm = normalize_digits(ncm, 8)
    cest = normalize_digits(cest, 7)
    cfop = normalize_digits(cfop, 4)

    candidatas: List[Dict[str, Any]] = []
    for r in regras:
        if int(r.get("ativo", 1)) != 1:
            continue
        if str(r.get("uf_origem","")).upper() != uf_origem:
            continue
        if str(r.get("uf_destino","")).upper() != uf_destino:
            continue
        if not in_vigencia(str(r.get("vig_ini","1900-01-01")), str(r.get("vig_fim","")), data_emissao):
            continue

        rncm = normalize_digits(str(r.get("ncm","")), 8)
        rcest = normalize_digits(str(r.get("cest","")), 7)
        rcfop = normalize_digits(str(r.get("cfop","")), 4)

        if rncm and rncm != ncm:
            continue
        if rcest and rcest != cest:
            continue
        if rcfop and rcfop != cfop:
            continue

        candidatas.append(r)

    if not candidatas:
        return None

    candidatas.sort(key=lambda x: (int(x.get("prioridade",0)), spec_score(x)), reverse=True)
    return candidatas[0]

# =========================================================
# (AUTOMAÇÃO) Parâmetros padrão prontos (gera CSV e importa)
# =========================================================
def gerar_csv_padrao_uf(path: Path) -> None:
    rows = [{"uf": uf, "aliq_icms_interna": "18.00", "aliq_fcp": "2.00"} for uf in UFS_BRASIL]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["uf","aliq_icms_interna","aliq_fcp"], delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def gerar_csv_padrao_st_base(path: Path) -> None:
    """
    Gera um ST base único (você duplica em lote depois).
    Campos vazios (ncm/cest) NÃO são recomendados porque viram regra genérica.
    Então o padrão já vem com um exemplo de NCM/CEST para você substituir depois se quiser.
    """
    rows = [{
        "uf_origem": "SP",
        "uf_destino": "MG",
        "ncm": "85171231",      # EXEMPLO (smartphone)
        "cest": "0210690",      # EXEMPLO (7 dígitos)
        "cfop": "6102",
        "mva": "40.00",
        "red_bc_st": "0.00",
        "aliq_icms_interna_dest": "18.00",
        "aliq_fcp_dest": "2.00",
        "vig_ini": date.today().strftime("%Y-%m-%d"),
        "vig_fim": "",
        "prioridade": "10",
        "ativo": "1",
    }]
    fields = [
        "uf_origem","uf_destino","ncm","cest","cfop","mva","red_bc_st",
        "aliq_icms_interna_dest","aliq_fcp_dest","vig_ini","vig_fim","prioridade","ativo"
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def carregar_parametros_padrao_sem_editar() -> None:
    title("Carregar parâmetros padrão (UF + ST base) - automático")
    ensure_data_dir()
    gerar_csv_padrao_uf(FILE_UF_PADRAO_CSV)
    gerar_csv_padrao_st_base(FILE_ST_PADRAO_CSV)

    print(f"Gerado: {FILE_UF_PADRAO_CSV}")
    print(f"Gerado: {FILE_ST_PADRAO_CSV}")

    import_uf_aliquotas_csv(str(FILE_UF_PADRAO_CSV))
    import_st_regras_csv(str(FILE_ST_PADRAO_CSV))

    print("\nConcluído.")
    print("Próximo passo recomendado: duplicar a regra ST base para as UFs que você quiser (menu).")

# =========================================================
# (AUTOMAÇÃO) ST: criar base + duplicar em lote + listar/remover
# =========================================================
def listar_regras_st(limit: int = 200) -> List[Dict[str, Any]]:
    title("Listar regras ST")
    regras = load_tabela_st()
    if not regras:
        print("Nenhuma regra cadastrada.")
        return []
    regras_sorted = sorted(regras, key=lambda r: int(r.get("id",0)), reverse=True)[:limit]
    for r in regras_sorted:
        print(
            f"[{r.get('id')}] {r.get('uf_origem')}->{r.get('uf_destino')} | "
            f"NCM={r.get('ncm','')} CEST={r.get('cest','')} CFOP={r.get('cfop','')} | "
            f"MVA={r.get('mva',0)} Red={r.get('red_bc_st',0)} | "
            f"vig {r.get('vig_ini')}..{r.get('vig_fim','')} | pri={r.get('prioridade',0)} ativo={r.get('ativo',1)}"
        )
    return regras_sorted

def criar_regra_st_base_assistente() -> None:
    title("Assistente - Criar regra ST base (sem CSV)")
    data = load_tabela_st_data()
    regras = data.get("regras", [])
    seq = int(data.get("seq", 0) or 0)

    uf_origem = ask_uf("UF origem: ")
    uf_destino = ask_uf("UF destino: ")
    ncm = normalize_digits(ask_str("NCM (8 dígitos): "), 8)
    cest = normalize_digits(ask_str("CEST (7 dígitos) [opcional]: ", required=False), 7)
    cfop = normalize_digits(ask_str("CFOP [6102]: ", required=False) or "6102", 4)

    mva = ask_float("MVA (%) [40]: ", required=False, min_v=0.0) or 40.0
    red = ask_float("Redução BC ST (%) [0]: ", required=False, min_v=0.0) or 0.0
    aliq_int = ask_float("Alíquota interna destino (%) [18]: ", required=False, min_v=0.0) or 18.0
    aliq_fcp = ask_float("FCP destino (%) [2]: ", required=False, min_v=0.0) or 2.0

    vig_ini = ask_date_yyyy_mm_dd("Vigência início (YYYY-MM-DD) [hoje]: ", required=False, default_today=True)
    vig_fim = ask_date_yyyy_mm_dd("Vigência fim (YYYY-MM-DD) [vazio=sem fim]: ", required=False, default_today=False)

    prioridade = ask_int("Prioridade [10]: ", required=False, min_v=0) or 10
    ativo = 1

    seq += 1
    regra = {
        "id": seq,
        "uf_origem": uf_origem,
        "uf_destino": uf_destino,
        "ncm": ncm,
        "cest": cest,
        "cfop": cfop,
        "mva": float(mva),
        "red_bc_st": float(red),
        "aliq_icms_interna_dest": float(aliq_int),
        "aliq_fcp_dest": float(aliq_fcp),
        "vig_ini": vig_ini,
        "vig_fim": vig_fim,
        "prioridade": int(prioridade),
        "ativo": int(ativo),
    }
    regras.append(regra)
    data["seq"] = seq
    data["regras"] = regras
    save_tabela_st_data(data)

    print(f"Regra criada. ID={regra['id']} ({uf_origem}->{uf_destino} NCM={ncm} CFOP={cfop})")

def _rule_signature(r: Dict[str, Any]) -> Tuple:
    """
    Assinatura usada para evitar duplicatas “idênticas”.
    """
    return (
        str(r.get("uf_origem","")).upper(),
        str(r.get("uf_destino","")).upper(),
        str(r.get("ncm","")),
        str(r.get("cest","")),
        str(r.get("cfop","")),
        str(r.get("vig_ini","")),
        str(r.get("vig_fim","")),
        float(r.get("mva",0.0)),
        float(r.get("red_bc_st",0.0)),
        r.get("aliq_icms_interna_dest", None),
        r.get("aliq_fcp_dest", None),
        int(r.get("prioridade",0)),
        int(r.get("ativo",1)),
    )

def duplicar_regra_st_em_lote() -> None:
    title("Duplicar regra ST em lote (UF origem/destino)")
    data = load_tabela_st_data()
    regras = data.get("regras", [])
    if not regras:
        print("Não há regras ST. Crie uma regra base primeiro.")
        return

    listar_regras_st(limit=50)
    base_id = ask_int("Informe o ID da regra base: ", required=True, min_v=1) or 0
    base = None
    for r in regras:
        if int(r.get("id",0)) == int(base_id):
            base = r
            break
    if not base:
        print("Regra base não encontrada.")
        return

    print("\nModos:")
    print(" 1) Manter ORIGEM da base e escolher múltiplos DESTINOS")
    print(" 2) Manter DESTINO da base e escolher múltiplas ORIGENS")
    print(" 3) Cartesiano: ORIGENS x DESTINOS")
    print(" 4) Todas as UFs (27x26) usando a regra base (atenção: gera muitas regras)")
    modo = ask_int("Modo [3]: ", required=False, min_v=1) or 3

    if modo == 1:
        origens = [str(base.get("uf_origem","")).upper()]
        destinos = parse_uf_list(ask_str("Destinos (ex.: MG,RJ,ES ou TODAS): "))
    elif modo == 2:
        origens = parse_uf_list(ask_str("Origens (ex.: SP,PR,SC ou TODAS): "))
        destinos = [str(base.get("uf_destino","")).upper()]
    elif modo == 4:
        origens = list(UFS_BRASIL)
        destinos = list(UFS_BRASIL)
    else:
        origens = parse_uf_list(ask_str("Origens (ex.: SP,PR,SC ou TODAS): "))
        destinos = parse_uf_list(ask_str("Destinos (ex.: MG,RJ,ES ou TODAS): "))

    if not origens or not destinos:
        print("Lista de UF vazia.")
        return

    excluir_iguais = (ask_str("Excluir pares origem=destino? (S/N) [S]: ", required=False) or "S").upper() == "S"

    # opcional: sobrescrever vigência
    sobrescrever_vig = (ask_str("Definir nova vigência para as cópias? (S/N) [N]: ", required=False) or "N").upper() == "S"
    if sobrescrever_vig:
        vig_ini = ask_date_yyyy_mm_dd("Vigência início (YYYY-MM-DD) [hoje]: ", required=False, default_today=True)
        vig_fim = ask_date_yyyy_mm_dd("Vigência fim (YYYY-MM-DD) [vazio=sem fim]: ", required=False, default_today=False)
    else:
        vig_ini = str(base.get("vig_ini","")) or date.today().strftime("%Y-%m-%d")
        vig_fim = str(base.get("vig_fim","") or "")

    # evita duplicatas por assinatura
    existing = set(_rule_signature(r) for r in regras)
    seq = int(data.get("seq", 0) or 0)
    created = 0
    skipped = 0

    for uf_or in origens:
        for uf_de in destinos:
            if excluir_iguais and uf_or == uf_de:
                continue

            newr = dict(base)
            # id novo
            newr["id"] = None
            newr["uf_origem"] = uf_or
            newr["uf_destino"] = uf_de
            newr["vig_ini"] = vig_ini
            newr["vig_fim"] = vig_fim

            sig = _rule_signature(newr)
            if sig in existing:
                skipped += 1
                continue

            seq += 1
            newr["id"] = seq
            regras.append(newr)
            existing.add(sig)
            created += 1

    data["seq"] = seq
    data["regras"] = regras
    save_tabela_st_data(data)

    print(f"\nDuplicação concluída. Criadas: {created} | Ignoradas (já existiam): {skipped} | Total: {len(regras)}")

def remover_regra_st() -> None:
    title("Remover regra ST")
    data = load_tabela_st_data()
    regras = data.get("regras", [])
    if not regras:
        print("Nenhuma regra cadastrada.")
        return
    listar_regras_st(limit=50)
    rid = ask_int("ID da regra para remover: ", required=True, min_v=1) or 0
    before = len(regras)
    regras = [r for r in regras if int(r.get("id",0)) != int(rid)]
    after = len(regras)
    data["regras"] = regras
    save_tabela_st_data(data)
    print(f"Removidas: {before - after}")

# =========================================================
# CÁLCULOS (simplificados)
# =========================================================
def calc_item_totais(qtd: float, v_unit: float, desconto: float, frete: float, seguro: float, outras: float) -> Tuple[float, float]:
    v_bruto = round(qtd * v_unit, 2)
    v_total = round(v_bruto - desconto + frete + seguro + outras, 2)
    return v_bruto, v_total

def calc_st(
    v_operacao: float,
    p_icms_interna_dest: float,
    p_fcp_dest: float,
    p_mva: float,
    p_red_bc_st: float,
    p_icms_inter: float
) -> Dict[str, float]:
    mva_factor = 1.0 + (p_mva / 100.0)
    red_factor = 1.0 - (p_red_bc_st / 100.0)

    v_bc_st = round(v_operacao * mva_factor * red_factor, 2)
    v_icms_proprio = round(v_operacao * (p_icms_inter / 100.0), 2)
    v_icms_st_calc = round((v_bc_st * (p_icms_interna_dest / 100.0)) - v_icms_proprio, 2)
    v_icms_st = max(v_icms_st_calc, 0.0)
    v_fcp_st = round(v_bc_st * (p_fcp_dest / 100.0), 2)

    return {"v_bc_st": v_bc_st, "v_icms_proprio": v_icms_proprio, "v_icms_st": v_icms_st, "v_fcp_st": v_fcp_st}

def calc_difal_fcp(
    v_operacao: float,
    p_icms_interna_dest: float,
    p_fcp_dest: float,
    p_icms_inter: float,
    partilha_ufdest_pct: float = 100.0
) -> Dict[str, float]:
    difal_total = round(v_operacao * ((p_icms_interna_dest - p_icms_inter) / 100.0), 2)
    difal_total = max(difal_total, 0.0)
    v_fcp_ufdest = round(v_operacao * (p_fcp_dest / 100.0), 2)
    uf_dest = round(difal_total * (partilha_ufdest_pct / 100.0), 2)
    uf_rem = round(difal_total - uf_dest, 2)
    return {"v_difal_total": difal_total, "v_icms_ufdest": uf_dest, "v_icms_ufremet": uf_rem, "v_fcp_ufdest": v_fcp_ufdest}

def calcular_impostos_item(
    uf_origem: str,
    uf_destino: str,
    ind_final: int,
    ind_ie_dest: int,
    flag_importado: int,
    data_emissao: str,
    cfop: str,
    ncm: str,
    cest: str,
    v_operacao: float,
    tabela_uf: Dict[str, Any],
    tabela_st_regras: List[Dict[str, Any]],
    aplicar_st: int = 1
) -> Dict[str, Any]:
    uf_origem = uf_origem.upper()
    uf_destino = uf_destino.upper()

    p_inter = aliq_interestadual(uf_origem, uf_destino, int(flag_importado))

    uf_row = tabela_uf.get(uf_destino, {})
    p_interna = float(uf_row.get("aliq_icms_interna", 0.0))
    p_fcp = float(uf_row.get("aliq_fcp", 0.0))

    out: Dict[str, Any] = {
        "p_interestadual": p_inter,
        "p_interna_dest": p_interna,
        "p_fcp_dest": p_fcp,
        "difal": None,
        "st": None,
        "regra_st_aplicada": None,
    }

    if ind_final == 1 and ind_ie_dest == 9 and uf_origem != uf_destino:
        out["difal"] = calc_difal_fcp(v_operacao, p_interna, p_fcp, p_inter, 100.0)

    if aplicar_st == 1:
        regra = escolher_regra_st(tabela_st_regras, uf_origem, uf_destino, ncm, cest, cfop, data_emissao)
        if regra:
            p_mva = float(regra.get("mva", 0.0))
            p_red = float(regra.get("red_bc_st", 0.0))
            p_interna_eff = float(regra.get("aliq_icms_interna_dest", p_interna) or p_interna)
            p_fcp_eff = float(regra.get("aliq_fcp_dest", p_fcp) or p_fcp)

            out["st"] = calc_st(v_operacao, p_interna_eff, p_fcp_eff, p_mva, p_red, p_inter)
            out["regra_st_aplicada"] = {
                "id": regra.get("id"),
                "uf_origem": regra.get("uf_origem"), "uf_destino": regra.get("uf_destino"),
                "ncm": regra.get("ncm",""), "cest": regra.get("cest",""), "cfop": regra.get("cfop",""),
                "mva": p_mva, "red_bc_st": p_red,
                "vig_ini": regra.get("vig_ini"), "vig_fim": regra.get("vig_fim",""),
                "prioridade": regra.get("prioridade",0),
            }

    return out

# =========================================================
# ESTOQUE
# =========================================================
def load_estoque() -> Dict[str, Any]:
    return read_json(FILE_ESTOQUE, {"by_filial": {}})

def save_estoque(data: Dict[str, Any]) -> None:
    write_json(FILE_ESTOQUE, data)

def get_stock(estoque: Dict[str, Any], filial_id: int, produto_id: int) -> float:
    return float(estoque.get("by_filial", {}).get(str(filial_id), {}).get(str(produto_id), 0.0))

def set_stock(estoque: Dict[str, Any], filial_id: int, produto_id: int, qty: float) -> None:
    estoque.setdefault("by_filial", {}).setdefault(str(filial_id), {})[str(produto_id)] = round(float(qty), 4)

def apply_stock_delta(estoque: Dict[str, Any], filial_id: int, produto_id: int, delta: float) -> Tuple[bool, str]:
    current = get_stock(estoque, filial_id, produto_id)
    new = current + float(delta)
    if not ALLOW_NEGATIVE_STOCK and new < -1e-9:
        return False, f"Estoque insuficiente. Atual={current} | Delta={delta} | Resultaria={new}"
    set_stock(estoque, filial_id, produto_id, new)
    return True, ""

# =========================================================
# CADASTROS / IMPORTS
# =========================================================
def listar_filiais(active_only: bool = True) -> List[Dict[str, Any]]:
    store = load_store(FILE_FILIAIS)
    items = store.get("items", [])
    if active_only:
        items = [x for x in items if int(x.get("ativo",1)) == 1]
    if not items:
        print("Nenhuma filial cadastrada.")
        return []
    for x in items:
        print(f"[{x['id']}] {x['nome']} - UF {x['uf']} | ativo={x.get('ativo',1)}")
    return items

def cadastrar_filial() -> None:
    title("Cadastrar Filial")
    store = load_store(FILE_FILIAIS)
    _id = next_id(store)
    nome = ask_str("Nome: ")
    uf = ask_uf("UF: ")
    store["items"].append(asdict(Filial(id=_id, nome=nome, uf=uf, ativo=1)))
    save_store(FILE_FILIAIS, store)
    print("Filial cadastrada.")

def listar_pessoas(active_only: bool = True) -> List[Dict[str, Any]]:
    store = load_store(FILE_PESSOAS)
    items = store.get("items", [])
    if active_only:
        items = [x for x in items if int(x.get("ativo",1)) == 1]
    if not items:
        print("Nenhuma pessoa cadastrada.")
        return []
    for x in items:
        print(f"[{x['id']}] {x['nome']} | tipo={x['tipo']} | UF={x['uf']} | IE={x['ind_ie_dest']} | ativo={x.get('ativo',1)}")
    return items

def cadastrar_pessoa() -> None:
    title("Cadastrar Pessoa")
    store = load_store(FILE_PESSOAS)
    _id = next_id(store)
    nome = ask_str("Nome/Razão social: ")
    tipo = ask_str("Tipo (C=cliente, F=fornecedor, A=ambos): ").upper()
    if tipo not in ("C","F","A"):
        tipo = "C"
    documento = ask_str("Documento (CPF/CNPJ) [opcional]: ", required=False)
    uf = ask_uf("UF: ")
    ind_ie_dest = ask_int("Indicador IE (1=Contribuinte,2=Isento,9=Não contribuinte): ", required=True, min_v=1) or 9
    if ind_ie_dest not in (1,2,9):
        ind_ie_dest = 9
    store["items"].append(asdict(Pessoa(id=_id, nome=nome, tipo=tipo, documento=documento, uf=uf, ind_ie_dest=ind_ie_dest, ativo=1)))
    save_store(FILE_PESSOAS, store)
    print("Pessoa cadastrada.")

def listar_produtos(active_only: bool = True) -> List[Dict[str, Any]]:
    store = load_store(FILE_PRODUTOS)
    items = store.get("items", [])
    if active_only:
        items = [x for x in items if int(x.get("ativo",1)) == 1]
    if not items:
        print("Nenhum produto cadastrado.")
        return []
    for x in items:
        print(f"[{x['id']}] {x['sku']} | {x['descricao']} | NCM={x.get('ncm','')} | CEST={x.get('cest','')} | preço={x['preco_venda']} | importado={x.get('flag_importado',0)}")
    return items

def cadastrar_produto() -> None:
    title("Cadastrar Produto")
    store = load_store(FILE_PRODUTOS)
    _id = next_id(store)
    sku = ask_str("SKU: ").upper()
    descricao = ask_str("Descrição: ")
    ncm = normalize_digits(ask_str("NCM (8 dígitos) [opcional]: ", required=False), 8)
    cest = normalize_digits(ask_str("CEST (7 dígitos) [opcional]: ", required=False), 7)
    preco = ask_float("Preço venda: ", required=True, min_v=0.0) or 0.0
    flag_importado = ask_int("Produto importado (RSF 13/2012)? 1=Sim 0=Não: ", required=True, min_v=0) or 0
    flag_importado = 1 if flag_importado == 1 else 0
    store["items"].append(asdict(Produto(id=_id, sku=sku, descricao=descricao, ncm=ncm, cest=cest, preco_venda=float(preco), flag_importado=flag_importado, ativo=1)))
    save_store(FILE_PRODUTOS, store)
    print("Produto cadastrado.")

def import_produtos_csv(path: str) -> None:
    title("Importar Produtos (CSV)")
    if not os.path.exists(path):
        print("Arquivo não encontrado.")
        return

    store = load_store(FILE_PRODUTOS)
    existing = {str(x.get("sku","")).strip().upper(): x for x in store.get("items", [])}

    inserted = 0
    updated = 0

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {"sku","descricao","ncm","cest","preco_venda","flag_importado"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            print(f"CSV inválido. Cabeçalho esperado: {sorted(required)}")
            return

        for row in reader:
            sku = (row.get("sku") or "").strip().upper()
            if not sku:
                continue
            desc = (row.get("descricao") or "").strip()
            ncm = normalize_digits(str(row.get("ncm") or ""), 8)
            cest = normalize_digits(str(row.get("cest") or ""), 7)
            preco = float(str(row.get("preco_venda") or "0").replace(",", "."))
            flag = int(str(row.get("flag_importado") or "0").strip() or "0")
            flag = 1 if flag == 1 else 0

            if sku in existing:
                p = existing[sku]
                p["descricao"] = desc
                p["ncm"] = ncm
                p["cest"] = cest
                p["preco_venda"] = preco
                p["flag_importado"] = flag
                updated += 1
            else:
                pid = next_id(store)
                store["items"].append(asdict(Produto(id=pid, sku=sku, descricao=desc, ncm=ncm, cest=cest, preco_venda=preco, flag_importado=flag, ativo=1)))
                inserted += 1

    save_store(FILE_PRODUTOS, store)
    print(f"Importação concluída. Inseridos: {inserted} | Atualizados: {updated}")

# =========================================================
# ASSISTENTE: busca por SKU/descrição e CFOP sugerido
# =========================================================
def search_produtos(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return []
    store = load_store(FILE_PRODUTOS)
    items = [x for x in store.get("items", []) if int(x.get("ativo",1)) == 1]
    hits = []
    for x in items:
        hay = f"{x.get('sku','')} {x.get('descricao','')}".lower()
        if q in hay:
            hits.append(x)
    hits.sort(key=lambda x: (x.get("sku",""), x.get("descricao","")))
    return hits[:limit]

def cfop_sugerido(tipo_operacao: str, uf_origem: str, uf_destino: str) -> str:
    mesma_uf = uf_origem.upper() == uf_destino.upper()
    if tipo_operacao == "ENTRADA":
        return "1102" if mesma_uf else "2102"
    return "5102" if mesma_uf else "6102"

# =========================================================
# NF: criar, itens, calcular, emitir, cancelar
# =========================================================
def criar_nf(tipo_operacao: str) -> int:
    title(f"Criar NF ({tipo_operacao})")

    print("Filiais:")
    filiais = listar_filiais()
    if not filiais:
        print("Cadastre uma filial primeiro.")
        return 0
    filial_id = ask_int("Filial ID: ", required=True, min_v=1) or 0

    print("\nPessoas:")
    pessoas = listar_pessoas()
    if not pessoas:
        print("Cadastre pessoas (emitente/destinatário) primeiro.")
        return 0
    emitente_id = ask_int("Emitente ID: ", required=True, min_v=1) or 0
    destinatario_id = ask_int("Destinatário ID: ", required=True, min_v=1) or 0

    uf_origem = ask_uf("UF Origem: ")
    uf_destino = ask_uf("UF Destino: ")
    ind_final = ask_int("Consumidor final? 1=Sim 0=Não: ", required=True, min_v=0) or 0
    ind_final = 1 if ind_final == 1 else 0

    modelo = ask_str("Modelo (55/65) [55]: ", required=False) or "55"
    serie = ask_int("Série [1]: ", required=False, min_v=1) or 1
    numero = ask_int("Número (controle interno) [0]: ", required=False, min_v=0) or 0
    data_emissao = ask_date_yyyy_mm_dd("Data emissão (YYYY-MM-DD) [hoje]: ", required=False, default_today=True)

    store = load_store(FILE_NFS)
    nf_id = next_id(store)

    nf = NF(
        id=nf_id, tipo_operacao=tipo_operacao, filial_id=int(filial_id),
        emitente_id=int(emitente_id), destinatario_id=int(destinatario_id),
        uf_origem=uf_origem, uf_destino=uf_destino, ind_final=ind_final,
        modelo=modelo, serie=int(serie), numero=int(numero),
        data_emissao=data_emissao, status="RASCUNHO", estoque_postado=0,
        itens=[], totais={}
    )
    store["items"].append(asdict(nf))
    save_store(FILE_NFS, store)
    print(f"NF criada. ID={nf_id}")
    return nf_id

def add_itens_nf_assistente(nf_id: int) -> None:
    title(f"Assistente - Adicionar itens na NF {nf_id}")

    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return
    if nf.get("status") != "RASCUNHO":
        print("Só é possível editar NF em RASCUNHO.")
        return

    store_prod = load_store(FILE_PRODUTOS)
    produtos = [x for x in store_prod.get("items", []) if int(x.get("ativo",1)) == 1]
    if not produtos:
        print("Cadastre/import produtos primeiro.")
        return

    while True:
        print("\nDigite o SKU do produto (ou ENTER para buscar/listar; '0' para sair):")
        sku_in = input("SKU: ").strip().upper()

        prod: Optional[Dict[str, Any]] = None

        if sku_in == "0":
            break

        if sku_in:
            for p in produtos:
                if str(p.get("sku","")).upper() == sku_in:
                    prod = p
                    break
            if not prod:
                print("SKU não encontrado. Use ENTER para buscar por texto.")
                continue
        else:
            q = ask_str("Buscar por texto (SKU/descrição): ", required=True)
            hits = search_produtos(q, limit=10)
            if not hits:
                print("Nenhum encontrado.")
                continue
            for x in hits:
                print(f"[{x['id']}] {x['sku']} | {x['descricao']} | preço={money(float(x.get('preco_venda',0)))}")
            pid = ask_int("Produto ID: ", required=True, min_v=1) or 0
            prod = find_by_id(store_prod, int(pid))
            if not prod:
                print("Produto inválido.")
                continue

        cfop_default = normalize_digits(cfop_sugerido(nf["tipo_operacao"], nf["uf_origem"], nf["uf_destino"]), 4)
        cfop_in = ask_str(f"CFOP [{cfop_default}]: ", required=False) or cfop_default
        cfop_in = normalize_digits(cfop_in, 4)

        qtd = ask_float("Quantidade: ", required=True, min_v=0.0001) or 0.0
        v_unit_default = float(prod.get("preco_venda", 0.0))
        v_unit = ask_float(f"Valor unitário [{v_unit_default}]: ", required=False, min_v=0.0) or v_unit_default

        desconto = ask_float("Desconto (R$) [0]: ", required=False, min_v=0.0) or 0.0
        frete = ask_float("Frete (R$) [0]: ", required=False, min_v=0.0) or 0.0
        seguro = ask_float("Seguro (R$) [0]: ", required=False, min_v=0.0) or 0.0
        outras = ask_float("Outras despesas (R$) [0]: ", required=False, min_v=0.0) or 0.0

        v_bruto, v_total = calc_item_totais(float(qtd), float(v_unit), float(desconto), float(frete), float(seguro), float(outras))

        item_id = len(nf.get("itens", [])) + 1
        item = asdict(NFItem(
            id=item_id,
            produto_id=int(prod["id"]),
            sku=str(prod.get("sku","")),
            descricao=str(prod.get("descricao","")),
            ncm=str(prod.get("ncm","")),
            cest=str(prod.get("cest","")),
            cfop=cfop_in,
            qtd=float(qtd),
            v_unit=float(v_unit),
            desconto=float(desconto),
            frete=float(frete),
            seguro=float(seguro),
            outras=float(outras),
            v_bruto=float(v_bruto),
            v_total=float(v_total),
            impostos=None
        ))
        nf["itens"].append(item)
        save_store(FILE_NFS, store_nf)
        print(f"Item inserido. Total item: {money(v_total)}")

        cont = (ask_str("Adicionar outro item? (S/N) [S]: ", required=False) or "S").strip().upper()
        if cont != "S":
            break

def remove_item_nf(nf_id: int) -> None:
    title(f"Remover item da NF {nf_id}")
    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return
    if nf.get("status") != "RASCUNHO":
        print("Só é possível editar NF em RASCUNHO.")
        return

    itens = nf.get("itens", [])
    if not itens:
        print("NF sem itens.")
        return

    for it in itens:
        print(f"[{it['id']}] {it['sku']} | {it['descricao']} | qtd={it['qtd']} | total={money(float(it['v_total']))}")
    iid = ask_int("Item ID para remover: ", required=True, min_v=1) or 0

    nf["itens"] = [x for x in itens if int(x.get("id",0)) != int(iid)]
    for idx, it in enumerate(nf["itens"], start=1):
        it["id"] = idx

    save_store(FILE_NFS, store_nf)
    print("Item removido.")

def calcular_nf(nf_id: int) -> None:
    title(f"Calcular NF {nf_id} (ST/DIFAL/FCP + Totais)")
    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return

    tabela_uf = load_tabela_uf()
    if not tabela_uf:
        bootstrap_ufs_generic()
        tabela_uf = load_tabela_uf()

    tabela_st = load_tabela_st()

    store_pes = load_store(FILE_PESSOAS)
    dest = find_by_id(store_pes, int(nf["destinatario_id"]))
    ind_ie_dest = int(dest.get("ind_ie_dest", 9)) if dest else 9

    store_prod = load_store(FILE_PRODUTOS)

    itens = nf.get("itens", [])
    if not itens:
        print("NF sem itens.")
        return

    tot_v_prod = tot_desc = tot_frete = tot_seg = tot_out = tot_nf = 0.0
    tot_icms_st = tot_fcp_st = 0.0
    tot_icms_ufdest = tot_icms_ufremet = tot_fcp_ufdest = 0.0

    for it in itens:
        prod = find_by_id(store_prod, int(it["produto_id"])) or {}
        flag_importado = int(prod.get("flag_importado", 0))

        v_bruto, v_total = calc_item_totais(
            float(it.get("qtd", 0.0)),
            float(it.get("v_unit", 0.0)),
            float(it.get("desconto", 0.0)),
            float(it.get("frete", 0.0)),
            float(it.get("seguro", 0.0)),
            float(it.get("outras", 0.0)),
        )
        it["v_bruto"] = v_bruto
        it["v_total"] = v_total

        impostos = calcular_impostos_item(
            uf_origem=str(nf["uf_origem"]),
            uf_destino=str(nf["uf_destino"]),
            ind_final=int(nf.get("ind_final", 0)),
            ind_ie_dest=ind_ie_dest,
            flag_importado=flag_importado,
            data_emissao=str(nf["data_emissao"]),
            cfop=str(it.get("cfop","")),
            ncm=str(it.get("ncm","")),
            cest=str(it.get("cest","")),
            v_operacao=float(it.get("v_total", 0.0)),
            tabela_uf=tabela_uf,
            tabela_st_regras=tabela_st,
            aplicar_st=1
        )
        it["impostos"] = impostos

        tot_v_prod += float(it.get("v_bruto", 0.0))
        tot_desc += float(it.get("desconto", 0.0))
        tot_frete += float(it.get("frete", 0.0))
        tot_seg += float(it.get("seguro", 0.0))
        tot_out += float(it.get("outras", 0.0))
        tot_nf += float(it.get("v_total", 0.0))

        if impostos.get("st"):
            tot_icms_st += float(impostos["st"].get("v_icms_st", 0.0))
            tot_fcp_st += float(impostos["st"].get("v_fcp_st", 0.0))
        if impostos.get("difal"):
            tot_icms_ufdest += float(impostos["difal"].get("v_icms_ufdest", 0.0))
            tot_icms_ufremet += float(impostos["difal"].get("v_icms_ufremet", 0.0))
            tot_fcp_ufdest += float(impostos["difal"].get("v_fcp_ufdest", 0.0))

    nf["totais"] = {
        "v_prod": round(tot_v_prod, 2),
        "v_desc": round(tot_desc, 2),
        "v_frete": round(tot_frete, 2),
        "v_seg": round(tot_seg, 2),
        "v_outro": round(tot_out, 2),
        "v_nf": round(tot_nf, 2),
        "total_icms_st": round(tot_icms_st, 2),
        "total_fcp_st": round(tot_fcp_st, 2),
        "total_icms_ufdest": round(tot_icms_ufdest, 2),
        "total_icms_ufremet": round(tot_icms_ufremet, 2),
        "total_fcp_ufdest": round(tot_fcp_ufdest, 2),
    }
    save_store(FILE_NFS, store_nf)
    print("Cálculo concluído.")

def emitir_nf(nf_id: int) -> None:
    title(f"Emitir NF {nf_id} (postar estoque)")
    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return
    if nf.get("status") != "RASCUNHO":
        print("Só é possível emitir NF em RASCUNHO.")
        return
    itens = nf.get("itens", [])
    if not itens:
        print("NF sem itens.")
        return
    if not nf.get("totais"):
        print("Aviso: NF não calculada. Recomendado rodar 'Calcular NF' antes.")

    estoque = load_estoque()
    filial_id = int(nf["filial_id"])
    sign = 1.0 if nf["tipo_operacao"] == "ENTRADA" else -1.0

    if sign < 0 and not ALLOW_NEGATIVE_STOCK:
        for it in itens:
            pid = int(it["produto_id"])
            qtd = float(it.get("qtd", 0.0))
            current = get_stock(estoque, filial_id, pid)
            if current - qtd < -1e-9:
                print(f"Bloqueado: estoque insuficiente | produto_id={pid} | atual={current} | saída={qtd}")
                return

    for it in itens:
        pid = int(it["produto_id"])
        qtd = float(it.get("qtd", 0.0))
        ok, msg = apply_stock_delta(estoque, filial_id, pid, sign * qtd)
        if not ok:
            print(f"Falha ao postar estoque: {msg}")
            return

    nf["status"] = "EMITIDA"
    nf["estoque_postado"] = 1
    save_estoque(estoque)
    save_store(FILE_NFS, store_nf)
    print("NF emitida e estoque atualizado.")

def cancelar_nf(nf_id: int) -> None:
    title(f"Cancelar NF {nf_id} (reverter estoque se postado)")
    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return
    if nf.get("status") == "CANCELADA":
        print("NF já está cancelada.")
        return

    estoque_postado = int(nf.get("estoque_postado", 0))
    itens = nf.get("itens", [])

    if estoque_postado == 1:
        estoque = load_estoque()
        filial_id = int(nf["filial_id"])
        sign = -1.0 if nf["tipo_operacao"] == "ENTRADA" else 1.0

        if sign < 0 and not ALLOW_NEGATIVE_STOCK:
            for it in itens:
                pid = int(it["produto_id"])
                qtd = float(it.get("qtd", 0.0))
                current = get_stock(estoque, filial_id, pid)
                if current - qtd < -1e-9:
                    print(f"Bloqueado: reverter ENTRADA geraria negativo | produto_id={pid} | atual={current} | reverter={qtd}")
                    return

        for it in itens:
            pid = int(it["produto_id"])
            qtd = float(it.get("qtd", 0.0))
            ok, msg = apply_stock_delta(estoque, filial_id, pid, sign * qtd)
            if not ok:
                print(f"Falha ao reverter estoque: {msg}")
                return

        save_estoque(estoque)
        nf["estoque_postado"] = 0

    nf["status"] = "CANCELADA"
    save_store(FILE_NFS, store_nf)
    print("NF cancelada.")

def listar_nfs(limit: int = 50) -> List[Dict[str, Any]]:
    store_nf = load_store(FILE_NFS)
    items = store_nf.get("items", [])
    if not items:
        print("Nenhuma NF lançada.")
        return []
    items_sorted = sorted(items, key=lambda x: int(x.get("id",0)), reverse=True)[:limit]
    for nf in items_sorted:
        print(f"[{nf['id']}] {nf['tipo_operacao']} {nf['modelo']}-{nf['serie']}/{nf['numero']} | {nf['data_emissao']} | {nf['status']} | {nf['uf_origem']}->{nf['uf_destino']} | itens={len(nf.get('itens',[]))}")
    return items_sorted

def visualizar_nf(nf_id: int) -> None:
    title(f"Visualizar NF {nf_id}")
    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return

    print(f"NF {nf['id']} | {nf['tipo_operacao']} | {nf['modelo']}-{nf['serie']}/{nf['numero']} | {nf['data_emissao']} | {nf['status']}")
    print(f"Filial ID: {nf['filial_id']} | Emitente ID: {nf['emitente_id']} | Destinatário ID: {nf['destinatario_id']}")
    print(f"UF Origem: {nf['uf_origem']} -> UF Destino: {nf['uf_destino']} | Consumidor final: {nf.get('ind_final',0)}")
    print(f"Estoque postado: {nf.get('estoque_postado',0)}")

    itens = nf.get("itens", [])
    print("\nItens:")
    if not itens:
        print("(sem itens)")
    for it in itens:
        print(f"- Item {it['id']}: {it['sku']} | {it['descricao']} | NCM={it.get('ncm','')} CEST={it.get('cest','')} CFOP={it.get('cfop','')}")
        print(f"  qtd={it['qtd']} unit={money(float(it['v_unit']))} total={money(float(it['v_total']))}")
        imp = it.get("impostos")
        if imp:
            print(f"  p_inter={imp.get('p_interestadual')} | p_interna_dest={imp.get('p_interna_dest')} | p_fcp_dest={imp.get('p_fcp_dest')}")
            if imp.get("st"):
                st = imp["st"]
                base = imp.get("regra_st_aplicada") or {}
                print(f"  ST (regra {base.get('id')}): BCST={money(float(st['v_bc_st']))} vST={money(float(st['v_icms_st']))} FCPST={money(float(st['v_fcp_st']))}")
            if imp.get("difal"):
                df = imp["difal"]
                print(f"  DIFAL: UFDest={money(float(df['v_icms_ufdest']))} UFRemet={money(float(df['v_icms_ufremet']))} FCPDest={money(float(df['v_fcp_ufdest']))}")

    print("\nTotais:")
    t = nf.get("totais") or {}
    if not t:
        print("(não calculado — use 'Calcular NF')")
    else:
        for k, v in t.items():
            if k.startswith("v_") or k.startswith("total_"):
                print(f"  {k}: {money(float(v))}")
            else:
                print(f"  {k}: {v}")

def visualizar_estoque() -> None:
    title("Estoque (por filial)")
    estoque = load_estoque()
    by_filial = estoque.get("by_filial", {})
    if not by_filial:
        print("Sem movimentações.")
        return

    store_fil = load_store(FILE_FILIAIS)
    store_prod = load_store(FILE_PRODUTOS)
    fil_map = {int(x["id"]): x for x in store_fil.get("items", [])}
    prod_map = {int(x["id"]): x for x in store_prod.get("items", [])}

    for fkey, mp in by_filial.items():
        fid = int(fkey)
        fname = fil_map.get(fid, {}).get("nome", f"Filial {fid}")
        print(f"\nFilial [{fid}] {fname}")
        rows = []
        for pkey, qty in mp.items():
            pid = int(pkey)
            prod = prod_map.get(pid, {})
            sku = prod.get("sku", f"PID{pid}")
            desc = prod.get("descricao", "")
            rows.append((sku, desc, float(qty)))
        rows.sort(key=lambda x: x[0])
        for sku, desc, qty in rows:
            print(f"  {sku} | {desc} => {qty}")

def toggle_ativo(path: Path, entity_name: str) -> None:
    title(f"Ativar/Inativar {entity_name}")
    store = load_store(path)
    items = store.get("items", [])
    if not items:
        print("Nada cadastrado.")
        return
    for x in items:
        print(f"[{x['id']}] {x.get('nome', x.get('descricao', x.get('sku','')))} | ativo={x.get('ativo',1)}")
    _id = ask_int("ID: ", required=True, min_v=1) or 0
    it = find_by_id(store, int(_id))
    if not it:
        print("ID não encontrado.")
        return
    it["ativo"] = 0 if int(it.get("ativo",1)) == 1 else 1
    save_store(path, store)
    print("Atualizado.")

# =========================================================
# EXPORT HTML/PDF (mantido do seu modelo anterior)
# =========================================================
def export_nf_html(nf_id: int, out_path: str) -> None:
    title(f"Exportar NF {nf_id} para HTML")
    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return

    itens = nf.get("itens", [])
    totais = nf.get("totais") or {}

    html = []
    html.append("<html><head><meta charset='utf-8'>")
    html.append("<style>body{font-family:Arial; margin:20px;} table{border-collapse:collapse;width:100%;} th,td{border:1px solid #ccc;padding:6px;font-size:12px;} th{background:#f2f2f2;} .row{display:flex; gap:20px;} .box{border:1px solid #ccc; padding:10px; flex:1;} h2{margin:0 0 10px 0;}</style>")
    html.append("</head><body>")
    html.append(f"<h1>{APP_NAME}</h1>")
    html.append(f"<h2>NF {nf['id']} - {nf['tipo_operacao']} - {nf['status']}</h2>")
    html.append(f"<div class='row'>"
                f"<div class='box'><b>Chave interna</b>: {nf['id']}<br><b>Modelo/Série/Número</b>: {nf['modelo']}-{nf['serie']}/{nf['numero']}<br><b>Data</b>: {nf['data_emissao']}<br><b>UF Origem</b>: {nf['uf_origem']}<br><b>UF Destino</b>: {nf['uf_destino']}</div>"
                f"<div class='box'><b>Filial</b>: {nf['filial_id']}<br><b>Emitente</b>: {nf['emitente_id']}<br><b>Destinatário</b>: {nf['destinatario_id']}<br><b>Consumidor final</b>: {nf.get('ind_final',0)}<br><b>Estoque postado</b>: {nf.get('estoque_postado',0)}</div>"
                f"</div>")

    html.append("<h3>Itens</h3>")
    html.append("<table><tr><th>#</th><th>SKU</th><th>Descrição</th><th>NCM</th><th>CEST</th><th>CFOP</th><th>Qtd</th><th>V.Unit</th><th>Total</th><th>ST</th><th>DIFAL/FCP</th></tr>")
    for it in itens:
        imp = it.get("impostos") or {}
        st = imp.get("st") or {}
        df = imp.get("difal") or {}
        st_txt = ""
        if st:
            st_txt = f"BCST {money(float(st.get('v_bc_st',0)))}<br>vST {money(float(st.get('v_icms_st',0)))}<br>FCPST {money(float(st.get('v_fcp_st',0)))}"
        df_txt = ""
        if df:
            df_txt = f"UFDest {money(float(df.get('v_icms_ufdest',0)))}<br>UFRem {money(float(df.get('v_icms_ufremet',0)))}<br>FCP {money(float(df.get('v_fcp_ufdest',0)))}"

        html.append(
            "<tr>"
            f"<td>{it['id']}</td><td>{it.get('sku','')}</td><td>{it.get('descricao','')}</td>"
            f"<td>{it.get('ncm','')}</td><td>{it.get('cest','')}</td><td>{it.get('cfop','')}</td>"
            f"<td>{it.get('qtd',0)}</td><td>{money(float(it.get('v_unit',0)))}</td><td>{money(float(it.get('v_total',0)))}</td>"
            f"<td>{st_txt}</td><td>{df_txt}</td>"
            "</tr>"
        )
    html.append("</table>")

    html.append("<h3>Totais</h3>")
    html.append("<table>")
    for k in ["v_prod","v_desc","v_frete","v_seg","v_outro","v_nf","total_icms_st","total_fcp_st","total_icms_ufdest","total_icms_ufremet","total_fcp_ufdest"]:
        v = totais.get(k, 0.0)
        html.append(f"<tr><th>{k}</th><td>{money(float(v))}</td></tr>")
    html.append("</table>")

    html.append("<p><i>Observação: Documento gerado para controle interno/demonstração.</i></p>")
    html.append("</body></html>")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    print(f"HTML gerado: {out_path}")
    print("Dica: abra no navegador e use Imprimir > Salvar como PDF.")

def export_nf_pdf_reportlab(nf_id: int, out_path: str) -> None:
    title(f"Exportar NF {nf_id} para PDF (reportlab)")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
    except Exception:
        print("reportlab não está instalado.")
        print("Instale com: pip install reportlab")
        return

    store_nf = load_store(FILE_NFS)
    nf = find_by_id(store_nf, nf_id)
    if not nf:
        print("NF não encontrada.")
        return

    itens = nf.get("itens", [])
    totais = nf.get("totais") or {}

    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    y = height - 20*mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, y, "Resumo de NF (Controle Interno)")
    y -= 8*mm
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, y, f"NF {nf['id']} | {nf['tipo_operacao']} | {nf['status']} | Data {nf['data_emissao']}")
    y -= 6*mm
    c.drawString(20*mm, y, f"Modelo/Série/Número: {nf['modelo']}-{nf['serie']}/{nf['numero']} | UF {nf['uf_origem']} -> {nf['uf_destino']} | Consumidor final: {nf.get('ind_final',0)}")
    y -= 8*mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, y, "Itens")
    y -= 6*mm
    c.setFont("Helvetica", 9)

    def line(txt: str) -> None:
        nonlocal y
        if y < 20*mm:
            c.showPage()
            y = height - 20*mm
            c.setFont("Helvetica", 9)
        c.drawString(20*mm, y, txt)
        y -= 5*mm

    for it in itens:
        imp = it.get("impostos") or {}
        st = imp.get("st") or {}
        df = imp.get("difal") or {}
        base = imp.get("regra_st_aplicada") or {}

        line(f"{it['id']}) {it.get('sku','')} - {it.get('descricao','')} | CFOP {it.get('cfop','')} | Qtd {it.get('qtd',0)} | Unit {money(float(it.get('v_unit',0)))} | Total {money(float(it.get('v_total',0)))}")
        if st:
            line(f"    ST (regra {base.get('id')}): BCST {money(float(st.get('v_bc_st',0)))} | vST {money(float(st.get('v_icms_st',0)))} | FCPST {money(float(st.get('v_fcp_st',0)))}")
        if df:
            line(f"    DIFAL/FCP: UFDest {money(float(df.get('v_icms_ufdest',0)))} | UFRem {money(float(df.get('v_icms_ufremet',0)))} | FCP {money(float(df.get('v_fcp_ufdest',0)))}")

    y -= 4*mm
    c.setFont("Helvetica-Bold", 11)
    line("Totais")
    c.setFont("Helvetica", 9)
    for k in ["v_prod","v_desc","v_frete","v_seg","v_outro","v_nf","total_icms_st","total_fcp_st","total_icms_ufdest","total_icms_ufremet","total_fcp_ufdest"]:
        v = totais.get(k, 0.0)
        line(f"  {k}: {money(float(v))}")

    c.save()
    print(f"PDF gerado: {out_path}")

# =========================================================
# MENU
# =========================================================
def is_valid_uf(uf: str) -> bool:
    return (uf or "").strip().upper() in UFS_BRASIL


def auditar_e_corrigir_ufs(apenas_ativos: bool = True) -> None:
    """
    Varre cadastros (filiais e pessoas) e corrige UF vazia/inválida.
    - Se apenas_ativos=True: corrige somente registros ativos (recomendado).
    - Pergunta UF apenas quando faltar/estiver inválida e salva automaticamente.
    """
    title("Auditar e corrigir UFs (Filiais e Pessoas)")

    # --- Filiais ---
    store_fil = load_store(FILE_FILIAIS)
    filiais = store_fil.get("items", []) or []
    alterou_fil = 0
    checadas_fil = 0

    print("\n[1/2] Verificando FILIAIS...")
    for f in filiais:
        if apenas_ativos and int(f.get("ativo", 1)) != 1:
            continue
        checadas_fil += 1

        uf_atual = str(f.get("uf", "")).strip().upper()
        if not is_valid_uf(uf_atual):
            print("\nUF inválida/vazia em FILIAL:")
            print(f"  Filial: [{f.get('id')}] {f.get('nome')} | UF atual: '{uf_atual}'")
            uf_nova = ask_uf("  Informe a UF correta da filial: ")
            f["uf"] = uf_nova
            alterou_fil += 1

    if alterou_fil > 0:
        save_store(FILE_FILIAIS, store_fil)
        print(f"\nFiliais atualizadas: {alterou_fil}")
    else:
        print("\nFiliais: nenhuma correção necessária.")

    # --- Pessoas ---
    store_pes = load_store(FILE_PESSOAS)
    pessoas = store_pes.get("items", []) or []
    alterou_pes = 0
    checadas_pes = 0

    print("\n[2/2] Verificando PESSOAS (clientes/fornecedores)...")
    for p in pessoas:
        if apenas_ativos and int(p.get("ativo", 1)) != 1:
            continue
        checadas_pes += 1

        uf_atual = str(p.get("uf", "")).strip().upper()
        if not is_valid_uf(uf_atual):
            tipo = str(p.get("tipo", "")).upper()
            tipo_txt = "Cliente" if tipo == "C" else ("Fornecedor" if tipo == "F" else "Ambos")

            print("\nUF inválida/vazia em PESSOA:")
            print(f"  Pessoa: [{p.get('id')}] {p.get('nome')} | tipo={tipo_txt} | UF atual: '{uf_atual}'")
            uf_nova = ask_uf("  Informe a UF correta da pessoa: ")
            p["uf"] = uf_nova
            alterou_pes += 1

    if alterou_pes > 0:
        save_store(FILE_PESSOAS, store_pes)
        print(f"\nPessoas atualizadas: {alterou_pes}")
    else:
        print("\nPessoas: nenhuma correção necessária.")

    print("\nResumo da auditoria:")
    print(f"  Filiais checadas: {checadas_fil} | corrigidas: {alterou_fil}")
    print(f"  Pessoas checadas: {checadas_pes} | corrigidas: {alterou_pes}")
    print("\nConcluído.")
def menu() -> None:
    print("\nSelecione uma opção:")
    print(" 1) Cadastrar Filial")
    print(" 2) Cadastrar Pessoa")
    print(" 3) Cadastrar Produto")
    print(" 4) Importar Produtos (CSV)  [evita digitação]")
    print(" 5) Importar UF Alíquotas (CSV)  [opcional]")
    print(" 6) Importar Regras ST (CSV)     [opcional]")
    print(" 7) Carregar PARÂMETROS PADRÃO (UF + ST base) [100% automático]")
    print(" 8) Assistente: Criar regra ST base (sem CSV)")
    print(" 9) Duplicar regra ST em lote (origem/destino)")
    print("10) Listar regras ST")
    print("11) Remover regra ST")
    print("12) Criar NF Entrada (Compra)")
    print("13) Criar NF Saída (Venda)")
    print("14) Assistente: adicionar itens em NF (SKU/Busca + loop)")
    print("15) Remover item de NF")
    print("16) Calcular NF (ST/DIFAL/FCP + Totais)")
    print("17) Emitir NF (postar estoque)")
    print("18) Cancelar NF (reverter estoque se postado)")
    print("19) Visualizar NF")
    print("20) Listar NFs")
    print("21) Visualizar Estoque")
    print("22) Ativar/Inativar cadastro (Filial/Pessoa/Produto)")
    print("23) Exportar NF para HTML")
    print("24) Exportar NF para PDF (reportlab)")
    print("25) Auditar e corrigir UFs (cadastros) [automático]")
    print(" 0) Sair")

def bootstrap_files() -> None:
    ensure_data_dir()
    for p in [FILE_FILIAIS, FILE_PESSOAS, FILE_PRODUTOS, FILE_NFS]:
        if not p.exists():
            write_json(p, {"seq": 0, "items": []})
    if not FILE_ESTOQUE.exists():
        write_json(FILE_ESTOQUE, {"by_filial": {}})
    if not FILE_TBL_UF.exists():
        write_json(FILE_TBL_UF, {"updated_at":"", "ufs": {}})
    if not FILE_TBL_ST.exists():
        write_json(FILE_TBL_ST, {"updated_at":"", "seq": 0, "regras": []})

    bootstrap_ufs_generic()
    # normaliza ST ids se precisar
    st = load_tabela_st_data()
    save_tabela_st_data(st)

def main() -> None:
    title(APP_NAME)
    bootstrap_files()

    while True:
        menu()
        op = ask_str("Opção: ", required=True).strip()
        try:
            if op == "0":
                break
            elif op == "1":
                cadastrar_filial()
            elif op == "2":
                cadastrar_pessoa()
            elif op == "3":
                cadastrar_produto()
            elif op == "4":
                path = ask_str("Caminho produtos.csv (ex.: C:/temp/produtos.csv): ")
                import_produtos_csv(path)
            elif op == "5":
                path = ask_str("Caminho uf_aliquotas.csv: ")
                import_uf_aliquotas_csv(path)
            elif op == "6":
                path = ask_str("Caminho st_regras.csv: ")
                import_st_regras_csv(path)
            elif op == "7":
                carregar_parametros_padrao_sem_editar()
            elif op == "8":
                criar_regra_st_base_assistente()
            elif op == "9":
                duplicar_regra_st_em_lote()
            elif op == "10":
                listar_regras_st(limit=200)
            elif op == "11":
                remover_regra_st()
            elif op == "12":
                criar_nf("ENTRADA")
            elif op == "13":
                criar_nf("SAIDA")
            elif op == "14":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                add_itens_nf_assistente(int(nf_id))
            elif op == "15":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                remove_item_nf(int(nf_id))
            elif op == "16":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                calcular_nf(int(nf_id))
            elif op == "17":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                emitir_nf(int(nf_id))
            elif op == "18":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                cancelar_nf(int(nf_id))
            elif op == "19":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                visualizar_nf(int(nf_id))
            elif op == "20":
                title("Listar NFs")
                listar_nfs()
            elif op == "21":
                visualizar_estoque()
            elif op == "22":
                which = ask_str("Qual (1) Filial (2) Pessoa (3) Produto: ", required=True).strip()
                if which == "1":
                    toggle_ativo(FILE_FILIAIS, "Filial")
                elif which == "2":
                    toggle_ativo(FILE_PESSOAS, "Pessoa")
                elif which == "3":
                    toggle_ativo(FILE_PRODUTOS, "Produto")
                else:
                    print("Opção inválida.")
            elif op == "23":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                out = ask_str("Salvar em (ex.: C:/temp/nf.html): ")
                export_nf_html(int(nf_id), out)
            elif op == "24":
                nf_id = ask_int("NF ID: ", required=True, min_v=1) or 0
                out = ask_str("Salvar em (ex.: C:/temp/nf.pdf): ")
                export_nf_pdf_reportlab(int(nf_id), out)
            elif op == "25":
                auditar_e_corrigir_ufs(apenas_ativos=True)
            else:
                print("Opção inválida.")
        except KeyboardInterrupt:
            print("\nOperação cancelada.")
        except Exception as e:
            print(f"Erro: {e}")

    print("Encerrado.")

if __name__ == "__main__":
    main()