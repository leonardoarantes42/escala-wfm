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
    page_icon="🚙",
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

# --- FUNÇÕES DE CARREGAMENTO ---
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
        
        # Detecção de Cabeçalho
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
        
        # Filtros de Limpeza
        df = df.dropna(how='all')
        if 'NOME' in df.columns: df = df[df['NOME'] != '']
        if 'ILHA' in df.columns: df = df[df['ILHA'].str.strip() != '']

        return df, worksheet

    except Exception as e:
        st.error(f"Erro ao carregar aba '{nome_aba}': {e}")
        return None, None

# --- NOVAS FUNÇÕES DE KPI (INTELIGÊNCIA) ---

def calcular_kpis_data_especifica(df_mensal, data_escolhida):
    """Conta status baseada na data que o usuário escolheu"""
    metrics = {"Trabalhando": 0, "Folga": 0, "Afastado": 0}
    
    if data_escolhida in df_mensal.columns:
        contagem = df_mensal[data_escolhida].value_counts()
        metrics["Trabalhando"] = contagem.get("T", 0)
        metrics["Folga"] = contagem.get("F", 0)
        metrics["Afastado"] = contagem.get("FR", 0) + contagem.get("AF", 0) + contagem.get("ATESTADO", 0)
    
    return metrics

def analisar_gargalos_dim(df_dim):
    """Analisa hora a hora para achar picos e vales"""
    cols_horarios = [c for c in df_dim.columns if ':' in c]
    
    if not cols_horarios:
        return None

    menor_chat_valor = 9999
    menor_chat_hora = "-"
    
    maior_pausa_valor = -1
    maior_pausa_hora = "-"

    # Varre cada coluna de hora (06:00, 07:00...)
    for hora in cols_horarios:
        # Pega a coluna e converte para maiusculo
        coluna_limpa = df_dim[hora].astype(str).str.upper().str.strip()
        
        # Conta quantos CHAT tem nessa hora
        qtd_chat = coluna_limpa.eq('CHAT').sum()
        
        # Conta quantas PAUSAS (P ou PAUSA) tem nessa hora
        qtd_pausa = coluna_limpa.isin(['P', 'PAUSA']).sum()

        # Verifica se é o novo recorde (Mínimo Chat)
        # Ignoramos horários onde o chat é 0 se for muito cedo/tarde (opcional), 
        # mas aqui vamos mostrar a verdade nua e crua.
        if qtd_chat < menor_chat_valor:
            menor_chat_valor = qtd_chat
            menor_chat_hora = hora
            
        # Verifica se é o novo recorde (Máximo Pausa)
        if qtd_pausa > maior_pausa_valor:
            maior_pausa_valor = qtd_pausa
            maior_pausa_hora = hora
            
    return {
        "min_chat_hora": menor_chat_hora,
        "min_chat_valor": menor_chat_valor,
        "max_pausa_hora": maior_pausa_hora,
        "max_pausa_valor": maior_pausa_valor
    }

# --- VISUALIZAÇÃO ---
def colorir_grade(val):
    color = ''
    val = str(val).upper().strip() if isinstance(val, str) else str(val)
    if val == 'T': color = 'background-color: #e6f4ea; color: #1e8e3e' 
    elif val == 'F': color = 'background-color: #fce8e6; color: #c5221f'
    elif val == 'FR': color = 'background-color: #fff8e1; color: #f9ab00'
    elif 'CHAT' in val: color = 'background-color: #d2e3fc; color: #174ea6'
    elif 'EMAIL' in val: color = 'background-color: #fad2cf; color: #a50e0e'
    elif val == 'P' or 'PAUSA' in val: color = 'background-color: #fff8e1; color: #f9ab00'
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

    cores_atividade_map = {
        'CHAT': '#4285F4', 'E-MAIL': '#EA4335', 'EMAIL': '#EA4335',
        'P': '#FBBC05', 'PAUSA': '#FBBC05', 'T': '#34A853', 'TREINO': '#34A853', 
        'F': '#9AA0A6', '1X1': '#8E24AA', 'PADRINHO': '#F06292', 
        'MADRINHA': '#BA68C8', 'FINANCEIRO': '#4DB6AC', 'ASSISTIR AVD': '#7986CB'
    }

    coluna_cor = "Ilha" if colorir_por == "Ilha" else "Atividade"
    mapa_cores = None if colorir_por == "Ilha" else cores_atividade_map
    
    fig = px.timeline(
        df_timeline, x_start="Início", x_end="Fim", y="Analista", color=coluna_cor,
        color_discrete_map=mapa_cores, hover_data=["Ilha", "Atividade"],
        height=400 + (len(df_dim) * 25)
    )
    
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        xaxis=dict(side="top", tickformat="%H:%M", gridcolor='#eee', title=""),
        yaxis_title="",
        font=dict(family="Arial", size=12),
        margin=dict(l=10, r=10, t=60, b=100),
        legend=dict(
            orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5,
            title=dict(text=f"<b>{coluna_cor}</b>", side="top")
        )
    )
    return fig

