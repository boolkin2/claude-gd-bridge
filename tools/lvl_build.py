# Поставить уровень, собранный скриптом ИИ на lvlkit, в редактор GD (частями, с подписями — игрок
# видит стройку), сохранить и закрыть редактор (чтобы бот мог открыть уровень).
#   python -P tools/lvl_build.py out/auto/level.py      — выполнить скрипт (он зовёт L.save()) и поставить
#   python -P tools/lvl_build.py --saved "<имя>"        — поставить уже сохранённый out/levels/<имя>/
#   --no-editor — только выполнить скрипт и сохранить файлы
# Уровень с таким именем, сделанный не ИИ, не трогает (список ИИ-уровней — out/compose/ai_levels.json).
import argparse, json, os, runpy, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bridge as B

AI_LEVELS = os.path.join(ROOT, 'out', 'compose', 'ai_levels.json')
START_MODE = {'cube': 0, 'ship': 1, 'ball': 2, 'ufo': 3, 'wave': 4, 'robot': 5, 'spider': 6, 'swing': 7}


def status(text, progress=None):
    try:
        kw = {'text': text}
        if progress is not None:
            kw['progress'] = progress
        B.call('ui_status', **kw)
    except Exception:
        pass
    print(text, flush=True)


def ai_levels():
    return json.load(open(AI_LEVELS, encoding='utf-8')) if os.path.exists(AI_LEVELS) else []


def mark_ai(name):
    ai = ai_levels()
    if name not in ai:
        ai.append(name)
        os.makedirs(os.path.dirname(AI_LEVELS), exist_ok=True)
        json.dump(ai, open(AI_LEVELS, 'w', encoding='utf-8'), ensure_ascii=False)


def place(data):
    name, song = data['name'], int(data['song_id'])
    try:      # ping в одной сессии GD залипал (19.10) — не зависеть от него
        in_play = B.call('ping', timeout=5).get('scene') == 'play'
    except Exception:
        in_play = False
    if in_play:
        B.call('exit')
        time.sleep(1.5)
    existed = name in [l['name'] for l in B.call('level_list', source='local')['levels']]
    if existed and name not in ai_levels():
        raise SystemExit('level "%s" exists and was not made by AI - choose another name' % name)
    mark_ai(name)
    B.call('editor_open', name=name, song_id=song, create=True, timeout=90)
    # редактор подгружает объекты уровня не сразу: число сразу после открытия бывало 0, очистка
    # пропускалась, и старые объекты прошлой стройки оставались (бот бился о старые шипы, 19.10)
    n, same = -1, 0
    for _ in range(40):
        time.sleep(0.25)
        m = B.call('editor_info').get('objects', 0)
        same = same + 1 if m == n else 0
        n = m
        if same >= 4:
            break
    for _ in range(3):
        if n == 0:
            break
        B.call('editor_remove', all=True, label='clear before rebuild', timeout=120)
        time.sleep(0.5)
        n = B.call('editor_info').get('objects', 0)
    if n:
        raise SystemExit('could not clear the editor level (%d objects left)' % n)
    st = data['start']
    B.call('editor_settings', set={'start_mode': START_MODE[st['mode']], 'start_speed': st['speed'],
                                   'start_mini': bool(st['mini']), 'song_id': song,
                                   'song_offset': float(data.get('song_offset', 0.0))})
    objs = data['objects']
    parts = data['parts'] or [{'name': 'level', 't0': 0, 'first': 0}]
    # объекты до первой части (порталы L.change, конец L.end, объявленные раньше) — тоже в первую часть
    bounds = [0] + [p['first'] for p in parts[1:]] + [len(objs)]
    n = len(parts)
    for i, p in enumerate(parts):
        chunk = objs[bounds[i]:bounds[i + 1]]
        if not chunk:
            continue
        # большие части — кусками по 1500 объектов
        for j in range(0, len(chunk), 1500):
            sub = chunk[j:j + 1500]
            try:
                x = float(sub[0].split(',')[3])
                B.call('editor_view', x=x + 300, y=120, zoom=0.5)
            except Exception:
                pass
            B.call('editor_add', objects=';'.join(sub), label='%s (%d/%d)' % (p['name'], i + 1, n),
                   return_uids=False, timeout=120)
        status('building %d/%d: %s' % (i + 1, n, p['name']), (i + 1) / n)
    total = B.call('editor_info').get('objects', 0)
    if total != len(objs):
        print('WARNING: editor has %d objects, level has %d' % (total, len(objs)), flush=True)
    B.call('editor_save')
    B.call('editor_exit', save=True, timeout=90)
    status('level placed in the editor: %d objects' % len(objs), 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script', nargs='?')
    ap.add_argument('--saved')
    ap.add_argument('--no-editor', action='store_true')
    a = ap.parse_args()
    if a.script:
        import lvlkit
        a.script = os.path.abspath(a.script)
        os.chdir(ROOT)
        before = time.time()
        runpy.run_path(a.script, run_name='__main__')
        # последний сохранённый уровень — самый свежий level.json
        base = os.path.join(ROOT, 'out', 'levels')
        cands = [os.path.join(base, d, 'level.json') for d in os.listdir(base)]
        cands = [c for c in cands if os.path.exists(c) and os.path.getmtime(c) >= before - 1]
        if not cands:
            raise SystemExit('the script did not call L.save()')
        path = max(cands, key=os.path.getmtime)
    else:
        path = os.path.join(ROOT, 'out', 'levels', ''.join(c if c.isalnum() else '_' for c in a.saved), 'level.json')
    data = json.load(open(path, encoding='utf-8'))
    if not a.no_editor:
        place(data)
    print('ok: %s, %d objects' % (data['name'], len(data['objects'])))


if __name__ == '__main__':
    main()
