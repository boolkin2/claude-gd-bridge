# Мод Geode «claude.bridge» — спецификация

Зачем: управлять игрой и читать её состояние ТЕКСТОМ, без скриншотов и кликов по меню;
проверять уровень детерминированно (ввод по тикам физики) и быстро (ускорение времени).

## Транспорт
- Локальный TCP 127.0.0.1:47800, один клиент; запрос = одна строка JSON, ответ = одна строка
  JSON (`{"ok":true,...}` / `{"ok":false,"error":"..."}`). Сервер — свой поток (WinSock),
  всё, что трогает игру, — через `geode::queueInMainThread`, ответ — после выполнения.
- Клиент: `tools/bridge.py` (функция `call(cmd, **args)` + CLI `python -P bridge.py <cmd> '<json>'`).

## Команды (минимум для первой версии)
1. `ping` -> версия мода, версия GD, текущая сцена (menu / editor / play).
2. `load_level` {path: .gdlvl | level_string, name, song_id} -> создать (или заменить по имени)
   локальный уровень, без окна импорта. Ответ: индекс/имя.
3. `play` {name, start_x?: число | start_pos?: индекс, inputs: [[tick, 1|0], ...],
   max_ticks, speed?: множитель времени, sample?: шаг записи состояния в тиках}
   - Открыть уровень в PlayLayer (обычный режим, без практики), стартовать с начала или с
     указанной стартовой позиции.
   - Ввод — строго по тикам физики (240 Гц): нажатие/отпускание игрока 1 в начале тика N
     (хук на шаг физики `GJBaseGameLayer::update`/`processCommands` — выяснить по bindings).
   - Записывать на каждом `sample`-м тике и на каждом событии: tick, x, y, yVel, режим,
     mini, гравитация, скорость, onGround.
   - При смерти (хук `PlayLayer::destroyPlayer(PlayerObject*, GameObject*)`): tick, x, y,
     и убивший объект: id, позиция, поворот, масштаб, хитбокс (`getObjectRect`), тип.
   - Ответ: {result: "dead"|"finished"|"timeout", ticks, death?:{...}, states:[...]}.
   - `speed`>1: ускорить (масштаб времени планировщика), физика остаётся 240 Гц — проверить,
     что результат совпадает с speed=1.
4. `hitbox` {ids: [...]} -> для каждого id: тип (solid/hazard/slope/special/decor),
   размеры хитбокса (getObjectRect у созданного объекта без масштаба), есть ли поворот.
5. `exit` -> вернуться в «Мои уровни» (без сохранения, если в редакторе).

## Реализовано (v1.0.0, 17.10.2026) — `mod/src/main.cpp`, `mod/src/net.cpp`, клиент `tools/bridge.py`
- Сборка: `mod/build.ps1` (VsDevShell + Ninja, bindings — локальный клон `sdk/bindings`, копирует
  .geode в моды); перезапуск игры с ожиданием порта — `tools/gd_restart.ps1`.
- Команды: `ping`, `load_level` {name, level_string (сжатая k4), song_id} (клиент читает .gdlvl сам),
  `play` {name, inputs [[tick,1|0]], max_ticks, speed, sample, quit=true}, `hitbox` {ids},
  `objects` {x0, x1, ids, limit} (объекты живого уровня, нужен play с quit=false), `abort`, `exit`.
  Поток на клиента: ping/abort отвечают во время play.
- play: тик = вызов `GJBaseGameLayer::processCommands` (= `m_levelTime·240`); ввод — `handleButton`
  перед шагом. Ответ: result dead|finished|timeout|stalled|aborted, ticks, death {tick, x, y, mode,
  player_rect, object (часто пусто: при ударе о твёрдое GD даёт nullptr), contacts — объекты,
  пересекающие хитбокс игрока}, states [tick, x, y, yvel, mode, mini, upside, speed, ground, hold].
  Позиция — `getPosition()` (`m_position` обновляется раз в кадр!). y игры = y генератора + 90.
- Автопауза при потере фокуса окна во время play заблокирована (иначе тики встают).
- speed 1 и 20 дают побитово одинаковые состояния; speed 20 ≈ ×10 к реальному времени.
- Проверка уровня: `tools/verify.py [--load]` — прогон расписания бота и сверка с путём генератора
  по разделам (макс. отклонение, докуда дошёл, смерть с контактами).

