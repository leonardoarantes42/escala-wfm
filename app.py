import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Escalas Turbi", 
    layout="wide", 
    page_icon="logo_turbi.png", 
    initial_sidebar_state="expanded"
)

# --- CSS: DESIGN LIMPO E ALINHADO À ESQUERDA ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        /* Container dos KPIs */
        [data-testid="metric-container"] {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: flex-start !important;
            justify-content: center !important;
            text-align: left !important;
            background-color: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 10px 15px;
        }
        /* Título do KPI */
        [data-testid="stMetricLabel"] {
            width: 100%;
            justify-content: flex-start !important;
            font-size: 14px !important;
            color: #555;
        }
        /* Valor do KPI */
        [data-testid="stMetricValue"] {
            width: 100%;
            text-align: left !important;
            font-size: 26px !important;
            font-weight: bold;
            color: #1e3a8a;
        }
        @media (prefers-color-scheme: dark) {
            [data-testid="metric-container"] {
                background-color: #262730;
                border: 1px solid #444;
            }
            [data-testid="stMetricValue"] {
                color: #4dabf7;
            }
        }
        .stDataFrame { font-size: 13px; }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
COLUNAS_FIXAS_BACKEND = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']

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
        cabecalho_encontrado = []
        for i, linha in enumerate(dados[:5]):
            linha_upper = [str(col).upper().strip() for col in linha]
            if "NOME" in linha_upper or "NOMES" in linha_upper:
                indice_cabecalho = i
                cabecalho_encontrado = ['NOME' if str(col).upper().strip() == 'NOMES' else str(col).upper().strip() for col in linha]
                break
        
        if indice_cabecalho == -1:
            st.error(f"Erro: Cabeçalho não encontrado na aba '{nome_aba}'.")
            return None, None

        linhas = dados[indice_cabecalho + 1:]   
        df = pd.DataFrame(linhas, columns=cabecalho_encontrado)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # --- LIMPEZA CRÍTICA: MOSTRAR APENAS ILHAS PREENCHIDAS ---
        if 'ILHA' in df.columns:
            # Remove espaços em branco e filtra vazios
            df = df[df['ILHA'].astype(str).str.strip() != '']
            
        # Garante que NOME também não esteja vazio
        if 'NOME' in df.columns:
            df = df[df['NOME'].astype(str).str.strip() != '']

        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar aba '{nome_aba}': {e}")
        return None, None

# --- KPIS ---
def calcular_kpis_mensal_detalhado(df_mensal, data_escolhida):
    metrics = {"Trabalhando": 0, "Folga": 0, "Suporte": 0, "Emergencia": 0}
    if data_escolhida in df_mensal.columns:
        contagem = df_mensal[data_escolhida].value_counts()
        metrics["Trabalhando"] = contagem.get("T", 0)
        metrics["Folga"] = contagem.get("F", 0)
        if 'ILHA' in df_mensal.columns:
            df_dia = df_mensal[df_mensal[data_escolhida] == 'T']
            metrics["Suporte"] = df_dia[df_dia['ILHA'].str.contains("Suporte", case=False, na=False)].shape[0]
            metrics["Emergencia"] = df_dia[df_dia['ILHA'].str.contains("Emergência|Emergencia", case=False, na=False)].shape[0]
    return metrics

def calcular_resumo_dia_dim(df_dim):
    cols_horarios = [c for c in df_dim.columns if ':' in c]
    if not cols_horarios: return {"Trabalhando": 0, "Folga": 0}

    def juntar_linha(row):
        return "".join([str(val).upper() for val in row])

    # Cria um resumo da linha (ex: "CHAT CHAT P CHAT")
    resumo = df_dim[cols_horarios].apply(juntar_linha, axis=1)
    
    # 1. NO CHAT: Apenas quem tem a palavra CHAT na linha
    escalados_chat = resumo.str.contains('CHAT').sum()
    
    # 2. FOLGAS (SUPORTE E EMERGÊNCIA):
    # Regra: Tem 'F', não trabalha, E é de Suporte ou Emergência
    tem_trabalho = resumo.str.contains('CHAT|EMAIL|E-MAIL|P|TREINO|1:1|1X1|FINANCEIRO|REEMBOLSOS|BACKOFFICE')
    tem_folga = resumo.str.contains('F')
    eh_sup_emerg = df_dim['ILHA'].astype(str).str.contains('Suporte|Emergência|Emergencia', case=False, na=False)
    
    folga_filtrada = ((tem_folga) & (~tem_trabalho) & (eh_sup_emerg)).sum()
    
    return {"Trabalhando": escalados_chat, "Folga": folga_filtrada}

