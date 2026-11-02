"""Paso 1: descarga las fuentes originales en datos/originales/.

- MINSA - IPRESS (Plataforma Nacional de Datos Abiertos). El portal rechaza clientes sin
  User-Agent de navegador (HTTP 418), por eso se envía uno.
- Límites departamentales (GeoJSON, base INEI) del repositorio juaneladio/peru-geojson.
- La población censada 2017 por departamento (INEI, Censos Nacionales 2017, cuadro de población
  censada por departamento) se transcribió en datos/originales/poblacion_inei_2017.csv; total 29 381 884.

Uso:  python scripts/obtener_datos.py
"""
from datetime import date
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
ORIG = RAIZ / "datos/originales"
ORIG.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"}
FUENTES = {
    "IPRESS.csv": "https://www.datosabiertos.gob.pe/sites/default/files/recursos/2017/09/IPRESS.csv",
    "peru_departamental.geojson": "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_departamental_simple.geojson",
}
for nombre, url in FUENTES.items():
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    (ORIG / nombre).write_bytes(r.content)
    print(f"{nombre}: {len(r.content) / 1e6:.1f} MB  <- {url}")
print(f"Descarga: {date.today()}")
