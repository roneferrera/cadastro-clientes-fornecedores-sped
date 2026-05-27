# ============================================================
# app_sped_dominio.py  –  SPED Fiscal → Domínio Sistemas
# Dependências: streamlit, requests, pandas
# pip install streamlit requests pandas
# ============================================================

import streamlit as st
import requests
import time
import re
from datetime import datetime

# ==============================
# VERSÃO
# ==============================
VERSAO = "V1.2"

# ==============================
# CONSTANTES
# ==============================
COD_PAIS_BRASIL = {"1058", "01058"}

SITUACAO_ATIVA = 2
SITUACOES_DESCRICAO = {
    1: "NULA",
    2: "ATIVA",
    3: "SUSPENSA",
    4: "INAPTA",
    8: "BAIXADA",
}
SITUACAO_ICONE = {
    1: "🚫",
    2: "✅",
    3: "⚠️",
    4: "⛔",
    8: "❌",
}

# ==============================
# TEMA TR  (idêntico ao gerador_rpa_txt)
# ==============================
def apply_tr_theme():
    st.markdown("""
        <style>
        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Arial', sans-serif;
            color: #444444;
        }
        h1, h2, h3 {
            color: #FF8000;
            font-weight: 700;
        }
        section[data-testid="stSidebar"] {
            background-color: #444444;
            color: #FFFFFF;
        }
        section[data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }
        .stButton > button {
            background-color: #FF8000;
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-weight: bold;
        }
        .stButton > button:hover {
            background-color: #D64001;
            color: #FFFFFF;
        }
        .stDownloadButton > button {
            background-color: #FF8000;
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-weight: bold;
        }
        .stDownloadButton > button:hover {
            background-color: #D64001;
            color: #FFFFFF;
        }
        hr {
            border-color: #FF8000;
        }
        [data-testid="metric-container"] {
            background-color: #E9E9E9;
            border-left: 4px solid #FF8000;
            border-radius: 4px;
            padding: 10px;
        }
        .instrucoes-box {
            background-color: #E9E9E9;
            border-left: 4px solid #FF8000;
            border-radius: 4px;
            padding: 16px 20px;
            margin: 12px 0;
            color: #444444;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        .instrucoes-box h4 {
            color: #FF8000;
            margin-top: 14px;
            margin-bottom: 6px;
        }
        .instrucoes-box h4:first-child {
            margin-top: 0;
        }
        </style>
    """, unsafe_allow_html=True)


# ==============================
# FUNÇÕES AUXILIARES
# ==============================

