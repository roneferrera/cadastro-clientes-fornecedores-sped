# ============================================================
# app_sped_dominio.py  –  SPED Fiscal → Domínio Sistemas V2.2
# Dependências: streamlit, requests, pandas
# pip install streamlit requests pandas
# ============================================================

import streamlit as st
import requests
import time
import re
from datetime import datetime

VERSAO = "V2.2"
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
    cod = dados_api.get("codigo_municipio_ibge")
    if cod is None:
        return ""
    cod_str = str(cod).strip()
    return cod_str if cod_str.isdigit() else ""

def sanitizar_numero_endereco(valor: str) -> str:
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
                "cod_mun":  _get(campos,  7),
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
    return f"0000|{limpar_cnpj(cnpj_empresa)}|\n"


def _montar_endereco(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> dict:
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
        return {
            "logradouro":  _gs(dados_sped, "end"),
            "numero":      sanitizar_numero_endereco(_gs(dados_sped, "num")),
            "complemento": _gs(dados_sped, "compl"),
            "bairro":      _gs(dados_sped, "bairro"),
            "cod_mun":     _gs(dados_sped, "cod_mun"),
            "uf":          "",
            "cod_pais":    "",
            "cep":         "",
        }

    else:
        cod_ibge_api = extrair_cod_ibge(dados_api)
        num_api      = dados_api.get("numero", _gs(dados_sped, "num")) or ""
        cep_api      = re.sub(r"\D", "", dados_api.get("cep", "") or "")
        return {
            "logradouro":  (dados_api.get("logradouro",  _gs(dados_sped, "end"))  or ""),
            "numero":      sanitizar_numero_endereco(str(num_api)),
            "complemento": (dados_api.get("complemento", _gs(dados_sped, "compl")) or ""),
            "bairro":      (dados_api.get("bairro",      _gs(dados_sped, "bairro")) or ""),
            "cod_mun":     cod_ibge_api,
            "uf":          (dados_api.get("uf", "") or ""),
            "cod_pais":    "",
            "cep":         cep_api,
        }


def _montar_comuns(dados_api: dict, dados_sped: dict,
                   exterior: bool, usar_sped: bool) -> dict:
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
        "inscricao": inscricao,
        "razao":     razao,
        "apelido":   apelido,
        "ie":        ie,
        "im":        "",
        "suframa":   suframa,
        "ddd":       ddd,
        "telefone":  telefone,
        "fax":       fax,
        "data_cad":  "",
        "nat_jur":   nat_jur,
        "regime":    regime,
        "email":     email,
    }


