# Клиент мода claude.bridge (TCP 127.0.0.1:47800, строка JSON -> строка JSON). См. mod/SPEC.md.
#   python -P bridge.py ping
#   python -P bridge.py load_level '{"path": "out/retina_layout.gdlvl", "name": "RETINA BRIDGE"}'
#   python -P bridge.py play '{"name": "RETINA BRIDGE", "inputs_file": "out/retina_inputs.json", "speed": 4}'
#   python -P bridge.py hitbox '{"ids": [1, 8, 211]}'
#   python -P bridge.py exit
import base64, gzip, json, os, re, socket, sys, zlib

HOST, PORT = '127.0.0.1', 47800
TPS = 240  # тиков физики в секунду
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _send(req, timeout):
    with socket.create_connection((HOST, PORT), timeout=10) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps(req, separators=(',', ':')) + '\n').encode('utf-8'))
        buf = b''
        while not buf.endswith(b'\n'):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode('utf-8'))


def call(cmd, **args):
    """Отправить команду мосту. Ошибка моста -> RuntimeError."""
    req = dict(args, cmd=cmd)
    wait = float(req.get('timeout', 1800 if cmd == 'play' else 60)) + 15
    r = _send(req, wait)
    if not r.get('ok'):
        raise RuntimeError('bridge %s: %s' % (cmd, r.get('error')))
    return r


def read_gdlvl(path):
    """.gdlvl -> (имя k2, сжатая строка уровня k4, песня k45)."""
    s = open(path, 'r').read().strip()
    s += '=' * (-len(s) % 4)
    data = base64.urlsafe_b64decode(s)
    try:
        xml = gzip.decompress(data).decode('utf-8')
    except Exception:
        xml = zlib.decompress(data[10:], -zlib.MAX_WBITS).decode('utf-8')

    def key(k):
        m = re.search(r'<k>%s</k><[si]>([^<]*)</[si]>' % k, xml)
        return m.group(1) if m else None
    return key('k2'), key('k4'), int(key('k45') or 0)


def load_level(path=None, name=None, level_string=None, song_id=None, raw=None):
    """Загрузить уровень: из .gdlvl, сжатой строки (k4) или сырой строки уровня (raw)."""
    if raw is not None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from gdsave import encode_level_string
        level_string = encode_level_string(raw)
    if path:
        n, k4, song = read_gdlvl(path)
        name = name or n
        level_string = level_string or k4
        song_id = song_id or song
    return call('load_level', name=name, level_string=level_string, song_id=int(song_id or 0))


def ticks_from_seconds(inputs, lead=0):
    """[[t_сек, 1|0], ...] -> [[tick, 1|0], ...], tick = round(t·240) - lead.
    lead=1 компенсирует задержку игры: нажатие на тике N меняет y только с тика N+1,
    а модель генератора (physics.py) двигает игрока в том же шаге."""
    return [[max(0, int(round(t * TPS)) - lead), int(d)] for t, d in inputs]


def load_inputs(path, lead=0):
    """Расписание бота: поле ticks (генератор, точные тики) или inputs в секундах."""
    j = json.load(open(path))
    if isinstance(j, dict) and 'ticks' in j and not lead:
        return [[int(k), int(d)] for k, d in j['ticks']]
    inp = j['inputs'] if isinstance(j, dict) else j
    return ticks_from_seconds(inp, lead)


def play(name, inputs=(), max_ticks=None, speed=1.0, sample=24, quit=True, timeout=1800):
    """Прогон уровня. Ответ: result dead|finished|timeout, ticks, death{...}, states (списки state_fields)."""
    args = dict(name=name, inputs=list(inputs), speed=speed, sample=sample, quit=quit, timeout=timeout)
    if max_ticks:
        args['max_ticks'] = int(max_ticks)
    r = call('play', **args)
    f = r.get('state_fields', [])
    r['states'] = [dict(zip(f, s)) for s in r.get('states', [])]
    return r


def summary(r, n_states=3):
    """Короткая сводка ответа play для печати."""
    out = {k: v for k, v in r.items() if k not in ('states', 'state_fields', 'ok')}
    st = r.get('states', [])
    out['n_states'] = len(st)
    if st:
        out['last_states'] = st[-n_states:]
    return out


def _resolve(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def main(argv):
    if len(argv) < 2:
        print(__doc__ or 'usage: bridge.py <cmd> [json]')
        return 2
    cmd = argv[1]
    args = json.loads(argv[2]) if len(argv) > 2 else {}
    full = args.pop('full', False)
    if cmd == 'load_level' and 'path' in args:
        r = load_level(path=_resolve(args['path']), name=args.get('name'), song_id=args.get('song_id'))
    elif cmd == 'play':
        if 'inputs_file' in args:
            args['inputs'] = load_inputs(_resolve(args.pop('inputs_file')))
        out_file = args.pop('out', None)
        r = play(**args)
        if out_file:
            json.dump(r, open(_resolve(out_file), 'w'))
        if not full:
            r = summary(r)
    else:
        r = call(cmd, **args)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
