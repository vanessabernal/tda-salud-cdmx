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
from pathlib import Path
import urllib.request
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_HTML = PROJECT_ROOT / "mapa_rezago_y_salud_cdmx.html"

PUB_CSV = PROCESSED_DIR / "salud_cdmx_publico.csv"
PRIV_CSV = PROCESSED_DIR / "salud_cdmx_privado.csv"
DENUE_ZIP = RAW_DIR / "denue_09_csv.zip"
DENUE_SALUD_CSV = PROCESSED_DIR / "salud_cdmx_denue_limpio.csv"

DOWNLOAD_URL = (
    "https://www.datos.gob.mx/dataset/rezago_social/resource/"
    "afdb17f9-1f86-4511-9446-a46f688acbf2"
)
DENUE_DOWNLOAD_URL = (
    "https://cfcetlsadls.blob.core.windows.net/raw/inegi/denue_por_estado/"
    "ciudad_de_mexico_zip/denue_09_csv.zip?sv=2025-07-05&spr=https&"
    "st=2026-04-24T19%3A24%3A46Z&se=2026-06-09T19%3A24%3A00Z&sr=b&sp=r&"
    "sig=%2F5%2BqqFCki1Y%2Bdl3Y21slq3HOd7Ek5cDjh849JlR37Dc%3D"
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


def score_for_grs(value):
    scores = {
        "muy bajo": 1,
        "bajo": 2,
        "medio": 3,
        "alto": 4,
        "muy alto": 5,
    }
    return scores.get(str(value).strip().lower(), np.nan)


def color_for_prioridad(value):
    colors = {
        "Baja": "#1a9850",
        "Media": "#fee08b",
        "Alta": "#fc8d59",
        "Muy alta": "#d73027",
    }
    return colors.get(str(value).strip(), "#bdbdbd")


def clean_code(series, width):
    return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(width)


def preprocess_denue_salud():
    """Create the cleaned DENUE health CSV used by the public/private split."""
    if DENUE_SALUD_CSV.exists():
        return

    if not DENUE_ZIP.exists():
        raise FileNotFoundError(
            f"No se encontro {DENUE_ZIP}\n\n"
            "Descargalo desde la raiz del repo con:\n"
            f'curl.exe -L "{DENUE_DOWNLOAD_URL}" -o data/raw/denue_09_csv.zip'
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DENUE_ZIP) as z:
        with z.open("conjunto_de_datos/denue_inegi_09_.csv") as csv_file:
            df_raw = pd.read_csv(csv_file, encoding="latin1", low_memory=False)

    df = df_raw[df_raw["codigo_act"].astype(str).str.startswith("62")].copy()
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"])

    cols = [
        "id", "nom_estab", "codigo_act", "nombre_act", "per_ocu",
        "municipio", "localidad", "latitud", "longitud", "fecha_alta",
    ]
    df[cols].to_csv(DENUE_SALUD_CSV, index=False)
    print(f"CSV DENUE salud creado: {DENUE_SALUD_CSV} ({len(df):,} filas)")


def build_public_private_csvs():
    """Generate public/private location CSVs from the cleaned DENUE health file."""
    if PUB_CSV.exists() and PRIV_CSV.exists():
        return

    preprocess_denue_salud()

    df = pd.read_csv(DENUE_SALUD_CSV)
    df["codigo_4d"] = df["codigo_act"].astype(str).str[:4]

    prefijos_validos = ["6211", "6212", "6213", "6214", "6215", "6221", "6222", "6223"]
    mapa_tipo = {
        "6211": "Consultorio medico",
        "6212": "Consultorio dental",
        "6213": "Consultorio otros profesionales",
        "6214": "Centro ambulatorio",
        "6215": "Laboratorio/Dx",
        "6221": "Hospital general",
        "6222": "Hospital psiquiatrico",
        "6223": "Hospital especializado",
    }

    df = df[df["codigo_4d"].isin(prefijos_validos)].copy()
    df["tipo_infra"] = df["codigo_4d"].map(mapa_tipo)

    nombre_lower = df["nombre_act"].astype(str).str.lower()
    es_publico = nombre_lower.str.contains("sector público|sector publico", regex=True)
    es_privado = nombre_lower.str.contains("sector privado")
    df["sector"] = np.select(
        [es_publico, es_privado],
        ["publico", "privado"],
        default="otro",
    )
    df = df[df["sector"].isin(["publico", "privado"])].copy()

    points = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitud"], df["latitud"]),
        crs="EPSG:4326",
    ).to_crs("EPSG:32614")
    df["x_m"] = points.geometry.x.values
    df["y_m"] = points.geometry.y.values

    def tipos_unicos(values):
        return "; ".join(sorted(values.dropna().unique()))

    def tipo_mas_frecuente(values):
        counts = values.value_counts()
        return counts.index[0] if len(counts) else None

    def colapsar_por_ubicacion(df_in):
        return (
            df_in.groupby(["x_m", "y_m"], as_index=False)
            .agg(
                n_servicios=("id", "size"),
                id=("id", "first"),
                nom_estab=("nom_estab", "first"),
                codigo_act=("codigo_act", "first"),
                nombre_act=("nombre_act", "first"),
                tipo_infra=("tipo_infra", tipo_mas_frecuente),
                tipos_presentes=("tipo_infra", tipos_unicos),
                sector=("sector", "first"),
                per_ocu=("per_ocu", "first"),
                municipio=("municipio", "first"),
                localidad=("localidad", "first"),
                latitud=("latitud", "first"),
                longitud=("longitud", "first"),
                fecha_alta=("fecha_alta", "first"),
            )
        )

    df_pub = colapsar_por_ubicacion(df[df["sector"] == "publico"])
    df_priv = colapsar_por_ubicacion(df[df["sector"] == "privado"])

    lat_min, lat_max = 19.05, 19.60
    lon_min, lon_max = -99.40, -98.94

    def filtrar_bb(df_in):
        return df_in[
            df_in["latitud"].between(lat_min, lat_max)
            & df_in["longitud"].between(lon_min, lon_max)
        ].copy()

    df_pub = filtrar_bb(df_pub)
    df_priv = filtrar_bb(df_priv)

    cols_finales = [
        "id", "nom_estab", "codigo_act", "nombre_act",
        "tipo_infra", "tipos_presentes", "n_servicios",
        "sector", "per_ocu", "municipio", "localidad",
        "latitud", "longitud", "x_m", "y_m", "fecha_alta",
    ]
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df_pub[cols_finales].to_csv(PUB_CSV, index=False)
    df_priv[cols_finales].to_csv(PRIV_CSV, index=False)
    print(f"CSV publico creado: {PUB_CSV} ({len(df_pub):,} ubicaciones)")
    print(f"CSV privado creado: {PRIV_CSV} ({len(df_priv):,} ubicaciones)")


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
cdmx = cdmx.reset_index(drop=True)

