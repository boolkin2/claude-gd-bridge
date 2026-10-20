# Структура трека: громкость по полосам (сглажено 1 с, в дБ), плотность атак,
# «новизна» (резкая смена спектра) -> кандидаты границ разделов.
# Плюс крупный план атак с сеткой долей для окна [z0, z0+4 c].
import sys, json
import numpy as np
import soundfile as sf
from scipy import signal
from PIL import Image, ImageDraw

path, out = sys.argv[1], sys.argv[2]
zooms = [float(v) for v in sys.argv[3:]]
y, sr = sf.read(path, dtype='float32', always_2d=True)
y = y.mean(axis=1)
HOP, NFFT = 512, 2048
f, t, Z = signal.stft(y, fs=sr, nperseg=NFFT, noverlap=NFFT - HOP, boundary=None, padded=False)
S = np.abs(Z).astype(np.float32)
fps = sr / HOP
times = np.arange(S.shape[1]) / fps + (NFFT / 2) / sr
bands = [(20, 120), (120, 400), (400, 2000), (2000, 6000), (6000, 16000)]
E = np.stack([(S[(f >= a) & (f < b)] ** 2).sum(axis=0) for a, b in bands])
k = int(fps)  # 1 с
Es = np.stack([np.convolve(e, np.ones(k) / k, mode='same') for e in E])
dB = 10 * np.log10(Es + 1e-9)
dB -= dB.max(axis=1, keepdims=True)
logS = np.log1p(100 * S)
flux = np.maximum(0, np.diff(logS, axis=1, prepend=logS[:, :1])).sum(axis=0)
on = flux - np.median(flux); on /= np.percentile(on, 99)
# новизна: разница средних спектров (по 12 полосам) в окнах 3 с до/после
mel_edges = np.geomspace(30, 16000, 13)
M = np.stack([np.log1p(S[(f >= mel_edges[i]) & (f < mel_edges[i + 1])].mean(axis=0) * 100) for i in range(12)])
w = int(3 * fps)
cs = np.cumsum(np.pad(M, ((0, 0), (1, 0))), axis=1)
nov = np.zeros(M.shape[1])
for i in range(w, M.shape[1] - w):
    a = (cs[:, i] - cs[:, i - w]) / w
    b = (cs[:, i + w] - cs[:, i]) / w
    nov[i] = np.sqrt(((a - b) ** 2).sum())
pk, _ = signal.find_peaks(nov, distance=int(6 * fps), prominence=np.percentile(nov, 90) * 0.5)
bounds = sorted([(round(float(times[p]), 2), round(float(nov[p]), 2)) for p in pk])
print('novelty boundaries (t, strength):')
for b in bounds:
    print('  %d:%05.2f  %.2f' % (b[0] // 60, b[0] % 60, b[1]))
# плотность атак (пики) за 2 с
peaks, _ = signal.find_peaks(on, height=0.25, distance=int(0.06 * fps))
pt = times[peaks]
dens = np.histogram(pt, bins=np.arange(0, times[-1] + 2, 2))[0] / 2.0
json.dump({'bounds': bounds, 'density_per_s_2s_bins': dens.tolist(),
           'band_db_per_s': [[round(float(v), 1) for v in row[::int(fps)]] for row in dB]},
          open(out + '_sections.json', 'w'))

W, H = 1800, 420
dur = times[-1]
img = Image.new('RGB', (W, H), (10, 10, 14))
d = ImageDraw.Draw(img)
cols = [(255, 70, 60), (255, 170, 60), (90, 220, 110), (80, 160, 255), (190, 110, 255)]
for bi in range(5):
    pts = []
    for px in range(W):
        i = int(px / W * dur * fps)
        v = max(-40, dB[bi, min(i, dB.shape[1] - 1)])
        pts.append((px, 20 + (-v) * 6))
    d.line(pts, fill=cols[bi], width=1)
for px in range(W):
    i = int(px / W * dur / 2)
    if i < len(dens):
        h = dens[i] * 8
        d.line([(px, H - 5), (px, H - 5 - h)], fill=(70, 70, 80))
nv = nov / nov.max()
d.line([(px, 300 - nv[min(int(px / W * dur * fps), len(nv) - 1)] * 60) for px in range(W)], fill=(230, 230, 230))
for tb, s in bounds:
    X = tb / dur * W
    d.line([(X, 0), (X, H)], fill=(255, 255, 0))
    d.text((X + 2, 2), '%d:%02d' % (tb // 60, tb % 60), fill=(255, 255, 0))
for s in range(0, int(dur), 10):
    X = s / dur * W
    d.line([(X, H - 3), (X, H)], fill=(200, 200, 200))
img.save(out + '_sections.png')

# крупные планы
bj = json.load(open(out + '.json'))
beats = np.array(bj['beats'])
for z0 in zooms:
    W2, H2 = 1600, 160
    im = Image.new('RGB', (W2, H2), (10, 10, 14))
    dd = ImageDraw.Draw(im)
    i0, i1 = int(z0 * fps), int((z0 + 4) * fps)
    for i in range(i0, i1):
        X = (times[i] - z0) / 4 * W2
        h = max(0, on[i]) * 120
        dd.line([(X, H2 - 10), (X, H2 - 10 - h)], fill=(120, 200, 255))
    for b in beats[(beats >= z0) & (beats < z0 + 4)]:
        X = (b - z0) / 4 * W2
        dd.line([(X, 0), (X, H2)], fill=(255, 80, 80))
        for q in (0.25, 0.5, 0.75):
            Xq = X + q * (60 / bj['bpm']) / 4 * W2
            dd.line([(Xq, 0), (Xq, 12)], fill=(120, 120, 120))
    dd.text((4, 4), 'zoom %.2f..%.2f s' % (z0, z0 + 4), fill=(255, 255, 255))
    im.save(out + '_zoom_%d.png' % int(z0))
