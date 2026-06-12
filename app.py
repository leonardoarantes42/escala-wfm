import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import bcrypt
import time
import uuid
import unicodedata
import extra_streamlit_components as stx
import requests
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Escalas Turbi", 
    layout="wide", 
    page_icon="logo_turbi.png", 
    initial_sidebar_state="expanded"
)

# --- CSS: LAYOUT RESPONSIVO E COMPACTO (SEU CSS ORIGINAL) ---
st.markdown("""
    <style>
        /* 1. LAYOUT GERAL */
        section[data-testid="stSidebar"] .block-container {
            padding-top: 1.5rem !important;  /* Sobe os elementos para o topo */
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-bottom: 1rem !important;
        }

        /* 2. Controla o espaço ENTRE os componentes (Logo, Filtros, Botões) */
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.5rem !important; /* Diminui o buraco entre um item e outro */
        }
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
        .height-mensal { height: calc(100vh - 310px); }
        .height-diaria { height: calc(100vh - 330px); }
        .height-diaria-plantao { height: calc(100vh - 315px); }
        table { width: 100%; border-collapse: separate; border-spacing: 0; font-family: sans-serif; font-size: 11px; }
        
        /* AJUSTE DE LARGURA: min-width garante que as colunas do final não fiquem espremidas */
        th, td { 
            padding: 4px 6px; text-align: center; 
            border-bottom: 1px solid #444; border-right: 1px solid #444; 
            white-space: nowrap; 
            min-width: 70px; 
        }
        
        thead th { position: sticky; top: 0; background-color: #0e1117; color: white; z-index: 5; border-bottom: 2px solid #666; height: 35px; font-size: 11px; }
        
        /* Primeira coluna (Nomes) fica um pouco mais larga e fixa */
        table td:first-child, table th:first-child { 
            position: sticky; left: 0; background-color: #1c1e24; z-index: 6; 
            border-right: 2px solid #666; font-weight: bold; text-align: left; 
            min-width: 160px; 
        }
        thead th:first-child { z-index: 7; background-color: #0e1117; }

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
        :root {
            --primary-color: #1e3a8a !important;
            --background-color: #0e1117 !important;
            --secondary-background-color: #262730 !important;
            --text-color: #fafafa !important;
        }
        
        /* Força o fundo da aplicação inteira */
        .stApp {
            background-color: #0e1117 !important;
            color: #fafafa !important;
        }
        
        /* Correção específica para a Tabela (Dataframe) */
        /* Isso remove o fundo branco forçado das colunas fixas em Light Mode */
        [data-testid="stDataFrame"] {
            background-color: #0e1117 !important;
        }
        
        /* Garante que o texto dentro das tabelas seja legível */
        div[data-testid="stDataFrame"] * {
            color: #fafafa !important;
            background-color: #0e1117 !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
LINK_FORMULARIO = "https://docs.google.com/forms/u/0/d/e/1FAIpQLScWvMZ60ISW6RqF0_ZxN_hD5ugOCITUQRlqiFi249EvmLbXyQ/formResponse"
LINK_FORM_FERIAS = "https://docs.google.com/forms/d/e/1FAIpQLSfojdNvqnBvvMBHD6rkLyjXySQ8PJFT4qcI3_8FKzG2wVmQwQ/viewform"
LINK_FORM_DAYOFF = "https://docs.google.com/forms/d/e/1FAIpQLSfEJV517mWxn7lY5hduClsErjK39lIz_YNTcpQVq_HZBm4gvg/viewform"

# O Streamlit vai puxar do cofre invisível
GIST_ID = st.secrets["GIST_ID"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

# ==========================================
# 🚀 O NOVO MOTOR DE DADOS (PULL DO GITHUB)
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_gist_file(nome_do_arquivo):
    """Baixa um arquivo específico do nosso Data Lake no GitHub."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        resposta = requests.get(url, headers=headers)
        if resposta.status_code == 200:
            dados_gist = resposta.json()
            
            # Verifica se o arquivo que pedimos realmente existe lá
            if nome_do_arquivo not in dados_gist["files"]:
                st.error(f"Arquivo {nome_do_arquivo} não encontrado no Gist.")
                return {}
                
            arquivo_info = dados_gist["files"][nome_do_arquivo]
            
            # Se o JSON for gigante (> 1MB), pegamos a URL bruta
            if arquivo_info.get("truncated", False):
                raw_url = arquivo_info["raw_url"]
                raw_resp = requests.get(raw_url, headers=headers)
                conteudo_str = raw_resp.text
            else:
                conteudo_str = arquivo_info["content"]
                
            return json.loads(conteudo_str)
        else:
            st.error(f"Erro ao conectar no GitHub: {resposta.status_code}")
            return {}
    except Exception as e:
        st.error(f"🚨 Falha interna ao processar {nome_do_arquivo}: {e}")
        return {}

def normalizar_texto(texto):
    """Remove acentos e deixa maiúsculo (ex: LÍDER -> LIDER)"""
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto))
                  if unicodedata.category(c) != 'Mn').upper().strip()