def analisar_gargalos_dim(df_dim):
    cols_horarios = []
    for c in df_dim.columns:
        if ':' in c:
            try:
                hora = int(c.split(':')[0])
                if 9 <= hora <= 22: # Filtro 09h as 22h
                    cols_horarios.append(c)
            except: pass
    if not cols_horarios: return None

    menor_chat_valor = 9999; menor_chat_hora = "-"
    maior_pausa_valor = -1; maior_pausa_hora = "-"

    for hora in cols_horarios:
        coluna_limpa = df_dim[hora].astype(str).str.upper().str.strip()
        qtd_chat = coluna_limpa.eq('CHAT').sum()
        qtd_pausa = coluna_limpa.isin(['P', 'PAUSA']).sum()

        if qtd_chat < menor_chat_valor:
            menor_chat_valor = qtd_chat
            menor_chat_hora = hora
        if qtd_pausa > maior_pausa_valor:
            maior_pausa_valor = qtd_pausa
            maior_pausa_hora = hora
            
    return {
        "min_chat_hora": menor_chat_hora, "min_chat_valor": menor_chat_valor,
        "max_pausa_hora": maior_pausa_hora, "max_pausa_valor": maior_pausa_valor
    }

def filtrar_e_ordenar_dim(df, modo):
    df_filtrado = df.copy()
    cols_horarios = [c for c in df.columns if ':' in c]
    
    if 'ENTRADA' in df_filtrado.columns:
        df_filtrado['SORT_TEMP'] = pd.to_datetime(df_filtrado['ENTRADA'], format='%H:%M', errors='coerce')
    else:
        df_filtrado['SORT_TEMP'] = pd.NaT

    if modo == "💬 Apenas Chat":
        # Filtra quem tem chat
        mask = df_filtrado[cols_horarios].apply(lambda row: row.astype(str).str.upper().str.contains('CHAT').any(), axis=1)
        df_filtrado = df_filtrado[mask]
        # Ordena por horário APENAS se for filtro de Chat
        df_filtrado = df_filtrado.sort_values(by='SORT_TEMP', na_position='last')
        
    elif modo == "🚫 Apenas Folgas":
        # Filtra quem tem folga
        def is_pure_folga(row):
            s = "".join([str(val).upper() for val in row])
            has_f = 'F' in s
            has_work = any(x in s for x in ['CHAT', 'EMAIL', 'E-MAIL', 'P', '1:1', 'TREINO', 'FINANCEIRO'])
            return has_f and not has_work
        mask = df_filtrado[cols_horarios].apply(is_pure_folga, axis=1)
        df_filtrado = df_filtrado[mask]
        # Ordena por horário (opcional, mas bom pra folgas)
        df_filtrado = df_filtrado.sort_values(by='SORT_TEMP', na_position='last')

    # Remove coluna temporária
    df_filtrado = df_filtrado.drop(columns=['SORT_TEMP'])
    
    return df_filtrado

# --- ESTILOS VISUAIS ---
def colorir_mensal(val):
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': return 'background-color: #c9daf8; color: black' 
    elif val == 'F': return 'background-color: #93c47d; color: black'
    elif val == 'AF': return 'background-color: #f4cccc; color: black'
    return ''

def colorir_diario(val):
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'F': return 'background-color: #002060; color: white'
    elif 'CHAT' in val: return 'background-color: #d9ead3; color: black'
    elif val == 'P' or 'PAUSA' in val: return 'background-color: #fce5cd; color: black'
    elif 'FINANCEIRO' in val: return 'background-color: #11734b; color: white'
    elif 'E-MAIL' in val or 'EMAIL' in val: return 'background-color: #bfe1f6; color: black'
    elif 'REEMBOLSOS' in val: return 'background-color: #d4edbc; color: black'
    elif 'BACKOFFICE' in val: return 'background-color: #5a3286; color: white'
    return ''

# ================= MAIN APP =================

with st.sidebar:
    st.image("logo_turbi.png", width=140) 
    st.divider()
    with st.expander("🔍 Filtros"):
        filtro_lider_placeholder = st.empty()
        filtro_ilha_placeholder = st.empty()
        busca_nome = st.text_input("Buscar Nome")

st.markdown("### 🚙 Sistema de Escalas Turbi") 

df_global, _ = carregar_dados_aba('Mensal')
aba_mensal, aba_diaria = st.tabs(["📅 Visão Mensal", "⏱️ Visão Diária"])