print(f"AGEB de CDMX cargadas: {len(cdmx):,}")

# =========================================================================
# 2) Cargar las nubes de puntos de DENUE (salida del notebook 02)
# =========================================================================

build_public_private_csvs()

df_pub = pd.read_csv(PUB_CSV)
df_priv = pd.read_csv(PRIV_CSV)

print(f"Ubicaciones publicas: {len(df_pub):,}")
print(f"Ubicaciones privadas: {len(df_priv):,}")

# =========================================================================
# 3) Calcular prioridad de rezago en salud por AGEB
# =========================================================================

df_pub["sector"] = "publico"
df_priv["sector"] = "privado"
df_salud = pd.concat([df_pub, df_priv], ignore_index=True)

salud_points = gpd.GeoDataFrame(
    df_salud,
    geometry=gpd.points_from_xy(df_salud["longitud"], df_salud["latitud"]),
    crs="EPSG:4326",
)

join = gpd.sjoin(
    salud_points[["sector", "n_servicios", "geometry"]],
    cdmx[[cvegeo_column, "geometry"]],
    how="left",
    predicate="within",
)

join_valid = join.dropna(subset=["index_right"]).copy()
join_valid["index_right"] = join_valid["index_right"].astype(int)

conteo = join_valid.groupby("index_right").agg(
    servicios_salud=("n_servicios", "sum"),
    ubicaciones_salud=("n_servicios", "size"),
)
conteo_sector = join_valid.pivot_table(
    index="index_right",
    columns="sector",
    values="n_servicios",
    aggfunc="sum",
    fill_value=0,
)
conteo["servicios_publicos"] = conteo_sector.get("publico", 0)
conteo["servicios_privados"] = conteo_sector.get("privado", 0)

