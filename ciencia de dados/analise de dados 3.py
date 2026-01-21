import pandas as pd
import numpy as np
from pathlib import Path
import zipfile, random, string, datetime as dt
import shutil

rng = np.random.default_rng(2026)

out_root = Path("/mnt/data")
# ------------------------------
# DATASET 1: RH (Recursos Humanos)
# ------------------------------
rh_dir = out_root / "dataset_rh_ficticio"
if rh_dir.exists():
    shutil.rmtree(rh_dir)
rh_dir.mkdir(parents=True, exist_ok=True)

first_names = ["Ana","Bruno","Carla","Diego","Eduardo","Fernanda","Guilherme","Helena","Igor","Juliana",
               "Kaique","Larissa","Marcos","Natália","Otávio","Patrícia","Rafael","Sabrina","Thiago","Vanessa",
               "Yasmin","Renato","Aline","Caio","Beatriz","João","Lucas","Mariana","Pedro","Camila"]
last_names = ["Silva","Souza","Oliveira","Santos","Lima","Pereira","Carvalho","Ferreira","Almeida","Gomes",
              "Ribeiro","Martins","Barbosa","Cardoso","Teixeira","Costa","Araújo","Rocha","Dias","Melo"]

ufs = ["SP","RJ","MG","PR","SC","RS","BA","PE","CE","GO","DF"]
cities = {
    "SP": ["São Paulo","Campinas","Santos"],
    "RJ": ["Rio de Janeiro","Niterói","Duque de Caxias"],
    "MG": ["Belo Horizonte","Uberlândia","Contagem"],
    "PR": ["Curitiba","Londrina","Maringá"],
    "SC": ["Florianópolis","Joinville","Blumenau"],
    "RS": ["Porto Alegre","Caxias do Sul","Pelotas"],
    "BA": ["Salvador","Feira de Santana","Ilhéus"],
    "PE": ["Recife","Olinda","Caruaru"],
    "CE": ["Fortaleza","Sobral","Juazeiro do Norte"],
    "GO": ["Goiânia","Anápolis","Rio Verde"],
    "DF": ["Brasília","Taguatinga","Ceilândia"],
}

departamentos = ["TI","Dados","Financeiro","Fiscal","Comercial","Operações","RH","Suporte"]
cargos = {
    "TI": ["Dev Jr","Dev Pl","Dev Sr","QA","Infra"],
    "Dados": ["Analista de Dados Jr","Analista de Dados Pl","Cientista de Dados Jr","Eng. de Dados"],
    "Financeiro": ["Analista Financeiro Jr","Analista Financeiro Pl","Contas a Pagar","Contas a Receber"],
    "Fiscal": ["Assistente Fiscal","Analista Fiscal Jr","Analista Fiscal Pl","Especialista Fiscal"],
    "Comercial": ["Vendedor","Executivo de Contas","Inside Sales","Gerente Comercial"],
    "Operações": ["Assistente Operacional","Analista Operacional","Coordenador de Operações"],
    "RH": ["Analista de RH Jr","Analista de RH Pl","BP RH","Recrutador"],
    "Suporte": ["Suporte N1","Suporte N2","Customer Success","Coordenador Suporte"]
}
senioridade = ["Jr","Pl","Sr"]
escolaridade = ["Ensino Médio","Técnico","Graduação","Pós-graduação","Mestrado"]
regime = ["CLT","PJ"]
modelo_trabalho = ["Presencial","Híbrido","Remoto"]

def pick(lst):
    return random.choice(lst)

def random_name():
    return f"{pick(first_names)} {pick(last_names)}"

n_func = 650
func_ids = np.arange(1, n_func+1)

dep = rng.choice(departamentos, size=n_func, p=[0.18,0.10,0.14,0.12,0.16,0.13,0.07,0.10])
cargo = [pick(cargos[d]) for d in dep]

uf = rng.choice(ufs, size=n_func)
cidade = [pick(cities[u]) for u in uf]