# ================= ABA MENSAL =================
with aba_mensal:
    df_mensal = df_global
    if df_mensal is not None:
        colunas_datas = [c for c in df_mensal.columns if '/' in c]
        hoje_str = datetime.now().strftime("%d/%m")
        index_padrao = colunas_datas.index(hoje_str) if hoje_str in colunas_datas else 0

        c1, c2, c3, c4, c5 = st.columns([1.5, 1, 1, 1, 1])
        with c1:
            st.markdown("**Status do Dia:**")
            data_kpi_selecionada = st.selectbox("Data", colunas_datas, index=index_padrao, label_visibility="collapsed")
        
        kpis = calcular_kpis_mensal_detalhado(df_mensal, data_kpi_selecionada)
        # KPI Título alterado para "No Chat"
        with c2: st.metric("✅ No Chat", kpis["Trabalhando"])
        with c3: st.metric("🛋️ Folgas", kpis["Folga"])
        with c4: st.metric("🎧 Suporte", kpis["Suporte"])
        with c5: st.metric("🚨 Emergência", kpis["Emergencia"])

        st.markdown("---")

        lideres = sorted(df_mensal['LIDER'].unique().tolist()) if 'LIDER' in df_mensal.columns else []
        ilhas = sorted(df_mensal['ILHA'].unique().tolist()) if 'ILHA' in df_mensal.columns else []
        sel_lider = filtro_lider_placeholder.multiselect("Líder", lideres, default=lideres, key="f_lm")
        sel_ilha = filtro_ilha_placeholder.multiselect("Ilha", ilhas, default=ilhas, key="f_im")

        df_f = df_mensal.copy()
        if sel_lider and 'LIDER' in df_f: df_f = df_f[df_f['LIDER'].isin(sel_lider)]
        if sel_ilha and 'ILHA' in df_f: df_f = df_f[df_f['ILHA'].isin(sel_ilha)]
        if busca_nome and 'NOME' in df_f: df_f = df_f[df_f['NOME'].str.contains(busca_nome, case=False)]

        # Ordenação removida aqui? Não, na mensal podemos manter a lógica de Ilha se quiser, 
        # mas vou deixar padrão para não confundir com o pedido da diária.
        # Se quiser ordem da planilha, remova o bloco abaixo. Vou manter pois ajuda na visualização macro.
        if 'ILHA' in df_f.columns:
             df_f = df_f.sort_values(by=['ILHA', 'NOME'])

        cols_para_remover = ['EMAIL', 'E-MAIL', 'ADMISSÃO', 'ILHA', 'Z']
        cols_visuais = [c for c in df_f.columns if c.upper().strip() not in cols_para_remover]
        
        styler = df_f[cols_visuais].style.map(colorir_mensal)
        st.dataframe(styler, use_container_width=True, height=600, hide_index=True)

# ================= ABA DIÁRIA =================
with aba_diaria:
    abas = listar_abas_dim()
    if not abas:
        st.warning("Nenhuma aba DIM encontrada.")
    else:
        top_c1, top_c2, top_c3, top_c4, top_c5 = st.columns([1.5, 1, 1, 1.5, 1.5])
        with top_c1:
            st.markdown("**Selecione o Dia:**")
            aba_sel = st.selectbox("Dia", abas, label_visibility="collapsed")
        
        df_dim, ws_dim = carregar_dados_aba(aba_sel)
        
        if df_dim is not None:
            analise = analisar_gargalos_dim(df_dim)
            resumo_dia = calcular_resumo_dia_dim(df_dim)
            
            # KPI Título alterado para "No Chat"
            with top_c2: st.metric("👥 No Chat", resumo_dia["Trabalhando"])
            # KPI Folgas agora só conta Suporte/Emergencia
            with top_c3: st.metric("🚫 Folgas (Sup/Emerg)", resumo_dia["Folga"])
            
            if analise:
                with top_c4: st.metric("⚠️ Menos Chat (09h-22h)", f"{analise['min_chat_hora']}", f"{analise['min_chat_valor']}", delta_color="inverse")
                with top_c5: st.metric("☕ Pico Pausa (09h-22h)", f"{analise['max_pausa_hora']}", f"{analise['max_pausa_valor']}", delta_color="off")
            st.divider()

            df_dim_f = df_dim.copy()
            if sel_lider and 'LIDER' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            # ATENÇÃO: NENHUMA ORDENAÇÃO AQUI POR PADRÃO.
            # O dataframe segue a ordem original da planilha (df.index).

            tipo = st.radio("Modo:", ["▦ Grade Completa", "💬 Apenas Chat", "🚫 Apenas Folgas"], horizontal=True, label_visibility="collapsed")

            # Se for Grade Completa, mostra direto (ordem original).
            # Se for filtro, usa a função que filtra e ordena por horário.
            if tipo == "▦ Grade Completa":
                df_exibicao = df_dim_f
            else:
                df_exibicao = filtrar_e_ordenar_dim(df_dim_f, tipo)
            
            cols_para_remover_dim = ['EMAIL', 'E-MAIL', 'ILHA', 'Z']
            cols_v = [c for c in df_exibicao.columns if c.upper().strip() not in cols_para_remover_dim]
            
            if tipo != "▦ Grade Completa":
                st.caption(f"Mostrando **{len(df_exibicao)}** analistas ordenados por horário de entrada.")
                
            styler_dim = df_exibicao[cols_v].style.map(colorir_diario)
            st.dataframe(styler_dim, use_container_width=True, height=600, hide_index=True)
