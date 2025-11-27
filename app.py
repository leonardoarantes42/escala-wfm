import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Escala WFM", layout="wide")

# --- CONEXÃO ROBUSTA (GSPREAD) ---
def conectar_google_sheets():
    # Define o escopo (o que o robô pode fazer)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Carrega as credenciais direto dos Segredos do Streamlit
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    
    # Autentica
    client = gspread.authorize(credentials)
    return client

# --- FUNÇÕES ---
@st.cache_data(ttl=60)
def carregar_dados():
    client = conectar_google_sheets()
    
    # URL da sua planilha
    url = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
    
    try:
        # Tenta abrir a planilha
        sh = client.open_by_url(url)
        # Pega a primeira aba (índice 0)
        worksheet = sh.get_worksheet(0)
        
        # Pega todos os dados
        dados = worksheet.get_all_values()
        
        # Transforma em DataFrame (assumindo linha 2 como cabeçalho, índice 1)
        # Se a linha 1 for cabeçalho, mude para headers = dados.pop(0)
        cabecalho = dados[1] # Linha 2 do Excel
        linhas = dados[2:]   # Da linha 3 para baixo
        
        df = pd.DataFrame(linhas, columns=cabecalho)
        df = df.dropna(subset=['NOME']) # Filtra vazios
        return df

    except gspread.exceptions.SpreadsheetNotFound:
        st.error("ERRO CRÍTICO: O Robô autenticou, mas não encontrou a planilha. Verifique se o e-mail do robô está na lista de compartilhamento.")
        st.stop()
    except Exception as e:
        st.error(f"Erro detalhado: {e}")
        st.stop()

def colorir_escala(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e'
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f'
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00'
    elif val == 'TR': color = 'background-color: #e8f0fe; color: #1967d2'
    return color

# --- INTERFACE ---
st.title("🔒 Escala WFM (GSpread)")

if st.button("🔄 Recarregar"):
    st.cache_data.clear()

try:
    df = carregar_dados()

    # Filtros
    st.sidebar.header("Filtros")
    
    # Garante que as colunas existem antes de criar filtro
    if 'LIDER' in df.columns:
        lideres = df['LIDER'].unique().tolist()
        sel_lider = st.sidebar.multiselect("Líder", lideres, default=lideres)
    
    if 'ILHA' in df.columns:
        ilhas = df['ILHA'].unique().tolist()
        sel_ilha = st.sidebar.multiselect("Ilha", ilhas, default=ilhas)
    
    busca = st.sidebar.text_input("Buscar Nome")

    df_filtrado = df.copy()
    
    if 'LIDER' in df.columns and sel_lider: 
        df_filtrado = df_filtrado[df_filtrado['LIDER'].isin(sel_lider)]
    if 'ILHA' in df.columns and sel_ilha: 
        df_filtrado = df_filtrado[df_filtrado['ILHA'].isin(sel_ilha)]
    if 'NOME' in df.columns and busca: 
        df_filtrado = df_filtrado[df_filtrado['NOME'].str.contains(busca, case=False)]

    st.write(f"Visualizando **{len(df_filtrado)}** analistas.")
    
    colunas_fixas = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']
    st.dataframe(
        df_filtrado.style.map(colorir_escala, subset=df_filtrado.columns.difference(colunas_fixas, sort=False)),
        height=600,
        use_container_width=True
    )

except Exception as e:
    st.error(f"Erro geral: {e}")
