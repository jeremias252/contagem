import streamlit as st
import pandas as pd
import pdfplumber
import io

st.set_page_config(page_title="Controle de Estoque - Caixa Tomada", layout="wide")

# =========================================================================
# 1. MEMÓRIA CENTRAL COMPARTILHADA (Sincroniza todos os aparelhos)
# =========================================================================
@st.cache_resource
def obter_banco_central():
    return {"df": None, "current_file": None}

banco_central = obter_banco_central()

# =========================================================================
# 2. TELA DE LOGIN E CONTROLE DE ACESSO
# =========================================================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = ""
if "perfil" not in st.session_state:
    st.session_state.perfil = ""

if not st.session_state.autenticado:
    st.title("🔐 Portal de Acesso - Caixa Tomada")
    st.write("Identifique-se para iniciar a dupla contagem de inventário.")
    
    perfil = st.radio("Quem está acessando?", ["Equipe / Conferente", "Coordenador"])
    
    if perfil == "Coordenador":
        senha = st.text_input("Senha Master do Coordenador:", type="password")
        if st.button("Entrar como Coordenador"):
            if senha == "admincaixa":
                st.session_state.usuario = "Coordenador Geral"
                st.session_state.perfil = "Coordenador"
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Senha do Coordenador incorreta!")
                
    else: # Equipe
        nome_usuario = st.text_input("Seu Nome Completo:", placeholder="Ex: João Silva")
        senha = st.text_input("Senha da Equipe:", type="password")
        if st.button("Entrar para Contar"):
            if nome_usuario.strip() == "":
                st.warning("⚠️ Você precisa digitar seu nome para assinar suas contagens.")
            elif senha == "caixatomada2026":
                st.session_state.usuario = nome_usuario.strip().title()
                st.session_state.perfil = "Equipe"
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Senha da Equipe incorreta!")
                
    st.stop()

# =========================================================================
# 3. INTERFACE DO SISTEMA
# =========================================================================
st.title("📦 Sistema de Dupla Contagem - Caixa Tomada")

if st.session_state.perfil == "Coordenador":
    st.success(f"👑 Modo: **{st.session_state.usuario}** | Permissão total para gerenciar arquivos e auditar.")
else:
    st.info(f"👤 Modo: **Conferente ({st.session_state.usuario})** | Preencha as contagens e lembre-se de clicar em Salvar no final.")

# Função robusta de leitura do PDF
def extrair_dados_pdf(arquivo_pdf):
    dados = []
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                tabela = pagina.extract_table()
                if tabela:
                    for linha in tabela[1:]: 
                        linha_limpa = [item for item in linha if item is not None and str(item).strip() != ""]
                        if len(linha_limpa) >= 3:
                            produto = linha_limpa[-3]
                            estoque_bruto = linha_limpa[-2]
                            unidade = linha_limpa[-1]

                            estoque_str = str(estoque_bruto).replace('.', '').replace(',', '.')
                            try:
                                estoque_digital = float(estoque_str)
                            except ValueError:
                                estoque_digital = 0.0

                            dados.append({
                                "Produto": produto,
                                "Unidade": unidade,
                                "Estoque Digital": estoque_digital,
                                "Contagem 1": estoque_digital, 
                                "Quem Contou 1": "",
                                "Contagem 2": estoque_digital, 
                                "Quem Contou 2": "",
                                "Observações": ""
                            })
    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
    return pd.DataFrame(dados)

# PAINEL EXCLUSIVO DO COORDENADOR
if st.session_state.perfil == "Coordenador":
    st.subheader("⚙️ Painel de Controle do Coordenador")
    col_up, col_reset = st.columns([3, 1])
    
    with col_up:
        arquivo_upload = st.file_uploader("Carregar novo relatório PDF do Greenapp:", type=["pdf"])
        if arquivo_upload is not None:
            if banco_central["current_file"] != arquivo_upload.name:
                df_processado = extrair_dados_pdf(arquivo_upload)
                if not df_processado.empty:
                    banco_central["df"] = df_processado
                    banco_central["current_file"] = arquivo_upload.name
                    st.success(f"✅ Arquivo '{arquivo_upload.name}' liberado com sucesso!")
                    st.rerun()

    with col_reset:
        st.write("---")
        if st.button("🚨 ZERAR SISTEMA (LIMPAR TUDO)", help="Apaga completamente a memória do servidor para um novo inventário."):
            banco_central["df"] = None
            banco_central["current_file"] = None
            st.success("Memória do sistema totalmente limpa!")
            st.rerun()

