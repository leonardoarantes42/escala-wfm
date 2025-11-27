import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Sistema WFM", layout="wide", page_icon="📅")

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
COLUNAS_FIXAS = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']
SENHA_LIDER = "turbi123"

# --- CONEXÃO ROBUSTA ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

# --- FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def listar_abas_dim():
    """Descobre quais abas de dias (DIM) existem na planilha"""
    client = conectar_google_sheets()
    sh = client.open_by_url(URL_PLANILHA)
    todas_abas = [ws.title for ws in sh.worksheets()]
    # Filtra só as que começam com DIM e ordena
    abas_dim = sorted([aba for aba in todas_abas if aba.startswith("DIM")])
    return abas_dim

def carregar_dados_aba(nome_aba):
    """Carrega dados de uma aba específica com detecção inteligente de cabeçalho"""
    client = conectar_google_sheets()
    try:
        sh = client.open_by_url(URL_PLANILHA)
        if nome_aba == 'Mensal':
             worksheet = sh.get_worksheet(0)
        else:
             worksheet = sh.worksheet(nome_aba)

        dados = worksheet.get_all_values()
        
        # --- DETECÇÃO INTELIGENTE DE CABEÇALHO ---
        # Procura nas primeiras 5 linhas onde está a coluna "NOME" ou "NOMES"
        indice_cabecalho = -1
        cabecalho_encontrado = []
        
        for i, linha in enumerate(dados[:5]):
            # Converte tudo para maiúsculo e remove espaços para verificar
            linha_upper = [str(col).upper().strip() for col in linha]
            if "NOME" in linha_upper or "NOMES" in linha_upper:
                indice_cabecalho = i
                # Normaliza: Se achar "NOMES", troca para "NOME" para não quebrar o código
                cabecalho_encontrado = ['NOME' if str(col).upper().strip() == 'NOMES' else str(col).upper().strip() for col in linha]
                break
        
        if indice_cabecalho == -1:
            st.error(f"Erro: Não encontrei a coluna 'NOME' ou 'NOMES' nas primeiras 5 linhas da aba '{nome_aba}'.")
            return None, None

        # Carrega os dados a partir da linha seguinte ao cabeçalho encontrado
        linhas = dados[indice_cabecalho + 1:]   
        
        df = pd.DataFrame(linhas, columns=cabecalho_encontrado)
        
        # Limpeza e Segurança
        # Garante que não tenhamos colunas com nomes vazios (comum no pandas dar erro)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Filtra linhas vazias
        df = df.dropna(how='all')
        if 'NOME' in df.columns:
            df = df[df['NOME'] != '']
            
        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar aba '{nome_aba}': {e}")
        return None, None

# --- FUNÇÕES VISUAIS (GRÁFICO E CORES) ---
def colorir_grade(val):
    """Cores para a visão de grade (estilo Excel)"""
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    # Status Mensal
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e' # Verde
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f' # Vermelho
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00' # Amarelo
    # Status Diário (DIM)
    elif 'CHAT' in val: color = 'background-color: #d2e3fc; color: #174ea6' # Azul claro
    elif 'EMAIL' in val: color = 'background-color: #fad2cf; color: #a50e0e' # Vermelho claro
    elif val == 'P': color = 'background-color: #fff8e1; color: #f9ab00' # Pausa Amarelo
    return color