@st.cache_data(ttl=600, show_spinner=False)
def listar_abas_dim():
    data = fetch_gist_file("escala_cx.json")
    dims = data.get("DIMs", {})
    return sorted(list(dims.keys()))

# 1. FUNÇÃO PESADA (Refatorada para ler da memória)
@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados_aba(nome_aba):
    data = fetch_gist_file("escala_cx.json")
    
    # Identifica se a requisição é de um Mês ou de um DIM
    dados = []
    if nome_aba in data.get("Meses", {}):
        dados = data["Meses"][nome_aba]
    elif nome_aba in data.get("DIMs", {}):
        dados = data["DIMs"][nome_aba]
    else:
        return None, None

    if not dados:
        return None, None

    try:
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
            # --- CORREÇÃO: Lista de palavras que não podem ser deletadas ---
            lista_separadores = ['FINANCEIRO', 'E-MAIL', 'ASSÍNCRONO', 'ASSINCRONO', 'FINANCEIRO ASSÍNCRONO', 'PLENO', 'STAFF', 'N2']
            
            # Condição 1: A ilha não é vazia
            mask_ilha_preenchida = df['ILHA'].astype(str).str.strip() != ''
            # Condição 2: O nome é um dos nossos separadores VIP
            mask_eh_separador = df['NOME'].astype(str).str.upper().str.strip().isin(lista_separadores)
            
            # Mantém a linha se ela passar na Condição 1 OU na Condição 2
            df = df[mask_ilha_preenchida | mask_eh_separador]

        # 4. LIMPEZA DE DADOS
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()

        if len(df.columns) > 35: 
            df = df.iloc[:, :40] 
            
        return df, None

    except Exception as e:
        print(f"Erro: {e}")
        return None, None

# 2. FUNÇÃO LEVE (Lê Pessoas)
@st.cache_data(ttl=600, show_spinner=False)
def carregar_lista_pessoas():
    data = fetch_gist_file("escala_cx.json")
    dados = data.get("Pessoas", [])
    if not dados: return [], []
    
    try:
        df = pd.DataFrame(dados)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        lideres = []
        ilhas = []
        
        col_lider = next((c for c in df.columns if 'LIDER' in c), None)
        if col_lider:
            lideres = sorted([str(x).strip() for x in df[col_lider].unique() if str(x).strip() != ''])
            
        col_ilha = next((c for c in df.columns if 'ILHA' in c), None)
        if col_ilha:
            ilhas = sorted([str(x).strip() for x in df[col_ilha].unique() if str(x).strip() != ''])
            
        return lideres, ilhas
    except Exception as e:
        print(f"Erro ao ler Pessoas: {e}")
        return [], []

# ==========================================
# FUNÇÃO PARA LER PLANTÃO FDS
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def carregar_plantao_dia(data_str):
    data = fetch_gist_file("escala_cx.json")
    dados = data.get("ESCALA 26 STAFF", [])
    if not dados or len(dados) < 3: return None
    
    try:
        for linha in dados:
            if len(linha) >= 7: 
                data_planilha = str(linha[1]).strip() 
                if data_planilha == data_str:
                    staff = str(linha[2]).strip()     
                    urgencia = str(linha[5]).strip()  
                    telefone = str(linha[6]).strip()  
                    
                    if staff or urgencia:
                        return {"staff": staff, "urgencia": urgencia, "telefone": telefone}
        return None
    except Exception as e:
        return None