def converter_df_para_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# ================= MAIN APP =================

st.title("🚀 Sistema de EscalaS Turbi")

df_global, _ = carregar_dados_aba('Mensal')

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Painel")
    
    modo_edicao = st.checkbox("Modo Edição (Líderes)")
    pode_editar = False
    if modo_edicao:
        if st.text_input("Senha", type="password") == SENHA_LIDER:
            pode_editar = True
            st.success("Liberado 🔓")
        else: st.error("Senha incorreta")
    
    st.divider()
    with st.expander("🔍 Filtros Avançados"):
        filtro_lider_placeholder = st.empty()
        filtro_ilha_placeholder = st.empty()
        busca_nome = st.text_input("Buscar Nome")
        
    st.divider()
    csv_download_placeholder = st.empty()

# --- TABS ---
aba_mensal, aba_diaria = st.tabs(["📅 Visão Mensal (Macro)", "⏱️ Visão Diária (Operação)"])

# ================= ABA MENSAL =================
with aba_mensal:
    if st.button("🔄 Atualizar Mensal"): st.cache_data.clear(); st.rerun()
    
    df_mensal = df_global
    if df_mensal is not None:
        
        # --- SELETOR DE DATA PARA KPI (Novo!) ---
        # Procura colunas que pareçam data (ex: XX/XX)
        colunas_datas = [c for c in df_mensal.columns if '/' in c]
        
        # Cria 2 colunas: Uma para o texto, outra para o selectbox
        kpi_col1, kpi_col2 = st.columns([1, 3])
        with kpi_col1:
            st.markdown("### 📊 Status do Dia:")
        with kpi_col2:
            # Tenta pegar a data de hoje como padrão, se não pega a primeira
            hoje_str = datetime.now().strftime("%d/%m")
            index_padrao = colunas_datas.index(hoje_str) if hoje_str in colunas_datas else 0
            
            data_kpi_selecionada = st.selectbox(
                "Escolha a data para visualizar os indicadores:", 
                colunas_datas, 
                index=index_padrao,
                label_visibility="collapsed"
            )

        # Calcula KPI da data escolhida
        kpis = calcular_kpis_data_especifica(df_mensal, data_kpi_selecionada)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Trabalhando", kpis["Trabalhando"])
        c2.metric("🛋️ Folgas", kpis["Folga"])
        c3.metric("🏥 Afastados/Férias", kpis["Afastado"])
        st.divider()

        # --- FILTROS E TABELA ---
        lideres = sorted(df_mensal['LIDER'].unique().tolist()) if 'LIDER' in df_mensal.columns else []
        ilhas = sorted(df_mensal['ILHA'].unique().tolist()) if 'ILHA' in df_mensal.columns else []
        sel_lider = filtro_lider_placeholder.multiselect("Líder", lideres, default=lideres, key="f_lm")
        sel_ilha = filtro_ilha_placeholder.multiselect("Ilha", ilhas, default=ilhas, key="f_im")

        df_f = df_mensal.copy()
        if sel_lider and 'LIDER' in df_f: df_f = df_f[df_f['LIDER'].isin(sel_lider)]
        if sel_ilha and 'ILHA' in df_f: df_f = df_f[df_f['ILHA'].isin(sel_ilha)]
        if busca_nome and 'NOME' in df_f: df_f = df_f[df_f['NOME'].str.contains(busca_nome, case=False)]

        csv = converter_df_para_csv(df_f)
        csv_download_placeholder.download_button("📥 Baixar Mensal", csv, "mensal.csv", "text/csv")

        cols_visuais = [c for c in df_f.columns if c not in ['EMAIL', 'ADMISSÃO']]
        
        if pode_editar:
            st.data_editor(df_f, use_container_width=True, hide_index=True, key="ed_m")
        else:
            st.dataframe(df_f[cols_visuais].style.map(colorir_grade), use_container_width=True, height=600, hide_index=True)

