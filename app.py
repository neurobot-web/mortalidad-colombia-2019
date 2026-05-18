import os
import json
import unicodedata
import pandas as pd
import plotly.express as px
import dash
from dash import dcc, html, dash_table, Input, Output
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    title="Mortalidad Colombia 2019",
    suppress_callback_exceptions=True,
)
server = app.server

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

RUTA_NOFETAL = os.path.join(DATA_DIR, "Anexo1.NoFetal2019_CE_15-03-23.xlsx")
RUTA_CODIGOS = os.path.join(DATA_DIR, "Anexo2.CodigosDeMuerte_CE_15-03-23.xlsx")
RUTA_DIVIPOLA = os.path.join(DATA_DIR, "Divipola_CE.xlsx")
RUTA_GEOJSON = os.path.join(ASSETS_DIR, "colombia.geo.json")

COLORES = {
    "primario": "#01696f",
    "secundario": "#4f98a3",
    "acento": "#da7101",
    "peligro": "#a12c7b",
    "exito": "#437a22",
    "fondo": "#f7f6f2",
    "superficie": "#f9f8f5",
    "texto": "#28251d",
    "texto_suave": "#7a7974",
    "borde": "#dcd9d5",
}

PALETA_DISC = ["#01696f", "#da7101", "#a12c7b", "#437a22", "#006494", "#7a39bb", "#d19900"]
LAYOUT_BASE = dict(
    paper_bgcolor=COLORES["superficie"],
    plot_bgcolor=COLORES["fondo"],
    font=dict(family="Inter, Arial, sans-serif", color=COLORES["texto"], size=13),
    margin=dict(t=60, b=45, l=45, r=20),
)

CARD = {
    "borderRadius": "12px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
    "background": COLORES["superficie"],
    "padding": "18px",
    "border": f"1px solid {COLORES['borde']}",
}

KPI_STYLE = {
    "background": COLORES["superficie"],
    "borderRadius": "12px",
    "padding": "20px 24px",
    "textAlign": "center",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
    "border": f"1px solid {COLORES['borde']}",
}

MESES_NOMBRES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}

CATEGORIAS_EDAD = {
    (0, 4): "Mortalidad neonatal",
    (5, 6): "Mortalidad infantil",
    (7, 8): "Primera infancia",
    (9, 10): "Niñez",
    (11, 11): "Adolescencia",
    (12, 13): "Juventud",
    (14, 16): "Adultez temprana",
    (17, 19): "Adultez intermedia",
    (20, 24): "Vejez",
    (25, 28): "Longevidad / Centenarios",
    (29, 29): "Edad desconocida",
}

ORDEN_EDAD = list(dict.fromkeys(CATEGORIAS_EDAD.values())) + ["Sin información", "Otro"]


def validar_archivo(ruta):
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No se encontró el archivo: {ruta}")
    if not os.access(ruta, os.R_OK):
        raise PermissionError(f"No hay permisos de lectura para el archivo: {ruta}")


def normalizar_texto(texto):
    if pd.isna(texto):
        return None
    texto = str(texto).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = " ".join(texto.split())
    return texto


def limpiar_causa(valor):
    if pd.isna(valor):
        return pd.NA
    valor = str(valor).strip().upper().replace(".", "")
    valor = " ".join(valor.split())
    if valor in {"", "NAN", "NONE"}:
        return pd.NA
    return valor


def asignar_categoria_edad(valor):
    if pd.isna(valor):
        return "Sin información"
    try:
        valor = int(valor)
    except Exception:
        return "Sin información"
    for (a, b), nombre in CATEGORIAS_EDAD.items():
        if a <= valor <= b:
            return nombre
    return "Otro"


def detectar_columna(df, candidatos):
    mapa = {normalizar_texto(col): col for col in df.columns}
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        if candidato_norm in mapa:
            return mapa[candidato_norm]
    return None


