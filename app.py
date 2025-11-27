import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Sistema WFM", layout="wide", page_icon="📅")

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
# Colunas que sempre devem existir, mas não necessariamente serem mostradas
COLUNAS_FIXAS_BACKEND = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']
SENHA_LIDER = "turbi123"

# --- CONEXÃO ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

# --- CARREGAMENTO DE DADOS ---
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
        if nome_aba == 'Mensal':
             worksheet = sh.get_worksheet(0)
        else:
             worksheet = sh.worksheet(nome_aba)

        dados = worksheet.get_all_values()
        
        # Detecção Inteligente de Cabeçalho
        indice_cabecalho = -1
        cabecalho_encontrado = []
        for i, linha in enumerate(dados[:5]):
            linha_upper = [str(col).upper().strip() for col in linha]
            if "NOME" in linha_upper or "NOMES" in linha_upper:
                indice_cabecalho = i
                cabecalho_encontrado = ['NOME' if str(col).upper().strip() == 'NOMES' else str(col).upper().strip() for col in linha]
                break
        
        if indice_cabecalho == -1:
            st.error(f"Erro: Não encontrei cabeçalho na aba '{nome_aba}'.")
            return None, None

        linhas = dados[indice_cabecalho + 1:]   
        df = pd.DataFrame(linhas, columns=cabecalho_encontrado)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # --- FILTRO AUTOMÁTICO DE LIMPEZA ---
        # 1. Remove linhas vazias
        df = df.dropna(how='all')
        # 2. Garante que NOME existe
        if 'NOME' in df.columns:
            df = df[df['NOME'] != '']
        # 3. Garante que ILHA está preenchida (Pedido do usuário)
        if 'ILHA' in df.columns:
            df = df[df['ILHA'].str.strip() != '']

        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar aba '{nome_aba}': {e}")
        return None, None

# --- VISUALIZAÇÃO ---
def colorir_grade(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e' 
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f'
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00'
    elif 'CHAT' in val: color = 'background-color: #d2e3fc; color: #174ea6'
    elif 'EMAIL' in val: color = 'background-color: #fad2cf; color: #a50e0e'
    elif val == 'P': color = 'background-color: #fff8e1; color: #f9ab00'
    return color

def criar_grafico_timeline(df_dim, data_referencia_str="2025-01-01"):
    lista_timeline = []
    # Identifica colunas de horário
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
                
                if i + 1 < len(colunas_horas):
                    prox_hora_str = colunas_horas[i+1].strip()
                    fim_dt = datetime.strptime(f"{data_referencia_str} {prox_hora_str}", "%Y-%m-%d %H:%M")
                else:
                    fim_dt = inicio_dt + timedelta(hours=1)

                if fim_dt <= inicio_dt: fim_dt = fim_dt + timedelta(days=1)

                lista_timeline.append({
                    'Analista': analista, 'Ilha': ilha, 'Início': inicio_dt, 'Fim': fim_dt, 'Atividade': atividade.strip().upper()
                })
            except: continue

    df_timeline = pd.DataFrame(lista_timeline)
    if df_timeline.empty: return None

    cores_map = {
        'CHAT': '#4285F4', 'E-MAIL': '#EA4335', 'EMAIL': '#EA4335',
        'P': '#FBBC05', 'PAUSA': '#FBBC05', 'T': '#34A853', 
        'TREINO': '#34A853', 'F': '#9AA0A6', '1X1': '#8E24AA'
    }
    
    fig = px.timeline(
        df_timeline, x_start="Início", x_end="Fim", y="Analista", color="Atividade",
        color_discrete_map=cores_map, hover_data=["Ilha"],
        height=600 + (len(df_dim) * 20) # Altura ajustada
    )
    
    fig.update_yaxes(autorange="reversed")
    
    # --- MELHORIA VISUAL: HORÁRIOS NO TOPO ---
    fig.update_layout(
        xaxis=dict(
            side="top", # Joga os horários para cima
            tickformat="%H:%M",
            gridcolor='#eee'
        ),
        yaxis_title="",
        legend_title="Atividade",
        font=dict(family="Arial", size=12),
        margin=dict(l=10, r=10, t=50, b=10), # Margem topo maior para caber os horários
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# --- INTERFACE ---
st.title("🚀 Sistema de Escalas Turbi")

with st.sidebar:
    st.header("⚙️ Controle")
    modo_edicao = st.checkbox("Habilitar Modo Edição")
    pode_editar = False
    if modo_edicao:
        if st.text_input("Senha", type="password") == SENHA_LIDER:
            pode_editar = True
            st.success("Edição Liberada! 🔓")
        else:
            st.error("Senha necessária")
    
    st.divider()
    st.subheader("🔍 Filtros")
    filtro_lider_placeholder = st.empty()
    filtro_ilha_placeholder = st.empty()
    busca_nome = st.text_input("Buscar Nome")

aba_mensal, aba_diaria = st.tabs(["📅 Visão Mensal", "⏱️ Visão Diária"])

# === ABA MENSAL ===
with aba_mensal:
    st.caption("Visão macro do mês.")
    if st.button("🔄 Atualizar Mensal"): st.cache_data.clear(); st.rerun()
    
    df_mensal, ws_mensal = carregar_dados_aba('Mensal')
    
    if df_mensal is not None:
        # Filtros
        lideres = sorted(df_mensal['LIDER'].unique().tolist()) if 'LIDER' in df_mensal.columns else []
        ilhas = sorted(df_mensal['ILHA'].unique().tolist()) if 'ILHA' in df_mensal.columns else []
        
        sel_lider = filtro_lider_placeholder.multiselect("Líder", lideres, default=lideres, key="f_lider_m")
        sel_ilha = filtro_ilha_placeholder.multiselect("Ilha", ilhas, default=ilhas, key="f_ilha_m")

        df_filtrado = df_mensal.copy()
        if sel_lider and 'LIDER' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['LIDER'].isin(sel_lider)]
        if sel_ilha and 'ILHA' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['ILHA'].isin(sel_ilha)]
        if busca_nome and 'NOME' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['NOME'].str.contains(busca_nome, case=False)]

        # --- LIMPEZA ESTÉTICA DE COLUNAS ---
        # Removemos Email e Admissão APENAS para visualização
        cols_esconder = ['EMAIL', 'ADMISSÃO']
        cols_para_mostrar = [c for c in df_filtrado.columns if c not in cols_esconder]
        df_visual = df_filtrado[cols_para_mostrar]

        if pode_editar:
            st.info("📝 Modo Edição Ativo")
            # No modo edição mostramos tudo para não dar erro de save, ou gerenciamos com cuidado
            st.data_editor(df_filtrado, use_container_width=True, hide_index=True, key="ed_mensal")
            if st.button("💾 Salvar Mês"): st.warning("Salvar desativado no demo.")
        else:
            # Modo Leitura: Esconde colunas chatas e o index
            st.dataframe(
                df_visual.style.map(colorir_grade), 
                use_container_width=True, 
                height=600,
                hide_index=True # <--- AQUI ESCONDE O 0,1,2
            )

