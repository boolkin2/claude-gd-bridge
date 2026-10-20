# Автономный запуск Claude Code по заявке из GD. Запускается модом claude.bridge по кнопке
# «Send to Claude» (настройка Start Claude on Send) скрытым процессом; «Stop AI» в игре его убивает.
# Claude получает текст задания tools/auto_prompt.md + заявку и работает без чата: разрешены только
# чтение/правка файлов проекта и запуск `python -P tools/...` и `python -P out/auto/...`.
# Лог: out/claude_runs/<время>.log (поток событий), итог — <время>.md.
import datetime, glob, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bridge as B

LOGDIR = os.path.join(ROOT, 'out', 'claude_runs')
# Префиксное правило «:*» матчит только на границе слова: «python -P tools/:*» НЕ разрешает
# «python -P tools/bridge.py» (проверено: «This command requires approval»).
ALLOWED = ['Read', 'Glob', 'Grep', 'Write', 'Edit', 'Skill', 'TodoWrite',
           'Bash(python -P:*)', 'Bash(python -P tools/*)', 'Bash(python -P out/auto/*)']
NO_WINDOW = 0x08000000
MODELS = {'claude-sonnet-5-5': 'Sonnet 5.5', 'claude-opus-5-5': 'Opus 5.5'}
EFFORTS = {'low': 'Low', 'medium': 'Medium', 'high': 'High', 'xhigh': 'Extra', 'max': 'Max'}


def call(cmd, **kw):
    try:
        return B.call(cmd, **kw)
    except Exception:
        return None


def report(status=None, message=None, ui=None, progress=None, notify=None, icon='info'):
    if status is not None:
        call('request_status', status=status, message=message or '')
    if ui is not None:
        kw = {'text': ui}
        if progress is not None:
            kw['progress'] = progress
        call('ui_status', **kw)
    if notify:
        call('ui_notify', text=notify, icon=icon, time=4)


def find_claude():
    """-> список для запуска CLI без cmd.exe (обёртка npm .cmd ломает кавычки)."""
    exe = shutil.which('claude.exe') or os.path.expanduser(r'~\.local\bin\claude.exe')
    if exe and os.path.exists(exe):
        return [exe]
    for base in [os.path.dirname(shutil.which('claude') or ''), os.path.expandvars(r'%APPDATA%\npm'),
                 r'C:\nvm4w\nodejs']:
        if not base:
            continue
        pkg = os.path.join(base, 'node_modules', '@anthropic-ai', 'claude-code')
        native = os.path.join(pkg, 'bin', 'claude.exe')      # npm-пакет 2.x: нативный exe
        if os.path.exists(native):
            return [native]
        cli = os.path.join(pkg, 'cli.js')                     # старые версии: js
        if os.path.exists(cli):
            return [shutil.which('node') or 'node', cli]
    return None