# Hire dates last 6 years
hire_start = dt.date(2020, 1, 1)
hire_end = dt.date(2026, 1, 1)
hire_days = (hire_end - hire_start).days
data_admissao = [hire_start + dt.timedelta(days=int(rng.integers(0, hire_days))) for _ in range(n_func)]

# Terminations (turnover)
ativo = rng.choice([1,1,1,1,0], size=n_func)  # ~20% offboard
data_deslig = []
motivo = []
for a, adm in zip(ativo, data_admissao):
    if a == 1:
        data_deslig.append(pd.NaT)
        motivo.append(None)
    else:
        # termination after admission
        end_dt = dt.date(2026, 1, 20)
        span = (end_dt - adm).days
        term = adm + dt.timedelta(days=int(rng.integers(30, max(31, span))))
        data_deslig.append(pd.to_datetime(term))
        motivo.append(pick(["Pedido de demissão","Desempenho","Reestruturação","Fim de contrato","Acordo"]))

sen = rng.choice(senioridade, size=n_func, p=[0.45,0.38,0.17])
esc = rng.choice(escolaridade, size=n_func, p=[0.15,0.15,0.45,0.20,0.05])
reg = rng.choice(regime, size=n_func, p=[0.88,0.12])
work = rng.choice(modelo_trabalho, size=n_func, p=[0.35,0.45,0.20])

# Salaries by department & seniority
base_by_dep = {"TI": 5200, "Dados": 5600, "Financeiro": 4200, "Fiscal": 4300, "Comercial": 3500, "Operações": 3200, "RH": 3800, "Suporte": 3000}
mult_sen = {"Jr": 1.0, "Pl": 1.55, "Sr": 2.35}

salario = []
for d, s, r in zip(dep, sen, reg):
    base = base_by_dep[d] * mult_sen[s]
    # PJ often higher gross
    base *= 1.20 if r == "PJ" else 1.00
    val = float(np.round(rng.normal(base, base*0.12), 2))
    salario.append(max(1800.0, val))

df_func = pd.DataFrame({
    "funcionario_id": func_ids,
    "nome": [random_name() for _ in range(n_func)],
    "departamento": dep,
    "cargo": cargo,
    "senioridade": sen,
    "regime": reg,
    "modelo_trabalho": work,
    "uf": uf,
    "cidade": cidade,
    "escolaridade": esc,
    "data_admissao": pd.to_datetime(data_admissao),
    "ativo": ativo,
    "data_desligamento": pd.to_datetime(data_deslig),
    "motivo_desligamento": motivo,
    "salario_base": salario,
})

# Data quality injections
# Missing city
miss_city = rng.choice(df_func.index, size=18, replace=False)
df_func.loc[miss_city, "cidade"] = None
# Duplicate rows (simulate duplicated employee record)
dup_rows = df_func.sample(3, random_state=7)
df_func = pd.concat([df_func, dup_rows], ignore_index=True)
# Salary outliers
out_idx = rng.choice(df_func.index, size=4, replace=False)
df_func.loc[out_idx, "salario_base"] = df_func.loc[out_idx, "salario_base"] * 6

df_func.to_csv(rh_dir/"funcionarios.csv", index=False, encoding="utf-8")

# Attendance (last 120 days)
dates = pd.date_range("2025-09-22", "2026-01-20", freq="D")
# Only weekdays
dates = dates[dates.weekday < 5]

n_days = len(dates)
att_rows = []
status_values = ["PRESENTE","FALTA","ATRASO","ATESTADO","FÉRIAS"]
status_probs = [0.86, 0.03, 0.05, 0.03, 0.03]

