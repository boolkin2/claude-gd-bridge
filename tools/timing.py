# Ритм трека для синхронизации: сетка долей 217 BPM (фаза по «гребёнке»),
# сила атак в точках сетки 1/16 по полосам: всё / бочка / малый / хэты.
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SONG = os.path.join(HERE, '..', 'data', 'song.mp3')
BPM = 217.0
BEAT = 60.0 / BPM
SIXT = BEAT / 4

def _envelopes():
    import soundfile as sf
    from scipy import signal
    y, sr = sf.read(SONG, dtype='float32', always_2d=True)
    y = y.mean(axis=1)[:int(200 * sr)]
    HOP, NFFT = 256, 2048
    f, t, Z = signal.stft(y, fs=sr, nperseg=NFFT, noverlap=NFFT - HOP, boundary=None, padded=False)
    S = np.log1p(100 * np.abs(Z))
    fps = sr / HOP
    times = np.arange(S.shape[1]) / fps + (NFFT / 2) / sr

    def flux(lo, hi):
        m = (f >= lo) & (f < hi)
        v = np.maximum(0, np.diff(S[m], axis=1, prepend=S[m][:, :1])).sum(axis=0)
        v = v - np.median(v)
        return np.maximum(0, v / (np.percentile(v, 99.5) + 1e-9))
    return times, {'all': flux(30, 16000), 'low': flux(30, 150), 'mid': flux(150, 4000), 'high': flux(4000, 16000)}

def _phase(times, on, t0, t1):
    m = (times >= t0) & (times < t1)
    tt, oo = times[m], on[m]
    best = (-1, 0)
    for ph in np.linspace(0, BEAT, 120, endpoint=False):
        k = np.round((tt - ph) / BEAT)
        dev = tt - ph - k * BEAT
        s = float((oo * np.exp(-0.5 * (dev / 0.010) ** 2)).sum() / (oo.sum() + 1e-9))
        if s > best[0]:
            best = (s, ph)
    return best

def build(cache=os.path.join(HERE, '..', 'data', 'rhythm.json')):
    if os.path.exists(cache):
        return json.load(open(cache))
    times, env = _envelopes()
    report = []
    for a, b in ((3, 15), (15, 37.6), (37.6, 55.2), (55.2, 90), (90, 126), (126, 161), (161, 196.8)):
        s, ph = _phase(times, env['all'], a, b)
        report.append((a, b, round(ph, 4), round(s, 3)))
    s, anchor = _phase(times, env['all'], 55.2, 196.8)
    grid = np.arange(anchor, 197.5, SIXT)
    pts = []
    for g in grid:
        m = (times >= g - 0.018) & (times <= g + 0.018)
        pts.append([round(float(g), 5)] + [round(float(env[k][m].max()) if m.any() else 0.0, 3) for k in ('all', 'low', 'mid', 'high')])
    data = {'bpm': BPM, 'anchor': anchor, 'phase_report': report, 'grid': pts}
    json.dump(data, open(cache, 'w'))
    return data

if __name__ == '__main__':
    d = build()
    print('anchor %.4f' % d['anchor'])
    for r in d['phase_report']:
        print('window %5.1f-%5.1f phase %.4f score %.3f' % tuple(r))
    g = np.array(d['grid'])
    print('grid points', len(g))
    # средняя сила по позициям внутри доли (0, 1/4, 1/2, 3/4) в дропе
    m = (g[:, 0] > 55.2) & (g[:, 0] < 196.8)
    idx = np.arange(len(g))[m] % 4
    for k in range(4):
        print('pos %d/4: all %.3f low %.3f mid %.3f high %.3f' % ((k,) + tuple(g[m][idx == k][:, 1:].mean(axis=0))))