# BLOQUEIO DE SEGURANÇA SE NÃO HOUVER ARQUIVO NO SERVIDOR
if banco_central["df"] is None:
    st.divider()
    st.warning("⏳ **Aguardando Liberação:** O coordenador ainda não realizou o upload do PDF ou limpou o sistema. Aguarde a liberação do arquivo para iniciar.")
    st.stop()

# =========================================================================
# 4. ÁREA DE CONTAGEM COMPARTILHADA (SÓ EXECUTA SE HOUVER TABELA)
# =========================================================================
df_mestre = banco_central["df"]

# Calcula a situação em tempo real de cada item
def calcular_status(row):
    if row["Contagem 1"] != row["Contagem 2"]:
        return "⚠️ Conflito (1 vs 2)"
    elif row["Contagem 1"] != row["Estoque Digital"]:
        return "❌ Erro no Sistema"
    else:
        return "✅ Bateu"

df_mestre["Status"] = df_mestre.apply(calcular_status, axis=1)

# Indicadores Globais Dinâmicos
total_itens = len(df_mestre)
itens_corretos = len(df_mestre[df_mestre["Status"] == "✅ Bateu"])
itens_conflito = len(df_mestre[df_mestre["Status"] == "⚠️ Conflito (1 vs 2)"])
itens_divergentes = len(df_mestre[df_mestre["Status"] == "❌ Erro no Sistema"])

# Progresso real calculado pelas assinaturas preenchidas
total_contagens_esperadas = total_itens * 2
contagens_feitas = df_mestre["Quem Contou 1"].str.strip().ne("").sum() + df_mestre["Quem Contou 2"].str.strip().ne("").sum()
porcentagem = min(100, int((contagens_feitas / total_contagens_esperadas) * 100)) if total_contagens_esperadas > 0 else 0

st.subheader(f"📈 Progresso da Auditoria: {porcentagem}% Concluído")
st.progress(porcentagem / 100)
st.caption(f"Relatório em andamento: **{banco_central['current_file']}** | {contagens_feitas} de {total_contagens_esperadas} conferências feitas.")

st.subheader("📊 Painel Estatístico")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total de Produtos", total_itens)
m2.metric("✅ 100% Corretos", itens_corretos)
m3.metric("⚠️ Em Conflito", itens_conflito)
m4.metric("❌ Divergentes", itens_divergentes)

st.divider()

# Barra de Pesquisa e Filtros Visuais
st.subheader("🔍 Localizar Itens no Galpão")
col_pesquisa, col_filtro = st.columns([2, 1])
with col_pesquisa:
    termo_busca = st.text_input("Buscar produto pelo nome:", placeholder="Digite parte do nome...")
with col_filtro:
    opcao_filtro = st.selectbox("Mostrar na tabela:", ["Todos os itens", "Apenas Conflitos", "Apenas Divergentes", "Apenas Corretos"])

# Filtra a tabela de exibição preservando os índices originais do banco mestre
df_exibicao = df_mestre.copy()

if termo_busca:
    df_exibicao = df_exibicao[df_exibicao["Produto"].str.contains(termo_busca, case=False, na=False)]
if opcao_filtro == "Apenas Conflitos":
    df_exibicao = df_exibicao[df_exibicao["Status"] == "⚠️ Conflito (1 vs 2)"]
elif opcao_filtro == "Apenas Divergentes":
    df_exibicao = df_exibicao[df_exibicao["Status"] == "❌ Erro no Sistema"]
elif opcao_filtro == "Apenas Corretos":
    df_exibicao = df_exibicao[df_exibicao["Status"] == "✅ Bateu"]

st.info("🔒 Segurança Ativa: Colunas cinzas estão bloqueadas. Digite seus valores e use o botão 'Salvar' abaixo da tabela.")

# Exibição segura da tabela interativa
df_editado = st.data_editor(
    df_exibicao,
    column_config={
        "Produto": st.column_config.TextColumn("Produto", disabled=True, width="large"),
        "Unidade": st.column_config.TextColumn("Unidade", disabled=True, width="small"),
        "Estoque Digital": st.column_config.NumberColumn("Digital (Greenapp)", disabled=True, format="%.2f"),
        "Contagem 1": st.column_config.NumberColumn("Contagem 1", min_value=0.0, step=1.0, format="%.2f"),
        "Quem Contou 1": st.column_config.TextColumn("Quem Contou 1", disabled=True),
        "Contagem 2": st.column_config.NumberColumn("Contagem 2", min_value=0.0, step=1.0, format="%.2f"),
        "Quem Contou 2": st.column_config.TextColumn("Quem Contou 2", disabled=True),
        "Observações": st.column_config.TextColumn("Observações / Motivo"),
        "Status": st.column_config.TextColumn("Situação", disabled=True),
    },
    hide_index=False,
    use_container_width=True
)

