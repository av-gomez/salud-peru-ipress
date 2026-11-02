"""Música de fondo original (ambient), sintetizada con numpy. Obra propia, uso libre (CC0).

Uso: python reel/musica.py  -> reel/recursos/musica.wav (75 s)
"""
from pathlib import Path
import numpy as np
import soundfile as sf

SR, DUR = 44100, 75
t = np.arange(SR * DUR) / SR
acordes = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 246.94, 293.66], [164.81, 207.65, 246.94]]
musica = np.zeros_like(t)
for k in range(int(DUR / 4) + 1):
    a, b = k * 4.0, k * 4.0 + 4.6
    m = (t >= a) & (t < b)
    env = np.sin(np.pi * np.clip((t[m] - a) / 4.6, 0, 1)) ** 1.5
    for f in acordes[k % 4]:
        musica[m] += env * (np.sin(2 * np.pi * f * t[m]) + .3 * np.sin(2 * np.pi * 2 * f * t[m]))
# pulso suave de bajo y arpegio
for k in range(int(DUR * 2)):
    a = k * .5
    m = (t >= a) & (t < a + .45)
    f = acordes[(k // 8) % 4][k % 3] * 2
    musica[m] += .35 * np.exp(-(t[m] - a) * 6) * np.sin(2 * np.pi * f * t[m])
musica *= np.minimum(1, np.minimum(t / 2, (DUR - t) / 3))
musica = .5 * musica / np.abs(musica).max()
out = Path(__file__).resolve().parent / "recursos" / "musica.wav"
sf.write(out, np.stack([musica, musica], 1).astype(np.float32), SR)
print(out)
