// claude.bridge — TCP-мост: управление GD текстом (см. mod/SPEC.md). Здесь: сервер, реестр команд,
// прогон уровня ботом по тикам. Редактор — editor.cpp.
#include <Geode/Geode.hpp>
#include <Geode/modify/GJBaseGameLayer.hpp>
#include <Geode/modify/PlayLayer.hpp>
#include <Geode/modify/CCScheduler.hpp>
#include <chrono>
#include <deque>
#include <map>
#include <mutex>
#include <set>
#include "bridge.hpp"
#include "net.hpp"

using namespace geode::prelude;

namespace bridge {

// --- реестр команд ---------------------------------------------------------------------------
static std::map<std::string, Handler>& registry() {
    static std::map<std::string, Handler> m;
    return m;
}
void registerCommand(std::string const& name, Handler h) { registry()[name] = std::move(h); }
std::vector<std::string> commandNames() {
    std::vector<std::string> v;
    for (auto& [k, _] : registry()) v.push_back(k);
    return v;
}

std::string dumpOk(matjson::Value v) {
    v["ok"] = true;
    return v.dump(matjson::NO_INDENTATION);
}
std::string dumpErr(std::string const& e) {
    auto v = matjson::Value::object();
    v["ok"] = false;
    v["error"] = e;
    return v.dump(matjson::NO_INDENTATION);
}

char const* typeClass(GameObjectType t) {
    switch (t) {
        case GameObjectType::Solid: return "solid";
        case GameObjectType::Hazard:
        case GameObjectType::AnimatedHazard: return "hazard";
        case GameObjectType::Slope: return "slope";
        case GameObjectType::Decoration: return "decor";
        default: return "special";
    }
}

matjson::Value rectJson(CCRect const& r) {
    return matjson::Value(std::vector<matjson::Value>{r.origin.x, r.origin.y, r.size.width, r.size.height});
}

matjson::Value objectJson(GameObject* o) {
    auto v = matjson::Value::object();
    if (!o) return v;
    v["id"] = o->m_objectID;
    v["x"] = o->getPositionX();
    v["y"] = o->getPositionY();
    v["rot"] = o->getRotation();
    v["sx"] = o->getScaleX();
    v["sy"] = o->getScaleY();
    v["fx"] = o->m_isFlipX;
    v["fy"] = o->m_isFlipY;
    v["type"] = (int)o->m_objectType;
    v["class"] = typeClass(o->m_objectType);
    v["rect"] = rectJson(o->getObjectRect());
    v["w"] = o->m_width;
    v["h"] = o->m_height;
    v["radius"] = o->m_objectRadius;
    return v;
}

GJGameLevel* findLocalLevel(std::string const& name, int* index) {
    int i = 0;
    for (auto lvl : CCArrayExt<GJGameLevel*>(LocalLevelManager::get()->m_localLevels)) {
        if (std::string(lvl->m_levelName) == name) {
            if (index) *index = i;
            return lvl;
        }
        ++i;
    }
    return nullptr;
}

// onQuit идёт с переходом, PlayLayer живёт ещё ~0.5 с — не звать второй раз для того же слоя.
static PlayLayer* g_quitting = nullptr;
void quitPlayLayer() {
    auto pl = PlayLayer::get();
    if (pl && pl != g_quitting) {
        g_quitting = pl;
        pl->onQuit();
    }
}

bool sceneSettled() {
    auto sc = CCDirector::get()->getRunningScene();
    return sc && !typeinfo_cast<CCTransitionScene*>(sc) && !PlayLayer::get() && !LevelEditorLayer::get();
}

static std::vector<std::function<bool()>> g_waiters;
void addWaiter(std::function<bool()> w) { g_waiters.push_back(std::move(w)); }

static std::mutex g_logMx;
static std::deque<std::string> g_log;
void logEvent(std::string const& s) {
    std::lock_guard lk(g_logMx);
    g_log.push_back(s);
    while (g_log.size() > 200) g_log.pop_front();
}
std::vector<std::string> recentLog(size_t n) {
    std::lock_guard lk(g_logMx);
    std::vector<std::string> v;
    for (size_t i = g_log.size() > n ? g_log.size() - n : 0; i < g_log.size(); ++i) v.push_back(g_log[i]);
    return v;
}

std::string runCommandSync(std::string const& name, matjson::Value req) {
    auto it = registry().find(name);
    if (it == registry().end()) return dumpErr("unknown cmd: " + name);
    auto reply = std::make_shared<Reply>();
    auto fut = reply->p.get_future();
    try {
        it->second(req, reply);
    } catch (std::exception const& e) {
        return dumpErr(std::string("exception: ") + e.what());
    }
    if (fut.wait_for(std::chrono::seconds(0)) == std::future_status::ready) return fut.get();
    return "";
}

bool setting(char const* key) { return Mod::get()->getSettingValue<bool>(key); }

char const* modeName(PlayerObject* p) {
    if (p->m_isShip) return "ship";
    if (p->m_isBird) return "ufo";
    if (p->m_isBall) return "ball";
    if (p->m_isDart) return "wave";
    if (p->m_isRobot) return "robot";
    if (p->m_isSpider) return "spider";
    if (p->m_isSwing) return "swing";
    return "cube";
}

// Объекты уровня, чей хитбокс пересекает хитбокс игрока (с запасом pad), ближние первыми.
// Нужно, потому что при ударе о твёрдое GD зовёт destroyPlayer с object == nullptr.
matjson::Value contactsJson(GJBaseGameLayer* layer, PlayerObject* p, float pad, size_t limit) {
    CCRect pr = p->getObjectRect();
    CCRect big(pr.origin.x - pad, pr.origin.y - pad, pr.size.width + 2 * pad, pr.size.height + 2 * pad);
    CCPoint c(pr.getMidX(), pr.getMidY());
    std::vector<std::pair<float, GameObject*>> hits;
    for (auto o : CCArrayExt<GameObject*>(layer->m_objects)) {
        if (!o || o == p || o->m_objectType == GameObjectType::Decoration) continue;
        CCRect r = o->getObjectRect();
        if (r.size.width <= 0 && r.size.height <= 0) continue;
        if (!big.intersectsRect(r)) continue;
        hits.push_back({ccpDistance(c, CCPoint(r.getMidX(), r.getMidY())), o});
    }
    std::sort(hits.begin(), hits.end(), [](auto const& a, auto const& b) { return a.first < b.first; });
    auto arr = matjson::Value::array();
    for (size_t i = 0; i < hits.size() && i < limit; ++i) {
        auto v = objectJson(hits[i].second);
        v["overlap"] = pr.intersectsRect(hits[i].second->getObjectRect());
        arr.push(v);
    }
    return arr;
}

}  // namespace bridge

