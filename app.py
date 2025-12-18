import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.express as px
import bcrypt
import time
import uuid
import unicodedata
import extra_streamlit_components as stx

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Escalas Turbi", 
    layout="wide", 
    page_icon="logo_turbi.png", 
    initial_sidebar_state="expanded"
)

# --- CSS: LAYOUT RESPONSIVO E COMPACTO ---
st.markdown("""
    <style>
        /* 1. LAYOUT GERAL */
        .block-container {
            padding-top: 3.8rem !important;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        section[data-testid="stSidebar"] + section {
            overflow: hidden !important;
        }
        
        section[data-testid="stSidebar"] {
            z-index: 99999 !important;
        }
        
       /* 2. TABELA */
        .table-container {
            overflow-y: auto; overflow-x: auto; display: block;
            border: 1px solid #444; border-radius: 4px; background-color: #0e1117;
        }
        .height-mensal { height: calc(100vh - 270px); }
        .height-diaria { height: calc(100vh - 300px); }
        .height-aderencia {
            height: calc(100vh - 1000px); 
            overflow-y: auto; position: relative;
            top: -30px; margin-bottom: -30px;
        }
        table { width: 100%; border-collapse: separate; border-spacing: 0; font-family: sans-serif; font-size: 11px; }
        
        /* AJUSTE DE LARGURA: min-width garante que as colunas do final não fiquem espremidas */
        th, td { 
            padding: 4px 6px; text-align: center; 
            border-bottom: 1px solid #444; border-right: 1px solid #444; 
            white-space: nowrap; 
            min-width: 70px; /* <--- NOVO: Largura mínima para todas as células */
        }
        
        thead th { position: sticky; top: 0; background-color: #0e1117; color: white; z-index: 5; border-bottom: 2px solid #666; height: 35px; font-size: 11px; }
        
        /* Primeira coluna (Nomes) fica um pouco mais larga e fixa */
        table td:first-child, table th:first-child { 
            position: sticky; left: 0; background-color: #1c1e24; z-index: 6; 
            border-right: 2px solid #666; font-weight: bold; text-align: left; 
            min-width: 160px; /* <--- NOVO: Largura fixa maior para nomes */
        }
        thead th:first-child { z-index: 7; background-color: #0e1117; }

        @media (prefers-color-scheme: light) {
            .table-container { border: 1px solid #ddd; }
            th, td { border-bottom: 1px solid #ddd; border-right: 1px solid #ddd; }
            thead th { background-color: #f0f2f6; color: black; border-bottom: 2px solid #ccc; }
            table td:first-child, table th:first-child { background-color: #ffffff; border-right: 2px solid #ccc;}
            thead th:first-child { background-color: #f0f2f6; }
            [data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #ddd; }
        }

        /* 3. KPIS */
        [data-testid="metric-container"] { padding: 4px 8px; height: 60px; border-radius: 6px; border: 1px solid #333; background-color: #1c1e24; justify-content: center !important; }
        [data-testid="stMetricLabel"] { font-size: 10px !important; margin-bottom: 0 !important; }
        [data-testid="stMetricValue"] { font-size: 18px !important; }
        h3 { font-size: 26px !important; margin: 0 !important; padding: 0 !important;}
        .stCaption { font-size: 10px !important; margin-top: -5px !important;}

        /* 4. EXTRAS */
        .custom-link-btn { display: block; width: 100%; padding: 8px; text-align: center; border: 1px solid #1f77b4; border-radius: 4px; font-size: 12px; margin-top: 0px; margin-bottom: 10px; text-decoration: none; color: #1f77b4; font-weight: bold; }
        .custom-link-btn:hover { background-color: #1f77b4; color: white !important; }
        .footer-simple { margin-top: 10px; padding-top: 10px; border-top: 1px solid #444; color: #666; font-size: 10px; text-align: center; }
        [data-testid="stTabs"] { margin-top: -40px !important; }
        [data-testid="stRadio"] { margin-top: -30px !important; }

        /* 5. REMOVER STATUS DE CARREGAMENTO (NOVIDADE) */
        /* Esconde o "Running..." do topo direito */
        [data-testid="stStatusWidget"] {
            visibility: hidden;
        }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1L1WbR0rQcIra7J8S9AUX0yhwT-2RO-O4GMxAjaaBqr8/edit?gid=1076760569#gid=1076760569"
LINK_FORMULARIO = "https://docs.google.com/forms/u/0/d/e/1FAIpQLScWvMZ60ISW6RqF0_ZxN_hD5ugOCITUQRlqiFi249EvmLbXyQ/formResponse"

# --- FUNÇÕES DE DADOS ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

@st.cache_data(ttl=300)
def listar_abas_dim():
    client = conectar_google_sheets()
    sh = client.open_by_url(URL_PLANILHA)
    todas_abas = [ws.title for ws in sh.worksheets()]
    return sorted([aba for aba in todas_abas if aba.startswith("DIM")])

def normalizar_texto(texto):
    """Remove acentos e deixa maiúsculo (ex: LÍDER -> LIDER)"""
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto))
                  if unicodedata.category(c) != 'Mn').upper().strip()

# 1. FUNÇÃO PESADA (Lê a planilha mensal/diária) - Cache de 10 min
@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados_aba(nome_aba):
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        
        try:
            worksheet = sh.worksheet(nome_aba)
        except gspread.WorksheetNotFound:
            return None, None 
            
        dados = worksheet.get_all_values()
        
        # 1. Localizar Cabeçalho
        indice_cabecalho = -1
        cabecalho_bruto = []
        
        for i, linha in enumerate(dados[:15]):
            linha_norm = [normalizar_texto(col) for col in linha]
            
            tem_nome = "NOME" in linha_norm or "NOMES" in linha_norm
            tem_lider = "LIDER" in linha_norm
            tem_horario = any("HORARIO" in col for col in linha_norm)
            
            if tem_nome and (tem_lider or tem_horario):
                indice_cabecalho = i
                cabecalho_bruto = linha 
                break
        
        if indice_cabecalho == -1: return None, None

        # 2. Tratamento do Cabeçalho
        cabecalho_tratado = []
        contagem_cols = {}
        for col in cabecalho_bruto:
            col_str = normalizar_texto(col) 
            if col_str == "NOMES": col_str = "NOME"
            
            if col_str in contagem_cols:
                contagem_cols[col_str] += 1
                cabecalho_tratado.append(f"{col_str} ") 
            else:
                if col_str != "": contagem_cols[col_str] = 1
                cabecalho_tratado.append(col_str)

        linhas = dados[indice_cabecalho + 1:]   
        df = pd.DataFrame(linhas, columns=cabecalho_tratado)
        df = df.loc[:, df.columns != ''] 
        
        # 3. FILTRAGEM
        if 'NOME' in df.columns: 
             df = df[df['NOME'].astype(str).str.strip() != '']

        if 'ILHA' in df.columns: 
            df = df[df['ILHA'].astype(str).str.strip() != '']

        # 4. LIMPEZA DE DADOS
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()

        if len(df.columns) > 35: 
            df = df.iloc[:, :40] 
            
        return df, worksheet

    except Exception as e:
        print(f"Erro: {e}")
        return None, None

# 2. NOVA FUNÇÃO LEVE (Lê apenas a lista de Pessoas) - Cache de 10 min
@st.cache_data(ttl=600, show_spinner=False)
def carregar_lista_pessoas():
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        try:
            ws = sh.worksheet("Pessoas")
        except:
            return [], []
        
        # Pega todos os dados
        dados = ws.get_all_records()
        df = pd.DataFrame(dados)
        
        # Normaliza nomes das colunas
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        lideres = []
        ilhas = []
        
        # Procura coluna de Líder (aceita "LIDER ATUAL" ou "LIDER")
        col_lider = next((c for c in df.columns if 'LIDER' in c), None)
        if col_lider:
            lideres = sorted([str(x).strip() for x in df[col_lider].unique() if str(x).strip() != ''])
            
        # Procura coluna de Ilha
        col_ilha = next((c for c in df.columns if 'ILHA' in c), None)
        if col_ilha:
            ilhas = sorted([str(x).strip() for x in df[col_ilha].unique() if str(x).strip() != ''])
            
        return lideres, ilhas
        
    except Exception as e:
        print(f"Erro ao ler Pessoas: {e}")
        return [], []

# ==========================================
# 1. FUNÇÃO ONLINE (Recupera Coluna M)
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados_online():
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        try:
            ws = sh.worksheet("Online")
        except:
            return None
            
        # Pega tudo como texto bruto (matriz)
        dados = ws.get_all_values()
        if not dados or len(dados) < 2: return None
        
        # Cria DataFrame ignorando cabeçalho original para usar índices
        df = pd.DataFrame(dados[1:])
        
        # SELEÇÃO POSICIONAL RÍGIDA
        # Coluna B = Índice 1 (Data)
        # Coluna M = Índice 12 (Total)
        if len(df.columns) <= 12:
            return None
            
        # Renomeia para facilitar
        df = df.rename(columns={1: 'Dia_Fixo', 12: 'Total_M'})
        
        # Tratamento da Coluna M (Valor)
        df['Total_M'] = df['Total_M'].astype(str).str.replace(',', '.', regex=False)
        def limpar_valor(x):
            try:
                x = str(x).strip()
                if not x: return 0.0
                return float(x)
            except:
                return 0.0
        df['Horas_Valor'] = df['Total_M'].apply(limpar_valor)
        
        # Tratamento da Coluna B (Data Texto)
        df['Dia_Str'] = df['Dia_Fixo'].astype(str).str.strip()
        
        return df
    except Exception as e:
        return None

# ==========================================
# 2. FUNÇÃO PAUSAS (Recupera Porcentagens)
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados_pausas():
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        try:
            ws = sh.worksheet("Pausas")
        except:
            return None
            
        dados = ws.get_all_values()
        if len(dados) > 0:
            headers = [str(h).strip() for h in dados[0]]
            df = pd.DataFrame(dados[1:], columns=headers)
        else:
            return None

        # Colunas Alvo
        cols_alvo = [
            'Total (menos e-mail e Projeto)', 
            '%Pessoal',                       
            '%Programacao',
            '%Pausas_Total'
        ]
        
        for c in cols_alvo:
            if c in df.columns:
                def limpar_e_multiplicar(x):
                    x_str = str(x).strip()
                    if not x_str: return 0.0
                    
                    # Remove % e troca vírgula
                    clean = x_str.replace('%', '').replace(',', '.')
                    
                    try:
                        val = float(clean)
                        # Se for decimal pequeno (ex: 0.14), multiplica por 100
                        if val <= 1.0 and val != 0.0:
                            return val * 100
                        return val
                    except:
                        return 0.0
                
                df[c] = df[c].apply(limpar_e_multiplicar)

        # Prepara a Data
        if 'Dia' in df.columns:
             df['Dia_Str'] = df['Dia'].astype(str).str.strip()
             df['Dia_Date'] = pd.to_datetime(df['Dia'], format="%d/%m/%Y", errors='coerce')

        return df
    except Exception as e:
        return None
        
@st.cache_data(ttl=600, show_spinner=False)
def carregar_mapa_lideres():
    """Cria um dicionário {Nome_Analista: Nome_Lider} usando a aba Pessoas"""
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        ws = sh.worksheet("Pessoas")
        dados = ws.get_all_records()
        df = pd.DataFrame(dados)
        
        # Normaliza colunas
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # Tenta achar as colunas certas
        col_nome = next((c for c in df.columns if 'NOME' in c), None)
        col_lider = next((c for c in df.columns if 'LIDER' in c), None)
        
        if col_nome and col_lider:
            # Cria o dicionário
            return pd.Series(df[col_lider].values, index=df[col_nome]).to_dict()
            
        return {}
    except:
        return {}

def calcular_picos_vales_mensal(df_mensal):
    cols_data = [c for c in df_mensal.columns if '/' in c]
    if not cols_data: return None
    if 'ILHA' in df_mensal.columns:
        mask = df_mensal['ILHA'].astype(str).str.contains('Suporte|Emergência|Emergencia', case=False, na=False)
        df_filtrado = df_mensal[mask]
    else: df_filtrado = df_mensal
    max_val = -1; max_dia = "-"; min_val = 9999; min_dia = "-"
    for dia in cols_data:
        qtd_t = df_filtrado[dia].astype(str).str.upper().str.strip().value_counts().get("T", 0)
        if qtd_t > max_val: max_val = qtd_t; max_dia = dia
        if qtd_t < min_val: min_val = qtd_t; min_dia = dia
    return {"max_dia": max_dia, "max_val": max_val, "min_dia": min_dia, "min_val": min_val}

def gerar_dados_aderencia(df_mensal):
    cols_data = [c for c in df_mensal.columns if '/' in c]
    dados_lista = []
    if 'ILHA' in df_mensal.columns:
        mask = df_mensal['ILHA'].astype(str).str.contains('Suporte|Emergência|Emergencia', case=False, na=False)
        df_proc = df_mensal[mask]
    else: df_proc = df_mensal
    for dia in cols_data:
        counts = df_proc[dia].astype(str).str.upper().str.strip().value_counts()
        qtd_t = counts.get("T", 0); qtd_af = counts.get("AF", 0); qtd_to = counts.get("TO", 0)
        dados_lista.append({"Data": dia, "Realizado (T)": qtd_t, "Afastado (AF)": qtd_af, "Turnover (TO)": qtd_to, "Planejado": qtd_t + qtd_af + qtd_to})
    return pd.DataFrame(dados_lista)

def calcular_kpis_mensal_detalhado(df_mensal, data_escolhida):
    metrics = {"NoChat": 0, "Folga": 0, "Suporte": 0, "Emergencia": 0}
    if data_escolhida in df_mensal.columns:
        metrics["Folga"] = df_mensal[data_escolhida].value_counts().get("F", 0)
        if 'ILHA' in df_mensal.columns:
            mask_trabalhando = df_mensal[data_escolhida] == 'T'
            mask_ilhas_chat = df_mensal['ILHA'].astype(str).str.contains('Suporte|Emergência|Emergencia', case=False, na=False)
            metrics["NoChat"] = len(df_mensal[mask_trabalhando & mask_ilhas_chat])
            df_t = df_mensal[mask_trabalhando]
            metrics["Suporte"] = df_t[df_t['ILHA'].str.contains("Suporte", case=False, na=False)].shape[0]
            metrics["Emergencia"] = df_t[df_t['ILHA'].str.contains("Emergência|Emergencia", case=False, na=False)].shape[0]
    return metrics

def calcular_resumo_dia_dim(df_dim):
    cols_horarios = [c for c in df_dim.columns if ':' in c]
    if not cols_horarios: return {"Trabalhando": 0, "Folga": 0}
    resumo = df_dim[cols_horarios].apply(lambda row: "".join([str(val).upper() for val in row]), axis=1)
    eh_sup_emerg = df_dim['ILHA'].astype(str).str.contains('Suporte|Emergência|Emergencia', case=False, na=False)
    tem_trabalho = resumo.str.contains('CHAT|EMAIL|E-MAIL|P|TREINO|1:1|FINANCEIRO')
    return {"Trabalhando": resumo.str.contains('CHAT').sum(), "Folga": ((resumo.str.contains('F')) & (~tem_trabalho) & (eh_sup_emerg)).sum()}

def analisar_gargalos_dim(df_dim):
    cols_horarios = [c for c in df_dim.columns if ':' in c]
    cols_horarios = [c for c in cols_horarios if 9 <= int(c.split(':')[0]) <= 22]
    if not cols_horarios: return None
    min_chat = 9999; min_h = "-"; max_pausa = -1; max_h = "-"
    for hora in cols_horarios:
        col = df_dim[hora].astype(str).str.upper().str.strip()
        qt_chat = col.eq('CHAT').sum(); qt_pausa = col.isin(['P', 'PAUSA']).sum()
        if qt_chat < min_chat: min_chat = qt_chat; min_h = hora
        if qt_pausa > max_pausa: max_pausa = qt_pausa; max_h = hora
    return {"min_chat_hora": min_h, "min_chat_valor": min_chat, "max_pausa_hora": max_h, "max_pausa_valor": max_pausa}

def filtrar_e_ordenar_dim(df, modo):
    df_f = df.copy()
    cols_h = [c for c in df.columns if ':' in c]
    df_f['SORT_TEMP'] = pd.to_datetime(df_f['ENTRADA'], format='%H:%M', errors='coerce') if 'ENTRADA' in df_f.columns else pd.NaT
    if modo == "💬 Apenas Chat":
        mask = df_f[cols_h].apply(lambda row: row.astype(str).str.upper().str.contains('CHAT').any(), axis=1)
        df_f = df_f[mask].sort_values(by='SORT_TEMP', na_position='last')
    elif modo == "🚫 Apenas Folgas":
        mask = df_f[cols_h].apply(lambda row: 'F' in "".join([str(v).upper() for v in row]) and not any(x in "".join([str(v).upper() for v in row]) for x in ['CHAT', 'P', 'TREINO']), axis=1)
        df_f = df_f[mask].sort_values(by='SORT_TEMP', na_position='last')
    return df_f.drop(columns=['SORT_TEMP'])

def renderizar_tabela_html(df, modo_cores='diario', classe_altura='height-diaria'):
    # Função que analisa a LINHA INTEIRA (row)
    def style_row(row):
        styles = []
        
        # 1. Verifica se é uma LINHA DE CABEÇALHO/DIVISÃO (Olhando a coluna NOME)
        # Se a coluna NOME tiver um desses valores, a linha toda fica preta
        nome_linha = str(row['NOME']).upper().strip() if 'NOME' in row else ''
        
        # Lista de divisores visuais
        eh_cabecalho = nome_linha in [
            'FINANCEIRO', 'E-MAIL', 'FINANCEIRO ASSÍNCRONO', 
            'PLENO', 'STAFF', 'N2'
        ]
        
        for col, val in row.items():
            val_str = str(val).upper().strip()
            style = ''
            
            # --- REGRA 1: CABEÇALHOS (Linha Preta) ---
            if eh_cabecalho:
                style = 'background-color: #000000; color: white; font-weight: bold;'
            
            # --- REGRA 2: SLOTS NORMAIS (Coloridos) ---
            else:
                # Regras Gerais (Valem para Mensal e Diário)
                if val_str == 'FR': 
                    style = 'background-color: #ffffff; color: black' # Branco pedido
                elif val_str == 'AF': 
                    style = 'background-color: #f4cccc; color: black' # Vermelho claro

                # Regras Específicas
                if modo_cores == 'mensal':
                    if val_str == 'T': style = 'background-color: #c9daf8; color: black'
                    elif val_str == 'F': style = 'background-color: #93c47d; color: black'
                else:
                    # Cores Diárias
                    if val_str == 'F': style = 'background-color: #002060; color: white'
                    elif val_str == 'RT': style = 'background-color: #e6cff2; color: black' # Lilás pedido
                    elif val_str == 'REEMBOLSOS': style = 'background-color: #d4edbc; color: black' # Verde claro pedido
                    
                    elif 'CHAT' in val_str: style = 'background-color: #d9ead3; color: black'
                    elif 'PAUSA' in val_str or val_str == 'P': style = 'background-color: #fce5cd; color: black'
                    
                    # Aqui resolvemos a "Separação":
                    # Como já passamos pelo 'if eh_cabecalho', se caiu aqui é porque é SLOT de horário
                    elif 'EMAIL' in val_str or 'E-MAIL' in val_str: style = 'background-color: #bfe1f6; color: black' # Azul claro
                    elif 'FINANCEIRO' in val_str: style = 'background-color: #11734b; color: white' # Verde escuro
                    elif 'BACKOFFICE' in val_str: style = 'background-color: #5a3286; color: white'
            
            styles.append(style)
        return styles

    # Aplica o estilo linha por linha
    styler = df.style.apply(style_row, axis=1)
    return f'<div class="table-container {classe_altura}">{styler.hide(axis="index").to_html()}</div>'

# ================= SISTEMA DE LOGIN (VIA COOKIES 🍪) =================

# 1. Gerenciador de Cookies (Sem cache para evitar erros de widget)
def get_cookie_manager():
    return stx.CookieManager(key="turbi_cookie_manager_v2")

# 2. Gerenciador de Sessões Ativas (Memória do Servidor)
@st.cache_resource(show_spinner=False)
def get_session_manager():
    return {}

def validar_senha(usuario, senha_digitada):
    try:
        dados_user = st.secrets["credentials"]["usernames"].get(usuario)
        if not dados_user: return False, None
        
        senha_correta = False
        if dados_user["password"] == senha_digitada: 
             senha_correta = True
        elif bcrypt.checkpw(senha_digitada.encode('utf-8'), dados_user["password"].encode('utf-8')):
             senha_correta = True
             
        if senha_correta:
            return True, dados_user
        return False, None
    except Exception: return False, None

def impor_sessao_unica(email):
    """Garante apenas 1 aba ativa por email"""
    manager = get_session_manager()
    
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
        manager[email] = st.session_state["session_id"]
    
    if manager.get(email) != st.session_state["session_id"]:
        st.warning("⚠️ Conexão desconectada. Esta conta foi aberta em outro local.")
        time.sleep(3)
        st.session_state.clear()
        st.rerun()
    
    manager[email] = st.session_state["session_id"]

# --- LÓGICA DE ENTRADA ---

cookie_manager = get_cookie_manager()
cookies = cookie_manager.get_all()

# Tenta pegar login da URL
params = st.query_params
usuario_url = params.get("u")
senha_url = params.get("k")

# 1. TENTA LOGIN VIA COOKIE (Recuperação de F5)
token_cookie = cookies.get("turbi_token")

if token_cookie and not st.session_state.get("logado", False):
    try:
        email_cookie = token_cookie.split("|")[0]
        if email_cookie in st.secrets["credentials"]["usernames"]:
            dados = st.secrets["credentials"]["usernames"][email_cookie]
            st.session_state.update({
                "logado": True, 
                "usuario": email_cookie, 
                "nome": dados["name"], 
                "roles": dados.get("roles", ["viewer"])
            })
            st.rerun()
    except:
        pass 

# 2. ANTI-FLASH
if not st.session_state.get("logado", False):
    if "auth_check_completed" not in st.session_state:
        with st.spinner("Verificando credenciais..."):
            st.session_state["auth_check_completed"] = True
            time.sleep(1)
            st.rerun()

# 3. Se ainda não logou, mostra Login
if not st.session_state.get("logado", False):
    login_aprovado = False
    email_login = ""
    dados_login = {}

    if usuario_url and senha_url:
        val, dados = validar_senha(usuario_url, senha_url)
        if val:
            login_aprovado = True
            email_login = usuario_url
            dados_login = dados
            st.query_params.clear()

    if not login_aprovado:
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown("### 🔒 Acesso Sistema de Escalas Turbi")
            i_user = st.text_input("E-mail", placeholder="ex: nome@turbi.com.br")
            i_pass = st.text_input("Senha", type="password")
            if st.button("Entrar", type="primary", use_container_width=True):
                val, dados = validar_senha(i_user.strip(), i_pass)
                if val:
                    login_aprovado = True
                    email_login = i_user.strip()
                    dados_login = dados
                else: st.error("Acesso negado.")
    
    if login_aprovado:
        st.session_state.update({
            "logado": True, 
            "usuario": email_login, 
            "nome": dados_login["name"], 
            "roles": dados_login.get("roles", ["viewer"])
        })
        
        token_seguro = f"{email_login}|{str(uuid.uuid4())}"
        cookie_manager.set("turbi_token", token_seguro, key="set_cookie", expires_at=datetime.now() + pd.Timedelta(days=1))
        
        time.sleep(0.5) 
        st.rerun()
    
    st.stop() 

# Se passou, está logado. Ativa guardião.
impor_sessao_unica(st.session_state["usuario"])

# ================= APP PRINCIPAL =================

# 1. Carrega APENAS as listas leves para os filtros (Muito mais rápido!)
opcoes_lider, opcoes_ilha = carregar_lista_pessoas()

# --- SIDEBAR ---
with st.sidebar:
    st.write(f"👤 **{st.session_state.get('nome', 'Visitante')}**")
    if st.button("Sair / Logout", type="secondary"):
        st.session_state.clear(); st.query_params.clear(); st.rerun()
    st.divider()
    
    st.image("logo_turbi.png", width=180) 
    
    st.markdown("#### 🔍 Filtros")
    
    sel_lider = st.multiselect("Líder", options=opcoes_lider)
    sel_ilha = st.multiselect("Ilha", options=opcoes_ilha)
    
    busca_nome = st.text_input("Buscar Nome")
    st.divider()
    st.markdown(f'<a href="{LINK_FORMULARIO}" target="_blank" class="custom-link-btn">📝 Alteração de folga/horário</a>', unsafe_allow_html=True)
    st.markdown('<div class="footer-simple">Made by <b>Leonardo Arantes</b></div>', unsafe_allow_html=True)

# --- HEADER ---
c_title, _, c_search = st.columns([2, 0.5, 1.2])
with c_title: st.markdown("### 🚙 Sistema de Escalas Turbi")
with c_search:
    data_sel = st.date_input("Busca", value=datetime.now(), format="DD/MM/YYYY", label_visibility="collapsed")
    texto_busca = data_sel.strftime("%d/%m")
    st.caption(f"Filtrando: {texto_busca}")

# --- ABAS INTELIGENTES ---
eh_admin = 'admin' in st.session_state.get('roles', [])
abas = st.tabs(["📅 Visão Mensal", "⏱️ Visão Diária", "📊 Aderência"] if eh_admin else ["📅 Visão Mensal", "⏱️ Visão Diária"])
aba_mensal, aba_diaria = abas[0], abas[1]
aba_aderencia = abas[2] if eh_admin else None

# --- CONTEÚDO ABAS ---
MAPA_MESES = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
}

with aba_mensal:
    # 1. Carregamento Dinâmico (Mês correto)
    mes_num = data_sel.month
    nome_aba_oficial = MAPA_MESES.get(mes_num)
    
    df_global, _ = carregar_dados_aba(nome_aba_oficial)

    if df_global is None:
        st.warning(f"⚠️ A aba **{nome_aba_oficial}** não foi encontrada.")
        st.markdown(f"""
            <div style="background-color: #1e1e1e; padding: 15px; border-radius: 5px; border-left: 5px solid #ffbd45;">
                <p>Para poupar recursos, mantemos apenas os meses ativos nesta planilha.</p>
                <p>O histórico completo pode ser acessado no Drive:</p>
                <a href="https://drive.google.com/drive/folders/1WeIKaV6OvFOsNHdWhCirOx-zZogwdyPd?usp=drive_link" target="_blank" class="custom-link-btn" style="width: 200px;">
                    📂 Acessar Histórico (Drive)
                </a>
            </div>
        """, unsafe_allow_html=True)
    else:
        colunas_datas = [c for c in df_global.columns if '/' in c]
        dia_show = texto_busca if texto_busca in colunas_datas else (colunas_datas[0] if colunas_datas else None)
        
        if dia_show:
            kpis = calcular_kpis_mensal_detalhado(df_global, dia_show)
            picos = calcular_picos_vales_mensal(df_global)
            
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            
            with k1: st.metric("✅ Escalados(Sup & Emerg)", kpis["NoChat"])
            with k2: st.metric("🛋️ Folgas(Sup & Emerg)", kpis["Folga"])
            with k3: st.metric("🎧 Escalados Suporte", kpis["Suporte"])
            with k4: st.metric("🚨 Escalados Emergência", kpis["Emergencia"])
            
            if picos:
                with k5: st.metric("📈 Pico(Sup & Emerg)", f"{picos['max_dia']}", f"{picos['max_val']}")
                with k6: st.metric("📉 Vale(Sup & Emerg)", f"{picos['min_dia']}", f"{picos['min_val']}", delta_color="inverse")

            df_f = df_global.copy()
            if sel_lider: df_f = df_f[df_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_f.columns: df_f = df_f[df_f['ILHA'].isin(sel_ilha)]
            if busca_nome: df_f = df_f[df_f['NOME'].str.contains(busca_nome, case=False)]
            
            cols_clean = [c for c in df_f.columns if c.upper().strip() not in ['EMAIL', 'E-MAIL', 'ADMISSAO', 'ILHA', 'Z']]
            st.markdown(renderizar_tabela_html(df_f[cols_clean], 'mensal', 'height-mensal'), unsafe_allow_html=True)
        else:
            st.warning("Não encontrei colunas de data nesta aba.")

with aba_diaria:
    abas_dim = listar_abas_dim()
    
    # Formata a busca para bater com o nome da aba (Ex: "16/12")
    # Tenta achar uma aba que contenha a data filtrada
    aba_encontrada = next((a for a in abas_dim if texto_busca in a), None)
    
    if aba_encontrada:
        # SE ACHAR, CARREGA NORMALMENTE
        df_dim, _ = carregar_dados_aba(aba_encontrada)
        
        if df_dim is not None:
            analise = analisar_gargalos_dim(df_dim)
            resumo = calcular_resumo_dia_dim(df_dim)
            
            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1: st.metric("👥 No Chat", resumo["Trabalhando"])
            with kc2: st.metric("🛋️ Folgas(Sup & Emerg)", resumo["Folga"])
            if analise:
                with kc3: st.metric("⚠️ Menos Chats", f"{analise['min_chat_hora']}", f"{analise['min_chat_valor']}", delta_color="inverse")
                with kc4: st.metric("☕ Mais Pausas", f"{analise['max_pausa_hora']}", f"{analise['max_pausa_valor']}", delta_color="off")
            
            df_dim_f = df_dim.copy()
            
            if sel_lider and 'LIDER' in df_dim_f.columns:
                df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_f.columns:
                df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_f.columns:
                df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            tipo = st.radio("Modo:", ["▦ Grade", "💬 Apenas Chat", "🚫 Apenas Folgas"], horizontal=True, label_visibility="collapsed")
            df_exibicao = df_dim_f if tipo == "▦ Grade" else filtrar_e_ordenar_dim(df_dim_f, tipo)
            
            cols_v = [c for c in df_exibicao.columns if c.upper().strip() not in ['EMAIL', 'E-MAIL', 'ILHA', 'Z']]
            st.markdown(renderizar_tabela_html(df_exibicao[cols_v], 'diario', 'height-diaria'), unsafe_allow_html=True)
            
    else:
        # SE NÃO ACHAR A ABA (MOSTRA O AVISO)
        st.warning(f"⚠️ A aba diária para **{texto_busca}** não foi encontrada.")
        st.markdown(f"""
            <div style="background-color: #1e1e1e; padding: 15px; border-radius: 5px; border-left: 5px solid #ffbd45;">
                <p>Para poupar recursos, mantemos apenas as abas ativas nesta planilha.</p>
                <p>O histórico completo pode ser acessado no Drive:</p>
                <a href="https://drive.google.com/drive/folders/1WeIKaV6OvFOsNHdWhCirOx-zZogwdyPd?usp=drive_link" target="_blank" class="custom-link-btn" style="width: 200px;">
                    📂 Acessar Histórico (Drive)
                </a>
            </div>
        """, unsafe_allow_html=True)

if eh_admin and aba_aderencia:
    with aba_aderencia:
        # --- CSS PARA DEIXAR TUDO COMPACTO ---
        st.markdown("""
            <style>
                [data-testid='stVerticalBlock'] {
                    gap: 0.5rem !important; 
                }
                [data-testid='stColumn'] {
                    gap: 0rem !important;
                }
            </style>
        """, unsafe_allow_html=True)

        # --- CARREGAMENTO ---
        df_pausas = carregar_dados_pausas()
        df_online = carregar_dados_online()
        
        data_str_filtro = data_sel.strftime("%d/%m/%Y")
        string_busca_total_pausa = f"{data_str_filtro} Total"

        # --- CÁLCULO DO PREVISTO ---
        qtd_prevista_pessoas = 0
        if df_global is not None:
            df_ad = gerar_dados_aderencia(df_global)
            cols_d = [c for c in df_global.columns if '/' in c]
            d_sel_fmt = data_sel.strftime("%d/%m")
            d_match = d_sel_fmt if d_sel_fmt in cols_d else (cols_d[0] if cols_d else None)
            if df_ad is not None and d_match:
                row_ad = df_ad[df_ad['Data'] == d_match].iloc[0] if not df_ad[df_ad['Data'] == d_match].empty else None
                if row_ad is not None:
                    qtd_prevista_pessoas = row_ad['Realizado (T)'] + row_ad['Afastado (AF)']

        # --- MÉTRICAS (KPIs) ---
        c_desvio, c_pausa = st.columns(2)
        
        # KPI 1: DESVIO %
        horas_previstas = qtd_prevista_pessoas * 9.8
        horas_realizadas = 0.0
        if df_online is not None and 'Dia_Str' in df_online.columns:
            mask_dia = df_online['Dia_Str'] == data_str_filtro
            mask_val = df_online['Horas_Valor'] > 0
            df_online_filt = df_online[mask_dia & mask_val]
            horas_realizadas = df_online_filt['Horas_Valor'].sum()
            
        pct_desvio = ((horas_realizadas / horas_previstas) - 1) * 100 if horas_previstas > 0 else 0
        
        with c_desvio:
            st.metric(
                "🎯 Desvio % (Real vs Previsto)", 
                f"{pct_desvio:+.1f}%", 
                f"Real: {horas_realizadas:.1f}h / Previsto: {horas_previstas:.1f}h"
            )
            # AVISO CONDICIONAL: Só aparece se for HOJE
            if data_sel == pd.Timestamp.now().date():
                st.caption("⚠️ Os dados do dia vigente podem não estar 100% atualizados.")

        # KPI 2: MÉDIA PAUSA
        media_improdutiva = 0
        col_improd = "Total (menos e-mail e Projeto)" 
        if df_pausas is not None and 'Dia_Str' in df_pausas.columns:
            row_total = df_pausas[df_pausas['Dia_Str'] == string_busca_total_pausa]
            if not row_total.empty and col_improd in df_pausas.columns:
                media_improdutiva = row_total.iloc[0][col_improd]
        
        with c_pausa:
            st.metric("🛋️ Média % Pausa Improdutiva", f"{media_improdutiva:.1f}%", delta_color="inverse")
            
        # DIVISOR
        st.markdown("<hr style='margin-top: 5px; margin-bottom: 5px;'>", unsafe_allow_html=True)

        # --- GRÁFICOS ---
        st.markdown("#### 📅 Visão Mensal & Detalhe")
        g1, g2 = st.columns(2)
        with g1:
            if df_global is not None:
                 fig_b = px.bar(df_ad, x='Data', y=['Realizado (T)', 'Afastado (AF)', 'Turnover (TO)'], text_auto='.0f', title="Evolução de Presença", color_discrete_map={'Realizado (T)': '#1e3a8a', 'Afastado (AF)': '#d32f2f', 'Turnover (TO)': '#000000'})
                 
                 fig_b.update_layout(
                     height=300, 
                     margin=dict(t=30, b=0, l=0, r=0), 
                     showlegend=True,
                     xaxis_title=None,
                     yaxis_title="Headcount", 
                     legend_title_text=None,
                     legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
                 )
                 st.plotly_chart(fig_b, use_container_width=True)
        with g2:
            if df_pausas is not None and col_improd in df_pausas.columns:
                df_trend = df_pausas.dropna(subset=['Dia_Date']).copy()
                df_trend = df_trend[
                    (df_trend['Dia_Date'].dt.month == data_sel.month) & 
                    (df_trend['Dia_Date'].dt.year == data_sel.year)
                ]
                if not df_trend.empty:
                    df_trend_gp = df_trend.groupby('Dia_Date')[col_improd].mean().reset_index()
                    df_trend_gp['Data_Curta'] = df_trend_gp['Dia_Date'].dt.strftime('%d/%m')
                    
                    fig_l = px.line(
                        df_trend_gp, x='Data_Curta', y=col_improd, 
                        title="Tendência Pausa (%)", markers=True
                    )
                    
                    fig_l.update_traces(line_color='#d32f2f', name="Pausa Improdutiva", showlegend=True)
                    fig_l.update_xaxes(type='category', tickangle=30)
                    
                    fig_l.update_layout(
                        height=300, 
                        margin=dict(t=30, b=0, l=0, r=0),
                        xaxis_title=None,
                        yaxis_title="Total (menos e-mail e Projeto)",
                        legend_title_text=None,
                        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
                    )
                    st.plotly_chart(fig_l, use_container_width=True)
                else:
                    st.info("Sem dados de pausa para este mês.")

        # --- TABELA DETALHADA ---
        if df_pausas is not None:
            mask_dia = df_pausas['Dia_Str'] == data_str_filtro
            mask_no_total = ~df_pausas['Dia_Str'].str.contains("Total", case=False, na=False)
            df_detalhe = df_pausas[mask_dia & mask_no_total].copy()
            
            if not df_detalhe.empty:
                col_pessoal = "%Pessoal"         
                col_prog = "%Programacao"        
                cols_show = ['Nome_Analista', col_improd, col_pessoal, col_prog]
                cols_show = [c for c in cols_show if c in df_detalhe.columns]
                
                if col_improd in df_detalhe.columns:
                    df_detalhe = df_detalhe.sort_values(by=col_improd, ascending=False)
                
                st.markdown(f"##### 🕵️ Detalhe por Analista ({len(df_detalhe)} pessoas)")
                st.dataframe(
                    df_detalhe[cols_show],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Nome_Analista": st.column_config.TextColumn("Analista", width="medium"),
                        col_improd: st.column_config.NumberColumn("Total Improdutivo (%)", format="%.2f"),
                        col_pessoal: st.column_config.NumberColumn("% Pessoal", format="%.2f"),
                        col_prog: st.column_config.NumberColumn("% Programação", format="%.2f")
                    }
                )
            else:
                st.info(f"Nenhum analista encontrado para o dia {texto_busca}.")
        else:
            st.error("Erro ao carregar dados de Pausa.")