for day in dates:
    # Sample subset of employees active around that time
    sample_ids = rng.choice(df_func["funcionario_id"].unique(), size=520, replace=False)
    st = rng.choice(status_values, size=len(sample_ids), p=status_probs)
    horas = []
    extra = []
    remoto = []
    for s in st:
        if s == "PRESENTE":
            h = float(np.round(rng.normal(8.0, 0.4), 2))
            ex = float(np.round(max(0, rng.normal(0.3, 0.5)), 2))
        elif s == "ATRASO":
            h = float(np.round(rng.normal(7.2, 0.6), 2))
            ex = float(np.round(max(0, rng.normal(0.15, 0.35)), 2))
        elif s in ["FALTA","ATESTADO","FÉRIAS"]:
            h = 0.0
            ex = 0.0
        horas.append(max(0.0, h))
        extra.append(ex)
        remoto.append(int(rng.random() < 0.28))  # worked remote that day
    tmp = pd.DataFrame({
        "data": day,
        "funcionario_id": sample_ids,
        "status": st,
        "horas_trabalhadas": horas,
        "horas_extras": extra,
        "remoto": remoto
    })
    att_rows.append(tmp)

df_att = pd.concat(att_rows, ignore_index=True)

# Inject anomaly: negative hours for a few rows
anom = rng.choice(df_att.index, size=10, replace=False)
df_att.loc[anom, "horas_trabalhadas"] = -1.0

df_att.to_csv(rh_dir/"frequencia.csv", index=False, encoding="utf-8")

# Performance reviews (quarterly in 2025)
periodos = ["2025-Q1","2025-Q2","2025-Q3","2025-Q4"]
rev_rows = []
for per in periodos:
    ids = rng.choice(df_func["funcionario_id"].unique(), size=520, replace=False)
    score = np.round(np.clip(rng.normal(3.4, 0.7, size=len(ids)), 1.0, 5.0), 2)
    metas = np.clip(rng.poisson(6, size=len(ids)), 0, 12)
    promo = (score >= 4.4) & (metas >= 7) & (rng.random(len(ids)) < 0.25)
    rev_rows.append(pd.DataFrame({
        "periodo": per,
        "funcionario_id": ids,
        "score": score,
        "metas_atingidas": metas,
        "promocao_sugerida": promo.astype(int)
    }))
df_rev = pd.concat(rev_rows, ignore_index=True)
# missing scores
miss_score = rng.choice(df_rev.index, size=25, replace=False)
df_rev.loc[miss_score, "score"] = np.nan

df_rev.to_csv(rh_dir/"avaliacoes.csv", index=False, encoding="utf-8")

# Payroll (monthly 2025-01..2026-01)
months = pd.period_range("2025-01", "2026-01", freq="M").astype(str)
pay_rows = []
sal_map = df_func.drop_duplicates("funcionario_id").set_index("funcionario_id")["salario_base"].to_dict()
reg_map = df_func.drop_duplicates("funcionario_id").set_index("funcionario_id")["regime"].to_dict()

for m in months:
    ids = rng.choice(df_func["funcionario_id"].unique(), size=600, replace=False)
    gross = np.array([sal_map[i] for i in ids], dtype=float)
    # bonus: sales & performance
    bonus = np.round(np.clip(rng.normal(0.06, 0.08, size=len(ids)), 0, 0.35) * gross, 2)
    # deductions: taxes/benefits; PJ smaller deductions
    ded_pct = np.where(np.array([reg_map[i] for i in ids]) == "PJ", rng.uniform(0.02, 0.08, size=len(ids)), rng.uniform(0.12, 0.28, size=len(ids)))
    ded = np.round(gross * ded_pct, 2)
    net = np.round(gross + bonus - ded, 2)
    pay_rows.append(pd.DataFrame({
        "competencia": m,
        "funcionario_id": ids,
        "salario_bruto": gross,
        "bonus": bonus,
        "descontos": ded,
        "salario_liquido": net
    }))
df_pay = pd.concat(pay_rows, ignore_index=True)
# Inject duplicated payroll line
df_pay = pd.concat([df_pay, df_pay.sample(2, random_state=11)], ignore_index=True)
df_pay.to_csv(rh_dir/"folha_pagamento.csv", index=False, encoding="utf-8")