using namespace bridge;

namespace {

constexpr unsigned short kPort = 47800;

char const* sceneName() {
    if (PlayLayer::get()) return "play";
    if (LevelEditorLayer::get()) return "editor";
    return "menu";
}



// --- состояние прогона ---------------------------------------------------------------------
// waiting: ждём, пока прежняя сцена закроется (onQuit идёт с переходом), потом создаём PlayLayer;
// running: идут тики. Оба — active.
enum class Phase { Idle, Waiting, Running };

struct Run {
    bool active = false;
    Phase phase = Phase::Idle;
    std::string name;
    std::chrono::steady_clock::time_point phaseStart, lastTickWall;
    ReplyPtr reply;
    std::vector<std::pair<int, bool>> inputs;
    size_t next = 0;
    int tick = 0;
    int maxTicks = 240 * 600;
    int sample = 24;
    float speed = 1.f;
    bool hold = false;
    bool quitAfter = true;
    std::string lastMode;
    bool lastMini = false, lastUpside = false;
    float lastSpeed = 0.f;
    matjson::Value states = matjson::Value::array();
    std::chrono::steady_clock::time_point t0;
    int resets = 0;
};
Run g_run;

// tick, x, y, yVel, mode, mini, upside, speed, onGround, hold.
// Позиция — getPosition(): m_position обновляется раз в кадр, а не на каждом шаге физики.
matjson::Value stateJson(PlayerObject* p, int tick) {
    return matjson::Value(std::vector<matjson::Value>{
        tick, p->getPositionX(), p->getPositionY(), p->m_yVelocity, modeName(p),
        p->m_vehicleSize < 1.f, p->m_isUpsideDown, p->m_playerSpeed, p->m_isOnGround, g_run.hold});
}

void finishRun(char const* result, matjson::Value extra = matjson::Value::object()) {
    if (!g_run.active) return;
    g_run.active = false;
    g_run.phase = Phase::Idle;
    CCDirector::get()->getScheduler()->setTimeScale(1.f);
    extra["result"] = result;
    extra["ticks"] = g_run.tick;
    extra["resets"] = g_run.resets;
    extra["wall"] = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_run.t0).count();
    if (auto pl = PlayLayer::get()) {
        extra["level_time"] = pl->m_gameState.m_levelTime;
        extra["progress"] = (int)pl->m_gameState.m_currentProgress;
    }
    extra["state_fields"] = matjson::Value(std::vector<matjson::Value>{
        "tick", "x", "y", "yvel", "mode", "mini", "upside", "speed", "ground", "hold"});
    extra["states"] = std::move(g_run.states);
    g_run.states = matjson::Value::array();
    logEvent(fmt::format("play {}: {} @ tick {}", g_run.name, result, g_run.tick));
    auto reply = std::move(g_run.reply);
    if (reply) reply->set(dumpOk(std::move(extra)));
    if (g_run.quitAfter) Loader::get()->queueInMainThread([] { quitPlayLayer(); });
}

