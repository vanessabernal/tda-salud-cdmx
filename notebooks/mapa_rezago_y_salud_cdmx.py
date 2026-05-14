"""
Mapa interactivo de CDMX que combina:
  - Choropleth de grado de rezago social (AGEB, CONEVAL 2020)
  - Ubicaciones de establecimientos de salud privados (DENUE 2025)
  - Ubicaciones de establecimientos de salud públicos (DENUE 2025)

Requiere correr antes el notebook 02_filtrado_y_split.ipynb para tener:
  data/processed/salud_cdmx_publico.csv
  data/processed/salud_cdmx_privado.csv
"""

import geopandas as gpd
import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap
from pathlib import Path
import urllib.request
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_HTML = PROJECT_ROOT / "mapa_rezago_y_salud_cdmx.html"

PUB_CSV = PROCESSED_DIR / "salud_cdmx_publico.csv"
PRIV_CSV = PROCESSED_DIR / "salud_cdmx_privado.csv"

DOWNLOAD_URL = (
    "https://www.datos.gob.mx/dataset/rezago_social/resource/"
    "afdb17f9-1f86-4511-9446-a46f688acbf2"
)

# =========================================================================
# Helpers para cargar el shapefile de rezago social (sin cambios vs antes)
# =========================================================================

def find_geodata_path():
    """Return a local shapefile or CONEVAL zip with AGEB rezago social geometry."""
    expected = RAW_DIR / "rezago_social_ageb_2020.shp"
    if expected.exists():
        return expected

    shapefiles = sorted(RAW_DIR.rglob("*.shp")) if RAW_DIR.exists() else []
    if shapefiles:
        return shapefiles[0]

    zipfiles = []
    if RAW_DIR.exists():
        zipfiles = sorted(
            path
            for path in RAW_DIR.glob("*.zip")
            if all(text in path.name.lower() for text in ["grs", "ageb", "2020"])
        )
    if zipfiles:
        return f"zip:///{zipfiles[0].as_posix()}"

    # Download the ZIP file automatically
    zip_url = "https://repodatos.atdt.gob.mx/CONEVAL/rezago_social/grs_ageb_2020_shp.zip"
    zip_path = RAW_DIR / "grs_ageb_2020_shp.zip"
    print("Descargando datos geoespaciales de rezago social AGEB 2020...")
    urllib.request.urlretrieve(zip_url, zip_path)
    print("Descomprimiendo el archivo ZIP...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(RAW_DIR)
    
    # Check again for shapefiles after download
    shapefiles = sorted(RAW_DIR.rglob("*.shp"))
    if shapefiles:
        return shapefiles[0]
    
    raise FileNotFoundError(
        "No se pudo encontrar la información geoespacial después de la descarga.\n\n"
        f"Verifica el contenido del directorio:\n{RAW_DIR}"
    )


def choose_column(gdf, candidates, contains=None, required=True):
    lower_columns = {column.lower(): column for column in gdf.columns}

    for column in candidates:
        if column in gdf.columns:
            return column
        if column.lower() in lower_columns:
            return lower_columns[column.lower()]

    if contains:
        for text in contains:
            for lower_column, original_column in lower_columns.items():
                if text in lower_column:
                    return original_column

    if required:
        raise KeyError(
            "No se encontro una columna esperada. Columnas disponibles:\n"
            + ", ".join(gdf.columns)
        )

    return None


def color_for_grs(value):
    colors = {
        "muy bajo": "#1a9850",
        "bajo": "#91cf60",
        "medio": "#fee08b",
        "alto": "#fc8d59",
        "muy alto": "#d73027",
    }
    return colors.get(str(value).strip().lower(), "#bdbdbd")


def clean_code(series, width):
    return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(width)


# =========================================================================
# 1) Cargar y filtrar la capa de rezago social
# =========================================================================

geodata_path = find_geodata_path()
gdf = gpd.read_file(geodata_path)

cvegeo_column = choose_column(
    gdf,
    ["CVEGEO", "CVE_GEO", "CVE_AGEB"],
    contains=["cvegeo"],
    required=False,
)
if not cvegeo_column:
    component_columns = ["clv_ntd", "clv_mnc", "clv_lcl", "ageb"]
    if all(column in gdf.columns for column in component_columns):
        cvegeo_column = "CVEGEO"
        gdf[cvegeo_column] = (
            clean_code(gdf["clv_ntd"], 2)
            + clean_code(gdf["clv_mnc"], 3)
            + clean_code(gdf["clv_lcl"], 4)
            + clean_code(gdf["ageb"], 4)
        )
    else:
        cvegeo_column = choose_column(gdf, ["ageb"], contains=["ageb"])

cve_ent_column = choose_column(
    gdf,
    ["CVE_ENT", "CVE_ENTI", "clv_ntd", "ENTIDAD"],
    contains=["cve_ent", "entidad", "clv_ntd"],
    required=False,
)
grs_column = choose_column(gdf, ["GRS", "gdo_rezsoc", "grado_rezsoc"], contains=["grs", "grado"])

if cve_ent_column:
    cdmx = gdf[clean_code(gdf[cve_ent_column], 2) == "09"].copy()
else:
    cdmx = gdf.iloc[0:0].copy()

if cdmx.empty:
    cdmx = gdf[gdf[cvegeo_column].astype(str).str.startswith("09")].copy()

if cdmx.empty:
    raise ValueError("No se encontraron AGEB de CDMX con clave de entidad 09.")

if cdmx.crs and cdmx.crs.to_epsg() != 4326:
    cdmx = cdmx.to_crs(epsg=4326)

print(f"AGEB de CDMX cargadas: {len(cdmx):,}")

# =========================================================================
# 2) Cargar las nubes de puntos de DENUE (salida del notebook 02)
# =========================================================================

for csv_path in [PUB_CSV, PRIV_CSV]:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"No se encontro {csv_path}\n"
            "Corre primero el notebook 02_filtrado_y_split.ipynb."
        )

