"""
IAE Sales Engine — painel Streamlit: higienização, blacklist, UTM, Gemini e envio SMTP.
Execute: streamlit run app.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src.blacklist import apply_blacklist, load_blacklist
from src.config import (
    DADOS_DIR,
    DEFAULT_BLACKLIST,
    FROM_EMAIL,
    GEMINI_API_KEY,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)
from src.domain_validation import validate_emails_column
from src.gemini_client import aplicar_placeholders, gerar_variacoes_copy
from src.mailer import (
    DELAY_MAX_S,
    DELAY_MIN_S,
    FilaEnvioInteligente,
    MAX_POR_HORA,
    enviar_email_html,
)
from src.utm_tracker import inject_utm_in_html

COL_CIDADE = "Cidade"
COL_EMAIL = "E-mail da Secretaria de Turismo"
COL_SITE = "Site (Domínio Oficial)"
COL_CATEGORIA = "Categoria"


def _listar_csvs_dados() -> list[Path]:
    if not DADOS_DIR.exists():
        return []
    return sorted(DADOS_DIR.glob("*.csv"), key=lambda p: p.name.lower())


def _garantir_categoria(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if COL_CATEGORIA not in out.columns:
        out[COL_CATEGORIA] = "Estância Turística / MIT (SP)"
    return out


def _filtrar_envio(df: pd.DataFrame) -> pd.DataFrame:
    m = (df["status_higiene"] == "Válido") & (~df["blacklist_bloqueado"])
    return df.loc[m].copy()


def main() -> None:
    st.set_page_config(page_title="IAE Sales Engine", layout="wide")
    st.title("IAE Sales Engine")
    st.caption("Prospecção IAE Smart Guide — higienização, compliance, UTM e envio inteligente")

    with st.sidebar:
        st.header("Fonte de dados")
        csvs = _listar_csvs_dados()
        opcoes = [p.name for p in csvs]
        if not opcoes:
            st.warning("Nenhum .csv em /dados. Adicione arquivos ou use upload abaixo.")
            arquivo_escolhido = None
        else:
            arquivo_escolhido = st.selectbox("Planilha em /dados", options=opcoes, index=0)

        upload = st.file_uploader("Enviar nova planilha CSV", type=["csv"])
        if upload is not None:
            destino = DADOS_DIR / upload.name
            DADOS_DIR.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(upload.getvalue())
            st.success(f"Planilha '{upload.name}' salva!")
            st.rerun()

        st.header("Campanha (UTM)")
        utm_campaign = st.text_input(
            "utm_campaign",
            value="prospeccao",
            help="Usado em utm_campaign para links iaesmartguide.com.br",
        )

        st.header("Blacklist")
        st.caption(str(DEFAULT_BLACKLIST))
        path_bl = st.text_input("Caminho blacklist.csv", value=str(DEFAULT_BLACKLIST))

        st.header("Credenciais (.env)")
        st.caption("SMTP e GEMINI_API_KEY devem estar no arquivo .env na raiz do projeto.")
        ok_smtp = bool(SMTP_USER and SMTP_PASSWORD)
        st.write("SMTP:", "OK" if ok_smtp else "incompleto")
        st.write("Gemini:", "OK" if GEMINI_API_KEY else "falta GEMINI_API_KEY")

    # Carregar DataFrame
    df: pd.DataFrame | None = None
    if arquivo_escolhido:
        path = DADOS_DIR / arquivo_escolhido
        df = pd.read_csv(path)

    if df is None or df.empty:
        st.info("Carregue uma planilha para iniciar. Colunas esperadas: Cidade, E-mail da Secretaria de Turismo, Site (Domínio Oficial); opcional: Categoria.")
        return

    for col in (COL_CIDADE, COL_EMAIL, COL_SITE):
        if col not in df.columns:
            st.error(f"Coluna obrigatória ausente: {col}")
            return

    df = _garantir_categoria(df)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("1. Validar domínios (MX/DNS)", type="primary"):
            with st.status("Validando domínios...", expanded=True) as status:
                status.write("Validando Domínios")
                df_v = validate_emails_column(df, COL_EMAIL)
                st.session_state["df_work"] = df_v
                status.update(label="Domínios validados", state="complete")
    with col2:
        if st.button("2. Aplicar blacklist"):
            with st.status("Filtrando Blacklist", expanded=True) as status:
                status.write("Filtrando Blacklist")
                path_b = Path(path_bl)
                em_bl, dom_bl = load_blacklist(path_b)
                base = st.session_state.get("df_work", df)
                df_b = apply_blacklist(base, COL_EMAIL, COL_SITE, em_bl, dom_bl)
                st.session_state["df_work"] = df_b
                status.update(label="Blacklist aplicada", state="complete")
    with col3:
        st.metric("Linhas carregadas", len(df))

    if st.button("Pipeline: validação + blacklist", help="Executa os dois passos em sequência"):
        with st.status("Processando pipeline...", expanded=True) as status:
            status.write("Validando Domínios")
            df_v = validate_emails_column(df, COL_EMAIL)
            status.write("Filtrando Blacklist")
            path_b = Path(path_bl)
            em_bl, dom_bl = load_blacklist(path_b)
            df_b = apply_blacklist(df_v, COL_EMAIL, COL_SITE, em_bl, dom_bl)
            st.session_state["df_work"] = df_b
            status.update(label="Pipeline concluído", state="complete")

    df_work = st.session_state.get("df_work", df)

    if "status_higiene" in df_work.columns:
        c_valid = (df_work["status_higiene"] == "Válido").sum()
        c_inv = (df_work["status_higiene"] == "Inválido").sum()
        b1, b2 = st.columns(2)
        b1.metric("Válidos (MX)", int(c_valid))
        b2.metric("Inválidos", int(c_inv))

    if "blacklist_bloqueado" in df_work.columns:
        bl = int(df_work["blacklist_bloqueado"].sum())
        st.metric("Bloqueados por blacklist", bl)

    st.subheader("Prévia dos dados (após processamento)")
    st.dataframe(df_work, use_container_width=True)

    st.divider()
    st.subheader("Criação de campanha com IA (Gemini)")
    idx_var = st.number_input("Variação escolhida (1 a 3)", min_value=1, max_value=3, value=1)

    if st.button("Gerar 3 variações com Gemini"):
        try:
            primeira = df_work.iloc[0]
            vars_copy = gerar_variacoes_copy(
                str(primeira[COL_CIDADE]),
                str(primeira[COL_CATEGORIA]),
                str(primeira[COL_SITE]),
            )
            st.session_state["variacoes_ia"] = vars_copy
            st.success("3 variações geradas.")
        except Exception as e:
            st.error(str(e))

    if "variacoes_ia" in st.session_state:
        vars_copy = st.session_state["variacoes_ia"]
        for i, item in enumerate(vars_copy, start=1):
            with st.expander(f"Variação {i}"):
                st.write("**Assunto:**", item.get("assunto", ""))
                st.markdown(item.get("corpo_html", ""), unsafe_allow_html=True)

    st.divider()
    st.subheader("Envio de teste")

    col_teste1, col_teste2 = st.columns([3, 1])
    with col_teste1:
        email_teste = st.text_input(
            "E-mail para teste",
            placeholder="seuemail@exemplo.com",
            help="Envia uma prévia da variação escolhida para validar antes de disparar a campanha.",
        )
    with col_teste2:
        st.write("")
        st.write("")
        btn_teste = st.button("Enviar teste", use_container_width=True)

    if btn_teste:
        if not email_teste:
            st.warning("Digite um endereço de e-mail para o teste.")
        elif "variacoes_ia" not in st.session_state:
            st.error("Gere as variações com Gemini antes de enviar o teste.")
        elif not ok_smtp:
            st.error("Configure SMTP_USER e SMTP_PASSWORD nas variáveis de ambiente.")
        else:
            variacoes = st.session_state["variacoes_ia"]
            escolha = variacoes[int(idx_var) - 1]
            cidade_ex = str(df_work.iloc[0][COL_CIDADE]) if not df_work.empty else "Cidade Exemplo"
            categoria_ex = str(df_work.iloc[0][COL_CATEGORIA]) if not df_work.empty else "Categoria Exemplo"
            assunto_ex, corpo_ex = aplicar_placeholders(
                escolha["assunto"], escolha["corpo_html"], cidade_ex, categoria_ex
            )
            corpo_ex = inject_utm_in_html(corpo_ex, utm_campaign or "prospeccao", cidade_ex)
            try:
                enviar_email_html(
                    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
                    FROM_EMAIL, email_teste,
                    f"[TESTE] {assunto_ex}", corpo_ex,
                )
                st.success(f"E-mail de teste enviado para {email_teste}!")
            except Exception as e:
                st.error(f"Falha ao enviar teste: {e}")

    st.divider()
    st.subheader("Envio")

    limite_teste = st.number_input("Máximo de e-mails nesta execução (0 = todos elegíveis)", min_value=0, value=0)

    if st.button("Enviar campanha", type="primary"):
        st.session_state["last_errors"] = []
        if "variacoes_ia" not in st.session_state:
            st.error("Gere as variações com Gemini antes de enviar.")
            return
        if not ok_smtp:
            st.error("Configure SMTP_USER e SMTP_PASSWORD no .env")
            return
        if "status_higiene" not in df_work.columns:
            st.error('Execute primeiro "Validar domínios" ou o pipeline completo.')
            return
        if "blacklist_bloqueado" not in df_work.columns:
            st.error('Execute "Aplicar blacklist" ou o pipeline completo antes do envio.')
            return

        filtrado = _filtrar_envio(df_work)
        if filtrado.empty:
            st.warning("Nenhum destinatário elegível (válido + fora da blacklist).")
            return

        variacoes = st.session_state["variacoes_ia"]
        escolha = variacoes[int(idx_var) - 1]
        assunto_tpl = escolha["assunto"]
        corpo_tpl = escolha["corpo_html"]

        fila = FilaEnvioInteligente()
        sucesso = 0
        erros = 0
        total = len(filtrado) if limite_teste == 0 else min(len(filtrado), int(limite_teste))

        progress = st.progress(0.0)
        log_box = st.empty()

        with st.status("Enviando...", expanded=True) as status:
            status.write("Enviando...")
            for i, (_, row) in enumerate(filtrado.iterrows()):
                if limite_teste and i >= limite_teste:
                    break

                cidade = str(row[COL_CIDADE])
                categoria = str(row[COL_CATEGORIA])
                email = str(row[COL_EMAIL]).strip()

                assunto, corpo = aplicar_placeholders(assunto_tpl, corpo_tpl, cidade, categoria)
                corpo_final = inject_utm_in_html(corpo, utm_campaign or "prospeccao", cidade)

                fila.aguardar_vaga_hora()
                try:
                    enviar_email_html(
                        SMTP_HOST,
                        SMTP_PORT,
                        SMTP_USER,
                        SMTP_PASSWORD,
                        FROM_EMAIL,
                        email,
                        assunto,
                        corpo_final,
                    )
                    fila.registrar_envio()
                    sucesso += 1
                except Exception as e:
                    erros += 1
                    st.session_state["last_errors"].append(f"{email}: {e}")

                progress.progress((i + 1) / max(total, 1))
                log_box.caption(f"Processados: {i + 1}/{total} | OK: {sucesso} | Erro: {erros}")

                if i + 1 < total:
                    fila.pausa_entre_envios()

            status.update(label="Envio finalizado", state="complete")

        st.subheader("Resultado")
        res_df = pd.DataFrame({"Tipo": ["Sucesso", "Erros"], "Quantidade": [sucesso, erros]})
        st.bar_chart(res_df.set_index("Tipo"))
        st.caption(
            f"Fila inteligente: até {MAX_POR_HORA} envios por hora; "
            f"intervalo aleatório de {DELAY_MIN_S} a {DELAY_MAX_S} s entre envios."
        )

        if st.session_state.get("last_errors"):
            with st.expander("Últimos erros"):
                for line in st.session_state["last_errors"][-20:]:
                    st.text(line)


if __name__ == "__main__":
    main()
