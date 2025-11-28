import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Escalas Turbi", 
    layout="wide", 
    page_icon="logo_turbi.png", 
    initial_sidebar_state="expanded"
)

# --- CSS: DESIGN LIMPO ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        /* KPIs à Esquerda */
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
        [data-testid="stMetricLabel"] {
            width: 100%;
            justify-content: flex-start !important;
            font-size: 14px !important;
            color: #555;
        }
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
SENHA_LIDER = "turbi123"
OPCOES_ATIVIDADE = ["Chat", "E-mail", "P", "1:1", "F", "Treino", "Almoço", "Feedback", "Financeiro", "Reembolsos", "BackOffice"]

# ORDEM DAS ILHAS PARA AGRUPAMENTO
ORDEM_DAS_ILHAS = [
    "Suporte", "Emergência", # Grupo 1
    "Financeiro",            # Grupo 2 (Terá destaque)
    "E-mail", "Pleno", "RA", "Staff" # Outros
]

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
        df = df.dropna(how='all')
        if 'NOME' in df.columns: df = df[df['NOME'] != '']
        if 'ILHA' in df.columns: df = df[df['ILHA'].str.strip() != '']

        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar aba '{nome_aba}': {e}")
        return None, None

# --- NOVAS REGRAS DE KPI E FILTRO ---

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
    """
    Conta Escalados (Apenas quem tem CHAT) e Folgas totais.
    """
    cols_horarios = [c for c in df_dim.columns if ':' in c]
    if not cols_horarios: return {"Trabalhando": 0, "Folga": 0}

    def juntar_linha(row):
        return "".join([str(val).upper() for val in row])

    resumo = df_dim[cols_horarios].apply(juntar_linha, axis=1)
    
    # REQUISITO: Escalados conta APENAS quem tem CHAT
    escalados_chat = resumo.str.contains('CHAT').sum()
    
    # REQUISITO: Folga conta quem tem 'F' e NÃO tem atividade de trabalho
    # Se tiver 'F' mas tiver 'CHAT' (ex: folga parcial/extra), não conta como folga total
    tem_trabalho = resumo.str.contains('CHAT|EMAIL|E-MAIL|P|TREINO|1:1|1X1|FINANCEIRO|REEMBOLSOS|BACKOFFICE')
    tem_folga = resumo.str.contains('F')
    folga_total = ((tem_folga) & (~tem_trabalho)).sum()
    
    return {"Trabalhando": escalados_chat, "Folga": folga_total}

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
        # Mostra apenas quem tem pelo menos 1 'CHAT'
        mask = df_filtrado[cols_horarios].apply(lambda row: row.astype(str).str.upper().str.contains('CHAT').any(), axis=1)
        df_filtrado = df_filtrado[mask]
        
    elif modo == "🚫 Apenas Folgas":
        # REQUISITO: Mostrar SÓ quem tem 'F' e NÃO tem outras coisas
        def is_pure_folga(row):
            s = "".join([str(val).upper() for val in row])
            has_f = 'F' in s
            has_work = any(x in s for x in ['CHAT', 'EMAIL', 'E-MAIL', 'P', '1:1', 'TREINO', 'FINANCEIRO'])
            return has_f and not has_work
            
        mask = df_filtrado[cols_horarios].apply(is_pure_folga, axis=1)
        df_filtrado = df_filtrado[mask]

    df_filtrado = df_filtrado.sort_values(by='SORT_TEMP', na_position='last')
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

def estilo_separacao_financeiro(df):
    """
    Desenha uma borda grossa especificamente acima da ilha FINANCEIRO
    para criar a separação visual solicitada.
    """
    estilos = pd.DataFrame('', index=df.index, columns=df.columns)
    if 'ILHA' in df.columns:
        ilhas = df['ILHA'].astype(str).str.strip()
        # Identifica onde começa o Financeiro (Linha atual é Financeiro E anterior não era)
        is_fin = ilhas == "Financeiro"
        was_not_fin = ilhas.shift(1) != "Financeiro"
        inicio_financeiro = is_fin & was_not_fin
        
        # Aplica a borda
        idx_fin = inicio_financeiro[inicio_financeiro].index
        for idx in idx_fin:
            if idx in estilos.index:
                # Borda Roxa (cor do Nubank/Financeiro moderno) para destacar
                estilos.loc[idx, :] = 'border-top: 3px solid #5a3286 !important;'
                
    return estilos