for column in ["servicios_salud", "ubicaciones_salud", "servicios_publicos", "servicios_privados"]:
    cdmx[column] = conteo[column].reindex(cdmx.index).fillna(0).astype(int)

cdmx_metric = cdmx.to_crs("EPSG:32614")
cdmx["area_km2"] = cdmx_metric.geometry.area / 1_000_000
cdmx["servicios_por_km2"] = cdmx["servicios_salud"] / cdmx["area_km2"].replace(0, np.nan)
cdmx["grs_score"] = cdmx[grs_column].map(score_for_grs)

max_density = cdmx["servicios_por_km2"].quantile(0.95)
if pd.isna(max_density) or max_density == 0:
    max_density = 1

cdmx["oferta_norm"] = (cdmx["servicios_por_km2"] / max_density).clip(0, 1).fillna(0)
cdmx["prioridad_score"] = cdmx["grs_score"] * (1 - 0.65 * cdmx["oferta_norm"])

cdmx["prioridad_salud"] = pd.cut(
    cdmx["prioridad_score"],
    bins=[0, 1.8, 2.8, 3.8, 5.1],
    labels=["Baja", "Media", "Alta", "Muy alta"],
    include_lowest=True,
).astype(str)

print("Prioridad de rezago en salud por AGEB:")
print(cdmx["prioridad_salud"].value_counts().sort_index())

# =========================================================================
# 4) Construir el mapa interactivo
# =========================================================================

m = folium.Map(
    location=[19.4326, -99.1332],
    zoom_start=11,
    tiles="CartoDB positron",
    prefer_canvas=True,
)

# --- Capa principal: prioridad de rezago en salud ---
rezago_layer = folium.FeatureGroup(name="Prioridad de rezago en salud (AGEB)", show=True)
folium.GeoJson(
    cdmx,
    style_function=lambda feature: {
        "fillColor": color_for_prioridad(feature["properties"].get("prioridad_salud")),
        "color": "#4a4a4a",
        "weight": 0.3,
        "fillOpacity": 0.65,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=[
            cvegeo_column,
            grs_column,
            "prioridad_salud",
            "servicios_salud",
            "servicios_publicos",
            "servicios_privados",
            "servicios_por_km2",
        ],
        aliases=[
            "CVEGEO",
            "Grado de rezago social",
            "Prioridad en salud",
            "Servicios de salud",
            "Servicios publicos",
            "Servicios privados",
            "Servicios por km2",
        ],
        localize=True,
    ),
).add_to(rezago_layer)
rezago_layer.add_to(m)


def radio_marcador(n_servicios, base, escala):
    """Radio del CircleMarker proporcional a log2(n_servicios)."""
    return base + escala * np.log2(np.maximum(n_servicios, 1))


# --- Capa 2: Establecimientos PRIVADOS ---
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

# =========================================================================
# 5) Leyenda fija y control de capas
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
<b style="font-size:13px;">Prioridad de rezago en salud</b><br>
<i style="background:#1a9850;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Baja<br>
<i style="background:#fee08b;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Media<br>
<i style="background:#fc8d59;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Alta<br>
<i style="background:#d73027;width:14px;height:14px;display:inline-block;margin-right:6px;"></i>Muy alta<br>
<hr style="margin:6px 0;">
<b style="font-size:13px;">Establecimientos de salud</b><br>
<i style="background:#4a148c;border:1px solid #fff;border-radius:50%;width:12px;height:12px;display:inline-block;margin-right:6px;"></i>Publico<br>
<i style="background:#1f77b4;border-radius:50%;width:10px;height:10px;display:inline-block;margin-right:6px;opacity:0.7;"></i>Privado<br>
<span style="font-size:10px;color:#666;">Tamano proporcional a # de servicios.</span>
<hr style="margin:6px 0;">
<span style="font-size:10px;color:#666;">
Combina GRS general con baja densidad<br>
de establecimientos de salud DENUE.
</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

folium.LayerControl(collapsed=False).add_to(m)

# =========================================================================
# 6) Guardar
# =========================================================================

m.save(OUTPUT_HTML)
print(f"\nMapa guardado en: {OUTPUT_HTML}")
print("Abrelo en el navegador para explorar la prioridad por AGEB y las capas publico/privado.")
