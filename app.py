import streamlit as st
import pandas as pd

# Configuração da Página
st.set_page_config(page_title="Escala WFM", layout="wide")

# --- FUNÇÕES DE CARREGAMENTO ---
@st.cache_data(ttl=60)
def carregar_dados():
    # ID da sua planilha TESTE STREAMLIT
    sheet_id = "1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    # Lendo o CSV
    df = pd.read_csv(url, header=1)
    
    # Limpeza básica
    df = df.dropna(subset=['NOME'])
    
    return df

# --- FUNÇÃO DE ESTILO (AS CORES) ---
def colorir_escala(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    
    if val == 'T':
        color = 'background-color: #e6f4ea; color: #1e8e3e' # Verde claro
    elif val == 'F':
        color = 'background-color: #fce8e6; color: #c5221f' # Vermelho claro
    elif val == 'FR':
        color = 'background-color: #fff8e1; color: #f9ab00' # Amarelo (Férias)
    elif val == 'TR':
        color = 'background-color: #e8f0fe; color: #1967d2' # Azul (Treino)
    
    return color

# --- INTERFACE PRINCIPAL ---
st.title("📊 Visualizador de Escala - Dezembro")

try:
    df = carregar_dados()
    
    # --- BARRA LATERAL (FILTROS) ---
    st.sidebar.header("Filtros")
    
    lista_lideres = df['LIDER'].unique().tolist()
    lider_selecionado = st.sidebar.multiselect("Filtrar por Líder", lista_lideres, default=lista_lideres)
    
    lista_ilhas = df['ILHA'].unique().tolist()
    ilha_selecionada = st.sidebar.multiselect("Filtrar por Ilha", lista_ilhas, default=lista_ilhas)
    
    busca_nome = st.sidebar.text_input("Buscar Analista (Nome)")

    # --- APLICANDO FILTROS ---
    df_filtrado = df.copy()
    
    if lider_selecionado:
        df_filtrado = df_filtrado[df_filtrado['LIDER'].isin(lider_selecionado)]
        
    if ilha_selecionada:
        df_filtrado = df_filtrado[df_filtrado['ILHA'].isin(ilha_selecionada)]
        
    if busca_nome:
        df_filtrado = df_filtrado[df_filtrado['NOME'].str.contains(busca_nome, case=False)]

    # --- EXIBIÇÃO ---
    st.write(f"Mostrando **{len(df_filtrado)}** analistas.")
    
    colunas_fixas = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']
    
    # Renderiza a tabela
    st.dataframe(
        df_filtrado.style.map(colorir_escala, subset=df_filtrado.columns.difference(colunas_fixas)),
        height=600,
        use_container_width=True
    )

except Exception as e:
    st.error(f"Erro ao carregar a planilha. Detalhes: {e}")
