import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Escala CX Turbi", layout="wide")

# --- CONEXÃO ROBUSTA (GSPREAD) ---
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(credentials)
    return client

# --- FUNÇÕES ---
def carregar_dados():
    client = conectar_google_sheets()
    # SUA PLANILHA (Pode manter o link fixo)
    url = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
    
    try:
        sh = client.open_by_url(url)
        worksheet = sh.get_worksheet(0) # Pega a primeira aba
        dados = worksheet.get_all_values()
        
        # Tratamento do cabeçalho (assumindo linha 2 como cabeçalho)
        cabecalho = dados[1] 
        linhas = dados[2:]   
        
        df = pd.DataFrame(linhas, columns=cabecalho)
        
        # Guardamos a worksheet no retorno para usar na hora de salvar
        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar: {e}")
        return None, None

def colorir_escala(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e' # Verde
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f' # Vermelho
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00' # Amarelo
    elif val == 'TR': color = 'background-color: #e8f0fe; color: #1967d2' # Azul
    return color

# --- INTERFACE ---
st.title("🔒 Escala CX Turbi")

# Carrega os dados (usamos session_state para não recarregar toda hora)
if 'df_dados' not in st.session_state:
    df, ws = carregar_dados()
    if df is not None:
        st.session_state['df_dados'] = df
        st.session_state['worksheet_obj'] = ws

# Botão de recarregar manual
if st.button("🔄 Atualizar Dados da Planilha"):
    df, ws = carregar_dados()
    st.session_state['df_dados'] = df
    st.session_state['worksheet_obj'] = ws
    st.rerun()

# --- ÁREA DE LOGIN DO LÍDER ---
st.sidebar.divider()
modo_edicao = st.sidebar.checkbox("Sou Líder (Habilitar Edição)")

pode_editar = False
if modo_edicao:
    senha = st.sidebar.text_input("Senha de Acesso", type="password")
    if senha == "turbi123": # <--- SUA SENHA AQUI
        pode_editar = True
        st.sidebar.success("Modo Edição ATIVO 🔓")
    elif senha:
        st.sidebar.error("Senha incorreta")

# --- FILTROS (Comuns a todos) ---
df_visualizacao = st.session_state.get('df_dados', pd.DataFrame()).copy()

if not df_visualizacao.empty:
    st.sidebar.header("Filtros")
    
    # Filtros Dinâmicos
    if 'LIDER' in df_visualizacao.columns:
        lideres = df_visualizacao['LIDER'].unique().tolist()
        sel_lider = st.sidebar.multiselect("Líder", lideres, default=lideres)
        if sel_lider: df_visualizacao = df_visualizacao[df_visualizacao['LIDER'].isin(sel_lider)]
        
    if 'ILHA' in df_visualizacao.columns:
        ilhas = df_visualizacao['ILHA'].unique().tolist()
        sel_ilha = st.sidebar.multiselect("Ilha", ilhas, default=ilhas)
        if sel_ilha: df_visualizacao = df_visualizacao[df_visualizacao['ILHA'].isin(sel_ilha)]

    busca = st.sidebar.text_input("Buscar Nome")
    if busca and 'NOME' in df_visualizacao.columns:
        df_visualizacao = df_visualizacao[df_visualizacao['NOME'].str.contains(busca, case=False)]

    st.write(f"Visualizando **{len(df_visualizacao)}** analistas.")
    
    colunas_fixas = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']

    # --- DECISÃO: MODO LEITURA OU MODO EDIÇÃO ---
    if pode_editar:
        st.info("💡 Você está no modo de edição. Clique nas células para alterar. Ao terminar, clique em 'Salvar Alterações'.")
        
        # Mostra a tabela editável
        df_editado = st.data_editor(
            df_visualizacao,
            height=600,
            use_container_width=True,
            num_rows="dynamic" # Permite adicionar linhas se precisar
        )
        
        # Botão de Salvar
        if st.button("💾 SALVAR ALTERAÇÕES NO GOOGLE SHEETS", type="primary"):
            try:
                # Lógica de Salvamento
                ws = st.session_state['worksheet_obj']
                
                # Atenção: Atualizar a planilha inteira requer cuidado.
                # Aqui vamos atualizar tudo baseado no que está na tela (cuidado com filtros!)
                # Se filtrar e salvar, pode apagar os outros dados se não fizermos o merge.
                # SOLUÇÃO SEGURA PARA FILTROS: 
                # O ideal é editar sem filtros ou atualizar apenas as células mudadas.
                # Para simplificar hoje: Avisamos para tirar os filtros antes de salvar ou
                # salvamos apenas se não houver filtro ativo.
                
                if len(df_editado) != len(st.session_state['df_dados']):
                    st.warning("⚠️ Você está vendo uma lista filtrada. Para salvar com segurança, remova os filtros antes de editar.")
                else:
                    st.write("⏳ Salvando... aguarde...")
                    
                    # Prepara os dados: Cabeçalho + Linhas
                    dados_finais = [df_editado.columns.values.tolist()] + df_editado.values.tolist()
                    
                    # Limpa a planilha antiga e cola a nova (A partir da linha 2, mantendo a linha 1 de dias da semana intacta se quiser, mas aqui vamos substituir da A2 para baixo)
                    # Para facilitar, vamos atualizar tudo a partir da célula A2 (assumindo que A1 é cabeçalho de dias)
                    
                    ws.update(dados_finais, 'A2') 
                    
                    st.success("✅ Sucesso! Planilha atualizada.")
                    # Atualiza o estado local
                    st.session_state['df_dados'] = df_editado
                    
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
                
    else:
        # Modo Apenas Leitura (Colorido)
        st.dataframe(
            df_visualizacao.style.map(colorir_escala, subset=df_visualizacao.columns.difference(colunas_fixas, sort=False)),
            height=600,
            use_container_width=True
        )

else:
    st.warning("Nenhum dado carregado.")
