import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime, timedelta
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema de Escalas Turbi", 
    layout="wide", 
    page_icon="🚀",
    initial_sidebar_state="expanded"
)

# --- CONSTANTES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sZ8fpjLMfJb25TfJL9Rj8Yhkdw91sZ0yNWGZIgKPO8Q"
COLUNAS_FIXAS_BACKEND = ['NOME', 'EMAIL', 'ADMISSÃO', 'ILHA', 'ENTRADA', 'SAIDA', 'LIDER']
SENHA_LIDER = "turbi123"

# --- CONEXÃO GOOGLE SHEETS ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

# --- FUNÇÕES DE CARREGAMENTO DE DADOS ---
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
        # Remove colunas duplicadas se houver
        df = df.loc[:, ~df.columns.duplicated()]
        
        # --- FILTRO AUTOMÁTICO DE LIMPEZA ---
        df = df.dropna(how='all')
        if 'NOME' in df.columns: df = df[df['NOME'] != '']
        if 'ILHA' in df.columns: df = df[df['ILHA'].str.strip() != '']

        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar aba '{nome_aba}': {e}")
        return None, None

# --- FUNÇÕES VISUAIS (GRADE E GRÁFICO) ---
def colorir_grade(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e' 
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f'
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00'
    elif 'CHAT' in val: color = 'background-color: #d2e3fc; color: #174ea6'
    elif 'EMAIL' in val: color = 'background-color: #fad2cf; color: #a50e0e'
    elif val == 'P' or 'PAUSA' in val: color = 'background-color: #fff8e1; color: #f9ab00'
    elif 'TREINO' in val: color = 'background-color: #e8f0fe; color: #1967d2'
    return color

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

    # Mapa de cores fixo para Atividades
    cores_atividade_map = {
        'CHAT': '#4285F4', 'E-MAIL': '#EA4335', 'EMAIL': '#EA4335',
        'P': '#FBBC05', 'PAUSA': '#FBBC05', 'T': '#34A853', 
        'TREINO': '#34A853', 'F': '#9AA0A6', '1X1': '#8E24AA',
        'PADRINHO': '#F06292', 'MADRINHA': '#BA68C8',
        'FINANCEIRO': '#4DB6AC', 'ASSISTIR AVD': '#7986CB'
    }

    # Define qual coluna usar para cor e qual mapa
    coluna_cor_plotly = "Ilha" if colorir_por == "Ilha" else "Atividade"
    mapa_cores_plotly = None if colorir_por == "Ilha" else cores_atividade_map
    
    fig = px.timeline(
        df_timeline, x_start="Início", x_end="Fim", y="Analista", 
        color=coluna_cor_plotly,
        color_discrete_map=mapa_cores_plotly, 
        hover_data=["Ilha", "Atividade"],
        height=400 + (len(df_dim) * 25) # Altura dinâmica
    )
    
    fig.update_yaxes(autorange="reversed")
    
    # --- CORREÇÃO VISUAL: Horários no topo, Legenda embaixo ---
    fig.update_layout(
        xaxis=dict(
            side="top", 
            tickformat="%H:%M",
            gridcolor='#eee',
            title=""
        ),
        yaxis_title="",
        legend_title=colorir_por,
        font=dict(family="Arial", size=12),
        # Aumentei a margem inferior (b=100) para caber a legenda
        margin=dict(l=10, r=10, t=60, b=100), 
        # Legenda horizontal (h) posicionada abaixo do gráfico (y=-0.15)
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
    )
    return fig

# --- FUNÇÃO AUXILIAR: DOWNLOAD CSV ---
def converter_df_para_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# ================= MAIN APP =================

st.title("🚀 Sistema de Escalas Turbi")

# --- CARREGAMENTO INICIAL DE DADOS (MENSAL) PARA KPIS ---
# Carregamos o mensal primeiro para ter uma visão geral
df_global, _ = carregar_dados_aba('Mensal')

# --- BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Painel de Controle")
    
    # 1. Modo Edição
    modo_edicao = st.checkbox("Habilitar Modo Edição (Líderes)")
    pode_editar = False
    if modo_edicao:
        if st.text_input("Senha de Acesso", type="password") == SENHA_LIDER:
            pode_editar = True
            st.success("Edição Liberada! 🔓")
        else:
            st.error("Senha necessária")
    
    st.divider()
    
    # 2. Filtros (Agora dentro de um Expander para limpar o visual)
    with st.expander("🔍 Filtros Avançados", expanded=False):
        filtro_lider_placeholder = st.empty()
        filtro_ilha_placeholder = st.empty()
        busca_nome = st.text_input("Buscar por Nome")
        
    st.divider()

    # 3. Área de Download
    st.subheader("📂 Exportar")
    csv_download_placeholder = st.empty() # Placeholder para o botão
    st.caption("Baixa os dados da visão atual.")


# --- KPIS (BIG NUMBERS) NO TOPO ---
if df_global is not None:
    col_k1, col_k2, col_k3 = st.columns(3)
    # Calcula métricas baseadas na aba Mensal completa
    total_analistas = len(df_global)
    total_lideres = len(df_global['LIDER'].unique()) if 'LIDER' in df_global.columns else 0
    total_ilhas = len(df_global['ILHA'].unique()) if 'ILHA' in df_global.columns else 0

    col_k1.metric("Total Analistas", total_analistas, help="Contagem total na aba Mensal")
    col_k2.metric("Total Líderes", total_lideres)
    col_k3.metric("Total Ilhas/Times", total_ilhas)
    st.divider()
else:
    st.warning("Carregando dados globais...")


# --- ABAS PRINCIPAIS ---
aba_mensal, aba_diaria = st.tabs(["📅 Visão Mensal (Macro)", "⏱️ Visão Diária (Operação)"])

# ================= ABA MENSAL =================
with aba_mensal:
    if st.button("🔄 Atualizar Visão Mensal"): st.cache_data.clear(); st.rerun()
    
    # Usa o df_global já carregado
    df_mensal = df_global
    
    if df_mensal is not None:
        # --- Lógica de Filtros Global ---
        lideres = sorted(df_mensal['LIDER'].unique().tolist()) if 'LIDER' in df_mensal.columns else []
        ilhas = sorted(df_mensal['ILHA'].unique().tolist()) if 'ILHA' in df_mensal.columns else []
        
        # Preenche os placeholders da sidebar
        sel_lider = filtro_lider_placeholder.multiselect("Líder", lideres, default=lideres, key="f_lider_m")
        sel_ilha = filtro_ilha_placeholder.multiselect("Ilha", ilhas, default=ilhas, key="f_ilha_m")

        # Aplica Filtros
        df_filtrado = df_mensal.copy()
        if sel_lider and 'LIDER' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['LIDER'].isin(sel_lider)]
        if sel_ilha and 'ILHA' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['ILHA'].isin(sel_ilha)]
        if busca_nome and 'NOME' in df_filtrado: df_filtrado = df_filtrado[df_filtrado['NOME'].str.contains(busca_nome, case=False)]

        # --- Preparação para Exibição ---
        # Remove colunas 'sujas' apenas para visualização
        cols_esconder = ['EMAIL', 'ADMISSÃO']
        cols_para_mostrar = [c for c in df_filtrado.columns if c not in cols_esconder]
        df_visual = df_filtrado[cols_para_mostrar]

        # Atualiza botão de download na sidebar com os dados filtrados deste mês
        csv_mensal = converter_df_para_csv(df_visual)
        csv_download_placeholder.download_button(label="📥 Baixar Dados Mensais (CSV)", data=csv_mensal, file_name="escala_mensal_filtrada.csv", mime="text/csv")

        st.caption(f"Mostrando {len(df_visual)} analistas filtrados.")

        if pode_editar:
            st.info("📝 Modo Edição Ativo. Salvar desabilitado no demo.")
            st.data_editor(df_filtrado, use_container_width=True, hide_index=True, key="ed_mensal")
        else:
            st.dataframe(
                df_visual.style.map(colorir_grade), 
                use_container_width=True, 
                height=650,
                hide_index=True
            )