## Редактор (v1.1, `mod/src/editor.cpp`, клиент `tools/gdedit.py`, навык `.claude/skills/gd-builder`)
Координаты как в строке уровня (y=0 — земля). Объекты — строки свойств «k,v,…» (полный доступ к
любому ключу любого объекта). Каждое изменение пишется в историю ИИ (откат `editor_undo`).
- `editor_open {name, create=true, song_id?, reopen, save_current}`, `editor_exit {save}`,
  `editor_save {disk}`, `editor_info`, `editor_settings {set:{start_mode, start_speed, start_mini,
  start_dual, flipped_gravity, platformer, song_id, audio_track, song_offset, fade_in/out, background,
  ground, middleground, ground_line, font, allow_multi_rotation, player_squeeze, fix_*}}`.
- `editor_add {objects, label, select, undo}` -> uids; `editor_list {фильтр, full, limit}`;
  `editor_remove {фильтр}`; `editor_modify {фильтр, set:{ключ:знач}, unset, dx, dy}` (объект
  пересоздаётся, uid новый); фильтр: uids ids x0 x1 y0 y1 groups selected all.
- `editor_undo {steps}`, `editor_history`, `editor_select {фильтр, add}`, `editor_selected {full}`,
  `editor_view {x, y, zoom}`, `editor_string` (вся строка уровня), `editor_playtest {start|stop}`.
- `object_catalog` (4092 ID), `object_probe {ids}` (класс, хитбокс, свойства по умолчанию) ->
  `data/gd_objects.json` (`tools/probe_all.py`), поиск `tools/gdfind.py`.
- `level_list {source: saved|local}`, `level_export {id|name|текущий}` — строки чужих уровней.
- Служебные: `commands`, `log` (журнал команд).
- Найдено: твёрдые блоки — только поворот на 90° (иначе ключ 6 отбрасывается игрой).

## Интерфейс в игре (v1.2, `mod/src/ui.cpp`)
- Настройки Geode (mod.json): server-enabled, port (после смены — перезапуск), read-only (мост
  отказывает в load_level/editor_add/remove/modify/undo/save/settings.set; editor_open без create,
  editor_exit без save), auto-backup (копия уровня перед первой правкой ИИ за сессию редактора ->
  `<save-папка мода>/backups`), notifications, editor-button, block-autopause.
- Панель «Claude Bridge» (кнопка «AI» в редакторе, «Claude AI» в меню Create): статус сервера и
  клиентов, строка «AI: …» с прогрессом, заявка, редактор/число действий ИИ, журнал; кнопки
  Undo AI / New Level / Settings / Help. Окно «New level for Claude»: имя, Song ID, файл песни,
  сложность (Auto..Extreme Demon), упор (только Hard/Insane/Extreme Demon; иначе Beauty), заметки ->
  `<save-папка мода>/request.json`.
- Команды: `request_get`, `request_status {status, message}`, `ui_status {text, progress}`,
  `ui_notify {text, icon, time}`, `ui_open {panel: main|request|references|settings}`, `ui_nodes {id}`.
- v1.3: окно «Reference levels» (галочки по скачанным уровням + вписать ID/название) ->
  `request.references`; автозапуск (`mod/src/runner.cpp`): по Send (настройка auto-start)
  мод запускает `claude-command` (по умолчанию `python -P D:\GDRetina\tools\start_claude.py`) в
  `project-dir` скрытым процессом в job-объекте; «Stop AI»/выход из игры убивают дерево процессов;
  строка «Claude run: …» в панели; команды `run_start`, `run_stop`, `run_status`.
  `start_claude.py` запускает Claude Code CLI (`-p`, задание из stdin, allowedTools: Read Glob Grep
  Write Edit Skill TodoWrite, `Bash(python -P:*)` — префикс «:*» матчит только на границе слова).
- Остановка (исправлено 18.10: два тестовых прогона пережили Stop и достроили уровень сами): job мода
  не удерживал claude.exe. Теперь запускальщик держит claude.exe в своём job (KILL_ON_JOB_CLOSE) и
  пишет `out/claude_runs/current.json` {runner, claude}; Stop убивает деревья этих процессов
  (с проверкой имени exe); «Claude run» = running, пока жив любой из них. Проверено: после Stop
  процессов нет, журнал моста за 20 с не вырос.
  Текст для игры транслитерируется (шрифты GD без кириллицы).

