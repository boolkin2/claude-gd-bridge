// Бот-поисковик: уровень открыт в режиме практики, точки сохранения GD (createCheckpoint) и откат к
// любой из них (resetLevel с этой точкой). Партия вариантов нажатий прогоняется подряд; перебор ведёт
// tools/solver.py. Откат — ТОЛЬКО вне шага игры (в хуке планировщика, до его update): resetLevel
// внутри GJBaseGameLayer::update ронял игру в preUpdateVisibility (краш 18.10). За кадр — несколько
// попыток: откат -> CCScheduler::update ровно на нужное число шагов -> откат -> ...
// Команды: sim_start, sim_try, sim_free, sim_status, sim_end (см. mod/SPEC.md).
#include <Geode/Geode.hpp>
#include <Geode/modify/GJBaseGameLayer.hpp>
#include <Geode/modify/PlayLayer.hpp>
#include <Geode/modify/CCScheduler.hpp>
#include <Geode/modify/FMODAudioEngine.hpp>
#include <chrono>
#include <map>
#include <set>
#include "bridge.hpp"

using namespace geode::prelude;
using namespace bridge;

namespace {

using Clock = std::chrono::steady_clock;

struct Cp {
    CheckpointObject* obj = nullptr;
    int tick = 0;
    bool hold = false;
};

// Автопилот на отрезке [from, to): кнопку решает мод по состоянию игрока (замкнутый контур), чтобы
// держаться у высоты y. kind: 0 — корабль (зажать, если прогноз y + vy*k ниже цели), 1 — волна
// (гистерезис ±band), 2 — НЛО/импульс (тап, если прогноз ниже цели, не чаще gap тиков),
// 3 — по текущему режиму (корабль/swing -> 0, волна -> 1, НЛО -> 2, остальные — обычные нажатия):
// один автопилот проходит и стык режимов (вход в волну зависит от высоты, где кончилось НЛО);
// 4 — то же, но цель — середина свободного промежутка впереди (look ед.), по геометрии уровня;
// 5 — заход на стык: до первой смены режима держать высоту y (как 3), после — по коридору (как 4).
// Перевёрнутая гравитация учитывается. Нажатия, сделанные автопилотом, возвращаются в "applied".
struct Policy {
    int from = 0, to = 0, kind = 0;
    float y = 0, k = 2.f, band = 4.f;
    int gap = 6;
    float look = 45.f;   // kind 4: насколько вперёд смотреть на свободный промежуток
};

// Препятствия уровня (твёрдые, опасные, склоны) — прямоугольники хитбоксов, по x0; для автопилота
// по коридору (kind 4): цель — середина свободного промежутка по высоте впереди игрока.
struct Box {
    float x0, x1, y0, y1;
    int kind = 0;  // 0 прямоугольник; склон: 1 пол вверх, 2 пол вниз, 3 потолок вверх, 4 потолок вниз
};
std::vector<Box> g_boxes;
float g_boxMaxW = 0;

void buildBoxes(PlayLayer* pl) {
    g_boxes.clear();
    g_boxMaxW = 0;
    for (auto o : CCArrayExt<GameObject*>(pl->m_objects)) {
        if (!o) continue;
        auto t = o->m_objectType;
        if (t != GameObjectType::Solid && t != GameObjectType::Hazard && t != GameObjectType::AnimatedHazard &&
            t != GameObjectType::Slope)
            continue;
        auto r = o->getObjectRect();
        if (r.size.width <= 0 || r.size.height <= 0) continue;
        Box b{r.getMinX(), r.getMaxX(), r.getMinY(), r.getMaxY(), 0};
        if (t == GameObjectType::Slope) {
            // треугольник склона по отражениям (поворот 180 = оба отражения; 90/270 — как прямоугольник):
            // пол вверх — без отражений, пол вниз — fx, потолок вверх — fx+fy, потолок вниз — fy
            int rot = ((int)std::lround(o->getRotation()) % 360 + 360) % 360;
            bool fx = o->m_isFlipX, fy = o->m_isFlipY;
            if (rot == 180) {
                fx = !fx;
                fy = !fy;
            }
            if (rot == 0 || rot == 180) b.kind = fy ? (fx ? 3 : 4) : (fx ? 2 : 1);
        }
        g_boxes.push_back(b);
        g_boxMaxW = std::max(g_boxMaxW, r.size.width);
    }
    std::sort(g_boxes.begin(), g_boxes.end(), [](Box const& a, Box const& b) { return a.x0 < b.x0; });
}

// Твёрдые/опасные интервалы по высоте в полосе [X-hw, X+hw] (склоны — по диагонали).
void solidIntervals(float X, float hw, std::vector<std::pair<float, float>>& iv);

// Свободна ли точка: полоса x±hw, высота y±hh, внутри области 90..390.
bool pointFree(float X, float y, float hw, float hh) {
    if (y - hh < 90.f || y + hh > 390.f) return false;
    static std::vector<std::pair<float, float>> iv;
    iv.clear();
    solidIntervals(X, hw, iv);
    for (auto& [a, b] : iv)
        if (a < y + hh && b > y - hh) return false;
    return true;
}

// Волна летит прямыми под наклоном slope: сколько ед. по x свободно, если лететь прямо (dir +1/-1).
float freeRun(float x, float y, float slope, int dir, float hw, float hh, float maxD) {
    for (float d = 3.f; d <= maxD; d += 3.f)
        if (!pointFree(x + d, y + dir * slope * d, hw, hh)) return d;
    return maxD + 3.f;
}

// Середина свободного промежутка по высоте на x = X (полоса шириной 2*hw), ближайшего к y.
// Пол/потолок области режима — 90..390 (порталы на y=120: область 0..300 над землёй).
void solidIntervals(float X, float hw, std::vector<std::pair<float, float>>& iv) {
    auto lo = std::lower_bound(g_boxes.begin(), g_boxes.end(), X - hw - g_boxMaxW,
                               [](Box const& b, float v) { return b.x0 < v; });
    for (auto it = lo; it != g_boxes.end() && it->x0 <= X + hw; ++it) {
        if (it->x1 < X - hw) continue;
        if (it->kind == 0) {
            iv.push_back({it->y0, it->y1});
            continue;
        }
        // склон: твёрдая часть по диагонали; на полосе [X-hw, X+hw] — самая широкая
        float w = std::max(1e-3f, it->x1 - it->x0), h = it->y1 - it->y0;
        float xa = std::clamp(X - hw, it->x0, it->x1), xb = std::clamp(X + hw, it->x0, it->x1);
        auto line = [&](float x) {
            float f = (x - it->x0) / w;
            return (it->kind == 1 || it->kind == 3) ? it->y0 + f * h : it->y1 - f * h;
        };
        float la = line(xa), lb = line(xb);
        if (it->kind <= 2) iv.push_back({it->y0, std::max(la, lb)});   // пол: от низа до линии
        else iv.push_back({std::min(la, lb), it->y1});                  // потолок: от линии до верха
    }
}

float gapCenter(float X, float hw, float y) {
    std::vector<std::pair<float, float>> iv;
    solidIntervals(X, hw, iv);
    std::sort(iv.begin(), iv.end());
    float floorY = 90.f, ceilY = 390.f;
    float best = y, bestD = 1e9f;
    float cur = floorY;
    auto consider = [&](float a, float b) {
        if (b - a < 4.f) return;
        float c = 0.5f * (a + b);
        float d = (y >= a && y <= b) ? 0.f : std::min(std::fabs(y - a), std::fabs(y - b));
        if (d < bestD) {
            bestD = d;
            best = c;
        }
    };
    for (auto& [a, b] : iv) {
        if (b <= cur) continue;
        if (a > cur) consider(cur, std::min(a, ceilY));
        cur = std::max(cur, b);
        if (cur >= ceilY) break;
    }
    if (cur < ceilY) consider(cur, ceilY);
    return best;
}

struct Variant {
    int from = 0;                              // id точки; 0 — начало уровня
    int until = 0;                             // прогон до этого тика (не включая)
    std::vector<std::pair<int, bool>> inputs;  // абсолютные тики: (тик, зажато)
    std::vector<int> save;                     // тики, на которых сохранить точку
    std::vector<Policy> policy;
};

enum class Phase { Off, Opening, Ready, Running };

struct Sim {
    Phase phase = Phase::Off;
    std::string name;
    bool launched = false;
    // шагов физики за кадр: подстраивается под бюджет времени кадра (ускорение через timeScale
    // уходило в разнос: кадр дольше -> dt больше -> ещё больше шагов)
    float tpf = 120.f;
    float budgetMs = 25.f;
    int ticksLeft = 0;         // шагов, разрешённых текущему вызову update планировщика
    // Физика GD чуть зависит от разбиения шагов по кадрам (isLastTick, позиция для точки — раз в кадр):
    // замер 18.10 — остановка вызова update на другом тике давала расхождение 0.4 ед. Поэтому разбиение
    // фиксированное: ровно frameTicks шагов за вызов update, кадры с тика 0 (4 = 60 FPS), точки — только
    // на границах кадров. Тогда любой откат воспроизводит прогон с начала тик в тик.
    int frameTicks = 4;
    int stepsSeen = 0;
    long long partErr = 0;
    double resetMs = 0, cpMs = 0;
    long long resets = 0, cpMade = 0;
    bool detail = false;
    int sample = 0;
    bool stopOnSuccess = false;
    std::map<int, Cp> cps;     // id 0 — точка в самом начале уровня (ставится первой попыткой)
    std::set<CheckpointObject*> ours;
    int nextId = 1;
    ReplyPtr reply;
    std::vector<Variant> batch;
    size_t vi = 0;
    bool startPending = false;
    long long frame = 0;
    matjson::Value results = matjson::Value::array();
    // текущая попытка
    int tick = 0;
    size_t next = 0, nextSave = 0;
    bool hold = false;
    bool dead = false, finished = false;
    matjson::Value death;
    matjson::Value saved = matjson::Value::array();
    matjson::Value states = matjson::Value::array();
    matjson::Value applied = matjson::Value::array();  // фактические переключения кнопки в попытке
    int lastTap = -1000;
    int pol5Mode = -1;         // kind 5: режим в начале автопилота; 99 — режим уже сменился
    Clock::time_point lastActivity, batchStart;
    long long attempts = 0, ticksRun = 0, batchAttempts = 0, batchTicks = 0;
};
Sim g_sim;

// профиль: что дорого в откате (resetLevel) — только время, функции зовутся как обычно
std::map<std::string, std::pair<double, long long>> g_prof;
struct Prof {
    char const* name;
    Clock::time_point t0 = Clock::now();
    explicit Prof(char const* n) : name(n) {}
    ~Prof() {
        if (g_sim.phase == Phase::Off) return;
        auto& e = g_prof[name];
        e.first += std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
        e.second++;
    }
};

bool isSimLayer(GJBaseGameLayer* l) {
    auto pl = PlayLayer::get();
    return pl && static_cast<GJBaseGameLayer*>(pl) == l;
}

matjson::Value playerJson(PlayerObject* p, int tick) {
    return matjson::Value(std::vector<matjson::Value>{
        tick, p->getPositionX(), p->getPositionY(), p->m_yVelocity, modeName(p), p->m_vehicleSize < 1.f,
        p->m_isUpsideDown, p->m_playerSpeed, p->m_isOnGround, g_sim.hold});
}

// Точка создаётся штатно (createCheckpoint + storeCheckpoint: тот ставит в уровень объект-ромбик
// точки; без него откат ронял игру — ромбик без родителя попадал в отрисовку, краш 18.10), но в
// списке практики m_checkpointArray НЕ живёт: GD держит там не больше 50 точек и молча выкидывает
// старые (замер 18.10). Храним у себя; в список точка попадает только на время отката (resetLevel
// грузит последнюю), удаление — штатным removeCheckpoint (уберёт и ромбик).
void removeFromLevel(PlayLayer* pl, CheckpointObject* o) {
    if (!pl || !o) return;
    auto arr = pl->m_checkpointArray;
    auto idx = arr->indexOfObject(o);
    if (idx == CC_INVALID_INDEX) arr->addObject(o);
    else if (idx != arr->count() - 1) arr->exchangeObjectAtIndex(idx, arr->count() - 1);
    pl->removeCheckpoint(false);
}

// список практики очистить: чужие точки (автоточки практики) — штатно, свои — только из списка
void dropForeign(PlayLayer* pl) {
    auto arr = pl->m_checkpointArray;
    for (int i = (int)arr->count() - 1; i >= 0; --i) {
        auto o = static_cast<CheckpointObject*>(arr->objectAtIndex(i));
        if (g_sim.ours.count(o)) {
            arr->removeObjectAtIndex(i);
            continue;
        }
        if (i != (int)arr->count() - 1) arr->exchangeObjectAtIndex(i, arr->count() - 1);
        pl->removeCheckpoint(false);
    }
}

int addCp(PlayLayer* pl, int id, int tick, bool hold) {
    auto cp = pl->createCheckpoint();
    if (!cp) return -1;
    cp->retain();
    pl->storeCheckpoint(cp);
    pl->m_checkpointArray->removeObject(cp);
    g_sim.cps[id] = Cp{cp, tick, hold};
    g_sim.cpMade++;
    g_sim.ours.insert(cp);
    return id;
}

void freeCp(Cp& c) {
    if (!c.obj) return;
    removeFromLevel(PlayLayer::get(), c.obj);
    g_sim.ours.erase(c.obj);
    c.obj->release();
    c.obj = nullptr;
}

void freeAll() {
    for (auto& [id, c] : g_sim.cps) freeCp(c);
    g_sim.cps.clear();
    g_sim.ours.clear();
}

void replyBatch(std::string const& error = "") {
    g_sim.phase = Phase::Ready;
    g_sim.startPending = false;
    auto reply = std::move(g_sim.reply);
    if (!reply) return;
    if (!error.empty()) return reply->set(dumpErr(error));
    auto v = matjson::Value::object();
    v["results"] = std::move(g_sim.results);
    g_sim.results = matjson::Value::array();
    v["attempts"] = g_sim.batchAttempts;
    v["ticks_run"] = g_sim.batchTicks;
    v["wall"] = std::chrono::duration<double>(Clock::now() - g_sim.batchStart).count();
    v["checkpoints"] = (int)g_sim.cps.size();
    reply->set(dumpOk(v));
}

// Откат к началу варианта vi: точка сохранения (или начало уровня) -> resetLevel практики.
bool startVariant(PlayLayer* pl) {
    auto& v = g_sim.batch[g_sim.vi];
    int tick = 0;
    bool hold = false;
    CheckpointObject* obj = nullptr;
    auto it = g_sim.cps.find(v.from);
    if (it != g_sim.cps.end()) {
        obj = it->second.obj;
        tick = it->second.tick;
        hold = it->second.hold;
    } else if (v.from != 0 || !g_sim.cps.empty()) {
        return false;  // неизвестная точка (начало без точки 0 — только самая первая попытка)
    }
    if (g_sim.hold) {
        pl->handleButton(false, 1, true);
        g_sim.hold = false;
    }
    dropForeign(pl);
    if (obj) pl->m_checkpointArray->addObject(obj);
    auto r0 = Clock::now();
    pl->resetLevel();
    if (obj) pl->m_checkpointArray->removeObject(obj);
    g_sim.resetMs += std::chrono::duration<double, std::milli>(Clock::now() - r0).count();
    g_sim.resets++;
    if (!obj) addCp(pl, 0, 0, false);  // первая попытка: чистый старт, точка 0 — тут же
    if (hold) {
        pl->handleButton(true, 1, true);
        g_sim.hold = true;
    }
    g_sim.tick = tick;
    g_sim.next = 0;
    while (g_sim.next < v.inputs.size() && v.inputs[g_sim.next].first < tick) g_sim.next++;
    g_sim.nextSave = 0;
    while (g_sim.nextSave < v.save.size() && v.save[g_sim.nextSave] <= tick) g_sim.nextSave++;
    g_sim.dead = g_sim.finished = false;
    g_sim.death = matjson::Value::object();
    g_sim.saved = matjson::Value::array();
    g_sim.states = matjson::Value::array();
    g_sim.applied = matjson::Value::array();
    g_sim.lastTap = -1000;
    g_sim.pol5Mode = -1;
    g_sim.startPending = false;
    g_sim.attempts++;
    g_sim.batchAttempts++;
    return true;
}

void endVariant(PlayerObject* p) {
    auto r = matjson::Value::object();
    r["result"] = g_sim.dead ? "dead" : g_sim.finished ? "finished" : "reached";
    r["tick"] = g_sim.dead ? g_sim.tick - 1 : g_sim.tick;
    r["x"] = p->getPositionX();
    r["y"] = p->getPositionY();
    r["vy"] = p->m_yVelocity;
    r["mode"] = modeName(p);
    r["saved"] = std::move(g_sim.saved);
    g_sim.saved = matjson::Value::array();
    r["applied"] = std::move(g_sim.applied);
    g_sim.applied = matjson::Value::array();
    if (g_sim.dead) r["death"] = std::move(g_sim.death);
    if (g_sim.sample > 0) {
        r["states"] = std::move(g_sim.states);
        g_sim.states = matjson::Value::array();
    }
    g_sim.results.push(std::move(r));
    bool ok = !g_sim.dead;
    g_sim.vi++;
    if (g_sim.vi >= g_sim.batch.size() || (g_sim.stopOnSuccess && ok)) return replyBatch();
    g_sim.startPending = true;
}

void failVariant(char const* why) {
    auto r = matjson::Value::object();
    r["result"] = "error";
    r["error"] = why;
    g_sim.results.push(std::move(r));
    g_sim.vi++;
    if (g_sim.vi >= g_sim.batch.size()) return replyBatch();
    g_sim.startPending = true;
}

void simFrame() {
    g_sim.frame++;
    if (g_sim.phase == Phase::Off) return;
    auto now = Clock::now();
    if (g_sim.phase == Phase::Opening) {
        if (!g_sim.launched) {
            if (!sceneSettled()) {
                if (now - g_sim.lastActivity > std::chrono::seconds(20)) {
                    g_sim.phase = Phase::Off;
                    if (auto r = std::move(g_sim.reply)) r->set(dumpErr("previous scene did not close"));
                }
                return;
            }
            auto level = findLocalLevel(g_sim.name);
            if (!level) {
                g_sim.phase = Phase::Off;
                if (auto r = std::move(g_sim.reply)) r->set(dumpErr("level vanished"));
                return;
            }
            g_sim.launched = true;
            g_sim.lastActivity = now;
            CCDirector::get()->replaceScene(PlayLayer::scene(level, false, false));
            return;
        }
        auto pl = PlayLayer::get();
        auto sc = CCDirector::get()->getRunningScene();
        if (pl && sc && !typeinfo_cast<CCTransitionScene*>(sc)) {
            if (!pl->m_isPracticeMode) pl->togglePracticeMode(true);
            FMODAudioEngine::get()->stopAllMusic(true);
            g_sim.phase = Phase::Ready;
            auto v = matjson::Value::object();
            v["name"] = g_sim.name;
            v["budget_ms"] = g_sim.budgetMs;
            if (auto r = std::move(g_sim.reply)) r->set(dumpOk(v));
        } else if (now - g_sim.lastActivity > std::chrono::seconds(30)) {
            g_sim.phase = Phase::Off;
            if (auto r = std::move(g_sim.reply)) r->set(dumpErr("level did not open"));
        }
        return;
    }
    if (!PlayLayer::get()) {  // уровень закрыли извне
        freeAll();
        bool had = g_sim.reply != nullptr;
        auto r = std::move(g_sim.reply);
        g_sim = Sim{};
        if (had && r) r->set(dumpErr("level was closed"));
        return;
    }
    if (g_sim.phase == Phase::Running && now - g_sim.lastActivity > std::chrono::seconds(15)) {
        replyBatch("solver stalled (no game ticks for 15 s)");
    }
}

}  // namespace