rh_readme = """# Dataset fictício: RH (Recursos Humanos) - Brasil

Arquivos:
- funcionarios.csv
- frequencia.csv
- avaliacoes.csv
- folha_pagamento.csv

Relações:
- frequencia.funcionario_id -> funcionarios.funcionario_id
- avaliacoes.funcionario_id -> funcionarios.funcionario_id
- folha_pagamento.funcionario_id -> funcionarios.funcionario_id

Problemas intencionais:
- cidade faltante em parte do cadastro
- registros duplicados de funcionário e folha
- salário com outliers
- horas_trabalhadas negativas em poucos registros
- score faltante em avaliações

Sugestões de exercícios:
1) Turnover por departamento e motivo
2) Absenteísmo e atrasos por time
3) Análise salarial (distribuições, outliers, equidade por senioridade)
4) Correlação performance x bônus x promoções
5) Construir um modelo simples para prever risco de desligamento (proxy)
"""
(rh_dir/"README_DATASET.md").write_text(rh_readme, encoding="utf-8")

rh_zip = out_root / "dataset_rh_ficticio.zip"
if rh_zip.exists():
    rh_zip.unlink()
with zipfile.ZipFile(rh_zip, "w", zipfile.ZIP_DEFLATED) as z:
    for fp in rh_dir.glob("*"):
        z.write(fp, arcname=fp.name)

# ------------------------------
# DATASET 2: Fiscal/NF-e (didático)
# ------------------------------
fiscal_dir = out_root / "dataset_fiscal_nfe_ficticio"
if fiscal_dir.exists():
    shutil.rmtree(fiscal_dir)
fiscal_dir.mkdir(parents=True, exist_ok=True)

def gen_digits(n):
    return "".join(map(str, rng.integers(0, 10, size=n)))

def gen_cnpj_one():
    return gen_digits(14)

# Emitters (companies)
n_emit = 25
emit_ids = np.arange(1, n_emit+1)
emit_uf = rng.choice(ufs, size=n_emit)
emit_city = [pick(cities[u]) for u in emit_uf]
emit_cnpj = [gen_cnpj_one() for _ in range(n_emit)]
emit_razao = [f"Empresa {i:02d} Comércio e Serviços LTDA" for i in emit_ids]

df_emit = pd.DataFrame({
    "emitente_id": emit_ids,
    "cnpj": emit_cnpj,
    "razao_social": emit_razao,
    "uf": emit_uf,
    "cidade": emit_city,
    "crt": rng.choice([1,2,3], size=n_emit, p=[0.30,0.10,0.60])  # regime tributário (simples/...). didático
})
df_emit.to_csv(fiscal_dir/"emitentes.csv", index=False, encoding="utf-8")

# Recipients (customers)
n_dest = 4200
dest_ids = np.arange(1, n_dest+1)
dest_tipo = rng.choice(["PF","PJ"], size=n_dest, p=[0.82,0.18])
dest_doc = [gen_digits(11) if t=="PF" else gen_cnpj_one() for t in dest_tipo]
dest_uf = rng.choice(ufs, size=n_dest)
dest_city = [pick(cities[u]) for u in dest_uf]

df_dest = pd.DataFrame({
    "destinatario_id": dest_ids,
    "tipo": dest_tipo,
    "documento": dest_doc,
    "uf": dest_uf,
    "cidade": dest_city,
})
# Missing city issues
df_dest.loc[rng.choice(df_dest.index, size=35, replace=False), "cidade"] = None
df_dest.to_csv(fiscal_dir/"destinatarios.csv", index=False, encoding="utf-8")

# Products for NF-e
n_prod = 600
prod_ids = np.arange(1, n_prod+1)

cats = ["Eletrônicos","Informática","Acessórios","Áudio","TV","Rede","Armazenamento"]
cat_probs = [0.20,0.25,0.18,0.10,0.12,0.07,0.08]
cat = rng.choice(cats, size=n_prod, p=cat_probs)
ncm_by_cat = {
    "Eletrônicos": "85171231",
    "Informática": "84713012",
    "Acessórios": "84716053",
    "Áudio": "85182100",
    "TV": "85287200",
    "Rede": "85176239",
    "Armazenamento": "84717012",
}
ncm = [ncm_by_cat[c] for c in cat]
desc = [f"Produto {i:04d} - {c}" for i, c in zip(prod_ids, cat)]
ean = np.char.add(rng.integers(10**11, 10**12, size=n_prod).astype(str), rng.integers(0,10,size=n_prod).astype(str)).tolist()