def criar_grafico_timeline(df_dim, data_referencia_str="2025-01-01"):
    """Transforma a grade horária em um gráfico de linha do tempo bonito"""
    lista_timeline = []
    
    # Identifica colunas de horário (assumindo formato HH:MM)
    colunas_horas = [col for col in df_dim.columns if ':' in col and col not in COLUNAS_FIXAS]
    
    if not colunas_horas:
        return None

    data_base = datetime.strptime(data_referencia_str, "%Y-%m-%d")

    for _, row in df_dim.iterrows():
        analista = row['NOME']
        ilha = row.get('ILHA', 'Geral')
        
        for i, hora_col in enumerate(colunas_horas):
            atividade = row[hora_col]
            if not atividade or atividade.strip() == '': continue
            
            try:
                # Cria horário de início e fim (assumindo blocos de 1h ou a distância entre colunas)
                hora_inicio_str = hora_col.strip()
                inicio_dt = datetime.strptime(f"{data_referencia_str} {hora_inicio_str}", "%Y-%m-%d %H:%M")
                
                # Tenta calcular o fim baseado na próxima coluna, ou assume 1h se for a última
                if i + 1 < len(colunas_horas):
                    prox_hora_str = colunas_horas[i+1].strip()
                    fim_dt = datetime.strptime(f"{data_referencia_str} {prox_hora_str}", "%Y-%m-%d %H:%M")
                else:
                    fim_dt = inicio_dt + timedelta(hours=1)

                # Ajuste para virada de dia (ex: turno termina 02:00 do dia seguinte)
                if fim_dt <= inicio_dt:
                     fim_dt = fim_dt + timedelta(days=1)

                lista_timeline.append({
                    'Analista': analista,
                    'Ilha': ilha,
                    'Início': inicio_dt,
                    'Fim': fim_dt,
                    'Atividade': atividade.strip().upper()
                })
            except Exception:
                 continue # Pula se der erro em algum horário mal formatado

    df_timeline = pd.DataFrame(lista_timeline)
    
    if df_timeline.empty: return None

    # Mapa de cores oficial
    cores_map = {
        'CHAT': '#4285F4',    # Azul Google
        'E-MAIL': '#EA4335',  # Vermelho
        'EMAIL': '#EA4335',
        'P': '#FBBC05',       # Amarelo Pausa
        'PAUSA': '#FBBC05',
        'T': '#34A853',       # Verde Treino
        'TREINO': '#34A853',
        'F': '#9AA0A6',       # Cinza Folga
        '1X1': '#8E24AA'      # Roxo
    }
    
    fig = px.timeline(
        df_timeline, 
        x_start="Início", 
        x_end="Fim", 
        y="Analista", 
        color="Atividade",
        color_discrete_map=cores_map,
        hover_data=["Ilha"],
        height=600 + (len(df_dim) * 15) # Altura dinâmica baseada no nº de pessoas
    )
    
    fig.update_yaxes(autorange="reversed") # Analistas de A-Z de cima para baixo
    fig.update_layout(
        xaxis_title="Horário (Linha do Tempo)",
        yaxis_title="",
        legend_title="Legenda",
        font=dict(family="Arial", size=12),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(
            tickformat="%H:%M",
            gridcolor='#eee'
        )
    )
    return fig

# --- INTERFACE PRINCIPAL ---
st.title("🚀 Sistema de Gestão de Escala WFM")

# 1. Barra Lateral de Controle (Login e Filtros Globais)
with st.sidebar:
    st.header("⚙️ Controle")
    modo_edicao = st.checkbox("Habilitar Modo Edição (Líderes)")
    pode_editar = False
    if modo_edicao:
        senha = st.text_input("Senha", type="password")
        if senha == SENHA_LIDER:
            pode_editar = True
            st.success("Edição Liberada! 🔓")
        elif senha:
            st.error("Senha Incorreta")
    
    st.divider()
    st.subheader("🔍 Filtros Globais")
    # Placeholder para os filtros (serão preenchidos após carregar os dados)
    filtro_lider_placeholder = st.empty()
    filtro_ilha_placeholder = st.empty()
    busca_nome = st.text_input("Buscar Analista (Nome)")

# 2. Abas Principais (Mensal vs Diária)
aba_mensal, aba_diaria = st.tabs(["📅 Visão Mensal (Macro)", "⏱️ Visão Diária (Detalhada)"])

# --- LÓGICA DA ABA MENSAL ---
with aba_mensal:
    st.subheader("Escala Geral do Mês")
    if st.button("🔄 Atualizar Mensal"): st.cache_data.clear(); st.rerun()
    
    df_mensal, ws_mensal = carregar_dados_aba('Mensal')
    
    if df_mensal is not None:
        # --- Aplicação dos Filtros (Replicado para ambas as abas) ---
        # Preenche os selects da sidebar baseado nos dados carregados
        lideres_opcoes = sorted(df_mensal['LIDER'].unique().tolist()) if 'LIDER' in df_mensal.columns else []
        ilhas_opcoes = sorted(df_mensal['ILHA'].unique().tolist()) if 'ILHA' in df_mensal.columns else []
        
        sel_lider = filtro_lider_placeholder.multiselect("Líder", lideres_opcoes, default=lideres_opcoes, key="filtro_lider_mensal")
        sel_ilha = filtro_ilha_placeholder.multiselect("Ilha", ilhas_opcoes, default=ilhas_opcoes, key="filtro_ilha_mensal")

        df_filtrado = df_mensal.copy()
        if sel_lider and 'LIDER' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['LIDER'].isin(sel_lider)]
        if sel_ilha and 'ILHA' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['ILHA'].isin(sel_ilha)]
        if busca_nome and 'NOME' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['NOME'].str.contains(busca_nome, case=False)]
        
        st.caption(f"Mostrando {len(df_filtrado)} de {len(df_mensal)} analistas.")

        # Lógica de Exibição/Edição
        if pode_editar:
            st.info("📝 Modo Edição: Altere os 'T'/'F' e clique em Salvar.")
            df_editado = st.data_editor(df_filtrado, use_container_width=True, key="editor_mensal")
            if st.button("💾 Salvar Mês (Cuidado com Filtros!)", type="primary"):
                st.warning("Funcionalidade de salvar desabilitada neste demo para segurança. Implementar a lógica de update segura.")
        else:
            cols_dados = df_filtrado.columns.difference(COLUNAS_FIXAS)
            st.dataframe(df_filtrado.style.map(colorir_grade, subset=cols_dados), use_container_width=True, height=600)


