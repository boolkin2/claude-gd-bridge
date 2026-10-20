# Справочник объектов GD 2.2 для сборки уровней через мост (claude.bridge, команды editor_*).
# Объект = строка свойств «ключ,значение,...» как в сохранении уровня. Координаты: x — вправо
# (блок 30 ед., центры блоков на 15 + 30k), y — вверх от земли (y = 15 — блок на земле).
# Пометка (?) — ключ/ID по памяти, сверить командой object_probe или editor_selected на примере.

# --- ключи свойств --------------------------------------------------------------------------------
KEYS = {
    'id': 1, 'x': 2, 'y': 3, 'fx': 4, 'fy': 5, 'rot': 6,
    'red': 7, 'green': 8, 'blue': 9, 'duration': 10, 'touch': 11,
    'tint_ground': 14, 'p1': 15, 'p2': 16, 'blending': 17,
    'layer': 20, 'color': 21, 'color2': 22, 'target_color': 23, 'z': 24, 'zorder': 25,
    'move_x': 28, 'move_y': 29, 'easing': 30, 'text': 31, 'scale': 32, 'opacity': 35,
    'hsv_on': 41, 'hsv2_on': 42, 'hsv': 43, 'hsv2': 44,
    'fade_in': 45, 'hold': 46, 'fade_out': 47, 'pulse_mode': 48, 'copy_hsv': 49, 'copy_color': 50,
    'target': 51, 'pulse_target_type': 52, 'tp_offset': 54, 'activate': 56, 'groups': 57,
    'lock_x': 58, 'lock_y': 59, 'copy_opacity': 60, 'layer2': 61, 'spawn': 62, 'spawn_delay': 63,
    'dont_fade': 64, 'main_only': 65, 'detail_only': 66, 'dont_enter': 67,
    'degrees': 68, 'times360': 69, 'lock_rot': 70, 'center': 71, 'x_mod': 72, 'y_mod': 73,
    'strength': 75, 'anim_id': 76, 'count': 77, 'subtract': 78, 'pickup_mode': 79, 'item': 80,
    'hold_mode': 81, 'toggle_mode': 82, 'interval': 84, 'easing_rate': 85, 'exclusive': 86,
    'multi': 87, 'comparison': 88, 'dual_mode': 89, 'follow_speed': 90, 'follow_delay': 91,
    'y_offset': 92, 'on_exit': 93, 'dynamic': 94, 'block_b': 95, 'no_glow': 96,
    'rot_speed': 97, 'no_rotation': 98, 'multi_activate': 99, 'use_target': 100,
    'target_axis': 101, 'editor_disable': 102, 'high_detail': 103, 'max_speed': 105,
    'random_start': 106, 'anim_speed': 107, 'linked': 108,
    'sx': 128, 'sy': 129, 'particles': 145,
}

# --- ID объектов ------------------------------------------------------------------------------------
ID = {
    # геймплей
    'block': 1, 'spike': 8, 'small_spike': 39, 'slope45': 289, 'slope22': 291,
    'decor_block': 211,            # НЕ твёрдый (проверено мостом)
    'start_pos': 31, 'end': 3600, 'collision_block': 1816, 'text': 914, 'particles': 2065,
    # порталы режима / размера / гравитации / прочие
    'cube': 12, 'ship': 13, 'ball': 47, 'ufo': 111, 'wave': 660, 'robot': 745, 'spider': 1331, 'swing': 1933,
    'mini': 101, 'big': 99, 'grav_down': 10, 'grav_up': 11, 'grav_toggle': 2926,
    'mirror': 45, 'unmirror': 46, 'dual': 286, 'single': 287, 'teleport': 747,
    # скорости
    'speed_05': 200, 'speed_1': 201, 'speed_2': 202, 'speed_3': 203, 'speed_4': 1334,
    # орбы и пады
    'orb_yellow': 36, 'orb_blue': 84, 'orb_pink': 141, 'orb_green': 1022, 'orb_black': 1330,
    'orb_red': 1333, 'orb_dash': 1704, 'orb_dash_pink': 1751, 'orb_spider': 3004, 'orb_teleport': 3027,
    'pad_yellow': 35, 'pad_blue': 67, 'pad_pink': 140, 'pad_red': 1332, 'pad_spider': 3005,
    # триггеры
    'trig_color': 899, 'trig_move': 901, 'trig_pulse': 1006, 'trig_alpha': 1007, 'trig_toggle': 1049,
    'trig_spawn': 1268, 'trig_rotate': 1346, 'trig_follow': 1347, 'trig_shake': 1520,
    'trig_animate': 1585, 'trig_touch': 1595, 'trig_count': 1611, 'trig_stop': 1616,
    'trig_collision': 1815, 'trig_follow_y': 1814, 'trig_on_death': 1812,
    'trig_zoom': 1913, 'trig_static_cam': 1914, 'trig_offset_cam': 1916, 'trig_end': 1931,
    'trig_rotate_cam': 2015, 'trig_edge_cam': 2062, 'trig_scale': 2067, 'trig_random': 2068,
}