preco = np.round(np.clip(rng.lognormal(mean=7.2, sigma=0.55, size=n_prod), 35, 12000), 2)

df_prod_nf = pd.DataFrame({
    "produto_id": prod_ids,
    "descricao": desc,
    "categoria": cat,
    "ncm": ncm,
    "ean": ean,
    "preco_referencia": preco
})
# NCM inválido em poucos itens
bad_ncm = rng.choice(df_prod_nf.index, size=8, replace=False)
df_prod_nf.loc[bad_ncm[:4], "ncm"] = df_prod_nf.loc[bad_ncm[:4], "ncm"].str[:-1]  # 7 dígitos
df_prod_nf.loc[bad_ncm[4:], "ncm"] = df_prod_nf.loc[bad_ncm[4:], "ncm"] + "0"      # 9 dígitos
df_prod_nf.to_csv(fiscal_dir/"produtos.csv", index=False, encoding="utf-8")

# NF-e headers
n_nfe = 12000
nfe_ids = np.arange(1, n_nfe+1)

issue_start = dt.date(2025, 1, 1)
issue_end = dt.date(2026, 1, 20)
issue_days = (issue_end - issue_start).days
dh_emissao = [issue_start + dt.timedelta(days=int(rng.integers(0, issue_days))) for _ in range(n_nfe)]

emit_fk = rng.choice(emit_ids, size=n_nfe)
dest_fk = rng.choice(dest_ids, size=n_nfe)

uf_origem = df_emit.set_index("emitente_id")["uf"].to_dict()
uf_dest = df_dest.set_index("destinatario_id")["uf"].to_dict()
uf_o = np.array([uf_origem[e] for e in emit_fk])
uf_d = np.array([uf_dest[d] for d in dest_fk])

modelo = rng.choice([55,65], size=n_nfe, p=[0.78,0.22])  # 55 NFe, 65 NFCe (didático)
serie = rng.integers(1, 6, size=n_nfe)
numero = rng.integers(10000, 99999, size=n_nfe)

status = rng.choice(["AUTORIZADA","CANCELADA","DENEGADA"], size=n_nfe, p=[0.93,0.05,0.02])

# Charges
frete = np.round(np.where(modelo==55, rng.uniform(0, 180, size=n_nfe), 0.0), 2)
desconto = np.round(rng.uniform(0, 120, size=n_nfe), 2)
outros = np.round(rng.uniform(0, 60, size=n_nfe), 2)

df_nfe = pd.DataFrame({
    "nfe_id": nfe_ids,
    "dh_emissao": pd.to_datetime(dh_emissao),
    "modelo": modelo,
    "serie": serie,
    "numero": numero,
    "emitente_id": emit_fk,
    "destinatario_id": dest_fk,
    "uf_origem": uf_o,
    "uf_destino": uf_d,
    "status": status,
    "frete": frete,
    "desconto": desconto,
    "outros": outros,
})

# Duplicate invoice number within same series/emitter (data issue)
dup_hdr = df_nfe.sample(8, random_state=33)
df_nfe = pd.concat([df_nfe, dup_hdr], ignore_index=True)

# Items per NF-e
itens_por = rng.integers(1, 8, size=len(df_nfe))
n_itens = int(itens_por.sum())

nfe_rep = np.repeat(df_nfe["nfe_id"].values, itens_por)
prod_fk = rng.choice(prod_ids, size=n_itens)
qtd = rng.integers(1, 6, size=n_itens).astype(float)

# Unit price around reference with random variance
ref_price_map = df_prod_nf.set_index("produto_id")["preco_referencia"].to_dict()
unit = np.array([ref_price_map[p] for p in prod_fk]) * rng.uniform(0.85, 1.12, size=n_itens)
unit = np.round(unit, 2)

