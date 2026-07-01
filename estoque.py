import streamlit as st
import pandas as pd
import pdfplumber
import io

st.set_page_config(page_title="Controle de Estoque - Caixa Tomada", layout="wide")

# =========================================================================
# 1. MEMÓRIA CENTRAL COMPARTILHADA (Sincroniza todos os celulares/PCs)
# =========================================================================
@st.cache_resource
def obter_banco_central():
    # Este cofre de dados é compartilhado entre todos os usuários que acessam o site
    return {"df": None, "current_file": None, "alterados": set()}

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
    st.write("Identifique-se para acessar o sistema de inventário.")
    
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
# 3. INTERFACE DO SISTEMA (PÓS-LOGIN)
# =========================================================================
st.title("📦 Sistema de Contagem Cooperativo - Caixa Tomada")

# Barra de status do usuário logado
if st.session_state.perfil == "Coordenador":
    st.success(f"👑 Modo: **{st.session_state.usuario}** | Você tem permissão para gerenciar arquivos e zerar o sistema.")
else:
    st.info(f"👤 Modo: **Conferente ({st.session_state.usuario})** | Suas contagens serão salvas com sua assinatura automaticamente.")

# Função de extração do PDF
def extrair_dados_pdf(arquivo_pdf):
    dados = []
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                tabela = pagina.extract_table()
                if tabela:
                    for linha in tabela[1:]: 
                        if len(linha) >= 6:
                            estoque_str = str(linha[4]).replace('.', '').replace(',', '.') if linha[4] else "0"
                            try:
                                estoque_digital = float(estoque_str)
                            except ValueError:
                                estoque_digital = 0.0

                            dados.append({
                                "Produto": linha[3] if linha[3] else "Sem Nome",
                                "Unidade": linha[5] if linha[5] else "UN",
                                "Estoque Digital": estoque_digital,
                                "Estoque Físico": estoque_digital, # Começa igual ao digital
                                "Observações": "",
                                "Conferente": ""
                            })
    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
    return pd.DataFrame(dados)

# -------------------------------------------------------------------------
# PAINEL EXCLUSIVO DO COORDENADOR (UPLOAD E RESET)
# -------------------------------------------------------------------------
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
                    banco_central["alterados"] = set()
                    st.success(f"✅ Arquivo '{arquivo_upload.name}' carregado e transmitido para a equipe!")
                    st.rerun()

    with col_reset:
        st.write("---")
        if st.button("🚨 ZERAR SISTEMA", help="Apaga o PDF atual e todas as contagens feitas pela equipe para iniciar um novo ano."):
            banco_central["df"] = None
            banco_central["current_file"] = None
            banco_central["alterados"] = set()
            st.warning("O estoque central foi resetado com sucesso!")
            st.rerun()

# -------------------------------------------------------------------------
# VERIFICAÇÃO DE DADOS CARREGADOS (BLOQUEIO PARA A EQUIPE)
# -------------------------------------------------------------------------
if banco_central["df"] is None:
    st.divider()
    st.warning("⏳ **Aguardando Liberação:** O coordenador ainda não realizou o upload do relatório PDF do Greenapp. Por favor, aguarde para iniciar a contagem.")
    st.stop()

# =========================================================================
# 4. ÁREA DE CONTAGEM COMPARTILHADA (Visível para todos pós-upload)
# =========================================================================
# Sempre puxa os dados mais recentes do cofre central
df_mestre = banco_central["df"]
df_mestre["Diferença"] = df_mestre["Estoque Físico"] - df_mestre["Estoque Digital"]

# Cálculos para o Dashboard e Progresso
total_itens = len(df_mestre)
itens_corretos = len(df_mestre[df_mestre["Diferença"] == 0])
itens_divergentes = len(df_mestre[df_mestre["Diferença"] != 0])
itens_conferidos = len(banco_central["alterados"])
porcentagem = min(100, int((itens_conferidos / total_itens) * 100)) if total_itens > 0 else 0

# Exibição do Progresso Geral da Empresa
st.subheader(f"📈 Progresso Geral do Inventário: {porcentagem}% Concluído")
st.progress(porcentagem / 100)
st.caption(f"Arquivo Atual: **{banco_central['current_file']}** | {itens_conferidos} de {total_itens} itens auditados pela equipe.")

# Métricas em tempo real
st.subheader("📊 Números Atuais do Estoque")
m1, m2, m3 = st.columns(3)
m1.metric("Total de Produtos", total_itens)
m2.metric("✅ Itens Batendo", itens_corretos)
m3.metric("❌ Itens com Erro", itens_divergentes, delta=f"{itens_divergentes} correções" if itens_divergentes > 0 else None, delta_color="inverse")

st.divider()