# ================= ABA DIÁRIA =================
with aba_diaria:
    abas = listar_abas_dim()
    if not abas:
        st.warning("Nenhuma aba DIM encontrada.")
    else:
        c_sel, c_btn, c_cor = st.columns([3, 1, 2])
        with c_sel: aba_sel = st.selectbox("Selecione o Dia:", abas)
        with c_btn: 
            st.write(""); 
            if st.button("🔄 Atualizar"): st.cache_data.clear(); st.rerun()
        
        df_dim, ws_dim = carregar_dados_aba(aba_sel)
        
        if df_dim is not None:
            # --- ANÁLISE DE GARGALOS (Novo!) ---
            analise = analisar_gargalos_dim(df_dim)
            
            if analise:
                st.markdown(f"### 🌡️ Termômetro da Operação: {aba_sel}")
                k1, k2 = st.columns(2)
                
                # Card de Alerta (Menos Chat)
                k1.metric(
                    label="⚠️ Horário com MENOS Chat", 
                    value=f"{analise['min_chat_hora']}",
                    delta=f"{analise['min_chat_valor']} pessoas",
                    delta_color="inverse" # Fica vermelho se for baixo
                )
                
                # Card de Atenção (Pico de Pausa)
                k2.metric(
                    label="☕ Horário com MAIS Pausas", 
                    value=f"{analise['max_pausa_hora']}",
                    delta=f"{analise['max_pausa_valor']} pessoas em pausa",
                    delta_color="off" # Cinza/Neutro
                )
                st.divider()

            # --- FILTROS VISUAIS ---
            df_dim_f = df_dim.copy()
            if sel_lider and 'LIDER' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['LIDER'].isin(sel_lider)]
            if sel_ilha and 'ILHA' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['ILHA'].isin(sel_ilha)]
            if busca_nome and 'NOME' in df_dim_f: df_dim_f = df_dim_f[df_dim_f['NOME'].str.contains(busca_nome, case=False)]
            
            # Download
            csv_d = converter_df_para_csv(df_dim_f)
            csv_download_placeholder.download_button(f"📥 Baixar {aba_sel}", csv_d, f"{aba_sel}.csv", "text/csv")

            tipo = st.radio("Modo:", ["📊 Timeline", "▦ Grade"], index=1 if pode_editar else 0, horizontal=True)

            if pode_editar or tipo == "▦ Grade":
                cols_v = [c for c in df_dim_f.columns if c != 'EMAIL']
                if pode_editar: st.data_editor(df_dim_f, use_container_width=True, hide_index=True, key="ed_d")
                else: st.dataframe(df_dim_f[cols_v].style.map(colorir_grade), use_container_width=True, height=600, hide_index=True)
            else:
                with c_cor: cor_opt = st.radio("Colorir por:", ["Atividade", "Ilha"], horizontal=True)
                with st.spinner("Gerando gráfico..."):
                    try:
                        dm = aba_sel.replace("DIM", "").strip()
                        dt_ref = f"{datetime.now().year}-{dm.split('/')[1]}-{dm.split('/')[0]}"
                    except: dt_ref = "2025-01-01"

                    fig = criar_grafico_timeline(df_dim_f, dt_ref, cor_opt)
                    if fig: st.plotly_chart(fig, use_container_width=True)
                    else: st.warning("Erro ao gerar gráfico.")
