import streamlit as st
import pandas as pd
import pdfplumber
import io

st.set_page_config(page_title="Controle de Estoque - Caixa Tomada", layout="wide")

# 1. SISTEMA DE SEGURANÇA (SENHA DE ACESSO)
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acesso Restrito - Caixa Tomada")
    st.write("Por favor, insira a senha da empresa para acessar o sistema de contagem.")
    
    senha = st.text_input("Senha de Acesso:", type="password")
    botao_entrar = st.button("Entrar no Sistema")
    
    if botao_entrar:
        if senha == "caixatomada2026":
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Senha incorreta! Tente novamente ou fale com o administrador.")
    st.stop() # Interrompe a execução do código se não estiver autenticado

# --- A PARTIR DAQUI SÓ EXECUTAR SE ESTIVER AUTENTICADO ---

st.title("📦 Sistema de Contagem de Estoque Ultra")
st.write("Controle de inventário seguro, inteligente e sem papel.")

# Inicialização da memória interna (Session State)
if "df" not in st.session_state:
    st.session_state.df = None
if "current_file" not in st.session_state:
    st.session_state.current_file = None
if "alterados" not in st.session_state:
    st.session_state.alterados = set() # Guarda quais índices o usuário já mexeu

def extrair_dados_pdf(arquivo_pdf):
    dados = []
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                tabela = pagina.extract_table()
                if tabela:
                    for linha in tabela[1:]: # Pula o cabeçalho
                        if len(linha) >= 6:
                            estoque_str = str(linha[4]).replace('.', '').replace(',', '.') if linha[4] else "0"
                            try:
                                estoque_digital = float(estoque_str)
                            except ValueError:
                                estoque_digital = 0.0

                            dados.append({
                                "Produto": linha[3] if linha[3] else "Sem Nome",
                                "Unidade": linha[5] if linha[5] else "UN",
                                "Estoque Digital": estoque_digital
                            })
    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
    
    return pd.DataFrame(dados)

arquivo_upload = st.file_uploader("Carregue o relatório PDF do Greenapp", type=["pdf"])

