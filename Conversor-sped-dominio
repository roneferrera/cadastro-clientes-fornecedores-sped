# ============================================================
# app.py  –  SPED Fiscal → Domínio Sistemas (Leiaute com Separador)
# Dependências: streamlit, requests, pandas
# pip install streamlit requests pandas
# ============================================================

import streamlit as st
import requests
import time
import re
from datetime import datetime

# ─────────────────────────────────────────────
# Configuração da página
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SPED → Domínio Sistemas",
    page_icon="🏢",
    layout="wide",
)

st.title("🏢 SPED Fiscal → Leiaute Domínio Sistemas com Separador")
st.markdown(
    "Lê o arquivo SPED Fiscal, extrai participantes (registro **0150**), "
    "consulta na **Receita Federal** via API pública e gera o arquivo no "
    "**Leiaute Domínio Sistemas com Separador** (`|`). \n\n"
    "- 🌍 **Exterior** → dados do SPED \n"
    "- ❌ **CNPJ Baixado / Inapto / Suspenso / Nulo** → dados do SPED + alerta \n"
    "- ✅ **CNPJ Ativo** → dados atualizados da Receita Federal"
)

# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────
COD_PAIS_BRASIL = {"1058", "01058"}

# Situações cadastrais da Receita Federal
SITUACAO_ATIVA = 2
SITUACOES_DESCRICAO = {
    1: "NULA",
    2: "ATIVA",
    3: "SUSPENSA",
    4: "INAPTA",
    8: "BAIXADA",
}

# Ícone por situação
SITUACAO_ICONE = {
    1: "🚫",   # Nula
    2: "✅",   # Ativa
    3: "⚠️",  # Suspensa
    4: "⛔",   # Inapta
    8: "❌",   # Baixada
}


# ─────────────────────────────────────────────
# Funções auxiliares
# ─────────────────────────────────────────────

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
    """
    Retorna (codigo_int, descricao_str) da situação cadastral.
    Tenta primeiro o campo numérico 'situacao_cadastral',
    depois o textual 'descricao_situacao_cadastral'.
    """
    codigo = dados_api.get("situacao_cadastral")
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        codigo = None

    descricao = dados_api.get("descricao_situacao_cadastral", "") or ""

    # Se não veio código, tenta inferir pela descrição
    if codigo is None:
        desc_up = descricao.upper()
        if "ATIVA" in desc_up:
            codigo = 2
        elif "BAIXADA" in desc_up:
            codigo = 8
        elif "INAPTA" in desc_up:
            codigo = 4
        elif "SUSPENSA" in desc_up:
            codigo = 3
        elif "NULA" in desc_up:
            codigo = 1
        else:
            codigo = 0  # desconhecido

    if not descricao:
        descricao = SITUACOES_DESCRICAO.get(codigo, "DESCONHECIDA")

    return codigo, descricao


def cnpj_esta_ativo(dados_api: dict) -> bool:
    """Retorna True apenas se a situação cadastral for ATIVA (código 2)."""
    codigo, _ = get_situacao_cadastral(dados_api)
    return codigo == SITUACAO_ATIVA


def consultar_cnpj(cnpj: str) -> dict | None:
    """
    Consulta o CNPJ na API pública Minha Receita.
    Retorna dict com os dados ou None em caso de erro de rede/HTTP.
    """
    cnpj_limpo = limpar_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        return None
    url = f"https://minhareceita.org/{cnpj_limpo}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def mapear_natureza_juridica(codigo_nj: int | None) -> str:
    if not codigo_nj:
        return "7"
    codigo_str = str(codigo_nj)
    if codigo_str.startswith("10"):
        return "1"
    if codigo_str.startswith("11"):
        return "2"
    if codigo_str.startswith("12"):
        return "3"
    if codigo_str.startswith("20"):
        return "4"
    if codigo_str.startswith("21"):
        return "5"
    if codigo_str.startswith("22"):
        return "6"
    if codigo_nj == 2150:
        return "8"
    return "7"


