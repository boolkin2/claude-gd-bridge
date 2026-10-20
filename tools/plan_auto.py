# Автопланировщик уровня: заявка (сложность, упор) + анализ музыки (music.py) -> план разделов для
# gen_layout.configure: [(b0, b1, режим, скорость, мини, параметры), ...] в долях + подписи разделов.
# Разнообразие: фразы короче в дропах и на высокой сложности; режим не повторяется подряд; стиль
# (паттерн) не повторяется в последних трёх; на дропах сложных уровней — смена скорости как приём
# (как в GRIEF); параметры (запасы, окна, плотность кликов) — по таблице сложности (docs/design_guide.md).
#   from plan_auto import make_plan; plan = make_plan(music, difficulty='Hard Demon', focus='Balanced')
import random

DIFFS = ['Auto', 'Easy', 'Normal', 'Hard', 'Harder', 'Insane', 'Easy Demon', 'Medium Demon', 'Hard Demon',
         'Insane Demon', 'Extreme Demon']
#                   Auto Easy Norm Hard Hrdr Ins  EasyD MedD HardD InsD ExtD
WAVE_M = [40, 36, 30, 24, 20, 18, 16, 14, 12, 10, 8]
SHIP_M = [45, 40, 34, 28, 24, 22, 20, 18, 16, 14, 12]
WINDOW = [0.09, 0.08, 0.07, 0.06, 0.055, 0.05, 0.048, 0.045, 0.04, 0.035, 0.03]
CLICK_Q = [0.85, 0.8, 0.7, 0.62, 0.58, 0.54, 0.5, 0.47, 0.44, 0.4, 0.36]
PHRASE_DROP = [32, 32, 32, 16, 16, 16, 16, 12, 8, 8, 4]   # долей в фразе (смена режима)
MAX_SPEED = [1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4]

MODE_W = {
    'intro': {'cube': 3, 'ship': 2, 'ufo': 1, 'ball': 1},
    'build': {'ship': 2, 'cube': 2, 'ball': 1.5, 'ufo': 1.5, 'spider': 1, 'wave': 1},
    'drop': {'wave': 3, 'ship': 2, 'spider': 1.5, 'ufo': 1, 'ball': 1, 'cube': 1},
    'calm': {'cube': 2, 'ufo': 2, 'ball': 1.5, 'ship': 1.5, 'wave': 0.5},
    'outro': {'cube': 2, 'ship': 2, 'ufo': 1},
}
PATTERNS = {
    'wave': ['zigzag', 'spam', 'diagonal'],
    'ship': ['gates', 'tunnel', 'hops'],
    'ufo': ['hops', 'gates', 'tunnel'],
    'cube': ['jumps', 'platforms'],
    'ball': ['lanes'],
    'spider': ['lanes'],
}


def _pick(rng, weights):
    items = [(k, w) for k, w in weights.items() if w > 0]
    r = rng.random() * sum(w for _, w in items)
    for k, w in items:
        r -= w
        if r <= 0:
            return k
    return items[-1][0]


