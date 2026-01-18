# robo_automacao.py
# Automação por dados para o seu "Sistema NFE" (CustomTkinter + JSON)
# Objetivo: importar produtos em massa, validar e gerar relatório

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

import sistema_gui_principal as sysnfe  # importa seu sistema (não abre a UI por causa do __main__)


# -------------------------
# Utilitários
# -------------------------
def ts_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_produtos():
    """Cria backup do produtos.json antes de alterar (boa prática)."""
    sysnfe.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if sysnfe.PRODUTOS_JSON.exists():
        bkp = sysnfe.DATA_DIR / f"produtos_backup_{ts_compact()}.json"
        bkp.write_text(sysnfe.PRODUTOS_JSON.read_text(encoding="utf-8"), encoding="utf-8")
        return bkp
    return None


def category_prefix(cat: str) -> str:
    cat = (cat or "").strip().upper()
    cat = re.sub(r"[^A-Z0-9]", "", cat)
    return cat[:6] if len(cat) >= 3 else cat


def next_id(produtos: list[dict]) -> int:
    mx = 0
    for p in produtos:
        try:
            mx = max(mx, int(p.get("id", 0)))
        except Exception:
            pass
    return mx + 1


def next_seq_for_prefix(produtos: list[dict], prefix: str) -> int:
    mx = 0
    needle = f"{prefix}-"
    for p in produtos:
        sku = str(p.get("sku", "") or "")
        if sku.startswith(needle):
            suf = sku[len(needle):]
            if suf.isdigit():
                mx = max(mx, int(suf))
    return mx + 1


def generate_sku(produtos: list[dict], categoria: str) -> str:
    pref = category_prefix(categoria)
    if not pref:
        return ""
    seq = next_seq_for_prefix(produtos, pref)
    return f"{pref}-{seq:06d}"


def parse_bool(v) -> bool:
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "sim", "s", "yes", "y")


def validate_produto(p: dict) -> tuple[list[str], list[str]]:
    """
    Regras alinhadas ao seu sistema:
    - Categoria/Descrição/Unidade obrigatórias
    - Estoque inteiro >= 0
    - Preços >= 0
    - NCM: 8 dígitos obrigatório
    - EAN: opcional, mas se informado tem que ser GTIN válido
    - CFOP: opcional, se informado ideal 4 dígitos
    """
    errs = []
    warns = []

    if not str(p.get("categoria", "")).strip():
        errs.append("Categoria é obrigatória.")
    if not str(p.get("descricao", "")).strip():
        errs.append("Descrição é obrigatória.")
    if not str(p.get("unidade", "")).strip():
        errs.append("Unidade é obrigatória.")

    try:
        est = int(p.get("estoque_inicial", 0))
        if est < 0:
            errs.append("Estoque inicial inválido (< 0).")
    except Exception:
        errs.append("Estoque inicial inválido (não é inteiro).")

    try:
        pc = float(p.get("preco_custo", 0) or 0)
        if pc < 0:
            errs.append("Preço custo inválido (< 0).")
    except Exception:
        errs.append("Preço custo inválido (não numérico).")

    try:
        pv = float(p.get("preco_venda", 0) or 0)
        if pv < 0:
            errs.append("Preço venda inválido (< 0).")
    except Exception:
        errs.append("Preço venda inválido (não numérico).")

    ncm = sysnfe._only_digits(str(p.get("ncm", "")))
    if len(ncm) != 8:
        errs.append("NCM inválido: deve ter 8 dígitos.")
    else:
        p["ncm"] = ncm

    ean = sysnfe._only_digits(str(p.get("ean", "")))
    if ean:
        if len(ean) not in (8, 12, 13, 14):
            errs.append("EAN inválido: use 8/12/13/14 dígitos.")
        elif not sysnfe.is_valid_gtin(ean):
            errs.append("EAN inválido: dígito verificador não confere.")
        else:
            p["ean"] = ean
    else:
        warns.append("EAN não informado (ok se não aplicável).")

    cfop = sysnfe._only_digits(str(p.get("cfop", "")))
    if cfop and len(cfop) != 4:
        warns.append("CFOP fora do padrão (ideal 4 dígitos).")
    elif cfop:
        p["cfop"] = cfop

    return errs, warns


def sniff_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:2000]
    if ";" in sample and "," not in sample:
        return ";"
    # tenta sniff do csv
    try:
        dialect = csv.Sniffer().sniff(sample)
        return dialect.delimiter
    except Exception:
        return ","