def cargar_anexo1():
    validar_archivo(RUTA_NOFETAL)
    df = pd.read_excel(RUTA_NOFETAL)
    df.columns = [str(c).strip().upper() for c in df.columns]
    renombre = {
        "COD_DEPARTAMENTO": "COD_DPTO",
        "COD_MUNICIPIO": "COD_MUNIC",
        "MES": "MES_DEF",
        "COD_MUERTE": "CAUSA",
    }
    df = df.rename(columns=renombre)
    requeridas = ["COD_DPTO", "COD_MUNIC", "MES_DEF", "SEXO", "GRUPO_EDAD1", "CAUSA"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias en Anexo1: {faltantes}")
    for col in ["COD_DPTO", "COD_MUNIC", "MES_DEF", "SEXO", "GRUPO_EDAD1"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["CAUSA"] = df["CAUSA"].apply(limpiar_causa)
    return df


def cargar_anexo2():
    validar_archivo(RUTA_CODIGOS)
    bruto = pd.read_excel(RUTA_CODIGOS, header=None)
    fila_header = None
    for i in range(min(20, len(bruto))):
        fila = [normalizar_texto(x) for x in bruto.iloc[i].tolist()]
        if any(x and "CODIGO DE LA CIE-10 CUATRO CARACTERES" in x for x in fila):
            fila_header = i
            break
    if fila_header is None:
        raise ValueError("No fue posible detectar la fila de encabezado en Anexo2.")
    df_cod = pd.read_excel(RUTA_CODIGOS, header=fila_header)
    df_cod.columns = [str(c).strip().replace(chr(10), " ") for c in df_cod.columns]
    df_cod.columns = [" ".join(col.split()) for col in df_cod.columns]
    col_causa = detectar_columna(df_cod, [
        "Código de la CIE-10 cuatro caracteres",
        "Codigo de la CIE-10 cuatro caracteres",
    ])
    col_desc = detectar_columna(df_cod, [
        "Descripcion de códigos mortalidad a cuatro caracteres",
        "Descripción de códigos mortalidad a cuatro caracteres",
        "Descripcion de codigos mortalidad a cuatro caracteres",
        "Descripción de codigos mortalidad a cuatro caracteres",
    ])
    if not col_causa or not col_desc:
        raise ValueError(f"No se identificaron columnas válidas en Anexo2. Columnas detectadas: {df_cod.columns.tolist()}")
    df_cod = df_cod[[col_causa, col_desc]].copy()
    df_cod.columns = ["CAUSA", "NOMBRE_CAUSA"]
    df_cod["CAUSA"] = df_cod["CAUSA"].apply(limpiar_causa)
    df_cod["NOMBRE_CAUSA"] = df_cod["NOMBRE_CAUSA"].astype(str).str.strip()
    df_cod = df_cod.replace({"NOMBRE_CAUSA": {"nan": pd.NA, "": pd.NA}})
    df_cod = df_cod.dropna(subset=["CAUSA", "NOMBRE_CAUSA"]).drop_duplicates(subset=["CAUSA"])
    return df_cod


def cargar_divipola():
    validar_archivo(RUTA_DIVIPOLA)
    df_div = pd.read_excel(RUTA_DIVIPOLA, sheet_name=0)
    df_div.columns = [str(c).strip().upper() for c in df_div.columns]
    df_div = df_div.rename(columns={
        "COD_DEPARTAMENTO": "COD_DPTO",
        "DEPARTAMENTO": "NOM_DPTO",
        "COD_MUNICIPIO": "COD_MUNIC",
        "MUNICIPIO": "NOM_MUNIC",
    })
    requeridas = ["COD_DPTO", "NOM_DPTO", "COD_MUNIC", "NOM_MUNIC"]
    faltantes = [c for c in requeridas if c not in df_div.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias en Divipola: {faltantes}")
    for col in ["COD_DPTO", "COD_MUNIC"]:
        df_div[col] = pd.to_numeric(df_div[col], errors="coerce")
    df_div["NOM_DPTO"] = df_div["NOM_DPTO"].astype(str).str.strip()
    df_div["NOM_MUNIC"] = df_div["NOM_MUNIC"].astype(str).str.strip()
    return df_div[["COD_DPTO", "NOM_DPTO", "COD_MUNIC", "NOM_MUNIC"]].drop_duplicates()


def cargar_geojson():
    if not os.path.exists(RUTA_GEOJSON):
        return None
    with open(RUTA_GEOJSON, "r", encoding="utf-8") as f:
        return json.load(f)


def validar_municipios(df):
    base_mun = df[["COD_DPTO", "COD_MUNIC", "NOM_DPTO", "NOM_MUNIC"]].drop_duplicates()
    sin_municipio = int(base_mun["NOM_MUNIC"].isna().sum())
    inconsistencias = base_mun[base_mun["NOM_MUNIC"].fillna("Sin información") == "Sin información"].copy()
    return {
        "municipios_unicos": int(base_mun[["COD_DPTO", "COD_MUNIC"]].drop_duplicates().shape[0]),
        "municipios_sin_match": sin_municipio,
        "muestra_inconsistencias": inconsistencias.head(20).to_dict("records"),
    }


def preparar_datos():
    df = cargar_anexo1()
    df_cod = cargar_anexo2()
    df_div = cargar_divipola()

    dep = df_div[["COD_DPTO", "NOM_DPTO"]].drop_duplicates(subset=["COD_DPTO"])
    mun = df_div[["COD_DPTO", "COD_MUNIC", "NOM_MUNIC"]].drop_duplicates(subset=["COD_DPTO", "COD_MUNIC"])

    filas_base = len(df)

    df = df.merge(dep, on="COD_DPTO", how="left", validate="many_to_one")
    df = df.merge(mun, on=["COD_DPTO", "COD_MUNIC"], how="left", validate="many_to_one")
    df = df.merge(df_cod, on="CAUSA", how="left", validate="many_to_one")

    if len(df) != filas_base:
        raise ValueError(
            f"Se detectó cambio inesperado en el número de filas tras los merge. "
            f"Filas iniciales: {filas_base}, filas finales: {len(df)}"
        )

    df["SEXO_LABEL"] = df["SEXO"].map({1: "Masculino", 2: "Femenino", 3: "Indeterminado"}).fillna("Sin información")
    df["CATEGORIA_EDAD"] = df["GRUPO_EDAD1"].apply(asignar_categoria_edad)
    df["MES_DEF"] = pd.to_numeric(df["MES_DEF"], errors="coerce")
    df = df[df["MES_DEF"].between(1, 12, inclusive="both") | df["MES_DEF"].isna()].copy()
    df["NOM_DPTO"] = df["NOM_DPTO"].fillna("Sin información")
    df["NOM_MUNIC"] = df["NOM_MUNIC"].fillna("Sin información")
    df["NOM_DPTO_NORM"] = df["NOM_DPTO"].apply(normalizar_texto)
    mapa_causas_manual = {"C61": "Tumor maligno de la próstata", "I10": "Hipertensión esencial primaria"}
    df["NOMBRE_CAUSA"] = df["NOMBRE_CAUSA"].fillna(df["CAUSA"].map(mapa_causas_manual)).fillna("Sin descripción")
    return df


print("Cargando y preparando datos desde carpeta data")
df = preparar_datos()
validacion_municipios = validar_municipios(df)
colombia_geo = cargar_geojson()

if colombia_geo is not None and "features" in colombia_geo:
    for feat in colombia_geo["features"]:
        props = feat.get("properties", {})
        nombre = props.get("NOMBRE_DPT") or props.get("DPTO_CNMBR") or props.get("departamento")
        props["DEPTO_NORM"] = normalizar_texto(nombre)


def agregar_mes(data):
    mm = data.groupby("MES_DEF").size().reset_index(name="TOTAL")
    mm = mm.sort_values("MES_DEF")
    mm["MES_NOMBRE"] = mm["MES_DEF"].map(MESES_NOMBRES)
    return mm


def agregar_edad(data):
    he = data.groupby("CATEGORIA_EDAD").size().reset_index(name="TOTAL")
    he["ORDEN"] = he["CATEGORIA_EDAD"].apply(lambda x: ORDEN_EDAD.index(x) if x in ORDEN_EDAD else 999)
    return he.sort_values("ORDEN")


def agregar_sexo(data):
    sd = data.groupby(["NOM_DPTO", "SEXO_LABEL"]).size().reset_index(name="TOTAL")
    tot = sd.groupby("NOM_DPTO", as_index=False)["TOTAL"].sum().sort_values("TOTAL", ascending=False)
    orden = tot["NOM_DPTO"].tolist()
    sd["NOM_DPTO"] = pd.Categorical(sd["NOM_DPTO"], categories=orden, ordered=True)
    return sd.sort_values(["NOM_DPTO", "SEXO_LABEL"])


def fig_vacia(titulo, mensaje):
    fig = px.scatter(x=[0], y=[0], title=titulo)
    fig.update_traces(marker_opacity=0)
    fig.update_layout(
        **LAYOUT_BASE,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(text=mensaje, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=14, color=COLORES["texto_suave"]))],
    )
    return fig


def fig_mapa(data):
    if colombia_geo is None:
        return fig_vacia("Distribución de muertes por departamento — Colombia 2019", "No se encontró el archivo assets/colombia.geo.json")
    mapa = data.groupby(["NOM_DPTO", "NOM_DPTO_NORM"]).size().reset_index(name="TOTAL")
    if mapa.empty:
        return fig_vacia("Distribución de muertes por departamento — Colombia 2019", "No hay datos para el filtro seleccionado")
    fig = px.choropleth(
        data_frame=mapa,
        geojson=colombia_geo,
        locations="NOM_DPTO_NORM",
        featureidkey="properties.DEPTO_NORM",
        color="TOTAL",
        color_continuous_scale="Teal",
        labels={"TOTAL": "Total muertes"},
        title=None,
        hover_name="NOM_DPTO",
    )
    fig.update_geos(visible=False)
    if len(mapa) > 1:
        fig.update_geos(fitbounds="locations")
    else:
        fig.update_geos(fitbounds=False, center={"lat": 4.5, "lon": -74.1}, projection_scale=12)
        nombre_unico = mapa["NOM_DPTO"].iloc[0]
        if nombre_unico == "ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA CATALINA":
            fig.update_geos(center={"lat": 12.55, "lon": -81.72}, projection_scale=28)
        elif nombre_unico == "BOGOTÁ, D.C.":
            fig.update_geos(center={"lat": 4.711, "lon": -74.0721}, projection_scale=45)
    layout_mapa = {**LAYOUT_BASE, "margin": dict(t=55, b=10, l=10, r=10)}
    fig.update_layout(**layout_mapa)
    return fig


def fig_lineas(data):
    mm = agregar_mes(data)
    if mm.empty:
        return fig_vacia("Total de muertes por mes — Colombia 2019", "No hay datos para el filtro seleccionado")
    fig = px.line(
        mm,
        x="MES_NOMBRE",
        y="TOTAL",
        markers=True,
        category_orders={"MES_NOMBRE": [MESES_NOMBRES[i] for i in range(1, 13)]},
        labels={"MES_NOMBRE": "Mes", "TOTAL": "Total muertes"},
        title=None,
        color_discrete_sequence=[COLORES["primario"]],
    )
    fig.update_traces(line_width=2.5, marker_size=8)
    fig.update_layout(**LAYOUT_BASE)
    return fig


def fig_barras_violentas(data):
    hom = data[data["CAUSA"].fillna("").str.startswith("X95")]
    cv = hom.groupby("NOM_MUNIC").size().reset_index(name="HOMICIDIOS").nlargest(5, "HOMICIDIOS")
    if cv.empty:
        return fig_vacia("5 municipios con más homicidios por arma de fuego — 2019", "No hay registros X95 para el filtro seleccionado")
    fig = px.bar(
        cv.sort_values("HOMICIDIOS", ascending=True),
        x="HOMICIDIOS",
        y="NOM_MUNIC",
        orientation="h",
        labels={"NOM_MUNIC": "Municipio", "HOMICIDIOS": "Homicidios X95"},
        title=None,
        color="HOMICIDIOS",
        color_continuous_scale=[[0, "#fde68a"], [1, COLORES["peligro"]]],
        text="HOMICIDIOS",
    )
    fig.update_layout(**LAYOUT_BASE)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig


def fig_circular(data):
    menor = data.groupby("NOM_MUNIC").size().reset_index(name="TOTAL").nsmallest(10, "TOTAL")
    if menor.empty:
        return fig_vacia("10 municipios con menor número de muertes registradas — 2019", "No hay datos para el filtro seleccionado")
    menor["NOM_MUNIC_LIMPIO"] = (
        menor["NOM_MUNIC"]
        .astype(str)
        .str.replace(r"\s*\[[^\]]+\]", "", regex=True)
        .str.strip()
    )
    fig = px.pie(
        menor,
        names="NOM_MUNIC_LIMPIO",
        values="TOTAL",
        title=None,
        color_discrete_sequence=PALETA_DISC,
        hole=0.35,
    )
    fig.update_traces(
        labels=menor["NOM_MUNIC_LIMPIO"],
        text=menor["NOM_MUNIC_LIMPIO"],
        texttemplate="%{label}<br>%{percent}<br>%{value}",
        textposition="inside",
        textfont_size=11,
        hovertemplate="<b>%{label}</b><br>Muertes: %{value}<br>Participación: %{percent}<extra></extra>",
        sort=False
    )
    layout_pie = {**LAYOUT_BASE, "showlegend": True, "legend": dict(font=dict(size=9), itemsizing="constant", title_text="Municipio")}
    fig.update_layout(**layout_pie)
    return fig

def fig_histograma(data):
    he = agregar_edad(data)
    if he.empty:
        return fig_vacia("Distribución de muertes por grupo de edad — Colombia 2019", "No hay datos para el filtro seleccionado")
    ymax = max(he["TOTAL"].max() * 1.14, he["TOTAL"].max() + 5000)
    fig = px.bar(
        he,
        x="CATEGORIA_EDAD",
        y="TOTAL",
        labels={"CATEGORIA_EDAD": "Grupo de edad", "TOTAL": "Total muertes"},
        title=None,
        color="TOTAL",
        color_continuous_scale="Teal",
        text="TOTAL",
    )
    layout_hist = {**LAYOUT_BASE, "margin": dict(t=95, b=70, l=45, r=20), "yaxis": dict(range=[0, ymax], automargin=True)}
    fig.update_layout(**layout_hist, xaxis_tickangle=-35)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig

def fig_barras_sexo(data):
    sd = agregar_sexo(data)
    if sd.empty:
        return fig_vacia("Total de muertes por sexo en cada departamento — Colombia 2019", "No hay datos para el filtro seleccionado")
    fig = px.bar(
        sd,
        y="NOM_DPTO",
        x="TOTAL",
        color="SEXO_LABEL",
        orientation="h",
        barmode="stack",
        labels={"NOM_DPTO": "Departamento", "TOTAL": "Total muertes", "SEXO_LABEL": "Sexo"},
        title=None,
        color_discrete_map={"Masculino": COLORES["primario"], "Femenino": COLORES["acento"], "Indeterminado": COLORES["peligro"], "Sin información": COLORES["texto_suave"]},
    )
    fig.update_layout(**LAYOUT_BASE, height=760, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig




def tabla_top_departamentos(data):
    top = data.groupby("NOM_DPTO").size().reset_index(name="TOTAL").sort_values("TOTAL", ascending=False).head(5)
    return top.to_dict("records")

def tabla_top10(data):
    top10 = (
        data.groupby(["CAUSA", "NOMBRE_CAUSA"]).size().reset_index(name="TOTAL")
        .sort_values(["TOTAL", "CAUSA"], ascending=[False, True])
        .head(10)
    )
    return top10[["CAUSA", "NOMBRE_CAUSA", "TOTAL"]].to_dict("records")


def calcular_kpis(data):
    return {
        "muertes": len(data),
        "departamentos": data["NOM_DPTO"].nunique(dropna=True),
        "municipios": data[["COD_DPTO", "COD_MUNIC"]].drop_duplicates().shape[0],
        "causas": data["CAUSA"].nunique(dropna=True),
    }


def tarjeta_kpi(titulo, valor, color, icono):
    return html.Div(
        [
            html.Div(html.I(className=f"fa {icono}", style={"fontSize": "1.25rem", "color": "white"}), className="mb-2"),
            html.P(titulo, className="small mb-1", style={"color": "rgba(255,255,255,0.85)"}),
            html.H4(valor, className="fw-bold mb-0", style={"color": "white"}),
        ],
        style={
            **KPI_STYLE,
            "background": color,
            "border": "none",
        },
    )


kpi_base = calcular_kpis(df)

NAVBAR = dbc.Navbar(
    dbc.Container(
        [
            html.A(
                dbc.Row(
                    [
                        dbc.Col(html.I(className="fa fa-heartbeat me-2", style={"color": COLORES["acento"], "fontSize": "1.4rem"})),
                        dbc.Col(dbc.NavbarBrand("Mortalidad Colombia 2019", className="fw-bold fs-5")),
                    ],
                    align="center",
                ),
                href="#",
                style={"textDecoration": "none"},
            ),
            html.Div([html.Span("Datos DANE Estadísticas Vitales - Desarrollo Mónica Contreras", className="text-white-50 small")]),
        ],
        fluid=True,
    ),
    color=COLORES["primario"],
    dark=True,
    className="mb-0 py-2",
)

texto_validacion = f"Municipios únicos validados contra Divipola: {validacion_municipios['municipios_unicos']} | Sin match: {validacion_municipios['municipios_sin_match']}"

app.layout = dbc.Container(
    [
        NAVBAR,
        html.Br(),
        dbc.Row(
            [
                dbc.Col(tarjeta_kpi("Total de muertes", f"{kpi_base['muertes']:,}", COLORES["primario"], "fa-heartbeat"), md=3),
                dbc.Col(tarjeta_kpi("Departamentos", str(kpi_base["departamentos"]), COLORES["acento"], "fa-map"), md=3),
                dbc.Col(tarjeta_kpi("Municipios válidos", str(kpi_base["municipios"]), COLORES["secundario"], "fa-map-marker-alt"), md=3),
                dbc.Col(tarjeta_kpi("Causas registradas", str(kpi_base["causas"]), COLORES["peligro"], "fa-notes-medical"), md=3),
            ],
            className="g-3 mb-4",
            id="bloque-kpis",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Filtrar por departamento", className="fw-semibold small"),
                        dcc.Dropdown(
                            id="filtro-depto",
                            options=[{"label": "Todos", "value": "TODOS"}] + [{"label": d, "value": d} for d in sorted(df["NOM_DPTO"].dropna().unique())],
                            value="TODOS",
                            clearable=False,
                            style={"borderRadius": "8px", "fontSize": "0.9rem"},
                        ),
                        html.Small("El filtro actualiza todas las visualizaciones y la tabla.", className="text-muted d-block mt-2"),
                    ],
                    md=4,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(html.Div(dcc.Graph(id="graf-mapa", figure=fig_mapa(df), config={"displayModeBar": False}), style=CARD), md=8),
                dbc.Col(
                    html.Div(
                        [
                            html.H6([html.I(className="fa fa-list-ol me-2"), "5 departamentos con más muertes"], className="fw-bold mb-3", style={"color": COLORES["texto"]}),
                            dash_table.DataTable(
                                id="tabla-top-deptos",
                                columns=[
                                    {"name": "Departamento", "id": "NOM_DPTO"},
                                    {"name": "Total", "id": "TOTAL"},
                                ],
                                data=tabla_top_departamentos(df),
                                style_table={"overflowX": "auto"},
                                style_header={"backgroundColor": COLORES["primario"], "color": "white", "fontWeight": "bold", "textAlign": "left", "fontSize": "0.9rem", "padding": "10px"},
                                style_cell={"textAlign": "left", "padding": "9px 12px", "fontSize": "0.9rem", "fontFamily": "Inter, Arial, sans-serif", "backgroundColor": COLORES["superficie"], "color": COLORES["texto"], "border": f"1px solid {COLORES['borde']}"},
                            ),
                        ],
                        style=CARD,
                    ),
                    md=4,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(html.Div([
            html.H6([html.I(className="fa fa-chart-line me-2"), "Total de muertes por mes"], className="fw-bold mb-3", style={"color": COLORES["texto"]}),
            dcc.Graph(id="graf-lineas", figure=fig_lineas(df), config={"displayModeBar": False})
        ], style=CARD), md=6),
                dbc.Col(html.Div([
            html.H6([html.I(className="fa fa-crosshairs me-2"), "5 municipios con más homicidios por arma de fuego"], className="fw-bold mb-3", style={"color": COLORES["texto"]}),
            dcc.Graph(id="graf-violentas", figure=fig_barras_violentas(df), config={"displayModeBar": False})
        ], style=CARD), md=6),
            ],
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(html.Div([
            html.H6([html.I(className="fa fa-chart-pie me-2"), "10 municipios con menor número de muertes registradas"], className="fw-bold mb-3", style={"color": COLORES["texto"]}),
            dcc.Graph(id="graf-circular", figure=fig_circular(df), config={"displayModeBar": False})
        ], style=CARD), md=5),
                dbc.Col(html.Div([
            html.H6([html.I(className="fa fa-users me-2"), "Distribución de muertes por grupo de edad"], className="fw-bold mb-3", style={"color": COLORES["texto"]}),
            dcc.Graph(id="graf-histograma", figure=fig_histograma(df), config={"displayModeBar": False})
        ], style=CARD), md=7),
            ],
            className="mb-4",
        ),
        dbc.Row(dbc.Col(html.Div([
            html.H6([html.I(className="fa fa-venus-mars me-2"), "Total de muertes por sexo en cada departamento"], className="fw-bold mb-3", style={"color": COLORES["texto"]}),
            dcc.Graph(id="graf-sexo", figure=fig_barras_sexo(df), config={"displayModeBar": False})
        ], style=CARD), width=12), className="mb-4"),
        dbc.Row(
            dbc.Col(
                html.Div(
                    [
                        html.H6("10 principales causas de muerte en Colombia 2019", className="fw-bold mb-3", style={"color": COLORES["texto"], "fontSize": "1rem"}),
                        dash_table.DataTable(
                            id="tabla-causas",
                            columns=[
                                {"name": "Código", "id": "CAUSA"},
                                {"name": "Causa de muerte", "id": "NOMBRE_CAUSA"},
                                {"name": "Total de casos", "id": "TOTAL"},
                            ],
                            data=tabla_top10(df),
                            style_table={"overflowX": "auto", "borderRadius": "8px"},
                            style_header={"backgroundColor": COLORES["primario"], "color": "white", "fontWeight": "bold", "textAlign": "left", "fontSize": "0.9rem", "padding": "10px"},
                            style_cell={"textAlign": "left", "padding": "9px 14px", "fontSize": "0.9rem", "fontFamily": "Inter, Arial, sans-serif", "backgroundColor": COLORES["superficie"], "color": COLORES["texto"], "border": f"1px solid {COLORES['borde']}"},
                            style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": COLORES["fondo"]}],
                            sort_action="native",
                            page_size=10,
                        ),
                    ],
                    style=CARD,
                ),
                width=12,
            ),
            className="mb-5",
        ),
        dbc.Accordion(
            [
                dbc.AccordionItem(
                    [
                        html.P(texto_validacion, className="mb-2"),
                        html.Small("Control interno de integridad territorial entre Anexo 1 y Divipola.", className="text-muted"),
                    ],
                    title="Validación de integridad territorial",
                )
            ],
            start_collapsed=True,
            className="mb-4",
        ),
        html.Footer(
            dbc.Container(
                html.P(
                    [
                        "Fuente de datos: ",
                        html.A("DANE Estadísticas Vitales 2019", href="https://microdatos.dane.gov.co/index.php/catalog/696", target="_blank", rel="noopener noreferrer", style={"color": COLORES["secundario"]}),
                        " · Desarrollado por Mónica Contreras, con Python Dash y Plotly",
                    ],
                    className="text-center text-muted small py-3 mb-0",
                )
            ),
            style={"borderTop": f"1px solid {COLORES['borde']}", "background": COLORES["fondo"]},
        ),
    ],
    fluid=True,
    style={"background": COLORES["fondo"], "minHeight": "100vh", "fontFamily": "Inter, Arial, sans-serif"},
)


@app.callback(
    Output("graf-mapa", "figure"),
    Output("graf-lineas", "figure"),
    Output("graf-violentas", "figure"),
    Output("graf-circular", "figure"),
    Output("graf-histograma", "figure"),
    Output("graf-sexo", "figure"),
    Output("tabla-causas", "data"),
    Output("tabla-top-deptos", "data"),
    Input("filtro-depto", "value"),
)
def actualizar_visualizaciones(depto):
    dff = df if depto == "TODOS" else df[df["NOM_DPTO"] == depto].copy()
    return fig_mapa(dff), fig_lineas(dff), fig_barras_violentas(dff), fig_circular(dff), fig_histograma(dff), fig_barras_sexo(dff), tabla_top10(dff), tabla_top_departamentos(dff)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
