import geopandas as gpd
import folium
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_HTML = PROJECT_ROOT / "mapa_rezago_cdmx.html"
DOWNLOAD_URL = (
    "https://www.datos.gob.mx/dataset/rezago_social/resource/"
    "afdb17f9-1f86-4511-9446-a46f688acbf2"
)


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

    raise FileNotFoundError(
        "No se encontro informacion geoespacial de rezago social AGEB 2020.\n\n"
        f"Descarga el SHP/ZIP de CONEVAL desde:\n{DOWNLOAD_URL}\n\n"
        f"Y guardalo en:\n{RAW_DIR}\n\n"
        "Tambien puedes descomprimirlo ahi; el script buscara cualquier .shp "
        "dentro de data/raw/."
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

m = folium.Map(location=[19.4326, -99.1332], zoom_start=11)

folium.GeoJson(
    cdmx,
    name="Grado de rezago social",
    style_function=lambda feature: {
        "fillColor": color_for_grs(feature["properties"].get(grs_column)),
        "color": "#4a4a4a",
        "weight": 0.3,
        "fillOpacity": 0.75,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=[cvegeo_column, grs_column],
        aliases=["CVEGEO", "Grado de rezago social"],
        localize=True,
    ),
).add_to(m)

folium.LayerControl().add_to(m)
m.save(OUTPUT_HTML)
print(f"Mapa guardado en: {OUTPUT_HTML}")