def make_plan(music, difficulty='Hard', focus='Beauty', seed=1, max_len=200.0, allow_mini=True):
    d = DIFFS.index(difficulty) if difficulty in DIFFS else 3
    rng = random.Random(seed)
    k_focus = {'Difficulty': 0.8, 'Beauty': 1.2}.get(focus, 1.0)   # множитель запасов
    beat = 60.0 / music['bpm']
    anchor = music['anchor']
    tb = lambda t: int(round((t - anchor) / beat))
    secs = [s for s in music['sections'] if s['t0'] < max_len]
    end_t = min(secs[-1]['t1'], max_len) if secs else max_len
    end_b = tb(end_t) // 4 * 4
    plan, labels = [], []
    hist = []   # (режим, паттерн)
    prev_mode = None
    for si, ms in enumerate(secs):
        b0, b1 = max(0, tb(ms['t0'])), min(end_b, tb(ms['t1']))
        if b1 - b0 < 4:
            continue
        lab = ms['label']
        base = PHRASE_DROP[d]
        phrase = {'drop': base, 'build': base * 2, 'intro': 32, 'calm': max(16, base * 2), 'outro': 32}[lab]
        phrase = max(4, min(phrase, 64))
        b = b0
        while b < b1:
            pb1 = min(b1, b + phrase)
            if b1 - pb1 < 4:
                pb1 = b1
            w = dict(MODE_W[lab])
            if d >= 7:
                w['wave'] = w.get('wave', 0) + 1
                w['spider'] = w.get('spider', 0) + 0.5
            if prev_mode in w and len(w) > 1:
                w[prev_mode] = 0
            mode = _pick(rng, w)
            pats = [p for p in PATTERNS[mode] if (mode, p) not in hist[-3:]] or PATTERNS[mode]
            pat = rng.choice(pats)
            if mode == 'wave' and lab == 'drop' and d >= 6 and rng.random() < 0.5:
                pat = 'spam'
            # скорость
            sp_opts = {'calm': [0.5, 1], 'intro': [1], 'outro': [1], 'build': [1, 2], 'drop': [2, 3, 4]}[lab]
            sp_opts = [v for v in sp_opts if v <= MAX_SPEED[d]] or [1]
            mini = allow_mini and mode == 'wave' and rng.random() < [0, 0, 0, .1, .15, .25, .3, .35, .4, .45, .5][d]
            prm = {'pattern': pat}
            if mode == 'wave':
                prm.update(style=pat, m=round(WAVE_M[d] * k_focus, 1), q=CLICK_Q[d])
                if lab == 'drop' and d >= 5 and rng.random() < 0.2:
                    prm['flip'] = True
                if lab == 'build' and pat != 'spam':
                    prm['cresc'] = True        # смены направления всё чаще к концу фразы
                if lab == 'drop' and d >= 5 and rng.random() < 0.5:
                    prm['squeeze'] = True      # кульминация фразы — коридор уже
            elif mode in ('ship', 'ufo'):
                prm.update(m=round(SHIP_M[d] * k_focus, 1), q=CLICK_Q[d], band='drums' if mode == 'ship' else 'low')
                if pat == 'tunnel' and (d >= 8 or focus == 'Difficulty'):
                    prm['spikes'] = True
            elif mode == 'cube':
                prm.update(w=round(WINDOW[d] * k_focus, 3), band='low', q=CLICK_Q[d], m=round(SHIP_M[d] * k_focus, 1))
                if pat == 'jumps':
                    prm['orbs'] = rng.choice([['yellow'], ['yellow', 'pink'], ['pink', 'red'], ['yellow', 'red', 'pink']])
                    if rng.random() < 0.5:
                        prm['pads'] = rng.choice([['pink'], ['yellow'], ['pink', 'yellow']])
            elif mode == 'spider':
                prm.update(w=round(WINDOW[d] * k_focus, 3), q=CLICK_Q[d], mingap=1 if d >= 7 else 2)
            elif mode == 'ball':
                prm.update(w=round(WINDOW[d] * k_focus, 3), band='low')
            # смена скорости как приём: фраза дропа делится на куски с разной скоростью (GRIEF)
            split = mode in ('wave', 'ship') and lab == 'drop' and d >= 6 and pb1 - b >= 8 and rng.random() < 0.6
            pieces = []
            if split:
                n = 2 if pb1 - b < 12 else rng.choice([2, 3, 4])
                cuts = [b + (pb1 - b) * i // n for i in range(n)] + [pb1]
                cuts = sorted(set(c // 2 * 2 for c in cuts[:-1])) + [pb1]
                last = None
                for a_, z_ in zip(cuts, cuts[1:]):
                    if z_ - a_ < 2:
                        continue
                    opts = [v for v in sp_opts + [1] if v != last] or sp_opts
                    last = rng.choice(opts)
                    pieces.append((a_, z_, last))
            else:
                pieces.append((b, pb1, rng.choice(sp_opts)))
            for a_, z_, spd in pieces:
                plan.append([None if not plan else a_, z_, mode, spd, mini, dict(prm)])
                labels.append('%s: %s %sx%s%s' % (lab, mode, spd, ' mini' if mini else '',
                                                   ' ' + pat if pat not in ('lanes',) else ''))
            hist.append((mode, pat))
            prev_mode = mode
            b = pb1
    if not plan:
        raise ValueError('song too short for a plan')
    # первый раздел — с начала уровня; конец — по последнему разделу
    plan[0][0] = None
    return {'plan': [tuple(p) for p in plan], 'labels': labels, 'end_beat': plan[-1][1],
            'difficulty': difficulty, 'focus': focus, 'seed': seed}


if __name__ == '__main__':
    import sys, json, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from music import analyze
    m = analyze(sys.argv[1], bpm=float(sys.argv[3]) if len(sys.argv) > 3 else None)
    p = make_plan(m, sys.argv[2] if len(sys.argv) > 2 else 'Hard Demon', 'Balanced')
    for (b0, b1, mode, spd, mini, prm), lab in zip(p['plan'], p['labels']):
        print('%5s-%4d  %-34s %s' % (b0, b1, lab, {k: v for k, v in prm.items() if k != 'pattern'}))
