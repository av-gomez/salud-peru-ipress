"""Fondos animados de las escenas del reel (1080x920 px) a partir de los datos procesados.

Cada escena animada se guarda como una carpeta de cuadros (visuales/<clave>/000.png ...);
hacer_reel.py elige el cuadro según el tiempo transcurrido en la escena.
La escena final usa una captura vertical del dashboard en móvil que se desplaza.

Uso (desde la raíz del repositorio): python reel/visuales.py
"""
import shutil
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

matplotlib.use("Agg")
RAIZ = Path(__file__).resolve().parents[1]
OUT = RAIZ / "reel" / "visuales"
FONDO, TINTA, TINTA2, ACC, ACC2, AMA, VIO = "#14110f", "#f3ede7", "#a89f97", "#2ec4b6", "#f26b1d", "#e9c46a", "#9b87ff"
plt.rcParams.update({"figure.facecolor": FONDO, "axes.facecolor": FONDO, "text.color": TINTA,
                     "axes.labelcolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                     "axes.edgecolor": "#3a332e", "font.size": 26, "font.family": "Arial"})

d = pd.read_csv(RAIZ / "datos/procesados/ipress_limpio.csv")
dep = pd.read_csv(RAIZ / "datos/procesados/departamentos.csv")
geo = gpd.read_file(RAIZ / "datos/originales/peru_departamental.geojson").merge(
    dep, left_on="NOMBDEP", right_on="departamento")
facil = lambda x: 1 - (1 - x) ** 3   # ease-out


def lienzo():
    return plt.subplots(figsize=(10.8, 9.2), dpi=100)


def guardar(fig, ruta):
    fig.savefig(ruta, dpi=100, facecolor=FONDO)
    plt.close(fig)
    im = Image.open(ruta).convert("RGB")
    if im.size != (1080, 920):
        im.resize((1080, 920)).save(ruta)


def carpeta(nombre):
    c = OUT / nombre
    shutil.rmtree(c, ignore_errors=True)
    c.mkdir(parents=True)
    return c


def titulo(ax, texto):
    ax.set_title(texto, fontsize=30, color=TINTA, loc="left", pad=18, weight="bold")


# 1. mapa: aparecen los establecimientos georreferenciados según su año de inicio
c = carpeta("mapa_puntos")
pts = d[d["lat"].notna()].copy()
pts["anio"] = pts["anio_inicio"].fillna(1900)
col = {"Sin categoría": "#7d746c", "I nivel": ACC, "II nivel": AMA, "III nivel": ACC2}
tam = {"Sin categoría": 5, "I nivel": 5, "II nivel": 30, "III nivel": 110}
anios = np.linspace(1995, 2017, 24).round().astype(int)
for k, a in enumerate(anios):
    fig, ax = lienzo()
    fig.subplots_adjust(0, 0, 1, .9)
    geo.plot(ax=ax, color="#2a2420", edgecolor="#4a413a", linewidth=.8)
    v = pts[pts["anio"] <= a]
    for nv in ["Sin categoría", "I nivel", "II nivel", "III nivel"]:
        p = v[v["nivel"] == nv]
        ax.scatter(p["lon"], p["lat"], s=tam[nv], c=col[nv], alpha=.85, linewidths=0, label=nv)
    ax.set_axis_off()
    ax.text(.98, .9, f"{a}", transform=ax.transAxes, ha="right", fontsize=64, weight="bold", color=TINTA)
    ax.text(.98, .84, "año de inicio", transform=ax.transAxes, ha="right", fontsize=22, color=TINTA2)
    ax.legend(loc="lower left", frameon=False, markerscale=2.2, fontsize=22, labelcolor=TINTA)
    titulo(ax, "Establecimientos de salud del Perú")
    guardar(fig, c / f"{k:03d}.png")

# 2. concentración: las barras crecen
c = carpeta("concentracion")
lc = d["departamento"].isin(["LIMA", "CALLAO"])
cats = ["Población", "Todos los\nlocales", "Hospitales\nII y III", "Hospitales\nIII nivel"]
vals = [35.7, lc.mean() * 100, lc[d["nivel"].isin(["II nivel", "III nivel"])].mean() * 100,
        lc[d["nivel"] == "III nivel"].mean() * 100]
for k in range(20):
    fig, ax = lienzo()
    f = facil(min(1, (k + 1) / 16))
    b = ax.bar(cats, [v * f for v in vals], color=[TINTA2, ACC, AMA, ACC2], width=.66)
    for r, v in zip(b, vals):
        ax.text(r.get_x() + r.get_width() / 2, v * f + 1.5, f"{v * f:.0f} %", ha="center", fontsize=40, weight="bold")
    ax.set_ylim(0, 75)
    ax.set_yticks([])
    ax.spines[["top", "right", "left"]].set_visible(False)
    plt.xticks(fontsize=24)
    titulo(ax, "Peso de Lima y Callao en el Perú")
    fig.tight_layout()
    guardar(fig, c / f"{k:03d}.png")

# 3. mapa: departamentos con y sin III nivel (se colorean y aparecen los hospitales)
c = carpeta("mapa_iii")
geo["tiene"] = geo["nivel_III"] > 0
iii = d[(d["nivel"] == "III nivel") & d["lat"].notna()]
for k in range(18):
    fig, ax = lienzo()
    fig.subplots_adjust(0, 0, 1, .9)
    f = min(1, k / 10)
    geo.plot(ax=ax, color="#2a2420", edgecolor=FONDO, linewidth=1.2)
    geo[~geo["tiene"]].plot(ax=ax, color="#7a3b22", edgecolor=FONDO, linewidth=1.2, alpha=f)
    geo[geo["tiene"]].plot(ax=ax, color=ACC, edgecolor=FONDO, linewidth=1.2, alpha=f)
    if k >= 8:
        ax.scatter(iii["lon"], iii["lat"], s=160 * min(1, (k - 7) / 5), c=ACC2, edgecolor="white", linewidth=1.5, zorder=3)
    ax.set_axis_off()
    ax.set_xlim(-89, -68.3)
    ax.text(.02, .14, "■ con III nivel: 9", color=ACC, transform=ax.transAxes, fontsize=30, weight="bold")
    ax.text(.02, .06, "■ sin III nivel: 16", color="#e08a62", transform=ax.transAxes, fontsize=30, weight="bold")
    titulo(ax, "¿Dónde hay hospitales de III nivel?")
    guardar(fig, c / f"{k:03d}.png")

# 4. densidad vs capacidad: Amazonas resaltado
c = carpeta("densidad")
for k in range(16):
    fig, ax = lienzo()
    otros = dep[dep["departamento"] != "AMAZONAS"]
    ama = dep[dep["departamento"] == "AMAZONAS"]
    ax.scatter(otros["eess_10k"], otros["hosp_100k"], s=otros["poblacion_2017"] / 9000 + 80, c=ACC, alpha=.55, edgecolor="white")
    pulso = 1 + .6 * np.sin(k / 15 * np.pi)
    ax.scatter(ama["eess_10k"], ama["hosp_100k"], s=500 * pulso, c=ACC2, edgecolor="white", linewidth=2, zorder=3)
    ax.annotate("Amazonas\n13,9 por 10 000 hab.", (13.94, 2.37), xytext=(-260, 90), textcoords="offset points",
                fontsize=26, color=ACC2, weight="bold", arrowprops=dict(arrowstyle="-", color=ACC2, lw=2))
    for nombre in ("LIMA", "HUANUCO", "MOQUEGUA"):
        r = dep[dep["departamento"] == nombre].iloc[0]
        ax.annotate(nombre.title().replace("Huanuco", "Huánuco"), (r.eess_10k, r.hosp_100k), xytext=(12, 8),
                    textcoords="offset points", fontsize=22, color=TINTA)
    ax.axvline(7.07, color=TINTA2, ls=":", lw=2)
    ax.text(7.25, .55, "promedio\nPerú: 7,1", color=TINTA2, fontsize=20)
    ax.set_xlabel("Establecimientos por 10 000 hab.")
    ax.set_ylabel("Hospitales II–III por 100 000 hab.")
    ax.set_ylim(.4, 3.7)
    ax.spines[["top", "right"]].set_visible(False)
    titulo(ax, "Más locales ≠ más capacidad")
    fig.tight_layout()
    guardar(fig, c / f"{k:03d}.png")

# 5. altas por año y sector: las líneas se dibujan
c = carpeta("altas")
a = d[d["anio_inicio"].between(1990, 2016)]
pri = a[a["sector"] == "Privado"].groupby("anio_inicio").size().reindex(range(1990, 2017), fill_value=0)
pub = a[a["sector"] != "Privado"].groupby("anio_inicio").size().reindex(range(1990, 2017), fill_value=0)
for k in range(24):
    fig, ax = lienzo()
    hasta = 1990 + int(round(facil(min(1, (k + 1) / 20)) * 26))
    x = list(range(1990, hasta + 1))
    ax.plot(x, pri.loc[x], color=VIO, lw=6, label="Privados")
    ax.plot(x, pub.loc[x], color=ACC, lw=6, label="Públicos")
    ax.axvspan(2008, 2016.5, color="#ffffff", alpha=.06)
    ax.text(1990.3, 1060, "2008–2017: 9 de cada 10\nnuevos son privados", fontsize=26, color=VIO, va="top", weight="bold")
    ax.set_xlim(1989, 2017)
    ax.set_ylim(0, 1450)
    ax.legend(frameon=False, fontsize=26, loc="upper left")
    ax.set_ylabel("Nuevos establecimientos por año")
    ax.spines[["top", "right"]].set_visible(False)
    titulo(ax, "¿Quién abre establecimientos?")
    fig.tight_layout()
    guardar(fig, c / f"{k:03d}.png")

# 6. dashboard en móvil (captura vertical tomada con Edge headless, ver README)
mov = Image.open(RAIZ / "reel/recursos/dash_movil.png").convert("RGB")
ancho = 600
mov = mov.resize((ancho, int(mov.height * ancho / mov.width)))
tira = Image.new("RGB", (1080, mov.height + 120), FONDO)
tira.paste(mov, ((1080 - ancho) // 2, 60))
for f in OUT.glob("dashboard*.png"):
    f.unlink()
tira.save(OUT / "dashboard_scroll.png")
print("visuales listos en", OUT)
