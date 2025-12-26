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

# Configuração da página
st.set_page_config(page_title="GeoPhoto Pro 5km - Ministério da Agricultura", layout="wide")

st.title("📍 Levantamento Fotográfico de Grande Escala")
st.markdown("Filtro de densidade expandido para até 5km e nomenclatura em GMS.")

def dms_to_dd(dms, ref):
    degrees = dms[0]
    minutes = dms[1]
    seconds = dms[2]
    dd = degrees + (minutes / 60) + (seconds / 3600)
    if ref in ['S', 'W']:
        dd = -dd
    return dd

def dd_to_gms(decimal, is_lat):
    """Converte Graus Decimais para a string formatada em Graus, Minutos e Segundos."""
    abs_decimal = abs(decimal)
    degrees = int(abs_decimal)
    minutes_full = (abs_decimal - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 2)
    
    if is_lat:
        direction = 'N' if decimal >= 0 else 'S'
    else:
        direction = 'E' if decimal >= 0 else 'W'
        
    return f"{degrees}°{minutes}'{seconds}\"{direction}"

# Barra Lateral de Configurações - AMPLIADA PARA 5KM
st.sidebar.header("Configurações de Filtro")
raio_minimo = st.sidebar.slider(
    "Distância mínima entre pontos (metros)", 
    min_value=0, 
    max_value=5000, # Limite expandido para 5km
    value=100,      # Valor padrão inicial
    step=50,        # Passo de 50m para facilitar ajuste em grandes escalas
    help="Pontos capturados a uma distância menor que esta em relação ao ponto anterior serão descartados."
)

uploaded_files = st.file_uploader("Carregue as fotos do levantamento", type=['jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    raw_data = []
    
    for file in uploaded_files:
        try:
            img = Image(file)
            if img.has_exif and hasattr(img, 'gps_latitude'):
                lat = dms_to_dd(img.gps_latitude, img.gps_latitude_ref)
                lon = dms_to_dd(img.gps_longitude, img.gps_longitude_ref)
                
                dt_str = getattr(img, 'datetime_original', None)
                dt_obj = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S') if dt_str else datetime.fromtimestamp(file.last_modified)
                
                # Gerar nome em GMS
                nome_gms = f"{dd_to_gms(lat, True)}, {dd_to_gms(lon, False)}"
                
                raw_data.append({
                    "Arquivo": file.name,
                    "Latitude": lat,
                    "Longitude": lon,
                    "Timestamp": dt_obj,
                    "Coord_GMS": nome_gms
                })
        except Exception as e:
            st.error(f"Erro no arquivo {file.name}: {e}")

    if raw_data:
        # Ordenação Cronológica Obrigatória
        df_full = pd.DataFrame(raw_data).sort_values(by='Timestamp')
        
        # Lógica de Filtragem Espacial
        filtered_points = []
        if not df_full.empty:
            last_kept_point = df_full.iloc[0]
            filtered_points.append(last_kept_point)
            
            for i in range(1, len(df_full)):
                current_point = df_full.iloc[i]
                dist = geodesic(
                    (last_kept_point['Latitude'], last_kept_point['Longitude']),
                    (current_point['Latitude'], current_point['Longitude'])
                ).meters
                
                if dist >= raio_minimo:
                    filtered_points.append(current_point)
                    last_kept_point = current_point

        df_filtered = pd.DataFrame(filtered_points)
        
        # Métricas de Otimização
        st.info(f"📊 Resumo: {len(df_full)} fotos processadas ➔ {len(df_filtered)} pontos no KML.")

        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Dados do Trajeto")
            st.dataframe(df_filtered[['Timestamp', 'Coord_GMS']], use_container_width=True)
            
            # Geração do KML
            kml = simplekml.Kml()
            coords_list = []
            
            for _, row in df_filtered.iterrows():
                # Nome do ponto = Coordenada GMS
                pnt = kml.newpoint(name=row['Coord_GMS'], coords=[(row['Longitude'], row['Latitude'])])
                pnt.description = f"Foto: {row['Arquivo']}\nData: {row['Timestamp'].strftime('%d/%m/%Y %H:%M:%S')}"
                coords_list.append((row['Longitude'], row['Latitude']))
            
            # Linha de trajeto
            if len(coords_list) > 1:
                lin = kml.newlinestring(name="Caminho do Levantamento", coords=coords_list)
                lin.style.linestyle.color = simplekml.Color.cyan
                lin.style.linestyle.width = 5

            with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp:
                kml.save(tmp.name)
                with open(tmp.name, 'rb') as f:
                    st.download_button("💾 Baixar KML (GMS + Trajeto)", f, "levantamento_otimizado.kml")
                os.unlink(tmp.name)

        with col2:
            st.subheader("Visualização Espacial")
            # Centraliza o mapa na média dos pontos filtrados
            m = folium.Map(location=[df_filtered['Latitude'].mean(), df_filtered['Longitude'].mean()], zoom_start=13)
            
            # Desenha o trajeto no mapa interativo
            folium.PolyLine(df_filtered[['Latitude', 'Longitude']].values, color="cyan", weight=4, opacity=0.8).add_to(m)
            
            for _, row in df_filtered.iterrows():
                folium.Marker(
                    [row['Latitude'], row['Longitude']],
                    popup=f"<b>Coordenada:</b><br>{row['Coord_GMS']}<br><b>Hora:</b> {row['Timestamp'].strftime('%H:%M:%S')}",
                    icon=folium.Icon(color='blue', icon='camera')
                ).add_to(m)
            folium_static(m)
