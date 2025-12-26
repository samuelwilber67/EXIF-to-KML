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
st.set_page_config(page_title="GeoPhoto Pro - Ministério da Agricultura", layout="wide")

st.title("📍 Levantamento Fotográfico Georreferenciado")
st.markdown("Ferramenta otimizada para criação de trajetos e redução de densidade de pontos.")

def dms_to_dd(dms, ref):
    degrees = dms[0]
    minutes = dms[1]
    seconds = dms[2]
    dd = degrees + (minutes / 60) + (seconds / 3600)
    if ref in ['S', 'W']:
        dd = -dd
    return dd

# Barra Lateral de Configurações
st.sidebar.header("Configurações de Filtro")
raio_minimo = st.sidebar.slider("Raio de distância mínima entre pontos (metros)", 0, 500, 10, 
                               help="Pontos dentro deste raio em relação ao ponto anterior serão descartados para reduzir o tamanho do arquivo.")

uploaded_files = st.file_uploader("Carregue as fotos do levantamento", type=['jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    raw_data = []
    
    for file in uploaded_files:
        try:
            img = Image(file)
            if img.has_exif and hasattr(img, 'gps_latitude'):
                lat = dms_to_dd(img.gps_latitude, img.gps_latitude_ref)
                lon = dms_to_dd(img.gps_longitude, img.gps_longitude_ref)
                
                # Extração da data/hora original
                dt_str = getattr(img, 'datetime_original', None)
                dt_obj = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S') if dt_str else datetime.fromtimestamp(file.last_modified)
                
                raw_data.append({
                    "Arquivo": file.name,
                    "Latitude": lat,
                    "Longitude": lon,
                    "Timestamp": dt_obj,
                    "Coord_Nome": f"{round(lat, 6)}, {round(lon, 6)}"
                })
        except Exception as e:
            st.error(f"Erro no arquivo {file.name}: {e}")

    if raw_data:
        # 1. Ordenação Cronológica (Critério de Data e Horário)
        df_full = pd.DataFrame(raw_data).sort_values(by='Timestamp')
        
        # 2. Lógica de Filtragem por Raio (Distância)
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
        
        # Exibição de métricas
        st.info(f"Original: {len(df_full)} pontos | Otimizado: {len(df_filtered)} pontos (Redução de {100 - (len(df_filtered)/len(df_full)*100):.1f}%)")

        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Pontos do Trajeto")
            st.dataframe(df_filtered[['Timestamp', 'Coord_Nome']], use_container_width=True)
            
            # Geração do KML
            kml = simplekml.Kml()
            
            # Criar os pontos (Nome = Coordenada)
            coords_list = []
            for _, row in df_filtered.iterrows():
                pnt = kml.newpoint(name=row['Coord_Nome'], coords=[(row['Longitude'], row['Latitude'])])
                pnt.description = f"Arquivo: {row['Arquivo']}\nData: {row['Timestamp']}"
                coords_list.append((row['Longitude'], row['Latitude']))
            
            # Criar o Caminho (LineString) entre o primeiro e o último
            if len(coords_list) > 1:
                lin = kml.newlinestring(name="Trajeto Cronológico", coords=coords_list)
                lin.style.linestyle.color = simplekml.Color.red
                lin.style.linestyle.width = 3

            with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp:
                kml.save(tmp.name)
                with open(tmp.name, 'rb') as f:
                    st.download_button("💾 Baixar KML Otimizado", f, "trajeto_campo.kml")
                os.unlink(tmp.name)

        with col2:
            st.subheader("Mapa de Campo")
            m = folium.Map(location=[df_filtered['Latitude'].mean(), df_filtered['Longitude'].mean()], zoom_start=14)
            
            # Desenhar linha no mapa
            folium.PolyLine(df_filtered[['Latitude', 'Longitude']].values, color="red", weight=2.5, opacity=1).add_to(m)
            
            for _, row in df_filtered.iterrows():
                folium.CircleMarker(
                    [row['Latitude'], row['Longitude']],
                    radius=5,
                    color='blue',
                    fill=True,
                    popup=f"Hora: {row['Timestamp'].strftime('%H:%M:%S')}\nCoord: {row['Coord_Nome']}"
                ).add_to(m)
            folium_static(m)
