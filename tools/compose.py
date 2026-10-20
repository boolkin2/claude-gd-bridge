# Уровень по заявке одной командой: заявка -> музыка -> план -> генерация с самопроверкой ->
# объекты в редактор GD разделами (с подписями, камера на месте стройки, прогресс в панели) ->
# сохранение -> проверка ботом. План можно выгрузить, отредактировать (идеи Claude) и подать обратно.
#   python -P compose.py --request bridge --plan-out out/auto/plan.json           (только план)
#   python -P compose.py --request bridge --plan-in out/auto/plan.json --editor --verify
#   python -P compose.py --name "MY LEVEL" --song-id 1029814 --bpm 217 --difficulty "Hard Demon" --editor
import sys, os, json, shutil, argparse, time, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B
import music as M
import plan_auto

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
AI_LEVELS = os.path.join(ROOT, 'out', 'compose', 'ai_levels.json')
START_MODE = {'cube': 0, 'ship': 1, 'ball': 2, 'ufo': 3, 'wave': 4, 'robot': 5, 'spider': 6, 'swing': 7}


USE_REQUEST = False   # статус заявки трогаем только при --request bridge


def status(text, progress=None, req_status=None, quiet=False):
    print('[compose]', text, flush=True)
    if quiet:
        return
    try:
        kw = {'text': text}
        if progress is not None:
            kw['progress'] = progress
        B.call('ui_status', **kw)
        if req_status and USE_REQUEST:
            B.call('request_status', status=req_status, message=text[:120])
    except Exception:
        pass


def prepare_song(song_id, song_file):
    """Песня-файл из заявки -> поверх %LOCALAPPDATA%\\GeometryDash\\<id>.mp3 (оригинал -> .orig)."""
    dst = os.path.join(os.environ['LOCALAPPDATA'], 'GeometryDash', '%d.mp3' % song_id)
    if song_file:
        if not os.path.exists(song_file):
            raise FileNotFoundError('song file not found: %s' % song_file)
        if os.path.exists(dst) and not os.path.exists(dst + '.orig'):
            shutil.copy2(dst, dst + '.orig')
        shutil.copy2(song_file, dst)
    if not os.path.exists(dst):
        raise FileNotFoundError('song %d is not downloaded in GD (%s)' % (song_id, dst))
    return dst


def relax(prm):
    """Ослабить раздел после провала самопроверки: шире запасы и окна, меньше кликов."""
    for k, d in (('m', 4.0), ('w', 0.01)):
        if k in prm:
            prm[k] = round(prm[k] + d, 3)
    if 'q' in prm:
        prm['q'] = round(min(0.95, prm['q'] + 0.07), 3)
    prm.pop('spikes', None)


def generate(plan, mus, song_id, name, tries=4):
    import gen_layout as G
    for attempt in range(tries):
        G.configure([tuple(p) for p in plan['plan']], plan['end_beat'], mus, song_id, name)
        with contextlib.redirect_stdout(io.StringIO()):
            G.build()
        probs = G.self_check()
        if not probs:
            return G, []
        bad = {p[0] for p in probs}
        status('self-check: sections %s too tight, relaxing (try %d)' % (sorted(bad), attempt + 1), quiet=True)
        for i in bad:
            relax(plan['plan'][i][5])
    return G, probs


def ai_levels():
    return json.load(open(AI_LEVELS, encoding='utf-8')) if os.path.exists(AI_LEVELS) else []


def mark_ai(name):
    """Запомнить, что уровень создан ИИ (его можно очищать и пересобирать без вопросов)."""
    ai = ai_levels()
    if name not in ai:
        ai.append(name)
        os.makedirs(os.path.dirname(AI_LEVELS), exist_ok=True)
        json.dump(ai, open(AI_LEVELS, 'w', encoding='utf-8'), ensure_ascii=False)


