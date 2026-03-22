"""
IAE Sales Engine — painel Streamlit: planilhas, higienização, blacklist, IA, layout rico e envio SMTP.
Execute: streamlit run app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.blacklist import apply_blacklist, load_blacklist
from src.config import (
    ANEXOS_DIR,
    DEFAULT_BLACKLIST,
    EMAIL_ASSETS_DIR,
    FROM_EMAIL,
    GEMINI_API_KEY,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)
from src.domain_validation import validate_emails_column
from src.email_layout import aplicar_layout_email
from src.gemini_client import aplicar_placeholders, gerar_mensagem_campanha
from src.mailer import (
    DELAY_MAX_S,
    DELAY_MIN_S,
    FilaEnvioInteligente,
    MAX_POR_HORA,
    enviar_email_avancado,
)
from src.planilhas_store import listar_planilhas, nome_seguro, PLANILHAS_DIR
from src.utm_tracker import preparar_links_campanha

COL_CIDADE = "Cidade"
COL_EMAIL = "E-mail da Secretaria de Turismo"
COL_SITE = "Site (Domínio Oficial)"
COL_CATEGORIA = "Categoria"


def _garantir_categoria(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if COL_CATEGORIA not in out.columns:
        out[COL_CATEGORIA] = "Estância Turística / MIT (SP)"
    return out


def _filtrar_envio(df: pd.DataFrame) -> pd.DataFrame:
    m = (df["status_higiene"] == "Válido") & (~df["blacklist_bloqueado"])
    return df.loc[m].copy()


def _cidades_elegiveis(df: pd.DataFrame) -> list[str]:
    if "status_higiene" in df.columns and "blacklist_bloqueado" in df.columns:
        m = (df["status_higiene"] == "Válido") & (~df["blacklist_bloqueado"])
        sub = df.loc[m]
    else:
        sub = df
    return sorted(sub[COL_CIDADE].dropna().astype(str).unique().tolist())


def _gemini_ok() -> bool:
    return bool(
        GEMINI_API_KEY
        or os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )


def _garantir_dirs_midia() -> None:
    EMAIL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ANEXOS_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    st.set_page_config(page_title="IAE Sales Engine", layout="wide")
    st.title("IAE Sales Engine")
    st.caption("Prospecção IAE Smart Guide — dados, compliance, IA e envio inteligente")

    if st.session_state.get("ultimo_envio"):
        u = st.session_state["ultimo_envio"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Último disparo — sucessos", u.get("sucesso", 0))
        c2.metric("Último disparo — erros", u.get("erros", 0))
        c3.metric("Destinatários previstos", u.get("total", 0))

    with st.sidebar:
        st.header("Planilhas salvas")
        paths = listar_planilhas()
        if not paths:
            st.warning("Nenhuma planilha .csv encontrada. Envie um arquivo abaixo.")
            arquivo_path: Path | None = None
        else:
            arquivo_path = st.selectbox(
                "Arquivo ativo",
                options=paths,
                format_func=lambda p: p.name,
                key="sel_planilha",
            )

        up = st.file_uploader("Enviar CSV", type=["csv"], key="up_csv")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Salvar como novo", help="Grava em dados/planilhas/"):
                if up is None:
                    st.warning("Selecione um arquivo CSV.")
                else:
                    PLANILHAS_DIR.mkdir(parents=True, exist_ok=True)
                    dest = PLANILHAS_DIR / nome_seguro(up.name)
                    dest.write_bytes(up.getbuffer())
                    st.success(f"Salvo: {dest.name}")
                    st.rerun()
        with c2:
            if st.button("Substituir selecionada", help="Sobrescreve o arquivo escolhido na lista"):
                if up is None:
                    st.warning("Selecione um CSV para substituir.")
                elif arquivo_path is None:
                    st.warning("Não há planilha selecionada.")
                else:
                    arquivo_path.write_bytes(up.getbuffer())
                    st.success(f"Atualizado: {arquivo_path.name}")
                    st.rerun()

        if arquivo_path is not None and st.button("Excluir planilha selecionada"):
            if arquivo_path.resolve() == Path(DEFAULT_BLACKLIST).resolve():
                st.error("Não é permitido excluir a blacklist.")
            else:
                try:
                    arquivo_path.unlink()
                    st.success("Arquivo removido.")
                    st.rerun()
                except OSError as e:
                    st.error(str(e))

        st.header("Campanha (UTM)")
        utm_campaign = st.text_input(
            "utm_campaign",
            value="prospeccao",
            help="Usado em utm_campaign para links iaesmartguide.com.br",
        )

        st.header("Blacklist")
        st.caption(str(DEFAULT_BLACKLIST))
        path_bl = st.text_input("Caminho blacklist.csv", value=str(DEFAULT_BLACKLIST))

        st.header("Credenciais")
        ok_smtp = bool(SMTP_USER and SMTP_PASSWORD)
        st.write("SMTP:", "OK" if ok_smtp else "incompleto")
        st.write("Gemini / IA:", "OK" if _gemini_ok() else "falta chave")

    if "assunto_campanha" not in st.session_state:
        st.session_state["assunto_campanha"] = ""
    if "corpo_campanha" not in st.session_state:
        st.session_state["corpo_campanha"] = ""

    if arquivo_path is None:
        st.info(
            "Salve uma planilha em dados/planilhas/ ou coloque um .csv em dados/ (exceto blacklist). "
            "Colunas: Cidade, E-mail da Secretaria de Turismo, Site (Domínio Oficial); opcional: Categoria."
        )
        return

    df = pd.read_csv(arquivo_path)
    if df.empty:
        st.error("Planilha vazia.")
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

    if st.button("Pipeline: validação + blacklist"):
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

    op_cidades = _cidades_elegiveis(df_work)
    if not op_cidades:
        st.warning("Nenhuma cidade elegível na base atual. Verifique a planilha ou execute o pipeline.")
        cidades_alvo: list[str] = []
    else:
        cidades_alvo = st.multiselect(
            "Cidades alvo da campanha (após pipeline, só entram elegíveis)",
            options=op_cidades,
            default=op_cidades,
            help="Restringe o disparo às cidades selecionadas. Elegível = domínio válido e fora da blacklist.",
        )

    st.subheader("Prévia dos dados")
    st.dataframe(df_work, use_container_width=True)

    st.divider()
    st.subheader("Instruções para a IA + mensagem")
    instrucoes = st.text_area(
        "Estratégia e informações dos produtos/serviços",
        height=160,
        placeholder=(
            "Ex.: mencionar quiosque de informações, app móvel, integração com MIT; "
            "tom consultivo; CTA agendar demo; diferenciais em relação a concorrentes…"
        ),
        help="A IA usa este texto com prioridade para gerar assunto e corpo com placeholders {{CIDADE}} e {{CATEGORIA}}.",
    )

    if st.button("Gerar mensagem com Gemini"):
        if not _gemini_ok():
            st.error("Configure a integração Gemini (Replit) ou GEMINI_API_KEY.")
        else:
            try:
                ex = df_work.iloc[0]
                msg = gerar_mensagem_campanha(
                    str(ex[COL_CIDADE]),
                    str(ex[COL_CATEGORIA]),
                    str(ex[COL_SITE]),
                    instrucoes,
                )
                st.session_state["assunto_campanha"] = msg["assunto"]
                st.session_state["corpo_campanha"] = msg["corpo_html"]
                st.success("Mensagem gerada. Edite abaixo se quiser refinar.")
            except Exception as e:
                st.error(str(e))

    st.text_input("Assunto (template com {{CIDADE}} / {{CATEGORIA}})", key="assunto_campanha")
    st.text_area("Corpo HTML (editável)", key="corpo_campanha", height=360)

    st.divider()
    st.subheader("Aparência e anexos")
    _garantir_dirs_midia()

    usar_testeira = st.checkbox(
        "Incluir testeira (faixa visual no topo, sem upload)",
        value=True,
        help="Faixa com gradiente e título IAE Smart Guide — não usa arquivo de imagem.",
    )
    usar_banner = st.checkbox(
        "Incluir foto/imagem abaixo da testeira (opcional)",
        value=False,
        help="Requer upload; alguns servidores limitam tamanho de imagem inline. Se der erro, deixe só a testeira.",
    )
    img_up = st.file_uploader(
        "Imagem do banner (PNG, JPG ou WebP)",
        type=["png", "jpg", "jpeg", "webp"],
        help="Largura recomendada ~560–800 px. Arquivo leve para abrir rápido no celular.",
    )
    if img_up is not None:
        ext = Path(img_up.name).suffix.lower() or ".png"
        banner_path = EMAIL_ASSETS_DIR / f"banner_campanha{ext}"
        banner_path.write_bytes(img_up.getbuffer())
        st.session_state["banner_path"] = str(banner_path)
        st.image(img_up.getbuffer(), caption="Prévia do banner", width=400)

    anexar_pdf = st.checkbox("Anexar PDF (apresentação leve)", value=False)
    pdf_up = st.file_uploader("Arquivo PDF", type=["pdf"], help="Prefira arquivos pequenos (ex.: até 2–3 MB) para boa entrega.")
    if pdf_up is not None:
        if pdf_up.size > 4 * 1024 * 1024:
            st.warning("PDF acima de 4 MB pode falhar em alguns servidores. Considere compactar.")
        raw_name = Path(pdf_up.name).name.replace("..", "").strip() or "apresentacao.pdf"
        if not raw_name.lower().endswith(".pdf"):
            raw_name = f"{raw_name}.pdf"
        pdf_path = ANEXOS_DIR / raw_name
        pdf_path.write_bytes(pdf_up.getbuffer())
        st.session_state["pdf_path"] = str(pdf_path)
        st.caption(f"Salvo: {pdf_path.name}")

    banner_disk = Path(st.session_state["banner_path"]) if st.session_state.get("banner_path") else None
    pdf_disk = Path(st.session_state["pdf_path"]) if st.session_state.get("pdf_path") else None
    if usar_banner and (not banner_disk or not banner_disk.exists()):
        st.info("Para usar foto no topo, envie uma imagem acima — ou desmarque e use só a testeira.")

    st.divider()
    st.subheader("Envio de teste")

    col_te1, col_te2 = st.columns([3, 1])
    with col_te1:
        email_teste = st.text_input(
            "E-mail para teste",
            placeholder="seuemail@exemplo.com",
            help="Usa o assunto/corpo editados acima, com UTM e layout escolhidos.",
        )
    with col_te2:
        st.write("")
        st.write("")
        btn_teste = st.button("Enviar teste", use_container_width=True)

    if btn_teste:
        if not email_teste:
            st.warning("Digite um endereço de e-mail para o teste.")
        elif not st.session_state.get("assunto_campanha") or not st.session_state.get("corpo_campanha"):
            st.error("Gere a mensagem com a IA ou preencha assunto e corpo.")
        elif not ok_smtp:
            st.error("Configure SMTP_USER e SMTP_PASSWORD.")
        else:
            cidade_ex = str(df_work.iloc[0][COL_CIDADE]) if not df_work.empty else "Cidade"
            categoria_ex = str(df_work.iloc[0][COL_CATEGORIA]) if not df_work.empty else "Categoria"
            assunto_ex, corpo_ex = aplicar_placeholders(
                st.session_state["assunto_campanha"],
                st.session_state["corpo_campanha"],
                cidade_ex,
                categoria_ex,
            )
            corpo_ex = preparar_links_campanha(corpo_ex, utm_campaign or "prospeccao", cidade_ex)
            com_b = usar_banner and banner_disk is not None and banner_disk.exists()
            html_body = aplicar_layout_email(
                corpo_ex, com_testeira=usar_testeira, com_imagem=com_b
            )
            pdf_p = pdf_disk if anexar_pdf and pdf_disk and pdf_disk.exists() else None
            img_p = banner_disk if com_b else None
            try:
                enviar_email_avancado(
                    SMTP_HOST,
                    SMTP_PORT,
                    SMTP_USER,
                    SMTP_PASSWORD,
                    FROM_EMAIL,
                    email_teste,
                    f"[TESTE] {assunto_ex}",
                    html_body,
                    imagem_inline=img_p,
                    anexo_pdf=pdf_p,
                )
                st.success(f"E-mail de teste enviado para {email_teste}!")
            except Exception as e:
                st.error(f"Falha ao enviar teste: {e}")

    st.divider()
    st.subheader("Envio da campanha")

    limite_teste = st.number_input("Máximo de e-mails nesta execução (0 = todos elegíveis)", min_value=0, value=0)

    if st.button("Enviar campanha", type="primary"):
        st.session_state["last_errors"] = []
        if not st.session_state.get("assunto_campanha") or not st.session_state.get("corpo_campanha"):
            st.error("Gere a mensagem com a IA ou preencha assunto e corpo.")
            return
        if not ok_smtp:
            st.error("Configure SMTP_USER e SMTP_PASSWORD.")
            return
        if "status_higiene" not in df_work.columns:
            st.error('Execute o pipeline ou "Validar domínios".')
            return
        if "blacklist_bloqueado" not in df_work.columns:
            st.error("Execute a blacklist ou o pipeline completo.")
            return
        if not cidades_alvo:
            st.warning("Selecione ao menos uma cidade alvo.")
            return

        filtrado = _filtrar_envio(df_work)
        filtrado = filtrado[filtrado[COL_CIDADE].astype(str).isin(cidades_alvo)]
        if filtrado.empty:
            st.warning("Nenhum destinatário elegível com os filtros atuais.")
            return

        assunto_tpl = st.session_state["assunto_campanha"]
        corpo_tpl = st.session_state["corpo_campanha"]

        fila = FilaEnvioInteligente()
        sucesso = 0
        erros = 0
        total = len(filtrado) if limite_teste == 0 else min(len(filtrado), int(limite_teste))

        com_b = usar_banner and banner_disk is not None and banner_disk.exists()
        pdf_p = pdf_disk if anexar_pdf and pdf_disk and pdf_disk.exists() else None
        img_p = banner_disk if com_b else None

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
                corpo = preparar_links_campanha(corpo, utm_campaign or "prospeccao", cidade)
                html_body = aplicar_layout_email(
                    corpo, com_testeira=usar_testeira, com_imagem=com_b
                )

                fila.aguardar_vaga_hora()
                try:
                    enviar_email_avancado(
                        SMTP_HOST,
                        SMTP_PORT,
                        SMTP_USER,
                        SMTP_PASSWORD,
                        FROM_EMAIL,
                        email,
                        assunto,
                        html_body,
                        imagem_inline=img_p,
                        anexo_pdf=pdf_p,
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

        st.session_state["ultimo_envio"] = {
            "sucesso": sucesso,
            "erros": erros,
            "total": total,
        }

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