namespace bridge {
bool simActive() { return g_sim.phase != Phase::Off; }
}

// --- команды ----------------------------------------------------------------------------------------
BRIDGE_COMMAND(sim_start) {
    if (runActive()) return r->set(dumpErr("play run is active"));
    if (g_sim.phase != Phase::Off) return r->set(dumpErr("solver session already open (sim_end first)"));
    if (LevelEditorLayer::get()) return r->set(dumpErr("editor is open: editor_exit first"));
    auto name = req["name"].asString().unwrapOr("");
    if (!findLocalLevel(name)) return r->set(dumpErr("level not found: " + name));
    g_sim = Sim{};
    g_boxes.clear();
    g_sim.name = name;
    g_sim.budgetMs = (float)req["budget_ms"].asDouble().unwrapOr(25.0);
    g_sim.frameTicks = std::max(1, (int)req["frame_ticks"].asInt().unwrapOr(4));
    g_sim.phase = Phase::Opening;
    g_sim.reply = r;
    g_sim.lastActivity = Clock::now();
    quitPlayLayer();
    logEvent("solver: open " + name);
}

// variants: [{from, until, inputs: [[tick, 0|1]...], save: [ticks]}], stop_on_success, sample, detail
BRIDGE_COMMAND(sim_try) {
    if (g_sim.phase != Phase::Ready) return r->set(dumpErr("solver is not ready (sim_start first)"));
    auto arr = req["variants"].asArray();
    if (!arr || arr.unwrap().empty()) return r->set(dumpErr("need variants"));
    g_sim.batch.clear();
    for (auto& it : arr.unwrap()) {
        Variant v;
        v.from = (int)it["from"].asInt().unwrapOr(0);
        v.until = (int)it["until"].asInt().unwrapOr(0);
        if (auto ins = it["inputs"].asArray()) {
            for (auto& e : ins.unwrap()) {
                auto t = e[0].asInt().unwrapOr(-1);
                if (t >= 0) v.inputs.push_back({(int)t, e[1].asInt().unwrapOr(0) != 0});
            }
        }
        std::stable_sort(v.inputs.begin(), v.inputs.end(), [](auto const& a, auto const& b) { return a.first < b.first; });
        if (auto sv = it["save"].asArray())
            for (auto& e : sv.unwrap()) v.save.push_back((int)e.asInt().unwrapOr(0));
        if (auto pa = it["policy"].asArray()) {
            for (auto& e : pa.unwrap()) {
                Policy po;
                po.from = (int)e["from"].asInt().unwrapOr(0);
                po.to = (int)e["to"].asInt().unwrapOr(0);
                po.kind = (int)e["kind"].asInt().unwrapOr(0);
                po.y = (float)e["y"].asDouble().unwrapOr(0.0);
                po.k = (float)e["k"].asDouble().unwrapOr(2.0);
                po.band = (float)e["band"].asDouble().unwrapOr(4.0);
                po.gap = (int)e["gap"].asInt().unwrapOr(6);
                po.look = (float)e["look"].asDouble().unwrapOr(45.0);
                v.policy.push_back(po);
            }
        }
        std::sort(v.save.begin(), v.save.end());
        g_sim.batch.push_back(std::move(v));
    }
    g_sim.vi = 0;
    g_sim.stopOnSuccess = req["stop_on_success"].asBool().unwrapOr(false);
    g_sim.sample = (int)req["sample"].asInt().unwrapOr(0);
    g_sim.detail = req["detail"].asBool().unwrapOr(false);
    g_sim.results = matjson::Value::array();
    g_sim.batchAttempts = g_sim.batchTicks = 0;
    g_sim.batchStart = g_sim.lastActivity = Clock::now();
    g_sim.reply = r;
    g_sim.startPending = true;
    g_sim.phase = Phase::Running;
}

