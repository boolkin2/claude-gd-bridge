# Управление редактором GD через мост claude.bridge (без скриншотов).
#   from gdedit import Editor; from gdobjects import obj, block, spike, portal
#   ed = Editor(); ed.open('MY LEVEL', song_id=1029814)
#   uids = ed.add([block(15, 15), spike(45), portal('wave', 300)], label='intro')
#   ed.list(x0=0, x1=600); ed.modify(uids=uids[:1], set={'rot': 90}); ed.undo(); ed.save()
# CLI: python -P gdedit.py <cmd> '<json>'   (то же, что bridge.py, с короткими именами)
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B
from gdobjects import KEYS


def _key(k):
    if isinstance(k, int):
        return str(k)
    if k.isdigit():
        return k
    return str(KEYS[k])


class Editor:
    CHUNK = 4000  # объектов на одну команду editor_add

    def call(self, cmd, **kw):
        return B.call(cmd, **kw)

    # --- уровень и сцена ---------------------------------------------------------------------
    def open(self, name, create=True, song_id=None, reopen=False, save_current=True):
        kw = dict(name=name, create=create, reopen=reopen, save_current=save_current, timeout=60)
        if song_id:
            kw['song_id'] = int(song_id)
        return self.call('editor_open', **kw)

    def exit(self, save=True):
        return self.call('editor_exit', save=save, timeout=60)

    def save(self, disk=True):
        return self.call('editor_save', disk=disk)

    def info(self):
        return self.call('editor_info')

    def settings(self, **set_):
        """settings() — прочитать; settings(start_mode=4, start_speed=2, song_offset=1.2) — задать."""
        return self.call('editor_settings', **({'set': set_} if set_ else {}))

    def string(self):
        return self.call('editor_string')['level_string']

    def playtest(self, action='start'):
        return self.call('editor_playtest', action=action)

    # --- объекты -------------------------------------------------------------------------------
    def add(self, objs, label='add', select=False, undo=False):
        """objs: список строк объектов (gdobjects.obj/...) или одна строка «a;b;c». -> uid."""
        if isinstance(objs, str):
            objs = [o for o in objs.split(';') if o]
        uids = []
        for i in range(0, len(objs), self.CHUNK):
            part = objs[i:i + self.CHUNK]
            r = self.call('editor_add', objects=';'.join(part), label=label, select=select, undo=undo)
            uids += r.get('uids', [])
        return uids

    def list(self, full=False, limit=5000, **flt):
        return self.call('editor_list', full=full, limit=limit, **flt)

    def remove(self, label='remove', **flt):
        return self.call('editor_remove', label=label, **flt)

    def clear(self):
        return self.call('editor_remove', all=True, label='clear')

    def modify(self, set=None, unset=None, dx=0.0, dy=0.0, label='modify', **flt):
        """set={'rot': 90, 'groups': [3]} (имена из KEYS или номера ключей); unset=['sx']."""
        s = {}
        for k, v in (set or {}).items():
            if isinstance(v, (list, tuple)):
                v = '.'.join(str(int(g)) for g in v)
            elif isinstance(v, bool):
                v = 1 if v else 0
            s[_key(k)] = v
        u = [_key(k) for k in (unset or [])]
        return self.call('editor_modify', set=s, unset=u, dx=dx, dy=dy, label=label, **flt)

    def undo(self, steps=1):
        return self.call('editor_undo', steps=steps)

    def history(self):
        return self.call('editor_history')['history']

    def select(self, add=False, **flt):
        return self.call('editor_select', add=add, **flt)

    def selected(self, full=True):
        return self.call('editor_selected', full=full)['objects']

    def view(self, x=None, y=None, zoom=None):
        kw = {k: v for k, v in (('x', x), ('y', y), ('zoom', zoom)) if v is not None}
        return self.call('editor_view', **kw)

    # --- справка об объектах и чужие уровни ------------------------------------------------------
    def catalog(self):
        return self.call('object_catalog')['objects']

    def probe(self, ids):
        return self.call('object_probe', ids=list(ids))['objects']

    def levels(self, source='saved'):
        return self.call('level_list', source=source)['levels']

    def export(self, **which):
        """export(id=149992717) | export(name='MY LEVEL') | export() — текущий (игра/редактор/страница
        уровня). -> dict с level_string (сжатым, как в сохранении) и метаданными."""
        return self.call('level_export', **which)


    # --- интерфейс в игре: заявка «новый уровень», статус и сообщения игроку ----------------------
    def request(self):
        """Заявка из окна «New level for Claude» (имя, song_id, song_file, difficulty, focus,
        focus_asked, notes, status) или None."""
        return self.call('request_get')['request']

    def request_status(self, status, message=''):
        """status: accepted | building | done | cancelled — видно в панели Claude в игре."""
        return self.call('request_status', status=status, message=message)

    def status(self, text, progress=None):
        """Строка «AI: …» в панели (русский текст игра покажет транслитом)."""
        kw = {'text': text}
        if progress is not None:
            kw['progress'] = float(progress)
        return self.call('ui_status', **kw)

    def notify(self, text, icon='info', time=3.0):
        """Всплывающее сообщение в игре: icon info|success|warning|error|loading."""
        return self.call('ui_notify', text=text, icon=icon, time=time)


def props_dict(props):
    """'1,8,2,45,3,15' -> {1: '8', 2: '45', 3: '15'}"""
    p = props.split(',')
    return {int(p[i]): p[i + 1] for i in range(0, len(p) - 1, 2)}


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'editor_info'
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    if not cmd.startswith(('editor_', 'object_', 'level_', 'request_', 'ui_', 'run_')) and             cmd not in ('ping', 'log', 'commands'):
        cmd = 'editor_' + cmd
    print(json.dumps(B.call(cmd, **args), ensure_ascii=False))