def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def formatar_data(data_str: str) -> str:
    if not data_str:
        return ""
    try:
        return datetime.strptime(data_str[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return ""


def is_exterior(cod_pais: str) -> bool:
    cod = (cod_pais or "").strip()
    if not cod:
        return False
    return cod not in COD_PAIS_BRASIL


def get_situacao_cadastral(dados_api: dict) -> tuple[int, str]:
    codigo = dados_api.get("situacao_cadastral")
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        codigo = None

    descricao = dados_api.get("descricao_situacao_cadastral", "") or ""

    if codigo is None:
        desc_up = descricao.upper()
        if   "ATIVA"    in desc_up: codigo = 2
        elif "BAIXADA"  in desc_up: codigo = 8
        elif "INAPTA"   in desc_up: codigo = 4
        elif "SUSPENSA" in desc_up: codigo = 3
        elif "NULA"     in desc_up: codigo = 1
        else:                       codigo = 0

    if not descricao:
        descricao = SITUACOES_DESCRICAO.get(codigo, "DESCONHECIDA")

    return codigo, descricao


def consultar_cnpj(cnpj: str) -> dict | None:
    cnpj_limpo = limpar_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        return None
    try:
        resp = requests.get(
            f"https://minhareceita.org/{cnpj_limpo}", timeout=15
        )
        if resp.status_code == 200:
            return resp.json()
        return None
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


def mapear_porte(porte: str | None) -> str:
    if not porte:
        return "N"
    p = porte.upper()
    if "MICRO"   in p or p == "ME":  return "M"
    if "PEQUENO" in p or p == "EPP": return "E"
    if "SIMPLES" in p:               return "M"
    return "N"


# ==============================
# LEITURA DO SPED FISCAL
# ==============================

def _split_sped(linha: str) -> list[str]:
    """
    Faz o split por pipe e remove os elementos vazios
    das extremidades (o SPED sempre começa e termina com |).
    """
    campos = linha.strip().split("|")
    if campos and campos[0] == "":
        campos = campos[1:]
    if campos and campos[-1] == "":
        campos = campos[:-1]
    return campos


def _get(campos: list[str], idx: int) -> str:
    """Retorna o campo pelo índice ou string vazia se não existir."""
    return campos[idx].strip() if idx < len(campos) else ""


def extrair_cabecalho_sped(conteudo: str, log: list) -> dict | None:
    """
    Extrai os dados da empresa do registro 0000 do SPED Fiscal.

    O layout do registro 0000 VARIA conforme a versão do leiaute
    (campo IND_SIT_ESP pode ou não estar presente).

    Versão COM IND_SIT_ESP (mais comum em versões antigas):
      |0000|COD_VER|TIPO_ESCRIT|IND_SIT_ESP|NUM_REC_ANTERIOR|
       DT_INI|DT_FIN|NOME|CNPJ|CPF|UF|IE|COD_MUN|IM|SUFRAMA|
       IND_PERFIL|IND_ATIV|
      → NOME=[7], CNPJ=[8]

    Versão SEM IND_SIT_ESP / SEM NUM_REC_ANTERIOR
    (ex: |0000|020|0|01032026|31032026|NOME|CNPJ|...|):
      → NOME=[5], CNPJ=[6]

    Estratégia robusta:
      1. Percorre todos os campos procurando o primeiro com 14 dígitos numéricos.
      2. O campo imediatamente anterior é o NOME.
      3. Registra qual índice foi encontrado para fins de log.
    """
    for linha in conteudo.splitlines():
        campos = _split_sped(linha)
        if not campos or campos[0] != "0000":
            continue

        log.append(
            f"Registro 0000 encontrado. "
            f"Total de campos (sem pipes extremos): {len(campos)}. "
            f"Conteúdo: {' | '.join(campos[:10])}{'...' if len(campos) > 10 else ''}"
        )

        # ── Busca robusta: procura o CNPJ (14 dígitos) em qualquer posição ──
        cnpj_encontrado = ""
        cnpj_idx        = -1
        nome_encontrado = ""

        for i, campo in enumerate(campos):
            limpo = re.sub(r"\D", "", campo)
            if len(limpo) == 14:
                cnpj_encontrado = limpo
                cnpj_idx        = i
                # O nome está no campo imediatamente anterior
                nome_encontrado = campos[i - 1].strip() if i > 0 else ""
                break

        if not cnpj_encontrado:
            log.append(
                "AVISO: CNPJ de 14 dígitos não localizado no registro 0000. "
                "Tentando mapeamento fixo (índice 6 e 7)..."
            )
            # Fallback: tenta índices 6 (CNPJ) e 5 (NOME) — layout sem IND_SIT_ESP
            cnpj_tentativa = limpar_cnpj(_get(campos, 6))
            if len(cnpj_tentativa) == 14:
                cnpj_encontrado = cnpj_tentativa
                cnpj_idx        = 6
                nome_encontrado = _get(campos, 5)
            else:
                # Tenta índice 8 (CNPJ) e 7 (NOME) — layout com IND_SIT_ESP
                cnpj_tentativa = limpar_cnpj(_get(campos, 8))
                if len(cnpj_tentativa) == 14:
                    cnpj_encontrado = cnpj_tentativa
                    cnpj_idx        = 8
                    nome_encontrado = _get(campos, 7)

        if not cnpj_encontrado:
            log.append(
                "ERRO: Não foi possível localizar o CNPJ da empresa "
                "no registro 0000 do SPED Fiscal. "
                "Verifique se o arquivo está correto."
            )
            return None

        # ── Extrai demais campos com base no índice do CNPJ ──────────────
        # DT_INI e DT_FIN ficam antes do NOME (2 posições antes do CNPJ - 1)
        # Layout: [...|DT_INI|DT_FIN|NOME|CNPJ|...]
        dt_ini = _get(campos, cnpj_idx - 3) if cnpj_idx >= 3 else ""
        dt_fin = _get(campos, cnpj_idx - 2) if cnpj_idx >= 2 else ""

        # UF, IE, COD_MUN ficam após o CNPJ
        # Layout: [...|CNPJ|CPF|UF|IE|COD_MUN|...]
        uf      = _get(campos, cnpj_idx + 2)
        ie      = _get(campos, cnpj_idx + 3)
        cod_mun = _get(campos, cnpj_idx + 4)

        # Formata datas DDMMAAAA → DD/MM/AAAA para exibição
        def fmt_dt_sped(s):
            s = s.strip()
            if len(s) == 8 and s.isdigit():
                return f"{s[0:2]}/{s[2:4]}/{s[4:8]}"
            return s

        log.append(
            f"Empresa identificada no SPED → "
            f"CNPJ: {cnpj_encontrado} | "
            f"Nome: {nome_encontrado} | "
            f"UF: {uf} | "
            f"Período: {fmt_dt_sped(dt_ini)} a {fmt_dt_sped(dt_fin)} "
            f"(CNPJ encontrado no índice [{cnpj_idx}])"
        )

        return {
            "cnpj":    cnpj_encontrado,
            "nome":    nome_encontrado,
            "dt_ini":  dt_ini,
            "dt_fin":  dt_fin,
            "uf":      uf,
            "ie":      ie,
            "cod_mun": cod_mun,
        }

    log.append("ERRO: Registro 0000 não encontrado no arquivo SPED Fiscal.")
    return None


def extrair_participantes_sped(conteudo: str) -> list[dict]:
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
                "cod_part": _get(campos, 1),
                "nome":     _get(campos, 2),
                "cod_pais": _get(campos, 3),
                "cnpj":     _get(campos, 4),
                "cpf":      _get(campos, 5),
                "ie":       _get(campos, 6),
                "cod_mun":  _get(campos, 7),
                "suframa":  _get(campos, 8),
                "end":      _get(campos, 9),
                "num":      _get(campos, 10),
                "compl":    _get(campos, 11),
                "bairro":   _get(campos, 12),
            })
        except Exception:
            continue
    return participantes