desc_pct = rng.uniform(0, 0.12, size=n_itens)
desc_val = np.round(unit * desc_pct, 2)
unit_liq = np.round(unit - desc_val, 2)

vprod = np.round(unit_liq * qtd, 2)

# Fiscal rules simplified
# CFOP: intra vs inter
# Determine origin/dest for each item via join nfe_id -> uf's
hdr_map = df_nfe.drop_duplicates("nfe_id").set_index("nfe_id")[["uf_origem","uf_destino","modelo","status"]].to_dict("index")

uf_o_item = np.array([hdr_map[i]["uf_origem"] for i in nfe_rep])
uf_d_item = np.array([hdr_map[i]["uf_destino"] for i in nfe_rep])

cfop = np.where(uf_o_item == uf_d_item, "5102", "6102").astype(str)
# Introduce some invalid CFOPs
bad_cfop_idx = rng.choice(np.arange(n_itens), size=20, replace=False)
cfop[bad_cfop_idx[:10]] = "9999"
cfop[bad_cfop_idx[10:]] = "5A02"

cst = rng.choice(["00","20","40","60"], size=n_itens, p=[0.62,0.14,0.10,0.14])

# Aliquotas by destination UF (didactic)
icms_aliq_uf = {"SP":0.18,"RJ":0.20,"MG":0.18,"PR":0.19,"SC":0.17,"RS":0.18,"BA":0.18,"PE":0.18,"CE":0.18,"GO":0.17,"DF":0.18}
aliq_icms = np.array([icms_aliq_uf.get(u, 0.18) for u in uf_d_item])
pis_aliq = 0.0165
cof_aliq = 0.076
ipi_aliq = rng.choice([0.0, 0.02, 0.05, 0.10], size=n_itens, p=[0.65,0.18,0.12,0.05])

vbc = np.abs(vprod)
vicms = np.round(vbc * aliq_icms, 2) * np.sign(vprod)
vpis = np.round(vbc * pis_aliq, 2) * np.sign(vprod)
vcof = np.round(vbc * cof_aliq, 2) * np.sign(vprod)
vipi = np.round(vbc * ipi_aliq, 2) * np.sign(vprod)

# Cancelled/denied should have zero base (inject inconsistencies)
st_item = np.array([hdr_map[i]["status"] for i in nfe_rep])
mask_cancel = st_item != "AUTORIZADA"
# mostly zero out, but leave some inconsistent to train audits
keep_inconsistent = rng.random(n_itens) < 0.02
zero_mask = mask_cancel & (~keep_inconsistent)
vprod[zero_mask] = 0.0
vicms[zero_mask] = 0.0
vpis[zero_mask] = 0.0
vcof[zero_mask] = 0.0
vipi[zero_mask] = 0.0

df_it = pd.DataFrame({
    "item_id": np.arange(1, n_itens+1),
    "nfe_id": nfe_rep,
    "produto_id": prod_fk,
    "ncm": df_prod_nf.set_index("produto_id").loc[prod_fk, "ncm"].values,
    "cfop": cfop,
    "cst_icms": cst,
    "qtd": qtd,
    "v_un": unit,
    "v_desc_un": desc_val,
    "v_un_liq": unit_liq,
    "v_prod": np.round(vprod, 2),
    "v_bc": np.round(vbc, 2),
    "aliq_icms": np.round(aliq_icms, 4),
    "v_icms": vicms,
    "aliq_pis": pis_aliq,
    "v_pis": vpis,
    "aliq_cofins": cof_aliq,
    "v_cofins": vcof,
    "aliq_ipi": np.round(ipi_aliq, 4),
    "v_ipi": vipi
})

# Outliers: absurdly large values
out_items = rng.choice(df_it.index, size=15, replace=False)
df_it.loc[out_items, "v_un"] = df_it.loc[out_items, "v_un"] * 25
df_it.loc[out_items, "v_prod"] = df_it.loc[out_items, "v_un"] * df_it.loc[out_items, "qtd"]

df_it.to_csv(fiscal_dir/"itens_nfe.csv", index=False, encoding="utf-8")