# ==========================================
# FUNÇÕES DE CÁLCULO
# ==========================================
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
    def style_row(row):
        styles = []
        nome_linha = str(row['NOME']).upper().strip() if 'NOME' in row else ''
        eh_cabecalho = nome_linha in [
            'FINANCEIRO', 'E-MAIL', 'ASSÍNCRONO', 
            'PLENO', 'STAFF', 'N2'
        ]
        
        for col, val in row.items():
            val_str = str(val).upper().strip()
            style = ''
            
            if eh_cabecalho:
                style = 'background-color: #000000; color: white; font-weight: bold;'
            else:
                if val_str == 'FR': 
                    style = 'background-color: #ffffff; color: black'
                elif val_str == 'AF': 
                    style = 'background-color: #f4cccc; color: black'

                if modo_cores == 'mensal':
                    if val_str == 'T': style = 'background-color: #c9daf8; color: black'
                    elif val_str == 'F': style = 'background-color: #93c47d; color: black'
                else:
                    if val_str == 'F': style = 'background-color: #002060; color: white'
                    elif val_str == 'RT': style = 'background-color: #e6cff2; color: black'
                    elif val_str == 'REEMBOLSOS': style = 'background-color: #d4edbc; color: black'
                    elif 'CHAT' in val_str: style = 'background-color: #d9ead3; color: black'
                    elif 'PAUSA' in val_str or val_str == 'P': style = 'background-color: #fce5cd; color: black'
                    elif 'EMAIL' in val_str or 'E-MAIL' in val_str: style = 'background-color: #bfe1f6; color: black'
                    elif 'FINANCEIRO' in val_str: style = 'background-color: #11734b; color: white'
                    elif 'BACKOFFICE' in val_str: style = 'background-color: #5a3286; color: white'
        
            styles.append(style)
        return styles

    styler = df.style.apply(style_row, axis=1)
    return f'<div class="table-container {classe_altura}">{styler.hide(axis="index").to_html()}</div>'

# ================= SISTEMA DE LOGIN (VIA COOKIES 🍪) =================

def get_cookie_manager():
    return stx.CookieManager(key="turbi_cookie_manager_v2")

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

if not st.session_state.get("logado", False) and "startup_check" not in st.session_state:
    with st.spinner("🔄 Iniciando sistema..."):
        time.sleep(1)
        st.session_state["startup_check"] = True
        st.rerun()

params = st.query_params
usuario_url = params.get("u")
senha_url = params.get("k")

token_cookie = cookies.get("turbi_token")
ignorar_cookie = st.session_state.get("logout_just_happened", False)

if token_cookie and not st.session_state.get("logado", False) and not ignorar_cookie:
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

# 3. Se ainda não logou (mesmo após esperar), mostra Login
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

    # --- CORREÇÃO GHOSTING: Container Vazio para o Login ---
    login_container = st.empty()

    if not login_aprovado:
        # Colocamos tudo do login DENTRO desse container
        with login_container.container():
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                ("### 🔒 Acesso Sistema de Escalas Turbi")
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
        # --- LIMPADOR ATIVADO: Apaga a tela de login fisicamente antes de avançar ---
        login_container.empty()
        
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

impor_sessao_unica(st.session_state["usuario"])

# ================= APP PRINCIPAL =================

opcoes_lider, opcoes_ilha = carregar_lista_pessoas()

