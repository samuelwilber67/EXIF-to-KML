import streamlit as st
from exif import Image
import simplekml
import folium
from streamlit_folium import folium_static
import pandas as pd
from datetime import datetime
from geopy.distance import geodesic
import tempfile
import os
import requests

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Vistoria KML Pro",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CUSTOMIZADA (CSS) ---
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #007bff;
        color: white;
    }
    .reportview-container .main .block-container {
        padding-top: 2rem;
    }
    .metric-card {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 5px solid #007bff;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---

def get_road_route(points):
    """Obtém a rota seguindo estradas reais via API OSRM."""
    if len(points) < 2:
        return points
    
    # Formata as coordenadas para a API (lon,lat;lon,lat)
    coords_str = ";".join([f"{p[1]},{p[0]}" for p in points])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("code") == "Ok":
            # Retorna a lista de coordenadas da estrada [lat, lon]
            return [[c[1], c[0]] for c in data["routes"][0]["geometry"]["coordinates"]]
    except:
        pass
    return points # Fallback para linha reta em caso de erro

def dms_to_dd(dms, ref):
    degrees = dms[0]
    minutes = dms[1]
    seconds = dms[2]
    dd = degrees + (minutes / 60) + (seconds / 3600)
    if ref in ['S', 'W']:
        dd = -dd
    return dd

def dd_to_gms(decimal, is_lat):
    abs_decimal = abs(decimal)
    degrees = int(abs_decimal)
    minutes_full = (abs_decimal - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 2)
    direction = ('N' if decimal >= 0 else 'S') if is_lat else ('E' if decimal >= 0 else 'W')
    return f"{degrees}°{minutes}'{seconds}\"{direction}"

# --- CABEÇALHO ---
st.title("📑 Geração de Arquivo KML a Partir das Fotos da Vistoria")
st.info("Esta ferramenta processa fotos georreferenciadas, otimiza a densidade de pontos e traça rotas por estradas existentes.")

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/854/854878.png", width=100)
    st.header("Painel de Controle")
    
    raio_minimo = st.slider(
        "Distância mínima entre fotos (m)", 
        0, 5000, 100, 50,
        help="Pontos muito próximos serão ignorados para limpar o trajeto."
    )
    
    st.markdown("---")
    st.markdown("### Configurações de Rota")
    seguir_estradas = st.toggle("Seguir estradas existentes", value=True, help="Usa inteligência de mapas para traçar o caminho por ruas e rodovias.")
    
    st.markdown("---")
    st.caption("Desenvolvido para vistorias técnicas e engenharia.")

# --- CONTEÚDO PRINCIPAL ---
uploaded_files = st.file_uploader("Selecione ou arraste as fotos da vistoria", type=['jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    raw_data = []
    
    with st.spinner("Extraindo metadados EXIF..."):
        for file in uploaded_files:
            try:
                img = Image(file)
                if img.has_exif and hasattr(img, 'gps_latitude'):
                    lat = dms_to_dd(img.gps_latitude, img.gps_latitude_ref)
                    lon = dms_to_dd(img.gps_longitude, img.gps_longitude_ref)
                    dt_str = getattr(img, 'datetime_original', None)
                    dt_obj = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S') if dt_str else datetime.fromtimestamp(file.last_modified)
                    
                    raw_data.append({
                        "Arquivo": file.name,
                        "Latitude": lat,
                        "Longitude": lon,
                        "Timestamp": dt_obj,
                        "GMS": f"{dd_to_gms(lat, True)}, {dd_to_gms(lon, False)}"
                    })
            except:
                continue

    if raw_data:
        # Ordenação e Filtragem
        df_full = pd.DataFrame(raw_data).sort_values(by='Timestamp')
        filtered_points = []
        if not df_full.empty:
            last_p = df_full.iloc[0]
            filtered_points.append(last_p)
            for i in range(1, len(df_full)):
                curr_p = df_full.iloc[i]
                if geodesic((last_p['Latitude'], last_p['Longitude']), (curr_p['Latitude'], curr_p['Longitude'])).meters >= raio_minimo:
                    filtered_points.append(curr_p)
                    last_p = curr_p
        
        df_filtered = pd.DataFrame(filtered_points)

        # Métricas Modernas
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f'<div class="metric-card"><b>Total de Fotos</b><br><h2>{len(df_full)}</h2></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-card"><b>Pontos Filtrados</b><br><h2>{len(df_filtered)}</h2></div>', unsafe_allow_html=True)
        with m3:
            reducao = (1 - len(df_filtered)/len(df_full))*100
            st.markdown(f'<div class="metric-card"><b>Otimização</b><br><h2>{reducao:.1f}%</h2></div>', unsafe_allow_html=True)

        st.markdown("---")

        c1, c2 = st.columns([1, 2])

        with c1:
            st.subheader("📋 Relatório de Pontos")
            st.dataframe(df_filtered[['Timestamp', 'GMS']], use_container_width=True, height=400)
            
            # Processamento da Rota
            ponto_coords = [(row['Latitude'], row['Longitude']) for _, row in df_filtered.iterrows()]
            
            if seguir_estradas:
                with st.spinner("Calculando rota por estradas..."):
                    rota_final = get_road_route(ponto_coords)
            else:
                rota_final = ponto_coords

            # Geração do KML
            kml = simplekml.Kml()
            for _, row in df_filtered.iterrows():
                pnt = kml.newpoint(name=row['GMS'], coords=[(row['Longitude'], row['Latitude'])])
                pnt.description = f"Vistoria: {row['Arquivo']}\nData: {row['Timestamp']}"
            
            if len(rota_final) > 1:
                lin = kml.newlinestring(name="Caminho da Vistoria")
                lin.coords = [(p[1], p[0]) for p in rota_final]
                lin.style.linestyle.color = simplekml.Color.blue
                lin.style.linestyle.width = 4

            with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp:
                kml.save(tmp.name)
                with open(tmp.name, 'rb') as f:
                    st.download_button("🚀 Baixar Arquivo KML Final", f, "vistoria_estrada.kml", use_container_width=True)
                os.unlink(tmp.name)

        with c2:
            st.subheader("🗺️ Mapa Interativo")
            m = folium.Map(location=[df_filtered['Latitude'].mean(), df_filtered['Longitude'].mean()], zoom_start=13, tiles="cartodbpositron")
            
            # Desenha a rota (estrada ou reta)
            folium.PolyLine(rota_final, color="#007bff", weight=5, opacity=0.7).add_to(m)
            
            for _, row in df_filtered.iterrows():
                folium.CircleMarker(
                    [row['Latitude'], row['Longitude']],
                    radius=6, color="#007bff", fill=True, fill_color="#ffffff",
                    popup=row['GMS']
                ).add_to(m)
            
            folium_static(m, width=800)