# Compute header totals from items then inject mismatches
sum_items = df_it.groupby("nfe_id")["v_prod"].sum().reset_index().rename(columns={"v_prod":"total_produtos"})
sum_imps = df_it.groupby("nfe_id")[["v_icms","v_pis","v_cofins","v_ipi"]].sum().reset_index()

df_nfe_tot = df_nfe.drop_duplicates("nfe_id").merge(sum_items, on="nfe_id", how="left").merge(sum_imps, on="nfe_id", how="left")
df_nfe_tot["total_produtos"] = df_nfe_tot["total_produtos"].fillna(0.0)
for col in ["v_icms","v_pis","v_cofins","v_ipi"]:
    df_nfe_tot[col] = df_nfe_tot[col].fillna(0.0)

df_nfe_tot["total_nfe"] = np.round(df_nfe_tot["total_produtos"] + df_nfe_tot["frete"] + df_nfe_tot["outros"] - df_nfe_tot["desconto"] + df_nfe_tot["v_ipi"], 2)

# Inject mismatched totals for audit training
mismatch_idx = rng.choice(df_nfe_tot.index, size=40, replace=False)
df_nfe_tot.loc[mismatch_idx, "total_nfe"] = np.round(df_nfe_tot.loc[mismatch_idx, "total_nfe"] * rng.uniform(0.7, 1.3, size=len(mismatch_idx)), 2)

df_nfe_tot.to_csv(fiscal_dir/"nfe_cabecalho.csv", index=False, encoding="utf-8")

fiscal_readme = """# Dataset fictício: Fiscal / NF-e (didático)

Arquivos:
- emitentes.csv
- destinatarios.csv
- produtos.csv
- nfe_cabecalho.csv
- itens_nfe.csv

Relações:
- nfe_cabecalho.emitente_id -> emitentes.emitente_id
- nfe_cabecalho.destinatario_id -> destinatarios.destinatario_id
- itens_nfe.nfe_id -> nfe_cabecalho.nfe_id
- itens_nfe.produto_id -> produtos.produto_id

Problemas intencionais (para treino):
- NCM inválido (7 ou 9 dígitos) em parte do catálogo
- CFOP inválido em alguns itens (9999 / 5A02)
- duplicidade de número/serie em alguns cabeçalhos
- notas CANCELADAS/DENEGADAS com itens não zerados em poucos casos (inconsistência)
- divergência entre total_nfe do cabeçalho e soma dos itens em algumas notas
- outliers de valores unitários e totais de itens

Sugestões de exercícios:
1) Auditoria: recomputar total e apontar divergências
2) Validação: NCM 8 dígitos, CFOP 4 dígitos numéricos, CST no domínio
3) ICMS por UF de destino e por CFOP
4) Identificar emitentes com maior taxa de cancelamento/denegação
5) Cluster/segmentação de destinatários por ticket e frequência
"""
(fiscal_dir/"README_DATASET.md").write_text(fiscal_readme, encoding="utf-8")

fiscal_zip = out_root / "dataset_fiscal_nfe_ficticio.zip"
if fiscal_zip.exists():
    fiscal_zip.unlink()
with zipfile.ZipFile(fiscal_zip, "w", zipfile.ZIP_DEFLATED) as z:
    for fp in fiscal_dir.glob("*"):
        z.write(fp, arcname=fp.name)

# Return summary
summary = {
    "RH_zip": str(rh_zip),
    "Fiscal_zip": str(fiscal_zip),
    "RH_files": sorted([p.name for p in rh_dir.glob("*")]),
    "Fiscal_files": sorted([p.name for p in fiscal_dir.glob("*")]),
    "RH_shapes": {
        "funcionarios": df_func.shape,
        "frequencia": df_att.shape,
        "avaliacoes": df_rev.shape,
        "folha": df_pay.shape,
    },
    "Fiscal_shapes": {
        "emitentes": df_emit.shape,
        "destinatarios": df_dest.shape,
        "produtos": df_prod_nf.shape,
        "cabecalho": df_nfe_tot.shape,
        "itens": df_it.shape,
    }
}
summary