# --- SIDEBAR ---
with st.sidebar:
    # 🌟 NOVO: Logo funcionando como "Avatar" no lugar do emoji
    c_logo, c_nome = st.columns([1, 4])
    
    with c_logo:
        # Tamanho ajustado (ex: 40px) para ficar um pouco maior que um emoji, mas ainda como ícone
        st.image("logo_turbi.png", width=40)
        
    with c_nome:
        # Alinhamento vertical (margin-top) para o nome não ficar "voando" em relação à imagem
        (f"<div style='margin-top: 8px; font-size: 16px;'><b>{st.session_state.get('nome', 'Visitante')}</b></div>", unsafe_allow_html=True)
        
    st.divider() # Linha sutil nativa do Streamlit
    
    # 🌟 FEATURE FLAG: ÁREA VIP DE DESENVOLVIMENTO
    usuario_logado = st.session_state.get("usuario", "")
    desenvolvedores = ["leonardo.arantes@turbi.com.br"] 
    
    if usuario_logado in desenvolvedores:
        ("<h4 style='margin-bottom: 30px;'>🧭 Navegação</h4>", unsafe_allow_html=True)
        menu_navegacao = st.radio(
            "Selecione a tela:",
            ["📅 Escala SC", "📊 Meus Resultados"],
            label_visibility="collapsed"
        )
        st.divider()
    else:
        # Para a operação normal, o menu nem aparece
        menu_navegacao = "📅 Escala SC"
    
    ("#### 🔍 Filtros")
    
    sel_lider = st.multiselect("Líder", options=opcoes_lider)
    sel_ilha = st.multiselect("Ilha", options=opcoes_ilha)
    
    busca_nome = st.text_input("Buscar Nome")
    ("<hr style='margin: 10px 0px;'>", unsafe_allow_html=True)
    
    # Links Úteis
    (f'<a href="{LINK_FORM_FERIAS}" target="_blank" class="custom-link-btn">🏖️ Solicitação de Férias</a>', unsafe_allow_html=True)
    st.markdown(f'<a href="{LINK_FORM_DAYOFF}" target="_blank" class="custom-link-btn">🎂 Solicitação de Day Off (Aniversário)</a>', unsafe_allow_html=True)
    st.markdown(f'<a href="{LINK_FORMULARIO}" target="_blank" class="custom-link-btn">📝 Alteração de folga/horário</a>', unsafe_allow_html=True)
    
    # Empurra o botão de Sair para o final
    st.markdown("<br>", unsafe_allow_html=True) 
    if st.button("🚪 Sair / Logout", type="secondary", use_container_width=True):
        try:
            cookie_manager.delete("turbi_token")
        except:
            pass
        
        st.session_state.clear()
        st.session_state["logout_just_happened"] = True
        
        st.query_params.clear()
        time.sleep(0.5)
        st.rerun()

    st.markdown('<div class="footer-simple">Made by <b>Leonardo Arantes</b></div>', unsafe_allow_html=True)

# ==========================================
# 🖥️ ROTEADOR DE TELAS
# ==========================================

# 🚨 IMPORTANTE: Lembre-se de mudar aqui também para Escala SC!
if menu_navegacao == "📅 Escala SC":
    
    # --- HEADER DA ESCALA ---
    c_title, _, c_search = st.columns([2, 0.5, 1.2])
    with c_title: st.markdown("### 🚙 Sistema de Escalas Turbi")
    with c_search:
        data_sel = st.date_input("Busca", value=datetime.now(), format="DD/MM/YYYY", label_visibility="collapsed")
        texto_busca = data_sel.strftime("%d/%m")
        st.caption(f"Filtrando: {texto_busca}")

    # --- ABAS INTELIGENTES ---
    abas = st.tabs(["📅 Visão Mensal", "⏱️ Visão Diária"])
    aba_mensal, aba_diaria = abas[0], abas[1]
    
    MAPA_MESES = {
        1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
        5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
        9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
    }
    
    with aba_mensal:
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
        # 1. Verifica se tem plantão hoje
        data_plantao_str = data_sel.strftime("%d/%m/%Y")
        plantao_hoje = carregar_plantao_dia(data_plantao_str)
        
        # 2. DECIDE A ALTURA DA TABELA: Se tem plantão, usa a classe menor
        classe_altura_dinamica = 'height-diaria-plantao' if plantao_hoje else 'height-diaria'
        
        if plantao_hoje:
            st.markdown(f"""
            <div style="background-color: #1c1e24; border: 1px solid #333; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; text-align: center;">
                <span style="font-size: 14px;">🚨 <b>PLANTÃO DE HOJE</b> &nbsp;|&nbsp; 
                <b>Supervisão:</b> {plantao_hoje['staff']} &nbsp;|&nbsp; 
                <b>Urgência:</b> {plantao_hoje['urgencia']} &nbsp;|&nbsp; 
                <b>📞 Telefone:</b> {plantao_hoje['telefone']}</span>
            </div>
            """, unsafe_allow_html=True)
    
        abas_dim = listar_abas_dim()
        aba_encontrada = next((a for a in abas_dim if texto_busca in a), None)
        
        if aba_encontrada:
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
                st.markdown(renderizar_tabela_html(df_exibicao[cols_v], 'diario', classe_altura_dinamica), unsafe_allow_html=True)
                
        else:
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
    
