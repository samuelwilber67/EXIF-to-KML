import streamlit as st
import pandas as pd
import simplekml
from geopy.geocoders import ArcGIS
import time
import re

# Configuração da interface
st.set_page_config(page_title="MAPA - Filtro Regional", layout="wide")
st.title("📍 Gestão Territorial de Convênios (Filtro por UF)")
st.markdown("---")

# Dicionário de Capitais para Alocação de Convênios Estaduais
CAPITAIS = {
    'AC': 'Rio Branco', 'AL': 'Maceió', 'AP': 'Macapá', 'AM': 'Manaus',
    'BA': 'Salvador', 'CE': 'Fortaleza', 'DF': 'Brasília', 'ES': 'Vitória',
    'GO': 'Goiânia', 'MA': 'São Luís', 'MT': 'Cuiabá', 'MS': 'Campo Grande',
    'MG': 'Belo Horizonte', 'PA': 'Belém', 'PB': 'João Pessoa', 'PR': 'Curitiba',
    'PE': 'Recife', 'PI': 'Teresina', 'RJ': 'Rio de Janeiro', 'RN': 'Natal',
    'RS': 'Porto Alegre', 'RO': 'Porto Velho', 'RR': 'Boa Vista', 'SC': 'Florianópolis',
    'SP': 'São Paulo', 'SE': 'Aracaju', 'TO': 'Palmas'
}

def detectar_colunas(colunas):
    mapeamento = {}
    padroes = {
        'convenio': [r'conv[êe]nio', r'n[ºo]', r'numero', r'id'],
        'municipio': [r'munic[íi]pio', r'cidade', r'localidade'],
        'uf': [r'uf', r'estado', r'sigla'],
        'percentual': [r'percentual', r'%', r'executado', r'execu[çc][ãa]o', r'fisico']
    }
    for chave, regex_list in padroes.items():
        for col in colunas:
            for regex in regex_list:
                if re.search(regex, col.lower()):
                    mapeamento[chave] = col
                    break
            if chave in mapeamento: break
    return mapeamento

def limpar_nome(nome):
    nome = str(nome).upper()
    termos = ["MUNICIPIO DE ", "PREFEITURA DE ", "GOVERNO DE ", "PM DE ", "PREFEITURA MUNICIPAL DE "]
    for termo in termos:
        nome = nome.replace(termo, "")
    return nome.strip()

def obter_estilo_execucao(valor):
    """Lógica de cores: Azul (0%), Amarelo (0-80%), Vermelho (>80%)"""
    try:
        v = float(str(valor).replace('%', '').replace(',', '.'))
        if v > 1 and v <= 100: v = v / 100
        
        if v == 0:
            return 'http://maps.google.com/mapfiles/kml/paddle/blu-circle.png', "0% (Não Iniciada)"
        elif v <= 0.8:
            return 'http://maps.google.com/mapfiles/kml/paddle/ylw-circle.png', f"{v*100:.1f}% (Em Andamento)"
        else:
            return 'http://maps.google.com/mapfiles/kml/paddle/red-circle.png', f"{v*100:.1f}% (Fase Final/Concluída)"
    except:
        return 'http://maps.google.com/mapfiles/kml/paddle/wht-circle.png', "Dado Inválido"

geolocator = ArcGIS(timeout=10)

uploaded_file = st.file_uploader("Suba sua planilha Excel", type=['xlsx', 'xls'])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    cols_detectadas = detectar_colunas(df.columns)
    
    # Interface Lateral para Ajustes e Filtros
    st.sidebar.header("⚙️ Configurações")
    c_conv = st.sidebar.text_input("Coluna Nº Convênio", cols_detectadas.get('convenio', ''))
    c_mun = st.sidebar.text_input("Coluna Município", cols_detectadas.get('municipio', ''))
    c_uf = st.sidebar.text_input("Coluna UF", cols_detectadas.get('uf', ''))
    c_perc = st.sidebar.text_input("Coluna Execução", cols_detectadas.get('percentual', ''))

    if c_uf in df.columns:
        ufs_disponiveis = sorted(df[c_uf].dropna().unique().tolist())
        ufs_selecionadas = st.multiselect("🌍 Filtrar por UF (Selecione uma ou mais)", ufs_disponiveis, default=ufs_disponiveis)
        df_filtrado = df[df[c_uf].isin(ufs_selecionadas)]
    else:
        st.error("Coluna de UF não detectada. Verifique o nome na barra lateral.")
        df_filtrado = pd.DataFrame()

    if not df_filtrado.empty:
        st.info(f"Registros selecionados após filtro: {len(df_filtrado)}")
        
        if st.button("🚀 Gerar Mapa Filtrado"):
            kml = simplekml.Kml()
            cache = {}
            progress_bar = st.progress(0)
            status_msg = st.empty()

            for i, (idx, row) in enumerate(df_filtrado.iterrows()):
                progress_bar.progress((i + 1) / len(df_filtrado))
                
                mun_raw = str(row[c_mun]).strip() if c_mun in df.columns else ""
                uf = str(row[c_uf]).strip().upper()
                convenio = str(row[c_conv]).strip()
                perc_val = row[c_perc] if c_perc in df.columns else 0

                # Lógica de Localização (Município vs Capital)
                is_estado = False
                if mun_raw == "" or pd.isna(row[c_mun]) or "ESTADO DE" in mun_raw.upper() or mun_raw.upper() == "ESTADO":
                    is_estado = True
                    mun_limpo = CAPITAIS.get(uf, "Brasília")
                    cabecalho = "🏢 CONVÊNIO COM O GOVERNO DO ESTADO"
                else:
                    mun_limpo = limpar_nome(mun_raw)
                    cabecalho = f"🏙️ Município: {mun_raw}"

                query = f"{mun_limpo}, {uf}, Brasil"
                status_msg.text(f"Geocodificando ({i+1}/{len(df_filtrado)}): {query}")

                if query in cache:
                    location = cache[query]
                else:
                    try:
                        location = geolocator.geocode(query)
                        cache[query] = location
                    except: location = None

                if location:
                    pnt = kml.newpoint(name=convenio)
                    pnt.coords = [(location.longitude, location.latitude)]
                    icon_url, perc_texto = obter_estilo_execucao(perc_val)
                    
                    pnt.description = (
                        f"<b>{cabecalho}</b><br><br>"
                        f"<b>UF:</b> {uf}<br>"
                        f"<b>Nº Convênio:</b> {convenio}<br>"
                        f"<b>Status de Execução:</b> {perc_texto}"
                    )
                    pnt.style.iconstyle.icon.href = icon_url
            
            status_msg.empty()
            st.success(f"Mapa gerado com {len(df_filtrado)} pontos!")
            st.download_button("💾 BAIXAR KML FILTRADO", kml.kml(), f"mapa_convenios_{len(ufs_selecionadas)}UFs.kml")
