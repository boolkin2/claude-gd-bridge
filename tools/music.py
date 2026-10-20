# Анализ любой песни для стройки уровня: темп, фаза долей, сетка 1/16 с силой атак по полосам,
# разделы трека с энергией и меткой (intro / build / drop / calm / outro). Кэш: data/music/<key>.json.
#   python -P music.py <mp3> [--key 1029814] [--bpm 217]   — проанализировать и напечатать разделы
#   from music import analyze; m = analyze(path)         — словарь (см. конец analyze)
import sys, os, json, math, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'data', 'music')


def song_path(song_id):
    """Файл песни GD по ID (кастомные песни лежат в %LOCALAPPDATA%\\GeometryDash\\<id>.mp3)."""
    p = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'GeometryDash', '%d.mp3' % int(song_id))
    return p if os.path.exists(p) else None


def _load(path, max_s=600):
    import soundfile as sf
    y, sr = sf.read(path, dtype='float32', always_2d=True)
    return y.mean(axis=1)[:int(max_s * sr)], sr


def _flux_bands(y, sr):
    from scipy import signal
    HOP, NFFT = 256, 2048
    f, t, Z = signal.stft(y, fs=sr, nperseg=NFFT, noverlap=NFFT - HOP, boundary=None, padded=False)
    A = np.abs(Z).astype(np.float32)
    S = np.log1p(100 * A)
    fps = sr / HOP
    times = np.arange(S.shape[1]) / fps + (NFFT / 2) / sr

    def flux(lo, hi):
        m = (f >= lo) & (f < hi)
        v = np.maximum(0, np.diff(S[m], axis=1, prepend=S[m][:, :1])).sum(axis=0)
        v = v - np.median(v)
        return np.maximum(0, v / (np.percentile(v, 99.5) + 1e-9))

    bands = {'all': flux(30, 16000), 'low': flux(30, 150), 'mid': flux(150, 4000), 'high': flux(4000, 16000)}
    energy = (A ** 2).sum(axis=0)
    return times, fps, bands, energy


