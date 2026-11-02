"""Limpieza, indicadores y exportación para el dashboard.

Entrada  (datos/originales/):
  IPRESS.csv                 MINSA - Registro de IPRESS (datosabiertos.gob.pe, corte sept. 2017)
  poblacion_inei_2017.csv    INEI - Censos Nacionales 2017, población censada por departamento
  peru_departamental.geojson Límites departamentales (juaneladio/peru-geojson, base INEI)
Salida (datos/procesados/ y web/data/):
  ipress_limpio.csv, departamentos.csv, web/data/ipress.json, web/data/resumen.json, web/data/peru.geojson

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

# ---------- 3. hallazgos (cifras que usan el dashboard, README y reel) ----------
pais_pob = int(pob["poblacion_2017"].sum())
lima = dep.set_index("departamento").loc[["LIMA", "CALLAO"]].sum()
tot = len(d)
hosp = d[d["nivel"].isin(["II nivel", "III nivel"])]
iii = d[d["nivel"] == "III nivel"]
cat_publico = d[d["sector"] != "Privado"]
resumen = {
    "corte": "septiembre 2017",
    "n_bruto": n_bruto, "n_duplicados": n_dup, "n_no_funcionan": n_inop, "n_final": tot,
    "n_con_coord": int(d["con_coord"].sum()),
    "poblacion_2017": pais_pob,
    "eess_10k_pais": round(tot / pais_pob * 1e4, 2),
    "pct_privado_pais": round((d["sector"] == "Privado").mean() * 100, 1),
    "lima_callao_pct_eess": round(lima["eess"] / tot * 100, 1),
    "lima_callao_pct_pob": round(lima["poblacion_2017"] / pais_pob * 100, 1),
    "lima_callao_pct_privados": round(lima["privados"] / (d["sector"] == "Privado").sum() * 100, 1),
    "lima_callao_pct_III": round(iii["departamento"].isin(["LIMA", "CALLAO"]).mean() * 100, 1),
    "n_III": len(iii), "n_II_III": len(hosp),
    "pct_publicos_I1": round((cat_publico["categoria"] == "I-1").mean() * 100, 1),
    "pct_publicos_I": round((cat_publico["nivel"] == "I nivel").mean() * 100, 1),
    "deps_sin_III": sorted(set(dep["departamento"]) - set(iii["departamento"])),
    "top_eess_10k": dep.nlargest(3, "eess_10k")[["departamento", "eess_10k", "pct_I1_publicos"]].to_dict("records"),
    "bottom_eess_10k": dep.nsmallest(3, "eess_10k")[["departamento", "eess_10k"]].to_dict("records"),
    "top_hosp_100k": dep.nlargest(3, "hosp_100k")[["departamento", "hosp_100k"]].to_dict("records"),
    "bottom_hosp_100k": dep.nsmallest(3, "hosp_100k")[["departamento", "hosp_100k"]].to_dict("records"),
    "altas_por_periodo": d.assign(p=pd.cut(d["anio_inicio"], [1899, 2007, 2012, 2017],
                                           labels=["hasta 2007", "2008-2012", "2013-2017"]))
                          .groupby(["p", "sector"], observed=True).size().unstack(fill_value=0).to_dict("index"),
}
pp = d[d["anio_inicio"].between(2008, 2017)]
resumen["pct_privado_altas_2008_2017"] = round((pp["sector"] == "Privado").mean() * 100, 1)
resumen["corr_eess10k_hosp100k"] = round(dep["eess_10k"].corr(dep["hosp_100k"]), 2)
(WEB / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))

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
print("ok:", tot, "establecimientos")