def mapear_porte(porte: str | None) -> str:
    if not porte:
        return "N"
    porte_up = porte.upper()
    if "MICRO" in porte_up or porte_up == "ME":
        return "M"
    if "PEQUENO" in porte_up or porte_up == "EPP":
        return "E"
    if "SIMPLES" in porte_up:
        return "M"
    return "N"


def extrair_participantes_sped(conteudo: str) -> list[dict]:
    """
    Extrai registros 0150 do SPED Fiscal.
    |0150|COD_PART|NOME|COD_PAIS|CNPJ|CPF|IE|COD_MUN|SUFRAMA|END|NUM|COMPL|BAIRRO|
    """
    participantes = []
    for linha in conteudo.splitlines():
        linha = linha.strip()
        campos = linha.split("|")
        if campos and campos[0] == "":
            campos = campos[1:]
        if campos and campos[-1] == "":
            campos = campos[:-1]
        if not campos:
            continue
        if campos[0] == "0150":
            try:
                participantes.append({
                    "cod_part": campos[1]  if len(campos) > 1  else "",
                    "nome":     campos[2]  if len(campos) > 2  else "",
                    "cod_pais": campos[3]  if len(campos) > 3  else "",
                    "cnpj":     campos[4]  if len(campos) > 4  else "",
                    "cpf":      campos[5]  if len(campos) > 5  else "",
                    "ie":       campos[6]  if len(campos) > 6  else "",
                    "cod_mun":  campos[7]  if len(campos) > 7  else "",
                    "suframa":  campos[8]  if len(campos) > 8  else "",
                    "end":      campos[9]  if len(campos) > 9  else "",
                    "num":      campos[10] if len(campos) > 10 else "",
                    "compl":    campos[11] if len(campos) > 11 else "",
                    "bairro":   campos[12] if len(campos) > 12 else "",
                })
            except IndexError:
                continue
    return participantes


# ─────────────────────────────────────────────
# Funções de geração de linhas Domínio
# ─────────────────────────────────────────────

def gerar_linha_0000(cnpj_empresa: str, nome_empresa: str) -> str:
    return f"0000|{limpar_cnpj(cnpj_empresa)}|\n"


def _campos_endereco(dados_api: dict, dados_sped: dict, exterior: bool, usar_sped: bool) -> dict:
    """
    Monta campos de endereço.
    - exterior=True  → sempre SPED, cod_mun="EX", uf="EX"
    - usar_sped=True → CNPJ baixado/inapto/etc: usa dados do SPED
    - caso contrário → dados da API
    """
    if exterior:
        return {
            "logradouro":  dados_sped.get("end", "")   or "",
            "numero":      dados_sped.get("num", "")   or "",
            "complemento": dados_sped.get("compl", "") or "",
            "bairro":      dados_sped.get("bairro", "") or "",
            "cod_mun":     "EX",
            "uf":          "EX",
            "cod_pais":    dados_sped.get("cod_pais", "") or "",
            "cep":         "",
        }
    elif usar_sped:
        return {
            "logradouro":  dados_sped.get("end", "")   or "",
            "numero":      dados_sped.get("num", "")   or "",
            "complemento": dados_sped.get("compl", "") or "",
            "bairro":      dados_sped.get("bairro", "") or "",
            "cod_mun":     dados_sped.get("cod_mun", "") or "",
            "uf":          "",   # UF não está no 0150 do SPED
            "cod_pais":    "",
            "cep":         "",
        }
    else:
        return {
            "logradouro":  dados_api.get("logradouro", dados_sped.get("end", ""))   or "",
            "numero":      dados_api.get("numero",     dados_sped.get("num", ""))   or "",
            "complemento": dados_api.get("complemento", dados_sped.get("compl", "")) or "",
            "bairro":      dados_api.get("bairro",     dados_sped.get("bairro", "")) or "",
            "cod_mun":     str(dados_api.get("codigo_municipio", dados_sped.get("cod_mun", "")) or ""),
            "uf":          dados_api.get("uf", "") or "",
            "cod_pais":    "",
            "cep":         re.sub(r"\D", "", dados_api.get("cep", "") or ""),
        }


