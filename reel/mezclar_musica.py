"""Mezcla la música de fondo bajo la narración (-20 dB aprox., con ducking) y deja salidas/reel.mp4.

Uso: python mezclar_musica.py   (después de hacer_reel.py)
"""
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

AQUI = Path(__file__).resolve().parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
voz = AQUI / "salidas" / "reel_voz.mp4"
if not voz.exists():
    shutil.move(AQUI / "salidas" / "reel.mp4", voz)
filtro = ("[1:a]volume=0.22,aformat=channel_layouts=stereo[m];"
          "[m][0:a]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
          "[0:a][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(voz), "-i", str(AQUI / "recursos" / "musica.wav"),
                "-filter_complex", filtro, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(AQUI / "salidas" / "reel.mp4")], check=True)
voz.unlink()
print("salidas/reel.mp4 con música")
