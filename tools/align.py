# Привязка скриншота редактора к координатам уровня: подбор сдвига (и масштаба) так,
# чтобы контуры шипов уровня легли на белые пиксели скриншота. Затем — след игрока
# в координатах уровня и сравнение с расчётным путём генератора.
import sys, os, json
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def spikes_of(lv_objs):
    out = []
    for o in lv_objs:
        p = o.split(','); d = dict(zip(p[0::2], p[1::2]))
        if d['1'] == '8':
            out.append((float(d['2']), float(d['3']), d.get('5') == '1'))
    return out

def tips(spk):
    # вершина шипа: 15 ед. от центра (вверх у обычного, вниз у перевёрнутого)
    return np.array([(x, y - 15 if f else y + 15) for x, y, f in spk])

def align(png, spk, x_guess, y_guess=None, scale=1.625):
    im = np.asarray(Image.open(png).convert('RGB')).astype(int)
    white = (im[..., 0] > 225) & (im[..., 1] > 225) & (im[..., 2] > 225)
    white[:150] = False; white[780:] = False; white[:, :180] = False; white[:, 1500:] = False
    T = tips(spk)
    best = None
    for x0 in np.arange(x_guess - 400, x_guess + 400, 1.0):
        sx = (T[:, 0] - x0) * scale
        vis = (sx > 190) & (sx < 1490)
        if vis.sum() < 3:
            continue
        for gy in range(700, 820):
            sy = gy - T[:, 1] * scale
            ix = np.round(sx[vis]).astype(int); iy = np.round(sy[vis]).astype(int)
            ok = (iy > 150) & (iy < 780)
            if ok.sum() < 3:
                continue
            hit = 0
            for a, b in zip(ix[ok], iy[ok]):
                hit += white[b - 2:b + 3, a - 2:a + 3].any()
            sc = hit / ok.sum()
            if best is None or sc > best[0] or (sc == best[0] and ok.sum() > best[3]):
                best = (sc, x0, gy, ok.sum())
    return best

def trail(png, x0, gy, scale=1.625):
    im = np.asarray(Image.open(png).convert('RGB')).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    m = (g > 180) & (r < 170) & (b < 120) & (g - r > 60)
    m[:, :185] = False; m[:150] = False; m[780:] = False; m[:, 1500:] = False
    out = []
    for cx in range(m.shape[1]):
        ys = np.nonzero(m[:, cx])[0]
        if len(ys):
            out.append((x0 + cx / scale, (gy - float(np.median(ys))) / scale))
    return out

if __name__ == '__main__':
    import gen_layout as GL
    GL.build()
    png, death_t = sys.argv[1], float(sys.argv[2])
    xd = GL.X(death_t)
    # крестик смерти ~ в 838 px от левого края
    spk = spikes_of(GL.C.lv.objs)
    spk = [s for s in spk if xd - 1200 < s[0] < xd + 1200]
    best = align(png, spk, xd - 838 / 1.625)
    print('align score %.2f x0=%.1f ground_px=%d n=%d' % best)
    tr = trail(png, best[1], best[2])
    path = [(x, y) for (t, x, y, h, m) in GL.C.path]
    px = np.array([p[0] for p in path]); py = np.array([p[1] for p in path])
    for x, y in tr[::20]:
        k = np.argmin(abs(px - x))
        print('x=%7.1f real=%6.1f plan=%6.1f d=%+5.1f' % (x, y, py[k], y - py[k]))
