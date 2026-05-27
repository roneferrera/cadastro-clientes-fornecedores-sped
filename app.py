# ============================================================
# app_sped_dominio.py  –  SPED Fiscal → Domínio Sistemas V2.1
# Dependências: streamlit, requests, pandas
# pip install streamlit requests pandas
# ============================================================

import streamlit as st
import requests
import time
import re
from datetime import datetime

VERSAO = "V2.1"
COD_PAIS_BRASIL = {"1058", "01058"}
SITUACAO_ATIVA  = 2
SITUACOES_DESCRICAO = {1: "NULA", 2: "ATIVA", 3: "SUSPENSA", 4: "INAPTA", 8: "BAIXADA"}
SITUACAO_ICONE  = {1: "🚫", 2: "✅", 3: "⚠️", 4: "⛔", 8: "❌"}


# ==============================
# TEMA TR
# ==============================
def apply_tr_theme():
    st.markdown("""
        <style>
        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Arial', sans-serif; color: #444444;
        }
        h1, h2, h3 { color: #FF8000; font-weight: 700; }
        section[data-testid="stSidebar"] { background-color: #444444; color: #FFFFFF; }
        section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
        .stButton > button {
            background-color: #FF8000; color: #FFFFFF;
            border: none; border-radius: 4px; font-weight: bold;
        }
        .stButton > button:hover { background-color: #D64001; color: #FFFFFF; }
        .stDownloadButton > button {
            background-color: #FF8000; color: #FFFFFF;
            border: none; border-radius: 4px; font-weight: bold;
        }
        .stDownloadButton > button:hover { background-color: #D64001; color: #FFFFFF; }
        hr { border-color: #FF8000; }
        [data-testid="metric-container"] {
            background-color: #E9E9E9; border-left: 4px solid #FF8000;
            border-radius: 4px; padding: 10px;
        }
        .instrucoes-box {
            background-color: #E9E9E9; border-left: 4px solid #FF8000;
            border-radius: 4px; padding: 16px 20px; margin: 12px 0;
            color: #444444; font-family: 'Segoe UI', Arial, sans-serif;
        }
        .instrucoes-box h4 { color: #FF8000; margin-top: 14px; margin-bottom: 6px; }
        .instrucoes-box h4:first-child { margin-top: 0; }
        </style>
    """, unsafe_allow_html=True)


# ==============================
# FUNÇÕES AUXILIARES
# ==============================
def limpar_cnpj(v: str) -> str:
    return re.sub(r"\D", "", v or "")

def is_exterior(cod_pais: str) -> bool:
    cod = (cod_pais or "").strip()
    return bool(cod) and cod not in COD_PAIS_BRASIL

def _gs(d: dict, k: str) -> str:
    return (d.get(k) or "").strip()

def get_situacao_cadastral(dados_api: dict) -> tuple:
    codigo = dados_api.get("situacao_cadastral")
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        codigo = None
    descricao = dados_api.get("descricao_situacao_cadastral", "") or ""
    if codigo is None:
        d = descricao.upper()
        if   "ATIVA"    in d: codigo = 2
        elif "BAIXADA"  in d: codigo = 8
        elif "INAPTA"   in d: codigo = 4
        elif "SUSPENSA" in d: codigo = 3
        elif "NULA"     in d: codigo = 1
        else:                 codigo = 0
    if not descricao:
        descricao = SITUACOES_DESCRICAO.get(codigo, "DESCONHECIDA")
    return codigo, descricao

