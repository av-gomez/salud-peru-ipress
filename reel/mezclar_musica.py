"""Mezcla la música de fondo bajo la narración y deja el reel final en reel/reel.mp4.

- La música entra a ~-8 dB respecto de la voz y baja aún más mientras se habla (sidechain/ducking).
- Fundido de entrada (1 s) y de salida (2,5 s) de la música.
- Copia los subtítulos a reel/subtitulos.srt.

Uso: python mezclar_musica.py   (después de hacer_reel.py)
"""
import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

AQUI = Path(__file__).resolve().parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
voz = AQUI / "salidas" / "reel.mp4"
info = subprocess.run([FF, "-i", str(voz)], capture_output=True, text=True).stderr
h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
dur = int(h) * 3600 + int(m) * 60 + float(s)
filtro = (f"[1:a]volume=0.40,afade=t=in:d=1,afade=t=out:st={dur - 2.5:.2f}:d=2.5,aformat=channel_layouts=stereo[m];"
          "[0:a]aformat=channel_layouts=stereo,asplit=2[v1][v2];"
          "[m][v1]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
          "[v2][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(voz), "-i", str(AQUI / "recursos" / "musica.wav"),
                "-filter_complex", filtro, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(AQUI / "reel.mp4")], check=True)
shutil.copy(AQUI / "salidas" / "reel.srt", AQUI / "subtitulos.srt")
print(f"reel/reel.mp4 listo ({dur:.1f} s) y reel/subtitulos.srt")
