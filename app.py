import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Escalas Turbi", 
    layout="wide", 
    page_icon="logo_turbi.png", 
    initial_sidebar_state="expanded"
)

# --- CSS: O SEGREDO DO LAYOUT FIXO ---
st.markdown("""
    <style>
        /* 1. REMOVE ESPAÇOS EM BRANCO DO TOPO */
        /* Isso resolve o problema do título ocupar muito espaço mesmo sendo pequeno */
        .block-container {
            padding-top: 1.5rem !important; /* Mínimo necessário */
            padding-bottom: 0rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        
        /* 2. TRAVAMENTO TOTAL DA PÁGINA (APP MODE) */
        /* Essa é a regra mágica. Ela proíbe a página inteira de rolar.
           Assim, o Título, Abas e KPIs nunca vão "subir". */
        [data-testid="stAppViewContainer"] {
            overflow: hidden !important;
        }
        
        /* Esconde barra de rolagem do navegador */
        ::-webkit-scrollbar { display: none; }
        
        /* 3. TABELA COM SCROLL INTERNO INTELIGENTE */
        .table-container {
            /* Calcula: Altura da Tela (100vh) - Cabeçalho (aprox 240px) */
            /* Se o título estiver cortando embaixo, aumente o 240px para 250px */
            height: calc(100vh - 240px); 
            overflow-y: auto; /* Permite rolar apenas aqui dentro */
            overflow-x: auto;
            display: block;
            border: 1px solid #444;
            border-radius: 4px;
            background-color: #0e1117; /* Fundo para evitar transparência */
        }
        
        /* Estilos da Tabela */
        table {
            width: 100%;
            border-collapse: separate; 
            border-spacing: 0;
            font-family: sans-serif;
            font-size: 11px;
        }
        th, td {
            padding: 4px 6px;
            text-align: center;
            border-bottom: 1px solid #444;
            border-right: 1px solid #444;
            white-space: nowrap;
        }
        
        /* Cabeçalho da Tabela Fixo */
        thead th {
            position: sticky;
            top: 0;
            background-color: #0e1117; 
            color: white;
            z-index: 10; /* Z-index alto para ficar por cima */
            border-bottom: 2px solid #666;
            height: 35px;
            font-size: 11px;
        }

        /* Primeira Coluna Fixa (NOME) */
        table td:first-child, table th:first-child {
            position: sticky;
            left: 0;
            background-color: #1c1e24; 
            z-index: 11; /* Maior que o header normal */
            border-right: 2px solid #666; 
            font-weight: bold;
            text-align: left;
            min-width: 140px;
        }
        /* Canto Superior Esquerdo (Cruzamento) */
        thead th:first-child {
            z-index: 12; /* O maior de todos */
            background-color: #0e1117;
        }

        /* Ajustes Modo Claro */
        @media (prefers-color-scheme: light) {
            .table-container { border: 1px solid #ddd; background-color: #fff; }
            th, td { border-bottom: 1px solid #ddd; border-right: 1px solid #ddd; }
            thead th { background-color: #f0f2f6; color: black; border-bottom: 2px solid #ccc; }
            table td:first-child, table th:first-child { background-color: #ffffff; border-right: 2px solid #ccc;}
            thead th:first-child { background-color: #f0f2f6; }
        }

        /* 4. KPIS MINIATURA */
        [data-testid="metric-container"] {
            padding: 4px 8px;
            height: 50px;
            border-radius: 6px;
            border: 1px solid #333;
            background-color: #1c1e24;
            justify-content: center !important;
        }
        [data-testid="stMetricLabel"] { font-size: 10px !important; margin-bottom: 0 !important; }
        [data-testid="stMetricValue"] { font-size: 18px !important; }
        @media (prefers-color-scheme: light) {
            [data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #ddd; }
        }

        /* 5. SIDEBAR: REMOVENDO ESPAÇOS EXTRAS */
        /* Aproxima o botão do logo */
        .custom-link-btn {
            display: block; width: 100%; padding: 8px; text-align: center;
            border: 1px solid #1f77b4; border-radius: 4px;
            font-size: 12px; 
            margin-top: 0px; /* Remove margem do topo */
            margin-bottom: 20px; 
            text-decoration: none; color: #1f77b4; font-weight: bold;
        }
        .custom-link-btn:hover { background-color: #1f77b4; color: white !important; }

        /* Rodapé Absoluto */
        .footer-simple {
            position: fixed; bottom: 0; left: 0; width: 336px;
            padding: 10px; border-top: 1px solid #444;
            background-color: #262730; color: #666; font-size: 10px; text-align: center; z-index: 99;
        }
        @media (prefers-color-scheme: light) {
            .footer-simple { background-color: #f0f2f6; border-top: 1px solid #ddd; }
        }
        
        /* Ajuste fino dos elementos do Streamlit para economizar espaço */
        h3 { font-size: 16px !important; margin: 0 !important; padding: 0 !important; padding-top: 5px !important;}
        .stCaption { margin-top: -5px !important; margin-bottom: 0 !important;}
        div[data-testid="stVerticalBlock"] > div { gap: 0.5rem !important; } /* Reduz espaço entre elementos verticais */
        
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
LINK_FORMULARIO = "https://docs.google.com/forms/u/0/d/e/1FAIpQLScWvMZ60ISW6RqF0_ZxN_hD5ugOCITUQRlqiFi249EvmLbXyQ/formResponse"

# --- CONEXÃO ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

# --- CARREGAMENTO ---
@st.cache_data(ttl=300)
def listar_abas_dim():
    client = conectar_google_sheets()
    sh = client.open_by_url(URL_PLANILHA)
    todas_abas = [ws.title for ws in sh.worksheets()]
    abas_dim = sorted([aba for aba in todas_abas if aba.startswith("DIM")])
    return abas_dim

def carregar_dados_aba(nome_aba):
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        if nome_aba == 'Mensal': worksheet = sh.get_worksheet(0)
        else: worksheet = sh.worksheet(nome_aba)

        dados = worksheet.get_all_values()
        
        indice_cabecalho = -1
        cabecalho_bruto = []
        for i, linha in enumerate(dados[:5]):
            linha_upper = [str(col).upper().strip() for col in linha]
            if "NOME" in linha_upper or "NOMES" in linha_upper:
                indice_cabecalho = i
                cabecalho_bruto = linha
                break
        
        if indice_cabecalho == -1: return None, None

        cabecalho_tratado = []
        contagem_cols = {}
        for col in cabecalho_bruto:
            col_str = str(col).strip().upper()
            if col_str == "NOMES": col_str = "NOME"
            if col_str in contagem_cols:
                contagem_cols[col_str] += 1
                novo_nome = f"{col_str}_fim"
                cabecalho_tratado.append(novo_nome)
            else:
                if col_str != "": contagem_cols[col_str] = 1
                cabecalho_tratado.append(col_str)

        linhas = dados[indice_cabecalho + 1:]   
        df = pd.DataFrame(linhas, columns=cabecalho_tratado)
        df = df.loc[:, df.columns != '']
        if 'ILHA' in df.columns: df = df[df['ILHA'].astype(str).str.strip() != '']
        if 'NOME' in df.columns: df = df[df['NOME'].astype(str).str.strip() != '']
        if nome_aba == 'Mensal': df = df.iloc[:, :39] 

        return df, worksheet
    except Exception: return None, None

# --- KPIS ---
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
    def juntar_linha(row): return "".join([str(val).upper() for val in row])
    resumo = df_dim[cols_horarios].apply(juntar_linha, axis=1)
    escalados_chat = resumo.str.contains('CHAT').sum()
    tem_folga = resumo.str.contains('F')
    eh_sup_emerg = df_dim['ILHA'].astype(str).str.contains('Suporte|Emergência|Emergencia', case=False, na=False)
    tem_trabalho = resumo.str.contains('CHAT|EMAIL|E-MAIL|P|TREINO|1:1|FINANCEIRO')
    folga_filtrada = ((tem_folga) & (~tem_trabalho) & (eh_sup_emerg)).sum()
    return {"Trabalhando": escalados_chat, "Folga": folga_filtrada}

def analisar_gargalos_dim(df_dim):
    cols_horarios = []
    for c in df_dim.columns:
        if ':' in c:
            try:
                hora = int(c.split(':')[0])
                if 9 <= hora <= 22: cols_horarios.append(c)
            except: pass
    if not cols_horarios: return None
    menor_chat_valor = 9999; menor_chat_hora = "-"; maior_pausa_valor = -1; maior_pausa_hora = "-"
    for hora in cols_horarios:
        coluna_limpa = df_dim[hora].astype(str).str.upper().str.strip()
        qtd_chat = coluna_limpa.eq('CHAT').sum()
        qtd_pausa = coluna_limpa.isin(['P', 'PAUSA']).sum()
        if qtd_chat < menor_chat_valor: menor_chat_valor = qtd_chat; menor_chat_hora = hora
        if qtd_pausa > maior_pausa_valor: maior_pausa_valor = qtd_pausa; maior_pausa_hora = hora
    return {"min_chat_hora": menor_chat_hora, "min_chat_valor": menor_chat_valor, "max_pausa_hora": maior_pausa_hora, "max_pausa_valor": maior_pausa_valor}

def filtrar_e_ordenar_dim(df, modo):
    df_f = df.copy()
    cols_h = [c for c in df.columns if ':' in c]
    if 'ENTRADA' in df_f.columns:
        df_f['SORT_TEMP'] = pd.to_datetime(df_f['ENTRADA'], format='%H:%M', errors='coerce')
    else: df_f['SORT_TEMP'] = pd.NaT

    if modo == "💬 Apenas Chat":
        mask = df_f[cols_h].apply(lambda row: row.astype(str).str.upper().str.contains('CHAT').any(), axis=1)
        df_f = df_f[mask].sort_values(by='SORT_TEMP', na_position='last')
    elif modo == "🚫 Apenas Folgas":
        def is_pure_folga(row):
            s = "".join([str(val).upper() for val in row])
            return 'F' in s and not any(x in s for x in ['CHAT', 'P', 'TREINO'])
        mask = df_f[cols_h].apply(is_pure_folga, axis=1)
        df_f = df_f[mask].sort_values(by='SORT_TEMP', na_position='last')

    return df_f.drop(columns=['SORT_TEMP'])

# --- ESTILIZAÇÃO HTML ---
def renderizar_tabela_html(df, modo_cores='diario'):
    def get_color(val):
        val = str(val).upper().strip()
        if modo_cores == 'mensal':
            if val == 'T': return 'background-color: #c9daf8; color: black'
            elif val == 'F': return 'background-color: #93c47d; color: black'
            elif val == 'AF': return 'background-color: #f4cccc; color: black'
        else: # diario
            if val == 'F': return 'background-color: #002060; color: white'
            elif 'CHAT' in val: return 'background-color: #d9ead3; color: black'
            elif 'PAUSA' in val or val == 'P': return 'background-color: #fce5cd; color: black'
            elif 'EMAIL' in val or 'E-MAIL' in val: return 'background-color: #bfe1f6; color: black'
            elif 'FINANCEIRO' in val: return 'background-color: #11734b; color: white'
            elif 'BACKOFFICE' in val: return 'background-color: #5a3286; color: white'
        return ''

    styler = df.style.map(get_color).hide(axis="index")
    html = styler.to_html()
    return f'<div class="table-container">{html}</div>'

# ================= MAIN APP =================

df_global, _ = carregar_dados_aba('Mensal')

# --- SIDEBAR COMPACTA ---
with st.sidebar:
    st.image("logo_turbi.png", width=110) 
    # LINK COLADO NO LOGO (Sem st.divider antes)
    st.markdown(f'<a href="{LINK_FORMULARIO}" target="_blank" class="custom-link-btn">📝 Alteração de folga/horário</a>', unsafe_allow_html=True)
    
    st.markdown("##### 🔍 Filtros")
    if df_global is not None:
        opcoes_lider = sorted(df_global['LIDER'].unique().tolist()) if 'LIDER' in df_global.columns else []
        opcoes_ilha = sorted(df_global['ILHA'].unique().tolist()) if 'ILHA' in df_global.columns else []
    else: opcoes_lider = []; opcoes_ilha = []

    sel_lider = st.multiselect("Líder", options=opcoes_lider, default=[])
    sel_ilha = st.multiselect("Ilha", options=opcoes_ilha, default=[])
    busca_nome = st.text_input("Buscar Nome")

    # Rodapé Absoluto
    st.markdown('<div class="footer-simple">Made by <b>Leonardo Arantes</b></div>', unsafe_allow_html=True)

# --- CABEÇALHO COMPACTO ---
# Ajuste fino das colunas
c_title, c_spacer, c_search = st.columns([2, 0.5, 1.2])
with c_title:
    st.markdown("### 🚙 Sistema de Escalas Turbi")
with c_search:
    hoje_display = datetime.now().strftime("%d/%m")
    texto_busca = st.text_input("Busca", value=hoje_display, label_visibility="collapsed")
    st.caption("Digite dia/mês (Ex: 04/12)")

aba_mensal, aba_diaria = st.tabs(["📅 Mensal", "⏱️ Diária"])

# ================= ABA MENSAL =================
with aba_mensal:
    if df_global is not None:
        df_mensal = df_global
        colunas_datas = [c for c in df_mensal.columns if '/' in c]
        
        dia_para_mostrar = texto_busca if texto_busca in colunas_datas else colunas_datas[0]
        
        kpis = calcular_kpis_mensal_detalhado(df_mensal, dia_para_mostrar)
        
        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1: st.metric("✅ No Chat", kpis["NoChat"])
        with kc2: st.metric("🛋️ Folgas", kpis["Folga"])
        with kc3: st.metric("🎧 Suporte", kpis["Suporte"])
        with kc4: st.metric("🚨 Emergência", kpis["Emergencia"])

        df_f = df_mensal.copy()
        if sel_lider: df_f = df_f[df_f['LIDER'].isin(sel_lider)]
        if sel_ilha: df_f = df_f[df_f['ILHA'].isin(sel_ilha)]
        if busca_nome: df_f = df_f[df_f['NOME'].str.contains(busca_nome, case=False)]

        cols_clean = [c for c in df_f.columns if c.upper().strip() not in ['EMAIL', 'E-MAIL', 'ADMISSÃO', 'ILHA', 'Z']]
        
        html_tabela = renderizar_tabela_html(df_f[cols_clean], 'mensal')
        st.markdown(html_tabela, unsafe_allow_html=True)

# ================= ABA DIÁRIA =================
with aba_diaria:
    abas = listar_abas_dim()
    
    if not abas:
        st.warning("Sem dados.")
    else:
        aba_selecionada = next((aba for aba in abas if texto_busca in aba), abas[0])
        
        df_dim, ws_dim = carregar_dados_aba(aba_selecionada)
        
        if df_dim is not None:
            analise = analisar_gargalos_dim(df_dim)
            resumo_dia = calcular_resumo_dia_dim(df_dim)
            
            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1: st.metric("👥 No Chat", resumo_dia["Trabalhando"])
            with kc2: st.metric("🛋️ Folgas", resumo_dia["Folga"])
            if analise:
                with kc3: st.metric("⚠️ -Chat", f"{analise['min_chat_hora']}", f"{analise['min_chat_valor']}", delta_color="inverse")
                with kc4: st.metric("☕ +Pausa", f"{analise['max_pausa_hora']}", f"{analise['max_pausa_valor']}", delta_color="off")
            
            df_dim_f = df_dim.copy()
            if sel_lider: df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha: df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome: df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            tipo = st.radio("Modo:", ["▦ Grade", "💬 Chat", "🚫 Folgas"], horizontal=True, label_visibility="collapsed")

            if tipo == "▦ Grade": df_exibicao = df_dim_f
            else: df_exibicao = filtrar_e_ordenar_dim(df_dim_f, "💬 Apenas Chat" if "Chat" in tipo else "🚫 Apenas Folgas")
            
            cols_v = [c for c in df_exibicao.columns if c.upper().strip() not in ['EMAIL', 'E-MAIL', 'ILHA', 'Z']]
            
            html_tabela_dim = renderizar_tabela_html(df_exibicao[cols_v], 'diario')
            st.markdown(html_tabela_dim, unsafe_allow_html=True)