def place_in_editor(G, plan, name, song_id, quiet):
    existed = name in [l['name'] for l in B.call('level_list', source='local')['levels']]
    if existed and name not in ai_levels():
        raise RuntimeError('level "%s" exists and was not made by AI - choose another name' % name)
    mark_ai(name)
    r = B.call('editor_open', name=name, song_id=song_id, create=True, timeout=60)
    if r.get('objects', 0):
        B.call('editor_remove', all=True, label='clear before rebuild')
    s0 = G.SECS[0]
    B.call('editor_settings', set={'start_mode': START_MODE[s0['mode']], 'start_speed': s0['speed'],
                                   'start_mini': bool(s0['mini']), 'song_id': song_id})
    objs = G.C.lv.objs
    n = len(G.SECS)
    for i, s in enumerate(G.SECS):
        a, b = s.get('obj_range', (0, 0))
        if b <= a:
            continue
        lab = 'section %d: %s' % (i + 1, plan['labels'][i] if i < len(plan['labels']) else s['mode'])
        B.call('editor_view', x=s['x0'] + 250, y=120, zoom=0.6)
        B.call('editor_add', objects=';'.join(objs[a:b]), label=lab, return_uids=False)
        status('building %d/%d: %s' % (i + 1, n, plan['labels'][i] if i < len(plan['labels']) else ''),
               progress=(i + 1) / n, quiet=quiet)
    tail = objs[G.SECS[-1].get('obj_range', (0, len(objs)))[1]:]
    if tail:
        B.call('editor_add', objects=';'.join(tail), label='end', return_uids=False)
    B.call('editor_save')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--request', help="'bridge' — заявка из игры, или путь к JSON заявки")
    ap.add_argument('--name')
    ap.add_argument('--song-id', type=int)
    ap.add_argument('--song-file')
    ap.add_argument('--bpm', type=float)
    ap.add_argument('--difficulty')
    ap.add_argument('--focus')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--max-len', type=float, default=300.0)
    ap.add_argument('--plan-in')
    ap.add_argument('--plan-out')
    ap.add_argument('--editor', action='store_true', help='поставить объекты в редактор GD')
    ap.add_argument('--verify', action='store_true', help='проверить ботом (speed 1)')
    ap.add_argument('--quiet', action='store_true', help='не писать статус в игру')
    a = ap.parse_args()
    rq = {}
    global USE_REQUEST
    USE_REQUEST = a.request == 'bridge'
    if a.request == 'bridge':
        rq = B.call('request_get')['request'] or {}
    elif a.request:
        rq = json.load(open(a.request, encoding='utf-8'))
    name = a.name or rq.get('name') or 'AI LEVEL'
    song_id = a.song_id or int(rq.get('song_id') or 0) or 1029814
    difficulty = a.difficulty or rq.get('difficulty') or 'Hard'
    focus = a.focus or rq.get('focus') or ('Beauty' if difficulty not in ('Hard Demon', 'Insane Demon', 'Extreme Demon') else 'Balanced')
    out_dir = os.path.join(ROOT, 'out', 'compose', ''.join(c if c.isalnum() else '_' for c in name))
    os.makedirs(out_dir, exist_ok=True)

    status('analyzing music', 0.02, 'building' if a.request == 'bridge' else None, a.quiet)
    path = prepare_song(song_id, a.song_file or rq.get('song_file') or None)
    mus = M.analyze(path, key=str(song_id), bpm=a.bpm or rq.get('bpm'))
    if a.plan_in:
        plan = json.load(open(a.plan_in, encoding='utf-8'))
    else:
        plan = plan_auto.make_plan(mus, difficulty, focus, seed=a.seed, max_len=a.max_len)
    plan['plan'] = [list(p) for p in plan['plan']]
    if a.plan_out:
        json.dump(plan, open(a.plan_out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('plan ->', a.plan_out, '(%d sections)' % len(plan['plan']))
        if not (a.editor or a.verify):
            return 0

    status('generating %d sections' % len(plan['plan']), 0.05, quiet=a.quiet)
    G, probs = generate(plan, mus, song_id, name)
    from gdlevel import write_gdlvl
    write_gdlvl(os.path.join(out_dir, 'level.gdlvl'), name, G.C.lv.string(), song_id)
    ticks = sorted([[G.tick_of(t), d] for t, d in G.C.inputs])
    json.dump({'ticks': ticks, 'end_tick': G.tick_of(G.T_END)}, open(os.path.join(out_dir, 'inputs.json'), 'w'))
    json.dump(plan, open(os.path.join(out_dir, 'plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('generated: %d objects, %d inputs, %.1f s, self-check %s' % (
        len(G.C.lv.objs), len(ticks), G.T_END, probs or 'ok'))

    if a.editor:
        status('placing objects in the editor', 0.1, quiet=a.quiet)
        place_in_editor(G, plan, name, song_id, a.quiet)
    if a.verify:
        status('verifying with the bot', 0.95, quiet=a.quiet)
        if a.editor:
            B.call('editor_exit', save=True, timeout=60)
        else:
            existed = name in [l['name'] for l in B.call('level_list', source='local')['levels']]
            if existed and name not in ai_levels():
                raise RuntimeError('level "%s" exists and was not made by AI - choose another name' % name)
            mark_ai(name)
            B.load_level(path=os.path.join(out_dir, 'level.gdlvl'), name=name)
        r = B.play(name, ticks, max_ticks=G.tick_of(G.T_END) + 480, speed=1, sample=0, timeout=900)
        res = r['result']
        msg = 'bot: %s at %.1f s' % (res, r['ticks'] / 240.0)
        if r.get('death'):
            x = r['death']['x']
            sec = next((i for i, s in enumerate(G.SECS) if s['x0'] <= x < s['x1']), -1)
            msg += ' (section %d: %s)' % (sec + 1, plan['labels'][sec] if 0 <= sec < len(plan['labels']) else '?')
        print(msg)
        status(msg, 1.0, 'done' if res == 'finished' else 'error', a.quiet)
        json.dump({'result': res, 'ticks': r['ticks'], 'death': r.get('death')},
                  open(os.path.join(out_dir, 'verify.json'), 'w'))
    elif a.editor:
        status('level placed in the editor (not verified)', 1.0, 'done', a.quiet)
    return 0


if __name__ == '__main__':
    sys.exit(main())