if arquivo_upload is not None:
    if st.session_state.current_file != arquivo_upload.name:
        df_recuperado = extrair_dados_pdf(arquivo_upload)
        if not df_recuperado.empty:
            df_recuperado["Estoque Físico"] = df_recuperado["Estoque Digital"]
            df_recuperado["Observações"] = ""
            st.session_state.df = df_recuperado
            st.session_state.current_file = arquivo_upload.name
            st.session_state.alterados = set() # Limpa histórico de modificações para o novo arquivo
        else:
            st.session_state.df = None
            st.session_state.current_file = None
            st.warning("O sistema não encontrou produtos no PDF. Verifique o layout.")

    if st.session_state.df is not None:
        
        # Monitora o que o usuário alterou comparando o Físico com o Digital
        st.session_state.df["Diferença"] = st.session_state.df["Estoque Físico"] - st.session_state.df["Estoque Digital"]
        
        total_itens = len(st.session_state.df)
        itens_corretos = len(st.session_state.df[st.session_state.df["Diferença"] == 0])
        itens_divergentes = len(st.session_state.df[st.session_state.df["Diferença"] != 0])
        
        # 2. BARRA DE PROGRESSO VISÍVEL
        # Consideramos um item "conferido" se ele foi explicitamente validado ou modificado
        itens_conferidos = len(st.session_state.alterados)
        porcentagem = min(100, int((itens_conferidos / total_itens) * 100)) if total_itens > 0 else 0
        
        st.subheader(f"📋 Progresso da Contagem: {porcentagem}% concluído")
        st.progress(porcentagem / 100)
        st.caption(f"Você já digitou/conferiu {itens_conferidos} de um total de {total_itens} produtos.")

        # PAINEL DE MÉTRICAS (DASHBOARD)
        st.subheader("📊 Painel Geral")
        m1, m2, m3 = st.columns(3)
        m1.metric("Total de Itens", total_itens)
        m2.metric("✅ Itens Corretos", itens_corretos)
        m3.metric(
            "❌ Itens com Divergência", 
            itens_divergentes, 
            delta=f"{itens_divergentes} para ajustar" if itens_divergentes > 0 else None,
            delta_color="inverse"
        )

        st.divider()

        # BARRA DE PESQUISA E FILTROS
        st.subheader("🔍 Localizar e Contar Produtos")
        col_pesquisa, col_filtro = st.columns([2, 1])
        
        with col_pesquisa:
            termo_busca = st.text_input("Buscar produto pelo nome:", placeholder="Digite parte do nome...")
        
        with col_filtro:
            opcao_filtro = st.selectbox("Mostrar linhas:", ["Todos os itens", "Apenas divergentes", "Apenas corretos"])

        # Aplicando filtros visuais na tabela de exibição
        df_exibicao = st.session_state.df.copy()
        df_exibicao["ID_Original"] = df_exibicao.index # Mantém o rastreio do índice real
        
        if termo_busca:
            df_exibicao = df_exibicao[df_exibicao["Produto"].str.contains(termo_busca, case=False, na=False)]
        
        if opcao_filtro == "Apenas divergentes":
            df_exibicao = df_exibicao[df_exibicao["Diferença"] != 0]
        elif opcao_filtro == "Apenas corretos":
            df_exibicao = df_exibicao[df_exibicao["Diferença"] == 0]

        st.info("🔒 Segurança Ativa: Colunas de sistema bloqueadas. Edite apenas o 'Estoque Físico' e as 'Observações'.")

        # 3. ALERTA DE DEDO GORDO (ANÁLISE DE GRANDES DESVIOS)
        # Varre o banco para ver se há erros absurdos digitados (ex: variação maior que 50% para mais ou para menos)
        erros_gritantes = []
        for idx, row in st.session_state.df.iterrows():
            dig = row["Estoque Digital"]
            fis = row["Estoque Físico"]
            if dig > 0:
                variacao = abs(fis - dig) / dig
                if variacao >= 0.50 and fis != dig:
                    erros_gritantes.append(row["Produto"])
        
        if erros_gritantes:
            st.error(f"⚠️ **Aviso de Possível Erro de Digitação:** Identificamos uma variação muito alta (maior que 50%) em alguns itens (Ex: {erros_gritantes[0][:40]}...). Por favor, revise se não digitou um zero a mais!")

        # TABELA EDITÁVEL INTELIGENTE
        df_editado = st.data_editor(
            df_exibicao,
            column_config={
                "Produto": st.column_config.TextColumn("Produto", disabled=True, width="large"),
                "Unidade": st.column_config.TextColumn("Unidade", disabled=True, width="small"),
                "Estoque Digital": st.column_config.NumberColumn("Estoque Digital (Sistema)", disabled=True, format="%.2f"),
                "Estoque Físico": st.column_config.NumberColumn("Estoque Físico (Contado)", min_value=0.0, step=1.0, format="%.2f"),
                "Observações": st.column_config.TextColumn("Observações / Motivo", help="Dica: Indique o motivo da diferença aqui."),
                "Diferença": st.column_config.NumberColumn("Diferença", disabled=True, format="%+.2f"),
                "ID_Original": st.column_config.TextColumn("ID", disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )

        # Atualiza a memória global e regista o progresso do utilizador
        for idx, row in df_editado.iterrows():
            id_real = row["ID_Original"]
            
            # Se o utilizador alterou o valor padrão ou escreveu uma observação, consideramos "conferido"
            if row["Estoque Físico"] != st.session_state.df.at[id_real, "Estoque Digital"] or row["Observações"] != "":
                st.session_state.alterados.add(id_real)
                
            st.session_state.df.at[id_real, "Estoque Físico"] = row["Estoque Físico"]
            st.session_state.df.at[id_real, "Observações"] = row["Observações"]
        
        # Atualiza cálculos finais para o relatório
        st.session_state.df["Diferença"] = st.session_state.df["Estoque Físico"] - st.session_state.df["Estoque Digital"]
        st.session_state.df["Status"] = st.session_state.df["Diferença"].apply(lambda x: "✅ Bateu" if x == 0 else "❌ Divergente")

        st.divider()

        # EXPORTAÇÃO EXCEL (.XLSX)
        st.subheader("📋 Relatório Final para o Greenapp")
        divergencias = st.session_state.df[st.session_state.df["Diferença"] != 0]

        if divergencias.empty:
            st.success("Tudo perfeito! Sem divergências até o momento.")
        else:
            st.warning(f"Existem {len(divergencias)} produtos com diferenças em relação ao Greenapp.")
            
            df_relatorio = divergencias[["Produto", "Unidade", "Estoque Digital", "Estoque Físico", "Diferença", "Observações"]]
            st.dataframe(df_relatorio, hide_index=True, use_container_width=True)

            # Criando o Excel em bytes
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_relatorio.to_excel(writer, index=False, sheet_name="Ajustes")
            
            st.download_button(
                label="📥 Baixar Erros para o Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name="ajustes_estoque_caixatomada.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