# --- LÓGICA DA ABA DIÁRIA (DIM) ---
with aba_diaria:
    # 1. Seletor de Dia
    abas_disponiveis = listar_abas_dim()
    if not abas_disponiveis:
        st.warning("Nenhuma aba 'DIM' encontrada na planilha.")
    else:
        col_sel1, col_sel2 = st.columns([3, 1])
        with col_sel1:
            aba_selecionada = st.selectbox("Selecione o Dia (DIM):", abas_disponiveis)
        with col_sel2:
            if st.button("🔄 Atualizar Dia"): st.cache_data.clear(); st.rerun()
        
        # 2. Carrega dados do dia selecionado
        df_dim, ws_dim = carregar_dados_aba(aba_selecionada)
        
        if df_dim is not None:
            # Aplica os MESMOS filtros globais da sidebar
            df_dim_filtrado = df_dim.copy()
            if sel_lider and 'LIDER' in df_dim_filtrado: df_dim_filtrado = df_dim_filtrado[df_dim_filtrado['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_filtrado: df_dim_filtrado = df_dim_filtrado[df_dim_filtrado['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_filtrado: df_dim_filtrado = df_dim_filtrado[df_dim_filtrado['NOME'].str.contains(busca_nome, case=False)]
            
            # 3. Toggle: Visão Visual vs Visão Grade
            col_tog1, col_tog2 = st.columns([4,1])
            with col_tog2:
                # Se estiver em modo edição, força a visão de grade
                tipo_visao = st.radio("Tipo de Visão:", ["📊 Visual (Timeline)", "▦ Grade (Excel)"], index=1 if pode_editar else 0, horizontal=True, label_visibility="collapsed")

            if pode_editar or tipo_visao == "▦ Grade (Excel)":
                # VISÃO DE GRADE (Para editar ou quem prefere assim)
                st.subheader(f"Visão de Grade: {aba_selecionada}")
                cols_horarios = df_dim_filtrado.columns.difference(COLUNAS_FIXAS)
                
                if pode_editar:
                    st.info("📝 Edite os horários (Chat, P, Email) e clique em Salvar.")
                    df_dim_editado = st.data_editor(df_dim_filtrado, use_container_width=True, key="editor_dim")
                    if st.button("💾 Salvar Dia (Cuidado com Filtros!)", type="primary"):
                         st.warning("Funcionalidade de salvar desabilitada neste demo para segurança.")
                else:
                    st.dataframe(df_dim_filtrado.style.map(colorir_grade, subset=cols_horarios), use_container_width=True, height=600)
            
            else:
                # VISÃO VISUAL (BONITA) - Timeline Plotly
                st.subheader(f"Timeline da Operação: {aba_selecionada}")
                with st.spinner("Gerando gráfico..."):
                    # Tenta extrair uma data válida do nome da aba (ex: DIM 01/12 -> 2024-12-01) para o gráfico
                    try:
                        dia_mes = aba_selecionada.replace("DIM", "").strip()
                        ano_atual = datetime.now().year # Assume ano atual
                        data_ref_str = f"{ano_atual}-{dia_mes.split('/')[1]}-{dia_mes.split('/')[0]}"
                    except:
                        data_ref_str = "2025-01-01" # Data fallback se der erro no nome da aba

                    fig_timeline = criar_grafico_timeline(df_dim_filtrado, data_ref_str)
                    
                    if fig_timeline:
                        st.plotly_chart(fig_timeline, use_container_width=True)
                    else:
                        st.warning("Não foi possível gerar a timeline. Verifique se as colunas de horário estão no formato HH:MM.")