def kill_on_close_job():
    """Job-объект Windows с KILL_ON_JOB_CLOSE: если этот запускальщик умрёт (Stop AI, выход из GD),
    система закроет хэндл и убьёт claude.exe и его детей."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.CreateJobObjectW.restype = ctypes.c_void_p
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    class BASIC(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class EXT(ctypes.Structure):
        _fields_ = [('Basic', BASIC), ('Io', ctypes.c_ulonglong * 6), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    info = EXT()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))

    def assign(pid):
        h = k32.OpenProcess(0x0001 | 0x0100, False, pid)  # PROCESS_TERMINATE | PROCESS_SET_QUOTA
        return bool(h) and bool(k32.AssignProcessToJobObject(job, h))
    return job, assign


def short(text, n=90):
    text = ' '.join(str(text).split())
    return text if len(text) <= n else text[:n - 3] + '...'


def main():
    os.makedirs(LOGDIR, exist_ok=True)
    os.makedirs(os.path.join(ROOT, 'out', 'auto'), exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    log_path = os.path.join(LOGDIR, stamp + '.log')
    r = call('request_get')
    rq = r and r.get('request')
    if not rq:
        return 0
    claude = find_claude()
    if not claude:
        report('error', 'Claude Code CLI is not installed', ui='error: Claude Code CLI not installed',
               notify='Claude Code CLI is not installed on this PC', icon='error')
        return 2
    prompt = open(os.path.join(HERE, 'auto_prompt.md'), encoding='utf-8').read()
    prompt = prompt.replace('{{REQUEST}}', json.dumps(rq, ensure_ascii=False, indent=1))
    prompt = prompt.replace('{{SUMMARY}}', os.path.relpath(log_path[:-4] + '.md', ROOT).replace('\\', '/'))
    # модель и размышления из окна заявки (Claude settings); неизвестное — по умолчанию CLI
    model = rq.get('model') if rq.get('model') in MODELS else None
    effort = rq.get('effort') if rq.get('effort') in EFFORTS else None
    label = '%s, %s' % (MODELS.get(model, 'default model'), EFFORTS.get(effort, 'default thinking'))
    report('accepted', 'Claude Code started (%s)' % label, ui='Claude Code started (%s)' % label, progress=0.0)
    cmd = claude + ['-p', '--output-format', 'stream-json', '--verbose', '--permission-mode', 'acceptEdits']
    if model:
        cmd += ['--model', model]
        if model != 'claude-sonnet-5-5':
            cmd += ['--fallback-model', 'claude-sonnet-5-5']   # если Opus недоступен/перегружен
    if effort:
        cmd += ['--effort', effort]
    cmd += ['--allowedTools'] + ALLOWED
    # фоновые задачи CLI в режиме -p гибнут вместе с сессией (18.10: Opus увёл стройку в фон,
    # закончил ход — стройку убило на генерации), поэтому фон выключен, а таймаут команд — 30 мин
    env = dict(os.environ, CLAUDE_CODE_DISABLE_BACKGROUND_TASKS='1',
               BASH_DEFAULT_TIMEOUT_MS='1800000', BASH_MAX_TIMEOUT_MS='1800000')
    t_start = datetime.datetime.now().timestamp()
    result_text, code = '', -1
    pid_file = os.path.join(LOGDIR, 'current.json')
    job, assign = kill_on_close_job()
    with open(log_path, 'w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                creationflags=NO_WINDOW, env=env)
        in_job = assign(proc.pid)
        json.dump({'runner': os.getpid(), 'claude': proc.pid, 'started': stamp, 'log': log_path,
                   'claude_in_job': in_job}, open(pid_file, 'w'))
        log.write('# runner %d, claude %d, claude_in_job=%s\n' % (os.getpid(), proc.pid, in_job))
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            log.write(line)
            log.flush()
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get('type') == 'system' and ev.get('subtype') == 'init':
                used = ev.get('model') or '?'
                log.write('# model in use: %s, effort: %s\n' % (used, effort))
                report(ui='Claude: %s, thinking %s' % (used, EFFORTS.get(effort, 'default')))
            elif ev.get('type') == 'result':
                result_text = str(ev.get('result') or '')
            elif ev.get('type') == 'assistant':
                for part in ev.get('message', {}).get('content', []):
                    if part.get('type') == 'tool_use' and part.get('name') == 'Bash':
                        log.write('# tool: %s\n' % short(part.get('input', {}).get('command', ''), 200))
        code = proc.wait()
    try:
        os.remove(pid_file)
    except OSError:
        pass
    if result_text and not os.path.exists(log_path[:-4] + '.md'):
        open(log_path[:-4] + '.md', 'w', encoding='utf-8').write(result_text)
    r = call('request_get')
    st = ((r or {}).get('request') or {}).get('status')
    # итог — по факту: свежий verify.json стройки (compose.py), а не по словам модели
    vj = os.path.join(ROOT, 'out', 'compose', ''.join(c if c.isalnum() else '_' for c in rq.get('name', '')),
                      'verify.json')
    verified = None
    if os.path.exists(vj) and os.path.getmtime(vj) >= t_start:
        try:
            verified = json.load(open(vj)).get('result')
        except ValueError:
            pass
    if st in ('cancelled', 'stopped', 'error'):
        pass
    elif verified is None:
        report('error', 'Claude ended without a built and verified level' if code == 0 else 'exit %d' % code)
        code = code or 3
    elif st != 'done':
        report('done' if verified == 'finished' else 'error', short(result_text or 'bot: %s' % verified, 120))
    report(ui='finished' if code == 0 else 'failed (exit %d)' % code,
           notify='Claude finished' if code == 0 else 'Claude failed (exit %d)' % code,
           icon='success' if code == 0 else 'error')
    # старые логи: держим последние 30
    for old in sorted(glob.glob(os.path.join(LOGDIR, '*.log')))[:-30]:
        os.remove(old)
    return code


if __name__ == '__main__':
    sys.exit(main())