## Прогон и поиск в игре (v1.4, 18–19.10, `mod/src/sim.cpp`)
Сейчас основной клиент — `tools/lvl_check.py`: ОДИН прогон нажатий задуманного пути (sim_try от 0).
Перебор `tools/solver.py` (точки, откаты, автопилот) — оставлен как инструмент, для стройки не используется.
- `sim_start {name, budget_ms=25, frame_ticks=4}` — уровень в режиме практики, физика стоит до команды.
- `sim_try {variants: [{from, until, inputs: [[тик, 0|1]], save: [тики], policy: [...]}], stop_on_success,
  sample, detail}` — попытки подряд: откат к точке `from` (0 — начало уровня), прогон до `until` или
  смерти/финиша; результат на вариант: result dead/reached/finished, tick, x, y, vy, mode, saved
  [[id, тик]], applied (фактические переключения кнопки), death (+contacts при detail), states.
- `policy` — автопилот на отрезке: kind 0 корабль/1 волна/2 НЛО к высоте y, 3 — по текущему режиму,
  4 — по коридору (геометрия уровня: середина свободного промежутка, волна — «самый длинный
  свободный луч»), 5 — до смены режима к высоте y, после — по коридору (заход на стык).
- `sim_free {ids | all | before}`, `sim_status` (точки, попытки, среднее время отката), `sim_end`.
- `game_exit {restart}` — штатный выход/перезапуск игры через Geode (не убивать процесс: Geode
  считает это падением).
- Что выяснили: откат — только вне шага игры (resetLevel внутри GJBaseGameLayer::update ронял игру);
  точка — createCheckpoint + storeCheckpoint (ромбик точки должен быть в уровне, иначе краш при
  откате), но список практики держит не больше 50 точек — храним свои отдельно, в список кладём на
  время отката; перемотка музыки при откате — 41 из 45 мс, во время поиска выключена (откат ~5 мс);
  физика чуть зависит от разбиения шагов по кадрам — фиксировано 4 шага на кадр (m_extraDelta = 0),
  точки только на границах кадров и только при отпущенной кнопке (свежее нажатие волны срабатывает
  на тик позже продолжения зажатия). Проверено: откат к любой точке повторяет прогон тик в тик.

## Что выяснил мост (учтено в генераторе/физике)
- Ввод на тике N меняет движение с шага N+1 (волна, корабль, НЛО; у куба vy ставится сразу, y — со
  следующего). Ввод тика N обрабатывается ДО порталов этого тика (прежним режимом).
- Порталы: срабатывают при пересечении хитбоксов (x и y), новая физика — со следующего шага.
  Полуширины: режим 17, размер 15.5, скорость 1x 16.5 / 2x 25.5 / 3x 32.5 / 4x 34.5, гравитация 12.5,
  орб 18. Объекты обходятся по секциям x по 100 ед. (по центру объекта): портал в правой секции
  проверяется уже после смены режима в левой; широкий блок не виден у своего края.
- x во float32: x = fl32(x + v/240) каждый тик (на 3x при x>16384 шаг 1.94922).
- Хитбокс паука 27×27 (порталы для паука ставить с полушириной 13.5 — иначе на 2 тика позже, и
  ввод следующего режима получает паук); vy округляется до 0.001; физика всех режимов — `tools/physics.py`.
- Орбы и пады (18.10, `tools/cal_items.py` -> `data/cal_items.json`, таблицы ORB_VY/PAD_VY): орб
  срабатывает в тик нажатия при касании хитбокса 36×36, пад — в тик касания; мини ×0.8; синий —
  переворот гравитации с падением к новой земле, зелёный — переворот + прыжок, чёрный — бросок вниз.
- Перенос vy при смене режима: множитель к скорости после последнего шага старого режима — тот же
  режим 1, куб/паук/шар 0.5, корабль/НЛО 0.25; из волны (vy волны = ±4·шаг x) — те же доли для
  мини и обычной волны; портал гравитации на стыке (выход из перевёрнутой волны) — ещё ×0.5
  (уточнено 18.10 на 13 стыках SPEED OF LIGHT; прежние «0.125 из обычной» были такими стыками).

## Дальше (после первой версии)
- `portal_test`: где срабатывает портал/орб/пад; калибровка физики «из первых рук»
  (запись траекторий для всех режимов, мини, орбов, падов).
- Разбиение проверки по стартовым позициям: `play` на каждый раздел, одна таблица итогов.

## Сборка
- Шаблон: `geode new` (CLI в `sdk/cli/geode.exe`), id `claude.bridge`, gd "2.2081",
  geode "5.11.2". Сборка: CMake + Ninja/MSBuild (MSVC из `D:\VS\BuildTools`), Release x64.
  Готовый `.geode` -> `<папка игры>\geode\mods\`.
- Перезапуск игры после установки мода: закрыть GeometryDash.exe и запустить exe напрямую.