def _campos_comuns(dados_api: dict, dados_sped: dict, exterior: bool, usar_sped: bool) -> dict:
    """
    Retorna campos comuns a 0010 e 0020.
    Quando usar_sped=True (CNPJ baixado/inapto/etc), usa dados do SPED.
    """
    if exterior or usar_sped:
        return {
            "cnpj":         limpar_cnpj(dados_sped.get("cnpj", "")) if not exterior else "",
            "razao":        (dados_sped.get("nome", "") or "")[:150],
            "fantasia":     "",
            "ie":           "" if exterior else (dados_sped.get("ie", "") or ""),
            "suframa":      "" if exterior else (dados_sped.get("suframa", "") or ""),
            "ddd1":         "",
            "tel1":         "",
            "ddd_fax":      "",
            "fax":          "",
            "data_cad":     "",
            "nat_jur":      "7",
            "regime":       "N",
            "email":        "",
        }
    else:
        return {
            "cnpj":         limpar_cnpj(dados_api.get("cnpj", dados_sped.get("cnpj", ""))),
            "razao":        (dados_api.get("razao_social", dados_sped.get("nome", "")) or "")[:150],
            "fantasia":     (dados_api.get("nome_fantasia", "") or "")[:40],
            "ie":           dados_sped.get("ie", "") or "",
            "suframa":      dados_sped.get("suframa", "") or "",
            "ddd1":         (dados_api.get("ddd_telefone_1", "") or "")[:2],
            "tel1":         dados_api.get("telefone_1", "") or "",
            "ddd_fax":      (dados_api.get("ddd_fax", "") or "")[:2],
            "fax":          dados_api.get("fax", "") or "",
            "data_cad":     formatar_data(dados_api.get("data_inicio_atividade", "")),
            "nat_jur":      mapear_natureza_juridica(dados_api.get("codigo_natureza_juridica")),
            "regime":       mapear_porte(dados_api.get("porte", "")),
            "email":        dados_api.get("email", "") or "",
        }


def gerar_linha_0010(dados_api: dict, dados_sped: dict, exterior: bool, usar_sped: bool) -> str:
    end = _campos_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _campos_comuns(dados_api, dados_sped, exterior, usar_sped)
    campos = [
        "0010", c["cnpj"], c["razao"], c["fantasia"],
        end["logradouro"], end["numero"], end["complemento"],
        end["bairro"], end["cod_mun"], end["uf"], end["cod_pais"], end["cep"],
        c["ie"], "",           # im (inscrição municipal)
        c["suframa"],
        c["ddd1"], c["tel1"], c["ddd_fax"], c["fax"], c["data_cad"],
        "",                    # conta_ctb
        "",                    # conta_forn
        "N",                   # agropec
        c["nat_jur"], c["regime"],
        "N", "", "", "N",      # contrib_icms, aliq_icms, categ_estab, interdep
        "", "N", "", "",       # mt_perc, paa, tipo_insc, proc_adm
    ]
    return "|".join(str(x) for x in campos) + "|\n"


def gerar_linha_0020(dados_api: dict, dados_sped: dict, exterior: bool, usar_sped: bool) -> str:
    end = _campos_endereco(dados_api, dados_sped, exterior, usar_sped)
    c   = _campos_comuns(dados_api, dados_sped, exterior, usar_sped)
    campos = [
        "0020", c["cnpj"], c["razao"], c["fantasia"],
        end["logradouro"], end["numero"], end["complemento"],
        end["bairro"], end["cod_mun"], end["uf"], end["cod_pais"], end["cep"],
        c["ie"], "",           # im
        c["suframa"],
        c["ddd1"], c["tel1"], c["ddd_fax"], c["fax"], c["data_cad"],
        "",                    # conta_ctb
        "",                    # conta_cli
        "N",                   # agropec
        c["nat_jur"], c["regime"],
        "N", "", "",           # contrib_icms, aliq_icms, categ_estab
        "",                    # ie_st
        c["email"],
        "N", "N", "", "",      # interdep, contrib_cprb, proc_adm, tipo_insc
    ]
    return "|".join(str(x) for x in campos) + "|\n"