// ids: [..] | all: true | before: тик (освободить точки раньше тика) — память под точки не бесконечна
BRIDGE_COMMAND(sim_free) {
    int n = 0;
    std::set<int> ids;
    if (auto arr = req["ids"].asArray())
        for (auto& e : arr.unwrap()) ids.insert((int)e.asInt().unwrapOr(0));
    bool all = req["all"].asBool().unwrapOr(false);
    int before = (int)req["before"].asInt().unwrapOr(-1);
    for (auto it = g_sim.cps.begin(); it != g_sim.cps.end();) {
        // точку 0 (начало уровня) — только явно или с all
        if (all || ids.count(it->first) || (it->first != 0 && it->second.tick < before)) {
            freeCp(it->second);
            it = g_sim.cps.erase(it);
            ++n;
        } else {
            ++it;
        }
    }
    auto v = matjson::Value::object();
    v["freed"] = n;
    v["checkpoints"] = (int)g_sim.cps.size();
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(sim_status) {
    static char const* names[] = {"off", "opening", "ready", "running"};
    auto v = matjson::Value::object();
    v["phase"] = names[(int)g_sim.phase];
    v["name"] = g_sim.name;
    v["checkpoints"] = (int)g_sim.cps.size();
    v["attempts"] = g_sim.attempts;
    v["ticks_run"] = g_sim.ticksRun;
    v["frame_ticks"] = g_sim.frameTicks;
    if (auto pl = PlayLayer::get()) {
        auto arr = pl->m_checkpointArray;
        int missing = 0, foreign = 0;
        for (auto& [id, c] : g_sim.cps)
            if (!c.obj) missing++;
        for (unsigned i = 0; i < arr->count(); ++i)
            if (!g_sim.ours.count(static_cast<CheckpointObject*>(arr->objectAtIndex(i)))) foreign++;
        v["array_count"] = (int)arr->count();
        v["missing"] = missing;
        v["foreign"] = foreign;
    }
    v["partition_errors"] = g_sim.partErr;
    v["reset_ms_avg"] = g_sim.resets ? g_sim.resetMs / g_sim.resets : 0.0;
    v["checkpoint_ms_avg"] = g_sim.cpMade ? g_sim.cpMs / g_sim.cpMade : 0.0;
    v["resets"] = g_sim.resets;
    auto pr = matjson::Value::object();
    for (auto& [k, e] : g_prof) pr[k] = matjson::Value(std::vector<matjson::Value>{e.first, e.second});
    v["prof"] = pr;
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(sim_end) {
    bool was = g_sim.phase != Phase::Off;
    freeAll();
    if (auto rp = std::move(g_sim.reply)) rp->set(dumpErr("solver session ended"));
    g_sim = Sim{};
    if (was && PlayLayer::get()) quitPlayLayer();
    auto v = matjson::Value::object();
    v["ended"] = was;
    r->set(dumpOk(v));
}

// --- хуки -------------------------------------------------------------------------------------------
class $modify(SimBGL, GJBaseGameLayer) {

    void processCommands(float dt, bool isHalfTick, bool isLastTick) {
        if (g_sim.phase == Phase::Off || !isSimLayer(this)) {
            GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
            return;
        }
        if (g_sim.phase == Phase::Running) g_sim.stepsSeen++;
        // открыт и ждёт команды / попытка кончилась / шаги этого вызова исчерпаны: физика стоит
        if (g_sim.phase != Phase::Running || g_sim.startPending || g_sim.ticksLeft <= 0) return;
        auto pl = static_cast<PlayLayer*>(static_cast<GJBaseGameLayer*>(this));
        g_sim.ticksLeft--;
        g_sim.lastActivity = Clock::now();
        auto& v = g_sim.batch[g_sim.vi];
        int n = g_sim.tick;
        Policy const* pol = nullptr;
        for (auto& po : v.policy)
            if (n >= po.from && n < po.to) pol = &po;
        int kind = pol ? pol->kind : -1;
        float target = pol ? pol->y : 0.f;
        if (kind == 5) {
            auto pp = m_player1;
            int mid = pp->m_isShip ? 1 : pp->m_isBird ? 2 : pp->m_isBall ? 3 : pp->m_isDart ? 4 : pp->m_isRobot ? 5
                      : pp->m_isSpider ? 6 : pp->m_isSwing ? 7 : 0;
            if (g_sim.pol5Mode < 0) g_sim.pol5Mode = mid;
            else if (g_sim.pol5Mode != 99 && g_sim.pol5Mode != mid) g_sim.pol5Mode = 99;
            kind = g_sim.pol5Mode == 99 ? 4 : 3;
        }
        if (kind == 3 || kind == 4) {
            auto pp = m_player1;
            if (kind == 4) {  // цель — середина свободного промежутка впереди
                if (g_boxes.empty()) buildBoxes(pl);
                auto pr = pp->getObjectRect();
                target = gapCenter(pp->getPositionX() + pol->look, pr.size.width * 0.5f + 2.f, pp->getPositionY());
            }
            kind = (pp->m_isShip || pp->m_isSwing) ? 0 : pp->m_isDart ? 1 : pp->m_isBird ? 2 : -1;
            if (kind < 0) pol = nullptr;  // куб/шар/паук/робот — нажатия из списка
        }
        auto setHold = [&](bool down) {
            if (down == g_sim.hold) return;
            this->handleButton(down, 1, true);
            g_sim.hold = down;
            g_sim.applied.push(matjson::Value(std::vector<matjson::Value>{n, down ? 1 : 0}));
        };
        if (pol) {
            while (g_sim.next < v.inputs.size() && v.inputs[g_sim.next].first <= n) g_sim.next++;
            auto pp = m_player1;
            float up = pp->m_isUpsideDown ? -1.f : 1.f;
            float y = pp->getPositionY();
            float pred = y + (float)pp->m_yVelocity * pol->k;
            bool want = g_sim.hold;
            if (kind == 0) {
                want = (target - pred) * up > 0;
            } else if (kind == 1 && pol->kind >= 4 && !(pol->kind == 5 && g_sim.pol5Mode != 99)) {
                // волна по коридору: «самый длинный свободный луч» — прямо вверх или прямо вниз
                auto pr = pp->getObjectRect();
                float hw = pr.size.width * 0.5f, hh = pr.size.height * 0.5f + 1.f;
                float slope = pp->m_vehicleSize < 1.f ? 2.f : 1.f;
                float x = pp->getPositionX();
                float upRun = freeRun(x, y, slope, +1, hw, hh, 150.f);
                float dnRun = freeRun(x, y, slope, -1, hw, hh, 150.f);
                bool goUp = g_sim.hold != pp->m_isUpsideDown;   // текущее направление (экранное)
                float curRun = goUp ? upRun : dnRun, othRun = goUp ? dnRun : upRun;
                if (othRun > curRun + pol->band) goUp = !goUp;  // поворот, только если заметно дальше
                want = goUp != pp->m_isUpsideDown;
            } else if (kind == 1) {
                float err = (target - y) * up;
                if (err > pol->band) want = true;
                else if (err < -pol->band) want = false;
            } else {
                if (g_sim.hold) want = false;  // тап — один тик
                else if ((target - pred) * up > 0 && n - g_sim.lastTap >= pol->gap) {
                    want = true;
                    g_sim.lastTap = n;
                }
            }
            setHold(want);
        } else {
            while (g_sim.next < v.inputs.size() && v.inputs[g_sim.next].first <= n) {
                setHold(v.inputs[g_sim.next].second);
                g_sim.next++;
            }
        }
        GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
        g_sim.ticksRun++;
        g_sim.batchTicks++;
        g_sim.tick = n + 1;
        auto p = m_player1;
        if (g_sim.sample > 0 && n % g_sim.sample == 0) g_sim.states.push(playerJson(p, n));
        if (g_sim.dead || g_sim.finished || g_sim.tick >= v.until) endVariant(p);
    }
};

class $modify(SimPL, PlayLayer) {
    void resetLevel() {
        Prof p("resetLevel");
        PlayLayer::resetLevel();
    }
    void loadFromCheckpoint(CheckpointObject* cp) {
        Prof p("loadFromCheckpoint");
        PlayLayer::loadFromCheckpoint(cp);
    }

    void destroyPlayer(PlayerObject* player, GameObject* object) {
        if (g_sim.phase == Phase::Off || PlayLayer::get() != this || object == m_anticheatSpike) {
            PlayLayer::destroyPlayer(player, object);
            return;
        }
        if (g_sim.phase == Phase::Running && player == m_player1 && !g_sim.dead) {
            g_sim.dead = true;
            auto d = matjson::Value::object();
            d["tick"] = g_sim.tick;
            d["x"] = player->getPositionX();
            d["y"] = player->getPositionY();
            d["yvel"] = player->m_yVelocity;
            d["mode"] = modeName(player);
            d["mini"] = player->m_vehicleSize < 1.f;
            d["upside"] = player->m_isUpsideDown;
            d["object"] = objectJson(object);
            if (g_sim.detail) d["contacts"] = contactsJson(this, player, 3.f, 6);
            g_sim.death = d;
        }
        // смерть не проигрываем: попытка кончится после этого шага
    }

    void levelComplete() {
        if (g_sim.phase == Phase::Off || PlayLayer::get() != this) return PlayLayer::levelComplete();
        g_sim.finished = true;
    }

    void playEndAnimationToPos(CCPoint pos) {
        if (g_sim.phase == Phase::Off || PlayLayer::get() != this) return PlayLayer::playEndAnimationToPos(pos);
        g_sim.finished = true;
    }

    void pauseGame(bool unfocused) {
        if (g_sim.phase != Phase::Off && PlayLayer::get() == this) return;
        PlayLayer::pauseGame(unfocused);
    }

    void startMusic() {
        if (g_sim.phase != Phase::Off && PlayLayer::get() == this) return;  // сотни откатов в секунду
        PlayLayer::startMusic();
    }
};

// Перемотка музыки к точке при откате — 41 мс из 45 (замер 18.10); во время поиска музыка не нужна.
class $modify(SimFMOD, FMODAudioEngine) {
    void setMusicTimeMS(unsigned int t, bool dontWait, int id) {
        if (g_sim.phase != Phase::Off) return;
        FMODAudioEngine::setMusicTimeMS(t, dontWait, id);
    }
};

class $modify(SimSched, CCScheduler) {
    void update(float dt) {
        simFrame();
        if (g_sim.phase != Phase::Running) return CCScheduler::update(dt);
        // кадр поиска: пока есть бюджет времени — откат (здесь, вне шага игры) и update планировщика
        // ровно на остаток попытки (не больше tpf шагов за вызов)
        auto t0 = Clock::now();
        float ts = this->getTimeScale();
        if (ts <= 0) ts = 1.f;
        for (int calls = 0; calls < 5000 && g_sim.phase == Phase::Running; ++calls) {
            auto pl = PlayLayer::get();
            if (!pl) break;
            if (g_sim.startPending) {
                if (!startVariant(pl)) {
                    failVariant("unknown checkpoint");
                    continue;
                }
            }
            auto& cur = g_sim.batch[g_sim.vi];
            int ft = g_sim.frameTicks;
            int want = ft - (g_sim.tick % ft);  // до границы кадра (после отката — всегда ft)
            g_sim.ticksLeft = want;
            g_sim.stepsSeen = 0;
            pl->m_extraDelta = 0.0;  // накопитель долей шага: ровно want шагов за вызов
            CCScheduler::update(want / 240.f / ts);
            if (g_sim.stepsSeen != want && g_sim.ticksLeft > 0) g_sim.partErr++;
            g_sim.ticksLeft = 0;
            // точка сохранения — на границе кадра и только при отпущенной кнопке, во ВСЕХ режимах:
            // после отката кнопку пришлось бы нажать заново, а свежее нажатие ≠ продолжение зажатия
            // (у волны срабатывает на тик позже — вариант, прошедший от одной точки, разбивался от другой)
            if (g_sim.phase == Phase::Running && !g_sim.startPending && g_sim.tick % ft == 0 &&
                g_sim.nextSave < cur.save.size() && cur.save[g_sim.nextSave] <= g_sim.tick) {
                if (!g_sim.hold) {
                    auto c0 = Clock::now();
                    int id = addCp(pl, g_sim.nextId, g_sim.tick, g_sim.hold);
                    g_sim.cpMs += std::chrono::duration<double, std::milli>(Clock::now() - c0).count();
                    if (id > 0) {
                        g_sim.nextId++;
                        g_sim.saved.push(matjson::Value(std::vector<matjson::Value>{id, g_sim.tick}));
                    }
                    while (g_sim.nextSave < cur.save.size() && cur.save[g_sim.nextSave] <= g_sim.tick) g_sim.nextSave++;
                }
            }
            if (std::chrono::duration<double, std::milli>(Clock::now() - t0).count() > g_sim.budgetMs) break;
        }
    }
};
