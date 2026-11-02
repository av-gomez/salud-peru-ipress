"""Paso 3: hallazgos e indicadores nacionales a partir de los datos procesados.

Lee datos/procesados/ (ipress_limpio.csv, departamentos.csv, limpieza.json) y la población del INEI.
Escribe web/data/resumen.json: todas las cifras citadas en el dashboard, el README y el guion del reel.

Uso:  python scripts/analizar_datos.py
"""
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ORIG, PROC, WEB = RAIZ / "datos/originales", RAIZ / "datos/procesados", RAIZ / "web/data"
d = pd.read_csv(PROC / "ipress_limpio.csv", dtype={"codigo_unico": str, "ubigeo": str})
dep = pd.read_csv(PROC / "departamentos.csv")
pob = pd.read_csv(ORIG / "poblacion_inei_2017.csv")
limpieza = json.loads((PROC / "limpieza.json").read_text(encoding="utf-8"))

pais_pob = int(pob["poblacion_2017"].sum())
lima = dep.set_index("departamento").loc[["LIMA", "CALLAO"]].sum()
tot = len(d)
hosp = d[d["nivel"].isin(["II nivel", "III nivel"])]
iii = d[d["nivel"] == "III nivel"]
cat_publico = d[d["sector"] != "Privado"]
resumen = {
    "corte": "septiembre 2017",
    **limpieza,
    "n_con_coord": int(d["lat"].notna().sum()),
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
print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))


# Hallazgo 3 (detalle): menor participación privada fuera de Lima
resumen["pct_privado_por_departamento"] = dep.set_index("departamento")["pct_privado"].sort_values().to_dict()
(WEB / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