# ─────────────────────────────────────────────
# Interface Streamlit
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configurações")
    cnpj_empresa = st.text_input("CNPJ da Empresa (apenas números)", max_chars=14)
    nome_empresa = st.text_input("Nome / Razão Social da Empresa")
    tipo_registro = st.radio(
        "Gerar registros como:",
        options=["Clientes (0010)", "Fornecedores (0020)", "Ambos (0010 e 0020)"],
        index=2,
    )
    delay_api = st.slider(
        "Intervalo entre consultas (segundos)",
        min_value=0.5, max_value=5.0, value=1.0, step=0.5,
    )
    st.markdown("---")
    st.markdown("**Legenda de situação cadastral:**")
    for cod, desc in SITUACOES_DESCRICAO.items():
        icone = SITUACAO_ICONE.get(cod, "❓")
        fonte = "API Receita" if cod == SITUACAO_ATIVA else "**Dados do SPED**"
        st.caption(f"{icone} **{desc}** → {fonte}")
    st.markdown("---")
    st.caption("API: **minhareceita.org** (gratuita, sem autenticação)")

# ─────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────
st.subheader("📂 1. Upload do arquivo SPED Fiscal")
arquivo_sped = st.file_uploader("Selecione o arquivo SPED Fiscal (.txt)", type=["txt"])