# ==============================
# GERAÇÃO DE LINHAS DOMÍNIO
# ==============================

def gerar_linha_0000(cnpj_empresa: str, nome_empresa: str) -> str:
    """
    Registro 0000 — Identificação da empresa.
    CNPJ e Nome extraídos automaticamente do registro 0000 do SPED Fiscal.
    """
    return f"0000|{limpar_cnpj(cnpj_empresa)}|\n"


def _campos_endereco(dados_api: dict, dados_sped: dict,
                     exterior: bool, usar_sped: bool) -> dict:
    if exterior:
        return {
            "logradouro":  _get_sped(dados_sped, "end"),
            "numero":      _get_sped(dados_sped, "num"),
            "complemento": _get_sped(dados_sped, "compl"),
            "bairro":      _get_sped(dados_sped, "bairro"),
            "cod_mun":     "EX",
            "uf":          "EX",
            "cod_pais":    _get_sped(dados_sped, "cod_pais"),
            "cep":         "",
        }
    elif usar_sped:
        return {
            "logradouro":  _get_sped(dados_sped, "end"),
            "numero":      _get_sped(dados_sped, "num"),
            "complemento": _get_sped(dados_sped, "compl"),
            "bairro":      _get_sped(dados_sped, "bairro"),
            "cod_mun":     _get_sped(dados_sped, "cod_mun"),
            "uf":          "",
            "cod_pais":    "",
            "cep":         "",
        }
    else:
        return {
            "logradouro":  dados_api.get("logradouro",
                           _get_sped(dados_sped, "end"))  or "",
            "numero":      dados_api.get("numero",
                           _get_sped(dados_sped, "num"))  or "",
            "complemento": dados_api.get("complemento",
                           _get_sped(dados_sped, "compl")) or "",
            "bairro":      dados_api.get("bairro",
                           _get_sped(dados_sped, "bairro")) or "",
            "cod_mun":     str(dados_api.get("codigo_municipio",
                           _get_sped(dados_sped, "cod_mun")) or ""),
            "uf":          dados_api.get("uf", "") or "",
            "cod_pais":    "",
            "cep":         re.sub(r"\D", "", dados_api.get("cep", "") or ""),
        }