# === ABA DIÁRIA ===
with aba_diaria:
    abas_disponiveis = listar_abas_dim()
    if not abas_disponiveis:
        st.warning("Nenhuma aba DIM encontrada.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1: aba_sel = st.selectbox("Selecione o Dia:", abas_disponiveis)
        with col2: 
            if st.button("🔄 Atualizar Dia"): st.cache_data.clear(); st.rerun()
        
        df_dim, ws_dim = carregar_dados_aba(aba_sel)
        
        if df_dim is not None:
            df_dim_f = df_dim.copy()
            if sel_lider and 'LIDER' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            # Toggle Visão
            tipo_visao = st.radio("Modo:", ["📊 Timeline", "▦ Grade"], index=1 if pode_editar else 0, horizontal=True, label_visibility="collapsed")

            if pode_editar or tipo_visao == "▦ Grade":
                # --- LIMPEZA ESTÉTICA DA GRADE ---
                cols_esconder_dim = ['EMAIL'] # Esconde Email no DIM
                cols_mostrar_dim = [c for c in df_dim_f.columns if c not in cols_esconder_dim]
                df_dim_visual = df_dim_f[cols_mostrar_dim]
                
                if pode_editar:
                    st.data_editor(df_dim_f, use_container_width=True, hide_index=True, key="ed_dim")
                    if st.button("💾 Salvar Dia"): st.warning("Salvar desativado no demo.")
                else:
                    st.dataframe(
                        df_dim_visual.style.map(colorir_grade), 
                        use_container_width=True, 
                        height=600,
                        hide_index=True # <--- ESCONDE O INDEX
                    )
            else:
                # VISÃO VISUAL
                with st.spinner("Gerando gráfico..."):
                    try:
                        dia_mes = aba_sel.replace("DIM", "").strip()
                        data_ref = f"{datetime.now().year}-{dia_mes.split('/')[1]}-{dia_mes.split('/')[0]}"
                    except: data_ref = "2025-01-01"

                    fig = criar_grafico_timeline(df_dim_f, data_ref)
                    if fig: st.plotly_chart(fig, use_container_width=True)
                    else: st.warning("Erro ao gerar gráfico. Verifique horários.")
