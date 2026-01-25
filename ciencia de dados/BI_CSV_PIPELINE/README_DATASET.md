# Dataset fictício: Fiscal / NF-e (didático)

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
