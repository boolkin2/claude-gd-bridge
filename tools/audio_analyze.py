# Анализ трека: огибающая громкости по полосам, сила атак (spectral flux),
# темп автокорреляцией, сетка долей (DP-трекинг как у Эллиса), картинка.
# Выход: song.json (bpm, beats, onsets, envelope) и song.png.
import sys, json
import numpy as np
import soundfile as sf
from scipy import signal
from PIL import Image, ImageDraw

path, out = sys.argv[1], sys.argv[2]
y, sr = sf.read(path, dtype='float32', always_2d=True)
y = y.mean(axis=1)
dur = len(y) / sr
HOP = 512
NFFT = 2048
f, t, Z = signal.stft(y, fs=sr, nperseg=NFFT, noverlap=NFFT - HOP, boundary=None, padded=False)
S = np.abs(Z).astype(np.float32)
fps = sr / HOP
times = np.arange(S.shape[1]) / fps + (NFFT / 2) / sr

def band(lo, hi):
    m = (f >= lo) & (f < hi)
    return S[m].sum(axis=0)

low, mid, high = band(20, 150), band(150, 2500), band(2500, 16000)
logS = np.log1p(100 * S)
flux = np.maximum(0, np.diff(logS, axis=1, prepend=logS[:, :1])).sum(axis=0)
# Атаки по низам (бочка) отдельно
low_log = np.log1p(100 * S[(f >= 20) & (f < 150)])
flux_low = np.maximum(0, np.diff(low_log, axis=1, prepend=low_log[:, :1])).sum(axis=0)

def norm(v):
    v = v - np.median(v)
    return v / (np.percentile(v, 99) + 1e-9)

onset = norm(flux)
# Темп: автокорреляция огибающей атак по окнам, общий максимум 70..220 BPM
def tempo_of(env):
    env = env - env.mean()
    ac = np.correlate(env, env, mode='full')[len(env) - 1:]
    lags = np.arange(len(ac))
    bpm = 60 * fps / np.maximum(lags, 1)
    m = (bpm >= 70) & (bpm <= 220)
    # предпочтение около 120-180 (лог-гаусс), как в librosa
    w = np.exp(-0.5 * (np.log2(bpm[m] / 150.0) / 1.0) ** 2)
    i = np.argmax(ac[m] * w)
    return bpm[m][i], lags[m][i]

bpm_all, _ = tempo_of(onset)
# по окнам 20 с — темп может меняться (брейккор)
win = int(20 * fps)
local = []
for s0 in range(0, len(onset) - win, win // 2):
    b, _ = tempo_of(onset[s0:s0 + win])
    local.append((round(s0 / fps, 1), round(float(b), 2)))

# DP-трекинг долей с фиксированным периодом
def track(env, bpm):
    period = 60 * fps / bpm
    n = len(env)
    score = env.copy().astype(np.float64)
    back = -np.ones(n, dtype=np.int64)
    lo, hi = int(round(period * 0.5)), int(round(period * 2))
    tight = 100.0
    for i in range(n):
        a, b = i - hi, i - lo
        if b < 0:
            continue
        a = max(a, 0)
        cand = np.arange(a, b + 1)
        pen = -tight * (np.log((i - cand) / period)) ** 2
        v = score[cand] + pen
        k = np.argmax(v)
        if v[k] > 0:
            score[i] += v[k]
            back[i] = cand[k]
    # конец — максимум в последнем периоде
    i = int(np.argmax(score[-int(period * 2):])) + n - int(period * 2)
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return np.array(beats[::-1])

beats_idx = track(onset, bpm_all)
beats = times[beats_idx]
# Пики атак (для синхронизации кликов)
peaks, props = signal.find_peaks(onset, height=0.25, distance=int(0.07 * fps))
onsets = [(float(times[p]), float(onset[p])) for p in peaks]
lpeaks, _ = signal.find_peaks(norm(flux_low), height=0.3, distance=int(0.09 * fps))
kicks = [float(times[p]) for p in lpeaks]

# Огибающая громкости (сек)
rms = np.sqrt(signal.convolve(y ** 2, np.ones(int(sr * 0.5)) / (sr * 0.5), mode='same'))[::sr // 10]
env = {'t_step': 0.1, 'rms': [round(float(v), 4) for v in rms]}
sec = lambda v: [round(float(x), 4) for x in signal.resample_poly(v, 1, int(fps // 10))]

json.dump({'duration': dur, 'bpm': float(bpm_all), 'local_bpm': local,
           'beats': [round(float(b), 4) for b in beats], 'onsets': onsets, 'kicks': kicks,
           'env': env}, open(out + '.json', 'w'))

# Картинка: по 60 с в строке, низ/середина/верх цветом, доли — штрихи
W, rowH = 1800, 110
rows = int(np.ceil(dur / 60))
img = Image.new('RGB', (W, rows * rowH), (10, 10, 14))
d = ImageDraw.Draw(img)
def series(v):
    v = np.convolve(v, np.ones(8) / 8, mode='same')
    return v / (np.percentile(v, 99.5) + 1e-9)
L, M, H = series(low), series(mid), series(high)
for r in range(rows):
    y0 = r * rowH + rowH - 10
    for px in range(W):
        tt = r * 60 + px * 60 / W
        k = int(tt * fps)
        if k >= len(L):
            break
        for v, col, off in ((L[k], (255, 80, 60), 0), (M[k], (80, 220, 120), 0), (H[k], (90, 140, 255), 0)):
            h = int(min(1.0, v) * 90)
            d.point((px, y0 - h), fill=col)
        o = onset[k]
    for b in beats:
        if r * 60 <= b < (r + 1) * 60:
            px = int((b - r * 60) / 60 * W)
            d.line([(px, y0), (px, y0 + 6)], fill=(200, 200, 200))
    for s in range(0, 60, 5):
        px = int(s / 60 * W)
        d.text((px + 2, r * rowH + 2), '%d:%02d' % ((r * 60 + s) // 60, (r * 60 + s) % 60), fill=(160, 160, 160))
img.save(out + '.png')
print('duration %.1f s, bpm %.2f, beats %d, onsets %d, kicks %d' % (dur, bpm_all, len(beats), len(onsets), len(kicks)))
print('local bpm:', local)