if arquivo_sped:
    conteudo_sped = arquivo_sped.read().decode("latin-1", errors="replace")
    participantes = extrair_participantes_sped(conteudo_sped)
    total = len(participantes)

    if total == 0:
        st.warning("⚠️ Nenhum registro 0150 encontrado no arquivo SPED informado.")
        st.stop()

    st.success(f"✅ {total} participante(s) encontrado(s) no SPED (registro 0150).")

    nacionais    = [p for p in participantes if not is_exterior(p["cod_pais"])]
    estrangeiros = [p for p in participantes if is_exterior(p["cod_pais"])]
    nac_cnpj     = [p for p in nacionais if len(limpar_cnpj(p["cnpj"])) == 14]
    nac_cpf      = [p for p in nacionais if len(limpar_cnpj(p["cnpj"])) != 14]

    c1, c2, c3 = st.columns(3)
    c1.metric("🇧🇷 Nacionais com CNPJ", len(nac_cnpj))
    c2.metric("🇧🇷 CPF / sem inscrição", len(nac_cpf))
    c3.metric("🌍 Exterior", len(estrangeiros))

    with st.expander("👁️ Visualizar participantes extraídos do SPED"):
        import pandas as pd
        df_part = pd.DataFrame(participantes)
        st.dataframe(df_part, use_container_width=True)

    # ─────────────────────────────────────────────
    # Processamento
    # ─────────────────────────────────────────────
    st.subheader("🚀 2. Processar e gerar arquivo Domínio")

    if not cnpj_empresa or not nome_empresa:
        st.warning("⚠️ Preencha o **CNPJ** e o **Nome da Empresa** na barra lateral.")
        st.stop()

    if st.button("▶️ Iniciar consulta e geração do arquivo", type="primary"):

        progresso = st.progress(0, text="Iniciando...")
        log_area  = st.empty()
        logs      = []

        linhas_saida = []
        dados_tabela = []

        # Contadores por situação
        contadores = {
            "api_ativa": 0,
            "baixada":   0,
            "inapta":    0,
            "suspensa":  0,
            "nula":      0,
            "sem_api":   0,
            "cpf_sped":  0,
            "exterior":  0,
        }

        linhas_saida.append(gerar_linha_0000(cnpj_empresa, nome_empresa))

        gerar_0010 = "0010" in tipo_registro or "Ambos" in tipo_registro
        gerar_0020 = "0020" in tipo_registro or "Ambos" in tipo_registro

        for idx, part in enumerate(participantes):
            pct       = int((idx + 1) / total * 100)
            cnpj_raw  = limpar_cnpj(part["cnpj"])
            nome_sped = part["nome"]
            exterior  = is_exterior(part["cod_pais"])

            progresso.progress(
                pct,
                text=f"Processando {idx+1}/{total}: "
                     f"{'🌍 EXTERIOR' if exterior else cnpj_raw or 'CPF'}"
            )

            # ── Inicializa variáveis de controle ──────────────────────────
            dados_api  = {}
            usar_sped  = False   # True = ignorar dados da API e usar SPED
            situacao_cod  = None
            situacao_desc = ""
            status_label  = ""
            razao_final   = nome_sped

            # ── Decide a origem dos dados ─────────────────────────────────
            if exterior:
                # Exterior: sempre SPED, nunca consulta API
                usar_sped     = True
                status_label  = f"🌍 Exterior (COD_PAIS={part['cod_pais']})"
                contadores["exterior"] += 1

            elif len(cnpj_raw) == 14:
                # Nacional com CNPJ: consulta API
                dados_api_bruto = consultar_cnpj(cnpj_raw)
                time.sleep(delay_api)

                if dados_api_bruto is None:
                    # Erro de rede / CNPJ não encontrado na API
                    usar_sped    = True
                    status_label = "⚠️ Sem resposta da API — dados do SPED"
                    contadores["sem_api"] += 1
                else:
                    situacao_cod, situacao_desc = get_situacao_cadastral(dados_api_bruto)
                    icone = SITUACAO_ICONE.get(situacao_cod, "❓")

                    if situacao_cod == SITUACAO_ATIVA:
                        # ✅ ATIVA: usa dados da API
                        dados_api    = dados_api_bruto
                        usar_sped    = False
                        razao_final  = dados_api.get("razao_social", nome_sped)
                        status_label = f"✅ ATIVA — dados da Receita Federal"
                        contadores["api_ativa"] += 1
                    else:
                        # ❌ BAIXADA / INAPTA / SUSPENSA / NULA: usa SPED
                        usar_sped    = True
                        status_label = (
                            f"{icone} {situacao_desc} "
                            f"(sit. {situacao_cod}) — dados do SPED"
                        )
                        if situacao_cod == 8:
                            contadores["baixada"] += 1
                        elif situacao_cod == 4:
                            contadores["inapta"] += 1
                        elif situacao_cod == 3:
                            contadores["suspensa"] += 1
                        elif situacao_cod == 1:
                            contadores["nula"] += 1
                        else:
                            contadores["sem_api"] += 1
            else:
                # CPF ou sem inscrição: usa SPED
                usar_sped    = True
                status_label = "ℹ️ CPF/sem CNPJ — dados do SPED"
                contadores["cpf_sped"] += 1

            # ── Gera as linhas do arquivo ─────────────────────────────────
            if gerar_0010:
                linhas_saida.append(
                    gerar_linha_0010(dados_api, part, exterior, usar_sped)
                )
            if gerar_0020:
                linhas_saida.append(
                    gerar_linha_0020(dados_api, part, exterior, usar_sped)
                )

            # ── Tabela de resultado ───────────────────────────────────────
            dados_tabela.append({
                "COD_PART":           part["cod_part"],
                "CNPJ/CPF":           cnpj_raw or limpar_cnpj(part["cpf"]),
                "Nome (SPED)":        nome_sped,
                "Razão Social (API)": dados_api.get("razao_social", ""),
                "Situação Receita":   situacao_desc or ("—" if exterior else "—"),
                "COD_PAIS":           part["cod_pais"],
                "Fonte dos Dados":    "SPED" if usar_sped else "Receita Federal",
                "Status":             status_label,
            })

            logs.append(
                f"[{idx+1:03d}/{total}] {cnpj_raw or part['cpf'] or 'EXT'} | "
                f"{razao_final[:40]} | {status_label}"
            )
            log_area.text_area(
                "Log de processamento", value="\n".join(logs[-20:]), height=200
            )

        progresso.progress(100, text="✅ Concluído!")

        # ─── Resultado ───────────────────────────────────────────────────
        st.subheader("📊 3. Resultado")

        # Métricas resumidas
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("✅ Ativos (API)",       contadores["api_ativa"])
        m2.metric("❌ Baixados (SPED)",    contadores["baixada"])
        m3.metric("⛔ Inaptos (SPED)",     contadores["inapta"])
        m4.metric("⚠️ Suspensos (SPED)",  contadores["suspensa"])
        m5.metric("🌍 Exterior (SPED)",    contadores["exterior"])
        m6.metric("ℹ️ CPF/Sem API (SPED)", contadores["cpf_sped"] + contadores["sem_api"])

        # Tabela com destaque por situação
        df_resultado = pd.DataFrame(dados_tabela)

        def highlight_situacao(row):
            status = str(row.get("Status", ""))
            if "ATIVA" in status:
                return ["background-color: #d4edda"] * len(row)   # verde
            if "BAIXADA" in status:
                return ["background-color: #f8d7da"] * len(row)   # vermelho
            if "INAPTA" in status:
                return ["background-color: #f5c6cb"] * len(row)   # vermelho escuro
            if "SUSPENSA" in status:
                return ["background-color: #fff3cd"] * len(row)   # amarelo
            if "Exterior" in status:
                return ["background-color: #cce5ff"] * len(row)   # azul
            return ["background-color: #e2e3e5"] * len(row)       # cinza

        st.dataframe(
            df_resultado.style.apply(highlight_situacao, axis=1),
            use_container_width=True,
        )

        # Alertas específicos para CNPJs problemáticos
        baixados = [r for r in dados_tabela if "BAIXADA" in r["Status"]]
        inaptos  = [r for r in dados_tabela if "INAPTA"  in r["Status"]]
        suspensos= [r for r in dados_tabela if "SUSPENSA" in r["Status"]]

        if baixados:
            with st.expander(f"❌ {len(baixados)} CNPJ(s) BAIXADO(s) — usando dados do SPED"):
                st.dataframe(
                    pd.DataFrame(baixados)[["COD_PART","CNPJ/CPF","Nome (SPED)"]],
                    use_container_width=True,
                )
        if inaptos:
            with st.expander(f"⛔ {len(inaptos)} CNPJ(s) INAPTO(s) — usando dados do SPED"):
                st.dataframe(
                    pd.DataFrame(inaptos)[["COD_PART","CNPJ/CPF","Nome (SPED)"]],
                    use_container_width=True,
                )
        if suspensos:
            with st.expander(f"⚠️ {len(suspensos)} CNPJ(s) SUSPENSO(s) — usando dados do SPED"):
                st.dataframe(
                    pd.DataFrame(suspensos)[["COD_PART","CNPJ/CPF","Nome (SPED)"]],
                    use_container_width=True,
                )

        # ─── Download ────────────────────────────────────────────────────
        conteudo_saida = "".join(linhas_saida)
        nome_arquivo   = f"dominio_separador_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        st.subheader("💾 4. Download do arquivo gerado")

        col_dl, col_mt = st.columns(2)
        with col_dl:
            st.download_button(
                label="⬇️ Baixar arquivo TXT (Domínio Separador)",
                data=conteudo_saida.encode("latin-1", errors="replace"),
                file_name=nome_arquivo,
                mime="text/plain",
            )
        with col_mt:
            st.metric("Total de linhas geradas", len(linhas_saida))

        with st.expander("👁️ Prévia do arquivo gerado (primeiras 30 linhas)"):
            st.code("".join(linhas_saida[:30]), language="text")

        st.success(
            f"🎉 Arquivo **{nome_arquivo}** gerado! "
            "Importe no Domínio via: Utilitários → Importação → "
            "Importação Padrão → Leiaute Domínio Sistemas com Separador."
        )

else:
    st.info("👆 Faça o upload do arquivo SPED Fiscal (.txt) para começar.")

# ─────────────────────────────────────────────
# Rodapé
# ─────────────────────────────────────────────
st.markdown("---")
st.caption(
    "API: **minhareceita.org** | Leiaute: **Domínio Sistemas com Separador** | "
    "Separador: `|` (pipe)"
)