def criar_grafico_timeline(df_dim, data_referencia_str="2025-01-01", colorir_por="Atividade"):
    lista_timeline = []
    colunas_horas = [col for col in df_dim.columns if ':' in col and col not in COLUNAS_FIXAS_BACKEND]
    if not colunas_horas: return None
    for _, row in df_dim.iterrows():
        analista = row['NOME']
        ilha = row.get('ILHA', 'Geral')
        for i, hora_col in enumerate(colunas_horas):
            atividade = row[hora_col]
            if not atividade or atividade.strip() == '': continue
            try:
                hora_inicio_str = hora_col.strip()
                inicio_dt = datetime.strptime(f"{data_referencia_str} {hora_inicio_str}", "%Y-%m-%d %H:%M")
                if i + 1 < len(colunas_horas): prox_hora_str = colunas_horas[i+1].strip(); fim_dt = datetime.strptime(f"{data_referencia_str} {prox_hora_str}", "%Y-%m-%d %H:%M")
                else: fim_dt = inicio_dt + timedelta(hours=1)
                if fim_dt <= inicio_dt: fim_dt = fim_dt + timedelta(days=1)
                lista_timeline.append({'Analista': analista, 'Ilha': ilha, 'Início': inicio_dt, 'Fim': fim_dt, 'Atividade': atividade.strip().upper()})
            except: continue
    df_timeline = pd.DataFrame(lista_timeline)
    if df_timeline.empty: return None
    cores_atividade_map = {'CHAT': '#d9ead3', 'E-MAIL': '#bfe1f6', 'EMAIL': '#bfe1f6', 'P': '#fce5cd', 'PAUSA': '#fce5cd', 'F': '#002060', 'FINANCEIRO': '#11734b', 'REEMBOLSOS': '#d4edbc', 'BACKOFFICE': '#5a3286', 'T': '#c9daf8', 'TREINO': '#e8f0fe', '1:1': '#f3e5f5'}
    coluna_cor = "Ilha" if colorir_por == "Ilha" else "Atividade"
    mapa_cores = None if colorir_por == "Ilha" else cores_atividade_map
    fig = px.timeline(df_timeline, x_start="Início", x_end="Fim", y="Analista", color=coluna_cor, color_discrete_map=mapa_cores, hover_data=["Ilha", "Atividade"], height=400 + (len(df_dim) * 25))
    fig.update_yaxes(autorange="reversed")
    start_range = datetime.strptime(f"{data_referencia_str} 06:00", "%Y-%m-%d %H:%M"); end_range = start_range + timedelta(days=1, hours=1)
    fig.update_xaxes(range=[start_range, end_range], side="top", tickformat="%H:%M", gridcolor='#eee', title="")
    fig.update_layout(yaxis_title="", font=dict(family="Arial", size=12), margin=dict(l=10, r=10, t=60, b=50), legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5, title=dict(text=f"<b>{coluna_cor}</b>", side="top")))
    return fig

# ================= MAIN APP =================

