"""Fondos de las escenas del reel (1080x920 px) a partir de los datos procesados.

Uso (desde la raíz): python reel/visuales.py
"""
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

matplotlib.use("Agg")
RAIZ = Path(__file__).resolve().parents[1]
OUT = RAIZ / "reel" / "visuales"
OUT.mkdir(exist_ok=True)
FONDO, TINTA, TINTA2, ACC, ACC2 = "#14110f", "#f3ede7", "#a89f97", "#2ec4b6", "#f26b1d"
plt.rcParams.update({"figure.facecolor": FONDO, "axes.facecolor": FONDO, "text.color": TINTA,
                     "axes.labelcolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                     "axes.edgecolor": "#3a332e", "font.size": 22, "font.family": "Arial"})

d = pd.read_csv(RAIZ / "datos/procesados/ipress_limpio.csv")
dep = pd.read_csv(RAIZ / "datos/procesados/departamentos.csv")
geo = gpd.read_file(RAIZ / "datos/originales/peru_departamental.geojson").merge(
    dep, left_on="NOMBDEP", right_on="departamento")


def guardar(fig, nombre):
    fig.savefig(OUT / f"{nombre}.png", dpi=100, facecolor=FONDO)
    plt.close(fig)
    im = Image.open(OUT / f"{nombre}.png").convert("RGB").resize((1080, 920))
    im.save(OUT / f"{nombre}.png")


# 1. todos los puntos georreferenciados, coloreados por nivel
fig, ax = plt.subplots(figsize=(10.8, 9.2))
geo.plot(ax=ax, color="#2a2420", edgecolor="#4a413a", linewidth=.8)
col = {"Sin categoría": "#6b625b", "I nivel": ACC, "II nivel": "#e9c46a", "III nivel": ACC2}
for nv, tam in [("Sin categoría", 4), ("I nivel", 4), ("II nivel", 25), ("III nivel", 90)]:
    p = d[(d["nivel"] == nv) & d["lat"].notna()]
    ax.scatter(p["lon"], p["lat"], s=tam, c=col[nv], alpha=.8, label=nv, linewidths=0)
ax.legend(loc="lower left", frameon=False, markerscale=2, fontsize=20)
ax.set_axis_off()
ax.set_title("Establecimientos con coordenadas, por nivel", fontsize=24, color=TINTA2)
guardar(fig, "mapa_puntos")

# 2. concentración: % población vs % establecimientos vs % III nivel en Lima+Callao
fig, ax = plt.subplots(figsize=(10.8, 9.2))
cats = ["Población", "Todos los\nestablecimientos", "Hospitales\nII y III nivel", "Hospitales\nIII nivel"]
lc = d["departamento"].isin(["LIMA", "CALLAO"])
vals = [35.7, lc.mean() * 100, lc[d["nivel"].isin(["II nivel", "III nivel"])].mean() * 100,
        lc[d["nivel"] == "III nivel"].mean() * 100]
b = ax.bar(cats, vals, color=[TINTA2, ACC, "#e9c46a", ACC2], width=.65)
for r, v in zip(b, vals):
    ax.text(r.get_x() + r.get_width() / 2, v + 1.5, f"{v:.0f} %", ha="center", fontsize=34, weight="bold")
ax.set_ylim(0, 75)
ax.set_yticks([])
ax.spines[["top", "right", "left"]].set_visible(False)
ax.set_title("Participación de Lima y Callao en el total del Perú", fontsize=24, color=TINTA2)
plt.xticks(fontsize=20)
fig.tight_layout()
guardar(fig, "concentracion")

# 3. mapa: departamentos con y sin III nivel
fig, ax = plt.subplots(figsize=(10.8, 9.2))
geo["tiene"] = geo["nivel_III"] > 0
geo[~geo["tiene"]].plot(ax=ax, color="#5a3a2a", edgecolor=FONDO, linewidth=1.2)
geo[geo["tiene"]].plot(ax=ax, color=ACC, edgecolor=FONDO, linewidth=1.2)
iii = d[(d["nivel"] == "III nivel") & d["lat"].notna()]
ax.scatter(iii["lon"], iii["lat"], s=120, c=ACC2, edgecolor="white", linewidth=1.2, zorder=3)
ax.set_axis_off()
ax.text(.02, .1, "■ con III nivel (9)", color=ACC, transform=ax.transAxes, fontsize=24)
ax.text(.02, .04, "■ sin III nivel (16)", color="#c07a55", transform=ax.transAxes, fontsize=24)
ax.set_title("¿Qué departamentos tienen hospitales de III nivel?", fontsize=24, color=TINTA2)
guardar(fig, "mapa_iii")

# 4. densidad vs capacidad
fig, ax = plt.subplots(figsize=(10.8, 9.2))
ax.scatter(dep["eess_10k"], dep["hosp_100k"], s=dep["poblacion_2017"] / 9000 + 60, c=ACC, alpha=.75, edgecolor="white")
for r in dep.itertuples():
    if r.departamento in ("AMAZONAS", "HUANCAVELICA", "LIMA", "TACNA", "HUANUCO", "MOQUEGUA", "LA LIBERTAD", "UCAYALI"):
        ax.annotate(r.departamento.title(), (r.eess_10k, r.hosp_100k), xytext=(8, 8), textcoords="offset points",
                    fontsize=20, color=ACC2 if r.departamento == "AMAZONAS" else TINTA)
ax.axvline(7.07, color=ACC2, ls=":", lw=2)
ax.text(7.2, 3.5, "promedio Perú", color=ACC2, fontsize=18)
ax.set_xlabel("Establecimientos por 10 000 hab.")
ax.set_ylabel("Hospitales II–III por 100 000 hab.")
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("Más locales no es más capacidad", fontsize=24, color=TINTA2)
fig.tight_layout()
guardar(fig, "densidad")

# 5. altas por año y sector
fig, ax = plt.subplots(figsize=(10.8, 9.2))
a = d[d["anio_inicio"].between(1990, 2017)]
pri = a[a["sector"] == "Privado"].groupby("anio_inicio").size()
pub = a[a["sector"] != "Privado"].groupby("anio_inicio").size()
ax.plot(pri.index, pri.values, color="#9b87ff", lw=5, label="Privados")
ax.plot(pub.index, pub.values, color=ACC, lw=5, label="Públicos")
ax.axvspan(2008, 2017, color="#ffffff", alpha=.06)
ax.legend(frameon=False, fontsize=24, loc="upper left")
ax.set_ylabel("Establecimientos que iniciaron")
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("Nuevos establecimientos por año de inicio", fontsize=24, color=TINTA2)
fig.tight_layout()
guardar(fig, "altas")

# 6. captura del dashboard (tomada con Edge headless: reel/recursos/dash_top.png)
cap = Image.open(RAIZ / "reel/recursos/dash_top.png").convert("RGB")
cap = cap.crop((60, 460, 1340, 1150))   # KPIs + mapas
cap.thumbnail((1080, 920))
lienzo = Image.new("RGB", (1080, 920), FONDO)
lienzo.paste(cap, ((1080 - cap.width) // 2, (920 - cap.height) // 2))
lienzo.save(OUT / "dashboard.png")
print("visuales listos en", OUT)
