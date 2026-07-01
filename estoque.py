import streamlit as st
import pandas as pd
import pdfplumber
import io

st.set_page_config(page_title="Controle de Estoque - Caixa Tomada", layout="wide")

st.title("📦 Sistema de Contagem de Estoque")
st.write("Faça o upload do relatório do Greenapp, insira a contagem física e exporte as divergências.")

def extrair_dados_pdf(arquivo_pdf):
    dados = []
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                tabela = pagina.extract_table()
                if tabela:
                    for linha in tabela[1:]: # Pula o cabeçalho
                        if len(linha) >= 6:
                            # Tratamento para transformar o texto do PDF em número decimal
                            estoque_str = str(linha[4]).replace('.', '').replace(',', '.') if linha[4] else "0"
                            try:
                                estoque_digital = float(estoque_str)
                            except ValueError:
                                estoque_digital = 0.0

                            dados.append({
                                "Produto": linha[3],
                                "Unidade": linha[5],
                                "Estoque Digital": estoque_digital
                            })
    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
    
    return pd.DataFrame(dados)

arquivo_upload = st.file_uploader("Carregue o relatório PDF do Greenapp", type=["pdf"])

if arquivo_upload is not None:
    df = extrair_dados_pdf(arquivo_upload)

    if not df.empty:
        df["Estoque Físico"] = df["Estoque Digital"] 
        
        st.subheader("📝 Preencha a Contagem Física")
        st.info("Dê um duplo clique na coluna 'Estoque Físico' para editar as quantidades.")
        
        df_editado = st.data_editor(
            df,
            column_config={
                "Estoque Físico": st.column_config.NumberColumn(
                    "Estoque Físico",
                    help="Digite a quantidade real contada",
                    min_value=0.0,
                    step=1.0,
                ),
                "Produto": st.column_config.TextColumn("Produto", disabled=True),
                "Unidade": st.column_config.TextColumn("Unidade", disabled=True),
                "Estoque Digital": st.column_config.NumberColumn("Estoque Digital", disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )

        df_editado["Diferença"] = df_editado["Estoque Físico"] - df_editado["Estoque Digital"]
        df_editado["Status"] = df_editado["Diferença"].apply(lambda x: "✅ Bateu" if x == 0 else "❌ Divergente")

        divergencias = df_editado[df_editado["Diferença"] != 0]

        st.divider()
        st.subheader("⚠️ Relatório de Divergências")
        
        if divergencias.empty:
            st.success("Parabéns! Nenhuma divergência encontrada. O estoque bateu perfeitamente.")
        else:
            st.warning(f"Foram encontrados {len(divergencias)} itens com quantidade divergente.")
            st.dataframe(divergencias, hide_index=True, use_container_width=True)

            csv = divergencias.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Relatório de Ajustes (CSV)",
                data=csv,
                file_name="ajustes_estoque.csv",
                mime="text/csv",
            )
    else:
        st.warning("O sistema não encontrou produtos no PDF. Verifique o layout.")