// Каждый кадр (главный поток): ожидатели переходов сцен, запуск уровня, сторож зависаний.
void frameTick() {
    if (!PlayLayer::get()) g_quitting = nullptr;
    if (!g_waiters.empty()) {
        auto ws = std::move(g_waiters);
        g_waiters.clear();
        for (auto& w : ws)
            if (!w()) g_waiters.push_back(std::move(w));
    }
    if (!g_run.active) return;
    auto now = std::chrono::steady_clock::now();
    if (g_run.phase == Phase::Waiting) {
        if (sceneSettled()) {
            auto level = findLocalLevel(g_run.name);
            if (!level) {
                auto reply = std::move(g_run.reply);
                g_run = Run{};
                if (reply) reply->set(dumpErr("level vanished"));
                return;
            }
            g_run.phase = Phase::Running;
            g_run.phaseStart = g_run.lastTickWall = now;
            CCDirector::get()->getScheduler()->setTimeScale(g_run.speed);
            CCDirector::get()->replaceScene(PlayLayer::scene(level, false, false));
        } else if (now - g_run.phaseStart > std::chrono::seconds(15)) {
            auto e = matjson::Value::object();
            e["error_detail"] = "previous scene did not close";
            finishRun("stalled", e);
        }
        return;
    }
    if (now - g_run.lastTickWall > std::chrono::seconds(15)) {
        auto e = matjson::Value::object();
        auto pl = PlayLayer::get();
        e["has_playlayer"] = pl != nullptr;
        if (pl) e["paused"] = pl->m_isPaused;
        finishRun("stalled", e);
    }
}