# -------------------------
# Ações do robô
# -------------------------
def cmd_import_csv(csv_path: Path, mode: str):
    """
    mode:
      - upsert  -> cria novo ou atualiza por SKU (se bater)
      - insert  -> só insere; se SKU existir, pula
    """
    if not csv_path.exists():
        raise SystemExit(f"[ERRO] CSV não encontrado: {csv_path}")

    bkp = backup_produtos()
    if bkp:
        print(f"[OK] Backup criado: {bkp}")

    produtos = sysnfe.load_produtos()

    delim = sniff_delimiter(csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim)

        inserted = 0
        updated = 0
        skipped = 0
        invalid = 0

        for row in reader:
            categoria = (row.get("categoria") or "").strip()
            descricao = (row.get("descricao") or "").strip()
            if not categoria or not descricao:
                invalid += 1
                continue

            sku = (row.get("sku") or "").strip()
            if not sku:
                sku = generate_sku(produtos, categoria)

            # tenta achar SKU existente
            idx_exist = None
            for i, p in enumerate(produtos):
                if str(p.get("sku", "")).strip() == sku:
                    idx_exist = i
                    break

            if idx_exist is not None and mode == "insert":
                skipped += 1
                continue

            base = produtos[idx_exist] if idx_exist is not None else {}

            produto = {
                "id": int(base.get("id", 0)) if idx_exist is not None else next_id(produtos),
                "ativo": parse_bool(row.get("ativo", "1")),
                "categoria": categoria,
                "sku": sku,
                "marca": (row.get("marca") or "").strip(),
                "descricao": descricao,
                "unidade": (row.get("unidade") or "UN").strip().upper(),
                "estoque_inicial": int((row.get("estoque_inicial") or "0").strip()),
                "preco_custo": sysnfe.parse_money((row.get("preco_custo") or "0").strip()),
                "preco_venda": sysnfe.parse_money((row.get("preco_venda") or "0").strip()),
                "ncm": (row.get("ncm") or "").strip(),
                "ean": (row.get("ean") or "").strip(),
                "cest": sysnfe._only_digits((row.get("cest") or "").strip()),
                "origem": (row.get("origem") or "0 - Nacional").strip(),
                "cst_csosn": (row.get("cst_csosn") or "").strip(),
                "cfop": (row.get("cfop") or "").strip(),
                "pis": (row.get("pis") or "01").strip(),
                "cofins": (row.get("cofins") or "01").strip(),
                "ipi": (row.get("ipi") or "50").strip(),
                "created_at": base.get("created_at") or datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

            errs, warns = validate_produto(produto)
            if errs:
                invalid += 1
                continue

            if idx_exist is None:
                produtos.append(produto)
                inserted += 1
            else:
                produtos[idx_exist] = produto
                updated += 1

        sysnfe.save_produtos(produtos)
        sysnfe.append_audit(f"ROBÔ: import_csv({csv_path.name}) inserted={inserted} updated={updated} skipped={skipped} invalid={invalid}")

    print("[OK] Importação finalizada.")
    print(f"  Inseridos: {inserted}")
    print(f"  Atualizados: {updated}")
    print(f"  Pulados: {skipped}")
    print(f"  Inválidos: {invalid}")
    print(f"  Total no sistema: {len(sysnfe.load_produtos())}")


def cmd_validate():
    produtos = sysnfe.load_produtos()

    sem_ncm = 0
    ean_invalid = 0
    cfop_inval = 0
    sem_cst = 0
    preco_venda_zero = 0
    inativos = 0

    for p in produtos:
        if not bool(p.get("ativo", True)):
            inativos += 1

        ncm = sysnfe._only_digits(str(p.get("ncm", "")))
        if len(ncm) != 8:
            sem_ncm += 1

        ean = sysnfe._only_digits(str(p.get("ean", "")))
        if ean and not sysnfe.is_valid_gtin(ean):
            ean_invalid += 1

        cfop = sysnfe._only_digits(str(p.get("cfop", "")))
        if cfop and len(cfop) != 4:
            cfop_inval += 1

        if not str(p.get("cst_csosn", "")).strip():
            sem_cst += 1

        try:
            if float(p.get("preco_venda", 0) or 0) <= 0:
                preco_venda_zero += 1
        except Exception:
            preco_venda_zero += 1

    pend = sem_ncm + ean_invalid + cfop_inval + sem_cst + preco_venda_zero

    out = []
    out.append("RELATÓRIO DE VALIDAÇÃO (ROBÔ) - Sistema NFE")
    out.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    out.append("")
    out.append(f"Produtos cadastrados: {len(produtos)}")
    out.append(f"Produtos inativos: {inativos}")
    out.append("")
    out.append("Pendências:")
    out.append(f" - Sem NCM válido (8 dígitos): {sem_ncm}")
    out.append(f" - EAN/GTIN inválido: {ean_invalid}")
    out.append(f" - CFOP fora do padrão: {cfop_inval}")
    out.append(f" - Sem CST/CSOSN: {sem_cst}")
    out.append(f" - Preço venda zerado/ inválido: {preco_venda_zero}")
    out.append("")
    out.append(f"Total pendências (soma): {pend}")

    sysnfe.DATA_DIR.mkdir(parents=True, exist_ok=True)
    report_path = sysnfe.DATA_DIR / f"relatorio_validacao_{ts_compact()}.txt"
    report_path.write_text("\n".join(out), encoding="utf-8")

    sysnfe.append_audit(f"ROBÔ: validate -> pend={pend} total={len(produtos)}")

    print("\n".join(out))
    print(f"\n[OK] Relatório salvo em: {report_path}")


# -------------------------
# CLI
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Robô de automação para o Sistema NFE (JSON).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("import-csv", help="Importa produtos de um CSV (carga em massa).")
    p1.add_argument("csv", type=str, help="Caminho do CSV (ex.: import_produtos.csv)")
    p1.add_argument("--mode", choices=["upsert", "insert"], default="upsert",
                    help="upsert=atualiza por SKU se existir; insert=só insere e pula duplicados")

    sub.add_parser("validate", help="Valida base e gera relatório de pendências.")

    args = ap.parse_args()

    if args.cmd == "import-csv":
        cmd_import_csv(Path(args.csv), mode=args.mode)
    elif args.cmd == "validate":
        cmd_validate()


if __name__ == "__main__":
    main()