def _tempo(env, fps, lo=70, hi=230):
    env = env - env.mean()
    n = len(env)
    spec = np.fft.rfft(env, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    lags = np.arange(n)
    bpm = 60 * fps / np.maximum(lags, 1)
    m = (bpm >= lo) & (bpm <= hi)
    w = np.exp(-0.5 * (np.log2(bpm[m] / 150.0) / 1.0) ** 2)
    i = int(np.argmax(ac[m] * w))
    # уточнение параболой
    L = lags[m][i]
    if 1 <= L < n - 1:
        a, b, c = ac[L - 1], ac[L], ac[L + 1]
        d = 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
        L = L + d
    return 60 * fps / L


def _phase(times, on, beat):
    best = (-1.0, 0.0)
    for ph in np.linspace(0, beat, 160, endpoint=False):
        k = np.round((times - ph) / beat)
        dev = times - ph - k * beat
        s = float((on * np.exp(-0.5 * (dev / 0.010) ** 2)).sum())
        if s > best[0]:
            best = (s, ph)
    return best[1]


def analyze(path, key=None, bpm=None, refresh=False):
    key = key or os.path.splitext(os.path.basename(path))[0]
    os.makedirs(CACHE, exist_ok=True)
    cp = os.path.join(CACHE, '%s.json' % key)
    if os.path.exists(cp) and not refresh:
        return json.load(open(cp))
    y, sr = _load(path)
    dur = len(y) / sr
    times, fps, B, energy = _flux_bands(y, sr)
    on = B['all']
    if not bpm:
        base = _tempo(on, fps)
        # автокорреляция путает темп с 2/3, 1/2 и т.п. (брейккор: 217 -> 144.7) — среди кратных
        # берём тот, где атаки резче всего ложатся на доли относительно середин между долями
        from scipy import signal as _sig
        pk, pr = _sig.find_peaks(on, height=0.15, distance=int(0.05 * fps))
        P, W = times[pk], pr['peak_heights']

        def comb(bt, ph, off=0.0):
            dev = (P - ph - off * bt) / bt
            dev = (dev - np.round(dev)) * bt
            return float((W * np.exp(-0.5 * (dev / 0.012) ** 2)).sum())

        # автокорреляция огибающей атак на лаге доли (и двух долей): у верного темпа она высокая,
        # у кратного 2:3 — низкая (815808: 120 BPM -> 0.05, 180 BPM -> 0.50)
        envz = on - on.mean()
        acf = np.fft.irfft(np.abs(np.fft.rfft(envz, 2 * len(envz))) ** 2)[:len(envz)]
        acf = acf / (acf[0] + 1e-12)

        def ac_at(bpm_):
            L = 60.0 * fps / bpm_
            i = int(L)
            if i + 1 >= len(acf):
                return 0.0
            return float(acf[i] + (acf[i + 1] - acf[i]) * (L - i))

        # интервалы между сильными атаками: верный темп объясняет их восьмыми/четвертями/половинными
        # (815808: 0.33 с -> 180; RETINA: 0.14/0.27 с -> 217; 467339: 0.18/0.37 с -> 162)
        sw = W >= np.percentile(W, 60) if len(W) else W
        ioi = np.diff(P[sw]) if len(P) else np.zeros(0)
        ioi = ioi[(ioi > 0.08) & (ioi < 1.5)]

        def ioi_score(bpm_):
            bt = 60.0 / bpm_
            sc = 0.0
            for mult, wgt in ((0.5, 1.0), (1.0, 1.0), (2.0, 0.5)):
                sc += wgt * float(np.sum(np.abs(ioi / (bt * mult) - 1.0) < 0.04))
            return sc + 1e-6

        best = None
        for r in (1, 1.5, 2, 4 / 3, 0.75, 2 / 3, 0.5, 3):
            if not 100 <= base * r <= 240:
                continue
            top = None
            for cand in base * r * np.linspace(0.995, 1.005, 41):   # дрейф за минуты > 1/16
                bt = 60.0 / cand
                for ph in np.linspace(0, bt, 48, endpoint=False):
                    s = comb(bt, ph)
                    if top is None or s > top[0]:
                        top = (s, cand, ph)
            s, cand, ph = top
            contrast = s / (comb(60.0 / cand, ph, 0.5) + 1e-9)
            score = ioi_score(cand) * (1.0 + 0.05 * min(contrast, 5.0))
            if best is None or score > best[0]:
                best = (score, cand)
        bpm = best[1]
    beat = 60.0 / bpm
    anchor = _phase(times, on, beat)
    sixt = beat / 4
    grid = []
    t = anchor
    while t < dur:
        m = (times >= t - 0.018) & (times <= t + 0.018)
        grid.append([round(t, 5)] + [round(float(B[k][m].max()) if m.any() else 0.0, 3)
                                     for k in ('all', 'low', 'mid', 'high')])
        t += sixt
    # энергия по тактам (4 доли) и границы разделов по скачкам энергии/плотности атак
    bar = 4 * beat
    nb = int((dur - anchor) // bar)
    e_bar, d_bar = [], []
    for i in range(nb):
        a, b = anchor + i * bar, anchor + (i + 1) * bar
        m = (times >= a) & (times < b)
        e_bar.append(float(np.log10(energy[m].mean() + 1e-9)) if m.any() else -9)
        d_bar.append(float(on[m].mean()) if m.any() else 0)
    e = np.array(e_bar); e = (e - e.min()) / (e.max() - e.min() + 1e-9)
    dd = np.array(d_bar); dd = (dd - dd.min()) / (dd.max() - dd.min() + 1e-9)
    score = 0.6 * e + 0.4 * dd
    sm = np.convolve(score, np.ones(2) / 2, mode='same')
    # границы — каждые 4/8 тактов там, где энергия сильно меняется; минимум 4 такта в разделе
    cuts = [0]
    for i in range(4, nb - 3):
        if i - cuts[-1] < 4:
            continue
        before, after = sm[max(0, i - 4):i].mean(), sm[i:i + 4].mean()
        if abs(after - before) > 0.18 or (i - cuts[-1] >= 16 and i % 8 == 0):
            cuts.append(i)
    cuts.append(nb)
    # метки по рангу энергии: самые громкие ~35% времени трека — drop, самые тихие ~30% — calm,
    # остальное — build; первый тихий раздел — intro, последний тихий — outro
    segs = [(cuts[k], cuts[k + 1], float(sm[cuts[k]:cuts[k + 1]].mean())) for k in range(len(cuts) - 1)]
    order = sorted(range(len(segs)), key=lambda k: -segs[k][2])
    total = sum(b - a for a, b, _ in segs) or 1
    lab = {}
    acc = 0
    for k in order:
        a, b, _ = segs[k]
        frac_before = acc / total
        lab[k] = 'drop' if frac_before < 0.35 else ('build' if frac_before < 0.70 else 'calm')
        acc += b - a
    sections = []
    for k, (a, b, lvl) in enumerate(segs):
        label = lab[k]
        if k == 0 and label != 'drop': label = 'intro'
        if k == len(segs) - 1 and label != 'drop': label = 'outro'
        sections.append({'bar0': a, 'bar1': b, 't0': round(anchor + a * bar, 3), 't1': round(anchor + b * bar, 3),
                         'beats': (b - a) * 4, 'energy': round(lvl, 3), 'label': label})
    # реальные атаки (пики) с силой по полосам — клики ставим на них: не зависит от ошибки темпа
    from scipy import signal as _sig
    pk, pr = _sig.find_peaks(on, height=0.12, distance=int(0.045 * fps))
    onsets = [[round(float(times[i]), 4)] + [round(float(B[k][i]), 3) for k in ('all', 'low', 'mid', 'high')]
              for i in pk]
    # точки сетки притягиваем к ближайшей атаке (±30% шестнадцатой): если темп определён неточно
    # (кратность 3:2 и т.п.), сильные точки всё равно ложатся на реальные удары
    if onsets:
        ot = np.array([o[0] for o in onsets])
        snapped, used = [], set()
        for g in grid:
            j = int(np.argmin(np.abs(ot - g[0])))
            if abs(ot[j] - g[0]) < 0.3 * sixt and j not in used:
                used.add(j)
                o = onsets[j]
                snapped.append([o[0]] + [max(a, b) for a, b in zip(g[1:], o[1:])])
            else:
                snapped.append(g)
        snapped.sort(key=lambda r: r[0])
        grid = [r for k, r in enumerate(snapped) if k == 0 or r[0] - snapped[k - 1][0] > 0.02]
    res = {'path': path, 'key': key, 'duration': round(dur, 2), 'bpm': round(bpm, 3), 'beat': beat,
           'anchor': round(anchor, 5), 'sixt': sixt, 'grid': grid, 'onsets': onsets, 'sections': sections}
    json.dump(res, open(cp, 'w'))
    return res


def strengths(m, t0, t1, band='drums'):
    """Точки сетки 1/16 в [t0, t1) и их сила; band: all/low/mid/high/drums (бочка+малый+0.25 хэтов)."""
    g = np.array(m['grid'])
    sel = (g[:, 0] >= t0 - 1e-4) & (g[:, 0] < t1 - 1e-4)
    g = g[sel]
    if band == 'drums':
        return g[:, 0], np.maximum(g[:, 2], g[:, 3]) + 0.25 * g[:, 4]
    return g[:, 0], g[:, {'all': 1, 'low': 2, 'mid': 3, 'high': 4}[band]]


def onsets_in(m, t0, t1, band='drums', min_gap=0.06):
    """Атаки в [t0, t1): (время, сила); band как в strengths; не чаще min_gap (оставляем сильнейшие)."""
    o = np.array(m['onsets']) if m['onsets'] else np.zeros((0, 5))
    o = o[(o[:, 0] >= t0) & (o[:, 0] < t1)]
    if band == 'drums':
        s = np.maximum(o[:, 2], o[:, 3]) + 0.25 * o[:, 4]
    else:
        s = o[:, {'all': 1, 'low': 2, 'mid': 3, 'high': 4}[band]]
    keep = []
    for i in np.argsort(-s):
        if all(abs(o[i, 0] - o[j, 0]) >= min_gap for j in keep):
            keep.append(i)
    keep.sort(key=lambda i: o[i, 0])
    return o[keep, 0], s[keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--key')
    ap.add_argument('--bpm', type=float)
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    m = analyze(a.path, a.key, a.bpm, a.refresh)
    print('duration %.1f s, bpm %.2f, anchor %.4f, grid %d' % (m['duration'], m['bpm'], m['anchor'], len(m['grid'])))
    for s in m['sections']:
        print('  %6.1f-%6.1f  %3d beats  energy %.2f  %s' % (s['t0'], s['t1'], s['beats'], s['energy'], s['label']))


if __name__ == '__main__':
    main()