SPEED_PORTAL = {0.5: 200, 1: 201, 2: 202, 3: 203, 4: 1334}
MODE_PORTAL = {'cube': 12, 'ship': 13, 'ball': 47, 'ufo': 111, 'wave': 660, 'robot': 745,
               'spider': 1331, 'swing': 1933}
START_MODE = {'cube': 0, 'ship': 1, 'ball': 2, 'ufo': 3, 'wave': 4, 'robot': 5, 'spider': 6, 'swing': 7}

# Хитбоксы (мост, полуширина по x): порталы режима 17, размера 15.5, гравитации 12.5,
# скорости 1x 16.5 / 2x 25.5 / 3x 32.5 / 4x 34.5, орб 18 (36x36), шип 3x6 (6x12), блок 15.
PORTAL_HW = {200: 17.5, 201: 16.5, 202: 25.5, 203: 32.5, 1334: 34.5, 99: 15.5, 101: 15.5,
             10: 12.5, 11: 12.5, 12: 17, 13: 17, 47: 17, 111: 17, 660: 17, 745: 17, 1331: 17, 1933: 17}


def _val(v):
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, (list, tuple)):
        return '.'.join(str(int(g)) for g in v)
    if isinstance(v, float):
        return ('%.4f' % v).rstrip('0').rstrip('.')
    return str(v)


def obj(oid, x, y, **props):
    """Строка объекта. props — по именам из KEYS (rot=90, groups=[1,2], sx=2) или числовым
    ключам k145='...'. Значения 0/False/None пропускаются для флагов-«по умолчанию»."""
    kv = [(1, int(oid)), (2, x), (3, y)]
    for name, v in props.items():
        if v is None:
            continue
        if name.startswith('k') and name[1:].isdigit():
            key = int(name[1:])
        elif name in KEYS:
            key = KEYS[name]
        else:
            raise KeyError('unknown property %r (add to gdobjects.KEYS or use k<num>=...)' % name)
        if key in (4, 5) and not v:
            continue
        kv.append((key, v))
    return ','.join('%d,%s' % (k, _val(v)) for k, v in kv)


def block(x, y, w=30, h=30, oid=1, **kw):
    """Блок с центром (x, y) размера w x h (масштаб sx/sy)."""
    if w != 30:
        kw['sx'] = w / 30.0
    if h != 30:
        kw['sy'] = h / 30.0
    return obj(oid, x, y, **kw)


def spike(x, y=15, down=False, small=False, **kw):
    return obj(39 if small else 8, x, y, fy=down, **kw)


def portal(kind, x, y=None, **kw):
    """kind: режим ('wave', ...), 'mini'/'big', 'grav_up'/'grav_down', скорость 0.5..4 (число)."""
    if isinstance(kind, (int, float)) and not isinstance(kind, bool):
        return obj(SPEED_PORTAL[kind], x, 15 if y is None else y, **kw)
    if kind in MODE_PORTAL:
        # высокий портал (как в генераторе): игрок проходит на любой высоте
        kw.setdefault('sy', 3.4)
        return obj(MODE_PORTAL[kind], x, 120 if y is None else y, **kw)
    return obj(ID[kind], x, 15 if y is None else y, **kw)


def trig_move(x, target, dx=0.0, dy=0.0, t=0.5, easing=0, y=300, **kw):
    """Move-триггер: сдвинуть группу target на (dx, dy) ед. за t с. (?) единицы move_x/move_y —
    сверить на примере (editor_selected)."""
    return obj(901, x, y, target=target, move_x=dx, move_y=dy, duration=t, easing=easing, **kw)


def trig_color(x, channel, rgb, t=0.0, y=300, blending=False, opacity=1.0, **kw):
    r, g, b = rgb
    return obj(899, x, y, red=r, green=g, blue=b, duration=t, target_color=channel,
               blending=blending, opacity=opacity, **kw)


def trig_alpha(x, target, opacity, t=0.0, y=300, **kw):
    return obj(1007, x, y, target=target, opacity=opacity, duration=t, **kw)


def trig_toggle(x, target, on=True, y=300, **kw):
    return obj(1049, x, y, target=target, activate=on, **kw)


def trig_rotate(x, target, degrees, t=0.5, center=None, y=300, **kw):
    return obj(1346, x, y, target=target, degrees=degrees, duration=t, center=center, **kw)


def trig_pulse(x, channel, rgb, fade_in=0.0, hold=0.0, fade_out=0.5, y=300, **kw):
    r, g, b = rgb
    return obj(1006, x, y, red=r, green=g, blue=b, fade_in=fade_in, hold=hold, fade_out=fade_out,
               target=channel, **kw)