// --- поток клиента ---------------------------------------------------------------------------
std::string handleLine(std::string const& line) {
    auto parsed = matjson::parse(line);
    if (!parsed) return dumpErr("bad json");
    auto req = parsed.unwrap();
    auto cmd = req["cmd"].asString().unwrapOr("");
    double timeout = req["timeout"].asDouble().unwrapOr(cmd == "play" ? 1800.0 : 60.0);
    auto reply = std::make_shared<Reply>();
    auto fut = reply->p.get_future();
    Loader::get()->queueInMainThread([cmd, req = std::move(req), reply]() mutable {
        auto& reg = registry();
        auto it = reg.find(cmd);
        if (it == reg.end()) return reply->set(dumpErr("unknown cmd: " + cmd));
        // настройки мода: сервер выключен / режим «только чтение»
        if (cmd != "ping" && !setting("server-enabled"))
            return reply->set(dumpErr("AI server is disabled in mod settings (Claude Bridge -> AI Server)"));
        if (setting("read-only")) {
            static const std::set<std::string> mutating = {
                "load_level", "editor_add", "editor_remove", "editor_modify", "editor_undo", "editor_save"};
            if (mutating.count(cmd) || (cmd == "editor_settings" && req.contains("set")))
                return reply->set(dumpErr("read-only mode is on in mod settings: changes are not allowed"));
            if (cmd == "editor_open") {
                req["create"] = false;
                req["save_current"] = false;
            }
            if (cmd == "editor_exit") req["save"] = false;
        }
        try {
            it->second(req, reply);
        } catch (std::exception const& e) {
            reply->set(dumpErr(std::string("exception: ") + e.what()));
        }
    });
    if (fut.wait_for(std::chrono::duration<double>(timeout)) != std::future_status::ready) {
        Loader::get()->queueInMainThread([] { finishRun("aborted"); });
        reply->set("");
        logEvent(cmd + ": timeout");
        return dumpErr("timeout");
    }
    auto out = fut.get();
    if (cmd != "ping" && cmd != "log")
        logEvent(cmd + (out.find("\"ok\":false") != std::string::npos ? ": ERROR" : ": ok"));
    return out;
}

}  // namespace

