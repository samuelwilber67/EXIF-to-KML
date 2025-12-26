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
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Vistoria KML Pro",
    page_icon="📍",
    layout="wide"
)

# --- ESTILIZAÇÃO CUSTOMIZADA ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border-top: 4px solid #007bff;
        text-align: center;
    }
    .stDownloadButton > button {
        width: 100%;
        background-color: #28a745;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES TÉCNICAS ---

def dms_to_dd(dms, ref):
    dd = dms[0] + (dms[1] / 60) + (dms[2] / 3600)
    return -dd if ref in ['S', 'W'] else dd

def dd_to_gms(decimal, is_lat):
    abs_d = abs(decimal)
    d = int(abs_d)
    m = int((abs_d - d) * 60)
    s = round((((abs_d - d) * 60) - m) * 60, 2)
    dir = ('N' if decimal >= 0 else 'S') if is_lat else ('E' if decimal >= 0 else 'W')
    return f"{d}°{m}'{s}\"{dir}"

def get_road_route(points):
    if len(points) &lt; 2: 
        return points
    coords = ";".join([f"{p[1]},{p[0]}" for p in points])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("code") == "Ok":
            return [[c[1], c[0]] for c in r["routes"][0]["geometry"]["coordinates"]]
    except: 
        pass
    return points

# --- INTERFACE ---
st.title("📑 Geração de Arquivo KML a Partir das Fotos da Vistoria")

with st.sidebar:
    st.header("⚙️ Configurações")
    raio_minimo = st.slider("Raio de Otimização (m)", 0, 5000, 100, 50)
    seguir_estradas = st.toggle("Seguir estradas reais", value=True)
    st.info("O último ponto da sequência é sempre incluído obrigatoriamente.")

uploaded_files = st.file_uploader("Upload das fotos da vistoria", type=['jpg', 'jpeg'], accept_multiple_files=True)

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
                raw_data.append({
                    "Arquivo": file.name, "Lat": lat, "Lon": lon, "Time": dt_obj,
                    "GMS": f"{dd_to_gms(lat, True)}, {dd_to_gms(lon, False)}"
                })
        except: 
            continue

    if raw_data:
        # 1. Ordenação e Filtragem com Ponto Final Obrigatório
        df_all = pd.DataFrame(raw_data).sort_values(by='Time')
        filtered = [df_all.iloc[0].to_dict()]
        
        for i in range(1, len(df_all) - 1):
            last_p = filtered[-1]
            curr_p = df_all.iloc[i]
            if geodesic((last_p['Lat'], last_p['Lon']), (curr_p['Lat'], curr_p['Lon'])).meters >= raio_minimo:
                filtered.append(curr_p.to_dict())
        
        # Inclusão obrigatória do último ponto
        if len(df_all) > 1:
            filtered.append(df_all.iloc[-1].to_dict())
        
        df_f = pd.DataFrame(filtered)

        # 2. Cálculos de Distância para Excel e KML
        dist_parcial = [0.0]
        dist_acumulada = [0.0]
        for i in range(1, len(df_f)):
            d = geodesic((df_f.iloc[i-1]['Lat'], df_f.iloc[i-1]['Lon']), (df_f.iloc[i]['Lat'], df_f.iloc[i]['Lon'])).meters
            dist_parcial.append(round(d, 2))
            dist_acumulada.append(round(sum(dist_parcial) / 1000, 3))
        
        df_f['Dist_Parcial_m'] = dist_parcial
        df_f['KM_Trecho'] = dist_acumulada

        # --- LAYOUT DE RESULTADOS ---
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<div class="metric-card">📸 Fotos<br><h2>{len(df_all)}</h2></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="metric-card">📍 Pontos KML<br><h2>{len(df_f)}</h2></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="metric-card">🛣️ Extensão<br><h2>{df_f["KM_Trecho"].max()} km</h2></div>', unsafe_allow_html=True)

        st.markdown("---")
        col_map, col_down = st.columns([2, 1])

        with col_down:
            st.subheader("📥 Downloads")
            
            # Gerar Excel
            output_excel = io.BytesIO()
            df_excel = df_f[['Arquivo', 'Time', 'GMS', 'Dist_Parcial_m', 'KM_Trecho']].copy()
            df_excel.columns = ['Arquivo', 'Data_Hora', 'Coordenadas_GMS', 'Dist_Parcial_Metros', 'KM_Acumulado']
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                df_excel.to_excel(writer, index=False, sheet_name='Relatorio_Vistoria')
            st.download_button("📊 Baixar Relatório Excel", output_excel.getvalue(), "relatorio_vistoria.xlsx")

            # Gerar KML
            kml = simplekml.Kml()
            ponto_coords = []
            for i, row in df_f.iterrows():
                # Lógica de Nomeação
                if i == 0:
                    nome = f"Início do trecho - {row['GMS']}"
                elif i == len(df_f) - 1:
                    nome = f"Final do trecho - {row['GMS']}"
                else:
                    nome = row['GMS']
                
                pnt = kml.newpoint(name=nome, coords=[(row['Lon'], row['Lat'])])
                pnt.description = f"Foto km {row['KM_Trecho']}\nArquivo: {row['Arquivo']}\nData: {row['Time']}"
                ponto_coords.append((row['Lat'], row['Lon']))

            if seguir_estradas:
                with st.spinner("Traçando rota por estradas..."):
                    rota_kml = get_road_route(ponto_coords)
            else:
                rota_kml = ponto_coords

            lin = kml.newlinestring(name="Eixo da Vistoria", coords=[(p[1], p[0]) for p in rota_kml])
            lin.style.linestyle.color = simplekml.Color.blue
            lin.style.linestyle.width = 4

            with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp:
                kml.save(tmp.name)
                with open(tmp.name, 'rb') as f:
                    st.download_button("🗺️ Baixar Arquivo KML", f, "vistoria_trecho.kml")
                os.unlink(tmp.name)

        with col_map:
            st.subheader("🗺️ Mapa do Trecho")
            m = folium.Map(location=[df_f['Lat'].mean(), df_f['Lon'].mean()], zoom_start=13, tiles="cartodbpositron")
            folium.PolyLine(rota_kml, color="#007bff", weight=4).add_to(m)
            for i, row in df_f.iterrows():
                folium.Marker([row['Lat'], row['Lon']], popup=f"KM {row['KM_Trecho']}").add_to(m)
            folium_static(m, width=700)