elif menu_navegacao == "📊 Meus Resultados":
    
    # --- HEADER DOS RESULTADOS ---
    st.markdown(f"### 📊 Painel de Performance: {st.session_state.get('nome', 'Visitante')}")
    st.caption("Acompanhe seus indicadores e sua evolução no Turbi Guide.")
    st.divider()
    
    # 1. Baixa o nosso pacote isolado de Métricas
    dados_metricas = fetch_gist_file("metricas_cx.json")
    
    if dados_metricas and "Resultados_Atuais" in dados_metricas:
        matriz_resultados = dados_metricas["Resultados_Atuais"]
        
        # 2. Rastreia dinamicamente onde está a linha de Cabeçalho (a que tem "E-MAIL")
        indice_cabecalho = -1
        for i, linha in enumerate(matriz_resultados[:10]):
            linha_upper = [str(x).upper().strip() for x in linha]
            if "E-MAIL" in linha_upper or "EMAIL" in linha_upper:
                indice_cabecalho = i
                cabecalho = linha_upper
                break
                
        if indice_cabecalho != -1:
            email_logado = st.session_state.get("usuario", "").strip().lower()
            linha_usuario = None
            
            # 3. Faz o PROCX no Python: Busca o analista exato na base
            for linha in matriz_resultados[indice_cabecalho+1:]:
                # Na Turbi Guide 2.0, E-MAIL é a coluna B (índice 1)
                if len(linha) > 1 and str(linha[1]).strip().lower() == email_logado:
                    linha_usuario = linha
                    break
            
            if linha_usuario:
                # ==========================================
                # 🎯 EXTRAÇÃO DINÂMICA (A MÁGICA DOS CABEÇALHOS)
                # ==========================================
                def buscar_valor_por_nome(nome_coluna):
                    try:
                        idx = cabecalho.index(nome_coluna)
                        return str(linha_usuario[idx]).strip()
                    except (ValueError, IndexError): # 🛡️ Blindagem contra colunas vazias
                        return "-"

                # 1. Busca os Nomes e Resultados Reais
                metrica_1_nome = cabecalho[4] if len(cabecalho) > 4 else "Métrica 1"
                metrica_1_val = linha_usuario[4] if len(linha_usuario) > 4 else "-"
                
                metrica_2_nome = cabecalho[5] if len(cabecalho) > 5 else "Métrica 2"
                metrica_2_val = linha_usuario[5] if len(linha_usuario) > 5 else "-"
                
                metrica_3_nome = cabecalho[6] if len(cabecalho) > 6 else "Métrica 3"
                metrica_3_val = linha_usuario[6] if len(linha_usuario) > 6 else "-"
                
                # 2. Busca as Novas Metas e Porcentagens que você criou no Sheets
                meta_1_val = buscar_valor_por_nome("META 1")
                meta_2_val = buscar_valor_por_nome("META 2")
                meta_3_val = buscar_valor_por_nome("META 3")
                
                ating_1_val = buscar_valor_por_nome("% ATINGIMENTO 1")
                ating_2_val = buscar_valor_por_nome("% ATINGIMENTO 2")
                ating_3_val = buscar_valor_por_nome("% ATINGIMENTO 3")

                # 3. Busca o consolidado final
                status_final = buscar_valor_por_nome("STATUSFINAL")
                bonus_final = buscar_valor_por_nome("BONIFICAÇÃO FINAL")
                qualidade = buscar_valor_por_nome("QUALIDADE")
                ncg = buscar_valor_por_nome("NCG")
                
                # ==========================================
                # 🎨 UI: RENDERIZAÇÃO DO DASHBOARD (O SHOW DE UX)
                # ==========================================
                
                # --- A) BANNER DE STATUS E BÔNUS ---
                cor_status = "#262730" # Cor padrão
                txt_status_upper = status_final.upper()
                
                if "SUPER TURBO" in txt_status_upper: cor_status = "#d100d1"   # Magenta
                elif "TURBO" in txt_status_upper: cor_status = "#1e3a8a"       # Azul Turbi
                elif "ACELERANDO" in txt_status_upper: cor_status = "#11734b"  # Verde Turbi
                elif "NEUTRO" in txt_status_upper: cor_status = "#b8860b"      # Dourado
                elif "ALERTA" in txt_status_upper: cor_status = "#8a1e1e"      # Vermelho
                
                st.markdown(f"""
                    <div style="background-color: {cor_status}; padding: 25px; border-radius: 8px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 4px 10px rgba(0,0,0,0.4);">
                        <div>
                            <div style="color: rgba(255,255,255,0.7); font-size: 13px; font-weight: bold; letter-spacing: 1px;">STATUS DO MÊS</div>
                            <div style="color: #fff; font-size: 36px; font-weight: 900; letter-spacing: 1px; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">{txt_status_upper}</div>
                        </div>
                        <div style="text-align: right; border-left: 1px solid rgba(255,255,255,0.2); padding-left: 25px;">
                            <div style="color: rgba(255,255,255,0.7); font-size: 13px; font-weight: bold; letter-spacing: 1px;">PROJEÇÃO DE BÔNUS</div>
                            <div style="color: #fff; font-size: 36px; font-weight: 900; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">{bonus_final}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                # --- B) MOTOR INTELIGENTE DOS SMART CARDS ---
                def draw_smart_card(titulo, real_str, meta_str, ating_str):
                    # Transforma os textos em números para o Python fazer as contas
                    def limpar_num(texto):
                        try: return float(str(texto).replace("%", "").replace(",", ".").strip())
                        except: return 0.0
                    
                    real_val = limpar_num(real_str)
                    meta_val = limpar_num(meta_str)
                    ating_val = limpar_num(ating_str)

                    # 1. Define Cores e Selos com base na Regra do Jogo
                    if ating_val >= 130:
                        cor_barra, tag_nivel = "#d100d1", "👑 SUPER TURBO"
                    elif ating_val >= 110:
                        cor_barra, tag_nivel = "#1e3a8a", "🚀 TURBO"
                    elif ating_val >= 70:
                        cor_barra, tag_nivel = "#11734b", "✅ ACELERANDO"
                    elif ating_val >= 30:
                        cor_barra, tag_nivel = "#b8860b", "⚠️ NEUTRO"
                    else:
                        cor_barra, tag_nivel = "#8a1e1e", "🚨 PISCA ALERTA"

                    # Limita a barra visualmente a 100% da caixa, mesmo se o cara fizer 130%
                    largura_visual = min(100, ating_val)
                    if largura_visual == 0: largura_visual = 2 # Mostra pelo menos uma pontinha

                    # 2. O Cérebro do Insight (Diferença para a Meta)
                    insight = ""
                    if ating_val >= 130:
                        insight = "🏆 Meta máxima atingida! Você é Super Turbo."
                    elif ating_val >= 100:
                        insight = f"🔥 Sensacional! Meta Acelerando ({meta_str}) já garantida."
                    else:
                        diff = abs(meta_val - real_val)
                        diff_str = f"{diff:g}".replace(".", ",") # Ex: 1.5 vira 1,5
                        t_upper = titulo.upper()
                        
                        if "TMO" in t_upper or "TMA" in t_upper:
                            insight = f"Falta reduzir {diff_str} min para bater a meta Acelerando."
                        elif "PRODUTIVIDADE" in t_upper:
                            insight = f"Faltam {diff_str} tickets para chegar na meta."
                        elif "DISPONIBILIDADE" in t_upper or "SLA" in t_upper:
                            insight = f"Faltam {diff_str}% para alcançar a meta Acelerando."
                        else:
                            insight = f"Faltam {diff_str} para a meta principal."

                    # 3. Desenho do Card HTML (🚨 SEM RECUO PARA NÃO VIRAR CÓDIGO)
                    return f"""<div style="background-color: #1c1e24; padding: 20px; border-radius: 8px; border: 1px solid #333; height: 100%; box-shadow: 0 4px 6px rgba(0,0,0,0.15); position: relative;">
<div style="position: absolute; top: 18px; right: 18px; font-size: 10px; font-weight: 800; color: {cor_barra}; background-color: {cor_barra}15; padding: 4px 8px; border-radius: 4px; border: 1px solid {cor_barra}40;">{tag_nivel}</div>
<div style="font-size: 11px; color: #999; margin-bottom: 5px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">{titulo}</div>
<div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 15px;">
<div style="font-size: 28px; color: #fff; font-weight: 900;">{real_str}</div>
<div style="font-size: 13px; color: #777; font-weight: bold;">/ {meta_str}</div>
</div>
<div style="width: 100%; background-color: #2b2d35; border-radius: 6px; height: 8px; margin-bottom: 8px;">
<div style="width: {largura_visual}%; background-color: {cor_barra}; height: 8px; border-radius: 6px; box-shadow: 0 0 8px {cor_barra}60;"></div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 11px; color: #aaa; margin-bottom: 15px; font-weight: bold;">
<span>0%</span>
<span style="color: {cor_barra};">{ating_str} Atingido</span>
</div>
<div style="font-size: 11.5px; color: #ccc; border-top: 1px dashed #444; padding-top: 12px; line-height: 1.4;">
💡 <i>{insight}</i>
</div>
</div>"""
                
                c1, c2, c3, c4 = st.columns(4)
                with c1: st.markdown(draw_smart_card(metrica_1_nome, metrica_1_val, meta_1_val, ating_1_val), unsafe_allow_html=True)
                with c2: st.markdown(draw_smart_card(metrica_2_nome, metrica_2_val, meta_2_val, ating_2_val), unsafe_allow_html=True)
                with c3: st.markdown(draw_smart_card(metrica_3_nome, metrica_3_val, meta_3_val, ating_3_val), unsafe_allow_html=True)
                
                # Card de Qualidade Modernizado (🚨 SEM RECUO PARA NÃO VIRAR CÓDIGO)
                card_qualidade = f"""<div style="background-color: #1c1e24; padding: 20px; border-radius: 8px; border: 1px solid #333; height: 100%; box-shadow: 0 4px 6px rgba(0,0,0,0.15); display: flex; flex-direction: column; justify-content: center;">
<div style="font-size: 11px; color: #999; margin-bottom: 5px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">QUALIDADE MENSAL</div>
<div style="font-size: 32px; color: #fff; font-weight: 900; margin-bottom: 15px;">{qualidade}</div>
<hr style="border: 0; height: 1px; background: #444; margin: 0 0 15px 0;">
<div style="background-color: #8a1e1e15; padding: 10px; border-radius: 6px; border-left: 4px solid #e74c3c;">
<div style="font-size: 12px; color: #e74c3c; font-weight: bold;">🚨 NCG (Não Conformidade):</div>
<div style="font-size: 16px; color: #fff; font-weight: bold;">{ncg} Registros</div>
</div>
</div>"""
                with c4: st.markdown(card_qualidade, unsafe_allow_html=True)
                
            else:
                st.info("Ops! Não encontramos resultados de performance consolidados para este usuário no ciclo atual.")
        else:
            st.error("Não foi possível carregar a estrutura de indicadores neste momento.")
    else:
        st.error("Serviço de métricas temporariamente indisponível.")