def _get_sped(d: dict, k: str) -> str:
    """Helper para evitar None em campos do SPED."""
    return (d.get(k) or "").strip()


def _campos_comuns(dados_api: dict, dados_sped: dict,
                   exterior: bool, usar_sped: bool) -> dict:
    if exterior or usar_sped:
        return {
            "cnpj":     limpar_cnpj(_get_sped(dados_sped, "cnpj")) if not exterior else "",
            "razao":    _get_sped(dados_sped, "nome")[:150],
            "fantasia": "",
            "ie":       "" if exterior else _get_sped(dados_sped, "ie"),
            "suframa":  "" if exterior else _get_sped(dados_sped, "suframa"),
            "ddd1": "", "tel1": "", "ddd_fax": "", "fax": "",
            "data_cad": "",
            "nat_jur":  "7",
            "regime":   "N",
            "email":    "",
        }
    else:
        return {
            "cnpj":     limpar_cnpj(
                            dados_api.get("cnpj",
                            _get_sped(dados_sped, "cnpj"))),
            "razao":    (dados_api.get("razao_social",
                         _get_sped(dados_sped, "nome")) or "")[:150],
            "fantasia": (dados_api.get("nome_fantasia", "") or "")[:40],
            "ie":       _get_sped(dados_sped, "ie"),
            "suframa":  _get_sped(dados_sped, "suframa"),
            "ddd1":     (dados_api.get("ddd_telefone_1", "") or "")[:2],
            "tel1":     dados_api.get("telefone_1", "") or "",
            "ddd_fax":  (dados_api.get("ddd_fax", "") or "")[:2],
            "fax":      dados_api.get("fax", "") or "",
            "data_cad": formatar_data(
                            dados_api.get("data_inicio_atividade", "")),
            "nat_jur":  mapear_natureza_juridica(
                            dados_api.get("codigo_natureza_juridica")),
            "regime":   mapear_porte(dados_api.get("porte", "")),
            "email":    dados_api.get("email", "") or "",
        }


def gerar_linha_0010(dados_api, dados_sped, exterior, usar_sped) -> str:
    end = _campos_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _campos_comuns(dados_api, dados_sped, exterior, usar_sped)
    campos = [
        "0010", c["cnpj"], c["razao"], c["fantasia"],
        end["logradouro"], end["numero"], end["complemento"],
        end["bairro"], end["cod_mun"], end["uf"], end["cod_pais"], end["cep"],
        c["ie"], "", c["suframa"],
        c["ddd1"], c["tel1"], c["ddd_fax"], c["fax"], c["data_cad"],
        "", "", "N", c["nat_jur"], c["regime"],
        "N", "", "", "N", "", "N", "", "",
    ]
    return "|".join(str(x) for x in campos) + "|\n"


