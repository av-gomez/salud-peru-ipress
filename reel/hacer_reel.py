"""Pasos 2 y 3: voz clonada (Qwen3-TTS), subtítulos (Whisper) y video (Pillow + ffmpeg).

Uso:
  python hacer_reel.py --voz mi_voz.m4a --autor "Amanda Gomez" \
      --fuente "NASA FIRMS, Sentinel-2, WorldPop" --tts Qwen/Qwen3-TTS-12Hz-0.6B-Base

Lee salidas/guion.json (ya revisado) y escribe en salidas/:
  reel.mp4 (1080x1920, 30 fps, H.264 + AAC, -14 LUFS), reel.srt, portada.png, posts.md
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
import jiwer
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
ANCHO, ALTO, FPS = 1080, 1920, 30
FONDO = (20, 17, 15)
TINTA = (243, 237, 231)
TINTA_2 = (168, 159, 151)
ACENTO = (242, 107, 29)
PAUSA = 0.35        # segundos de silencio entre escenas
CIERRE = 4.0        # segundos de la tarjeta final (créditos)
FUNDIDO = 0.3       # segundos de fundido entre escenas
MAX_WER = 0.25      # si Whisper entiende mal más del 25 %, se regenera la escena
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def fuente(negrita, tam):
    for nombre in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if negrita else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default(tam)


def normalizar(texto):
    texto = texto.lower()
    texto = re.sub(r"[^\wáéíóúüñ\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def frase_hablada(frase):
    """Por si quedó algún dígito: lo pasa a palabras."""
    from num2words import num2words

    def cambiar(m):
        n = m.group(0).replace(" ", "").replace(".", "").replace(",", ".")
        try:
            return num2words(float(n) if "." in n else int(n), lang="es")
        except ValueError:
            return m.group(0)
    return re.sub(r"\d[\d .,]*\d|\d", cambiar, frase)


def a_wav(origen, destino, inicio=0.0, fin=20.0):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", str(inicio), "-to", str(fin), "-i", str(origen),
                    "-ac", "1", "-ar", "24000", str(destino)], check=True)


def audio_16k(ruta):
    """Audio mono a 16 kHz para Whisper, decodificado con el ffmpeg de imageio."""
    crudo = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(ruta), "-f", "f32le",
                            "-ac", "1", "-ar", "16000", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(crudo, dtype=np.float32)


# ---------- voz ----------

def narrar(guion, args, whisper):
    import torch
    from qwen_tts import Qwen3TTSModel

    torch.set_num_threads(max(1, (torch.get_num_threads())))
    ref = AQUI / "salidas" / "voz_ref.wav"
    a_wav(args.voz, ref, args.voz_inicio, args.voz_fin)
    if args.texto_voz:
        ref_texto = args.texto_voz
    else:
        segs, _ = whisper.transcribe(audio_16k(ref), language="es")
        ref_texto = " ".join(s.text.strip() for s in segs)
    print(f"Tu grabación dice: «{ref_texto}»")

    t0 = time.time()
    if all((AQUI / "salidas" / f"escena_{i}.json").exists() for i in range(1, len(guion["escenas"]) + 1)):
        tts = prompt = None
    else:
      tts = Qwen3TTSModel.from_pretrained(args.tts, device_map=args.device, dtype=torch.float32)
      prompt = tts.create_voice_clone_prompt(ref_audio=str(ref), ref_text=ref_texto)
    print(f"Modelo de voz listo en {time.time() - t0:.0f} s")

    escenas = []
    from types import SimpleNamespace
    for i, esc in enumerate(guion["escenas"], 1):
        texto = frase_hablada(esc["frase"])
        cache = AQUI / "salidas" / f"escena_{i}.json"
        if cache.exists() and json.loads(cache.read_text(encoding="utf-8"))["frase"] == esc["frase"]:
            c = json.loads(cache.read_text(encoding="utf-8"))
            audio, sr = sf.read(AQUI / "salidas" / f"escena_{i}.wav", dtype="float32")
            escenas.append({"audio": audio, "sr": sr, "wer": c["wer"],
                            "palabras": [SimpleNamespace(**w) for w in c["palabras"]]})
            print(f"  escena {i}: desde caché")
            continue
        mejor = None
        for intento in range(1, 3):
            t1 = time.time()
            wavs, sr = tts.generate_voice_clone(text=texto, language="Spanish", voice_clone_prompt=prompt,
                                                 max_new_tokens=int(12 * (len(texto.split()) * 0.5 + 2)))
            audio = np.asarray(wavs[0], dtype=np.float32)
            ruta = AQUI / "salidas" / f"escena_{i}.wav"
            sf.write(ruta, audio, sr)
            segs, _ = whisper.transcribe(audio_16k(ruta), language="es", word_timestamps=True)
            palabras = [w for s in segs for w in s.words]
            oido = " ".join(w.word.strip() for w in palabras)
            # Whisper escribe "21" donde el guion dice "veintiuno": se comparan ambos en palabras
            wer = jiwer.wer(normalizar(texto), normalizar(frase_hablada(oido)) or "-")
            dur = len(audio) / sr
            print(f"  escena {i}, intento {intento}: {dur:.1f} s de audio en {time.time() - t1:.0f} s, WER {wer:.0%}")
            if mejor is None or wer < mejor["wer"]:
                mejor = {"audio": audio, "sr": sr, "palabras": palabras, "wer": wer}
            if wer <= MAX_WER:
                break
        if mejor["wer"] > MAX_WER:
            print(f"  ¡¡ escena {i} sigue con WER {mejor['wer']:.0%}: escúchala antes de publicar.")
        sf.write(AQUI / "salidas" / f"escena_{i}.wav", mejor["audio"], mejor["sr"])
        cache.write_text(json.dumps({"frase": esc["frase"], "wer": mejor["wer"], "palabras": [
            {"word": w.word, "start": w.start, "end": w.end} for w in mejor["palabras"]]}), encoding="utf-8")
        escenas.append(mejor)
    return escenas


def tiempos_palabras(frase, palabras_whisper, inicio, dur):
    """Usa el texto del guion (bien escrito) con los tiempos de Whisper."""
    guion = frase.split()
    if len(palabras_whisper) == len(guion):
        return [(p, inicio + w.start, inicio + w.end) for p, w in zip(guion, palabras_whisper)]
    a = palabras_whisper[0].start if palabras_whisper else 0.0
    b = palabras_whisper[-1].end if palabras_whisper else dur
    pesos = np.array([len(p) + 1 for p in guion], dtype=float)
    bordes = a + np.concatenate([[0], np.cumsum(pesos)]) / pesos.sum() * (b - a)
    return [(p, inicio + bordes[k], inicio + bordes[k + 1]) for k, p in enumerate(guion)]


def bloques(palabras, max_pal=5):
    """Agrupa palabras en renglones de subtítulo, cortando en signos de puntuación."""
    out, actual = [], []
    for p in palabras:
        actual.append(p)
        if len(actual) >= max_pal or p[0][-1] in ".,;:?!":
            out.append(actual)
            actual = []
    if actual:
        out.append(actual)
    return out


# ---------- video ----------

class Lienzo:
    """Compone cada cuadro: barra de progreso, aviso de IA, visual animado, cifra, etiqueta y subtítulo."""
    ANIM_FPS = 12      # velocidad de las animaciones (cuadros de visuales/<clave>/ por segundo)
    Y_VIS = 290        # borde superior del visual (1080x920)

    def __init__(self, guion, args):
        self.args = args
        self.n = len(guion["escenas"])
        self.f_cifra = fuente(True, 150)
        self.f_etiq = fuente(False, 46)
        self.f_sub = fuente(True, 58)
        self.f_peq = fuente(False, 28)
        self.f_peq_b = fuente(True, 30)
        self.f_tit = fuente(True, 64)
        self.f_med = fuente(True, 44)
        self.visuales = {}
        for esc in guion["escenas"]:
            clave = esc["visual"]
            if clave in self.visuales:
                continue
            carpeta = AQUI / "visuales" / clave
            if carpeta.is_dir():                       # animación: lista de cuadros
                self.visuales[clave] = [Image.open(f).convert("RGB") for f in sorted(carpeta.glob("*.png"))]
            elif (AQUI / "visuales" / f"{clave}_scroll.png").exists():   # imagen alta que se desplaza
                self.visuales[clave] = ("scroll", Image.open(AQUI / "visuales" / f"{clave}_scroll.png").convert("RGB"))
            else:
                self.visuales[clave] = [Image.open(AQUI / "visuales" / f"{clave}.png").convert("RGB")]

    def base(self, k=None, avance=0.0):
        img = Image.new("RGB", (ANCHO, ALTO), FONDO)
        d = ImageDraw.Draw(img)
        # barra de progreso por escenas
        if k is not None:
            ancho = (ANCHO - 120 - 12 * (self.n - 1)) / self.n
            for j in range(self.n):
                x0 = 60 + j * (ancho + 12)
                d.rounded_rectangle((x0, 168, x0 + ancho, 176), radius=4, fill=(60, 52, 46))
                lleno = 1 if j < k else (avance if j == k else 0)
                if lleno > 0.02:
                    d.rounded_rectangle((x0, 168, x0 + ancho * lleno, 176), radius=4, fill=ACENTO)
        # aviso de IA, visible todo el video
        d.rounded_rectangle((60, 200, 470, 252), radius=26, fill=(52, 45, 40))
        d.ellipse((80, 216, 100, 236), fill=ACENTO)
        d.text((112, 209), "Voz generada con IA", font=self.f_peq_b, fill=TINTA)
        d.text((60, 1665), f"Fuente: {self.args.fuente}", font=self.f_peq, fill=TINTA_2)
        d.text((60, 1705), f"Elaboración: {self.args.autor}", font=self.f_peq, fill=TINTA_2)
        return img, d

    def visual(self, clave, t_esc, dur):
        v = self.visuales[clave]
        if isinstance(v, tuple):                      # desplazamiento vertical suave
            alto = v[1]
            u = min(max((t_esc - 0.6) / max(dur - 1.4, 0.1), 0), 1)
            u = u * u * (3 - 2 * u)
            y = int((alto.height - 920) * u)
            return alto.crop((0, y, 1080, y + 920))
        cuadro = v[min(int(t_esc * self.ANIM_FPS), len(v) - 1)]
        z = 1 + 0.03 * min(t_esc / max(dur, 1), 1)    # acercamiento lento
        w, h = int(1080 * z), int(920 * z)
        return cuadro.resize((w, h), Image.BILINEAR).crop(((w - 1080) // 2, (h - 920) // 2, (w - 1080) // 2 + 1080, (h - 920) // 2 + 920))

    def cuadro(self, t, escena, t_esc, palabras_vis, k=0, dur=5.0):
        img, d = self.base(k, min(t_esc / dur, 1))
        img.paste(self.visual(escena["visual"], t_esc, dur), (0, self.Y_VIS))
        # cifra que cuenta hacia arriba en el primer 0,6 s
        cifra = escena["cifra"].replace("¡¡", "")
        d.text((60, 1225), contar(cifra, min(t_esc / 0.6, 1)), font=self.f_cifra, fill=TINTA)
        d.text((64, 1395), escena["etiqueta"], font=self.f_etiq, fill=TINTA_2)
        # subtítulo: el bloque que suena, con la palabra actual en naranja
        bloque = next((b for b in palabras_vis if b[0][1] - 0.05 <= t <= b[-1][2] + 0.25), None)
        if bloque:
            x, y = 60, 1480
            for p, a, b in bloque:
                ancho = d.textlength(p + " ", font=self.f_sub)
                if x + ancho > 940:   # margen derecho libre para los botones de la app
                    x, y = 60, y + 72
                d.text((x, y), p, font=self.f_sub, fill=ACENTO if a <= t <= b + 0.05 else TINTA)
                x += ancho
        return img

    def final(self, guion):
        img, d = self.base(self.n, 1)
        d.text((60, 330), "Explora los datos", font=self.f_med, fill=TINTA_2)
        envolver_titulo(img, d, guion.get("titulo", ""), self.f_tit, y=400)
        d.rounded_rectangle((60, 760, 1020, 900), radius=24, fill=(52, 45, 40))
        d.text((90, 778), "Dashboard interactivo", font=self.f_peq, fill=TINTA_2)
        d.text((90, 818), self.args.dashboard, font=self.f_med, fill=ACENTO)
        d.text((60, 960), "Créditos", font=self.f_med, fill=TINTA)
        creditos = [
            "Datos: MINSA – Registro IPRESS (datosabiertos.gob.pe)",
            "            e INEI – Censos Nacionales 2017",
            "Voz: generada con IA (Qwen3-TTS) a partir de",
            "            la voz de la autora",
            "Subtítulos: faster-whisper · Música: original (código)",
            "Mapas y gráficos: elaboración propia",
            f"Código: {self.args.repo}",
        ]
        for j, c in enumerate(creditos):
            d.text((60, 1030 + j * 50), c, font=self.f_peq, fill=TINTA_2)
        return img

    def portada(self, guion):
        img, d = self.base()
        img.paste(self.visual(guion["escenas"][0]["visual"], 99, 1), (0, self.Y_VIS))
        envolver_titulo(img, d, guion.get("titulo", ""), self.f_tit, y=1240)
        return img


def envolver_titulo(img, d, texto, f, y=700):
    d.rectangle((0, y - 20, ANCHO, y + 300), fill=FONDO)
    linea, lineas = "", []
    for p in texto.split():
        if d.textlength(linea + p, font=f) > 940:
            lineas.append(linea.strip())
            linea = ""
        linea += p + " "
    lineas.append(linea.strip())
    for k, l in enumerate(lineas[:4]):
        d.text((60, y + k * 78), l, font=f, fill=TINTA)
    return img


def contar(cifra, avance):
    if avance >= 1 or not re.match(r"[+\-]?\d", cifra):   # "Oct. 2026" no se anima
        return cifra
    m = re.search(r"\d[\d  ]*\d|\d", cifra)
    if not m:
        return cifra
    n = int(re.sub(r"\D", "", m.group(0)))
    v = f"{int(n * avance):,}".replace(",", " ")
    return cifra[:m.start()] + v + cifra[m.end():]


def loudnorm_2_pasadas(wav):
    """Mide el volumen y devuelve el filtro que lo lleva a -14 LUFS (una pasada se queda corta)."""
    base = "loudnorm=I=-14:TP=-1.5:LRA=11"
    salida = subprocess.run([FFMPEG, "-hide_banner", "-i", str(wav), "-af", base + ":print_format=json",
                             "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(salida[salida.rfind("{"):salida.rfind("}") + 1])
    return (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
            f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def srt_tiempo(s):
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voz", required=True)
    ap.add_argument("--voz-inicio", type=float, default=0.0, help="segundo donde empieza el tramo limpio de la grabación")
    ap.add_argument("--voz-fin", type=float, default=20.0, help="segundo donde termina (al cierre de una frase)")
    ap.add_argument("--texto-voz", help="lo que dices en la grabación (si no, lo transcribe Whisper)")
    ap.add_argument("--autor", required=True)
    ap.add_argument("--fuente", required=True)
    ap.add_argument("--repo", default="github.com/av-gomez/salud-peru-ipress")
    ap.add_argument("--dashboard", default="av-gomez.github.io/salud-peru-ipress")
    ap.add_argument("--guion", default=str(AQUI / "guion.json"))
    ap.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    guion = json.loads(Path(args.guion).read_text(encoding="utf-8"))
    if any("¡¡" in e["cifra"] for e in guion["escenas"]):
        print("Aviso: hay cifras marcadas con ¡¡ en el guion. Corrígelas o confirma que están bien.")
    sal = AQUI / "salidas"
    sal.mkdir(exist_ok=True)
    t_total = time.time()
    whisper = WhisperModel("small", device="cpu", compute_type="int8")
    escenas = narrar(guion, args, whisper)

    # línea de tiempo
    sr = escenas[0]["sr"]
    pausa = np.zeros(int(PAUSA * sr), dtype=np.float32)
    pistas, linea, t = [], [], 0.0
    for esc, datos in zip(guion["escenas"], escenas):
        dur = len(datos["audio"]) / sr
        pal = tiempos_palabras(esc["frase"], datos["palabras"], t, dur)
        linea.append({"escena": esc, "inicio": t, "fin": t + dur + PAUSA, "bloques": bloques(pal)})
        pistas += [datos["audio"], pausa]
        t += dur + PAUSA
    pistas.append(np.zeros(int(CIERRE * sr), dtype=np.float32))
    audio = np.concatenate(pistas)
    sf.write(sal / "reel.wav", audio, sr)
    filtro = loudnorm_2_pasadas(sal / "reel.wav")
    total = len(audio) / sr
    print(f"Audio: {total:.1f} s")

    # subtítulos .srt
    renglones = [b for tramo in linea for b in tramo["bloques"]]
    with open(sal / "reel.srt", "w", encoding="utf-8") as f:
        for k, b in enumerate(renglones, 1):
            f.write(f"{k}\n{srt_tiempo(b[0][1])} --> {srt_tiempo(b[-1][2])}\n{' '.join(p for p, _, _ in b)}\n\n")

    # cuadros -> ffmpeg (el volumen se lleva a -14 LUFS al mezclar)
    lienzo = Lienzo(guion, args)
    lienzo.portada(guion).save(sal / "portada.png")
    final = lienzo.final(guion)
    cmd = [FFMPEG, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
           "-i", str(sal / "reel.wav"),
           "-af", filtro, "-ar", "48000",
           "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", str(sal / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(int(total * FPS)):
        tt = n / FPS
        k = next((j for j, x in enumerate(linea) if x["inicio"] <= tt < x["fin"]), None)
        if k is None:
            # tarjeta final con fundido desde la última escena
            u = min((tt - linea[-1]["fin"]) / FUNDIDO, 1)
            x = linea[-1]
            if u < 1:
                ult = lienzo.cuadro(tt, x["escena"], tt - x["inicio"], [], len(linea) - 1, x["fin"] - x["inicio"])
                img = Image.blend(ult, final, u)
            else:
                img = final
        else:
            x = linea[k]
            img = lienzo.cuadro(tt, x["escena"], tt - x["inicio"], x["bloques"], k, x["fin"] - x["inicio"])
            if k > 0 and tt - x["inicio"] < FUNDIDO:   # fundido cruzado entre escenas
                p = linea[k - 1]
                prev = lienzo.cuadro(tt, p["escena"], tt - p["inicio"], [], k - 1, p["fin"] - p["inicio"])
                img = Image.blend(prev, img, (tt - x["inicio"]) / FUNDIDO)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()

    # posts, con el aviso de IA al final de cada uno
    aviso = "Voz generada con IA a partir de mi propia voz. Guion revisado contra la fuente."
    posts = guion.get("posts", {})
    with open(sal / "posts.md", "w", encoding="utf-8") as f:
        f.write(f"# Posts del reel: {guion.get('titulo', '')}\n\n")
        for red, nombre in (("x", "X"), ("linkedin", "LinkedIn"), ("facebook", "Facebook")):
            f.write(f"## {nombre}\n\n{posts.get(red, '').strip()}\n\n{aviso}\n\n")
    mb = (sal / "reel.mp4").stat().st_size / 1e6
    print(f"Listo en {time.time() - t_total:.0f} s: salidas/reel.mp4 ({total:.0f} s, {mb:.1f} MB), reel.srt, portada.png, posts.md")


if __name__ == "__main__":
    main()