# Barra de Pesquisa e Filtros Locais (Cada celular filtra o seu próprio visor)
st.subheader("🔍 Localizar Itens no Galpão")
col_pesquisa, col_filtro = st.columns([2, 1])

with col_pesquisa:
    termo_busca = st.text_input("Buscar produto pelo nome:", placeholder="Digite para filtrar na tela...")
with col_filtro:
    opcao_filtro = st.selectbox("Mostrar na tabela:", ["Todos os itens", "Apenas divergentes", "Apenas corretos"])

# Prepara os dados para serem mostrados na tabela de acordo com a busca do usuário
df_exibicao = df_mestre.copy()
df_exibicao["ID_Original"] = df_exibicao.index

if termo_busca:
    df_exibicao = df_exibicao[df_exibicao["Produto"].str.contains(termo_busca, case=False, na=False)]
if opcao_filtro == "Apenas divergentes":
    df_exibicao = df_exibicao[df_exibicao["Diferença"] != 0]
elif opcao_filtro == "Apenas corretos":
    df_exibicao = df_exibicao[df_exibicao["Diferença"] == 0]

# Alerta de Dedo Gordo
erros_gritantes = []
for idx, row in df_mestre.iterrows():
    dig = row["Estoque Digital"]
    fis = row["Estoque Físico"]
    if dig > 0 and fis != dig:
        if (abs(fis - dig) / dig) >= 0.50:
            erros_gritantes.append(row["Produto"])

if erros_gritantes:
    st.error(f"⚠️ **Alerta de Revisão:** Detectamos valores muito suspeitos (variação acima de 50%) no item: '{erros_gritantes[0][:45]}...'. Alguém pode ter digitado errado!")

st.info("🔒 Segurança Ativa: Colunas cinzas estão bloqueadas. Altere apenas o 'Estoque Físico' e as 'Observações'.")

# Tabela Interativa
df_editado = st.data_editor(
    df_exibicao,
    column_config={
        "Produto": st.column_config.TextColumn("Produto", disabled=True, width="large"),
        "Unidade": st.column_config.TextColumn("Unidade", disabled=True, width="small"),
        "Estoque Digital": st.column_config.NumberColumn("Digital (Greenapp)", disabled=True, format="%.2f"),
        "Estoque Físico": st.column_config.NumberColumn("Físico (Contado)", min_value=0.0, step=1.0, format="%.2f"),
        "Observações": st.column_config.TextColumn("Observações / Motivo", help="Digite justificativas aqui."),
        "Diferença": st.column_config.NumberColumn("Diferença", disabled=True, format="%+.2f"),
        "Conferente": st.column_config.TextColumn("Responsável", disabled=True),
        "ID_Original": None
    },
    hide_index=True,
    use_container_width=True
)

# SALVAMENTO INTELIGENTE (Salva na memória central apenas o que a pessoa alterou no seu visor)
for idx, row in df_editado.iterrows():
    id_real = row["ID_Original"]
    
    # Verifica se o valor digitado agora é diferente do que está gravado no banco mestre
    mudou_fisico = row["Estoque Físico"] != df_mestre.at[id_real, "Estoque Físico"]
    mudou_obs = row["Observações"] != df_mestre.at[id_real, "Observações"]
    
    if mudou_fisico or mudou_obs:
        # Atualiza a célula global
        banco_central["df"].at[id_real, "Estoque Físico"] = row["Estoque Físico"]
        banco_central["df"].at[id_real, "Observações"] = row["Observações"]
        
        # Carimba a assinatura de quem está logado nesta sessão!
        banco_central["df"].at[id_real, "Conferente"] = st.session_state.usuario
        banco_central["alterados"].add(id_real)
        
        # Recarrega a página para atualizar as métricas globais e a tabela de todo mundo
        st.rerun()

# -------------------------------------------------------------------------
# DOWNLOAD DO RELATÓRIO FINAL (Disponível para todos, mas focado no Coordenador)
# -------------------------------------------------------------------------
st.divider()
st.subheader("📋 Relatório consolidado para Ajuste no Greenapp")
divergencias = df_mestre[df_mestre["Diferença"] != 0]

if divergencias.empty:
    st.success("Estoque perfeito! Nenhuma divergência registrada até o momento.")
else:
    st.warning(f"Existem {len(divergencias)} itens com divergência aguardando correção.")
    
    df_relatorio = divergencias[["Produto", "Unidade", "Estoque Digital", "Estoque Físico", "Diferença", "Observações", "Conferente"]]
    st.dataframe(df_relatorio, hide_index=True, use_container_width=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_relatorio.to_excel(writer, index=False, sheet_name="Ajustes de Estoque")
    
    st.download_button(
        label="📥 Baixar Planilha Consolidada com Assinaturas (.xlsx)",
        data=buffer.getvalue(),
        file_name="ajustes_estoque_caixatomada_final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
