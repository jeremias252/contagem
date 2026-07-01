import streamlit as st
import pandas as pd
import pdfplumber
import io

st.set_page_config(page_title="Controle de Estoque - Caixa Tomada", layout="wide")

# =========================================================================
# 1. MEMÓRIA CENTRAL COMPARTILHADA
# =========================================================================
@st.cache_resource
def obter_banco_central():
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
    st.success(f"👑 Modo: **{st.session_state.usuario}** | Permissão total de gerenciamento.")
else:
    st.info(f"👤 Modo: **Conferente ({st.session_state.usuario})** | Suas alterações registrarão sua assinatura na respectiva contagem.")

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
                                "Contagem 1": estoque_digital, # Inicializa com o digital
                                "Quem Contou 1": "",
                                "Contagem 2": estoque_digital, # Inicializa com o digital
                                "Quem Contou 2": "",
                                "Observações": ""
                            })
    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
    return pd.DataFrame(dados)

# PAINEL DO COORDENADOR
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
                    st.success(f"✅ Arquivo '{arquivo_upload.name}' liberado para dupla contagem!")
                    st.rerun()

    with col_reset:
        st.write("---")
        if st.button("🚨 ZERAR SISTEMA"):
            banco_central["df"] = None
            banco_central["current_file"] = None
            banco_central["alterados"] = set()
            st.warning("O estoque central foi resetado!")
            st.rerun()

if banco_central["df"] is None:
    st.divider()
    st.warning("⏳ **Aguardando Liberação:** O coordenador ainda não carregou o relatório PDF do Greenapp.")
    st.stop()

# =========================================================================
# 4. ÁREA DE CONTAGEM COMPARTILHADA
# =========================================================================
df_mestre = banco_central["df"]

# Lógica de Status Inteligente para Dupla Contagem
def calcular_status(row):
    if row["Contagem 1"] != row["Contagem 2"]:
        return "⚠️ Conflito de Contagem"
    elif row["Contagem 1"] != row["Estoque Digital"]:
        return "❌ Divergente do Sistema"
    else:
        return "✅ Bateu"

df_mestre["Status"] = df_mestre.apply(calcular_status, axis=1)

total_itens = len(df_mestre)
itens_corretos = len(df_mestre[df_mestre["Status"] == "✅ Bateu"])
itens_conflito = len(df_mestre[df_mestre["Status"] == "⚠️ Conflito de Contagem"])
itens_divergentes = len(df_mestre[df_mestre["Status"] == "❌ Divergente do Sistema"])
itens_conferidos = len(banco_central["alterados"])
porcentagem = min(100, int((itens_conferidos / (total_itens * 2)) * 100)) if total_itens > 0 else 0

st.subheader(f"📈 Progresso da Auditoria Global: {porcentagem}% Concluído")
st.progress(porcentagem / 100)
st.caption(f"Arquivo: **{banco_central['current_file']}** | {itens_conferidos} de {total_itens * 2} contagens totais realizadas.")

st.subheader("📊 Resumo Estatístico do Inventário")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total de Produtos", total_itens)
m2.metric("✅ 100% Corretos", itens_corretos)
m3.metric("⚠️ Em Conflito (1 vs 2)", itens_conflito, delta=f"{itens_conflito} revisar" if itens_conflito > 0 else None, delta_color="off")
m4.metric("❌ Erros no Sistema", itens_divergentes, delta=f"{itens_divergentes} ajustar" if itens_divergentes > 0 else None, delta_color="inverse")

st.divider()

# Filtros
st.subheader("🔍 Filtros de Localização")
col_pesquisa, col_filtro = st.columns([2, 1])
with col_pesquisa:
    termo_busca = st.text_input("Buscar produto:", placeholder="Digite o nome do item...")
with col_filtro:
    opcao_filtro = st.selectbox("Mostrar na tabela:", ["Todos os itens", "Apenas Conflitos (1 vs 2)", "Apenas Divergentes do Sistema", "Apenas Corretos"])

df_exibicao = df_mestre.copy()
df_exibicao["ID_Original"] = df_exibicao.index

if termo_busca:
    df_exibicao = df_exibicao[df_exibicao["Produto"].str.contains(termo_busca, case=False, na=False)]
if opcao_filtro == "Apenas Conflitos (1 vs 2)":
    df_exibicao = df_exibicao[df_exibicao["Status"] == "⚠️ Conflito de Contagem"]
elif opcao_filtro == "Apenas Divergentes do Sistema":
    df_exibicao = df_exibicao[df_exibicao["Status"] == "❌ Divergente do Sistema"]
elif opcao_filtro == "Apenas Corretos":
    df_exibicao = df_exibicao[df_exibicao["Status"] == "✅ Bateu"]

st.info("💡 **Como Funciona:** Insira sua contagem na coluna 'Contagem 1' ou 'Contagem 2'. O sistema assinará seu nome na coluna ao lado automaticamente assim que você alterar o número.")

# Exibição da Tabela com Dupla Contagem
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
        "Status": st.column_config.TextColumn("Situação Atual", disabled=True),
        "ID_Original": None
    },
    hide_index=True,
    use_container_width=True
)

# SALVAMENTO E ASSINATURA AUTOMÁTICA POR COLUNA
for idx, row in df_editado.iterrows():
    id_real = row["ID_Original"]
    
    mudou_c1 = row["Contagem 1"] != df_mestre.at[id_real, "Contagem 1"]
    mudou_c2 = row["Contagem 2"] != df_mestre.at[id_real, "Contagem 2"]
    mudou_obs = row["Observações"] != df_mestre.at[id_real, "Observações"]
    
    if mudou_c1 or mudou_c2 or mudou_obs:
        banco_central["df"].at[id_real, "Contagem 1"] = row["Contagem 1"]
        banco_central["df"].at[id_real, "Contagem 2"] = row["Contagem 2"]
        banco_central["df"].at[id_real, "Observações"] = row["Observações"]
        
        if mudou_c1:
            banco_central["df"].at[id_real, "Quem Contou 1"] = st.session_state.usuario
            banco_central["alterados"].add(f"{id_real}_c1")
        if mudou_c2:
            banco_central["df"].at[id_real, "Quem Contou 2"] = st.session_state.usuario
            banco_central["alterados"].add(f"{id_real}_c2")
            
        st.rerun()

# RELATÓRIO EXCEL CONSOLIDADO
st.divider()
st.subheader("📋 Relatório Consolidado de Auditoria (Excel)")
erros_e_conflitos = df_mestre[df_mestre["Status"] != "✅ Bateu"]

if erros_e_conflitos.empty:
    st.success("Nenhum erro ou conflito detectado no momento!")
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
