"""Paso 2: limpieza, variables derivadas, indicadores por departamento y datos para la web.

Entrada  (datos/originales/):
  IPRESS.csv                 MINSA - Registro de IPRESS (datosabiertos.gob.pe, corte sept. 2017)
  poblacion_inei_2017.csv    INEI - Censos Nacionales 2017, población censada por departamento
  peru_departamental.geojson Límites departamentales (juaneladio/peru-geojson, base INEI)
Salida (datos/procesados/ y web/data/):
  ipress_limpio.csv, departamentos.csv, limpieza.json, web/data/ipress.json, web/data/peru.geojson
Luego: python scripts/analizar_datos.py (hallazgos -> web/data/resumen.json)

Uso:  python scripts/procesar_datos.py
"""
import json
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ORIG, PROC, WEB = RAIZ / "datos/originales", RAIZ / "datos/procesados", RAIZ / "web/data"
PROC.mkdir(parents=True, exist_ok=True)
WEB.mkdir(parents=True, exist_ok=True)


def sin_tildes(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


# ---------- 1. lectura y limpieza ----------
d = pd.read_csv(ORIG / "IPRESS.csv", encoding="latin1", dtype=str)
d.columns = [sin_tildes(c).lower().replace(" ", "_").replace(".", "") for c in d.columns]
n_bruto = len(d)
for c in d.columns:
    d[c] = d[c].str.strip()

d = d.drop_duplicates()                                   # filas idénticas
dup = d["codigo_unico"].duplicated(keep="first")
n_dup = int(dup.sum())
d = d[~dup]                                               # un registro por código único
n_inop = int((d["condicion"] != "EN FUNCIONAMIENTO").sum())
d = d[d["condicion"] == "EN FUNCIONAMIENTO"]               # solo establecimientos en funcionamiento

d["departamento"] = d["departamento"].map(sin_tildes)
d["categoria"] = d["categoria"].fillna("SIN CATEGORIA").map(sin_tildes)
d["clasificacion"] = d["clasificacion"].fillna("SIN CLASIFICACION")
for c in ["provincia", "distrito", "nombre_del_establecimiento", "institucion"]:
    d[c] = d[c].fillna("")


def nivel(cat):
    if cat.startswith("III"):
        return "III nivel"
    if cat.startswith("II"):
        return "II nivel"
    if cat.startswith("I-"):
        return "I nivel"
    return "Sin categoría"


d["nivel"] = d["categoria"].map(nivel)
publicos = {"GOBIERNO REGIONAL", "MINSA", "ESSALUD", "MUNICIPALIDAD PROVINCIAL", "MUNICIPALIDAD DISTRITAL", "INPE"}


def sector(inst):
    if inst == "PRIVADO":
        return "Privado"
    if inst in ("GOBIERNO REGIONAL", "MINSA"):
        return "MINSA / Gob. regional"
    if inst == "ESSALUD":
        return "EsSalud"
    if inst.startswith("SANIDAD"):
        return "FF.AA. y Policía"
    return "Otros públicos" if inst in publicos else "Otros"


d["sector"] = d["institucion"].map(sector)
d["internamiento"] = d["tipo"].str.contains("CON INTERNAMIENTO", na=False)
d["anio_inicio"] = pd.to_numeric(d["inicio_de_actividad"].str[-4:], errors="coerce")
d.loc[(d["anio_inicio"] < 1900) | (d["anio_inicio"] > 2017), "anio_inicio"] = pd.NA
d["camas"] = pd.to_numeric(d["camas"], errors="coerce")

# Las columnas NORTE/ESTE vienen rotuladas al revés: NORTE es la longitud y ESTE la latitud.
d["lon"] = pd.to_numeric(d["norte"], errors="coerce")
d["lat"] = pd.to_numeric(d["este"], errors="coerce")
fuera = ~(d["lon"].between(-81.5, -68.5) & d["lat"].between(-18.5, 0.1))
d.loc[fuera, ["lon", "lat"]] = pd.NA
d["con_coord"] = d["lat"].notna()

cols = ["codigo_unico", "nombre_del_establecimiento", "institucion", "sector", "clasificacion", "tipo",
        "categoria", "nivel", "internamiento", "departamento", "provincia", "distrito", "ubigeo",
        "anio_inicio", "camas", "lat", "lon"]
d[cols].to_csv(PROC / "ipress_limpio.csv", index=False, encoding="utf-8")

# ---------- 2. indicadores por departamento ----------
pob = pd.read_csv(ORIG / "poblacion_inei_2017.csv")
g = d.groupby("departamento")
dep = pd.DataFrame({
    "eess": g.size(),
    "publicos": g.apply(lambda x: (x["sector"] != "Privado").sum()),
    "privados": g.apply(lambda x: (x["sector"] == "Privado").sum()),
    "nivel_I": g.apply(lambda x: (x["nivel"] == "I nivel").sum()),
    "nivel_I1_publicos": g.apply(lambda x: ((x["categoria"] == "I-1") & (x["sector"] != "Privado")).sum()),
    "nivel_II_III": g.apply(lambda x: x["nivel"].isin(["II nivel", "III nivel"]).sum()),
    "nivel_III": g.apply(lambda x: (x["nivel"] == "III nivel").sum()),
    "internamiento": g["internamiento"].sum(),
}).reset_index().merge(pob, on="departamento", how="left")
dep["eess_10k"] = dep["eess"] / dep["poblacion_2017"] * 1e4
dep["publicos_10k"] = dep["publicos"] / dep["poblacion_2017"] * 1e4
dep["hosp_100k"] = dep["nivel_II_III"] / dep["poblacion_2017"] * 1e5
dep["internamiento_100k"] = dep["internamiento"] / dep["poblacion_2017"] * 1e5
dep["pct_privado"] = dep["privados"] / dep["eess"] * 100
dep["pct_I1_publicos"] = dep["nivel_I1_publicos"] / dep["publicos"].where(dep["publicos"] > 0) * 100
dep["hab_por_eess"] = dep["poblacion_2017"] / dep["eess"]
dep = dep.round(2).sort_values("eess", ascending=False)
dep.to_csv(PROC / "departamentos.csv", index=False, encoding="utf-8")

# ---------- 3. registro de la limpieza (lo usa analizar_datos.py) ----------
(PROC / "limpieza.json").write_text(json.dumps({"n_bruto": n_bruto, "n_duplicados": n_dup, "n_no_funcionan": n_inop,
                                                "n_final": len(d)}, indent=1), encoding="utf-8")
print(f"Limpieza: {n_bruto} filas -> {len(d)} establecimientos ({n_dup} duplicados, {n_inop} no funcionan)")

# ---------- 4. datos compactos para la web ----------
cods = {k: sorted(d[k].dropna().unique().tolist()) for k in ["sector", "nivel", "categoria", "departamento", "clasificacion"]}
idx = {k: {v: i for i, v in enumerate(vs)} for k, vs in cods.items()}
filas = []
for r in d.itertuples(index=False):
    filas.append([r.nombre_del_establecimiento.title(), idx["sector"][r.sector], idx["nivel"][r.nivel],
                  idx["categoria"][r.categoria], idx["departamento"][r.departamento],
                  idx["clasificacion"][r.clasificacion], r.provincia.title(), r.distrito.title(),
                  None if pd.isna(r.anio_inicio) else int(r.anio_inicio),
                  None if pd.isna(r.lat) else round(float(r.lat), 4),
                  None if pd.isna(r.lon) else round(float(r.lon), 4),
                  int(bool(r.internamiento)), r.institucion.title()])
(WEB / "ipress.json").write_text(json.dumps({"cods": cods, "campos": ["nombre", "sector", "nivel", "categoria",
    "departamento", "clasificacion", "provincia", "distrito", "anio", "lat", "lon", "internamiento", "institucion"],
    "filas": filas, "poblacion": dict(zip(pob["departamento"], pob["poblacion_2017"]))}, ensure_ascii=False,
    separators=(",", ":")), encoding="utf-8")
shutil.copy(ORIG / "peru_departamental.geojson", WEB / "peru.geojson")
print("ok:", len(d), "establecimientos")
