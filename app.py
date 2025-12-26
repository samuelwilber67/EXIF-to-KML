import streamlit as st
from exif import Image
import simplekml
import folium
from streamlit_folium import folium_static
import pandas as pd
import tempfile
import os

# Configuração da página
st.set_page_config(page_title="Photo EXIF to KML", layout="wide")

st.title("📍 Conversor de Fotos EXIF para KML")
st.markdown("""
Esta ferramenta extrai coordenadas GPS de suas fotos e gera um arquivo KML para uso em softwares de engenharia e SIG.
**Privacidade:** Suas fotos são processadas localmente e não são armazenadas no servidor.
""")

def dms_to_dd(dms, ref):
    degrees = dms[0]
    minutes = dms[1]
    seconds = dms[2]
    dd = degrees + (minutes / 60) + (seconds / 3600)
    if ref in ['S', 'W']:
        dd = -dd
    return dd

uploaded_files = st.file_uploader("Arraste suas fotos (JPG/JPEG) aqui", type=['jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    data_list = []
    
    for file in uploaded_files:
        try:
            img = Image(file)
            if img.has_exif and hasattr(img, 'gps_latitude'):
                lat = dms_to_dd(img.gps_latitude, img.gps_latitude_ref)
                lon = dms_to_dd(img.gps_longitude, img.gps_longitude_ref)
                
                data_list.append({
                    "Arquivo": file.name,
                    "Latitude": round(lat, 6),
                    "Longitude": round(lon, 6)
                })
            else:
                st.warning(f"⚠️ {file.name}: Sem dados de GPS encontrados.")
        except Exception as e:
            st.error(f"❌ Erro ao processar {file.name}: {e}")

    if data_list:
        df = pd.DataFrame(data_list)
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Dados Extraídos")
            st.dataframe(df, use_container_width=True)
            
            # Geração do KML
            kml = simplekml.Kml()
            for _, row in df.iterrows():
                kml.newpoint(name=row['Arquivo'], coords=[(row['Longitude'], row['Latitude'])])
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp:
                kml.save(tmp.name)
                with open(tmp.name, 'rb') as f:
                    st.download_button(
                        label="💾 Baixar Arquivo KML",
                        data=f,
                        file_name="levantamento_fotos.kml",
                        mime="application/vnd.google-earth.kml+xml"
                    )
                os.unlink(tmp.name)

        with col2:
            st.subheader("Visualização no Mapa")
            m = folium.Map(location=[df['Latitude'].mean(), df['Longitude'].mean()], zoom_start=12)
            for _, row in df.iterrows():
                folium.Marker(
                    [row['Latitude'], row['Longitude']], 
                    popup=row['Arquivo'],
                    tooltip=row['Arquivo']
                ).add_to(m)
            folium_static(m)
    else:
        st.info("Aguardando upload de fotos com metadados de localização.")