df_pub = pd.read_csv(PUB_CSV)
df_priv = pd.read_csv(PRIV_CSV)

print(f"Ubicaciones publicas: {len(df_pub):,}")
print(f"Ubicaciones privadas: {len(df_priv):,}")

# =========================================================================
# 3) Construir el mapa interactivo
# =========================================================================

# prefer_canvas=True acelera muchisimo el render con miles de CircleMarker
m = folium.Map(
    location=[19.4326, -99.1332],
    zoom_start=11,
    tiles="CartoDB positron",
    prefer_canvas=True,
)

# --- Capa 1: Choropleth de rezago social ---
rezago_layer = folium.FeatureGroup(name="Grado de rezago social (AGEB)", show=True)
folium.GeoJson(
    cdmx,
    style_function=lambda feature: {
        "fillColor": color_for_grs(feature["properties"].get(grs_column)),
        "color": "#4a4a4a",
        "weight": 0.3,
        "fillOpacity": 0.65,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=[cvegeo_column, grs_column],
        aliases=["CVEGEO", "Grado de rezago social"],
        localize=True,
    ),
).add_to(rezago_layer)
rezago_layer.add_to(m)


def radio_marcador(n_servicios, base, escala):
    """Radio del CircleMarker proporcional a log2(n_servicios)."""
    return base + escala * np.log2(np.maximum(n_servicios, 1))


# --- Capa 2: Establecimientos PRIVADOS ---
# Color azul, marcadores chicos y semitransparentes (son ~13k puntos)
priv_layer = folium.FeatureGroup(
    name=f"Privado ({len(df_priv):,} ubicaciones)",
    show=True,
)
for _, row in df_priv.iterrows():
    folium.CircleMarker(
        location=[row["latitud"], row["longitud"]],
        radius=radio_marcador(row["n_servicios"], base=1.5, escala=1.0),
        color="#1f77b4",
        weight=0,
        fill=True,
        fill_color="#1f77b4",
        fill_opacity=0.45,
        tooltip=(
            f"<b>{row['nom_estab']}</b><br>"
            f"{row['tipo_infra']}<br>"
            f"Servicios en la ubicacion: {row['n_servicios']}"
        ),
    ).add_to(priv_layer)
priv_layer.add_to(m)

# --- Capa 3: Establecimientos PUBLICOS ---
# Color morado oscuro con borde blanco para destacar sobre cualquier color del choropleth
pub_layer = folium.FeatureGroup(
    name=f"Publico ({len(df_pub):,} ubicaciones)",
    show=True,
)
for _, row in df_pub.iterrows():
    folium.CircleMarker(
        location=[row["latitud"], row["longitud"]],
        radius=radio_marcador(row["n_servicios"], base=3.5, escala=1.5),
        color="#ffffff",
        weight=1.2,
        fill=True,
        fill_color="#4a148c",
        fill_opacity=0.92,
        tooltip=(
            f"<b>{row['nom_estab']}</b><br>"
            f"{row['tipo_infra']}<br>"
            f"Servicios en la ubicacion: {row['n_servicios']}"
        ),
    ).add_to(pub_layer)
pub_layer.add_to(m)

# --- Capa 4 (oculta por defecto): Mapa de calor de la oferta privada ---
heat_data = df_priv[["latitud", "longitud", "n_servicios"]].values.tolist()
heat_layer = folium.FeatureGroup(name="Densidad oferta privada (heatmap)", show=False)
HeatMap(
    heat_data,
    radius=12,
    blur=18,
    min_opacity=0.2,
    max_zoom=13,
).add_to(heat_layer)
heat_layer.add_to(m)

# =========================================================================
# 4) Leyenda fija y control de capas
# =========================================================================

legend_html = """
<div style="
    position: fixed;
    bottom: 30px; left: 30px;
    z-index: 9999;
    background: white;
    padding: 12px 14px;
    border: 1px solid #888;
    border-radius: 6px;
    font-family: Arial, sans-serif;
    font-size: 12px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    line-height: 1.6;
">
<b style="font-size:13px;">Grado de rezago social</b><br>
<i style="background:#1a9850;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Muy bajo<br>
<i style="background:#91cf60;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Bajo<br>
<i style="background:#fee08b;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Medio<br>
<i style="background:#fc8d59;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Alto<br>
<i style="background:#d73027;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Muy alto<br>
<hr style="margin:6px 0;">
<b style="font-size:13px;">Establecimientos de salud</b><br>
<i style="background:#4a148c;border:1px solid #fff;border-radius:50%;width:12px;height:12px;display:inline-block;margin-right:6px;"></i>Publico<br>
<i style="background:#1f77b4;border-radius:50%;width:10px;height:10px;display:inline-block;margin-right:6px;opacity:0.7;"></i>Privado<br>
<span style="font-size:10px;color:#666;">(Tamano proporcional a # de servicios en la ubicacion)</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

folium.LayerControl(collapsed=False).add_to(m)

# =========================================================================
# 5) Guardar
# =========================================================================

m.save(OUTPUT_HTML)
print(f"\nMapa guardado en: {OUTPUT_HTML}")
print("Abrelo en el navegador para explorar las tres capas.")