# ================= ABA DIÁRIA =================
with aba_diaria:
    abas_disponiveis = listar_abas_dim()
    if not abas_disponiveis:
        st.warning("Nenhuma aba 'DIM' encontrada na planilha.")
    else:
        # Controles do Topo da Aba Diária
        c_sel, c_btn, c_cor = st.columns([3, 1, 2])
        with c_sel: aba_sel = st.selectbox("Selecione o Dia:", abas_disponiveis)
        with c_btn: 
            st.write("") # Espaçamento
            if st.button("🔄 Atualizar Dia"): st.cache_data.clear(); st.rerun()
        
        # Carrega dados do dia
        df_dim, ws_dim = carregar_dados_aba(aba_sel)
        
        if df_dim is not None:
            # Aplica os MESMOS filtros globais da sidebar
            df_dim_f = df_dim.copy()
            if sel_lider and 'LIDER' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            # Atualiza botão de download na sidebar com os dados deste DIA
            csv_diario = converter_df_para_csv(df_dim_f)
            csv_download_placeholder.download_button(label="📥 Baixar Dados do Dia (CSV)", data=csv_diario, file_name=f"escala_{aba_sel.replace('/','-')}.csv", mime="text/csv")

            # Seletor de Modo de Visão
            tipo_visao = st.radio("Modo de Visualização:", ["📊 Timeline (Visual)", "▦ Grade (Excel)"], index=1 if pode_editar else 0, horizontal=True, label_visibility="visible")
            st.divider()

            if pode_editar or tipo_visao == "▦ Grade (Excel)":
                # --- VISÃO GRADE ---
                cols_esconder_dim = ['EMAIL']
                cols_mostrar_dim = [c for c in df_dim_f.columns if c not in cols_esconder_dim]
                df_dim_visual = df_dim_f[cols_mostrar_dim]
                
                if pode_editar:
                    st.data_editor(df_dim_f, use_container_width=True, hide_index=True, key="ed_dim")
                else:
                    st.dataframe(
                        df_dim_visual.style.map(colorir_grade), 
                        use_container_width=True, 
                        height=650,
                        hide_index=True
                    )
            else:
                # --- VISÃO TIMELINE ---
                # Seletor de Cor (Só aparece no modo Timeline)
                with c_cor:
                    opcao_cor = st.radio("🎨 Colorir por:", ["Atividade", "Ilha"], horizontal=True)

                with st.spinner("Gerando cronograma..."):
                    try:
                        dia_mes = aba_sel.replace("DIM", "").strip()
                        data_ref = f"{datetime.now().year}-{dia_mes.split('/')[1]}-{dia_mes.split('/')[0]}"
                    except: data_ref = "2025-01-01"

                    # Chama a função gráfica com a nova opção de cor
                    fig = criar_grafico_timeline(df_dim_f, data_ref, colorir_por=opcao_cor)
                    if fig: st.plotly_chart(fig, use_container_width=True)
                    else: st.warning("Erro ao gerar gráfico. Verifique se há horários preenchidos.")
