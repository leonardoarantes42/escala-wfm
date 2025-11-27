import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.set_page_config(page_title="Escala WFM", layout="wide")

# --- CONEXÃO SEGURA ---
# Isto conecta-se usando os segredos que configurou no painel
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES ---
def carregar_dados():
    # O read() lê a primeira aba por defeito. 
    # usecols ajuda a garantir que lemos tudo, ou pode ajustar conforme necessário.
    # header=1 mantém-se se a estrutura for a mesma (linha 2 é o cabeçalho)
    df = conn.read(header=1) 
    df = df.dropna(subset=['NOME'])
    return df

def colorir_escala(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e'
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f'
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00'
    elif val == 'TR': color = 'background-color: #e8f0fe; color: #1967d2'
    return color

# --- INTERFACE ---
st.title("🔒 Escala WFM (Modo Seguro)")

try:
    # Botão para atualizar dados manualmente (útil quando alguém edita na planilha)
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        
    df = carregar_dados()

    # Filtros
    st.sidebar.header("Filtros")
    lideres = df['LIDER'].unique().tolist()
    sel_lider = st.sidebar.multiselect("Líder", lideres, default=lideres)
    
    ilhas = df['ILHA'].unique().tolist()
    sel_ilha = st.sidebar.multiselect("Ilha", ilhas, default=ilhas)
    
    busca = st.sidebar.text_input("Buscar Nome")

    # Lógica de Filtro
    df_filtrado = df.copy()
    if sel_lider: df_filtrado = df_filtrado[df_filtrado['LIDER'].isin(sel_lider)]
    if sel_ilha: df_filtrado = df_filtrado[df_filtrado['ILHA'].isin(sel_ilha)]
    if busca: df_filtrado = df_filtrado[df_filtrado['NOME'].str.contains(busca, case=False)]

    st.write(f"Visualizando **{len(df_filtrado)}** registos.")
    
    # Exibição
    colunas_fixas = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']
    st.dataframe(
        df_filtrado.style.map(colorir_escala, subset=df_filtrado.columns.difference(colunas_fixas)),
        height=600,
        use_container_width=True
    )

except Exception as e:
    st.error(f"Erro na conexão: {e}")