def gerar_linha_0010(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> str:
    end = _montar_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _montar_comuns(dados_api, dados_sped, exterior, usar_sped)

    campos = [
        "0010",
        c["inscricao"],
        c["razao"],
        c["apelido"],
        end["logradouro"],
        end["numero"],
        end["complemento"],
        end["bairro"],
        end["cod_mun"],
        end["uf"],
        end["cod_pais"],
        end["cep"],
        c["ie"],
        c["im"],
        c["suframa"],
        c["ddd"],
        c["telefone"],
        c["fax"],
        c["data_cad"],
        "",
        "",
        "N",
        c["nat_jur"],
        c["regime"],
        "N",
        "",
        "",
        "N",
        "",
        "N",
        "",
        "",
    ]
    return "|".join(str(x) for x in campos) + "|\n"


def gerar_linha_0020(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> str:
    end = _montar_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _montar_comuns(dados_api, dados_sped, exterior, usar_sped)

    campos = [
        "0020",
        c["inscricao"],
        c["razao"],
        c["apelido"],
        end["logradouro"],
        end["numero"],
        end["complemento"],
        end["bairro"],
        end["cod_mun"],
        end["uf"],
        end["cod_pais"],
        end["cep"],
        c["ie"],
        c["im"],
        c["suframa"],
        c["ddd"],
        c["telefone"],
        c["fax"],
        c["data_cad"],
        "",
        "",
        "N",
        c["nat_jur"],
        c["regime"],
        "N",
        "",
        "",
        "",
        c["email"],
        "N",
        "N",
        "",
        "",
    ]
    return "|".join(str(x) for x in campos) + "|\n"


# ==============================
# PROCESSAMENTO — MODO SPED
# ==============================
def processar_sped(conteudo_sped: str, modo: str,
                   delay_api: float, log: list) -> tuple:
    """
    modo = "auto"         → classifica por C100/D100
         = "clientes"     → gera só 0010 para todos
         = "fornecedores" → gera só 0020 para todos
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
        else:  # fornecedores
            e_cliente = False; e_fornecedor = True;  papel = "🏭 Fornecedor"

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
# PROCESSAMENTO — MODO CNPJ AVULSO
# ==============================
def _sped_vazio() -> dict:
    """Retorna um dict de participante SPED com todos os campos vazios."""
    return {
        "cod_part": "", "nome": "", "cod_pais": "1058",
        "cnpj": "", "cpf": "", "ie": "", "cod_mun": "",
        "suframa": "", "end": "", "num": "", "compl": "", "bairro": "",
    }


def processar_cnpjs_avulsos(
    lista_cnpjs: list[str],
    cnpj_empresa: str,
    modo: str,
    delay_api: float,
    log: list,
) -> tuple:
    """
    Consulta cada CNPJ da lista na Receita Federal e gera o arquivo
    Domínio no mesmo leiaute de _processar_sped_.

    modo = "clientes"     → gera só 0010
         = "fornecedores" → gera só 0020
         = "ambos"        → gera 0010 e 0020
    """
    total        = len(lista_cnpjs)
    linhas_saida = [gerar_linha_0000(cnpj_empresa)]
    dados_tabela = []
    contadores   = {
        "api_ativa": 0, "baixada": 0, "inapta": 0,
        "suspensa":  0, "nula":    0, "sem_api": 0,
        "cpf_sped":  0, "exterior": 0,
    }

    e_cliente    = modo in ("clientes",    "ambos")
    e_fornecedor = modo in ("fornecedores","ambos")
    papel = {
        "clientes":     "🛒 Cliente",
        "fornecedores": "🏭 Fornecedor",
        "ambos":        "🔄 Ambos",
    }.get(modo, "🔄 Ambos")

    progresso = st.progress(0, text="Iniciando...")
    log_area  = st.empty()

    for idx, cnpj_raw in enumerate(lista_cnpjs):
        pct = int((idx + 1) / total * 100)
        progresso.progress(pct, text=f"Consultando {idx+1}/{total}: {cnpj_raw}")

        dados_api  = {}
        usar_sped  = False          # aqui "sped" = fallback vazio
        part       = _sped_vazio()
        part["cnpj"] = cnpj_raw     # garante que a inscrição seja preenchida

        situacao_desc = ""
        status_label  = ""
        razao_final   = ""
        cod_mun_log   = ""

        dados_api_bruto = consultar_cnpj(cnpj_raw)
        time.sleep(delay_api)

        if dados_api_bruto is None:
            # Sem resposta: grava só o CNPJ, campos em branco
            usar_sped    = True
            status_label = f"⚠️ {cnpj_raw} — sem resposta da API. Campos em branco."
            razao_final  = cnpj_raw
            contadores["sem_api"] += 1

        else:
            situacao_cod, situacao_desc = get_situacao_cadastral(dados_api_bruto)
            icone = SITUACAO_ICONE.get(situacao_cod, "❓")

            if situacao_cod == SITUACAO_ATIVA:
                dados_api   = dados_api_bruto
                usar_sped   = False
                razao_final = dados_api.get("razao_social", cnpj_raw)
                cod_mun_log = extrair_cod_ibge(dados_api)
                status_label = (
                    f"✅ {cnpj_raw} — ATIVA | "
                    f"Município IBGE (API): {cod_mun_log}"
                )
                contadores["api_ativa"] += 1
            else:
                # Não ativo: grava CNPJ + dados parciais da API mesmo assim
                dados_api   = dados_api_bruto
                usar_sped   = False          # usa o que a API retornou
                razao_final = dados_api.get("razao_social", cnpj_raw)
                cod_mun_log = extrair_cod_ibge(dados_api)
                status_label = (
                    f"{icone} {cnpj_raw} — {situacao_desc} "
                    f"(sit. {situacao_cod}). Dados da API utilizados."
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

        if e_cliente:
            linhas_saida.append(
                gerar_linha_0010(dados_api, part, False, usar_sped)
            )
        if e_fornecedor:
            linhas_saida.append(
                gerar_linha_0020(dados_api, part, False, usar_sped)
            )

        dados_tabela.append({
            "COD_PART":             f"{idx+1:04d}",
            "CNPJ/CPF":             cnpj_raw,
            "Nome (SPED)":          "—",
            "Razão Social (API)":   dados_api.get("razao_social", ""),
            "Município IBGE (c09)": cod_mun_log,
            "Apelido":              razao_final[:40],
            "Papel":                papel,
            "Situação Receita":     situacao_desc or "—",
            "COD_PAIS":             "1058",
            "Fonte":                "Receita Federal" if not usar_sped else "Sem API",
            "Status":               status_label,
        })

        log_area.text_area(
            "Log de processamento",
            value="\n".join(log[-20:]),
            height=200,
        )

    progresso.progress(100, text="✅ Concluído!")
    log.append(
        f"Arquivo gerado com {len(linhas_saida) - 1} registro(s) | "
        f"Ativos(API)={contadores['api_ativa']} | "
        f"Baixados={contadores['baixada']} | "
        f"Inaptos={contadores['inapta']} | "
        f"Suspensos={contadores['suspensa']} | "
        f"SemAPI={contadores['sem_api']}"
    )

    cabecalho_fake = {
        "cnpj": cnpj_empresa, "nome": "Entrada manual de CNPJs",
        "dt_ini": "", "dt_fin": "", "uf": "", "ie": "", "cod_mun": "",
    }
    return linhas_saida, dados_tabela, contadores, cabecalho_fake


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
                Faça o upload do SPED Fiscal <b>ou</b> cole CNPJs avulsos
                e clique em <strong>▶ Gerar arquivo Domínio</strong>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Configurações")

        modo_sped = st.radio(
            "Classificação (modo SPED):",
            options=[
                "🔍 Automático (por C100/D100)",
                "🛒 Somente Clientes (0010)",
                "🏭 Somente Fornecedores (0020)",
            ],
            index=0,
        )

        st.markdown("---")

        modo_avulso = st.radio(
            "Classificação (modo CNPJs avulsos):",
            options=[
                "🛒 Somente Clientes (0010)",
                "🏭 Somente Fornecedores (0020)",
                "🔄 Ambos (0010 e 0020)",
            ],
            index=2,
        )

        st.markdown("---")

        delay_api = st.slider(
            "Intervalo entre consultas (s)",
            min_value=0.5, max_value=5.0, value=1.0, step=0.5,
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

            <h4>🔹 Modo A — SPED Fiscal</h4>
            <p>Exporte o <b>SPED Fiscal (.txt)</b> do sistema de origem (registros
            <b>0000</b> e <b>0150</b> obrigatórios) e faça o upload na aba
            <b>📂 SPED Fiscal</b>.</p>

            <h4>🔹 Modo B — CNPJs Avulsos</h4>
            <p>Na aba <b>🔢 CNPJs Avulsos</b>, informe o <b>CNPJ da sua empresa</b>
            (preenchimento obrigatório do registro 0000) e cole os CNPJs a importar
            — um por linha, com ou sem pontuação. Os dados serão buscados
            diretamente na <b>Receita Federal</b>.</p>

            <h4>🔹 Passo final — Importar no Domínio Sistemas</h4>
            <p><b>Utilitários → Importação → Importação Padrão →
            Leiaute Domínio Sistemas com Separador</b>.</p>

            <hr>

            <h4>⚠ Observações (V2.2)</h4>
            <ul>
                <li><b>Campo 06 — Número do endereço</b>: valores não numéricos
                    são substituídos por <b>vazio</b>.</li>
                <li><b>Campo 09 — Município IBGE</b>: sempre vindo da API
                    quando o CNPJ é encontrado.</li>
                <li><b>Campo 19 — Data do cadastro</b>: sempre <b>vazia</b>.</li>
                <li>No modo avulso, CNPJs não encontrados na API recebem
                    apenas a inscrição preenchida e demais campos em branco.</li>
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

    # ── Abas ─────────────────────────────────────────────────────────
    aba_sped, aba_avulso = st.tabs(["📂 SPED Fiscal", "🔢 CNPJs Avulsos"])

    # ════════════════════════════════════════════════════════════════
    # ABA 1 — SPED FISCAL
    # ════════════════════════════════════════════════════════════════
    with aba_sped:
        arquivo_sped = st.file_uploader(
            "Arquivo SPED Fiscal (.txt)",
            type=["txt"],
            help="CNPJ da empresa e classificação detectados automaticamente.",
            key="uploader_sped",
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            gerar_sped = st.button(
                "▶ Gerar arquivo Domínio",
                disabled=(arquivo_sped is None),
                use_container_width=True,
                type="primary",
                key="btn_gerar_sped",
            )
        with col2:
            limpar_sped = st.button(
                "🗑 Limpar",
                use_container_width=True,
                key="btn_limpar_sped",
            )

        if limpar_sped:
            for k, v in defaults.items():
                st.session_state[k] = v
            st.session_state.log = ["Campos limpos."]
            st.rerun()

        if gerar_sped and arquivo_sped is not None:
            for k in defaults:
                st.session_state[k] = (
                    ["Iniciando geração do arquivo..."] if k == "log" else None
                )

            conteudo_sped = arquivo_sped.read().decode("latin-1", errors="replace")
            modo_map = {
                "🔍 Automático (por C100/D100)":  "auto",
                "🛒 Somente Clientes (0010)":      "clientes",
                "🏭 Somente Fornecedores (0020)":  "fornecedores",
            }
            modo_selecionado = modo_map.get(modo_sped, "auto")

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

    # ════════════════════════════════════════════════════════════════
    # ABA 2 — CNPJs AVULSOS
    # ════════════════════════════════════════════════════════════════
    with aba_avulso:
        st.markdown(
            """
            <div style="background:#FFF8F0; border-left:4px solid #FF8000;
                        border-radius:4px; padding:10px 16px; margin-bottom:14px;
                        font-family:'Segoe UI',Arial,sans-serif; color:#444;">
                Cole os CNPJs abaixo — <b>um por linha</b>, com ou sem pontuação.
                Os dados serão buscados diretamente na
                <b>Receita Federal (minhareceita.org)</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        cnpj_empresa_avulso = st.text_input(
            "🏢 CNPJ da sua empresa (obrigatório — preenche o registro 0000)",
            placeholder="00.000.000/0000-00  ou  00000000000000",
            key="cnpj_empresa_avulso",
        )

        texto_cnpjs = st.text_area(
            "📋 CNPJs a importar (um por linha)",
            height=220,
            placeholder=(
                "11.222.333/0001-81\n"
                "44555666000177\n"
                "77.888.999/0001-00\n"
                "..."
            ),
            key="textarea_cnpjs",
        )

        # Pré-visualização do que será processado
        cnpjs_parsed = []
        avisos_parse = []
        if texto_cnpjs.strip():
            vistos = set()
            for i, linha in enumerate(texto_cnpjs.splitlines(), 1):
                c = limpar_cnpj(linha)
                if not c:
                    continue
                if len(c) != 14:
                    avisos_parse.append(
                        f"Linha {i}: '{linha.strip()}' → {len(c)} dígito(s) — ignorado."
                    )
                    continue
                if c in vistos:
                    avisos_parse.append(f"Linha {i}: {c} — duplicado, ignorado.")
                    continue
                vistos.add(c)
                cnpjs_parsed.append(c)

            st.info(
                f"**{len(cnpjs_parsed)}** CNPJ(s) válido(s) reconhecido(s)"
                + (f" · {len(avisos_parse)} ignorado(s)" if avisos_parse else "")
            )
            if avisos_parse:
                with st.expander("⚠️ Linhas ignoradas"):
                    for a in avisos_parse:
                        st.caption(a)

        col3, col4 = st.columns([1, 1])
        with col3:
            cnpj_emp_limpo = limpar_cnpj(cnpj_empresa_avulso)
            gerar_avulso = st.button(
                "▶ Gerar arquivo Domínio",
                disabled=(
                    len(cnpjs_parsed) == 0
                    or len(cnpj_emp_limpo) != 14
                ),
                use_container_width=True,
                type="primary",
                key="btn_gerar_avulso",
            )
        with col4:
            limpar_avulso = st.button(
                "🗑 Limpar",
                use_container_width=True,
                key="btn_limpar_avulso",
            )

        # Mensagem de validação do CNPJ empresa
        if cnpj_empresa_avulso.strip() and len(cnpj_emp_limpo) != 14:
            st.warning("⚠️ CNPJ da empresa inválido — deve ter 14 dígitos.")

        if limpar_avulso:
            for k, v in defaults.items():
                st.session_state[k] = v
            st.session_state.log = ["Campos limpos."]
            st.rerun()

        if gerar_avulso and cnpjs_parsed and len(cnpj_emp_limpo) == 14:
            for k in defaults:
                st.session_state[k] = (
                    ["Iniciando geração (modo CNPJs avulsos)..."]
                    if k == "log" else None
                )

            modo_avulso_map = {
                "🛒 Somente Clientes (0010)":      "clientes",
                "🏭 Somente Fornecedores (0020)":  "fornecedores",
                "🔄 Ambos (0010 e 0020)":          "ambos",
            }
            modo_av_sel = modo_avulso_map.get(modo_avulso, "ambos")

            linhas, dados_tabela, contadores, cabecalho = processar_cnpjs_avulsos(
                cnpjs_parsed,
                cnpj_emp_limpo,
                modo_av_sel,
                delay_api,
                st.session_state.log,
            )

            st.session_state.txt_gerado = "".join(linhas).encode(
                "latin-1", errors="replace"
            )
            st.session_state.nome_arquivo = (
                f"dominio_avulso_{cnpj_emp_limpo}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            st.session_state.dados_tabela = dados_tabela
            st.session_state.contadores   = contadores
            st.session_state.cabecalho    = cabecalho

            st.rerun()

    # ════════════════════════════════════════════════════════════════
    # RESULTADOS (compartilhados entre as abas)
    # ════════════════════════════════════════════════════════════════
    st.markdown("---")

    # ── Card empresa ──────────────────────────────────────────────────
    if st.session_state.cabecalho:
        cab = st.session_state.cabecalho
        def fmt_dt(s):
            s = (s or "").strip()
            if len(s) == 8 and s.isdigit():
                return f"{s[0:2]}/{s[2:4]}/{s[4:8]}"
            return s or "—"
        periodo = (
            f"{fmt_dt(cab['dt_ini'])} a {fmt_dt(cab['dt_fin'])}"
            if cab.get("dt_ini") else "—"
        )
        st.markdown(
            f"""
            <div style="background:#FFF8F0; border-left:4px solid #FF8000;
                        border-radius:4px; padding:12px 18px; margin-bottom:16px;
                        font-family:'Segoe UI',Arial,sans-serif; color:#444;">
                <b>🏢 Empresa identificada</b><br>
                <b>CNPJ:</b> {cab['cnpj']} &nbsp;|&nbsp;
                <b>Nome:</b> {cab['nome']} &nbsp;|&nbsp;
                <b>UF:</b> {cab['uf'] or '—'} &nbsp;|&nbsp;
                <b>Período:</b> {periodo}
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
            m2.metric("❌ Baixados",            cnt["baixada"])
            m3.metric("⛔ Inaptos",             cnt["inapta"])
            m4.metric("⚠️ Suspensos",          cnt["suspensa"])
            m5.metric("🌍 Exterior (SPED)",     cnt["exterior"])
            m6.metric("ℹ️ Sem API / CPF",      cnt["cpf_sped"] + cnt["sem_api"])

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
                    with st.expander(f"{label} ({len(lista)}) — dados da API"):
                        st.dataframe(
                            pd.DataFrame(lista)[
                                ["COD_PART", "CNPJ/CPF", "Razão Social (API)", "Papel"]
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