with st.sidebar:
    st.image("logo_turbi.png", width=140) 
    st.divider()
    modo_edicao = st.checkbox("Modo Edição (Líderes)")
    pode_editar = False
    if modo_edicao:
        if st.text_input("Senha", type="password") == SENHA_LIDER:
            pode_editar = True; st.success("Liberado 🔓")
        else: st.error("Senha incorreta")
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
        with c2: st.metric("✅ Trabalhando", kpis["Trabalhando"])
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

        # Ordenação
        if 'ILHA' in df_f.columns:
            df_f['ILHA'] = df_f['ILHA'].astype(str).str.strip()
            df_f['ILHA_CAT'] = pd.Categorical(df_f['ILHA'], categories=ORDEM_DAS_ILHAS, ordered=True)
            df_f = df_f.sort_values(by=['ILHA_CAT', 'NOME'], na_position='last').drop(columns=['ILHA_CAT'])

        cols_para_remover = ['EMAIL', 'E-MAIL', 'ADMISSÃO', 'ILHA', 'Z'] # Remove Z se existir
        cols_visuais = [c for c in df_f.columns if c.upper().strip() not in cols_para_remover]
        
        # Aplica a separação visual para o Financeiro
        styler = (df_f[cols_visuais].style
                  .map(colorir_mensal)
                  .apply(estilo_separacao_financeiro, axis=None)) # <--- Separador Financeiro

        if pode_editar: st.data_editor(df_f, use_container_width=True, hide_index=True, key="ed_m")
        else: st.dataframe(styler, use_container_width=True, height=600, hide_index=True)

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
            with top_c2: st.metric("👥 Escalados", resumo_dia["Trabalhando"])
            with top_c3: st.metric("🚫 Folgas", resumo_dia["Folga"])
            if analise:
                with top_c4: st.metric("⚠️ Menos Chat (09h-22h)", f"{analise['min_chat_hora']}", f"{analise['min_chat_valor']}", delta_color="inverse")
                with top_c5: st.metric("☕ Pico Pausa (09h-22h)", f"{analise['max_pausa_hora']}", f"{analise['max_pausa_valor']}", delta_color="off")
            st.divider()

            df_dim_f = df_dim.copy()
            if sel_lider and 'LIDER' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            # Ordenação Diária
            if 'ILHA' in df_dim_f.columns:
                df_dim_f['ILHA'] = df_dim_f['ILHA'].astype(str).str.strip()
                df_dim_f['ILHA_CAT'] = pd.Categorical(df_dim_f['ILHA'], categories=ORDEM_DAS_ILHAS, ordered=True)
                df_dim_f = df_dim_f.sort_values(by=['ILHA_CAT', 'NOME'], na_position='last').drop(columns=['ILHA_CAT'])

            tipo = st.radio("Modo:", ["📊 Timeline", "▦ Grade Completa", "💬 Apenas Chat", "🚫 Apenas Folgas"], index=1 if pode_editar else 0, horizontal=True, label_visibility="collapsed")

            if tipo == "📊 Timeline":
                c_spacer, c_opt = st.columns([3,1])
                with c_opt: cor_opt = st.radio("Cor:", ["Atividade", "Ilha"], horizontal=True)
                with st.spinner("Gerando gráfico..."):
                    try:
                        dm = aba_sel.replace("DIM", "").strip()
                        dt_ref = f"{datetime.now().year}-{dm.split('/')[1]}-{dm.split('/')[0]}"
                    except: dt_ref = "2025-01-01"
                    fig = criar_grafico_timeline(df_dim_f, dt_ref, cor_opt)
                    if fig: st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                    else: st.warning("Erro ao gerar gráfico.")
            
            else:
                # Filtrar e Ordenar
                df_exibicao = filtrar_e_ordenar_dim(df_dim_f, tipo)
                
                # Ignora Coluna Z aqui também
                cols_para_remover_dim = ['EMAIL', 'E-MAIL', 'ILHA', 'Z']
                cols_v = [c for c in df_exibicao.columns if c.upper().strip() not in cols_para_remover_dim]
                
                if pode_editar and tipo == "▦ Grade Completa":
                    time_cols = [c for c in cols_v if ':' in c]
                    column_config = {col: st.column_config.SelectboxColumn(col, options=OPCOES_ATIVIDADE, required=True, width="small") for col in time_cols}
                    st.info("✏️ Modo Edição")
                    st.data_editor(df_exibicao[cols_v], use_container_width=True, hide_index=True, key="ed_d", column_config=column_config)
                else:
                    if tipo != "▦ Grade Completa":
                        st.caption(f"Mostrando **{len(df_exibicao)}** analistas ordenados por horário de entrada.")
                    styler_dim = df_exibicao[cols_v].style.map(colorir_diario)
                    st.dataframe(styler_dim, use_container_width=True, height=600, hide_index=True)