// --- команды общего назначения ----------------------------------------------------------------
BRIDGE_COMMAND(ping) {
    auto v = matjson::Value::object();
    v["mod"] = Mod::get()->getVersion().toVString();
    v["gd"] = Loader::get()->getGameVersion();
    v["scene"] = sceneName();
    if (auto sc = CCDirector::get()->getRunningScene()) {
        if (auto ch = sc->getChildren(); ch && ch->count() > 0)
            v["layer"] = typeid(*static_cast<CCNode*>(ch->objectAtIndex(0))).name();
    }
    v["running"] = g_run.active;
    v["server_enabled"] = setting("server-enabled");
    v["read_only"] = setting("read-only");
    if (auto ed = LevelEditorLayer::get()) v["editor_level"] = std::string(ed->m_level->m_levelName);
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(commands) {
    auto v = matjson::Value::object();
    auto arr = matjson::Value::array();
    for (auto& n : commandNames()) arr.push(n);
    v["commands"] = arr;
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(log) {
    auto v = matjson::Value::object();
    auto arr = matjson::Value::array();
    for (auto& s : recentLog((size_t)req["n"].asInt().unwrapOr(50))) arr.push(s);
    v["log"] = arr;
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(load_level) {
    auto name = req["name"].asString().unwrapOr("");
    auto str = req["level_string"].asString().unwrapOr("");
    if (name.empty() || str.empty()) return r->set(dumpErr("need name and level_string (compressed k4)"));
    int songId = (int)req["song_id"].asInt().unwrapOr(0);
    int index = -1;
    auto level = findLocalLevel(name, &index);
    bool created = false;
    if (!level) {
        level = GameLevelManager::get()->createNewLevel();
        level->m_levelName = name;
        created = true;
        findLocalLevel(name, &index);
    }
    level->m_levelString = str;
    if (songId > 0) {
        level->m_songID = songId;
        level->m_audioTrack = 0;
    }
    level->m_isEditable = true;
    auto v = matjson::Value::object();
    v["name"] = name;
    v["index"] = index;
    v["created"] = created;
    v["bytes"] = (int)str.size();
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(play) {
    if (g_run.active) return r->set(dumpErr("run already active"));
    if (simActive()) return r->set(dumpErr("solver session is active: sim_end first"));
    auto name = req["name"].asString().unwrapOr("");
    auto level = findLocalLevel(name);
    if (!level) return r->set(dumpErr("level not found: " + name));
    if (LevelEditorLayer::get()) return r->set(dumpErr("editor is open: editor_exit first"));
    g_run = Run{};
    if (auto arr = req["inputs"].asArray()) {
        for (auto& it : arr.unwrap()) {
            auto t = it[0].asInt().unwrapOr(-1);
            auto d = it[1].asInt().unwrapOr(0);
            if (t >= 0) g_run.inputs.push_back({(int)t, d != 0});
        }
    }
    std::stable_sort(g_run.inputs.begin(), g_run.inputs.end(),
                     [](auto const& a, auto const& b) { return a.first < b.first; });
    g_run.maxTicks = (int)req["max_ticks"].asInt().unwrapOr(240 * 600);
    g_run.sample = (int)req["sample"].asInt().unwrapOr(24);
    g_run.speed = (float)req["speed"].asDouble().unwrapOr(1.0);
    g_run.quitAfter = req["quit"].asBool().unwrapOr(true);
    g_run.name = name;
    g_run.reply = r;
    g_run.t0 = g_run.phaseStart = std::chrono::steady_clock::now();
    g_run.active = true;
    g_run.phase = Phase::Waiting;
    quitPlayLayer();
}

BRIDGE_COMMAND(hitbox) {
    auto out = matjson::Value::object();
    if (auto arr = req["ids"].asArray()) {
        for (auto& it : arr.unwrap()) {
            int id = (int)it.asInt().unwrapOr(0);
            auto obj = GameObject::createWithKey(id);
            if (!obj) {
                out[std::to_string(id)] = nullptr;
                continue;
            }
            obj->customSetup();  // тип и размеры хитбокса ставятся здесь, не в createWithKey
            auto v = objectJson(obj);
            v["rotated"] = obj->getRotation() != 0.f;
            out[std::to_string(id)] = v;
        }
    }
    auto v = matjson::Value::object();
    v["objects"] = out;
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(exit) {
    if (g_run.active) finishRun("aborted");
    auto v = matjson::Value::object();
    if (PlayLayer::get()) {
        quitPlayLayer();  // уйдёт в окно уровня; «Мои уровни» — повторным exit
        v["scene"] = "leaving_play";
    } else if (LevelEditorLayer::get()) {
        return r->set(dumpErr("editor is open: use editor_exit"));
    } else {
        CCDirector::get()->replaceScene(LevelBrowserLayer::scene(GJSearchObject::create(SearchType::MyLevels)));
        v["scene"] = "menu";
    }
    r->set(dumpOk(v));
}

// Объекты живого уровня (нужен открытый PlayLayer, напр. play с quit=false) в [x0, x1],
// по желанию — только ids. Для калибровки хитбоксов порталов и т.п. «как в уровне».
BRIDGE_COMMAND(objects) {
    auto pl = PlayLayer::get();
    if (!pl) return r->set(dumpErr("no PlayLayer (play with quit=false first)"));
    double x0 = req["x0"].asDouble().unwrapOr(-1e9), x1 = req["x1"].asDouble().unwrapOr(1e9);
    std::set<int> ids;
    if (auto arr = req["ids"].asArray())
        for (auto& it : arr.unwrap()) ids.insert((int)it.asInt().unwrapOr(0));
    size_t limit = (size_t)req["limit"].asInt().unwrapOr(500);
    auto list = matjson::Value::array();
    size_t n = 0;
    for (auto o : CCArrayExt<GameObject*>(pl->m_objects)) {
        if (!o) continue;
        float x = o->getPositionX();
        if (x < x0 || x > x1) continue;
        if (!ids.empty() && !ids.count(o->m_objectID)) continue;
        list.push(objectJson(o));
        if (++n >= limit) break;
    }
    auto v = matjson::Value::object();
    v["objects"] = list;
    r->set(dumpOk(v));
}

// Штатный выход/перезапуск игры через Geode (с сохранением). Принудительное завершение процесса
// Geode считает падением и при следующем запуске показывает окно «игра упала» — так не делать.
BRIDGE_COMMAND(game_exit) {
    bool restart = req["restart"].asBool().unwrapOr(false);
    if (g_run.active) finishRun("aborted");
    auto v = matjson::Value::object();
    v["restart"] = restart;
    r->set(dumpOk(v));
    logEvent(restart ? "game: restart" : "game: exit");
    // ответ уходит раньше выхода: выходим через пару кадров
    addWaiter([restart, n = 0]() mutable {
        if (++n < 10) return false;
        if (restart) utils::game::restart(true);
        else utils::game::exit(true);
        return true;
    });
}

BRIDGE_COMMAND(abort) {
    bool was = g_run.active;
    if (was) finishRun("aborted");
    auto v = matjson::Value::object();
    v["aborted"] = was;
    r->set(dumpOk(v));
}

namespace bridge {
bool runActive() { return g_run.active; }
}

// --- хуки --------------------------------------------------------------------------------------
class $modify(BridgeBGL, GJBaseGameLayer) {
    void processCommands(float dt, bool isHalfTick, bool isLastTick) {
        auto pl = PlayLayer::get();
        if (g_run.phase != Phase::Running || !pl || pl == g_quitting ||
            static_cast<GJBaseGameLayer*>(pl) != static_cast<GJBaseGameLayer*>(this)) {
            GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
            return;
        }
        g_run.lastTickWall = std::chrono::steady_clock::now();
        int n = g_run.tick;
        bool event = false;
        while (g_run.next < g_run.inputs.size() && g_run.inputs[g_run.next].first <= n) {
            bool down = g_run.inputs[g_run.next].second;
            if (down != g_run.hold) {
                this->handleButton(down, 1, true);
                g_run.hold = down;
                event = true;
            }
            g_run.next++;
        }
        GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
        if (!g_run.active) return;  // умер внутри шага — ответ уже отправлен
        auto p = m_player1;
        std::string mode = modeName(p);
        bool mini = p->m_vehicleSize < 1.f;
        if (mode != g_run.lastMode || mini != g_run.lastMini || p->m_isUpsideDown != g_run.lastUpside ||
            p->m_playerSpeed != g_run.lastSpeed) {
            event = true;
            g_run.lastMode = mode;
            g_run.lastMini = mini;
            g_run.lastUpside = p->m_isUpsideDown;
            g_run.lastSpeed = p->m_playerSpeed;
        }
        if (event || (g_run.sample > 0 && n % g_run.sample == 0)) g_run.states.push(stateJson(p, n));
        g_run.tick = n + 1;
        if (g_run.tick >= g_run.maxTicks) finishRun("timeout");
    }
};

class $modify(BridgeSched, CCScheduler) {
    void update(float dt) {
        frameTick();
        CCScheduler::update(dt);
    }
};

class $modify(BridgePL, PlayLayer) {
    // окно без фокуса -> GD ставит паузу и тики встают; во время прогона пауза запрещена
    void pauseGame(bool unfocused) {
        if (g_run.phase == Phase::Running && this != g_quitting && setting("block-autopause")) return;
        PlayLayer::pauseGame(unfocused);
    }

    void destroyPlayer(PlayerObject* player, GameObject* object) {
        if (g_run.phase == Phase::Running && this != g_quitting && object != m_anticheatSpike &&
            player == m_player1) {
            auto d = matjson::Value::object();
            d["tick"] = g_run.tick;
            d["x"] = player->getPositionX();
            d["y"] = player->getPositionY();
            d["yvel"] = player->m_yVelocity;
            d["mode"] = modeName(player);
            d["mini"] = player->m_vehicleSize < 1.f;
            d["player_rect"] = rectJson(player->getObjectRect());
            d["object"] = objectJson(object);
            d["contacts"] = contactsJson(this, player, 3.f, 8);
            g_run.states.push(stateJson(player, g_run.tick));
            auto extra = matjson::Value::object();
            extra["death"] = d;
            finishRun("dead", extra);
        }
        PlayLayer::destroyPlayer(player, object);
    }

    void levelComplete() {
        if (g_run.phase == Phase::Running && this != g_quitting) finishRun("finished");
        PlayLayer::levelComplete();
    }

    void resetLevel() {
        PlayLayer::resetLevel();
        if (g_run.phase == Phase::Running && this != g_quitting) {
            g_run.resets++;
            g_run.tick = 0;
            g_run.next = 0;
            if (g_run.hold) {
                this->handleButton(false, 1, true);
                g_run.hold = false;
            }
            g_run.states = matjson::Value::array();
        }
    }
};

$on_mod(Loaded) {
    auto port = (unsigned short)Mod::get()->getSettingValue<int64_t>("port");
    if (port < 1024) port = kPort;
    bridge_net::start(port, handleLine);
    log::info("claude.bridge listening on 127.0.0.1:{}", port);
}
