# Сборка строки уровня GD 2.2 и вставка уровня в CCLocalLevels.dat.
import re, os, sys, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdsave import decode_save, encode_save, encode_level_string

def color(ch, r, g, b, blend=0, opacity=1):
    s = '1_%d_2_%d_3_%d_11_255_12_255_13_255_4_-1_6_%d_7_%g_15_1_18_0_8_1' % (r, g, b, ch, opacity)
    return s + ('_5_1' if blend else '')

class Level:
    def __init__(self, mode=0, mini=0, speed=0, colors=None, song_offset=0.0, bg=0, ground=0):
        self.objs = []
        self.mode, self.mini, self.speed = mode, mini, speed
        self.colors = colors or [color(1000, 18, 18, 24), color(1001, 12, 12, 16), color(1002, 255, 255, 255),
                                 color(1004, 255, 255, 255), color(1009, 12, 12, 16)]
        self.song_offset = song_offset
        self.bg, self.ground = bg, ground

    def add(self, oid, x, y, **kw):
        # kw: rot, fx, fy, sx, sy, groups (list), layer (editor layer), z, color (main channel)
        p = [1, oid, 2, round(x, 3), 3, round(y, 3)]
        if kw.get('fx'): p += [4, 1]
        if kw.get('fy'): p += [5, 1]
        if kw.get('rot'): p += [6, round(kw['rot'], 3)]
        if kw.get('layer'): p += [20, kw['layer']]
        if kw.get('color') is not None: p += [21, kw['color']]
        if kw.get('z') is not None: p += [24, kw['z']]
        if kw.get('groups'): p += [57, '.'.join(str(g) for g in kw['groups'])]
        sx, sy = kw.get('sx', 1), kw.get('sy', 1)
        if sx != 1: p += [128, round(sx, 4)]
        if sy != 1: p += [129, round(sy, 4)]
        for k, v in kw.get('extra', {}).items():
            p += [k, v]
        self.objs.append(','.join(str(v) for v in p))

    def header(self):
        kv = [('kS38', '|'.join(self.colors) + '|'), ('kA13', '%g' % self.song_offset), ('kA15', 0), ('kA16', 0),
              ('kA14', ''), ('kA6', self.bg), ('kA7', self.ground), ('kA25', 0), ('kA17', 0), ('kA18', 0),
              ('kS39', 0), ('kA2', self.mode), ('kA3', self.mini), ('kA8', 0), ('kA4', self.speed),
              ('kA9', 0), ('kA10', 0), ('kA22', 0), ('kA23', 0), ('kA24', 0), ('kA27', 1), ('kA40', 1),
              ('kA41', 1), ('kA42', 1), ('kA28', 0), ('kA29', 0), ('kA31', 1), ('kA32', 1), ('kA36', 0),
              ('kA43', 0), ('kA44', 0), ('kA45', 1), ('kA46', 0), ('kA47', 0), ('kA33', 1), ('kA34', 1),
              ('kA35', 0), ('kA37', 1), ('kA38', 1), ('kA39', 1), ('kA19', 0), ('kA26', 0), ('kA20', 0),
              ('kA21', 0), ('kA11', 0)]
        return ','.join('%s,%s' % (k, v) for k, v in kv)

    def string(self):
        return self.header() + ';' + ';'.join(self.objs) + ';'

def level_dict_xml(name, level_str, song_id, creator, desc='', seconds=0):
    k4 = encode_level_string(level_str)
    k3 = base64.urlsafe_b64encode(desc.encode()).decode() if desc else ''
    parts = ['<k>kCEK</k><i>4</i>', '<k>k2</k><s>%s</s>' % name]
    if k3:
        parts.append('<k>k3</k><s>%s</s>' % k3)
    parts += ['<k>k4</k><s>%s</s>' % k4, '<k>k5</k><s>%s</s>' % creator,
              '<k>k13</k><t />', '<k>k21</k><i>2</i>', '<k>k16</k><i>1</i>',
              '<k>k80</k><i>%d</i>' % seconds, '<k>k50</k><i>47</i>', '<k>k47</k><t />',
              '<k>k45</k><i>%d</i>' % song_id, '<k>k104</k><s>%d</s>' % song_id,
              '<k>kI1</k><r>0</r>', '<k>kI2</k><r>100</r>', '<k>kI3</k><r>0.5</r>']
    return '<d>' + ''.join(parts) + '</d>'

def write_gdlvl(path, name, level_str, song_id, desc=''):
    """Файл .gdlvl (экспорт/импорт GD 2.209): gzip+base64 от plist со словарём уровня."""
    k4 = encode_level_string(level_str)
    n_obj = level_str.count(';') - 1
    parts = ['<k>kCEK</k><i>4</i>', '<k>k23</k><i>1</i>', '<k>k2</k><s>%s</s>' % name]
    if desc:
        parts.append('<k>k3</k><s>%s</s>' % base64.urlsafe_b64encode(desc.encode()).decode())
    parts += ['<k>k4</k><s>%s</s>' % k4, '<k>k13</k><t />', '<k>k21</k><i>2</i>',
              '<k>k45</k><i>%d</i>' % song_id, '<k>k50</k><i>51</i>', '<k>k48</k><i>%d</i>' % n_obj,
              '<k>kI1</k><r>0</r>', '<k>kI2</k><r>100</r>', '<k>kI3</k><r>0.5</r>']
    xml = '<?xml version="1.0"?><plist version="1.0" gjver="2.0"><dict>' + ''.join(parts) + '</dict></plist>'
    open(path, 'w').write(encode_level_string(xml))

def inject(save_path, name, level_str, song_id, creator, desc='', seconds=0):
    xml = decode_save(save_path).decode('utf-8')
    m = re.search(r'<k>LLM_01</k><d>(.*?)</d><k>LLM_02</k>', xml, re.S)
    assert m, 'LLM_01 not found'
    body = m.group(1)
    # разобрать существующие k_N (вложенные <d> есть — режем по ключам верхнего уровня)
    entries = []
    pos = body.find('<k>k_')
    head = body[:pos] if pos >= 0 else body
    rest = body[pos:] if pos >= 0 else ''
    while rest:
        mm = re.match(r'<k>k_(\d+)</k>', rest)
        assert mm
        rest = rest[mm.end():]
        # найти конец <d>...</d> с учётом вложенности
        depth = 0; i = 0
        while True:
            if rest.startswith('<d>', i): depth += 1; i += 3
            elif rest.startswith('</d>', i):
                depth -= 1; i += 4
                if depth == 0: break
            elif rest.startswith('<d />', i) and depth == 0: i += 5; break
            else: i += 1
        entries.append(rest[:i]); rest = rest[i:]
    # убрать прежнюю версию нашего уровня (по имени)
    entries = [e for e in entries if '<k>k2</k><s>%s</s>' % name not in e]
    entries.insert(0, level_dict_xml(name, level_str, song_id, creator, desc, seconds))
    new_body = head + ''.join('<k>k_%d</k>%s' % (i, e) for i, e in enumerate(entries))
    xml2 = xml[:m.start(1)] + new_body + xml[m.end(1):]
    open(save_path, 'wb').write(encode_save(xml2.encode('utf-8')))
    return len(entries)
