# Совместная подгонка физики корабля по двум следам: калибровочному (длинные зажатия)
# и прогону лайаута (короткие нажатия). Ввод доходит до игры только на границе кадра
# (120 FPS): моделируем квантование ввода сеткой кадров с неизвестной фазой.
import json, sys, os
import numpy as np
from scipy.optimize import minimize
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

G = 0.958199
V = 311.58

def sim(sched, p, t0, t_end, y0=15.0, frame=None, phase=0.0, sub=240.0):
    y, vy, t = y0, 0.0, t0
    xs, ys = [], []
    dt = 0.25 * 0.9 * (240.0 / sub)
    ev = sorted(sched)
    st = 0
    while t < t_end:
        while ev:
            te = ev[0][0]
            if frame:
                te = phase + np.ceil((te - phase) / frame - 1e-9) * frame
            if te <= t + 1e-9:
                st = ev.pop(0)[1]
            else:
                break
        falling = vy < G * p.get('fthr', 1.0)
        if st:
            a = p['up_f'] if falling else p['up']
        else:
            a = -(p['dn_f'] if falling else p['dn_r'])
        vy += G * dt * a
        vy = max(-p['cap_dn'], min(p['cap_up'], vy))
        y += dt * vy
        if y < 15: y, vy = 15.0, max(vy, 0.0)
        if y > 285: y, vy = 285.0, min(vy, 0.0)
        t += 1 / sub
        xs.append(t); ys.append(y)
    return np.array(xs), np.array(ys)

def trail_run1():
    im = np.asarray(Image.open('run1.png').convert('RGB')).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    m = (g > 180) & (r < 170) & (b < 120) & (g - r > 60)
    out = []
    for cx in range(280, 826):
        ys = np.nonzero(m[160:790, cx])[0] + 160
        if len(ys):
            x = 1033.1 + (cx - 403) / 1.625
            y = 116.9 + (604 - np.median(ys)) / 1.62
            out.append((x / V + 0.0, y))
    return out

if __name__ == '__main__':
    import gen_layout as GL
    GL.build()
    sched1 = [e for e in sorted(GL.C.inputs) if 3.0 < e[0] < 4.3]
    t0_1 = GL.SECS[1]['t0']
    tr1 = trail_run1()
    # время на треке = x / V для раздела 1x, начиная с x=0 (раздел 0 тоже 1x)
    cal = json.load(open('trail_ship.json'))
    schedc = [tuple(e) for e in json.load(open('cal_ship_inputs.json'))['inputs']]
    trc = [(x / V, y) for x, y in cal if 5 < x < 1060]
    names = ['up', 'up_f', 'dn_f', 'dn_r', 'cap_up', 'cap_dn']
    def run(p, frame, phase):
        e = []
        xs, ys = sim(schedc, p, 0.0, 3.5, frame=frame, phase=phase)
        tt = np.array([a for a, b in trc]); yy = np.array([b for a, b in trc])
        e.append(np.interp(tt, xs, ys) - yy)
        xs, ys = sim(sched1, p, t0_1, 4.25, frame=frame, phase=phase)
        tt = np.array([a for a, b in tr1]); yy = np.array([b for a, b in tr1])
        mk = tt > t0_1 + 0.01
        e.append(np.interp(tt[mk], xs, ys) - yy[mk])
        return [float(np.sqrt(np.mean(v ** 2))) for v in e]
    cur = dict(up=0.4351, up_f=0.5159, dn_f=0.3133, dn_r=0.4571, cap_up=7.856, cap_dn=6.487)
    print('current params, no quantization:', run(cur, None, 0))
    for fr in (1 / 120.0, 1 / 60.0):
        print('current, frame %.4f:' % fr, [run(cur, fr, ph) for ph in (0, fr / 2)])
    ogd = dict(up=0.4, up_f=0.5, dn_f=0.32, dn_r=0.48, cap_up=8.0, cap_dn=6.4)
    print('OpenGD:', run(ogd, None, 0))
    def f(v):
        p = dict(zip(names, v)); p['fthr'] = 1.0
        a, b = run(p, None, 0)
        return a + b
    best = minimize(f, [cur[k] for k in names], method='Nelder-Mead', options={'maxiter': 4000})
    p = dict(zip(names, best.x))
    print('joint fit:', {k: round(float(v), 4) for k, v in p.items()}, run(p, None, 0))