def gerar_linha_0020(dados_api, dados_sped, exterior, usar_sped) -> str:
    end = _campos_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _campos_comuns(dados_api, dados_sped, exterior, usar_sped)
    campos = [
        "0020", c["cnpj"], c["razao"], c["fantasia"],
        end["logradouro"], end["numero"], end["complemento"],
        end["bairro"], end["cod_mun"], end["uf"], end["cod_pais"], end["cep"],
        c["ie"], "", c["suframa"],
        c["ddd1"], c["tel1"], c["ddd_fax"], c["fax"], c["data_cad"],
        "", "", "N", c["nat_jur"], c["regime"],
        "N", "", "", c["email"],
        "N", "N", "", "",
    ]
    return "|".join(str(x) for x in campos) + "|\n"


# ==============================
# PROCESSAMENTO PRINCIPAL
# ==============================

def processar_sped(conteudo_sped: str, gerar_0010: bool,
                   gerar_0020: bool, delay_api: float,
                   log: list) -> tuple:
    """
    1. Lê o registro 0000 do SPED → CNPJ e Nome (busca robusta).
    2. Lê os registros 0150 → participantes.
    3. Consulta a API para cada CNPJ nacional ativo.
    4. Monta as linhas do arquivo Domínio.
    """

    # ── 1. Cabeçalho da empresa ───────────────────────────────────────
    cabecalho = extrair_cabecalho_sped(conteudo_sped, log)
    if cabecalho is None:
        return None, None, None, None

    cnpj_empresa = cabecalho["cnpj"]
    nome_empresa = cabecalho["nome"]

    if not cnpj_empresa:
        log.append(
            "ERRO: CNPJ da empresa não encontrado no registro 0000 do SPED."
        )
        return None, None, None, None

    # ── 2. Participantes ──────────────────────────────────────────────
    participantes = extrair_participantes_sped(conteudo_sped)
    total = len(participantes)

    if total == 0:
        log.append(
            "AVISO: Nenhum registro 0150 (participantes) encontrado no SPED. "
            "O arquivo Domínio será gerado apenas com o registro 0000."
        )
        # Gera arquivo só com 0000 mesmo sem participantes
        linhas_saida = [gerar_linha_0000(cnpj_empresa, nome_empresa)]
        log.append(
            f"Arquivo gerado com 0 participante(s). "
            f"Empresa: {nome_empresa} | CNPJ: {cnpj_empresa}"
        )
        return linhas_saida, [], {
            "api_ativa": 0, "baixada": 0, "inapta": 0,
            "suspensa":  0, "nula":    0, "sem_api": 0,
            "cpf_sped":  0, "exterior": 0,
        }, cabecalho

    log.append(f"{total} participante(s) encontrado(s) no registro 0150.")

    # ── 3. Inicializa estruturas ──────────────────────────────────────
    linhas_saida = [gerar_linha_0000(cnpj_empresa, nome_empresa)]
    dados_tabela = []
    contadores   = {
        "api_ativa": 0, "baixada": 0, "inapta": 0,
        "suspensa":  0, "nula":    0, "sem_api": 0,
        "cpf_sped":  0, "exterior": 0,
    }

    progresso = st.progress(0, text="Iniciando...")
    log_area  = st.empty()

    # ── 4. Processa cada participante ─────────────────────────────────
    for idx, part in enumerate(participantes):
        pct      = int((idx + 1) / total * 100)
        cnpj_raw = limpar_cnpj(part["cnpj"])
        exterior = is_exterior(part["cod_pais"])

        progresso.progress(
            pct,
            text=(
                f"Processando {idx+1}/{total}: "
                f"{'🌍 EXTERIOR' if exterior else cnpj_raw or 'CPF'}"
            ),
        )

        dados_api     = {}
        usar_sped     = False
        situacao_desc = ""
        status_label  = ""
        razao_final   = part["nome"]

        if exterior:
            usar_sped    = True
            status_label = f"🌍 Exterior (COD_PAIS={part['cod_pais']})"
            contadores["exterior"] += 1
            log.append(
                f"[{idx+1:03d}/{total}] {part['nome'][:40]} | {status_label}"
            )

        elif len(cnpj_raw) == 14:
            dados_api_bruto = consultar_cnpj(cnpj_raw)
            time.sleep(delay_api)

            if dados_api_bruto is None:
                usar_sped    = True
                status_label = (
                    f"⚠️ {cnpj_raw} — sem resposta da API. "
                    "Usando dados do SPED."
                )
                contadores["sem_api"] += 1
                log.append(
                    f"[{idx+1:03d}/{total}] {cnpj_raw} | {status_label}"
                )
            else:
                situacao_cod, situacao_desc = get_situacao_cadastral(
                    dados_api_bruto
                )
                icone = SITUACAO_ICONE.get(situacao_cod, "❓")

                if situacao_cod == SITUACAO_ATIVA:
                    dados_api    = dados_api_bruto
                    usar_sped    = False
                    razao_final  = dados_api.get("razao_social", part["nome"])
                    status_label = (
                        f"✅ {cnpj_raw} — ATIVA. "
                        "Dados da Receita Federal."
                    )
                    contadores["api_ativa"] += 1
                else:
                    usar_sped    = True
                    status_label = (
                        f"{icone} {cnpj_raw} — {situacao_desc} "
                        f"(sit. {situacao_cod}). Usando dados do SPED."
                    )
                    if   situacao_cod == 8: contadores["baixada"]  += 1
                    elif situacao_cod == 4: contadores["inapta"]   += 1
                    elif situacao_cod == 3: contadores["suspensa"]  += 1
                    elif situacao_cod == 1: contadores["nula"]      += 1
                    else:                  contadores["sem_api"]   += 1

                log.append(
                    f"[{idx+1:03d}/{total}] {cnpj_raw} | "
                    f"{razao_final[:40]} | {status_label}"
                )
        else:
            usar_sped    = True
            status_label = (
                f"ℹ️ {cnpj_raw or limpar_cnpj(part['cpf'])} — "
                "CPF/sem CNPJ. Usando dados do SPED."
            )
            contadores["cpf_sped"] += 1
            log.append(
                f"[{idx+1:03d}/{total}] {part['nome'][:40]} | {status_label}"
            )

        if gerar_0010:
            linhas_saida.append(
                gerar_linha_0010(dados_api, part, exterior, usar_sped)
            )
        if gerar_0020:
            linhas_saida.append(
                gerar_linha_0020(dados_api, part, exterior, usar_sped)
            )

        dados_tabela.append({
            "COD_PART":           part["cod_part"],
            "CNPJ/CPF":           cnpj_raw or limpar_cnpj(part["cpf"]),
            "Nome (SPED)":        part["nome"],
            "Razão Social (API)": dados_api.get("razao_social", ""),
            "Situação Receita":   situacao_desc or "—",
            "COD_PAIS":           part["cod_pais"],
            "Fonte":              "SPED" if usar_sped else "Receita Federal",
            "Status":             status_label,
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

    # ── Banner principal ──────────────────────────────────────────────
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
                O CNPJ e o nome da empresa são lidos automaticamente
                do registro <strong>0000</strong> do SPED.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Configurações")

        tipo_registro = st.radio(
            "Gerar registros como:",
            options=["Clientes (0010)", "Fornecedores (0020)", "Ambos (0010 e 0020)"],
            index=2,
        )
        delay_api = st.slider(
            "Intervalo entre consultas (s)",
            min_value=0.5, max_value=5.0, value=1.0, step=0.5,
            help="Evita bloqueio por excesso de requisições na API pública.",
        )

        st.markdown("---")
        st.markdown("### 📋 Legenda — Situação Cadastral")
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
    with st.expander(
        "📖 **Instruções de Uso** — clique para expandir", expanded=False
    ):
        st.markdown(
            """
            <div class="instrucoes-box">

            <h4>🔹 Passo 1 — Exportar o SPED Fiscal</h4>
            <p>Exporte o arquivo <b>SPED Fiscal (.txt)</b> do sistema de origem.
            O arquivo deve conter o registro <b>0000</b> (identificação da empresa)
            e os registros <b>0150</b> (cadastro de participantes).</p>

            <h4>🔹 Passo 2 — Selecionar o tipo de registro</h4>
            <p>Na barra lateral, escolha se deseja gerar registros de
            <b>Clientes (0010)</b>, <b>Fornecedores (0020)</b> ou <b>Ambos</b>.</p>

            <h4>🔹 Passo 3 — Fazer upload e gerar o arquivo</h4>
            <ol>
                <li>Clique em <b>Browse files</b> e selecione o SPED Fiscal (.txt).</li>
                <li>Clique em <b>▶ Gerar arquivo Domínio</b>.</li>
                <li>Aguarde o processamento e clique em <b>⬇ Baixar arquivo TXT</b>.</li>
            </ol>

            <h4>🔹 Passo 4 — Importar no Domínio Sistemas</h4>
            <p>No Domínio, acesse <b>Utilitários → Importação → Importação Padrão →
            Leiaute Domínio Sistemas com Separador</b> e selecione o arquivo gerado.</p>

            <hr>

            <h4>⚠ Observações importantes</h4>
            <ul>
                <li>O <b>CNPJ e o nome da empresa</b> são lidos automaticamente do
                    registro <b>0000</b> do SPED Fiscal — não é necessário
                    preenchimento manual.</li>
                <li>O sistema detecta automaticamente o layout do registro 0000
                    (com ou sem campo <code>IND_SIT_ESP</code>).</li>
                <li><b>CNPJ Ativo</b>: dados atualizados da
                    <b>Receita Federal</b> via API pública.</li>
                <li><b>CNPJ Baixado / Inapto / Suspenso / Nulo</b>:
                    dados do <b>SPED Fiscal</b>.</li>
                <li><b>Participantes do Exterior</b> (COD_PAIS ≠ 1058):
                    dados do <b>SPED Fiscal</b>;
                    COD_MUN e UF preenchidos como <code>EX</code>.</li>
                <li><b>CPF / sem inscrição</b>: dados do <b>SPED Fiscal</b>,
                    sem consulta à API.</li>
                <li>O separador utilizado é <code>|</code> (pipe),
                    conforme leiaute Domínio Sistemas.</li>
                <li>API utilizada: <b>minhareceita.org</b>
                    (gratuita, sem autenticação).</li>
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
        help=(
            "Selecione o arquivo de texto do SPED Fiscal. "
            "O CNPJ da empresa será lido automaticamente do registro 0000."
        ),
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
            st.session_state[k] = v if k == "log" else (
                ["Campos limpos."] if k == "log" else v
            )
        st.session_state.log = ["Campos limpos."]
        st.rerun()

    # ── Processamento ─────────────────────────────────────────────────
    if gerar and arquivo_sped is not None:
        for k in ["log", "txt_gerado", "dados_tabela",
                  "contadores", "cabecalho"]:
            st.session_state[k] = (
                ["Iniciando geração do arquivo..."] if k == "log" else None
            )

        conteudo_sped = arquivo_sped.read().decode("latin-1", errors="replace")
        gerar_0010    = "0010" in tipo_registro or "Ambos" in tipo_registro
        gerar_0020    = "0020" in tipo_registro or "Ambos" in tipo_registro

        linhas, dados_tabela, contadores, cabecalho = processar_sped(
            conteudo_sped, gerar_0010, gerar_0020,
            delay_api, st.session_state.log,
        )

        tem_erro = any(
            str(l).startswith("ERRO") for l in st.session_state.log
        )

        if linhas and not tem_erro:
            conteudo_saida = "".join(linhas)
            st.session_state.txt_gerado = conteudo_saida.encode(
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

    # ── Card: empresa identificada no SPED ───────────────────────────
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
                        border-radius:4px; padding:12px 18px;
                        margin-bottom:16px;
                        font-family:'Segoe UI',Arial,sans-serif;
                        color:#444;">
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

        # Métricas
        if st.session_state.contadores:
            cnt = st.session_state.contadores
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("✅ Ativos (API)",        cnt["api_ativa"])
            m2.metric("❌ Baixados (SPED)",     cnt["baixada"])
            m3.metric("⛔ Inaptos (SPED)",      cnt["inapta"])
            m4.metric("⚠️ Suspensos (SPED)",   cnt["suspensa"])
            m5.metric("🌍 Exterior (SPED)",     cnt["exterior"])
            m6.metric("ℹ️ CPF/Sem API (SPED)", cnt["cpf_sped"] + cnt["sem_api"])

        # Tabela de resultado
        if st.session_state.dados_tabela:
            import pandas as pd

            df = pd.DataFrame(st.session_state.dados_tabela)

            def highlight_situacao(row):
                s = str(row.get("Status", ""))
                if "ATIVA"    in s: return ["background-color:#d4edda"] * len(row)
                if "BAIXADA"  in s: return ["background-color:#f8d7da"] * len(row)
                if "INAPTA"   in s: return ["background-color:#f5c6cb"] * len(row)
                if "SUSPENSA" in s: return ["background-color:#fff3cd"] * len(row)
                if "Exterior" in s: return ["background-color:#cce5ff"] * len(row)
                return ["background-color:#e2e3e5"] * len(row)

            st.dataframe(
                df.style.apply(highlight_situacao, axis=1),
                use_container_width=True,
            )

            # Expanders de alerta
            baixados  = [r for r in st.session_state.dados_tabela
                         if "BAIXADA"  in r["Status"]]
            inaptos   = [r for r in st.session_state.dados_tabela
                         if "INAPTA"   in r["Status"]]
            suspensos = [r for r in st.session_state.dados_tabela
                         if "SUSPENSA" in r["Status"]]

            if baixados:
                with st.expander(
                    f"❌ {len(baixados)} CNPJ(s) BAIXADO(s) "
                    "— dados do SPED utilizados"
                ):
                    st.dataframe(
                        pd.DataFrame(baixados)[
                            ["COD_PART", "CNPJ/CPF", "Nome (SPED)"]
                        ],
                        use_container_width=True,
                    )
            if inaptos:
                with st.expander(
                    f"⛔ {len(inaptos)} CNPJ(s) INAPTO(s) "
                    "— dados do SPED utilizados"
                ):
                    st.dataframe(
                        pd.DataFrame(inaptos)[
                            ["COD_PART", "CNPJ/CPF", "Nome (SPED)"]
                        ],
                        use_container_width=True,
                    )
            if suspensos:
                with st.expander(
                    f"⚠️ {len(suspensos)} CNPJ(s) SUSPENSO(s) "
                    "— dados do SPED utilizados"
                ):
                    st.dataframe(
                        pd.DataFrame(suspensos)[
                            ["COD_PART", "CNPJ/CPF", "Nome (SPED)"]
                        ],
                        use_container_width=True,
                    )

            with st.expander(
                "👁️ Prévia do arquivo gerado (primeiras 30 linhas)"
            ):
                preview = "".join(
                    st.session_state.txt_gerado
                    .decode("latin-1", errors="replace")
                    .splitlines(True)[:30]
                )
                st.code(preview, language="text")

    # ── Log de processamento ──────────────────────────────────────────
    st.markdown("**Log de processamento**")
    log_texto = "\n".join(st.session_state.log)
    tem_erro  = any(
        str(l).startswith("ERRO") for l in st.session_state.log
    )
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
