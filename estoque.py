import streamlit as st
import pandas as pd
import pdfplumber
import io

st.set_page_config(page_title="Controle de Estoque - Caixa Tomada", layout="wide")

st.title("📦 Sistema de Contagem de Estoque Pro")
st.write("Carregue o relatório do Greenapp, faça a contagem física com segurança e exporte para Excel.")

# Inicialização da memória para evitar perda de dados se o ecrã atualizar
if "df" not in st.session_state:
    st.session_state.df = None
if "current_file" not in st.session_state:
    st.session_state.current_file = None

def extrair_dados_pdf(arquivo_pdf):
    dados = []
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                tabela = pagina.extract_table()
                if tabela:
                    for linha in tabela[1:]: # Pula o cabeçalho
                        if len(linha) >= 6:
                            # Tratamento de texto para número decimal
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
    # Se um PDF novo for carregado, inicia uma nova sessão de dados
    if st.session_state.current_file != arquivo_upload.name:
        df_recuperado = extrair_dados_pdf(arquivo_upload)
        if not df_recuperado.empty:
            df_recuperado["Estoque Físico"] = df_recuperado["Estoque Digital"]
            df_recuperado["Observações"] = ""
            st.session_state.df = df_recuperado
            st.session_state.current_file = arquivo_upload.name
        else:
            st.session_state.df = None
            st.session_state.current_file = None
            st.warning("O sistema não encontrou produtos no PDF. Verifique o layout.")

    if st.session_state.df is not None:
        # Recálculo contínuo do dataframe principal
        st.session_state.df["Diferença"] = st.session_state.df["Estoque Físico"] - st.session_state.df["Estoque Digital"]
        
        total_itens = len(st.session_state.df)
        itens_corretos = len(st.session_state.df[st.session_state.df["Diferença"] == 0])
        itens_divergentes = len(st.session_state.df[st.session_state.df["Diferença"] != 0])

        # 1. PAINEL DE MÉTRICAS (DASHBOARD)
        st.subheader("📊 Painel Geral de Contagem")
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

        # 2. BARRA DE PESQUISA E FILTROS
        st.subheader("🔍 Localizar e Contar Produtos")
        col_pesquisa, col_filtro = st.columns([2, 1])
        
        with col_pesquisa:
            termo_busca = st.text_input("Buscar produto pelo nome:", placeholder="Digite parte do nome (ex: Cabo, Tomada)...")
        
        with col_filtro:
            opcao_filtro = st.selectbox("Mostrar linhas:", ["Todos os itens", "Apenas divergentes", "Apenas corretos"])

        # Aplicando filtros visuais sem perder os dados globais
        df_exibicao = st.session_state.df.copy()
        
        if termo_busca:
            df_exibicao = df_exibicao[df_exibicao["Produto"].str.contains(termo_busca, case=False, na=False)]
        
        if opcao_filtro == "Apenas divergentes":
            df_exibicao = df_exibicao[df_exibicao["Diferença"] != 0]
        elif opcao_filtro == "Apenas corretos":
            df_exibicao = df_exibicao[df_exibicao["Diferença"] == 0]

        st.info("🔒 Segurança Ativa: Você só consegue editar as colunas 'Estoque Físico' e 'Observações'. As demais estão bloqueadas.")

        # 3. TABELA EDITÁVEL INTELIGENTE
        df_editado = st.data_editor(
            df_exibicao,
            column_config={
                "Produto": st.column_config.TextColumn("Produto", disabled=True, width="large"),
                "Unidade": st.column_config.TextColumn("Unidade", disabled=True, width="small"),
                "Estoque Digital": st.column_config.NumberColumn("Estoque Digital (Sistema)", disabled=True, format="%.2f"),
                "Estoque Físico": st.column_config.NumberColumn("Estoque Físico (Contado)", min_value=0.0, step=1.0, format="%.2f"),
                "Observações": st.column_config.TextColumn("Observações / Motivo", placeholder="Opcional: Ex. Quebrado..."),
                "Diferença": st.column_config.NumberColumn("Diferença", disabled=True, format="%+.2f"),
            },
            hide_index=True,
            use_container_width=True
        )

        # Salva o que foi editado de volta no cofre de dados (Session State)
        st.session_state.df.update(df_editado)
        
        # Último recálculo para gerar relatório exato
        st.session_state.df["Diferença"] = st.session_state.df["Estoque Físico"] - st.session_state.df["Estoque Digital"]
        st.session_state.df["Status"] = st.session_state.df["Diferença"].apply(lambda x: "✅ Bateu" if x == 0 else "❌ Divergente")

        st.divider()

        # 4. EXPORTAÇÃO EXCEL
        st.subheader("📋 Relatório Final para o Greenapp")
        divergencias = st.session_state.df[st.session_state.df["Diferença"] != 0]

        if divergencias.empty:
            st.success("Tudo perfeito! Sem divergências até o momento.")
        else:
            st.warning(f"Existem {len(divergencias)} produtos aguardando correção.")
            
            df_relatorio = divergencias[["Produto", "Unidade", "Estoque Digital", "Estoque Físico", "Diferença", "Observações"]]
            st.dataframe(df_relatorio, hide_index=True, use_container_width=True)

            # Criando e empacotando o ficheiro Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_relatorio.to_excel(writer, index=False, sheet_name="Ajustes")
            
            st.download_button(
                label="📥 Baixar Erros para o Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name="ajustes_estoque_caixatomada.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