# =========================================================================
# BOTÃO DE SALVAMENTO SEGURO COM PROCESSAMENTO COMPLETO E TRAVAS
# =========================================================================
if st.button("💾 SALVAR E SINCRONIZAR CONTAGENS", type="primary", use_container_width=True):
    usuario_atual = st.session_state.usuario
    is_coordenador = st.session_state.perfil == "Coordenador"
    erros_travas = []
    
    for idx, row in df_editado.iterrows():
        orig_c1 = df_mestre.at[idx, "Contagem 1"]
        orig_c2 = df_mestre.at[idx, "Contagem 2"]
        orig_obs = df_mestre.at[idx, "Observações"]
        dono_c1 = df_mestre.at[idx, "Quem Contou 1"]
        dono_c2 = df_mestre.at[idx, "Quem Contou 2"]
        
        # Processa alterações na Contagem 1
        if row["Contagem 1"] != orig_c1:
            if dono_c1 != "" and dono_c1 != usuario_atual and not is_coordenador:
                erros_travas.append(f"'{row['Produto'][:30]}...': Contagem 1 pertence a {dono_c1}.")
            elif dono_c2 == usuario_atual and not is_coordenador:
                erros_travas.append(f"'{row['Produto'][:30]}...': Você já realizou a Contagem 2.")
            else:
                banco_central["df"].at[idx, "Contagem 1"] = row["Contagem 1"]
                banco_central["df"].at[idx, "Quem Contou 1"] = usuario_atual
                
        # Processa alterações na Contagem 2
        if row["Contagem 2"] != orig_c2:
            if dono_c2 != "" and dono_c2 != usuario_atual and not is_coordenador:
                erros_travas.append(f"'{row['Produto'][:30]}...': Contagem 2 pertence a {dono_c2}.")
            elif dono_c1 == usuario_atual and not is_coordenador:
                erros_travas.append(f"'{row['Produto'][:30]}...': Você já realizou a Contagem 1.")
            else:
                banco_central["df"].at[idx, "Contagem 2"] = row["Contagem 2"]
                banco_central["df"].at[idx, "Quem Contou 2"] = usuario_atual
                
        # Processa observações
        if row["Observações"] != orig_obs:
            banco_central["df"].at[idx, "Observações"] = row["Observações"]

    if erros_gritantes := [r["Produto"] for _, r in df_mestre.iterrows() if r["Estoque Digital"] > 0 and r["Contagem 1"] != r["Estoque Digital"] and (abs(r["Contagem 1"] - r["Estoque Digital"]) / r["Estoque Digital"]) >= 0.50]:
         st.warning(f"⚠️ Atenção: Há contagens com desvio maior que 50% em: {erros_gritantes[0][:40]}. Revise por segurança!")

    if erros_travas:
        for err in erros_travas[:3]: # Mostra os 3 primeiros erros de trava
            st.error(f"🔒 Alteração recusada em {err}")
        st.info("As demais linhas permitidas foram salvas. Recarregando dados...")
    else:
        st.success("🎉 Todas as alterações válidas foram transmitidas e guardadas com sucesso!")
    
    st.rerun()

# =========================================================================
# 5. GERADOR DO RELATÓRIO EXCEL CONSOLIDADO
# =========================================================================
st.divider()
st.subheader("📋 Relatório Consolidado de Auditoria (Excel)")
erros_e_conflitos = df_mestre[df_mestre["Status"] != "✅ Bateu"]

if erros_e_conflitos.empty:
    st.success("Nenhum erro ou conflito detectado até o momento!")
else:
    st.warning(f"Existem {len(erros_e_conflitos)} itens que possuem conflito de contagem ou erro em relação ao Greenapp.")
    df_relatorio = erros_e_conflitos[["Produto", "Unidade", "Estoque Digital", "Contagem 1", "Quem Contou 1", "Contagem 2", "Quem Contou 2", "Status", "Observações"]]
    st.dataframe(df_relatorio, hide_index=True, use_container_width=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_relatorio.to_excel(writer, index=False, sheet_name="Relatório de Auditoria")
    
    st.download_button(
        label="📥 Baixar Planilha de Erros e Conflitos (.xlsx)",
        data=buffer.getvalue(),
        file_name="auditoria_estoque_caixatomada.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