def consultar_cnpj(cnpj: str) -> dict | None:
    c = limpar_cnpj(cnpj)
    if len(c) != 14:
        return None
    try:
        r = requests.get(f"https://minhareceita.org/{c}", timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def mapear_natureza_juridica(codigo_nj) -> str:
    if not codigo_nj:
        return "7"
    s = str(codigo_nj)
    if s.startswith("10"): return "1"
    if s.startswith("11"): return "2"
    if s.startswith("12"): return "3"
    if s.startswith("20"): return "4"
    if s.startswith("21"): return "5"
    if s.startswith("22"): return "6"
    try:
        if int(codigo_nj) == 2150: return "8"
    except Exception:
        pass
    return "7"

def mapear_regime(porte: str | None, opcao_simples: bool = False) -> str:
    if opcao_simples:
        if porte:
            p = porte.upper()
            if "PEQUENO" in p or p == "EPP": return "E"
        return "M"
    if not porte:
        return "N"
    p = porte.upper()
    if "MICRO"   in p or p == "ME":  return "M"
    if "PEQUENO" in p or p == "EPP": return "E"
    return "N"

def extrair_cod_ibge(dados_api: dict) -> str:
    """
    Retorna o código IBGE do município da API minhareceita.org.
    Campo: "codigo_municipio_ibge" → int ou str, ex: 3550308
    NUNCA retorna o campo "municipio" (nome por extenso).
    """
    cod = dados_api.get("codigo_municipio_ibge")
    if cod is None:
        return ""
    cod_str = str(cod).strip()
    return cod_str if cod_str.isdigit() else ""

def sanitizar_numero_endereco(valor: str) -> str:
    """
    Campo 06 — Número do endereço (Numérico no leiaute Domínio).
    Valor não numérico (S/N, SN, s/n, -, --, em branco) → retorna vazio.
    Valor numérico → retorna apenas os dígitos.
    """
    if not valor:
        return ""
    v = valor.strip()
    apenas_digitos = re.sub(r"\D", "", v)
    if not apenas_digitos:
        return ""
    return apenas_digitos


# ==============================
# LEITURA DO SPED FISCAL
# ==============================
def _split_sped(linha: str) -> list:
    campos = linha.strip().split("|")
    if campos and campos[0] == "":
        campos = campos[1:]
    if campos and campos[-1] == "":
        campos = campos[:-1]
    return campos

def _get(campos: list, idx: int) -> str:
    return campos[idx].strip() if idx < len(campos) else ""

def extrair_cabecalho_sped(conteudo: str, log: list) -> dict | None:
    for linha in conteudo.splitlines():
        campos = _split_sped(linha)
        if not campos or campos[0] != "0000":
            continue

        log.append(
            f"Registro 0000 encontrado. Campos: {len(campos)}. "
            f"Prévia: {' | '.join(campos[:10])}{'...' if len(campos) > 10 else ''}"
        )

        cnpj_encontrado = ""
        cnpj_idx        = -1
        nome_encontrado = ""

        for i, campo in enumerate(campos):
            if len(re.sub(r"\D", "", campo)) == 14:
                cnpj_encontrado = re.sub(r"\D", "", campo)
                cnpj_idx        = i
                nome_encontrado = campos[i - 1].strip() if i > 0 else ""
                break

        if not cnpj_encontrado:
            for idx_c, idx_n in [(6, 5), (8, 7)]:
                t = limpar_cnpj(_get(campos, idx_c))
                if len(t) == 14:
                    cnpj_encontrado = t
                    cnpj_idx        = idx_c
                    nome_encontrado = _get(campos, idx_n)
                    break

        if not cnpj_encontrado:
            log.append("ERRO: CNPJ de 14 dígitos não localizado no registro 0000.")
            return None

        dt_ini  = _get(campos, cnpj_idx - 3) if cnpj_idx >= 3 else ""
        dt_fin  = _get(campos, cnpj_idx - 2) if cnpj_idx >= 2 else ""
        uf      = _get(campos, cnpj_idx + 2)
        ie      = _get(campos, cnpj_idx + 3)
        cod_mun = _get(campos, cnpj_idx + 4)

        def fmt_dt(s):
            s = s.strip()
            if len(s) == 8 and s.isdigit():
                return f"{s[0:2]}/{s[2:4]}/{s[4:8]}"
            return s

        log.append(
            f"Empresa identificada → CNPJ: {cnpj_encontrado} | "
            f"Nome: {nome_encontrado} | UF: {uf} | "
            f"Período: {fmt_dt(dt_ini)} a {fmt_dt(dt_fin)} (índice [{cnpj_idx}])"
        )
        return {
            "cnpj": cnpj_encontrado, "nome": nome_encontrado,
            "dt_ini": dt_ini, "dt_fin": dt_fin,
            "uf": uf, "ie": ie, "cod_mun": cod_mun,
        }

    log.append("ERRO: Registro 0000 não encontrado no arquivo SPED Fiscal.")
    return None


def extrair_participantes_sped(conteudo: str) -> list:
    """
    Extrai registros 0150 do SPED Fiscal.
    |0150|COD_PART|NOME|COD_PAIS|CNPJ|CPF|IE|COD_MUN|SUFRAMA|END|NUM|COMPL|BAIRRO|
    """
    participantes = []
    for linha in conteudo.splitlines():
        campos = _split_sped(linha)
        if not campos or campos[0] != "0150":
            continue
        try:
            participantes.append({
                "cod_part": _get(campos,  1),
                "nome":     _get(campos,  2),
                "cod_pais": _get(campos,  3),
                "cnpj":     _get(campos,  4),
                "cpf":      _get(campos,  5),
                "ie":       _get(campos,  6),
                "cod_mun":  _get(campos,  7),  # código IBGE do SPED
                "suframa":  _get(campos,  8),
                "end":      _get(campos,  9),
                "num":      _get(campos, 10),
                "compl":    _get(campos, 11),
                "bairro":   _get(campos, 12),
            })
        except Exception:
            continue
    return participantes


def classificar_participantes(conteudo: str, log: list) -> dict:
    """
    C100/D100: IND_OPER=0 → Entrada → FORNECEDOR
               IND_OPER=1 → Saída   → CLIENTE
    """
    clientes     = set()
    fornecedores = set()
    for linha in conteudo.splitlines():
        campos = _split_sped(linha)
        if not campos:
            continue
        if campos[0] in ("C100", "D100"):
            ind_oper = _get(campos, 1)
            cod_part = _get(campos, 3)
            if not cod_part:
                continue
            if ind_oper == "0":
                fornecedores.add(cod_part)
            elif ind_oper == "1":
                clientes.add(cod_part)
    log.append(
        f"Classificação por movimentação → "
        f"Somente Clientes: {len(clientes - fornecedores)} | "
        f"Somente Fornecedores: {len(fornecedores - clientes)} | "
        f"Ambos: {len(clientes & fornecedores)}"
    )
    return {"clientes": clientes, "fornecedores": fornecedores}


# ==============================
# GERAÇÃO DE LINHAS DOMÍNIO
# ==============================
def gerar_linha_0000(cnpj_empresa: str) -> str:
    """
    Registro 0000 — Identificação da empresa.
    Campo 01: "0000" (fixo)
    Campo 02: CNPJ apenas números
    """
    return f"0000|{limpar_cnpj(cnpj_empresa)}|\n"


def _montar_endereco(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> dict:
    """
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Campo 06 — Número do endereço (Numérico)                             │
    │   Valor não numérico (S/N, SN, s/n, -, --) → VAZIO                  │
    │   Valor numérico → apenas dígitos                                    │
    │                                                                      │
    │ Campo 09 — Código do município (Numérico IBGE)                       │
    │   Leiaute: "código estadual, federal ou IBGE/RAIS"                   │
    │                                                                      │
    │   CNPJ ATIVO (API)  → codigo_municipio_ibge da Receita Federal       │
    │                        ex: 3550308, 4106902, 3106200                 │
    │   CNPJ BAIXADO/INAPTO/SUSPENSO/CPF/SEM API                          │
    │                      → cod_mun do registro 0150 do SPED              │
    │   EXTERIOR          → "EX"                                           │
    │                                                                      │
    │   NUNCA usar dados_api["municipio"] (nome por extenso)               │
    │                                                                      │
    │ Campo 10 — UF                                                        │
    │   CNPJ ATIVO  → dados_api["uf"]                                      │
    │   SPED        → vazio                                                │
    │   EXTERIOR    → "EX"                                                 │
    │                                                                      │
    │ Campo 11 — Código do País                                            │
    │   EXTERIOR    → cod_pais do SPED                                     │
    │   Nacional    → vazio                                                │
    │                                                                      │
    │ Campo 12 — CEP                                                       │
    │   CNPJ ATIVO  → CEP da Receita (8 dígitos, sem traço)               │
    │   Demais      → vazio                                                │
    └──────────────────────────────────────────────────────────────────────┘
    """
    if exterior:
        return {
            "logradouro":  _gs(dados_sped, "end"),
            "numero":      sanitizar_numero_endereco(_gs(dados_sped, "num")),
            "complemento": _gs(dados_sped, "compl"),
            "bairro":      _gs(dados_sped, "bairro"),
            "cod_mun":     "EX",
            "uf":          "EX",
            "cod_pais":    _gs(dados_sped, "cod_pais"),
            "cep":         "",
        }

    elif usar_sped:
        # CNPJ baixado/inapto/suspenso/CPF/sem API
        # Usa cod_mun do SPED (código IBGE informado pelo contribuinte)
        return {
            "logradouro":  _gs(dados_sped, "end"),
            "numero":      sanitizar_numero_endereco(_gs(dados_sped, "num")),
            "complemento": _gs(dados_sped, "compl"),
            "bairro":      _gs(dados_sped, "bairro"),
            "cod_mun":     _gs(dados_sped, "cod_mun"),  # ← código IBGE do SPED
            "uf":          "",
            "cod_pais":    "",
            "cep":         "",
        }

    else:
        # CNPJ ATIVO — dados da Receita Federal
        # Campo 09 = codigo_municipio_ibge da API (número, ex: 3550308)
        # NUNCA usar dados_api["municipio"] (nome por extenso)
        cod_ibge_api = extrair_cod_ibge(dados_api)
        num_api      = dados_api.get("numero", _gs(dados_sped, "num")) or ""
        cep_api      = re.sub(r"\D", "", dados_api.get("cep", "") or "")
        return {
            "logradouro":  (dados_api.get("logradouro",  _gs(dados_sped, "end"))  or ""),
            "numero":      sanitizar_numero_endereco(str(num_api)),
            "complemento": (dados_api.get("complemento", _gs(dados_sped, "compl")) or ""),
            "bairro":      (dados_api.get("bairro",      _gs(dados_sped, "bairro")) or ""),
            "cod_mun":     cod_ibge_api,  # ← código IBGE numérico da Receita Federal
            "uf":          (dados_api.get("uf", "") or ""),
            "cod_pais":    "",
            "cep":         cep_api,
        }


def _montar_comuns(dados_api: dict, dados_sped: dict,
                   exterior: bool, usar_sped: bool) -> dict:
    """
    Campos comuns a 0010 e 0020.

    Campo 02 — Inscrição (apenas números):
      CNPJ ativo (API)    → CNPJ da API (14 dígitos)
      CNPJ baixado/inapto → CNPJ do SPED (14 dígitos)
      CPF                 → CPF do SPED (11 dígitos)
      Exterior            → vazio

    Campo 03 — Razão Social (máx 150 chars):
      CNPJ ativo → razao_social da API
      Demais     → nome do SPED

    Campo 04 — Apelido (máx 40 chars):
      SEMPRE = razao[:40]

    Campo 19 — Data do cadastro:
      SEMPRE VAZIO — evita erro "Não existem parâmetros para a vigência"
    """
    if exterior:
        inscricao = ""
        razao     = _gs(dados_sped, "nome")[:150]
        ie = suframa = ddd = telefone = fax = email = ""
        nat_jur = "7"
        regime  = "N"

    elif usar_sped:
        cnpj_sped = limpar_cnpj(_gs(dados_sped, "cnpj"))
        cpf_sped  = limpar_cnpj(_gs(dados_sped, "cpf"))
        inscricao = (
            cnpj_sped if len(cnpj_sped) == 14 else
            cpf_sped  if len(cpf_sped)  == 11 else
            cnpj_sped or cpf_sped
        )
        razao    = _gs(dados_sped, "nome")[:150]
        ie       = _gs(dados_sped, "ie")
        suframa  = _gs(dados_sped, "suframa")
        ddd = telefone = fax = email = ""
        nat_jur = "7"
        regime  = "N"

    else:
        # CNPJ ATIVO — dados da Receita Federal
        cnpj_api  = limpar_cnpj(dados_api.get("cnpj", "") or "")
        cnpj_sped = limpar_cnpj(_gs(dados_sped, "cnpj"))
        cpf_sped  = limpar_cnpj(_gs(dados_sped, "cpf"))
        inscricao = (
            cnpj_api  if len(cnpj_api)  == 14 else
            cnpj_sped if len(cnpj_sped) == 14 else
            cpf_sped  if len(cpf_sped)  == 11 else
            cnpj_api or cnpj_sped or cpf_sped
        )
        razao    = (dados_api.get("razao_social", _gs(dados_sped, "nome")) or "")[:150]
        ie       = _gs(dados_sped, "ie")
        suframa  = _gs(dados_sped, "suframa")
        tel_raw  = dados_api.get("ddd_telefone_1", "") or ""
        ddd      = tel_raw[:2]
        telefone = tel_raw[2:]
        fax      = dados_api.get("fax", "") or ""
        nat_jur  = mapear_natureza_juridica(dados_api.get("codigo_natureza_juridica"))
        opcao_simples = bool(dados_api.get("opcao_pelo_simples", False))
        regime   = mapear_regime(dados_api.get("porte", ""), opcao_simples)
        email    = dados_api.get("email", "") or ""

    apelido = razao[:40]

    return {
        "inscricao": inscricao,   # campo 02 — CNPJ/CPF apenas números
        "razao":     razao,       # campo 03 — máx 150
        "apelido":   apelido,     # campo 04 — razao[:40]
        "ie":        ie,          # campo 13
        "im":        "",          # campo 14
        "suframa":   suframa,     # campo 15
        "ddd":       ddd,         # campo 16
        "telefone":  telefone,    # campo 17
        "fax":       fax,         # campo 18
        "data_cad":  "",          # campo 19 — SEMPRE VAZIO
        "nat_jur":   nat_jur,     # campo 23
        "regime":    regime,      # campo 24
        "email":     email,       # campo 29 (só 0020)
    }


def gerar_linha_0010(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> str:
    """
    Registro 0010 — Cadastro de cliente (32 campos).
    Leiaute conforme Registro 0010.xlsx.
    """
    end = _montar_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _montar_comuns(dados_api, dados_sped, exterior, usar_sped)

    campos = [
        "0010",             # 01 Identificação — fixo "0010"
        c["inscricao"],     # 02 Inscrição — CNPJ/CPF apenas números
        c["razao"],         # 03 Razão Social — máx 150 chars
        c["apelido"],       # 04 Apelido — razao[:40]
        end["logradouro"],  # 05 Endereço
        end["numero"],      # 06 Número — numérico; S/N e similares → vazio
        end["complemento"], # 07 Complemento
        end["bairro"],      # 08 Bairro
        end["cod_mun"],     # 09 Código município — IBGE numérico ou "EX"
        end["uf"],          # 10 UF — ou "EX" para exterior
        end["cod_pais"],    # 11 Código do País — só exterior
        end["cep"],         # 12 CEP — 8 dígitos sem traço
        c["ie"],            # 13 Inscrição Estadual
        c["im"],            # 14 Inscrição Municipal
        c["suframa"],       # 15 Inscrição Suframa
        c["ddd"],           # 16 DDD
        c["telefone"],      # 17 Telefone
        c["fax"],           # 18 FAX
        c["data_cad"],      # 19 Data cadastro — SEMPRE VAZIO
        "",                 # 20 Conta contábil
        "",                 # 21 Conta contábil fornecedor
        "N",                # 22 Agropecuário — S/N
        c["nat_jur"],       # 23 Natureza jurídica — 1 a 9
        c["regime"],        # 24 Regime de apuração — N/M/E/O/U/I
        "N",                # 25 Contribuinte ICMS — S/N
        "",                 # 26 Alíquota ICMS
        "",                 # 27 Categoria do estabelecimento
        "N",                # 28 Interdependência — S/N
        "",                 # 29 MT-Percentual Carga Média
        "N",                # 30 Inscrito no PAA — S/N
        "",                 # 31 Tipo Inscrição
        "",                 # 32 Processo adm/judicial
    ]
    return "|".join(str(x) for x in campos) + "|\n"


def gerar_linha_0020(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> str:
    """
    Registro 0020 — Cadastro de fornecedor (33 campos).
    Leiaute conforme Registro 0020.xlsx.
    """
    end = _montar_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _montar_comuns(dados_api, dados_sped, exterior, usar_sped)

    campos = [
        "0020",             # 01 Identificação — fixo "0020"
        c["inscricao"],     # 02 Inscrição — CNPJ/CPF apenas números
        c["razao"],         # 03 Razão Social — máx 150 chars
        c["apelido"],       # 04 Apelido — razao[:40]
        end["logradouro"],  # 05 Endereço
        end["numero"],      # 06 Número — numérico; S/N e similares → vazio
        end["complemento"], # 07 Complemento
        end["bairro"],      # 08 Bairro
        end["cod_mun"],     # 09 Código município — IBGE numérico ou "EX"
        end["uf"],          # 10 UF — ou "EX" para exterior
        end["cod_pais"],    # 11 Código do País — só exterior
        end["cep"],         # 12 CEP — 8 dígitos sem traço
        c["ie"],            # 13 Inscrição Estadual
        c["im"],            # 14 Inscrição Municipal
        c["suframa"],       # 15 Inscrição Suframa
        c["ddd"],           # 16 DDD
        c["telefone"],      # 17 Telefone
        c["fax"],           # 18 FAX
        c["data_cad"],      # 19 Data cadastro — SEMPRE VAZIO
        "",                 # 20 Conta contábil
        "",                 # 21 Conta contábil cliente
        "N",                # 22 Agropecuário — S/N
        c["nat_jur"],       # 23 Natureza jurídica — 1 a 8
        c["regime"],        # 24 Regime de apuração — N/M/E/O/U/I
        "N",                # 25 Contribuinte ICMS — S/N
        "",                 # 26 Alíquota ICMS
        "",                 # 27 Categoria do estabelecimento
        "",                 # 28 Inscrição Estadual ST
        c["email"],         # 29 Email
        "N",                # 30 Interdependência — S/N
        "N",                # 31 Contribuinte da CPRB — S/N
        "",                 # 32 Processo adm/judicial
        "",                 # 33 Tipo Inscrição
    ]
    return "|".join(str(x) for x in campos) + "|\n"


# ==============================
# PROCESSAMENTO PRINCIPAL
# ==============================
def processar_sped(conteudo_sped: str, modo: str,
                   delay_api: float, log: list) -> tuple:
    """
    modo = "auto"         → classifica por C100/D100
         = "clientes"     → gera só 0010 para todos
         = "fornecedores" → gera só 0020 para todos
         = "ambos"        → gera 0010 e 0020 para todos
    """
    cabecalho = extrair_cabecalho_sped(conteudo_sped, log)
    if cabecalho is None:
        return None, None, None, None

    cnpj_empresa = cabecalho["cnpj"]
    nome_empresa = cabecalho["nome"]

    if not cnpj_empresa:
        log.append("ERRO: CNPJ da empresa não encontrado no registro 0000.")
        return None, None, None, None

    if modo == "auto":
        classificacao = classificar_participantes(conteudo_sped, log)
    else:
        classificacao = {"clientes": set(), "fornecedores": set()}

    participantes = extrair_participantes_sped(conteudo_sped)
    total = len(participantes)

    if total == 0:
        log.append("AVISO: Nenhum registro 0150 encontrado.")
        return (
            [gerar_linha_0000(cnpj_empresa)],
            [],
            {"api_ativa": 0, "baixada": 0, "inapta": 0,
             "suspensa": 0, "nula": 0, "sem_api": 0,
             "cpf_sped": 0, "exterior": 0},
            cabecalho,
        )

    log.append(f"{total} participante(s) encontrado(s) no registro 0150.")

    linhas_saida = [gerar_linha_0000(cnpj_empresa)]
    dados_tabela = []
    contadores   = {
        "api_ativa": 0, "baixada": 0, "inapta": 0,
        "suspensa":  0, "nula":    0, "sem_api": 0,
        "cpf_sped":  0, "exterior": 0,
    }

    progresso = st.progress(0, text="Iniciando...")
    log_area  = st.empty()

    for idx, part in enumerate(participantes):
        pct      = int((idx + 1) / total * 100)
        cnpj_raw = limpar_cnpj(part["cnpj"])
        exterior = is_exterior(part["cod_pais"])
        cod_part = part["cod_part"]

        # ── Papel ────────────────────────────────────────────────────
        if modo == "auto":
            e_cliente    = cod_part in classificacao["clientes"]
            e_fornecedor = cod_part in classificacao["fornecedores"]
            if not e_cliente and not e_fornecedor:
                e_cliente = e_fornecedor = True
                papel = "🔄 Ambos (sem movimentação)"
            elif e_cliente and e_fornecedor:
                papel = "🔄 Ambos"
            elif e_cliente:
                papel = "🛒 Cliente"
            else:
                papel = "🏭 Fornecedor"
        elif modo == "clientes":
            e_cliente = True;  e_fornecedor = False; papel = "🛒 Cliente"
        elif modo == "fornecedores":
            e_cliente = False; e_fornecedor = True;  papel = "🏭 Fornecedor"
        else:
            e_cliente = e_fornecedor = True; papel = "🔄 Ambos"

        progresso.progress(
            pct,
            text=f"Processando {idx+1}/{total}: "
                 f"{'🌍 EXT' if exterior else cnpj_raw or 'CPF'} [{papel}]",
        )

        dados_api     = {}
        usar_sped     = False
        situacao_desc = ""
        status_label  = ""
        razao_final   = part["nome"]
        cod_mun_log   = ""

        # ── Fonte dos dados ──────────────────────────────────────────
        if exterior:
            usar_sped    = True
            cod_mun_log  = "EX"
            status_label = f"🌍 Exterior (COD_PAIS={part['cod_pais']})"
            contadores["exterior"] += 1
            log.append(
                f"[{idx+1:03d}/{total}] {part['nome'][:35]} | "
                f"{papel} | {status_label}"
            )

        elif len(cnpj_raw) == 14:
            dados_api_bruto = consultar_cnpj(cnpj_raw)
            time.sleep(delay_api)

            if dados_api_bruto is None:
                usar_sped    = True
                cod_mun_log  = part["cod_mun"]
                status_label = (
                    f"⚠️ {cnpj_raw} — sem resposta da API. "
                    f"Usando SPED. Município IBGE (SPED): {cod_mun_log}"
                )
                contadores["sem_api"] += 1
                log.append(
                    f"[{idx+1:03d}/{total}] {cnpj_raw} | {papel} | {status_label}"
                )
            else:
                situacao_cod, situacao_desc = get_situacao_cadastral(dados_api_bruto)
                icone = SITUACAO_ICONE.get(situacao_cod, "❓")

                if situacao_cod == SITUACAO_ATIVA:
                    dados_api    = dados_api_bruto
                    usar_sped    = False
                    razao_final  = dados_api.get("razao_social", part["nome"])
                    cod_mun_log  = extrair_cod_ibge(dados_api)
                    status_label = (
                        f"✅ {cnpj_raw} — ATIVA | "
                        f"Município IBGE (API): {cod_mun_log}"
                    )
                    contadores["api_ativa"] += 1
                else:
                    usar_sped    = True
                    cod_mun_log  = part["cod_mun"]
                    status_label = (
                        f"{icone} {cnpj_raw} — {situacao_desc} "
                        f"(sit. {situacao_cod}). "
                        f"Usando SPED. Município IBGE (SPED): {cod_mun_log}"
                    )
                    if   situacao_cod == 8: contadores["baixada"]  += 1
                    elif situacao_cod == 4: contadores["inapta"]   += 1
                    elif situacao_cod == 3: contadores["suspensa"]  += 1
                    elif situacao_cod == 1: contadores["nula"]      += 1
                    else:                  contadores["sem_api"]   += 1

                log.append(
                    f"[{idx+1:03d}/{total}] {cnpj_raw} | "
                    f"{razao_final[:30]} | {papel} | {status_label}"
                )
        else:
            usar_sped    = True
            cod_mun_log  = part["cod_mun"]
            status_label = (
                f"ℹ️ {cnpj_raw or limpar_cnpj(part['cpf'])} — "
                f"CPF/sem CNPJ. Usando SPED. Município IBGE (SPED): {cod_mun_log}"
            )
            contadores["cpf_sped"] += 1
            log.append(
                f"[{idx+1:03d}/{total}] {part['nome'][:35]} | "
                f"{papel} | {status_label}"
            )

        # ── Gera linhas ──────────────────────────────────────────────
        if e_cliente:
            linhas_saida.append(
                gerar_linha_0010(dados_api, part, exterior, usar_sped)
            )
        if e_fornecedor:
            linhas_saida.append(
                gerar_linha_0020(dados_api, part, exterior, usar_sped)
            )

        dados_tabela.append({
            "COD_PART":             cod_part,
            "CNPJ/CPF":             cnpj_raw or limpar_cnpj(part["cpf"]),
            "Nome (SPED)":          part["nome"],
            "Razão Social (API)":   dados_api.get("razao_social", ""),
            "Município IBGE (c09)": cod_mun_log,
            "Apelido":              razao_final[:40],
            "Papel":                papel,
            "Situação Receita":     situacao_desc or "—",
            "COD_PAIS":             part["cod_pais"],
            "Fonte":                "SPED" if usar_sped else "Receita Federal",
            "Status":               status_label,
        })

        log_area.text_area(
            "Log de processamento",
            value="\n".join(log[-20:]),
            height=200,
        )

    progresso.progress(100, text="✅ Concluído!")
    log.append(
        f"Arquivo gerado com {len(linhas_saida) - 1} registro(s). "
        f"Empresa: {nome_empresa} | CNPJ: {cnpj_empresa} | "
        f"Ativos(API)={contadores['api_ativa']} | "
        f"Baixados={contadores['baixada']} | "
        f"Inaptos={contadores['inapta']} | "
        f"Suspensos={contadores['suspensa']} | "
        f"Exterior={contadores['exterior']} | "
        f"CPF/SemAPI={contadores['cpf_sped'] + contadores['sem_api']}"
    )
    return linhas_saida, dados_tabela, contadores, cabecalho


# ==============================
# INTERFACE STREAMLIT
# ==============================
def main():
    st.set_page_config(
        page_title="Domínio Sistemas | Thomson Reuters",
        page_icon="🟠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_tr_theme()

    st.markdown(
        f"""
        <div style="background:#444444; padding:24px 28px 18px 28px;
                    border-radius:8px; border-top:6px solid #FF8000;
                    margin-bottom:28px;">
            <h2 style="color:#FF8000; margin:0;
                       font-family:'Segoe UI',Arial,sans-serif;">
                🏢 Importação de Clientes e Fornecedores
                — SPED → Domínio &nbsp;|&nbsp; {VERSAO}
            </h2>
            <p style="color:#DDDDDD; margin:6px 0 0 0;
                      font-family:'Segoe UI',Arial,sans-serif;">
                Faça o upload do SPED Fiscal e clique em
                <strong>▶ Gerar arquivo Domínio</strong>.
                CNPJ, nome e classificação detectados automaticamente.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Configurações")
        modo = st.radio(
            "Modo de classificação:",
            options=[
                "🔍 Automático (por C100/D100)",
                "🛒 Somente Clientes (0010)",
                "🏭 Somente Fornecedores (0020)",
                "🔄 Ambos (0010 e 0020)",
            ],
            index=0,
        )
        delay_api = st.slider(
            "Intervalo entre consultas (s)",
            min_value=0.5, max_value=5.0, value=1.0, step=0.5,
        )
        st.markdown("---")
        st.markdown("### 📋 Campo 09 — Município (IBGE)")
        st.markdown(
            "| Situação | Fonte | Valor |\n"
            "|---|---|---|\n"
            "| CNPJ Ativo | Receita Federal | `codigo_municipio_ibge` |\n"
            "| CNPJ Baixado/Inapto/Suspenso | SPED 0150 | `cod_mun` |\n"
            "| CPF / Sem API | SPED 0150 | `cod_mun` |\n"
            "| Exterior | — | `EX` |"
        )
        st.markdown("---")
        st.markdown("### 📋 Campo 06 — Número")
        st.markdown(
            "| Valor | Campo 06 |\n"
            "|---|---|\n"
            "| `3355`, `450`, `17790` | Mantém |\n"
            "| `S/N`, `SN`, `s/n`, `-` | **Vazio** |"
        )
        st.markdown("---")
        st.markdown("### 📋 Situação Cadastral")
        for cod, desc in SITUACOES_DESCRICAO.items():
            icone = SITUACAO_ICONE.get(cod, "❓")
            fonte = "Receita Federal" if cod == SITUACAO_ATIVA else "**Dados do SPED**"
            st.caption(f"{icone} **{desc}** → {fonte}")
        st.markdown("---")
        st.markdown("### ℹ Sobre")
        st.markdown(f"**Versão:** {VERSAO}")
        st.markdown("**Thomson Reuters**")
        st.markdown("**Domínio Sistemas**")

    # ── Instruções ────────────────────────────────────────────────────
    with st.expander("📖 **Instruções de Uso** — clique para expandir", expanded=False):
        st.markdown(
            """
            <div class="instrucoes-box">

            <h4>🔹 Passo 1 — Exportar o SPED Fiscal</h4>
            <p>Exporte o arquivo <b>SPED Fiscal (.txt)</b> do sistema de origem.
            O arquivo deve conter o registro <b>0000</b> (empresa) e os registros
            <b>0150</b> (participantes).</p>

            <h4>🔹 Passo 2 — Selecionar o modo de classificação</h4>
            <ul>
                <li><b>🔍 Automático</b>: analisa C100/D100 — entrada=fornecedor, saída=cliente.</li>
                <li><b>🛒 Somente Clientes</b>: gera apenas registros 0010.</li>
                <li><b>🏭 Somente Fornecedores</b>: gera apenas registros 0020.</li>
                <li><b>🔄 Ambos</b>: gera 0010 e 0020 para todos.</li>
            </ul>

            <h4>🔹 Passo 3 — Fazer upload e gerar o arquivo</h4>
            <ol>
                <li>Clique em <b>Browse files</b> e selecione o SPED Fiscal (.txt).</li>
                <li>Clique em <b>▶ Gerar arquivo Domínio</b>.</li>
                <li>Clique em <b>⬇ Baixar arquivo TXT</b>.</li>
            </ol>

            <h4>🔹 Passo 4 — Importar no Domínio Sistemas</h4>
            <p>No Domínio: <b>Utilitários → Importação → Importação Padrão →
            Leiaute Domínio Sistemas com Separador</b>.</p>

            <hr>

            <h4>⚠ Observações importantes (V2.1)</h4>
            <ul>
                <li><b>Campo 06 — Número do endereço</b>: valores não numéricos
                    (<code>S/N</code>, <code>SN</code>, <code>s/n</code>, <code>-</code>)
                    são substituídos por <b>vazio</b> — o campo é Numérico no leiaute.</li>
                <li><b>Campo 09 — Código do município</b>:
                    CNPJ ativo → <code>codigo_municipio_ibge</code> da Receita Federal
                    (ex: <code>3550308</code>).
                    Demais → <code>cod_mun</code> do SPED.
                    Exterior → <code>EX</code>.</li>
                <li><b>Campo 19 — Data do cadastro</b>: sempre <b>vazia</b> —
                    evita o erro <i>"Não existem parâmetros para a vigência"</i>.</li>
                <li><b>CNPJ Ativo</b>: dados da <b>Receita Federal</b>.</li>
                <li><b>CNPJ Baixado/Inapto/Suspenso</b>: CNPJ + dados do <b>SPED</b>.</li>
                <li><b>Exterior</b>: dados do SPED; campos 09 e 10 = <code>EX</code>.</li>
            </ul>

            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Session state ─────────────────────────────────────────────────
    defaults = {
        "log":          [f"Aplicação pronta. Versão: {VERSAO}"],
        "txt_gerado":   None,
        "nome_arquivo": "dominio_separador.txt",
        "dados_tabela": None,
        "contadores":   None,
        "cabecalho":    None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Upload ────────────────────────────────────────────────────────
    arquivo_sped = st.file_uploader(
        "Arquivo SPED Fiscal (.txt)",
        type=["txt"],
        help="CNPJ da empresa e classificação detectados automaticamente.",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        gerar = st.button(
            "▶ Gerar arquivo Domínio",
            disabled=(arquivo_sped is None),
            use_container_width=True,
            type="primary",
        )
    with col2:
        limpar = st.button("🗑 Limpar", use_container_width=True)

    if limpar:
        for k, v in defaults.items():
            st.session_state[k] = v
        st.session_state.log = ["Campos limpos."]
        st.rerun()

    # ── Processamento ─────────────────────────────────────────────────
    if gerar and arquivo_sped is not None:
        for k in defaults:
            st.session_state[k] = (
                ["Iniciando geração do arquivo..."] if k == "log" else None
            )

        conteudo_sped = arquivo_sped.read().decode("latin-1", errors="replace")
        modo_map = {
            "🔍 Automático (por C100/D100)":  "auto",
            "🛒 Somente Clientes (0010)":      "clientes",
            "🏭 Somente Fornecedores (0020)":  "fornecedores",
            "🔄 Ambos (0010 e 0020)":          "ambos",
        }
        modo_selecionado = modo_map.get(modo, "auto")

        linhas, dados_tabela, contadores, cabecalho = processar_sped(
            conteudo_sped, modo_selecionado,
            delay_api, st.session_state.log,
        )

        tem_erro = any(str(l).startswith("ERRO") for l in st.session_state.log)

        if linhas and not tem_erro:
            st.session_state.txt_gerado = "".join(linhas).encode(
                "latin-1", errors="replace"
            )
            cnpj_arq = cabecalho["cnpj"] if cabecalho else "empresa"
            st.session_state.nome_arquivo = (
                f"dominio_separador_{cnpj_arq}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            st.session_state.dados_tabela = dados_tabela
            st.session_state.contadores   = contadores
            st.session_state.cabecalho    = cabecalho

        st.rerun()

    # ── Card empresa ──────────────────────────────────────────────────
    if st.session_state.cabecalho:
        cab = st.session_state.cabecalho
        def fmt_dt(s):
            s = (s or "").strip()
            if len(s) == 8 and s.isdigit():
                return f"{s[0:2]}/{s[2:4]}/{s[4:8]}"
            return s or "—"
        st.markdown(
            f"""
            <div style="background:#FFF8F0; border-left:4px solid #FF8000;
                        border-radius:4px; padding:12px 18px; margin-bottom:16px;
                        font-family:'Segoe UI',Arial,sans-serif; color:#444;">
                <b>🏢 Empresa identificada no SPED Fiscal (registro 0000)</b><br>
                <b>CNPJ:</b> {cab['cnpj']} &nbsp;|&nbsp;
                <b>Nome:</b> {cab['nome']} &nbsp;|&nbsp;
                <b>UF:</b> {cab['uf'] or '—'} &nbsp;|&nbsp;
                <b>Período:</b> {fmt_dt(cab['dt_ini'])} a {fmt_dt(cab['dt_fin'])}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Download + resultado ──────────────────────────────────────────
    if st.session_state.txt_gerado is not None:
        st.success("✅ Arquivo gerado com sucesso!")
        st.download_button(
            label="⬇ Baixar arquivo TXT (Domínio Separador)",
            data=st.session_state.txt_gerado,
            file_name=st.session_state.nome_arquivo,
            mime="text/plain",
            use_container_width=True,
            type="primary",
        )

        if st.session_state.contadores:
            cnt = st.session_state.contadores
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("✅ Ativos (API)",        cnt["api_ativa"])
            m2.metric("❌ Baixados (SPED)",     cnt["baixada"])
            m3.metric("⛔ Inaptos (SPED)",      cnt["inapta"])
            m4.metric("⚠️ Suspensos (SPED)",   cnt["suspensa"])
            m5.metric("🌍 Exterior (SPED)",     cnt["exterior"])
            m6.metric("ℹ️ CPF/Sem API (SPED)", cnt["cpf_sped"] + cnt["sem_api"])

        if st.session_state.dados_tabela:
            import pandas as pd
            df = pd.DataFrame(st.session_state.dados_tabela)

            def highlight_row(row):
                s = str(row.get("Status", ""))
                if "ATIVA"    in s: return ["background-color:#d4edda"] * len(row)
                if "BAIXADA"  in s: return ["background-color:#f8d7da"] * len(row)
                if "INAPTA"   in s: return ["background-color:#f5c6cb"] * len(row)
                if "SUSPENSA" in s: return ["background-color:#fff3cd"] * len(row)
                if "Exterior" in s: return ["background-color:#cce5ff"] * len(row)
                return ["background-color:#e2e3e5"] * len(row)

            st.dataframe(
                df.style.apply(highlight_row, axis=1),
                use_container_width=True,
            )

            if "Papel" in df.columns:
                st.markdown("**Resumo por classificação:**")
                r1, r2, r3 = st.columns(3)
                r1.metric("🛒 Clientes",     len(df[df["Papel"].str.contains("Cliente",    na=False)]))
                r2.metric("🏭 Fornecedores", len(df[df["Papel"].str.contains("Fornecedor", na=False)]))
                r3.metric("🔄 Ambos",        len(df[df["Papel"].str.contains("Ambos",      na=False)]))

            for label, filtro in [
                ("❌ CNPJ(s) BAIXADO(s)",  "BAIXADA"),
                ("⛔ CNPJ(s) INAPTO(s)",   "INAPTA"),
                ("⚠️ CNPJ(s) SUSPENSO(s)", "SUSPENSA"),
            ]:
                lista = [r for r in st.session_state.dados_tabela
                         if filtro in r["Status"]]
                if lista:
                    with st.expander(f"{label} ({len(lista)}) — dados do SPED"):
                        st.dataframe(
                            pd.DataFrame(lista)[
                                ["COD_PART", "CNPJ/CPF", "Nome (SPED)", "Papel"]
                            ],
                            use_container_width=True,
                        )

            with st.expander("👁️ Prévia do arquivo gerado (primeiras 30 linhas)"):
                preview = "".join(
                    st.session_state.txt_gerado
                    .decode("latin-1", errors="replace")
                    .splitlines(True)[:30]
                )
                st.code(preview, language="text")

    # ── Log ───────────────────────────────────────────────────────────
    st.markdown("**Log de processamento**")
    log_texto = "\n".join(st.session_state.log)
    tem_erro  = any(str(l).startswith("ERRO") for l in st.session_state.log)
    cor_borda = "#D32F2F" if tem_erro else "#388E3C"
    st.markdown(
        f"""
        <div style="background:#FCFCFC; border:1px solid {cor_borda};
                    border-radius:6px; padding:14px;
                    font-family:Consolas,monospace; font-size:13px;
                    white-space:pre-wrap; max-height:340px;
                    overflow-y:auto; color:#1F1F1F;">
{log_texto}
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
