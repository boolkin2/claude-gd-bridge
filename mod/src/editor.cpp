// Команды редактора claude.bridge: открыть/создать уровень, ставить/читать/менять/удалять любые
// объекты (строкой свойств как в сохранении уровня), настройки, камера, выделение, сохранение,
// откат действий ИИ, каталог объектов, экспорт чужих уровней.
// Координаты в командах — как в строке уровня: y = 0 — земля (мир редактора = y + 90).
#include <Geode/Geode.hpp>
#include <chrono>
#include <ctime>
#include <filesystem>
#include <set>
#include <sstream>
#include <unordered_map>
#include "bridge.hpp"

using namespace geode::prelude;
using namespace bridge;

namespace {

constexpr float kGround = 90.f;

LevelEditorLayer* editorOr(ReplyPtr const& r) {
    auto ed = LevelEditorLayer::get();
    if (!ed || !ed->m_editorUI) {
        r->set(dumpErr("editor is not open (editor_open first)"));
        return nullptr;
    }
    return ed;
}

// --- строка свойств объекта «k,v,k,v» ---------------------------------------------------------
struct Props {
    std::vector<std::pair<std::string, std::string>> kv;

    static Props parse(std::string const& s) {
        Props p;
        std::vector<std::string> parts;
        std::string cur;
        for (char c : s) {
            if (c == ',') {
                parts.push_back(cur);
                cur.clear();
            } else if (c != ';') {
                cur.push_back(c);
            }
        }
        parts.push_back(cur);
        for (size_t i = 0; i + 1 < parts.size(); i += 2) p.kv.push_back({parts[i], parts[i + 1]});
        return p;
    }
    std::string get(std::string const& k, std::string const& def = "") const {
        for (auto& [a, b] : kv)
            if (a == k) return b;
        return def;
    }
    void set(std::string const& k, std::string const& v) {
        for (auto& [a, b] : kv)
            if (a == k) {
                b = v;
                return;
            }
        kv.push_back({k, v});
    }
    void erase(std::string const& k) {
        std::erase_if(kv, [&](auto const& p) { return p.first == k; });
    }
    std::string str() const {
        std::string out;
        for (auto& [a, b] : kv) {
            if (!out.empty()) out.push_back(',');
            out += a;
            out.push_back(',');
            out += b;
        }
        return out;
    }
};

std::string fmtNum(double v) {
    std::ostringstream o;
    o.precision(10);
    o << v;
    return o.str();
}

std::string jsonToStr(matjson::Value const& v) {
    if (v.isString()) return v.asString().unwrap();
    if (v.isBool()) return v.asBool().unwrap() ? "1" : "0";
    if (v.isNumber()) return fmtNum(v.asDouble().unwrap());
    return v.dump(matjson::NO_INDENTATION);
}

std::string saveString(LevelEditorLayer* ed, GameObject* o) { return std::string(o->getSaveString(ed)); }

// --- история действий ИИ (для отката) ------------------------------------------------------------
struct Action {
    std::string what;
    std::vector<int> created;           // uid созданных
    std::vector<std::string> removed;   // строки удалённых (для восстановления)
};
std::vector<Action> g_hist;
LevelEditorLayer* g_histEditor = nullptr;

void pushHistory(LevelEditorLayer* ed, Action a) {
    if (g_histEditor != ed) {
        g_hist.clear();
        g_histEditor = ed;
    }
    g_hist.push_back(std::move(a));
    while (g_hist.size() > 100) g_hist.erase(g_hist.begin());
}

std::unordered_map<int, GameObject*> uidMap(LevelEditorLayer* ed) {
    std::unordered_map<int, GameObject*> m;
    for (auto o : CCArrayExt<GameObject*>(ed->m_objects))
        if (o) m[o->m_uniqueID] = o;
    return m;
}

// --- фильтр объектов -------------------------------------------------------------------------
struct Filter {
    bool any = false;
    double x0 = -1e18, x1 = 1e18, y0 = -1e18, y1 = 1e18;
    std::set<int> ids, uids, groups;
    bool selected = false;
    bool all = false;

    static Filter from(matjson::Value const& req) {
        Filter f;
        auto num = [&](char const* k, double& dst) {
            if (req.contains(k)) {
                dst = req[k].asDouble().unwrapOr(dst);
                f.any = true;
            }
        };
        num("x0", f.x0);
        num("x1", f.x1);
        num("y0", f.y0);
        num("y1", f.y1);
        auto ints = [&](char const* k, std::set<int>& dst) {
            if (auto arr = req[k].asArray()) {
                for (auto& it : arr.unwrap()) dst.insert((int)it.asInt().unwrapOr(0));
                f.any = true;
            }
        };
        ints("ids", f.ids);
        ints("uids", f.uids);
        ints("groups", f.groups);
        f.selected = req["selected"].asBool().unwrapOr(false);
        f.all = req["all"].asBool().unwrapOr(false);
        if (f.selected || f.all) f.any = true;
        return f;
    }

    bool match(LevelEditorLayer* ed, GameObject* o, std::set<GameObject*> const& sel) const {
        if (selected && !sel.count(o)) return false;
        double x = o->getPositionX(), y = o->getPositionY() - kGround;
        if (x < x0 || x > x1 || y < y0 || y > y1) return false;
        if (!ids.empty() && !ids.count(o->m_objectID)) return false;
        if (!uids.empty() && !uids.count(o->m_uniqueID)) return false;
        if (!groups.empty()) {
            auto g = Props::parse(saveString(ed, o)).get("57");
            bool hit = false;
            std::stringstream ss(g);
            std::string tok;
            while (std::getline(ss, tok, '.'))
                if (!tok.empty() && groups.count(std::atoi(tok.c_str()))) hit = true;
            if (!hit) return false;
        }
        return true;
    }
};

std::set<GameObject*> selectedSet(LevelEditorLayer* ed) {
    std::set<GameObject*> s;
    auto ui = ed->m_editorUI;
    if (ui->m_selectedObject) s.insert(ui->m_selectedObject);
    if (ui->m_selectedObjects)
        for (auto o : CCArrayExt<GameObject*>(ui->m_selectedObjects)) s.insert(o);
    return s;
}

std::vector<GameObject*> collect(LevelEditorLayer* ed, Filter const& f) {
    std::vector<GameObject*> out;
    auto sel = selectedSet(ed);
    for (auto o : CCArrayExt<GameObject*>(ed->m_objects))
        if (o && f.match(ed, o, sel)) out.push_back(o);
    return out;
}

// Компактная запись объекта: [uid, id, x, y, rot, sx, sy]; full — плюс строка свойств.
matjson::Value objRow(LevelEditorLayer* ed, GameObject* o, bool full) {
    auto v = matjson::Value::object();
    v["uid"] = o->m_uniqueID;
    v["id"] = o->m_objectID;
    v["x"] = o->getPositionX();
    v["y"] = o->getPositionY() - kGround;
    if (o->getRotation() != 0.f) v["rot"] = o->getRotation();
    if (o->getScaleX() != 1.f) v["sx"] = o->getScaleX();
    if (o->getScaleY() != 1.f) v["sy"] = o->getScaleY();
    if (full) {
        v["props"] = saveString(ed, o);
        v["class"] = typeClass(o->m_objectType);
    }
    return v;
}

std::vector<int> createFrom(LevelEditorLayer* ed, std::string const& objs, bool undo, CCArray** outArr = nullptr) {
    std::vector<int> uids;
    if (objs.empty()) return uids;
    auto arr = ed->createObjectsFromString(objs, !undo, true);
    if (arr) {
        for (auto o : CCArrayExt<GameObject*>(arr)) uids.push_back(o->m_uniqueID);
        if (outArr) *outArr = arr;
    }
    return uids;
}

void removeObjs(LevelEditorLayer* ed, std::vector<GameObject*> const& objs, std::vector<std::string>* saved) {
    ed->m_editorUI->deselectAll();
    for (auto o : objs) {
        if (saved) saved->push_back(saveString(ed, o));
        ed->removeObject(o, true);
    }
}

std::string joinObjects(matjson::Value const& v) {
    if (v.isString()) return v.asString().unwrap();
    std::string out;
    if (auto arr = v.asArray()) {
        for (auto& it : arr.unwrap()) {
            auto s = it.asString().unwrapOr("");
            if (s.empty()) continue;
            if (!out.empty() && out.back() != ';') out.push_back(';');
            out += s;
        }
    }
    return out;
}

matjson::Value intArr(std::vector<int> const& v) {
    auto a = matjson::Value::array();
    for (int x : v) a.push(x);
    return a;
}

// --- выход/вход в редактор ----------------------------------------------------------------------
void exitEditor(LevelEditorLayer* ed, bool save) {
    auto p = EditorPauseLayer::create(ed);
    if (save) p->saveLevel();
    p->onExitEditor(nullptr);
}

void waitUntil(std::function<bool()> cond, std::function<void()> then, ReplyPtr r, std::string what, int seconds = 20) {
    auto t0 = std::chrono::steady_clock::now();
    addWaiter([=]() {
        if (cond()) {
            then();
            return true;
        }
        if (std::chrono::steady_clock::now() - t0 > std::chrono::seconds(seconds)) {
            r->set(dumpErr("timeout waiting: " + what));
            return true;
        }
        return false;
    });
}

int speedToEnum(double s) {
    if (s < 0.75) return (int)Speed::Slow;
    if (s < 1.5) return (int)Speed::Normal;
    if (s < 2.5) return (int)Speed::Fast;
    if (s < 3.5) return (int)Speed::Faster;
    return (int)Speed::Fastest;
}
double enumToSpeed(int e) {
    switch ((Speed)e) {
        case Speed::Slow: return 0.5;
        case Speed::Fast: return 2;
        case Speed::Faster: return 3;
        case Speed::Fastest: return 4;
        default: return 1;
    }
}

matjson::Value settingsJson(LevelEditorLayer* ed) {
    auto s = ed->m_levelSettings;
    auto v = matjson::Value::object();
    v["name"] = std::string(ed->m_level->m_levelName);
    v["song_id"] = ed->m_level->m_songID;
    v["audio_track"] = ed->m_level->m_audioTrack;
    v["start_mode"] = s->m_startMode;  // 0 куб 1 корабль 2 шар 3 НЛО 4 волна 5 робот 6 паук 7 swing
    v["start_speed"] = enumToSpeed((int)s->m_startSpeed);
    v["start_mini"] = s->m_startMini;
    v["start_dual"] = s->m_startDual;
    v["flipped_gravity"] = s->m_isFlipped;
    v["platformer"] = s->m_platformerMode;
    v["two_player"] = s->m_twoPlayerMode;
    v["song_offset"] = s->m_songOffset;
    v["fade_in"] = s->m_fadeIn;
    v["fade_out"] = s->m_fadeOut;
    v["background"] = s->m_backgroundIndex;
    v["ground"] = s->m_groundIndex;
    v["middleground"] = s->m_middleGroundIndex;
    v["ground_line"] = s->m_groundLineIndex;
    v["font"] = s->m_fontIndex;
    v["allow_multi_rotation"] = s->m_allowMultiRotation;  // свободный поворот твёрдых объектов
    v["player_squeeze"] = s->m_enablePlayerSqueeze;
    v["fix_gravity_bug"] = s->m_fixGravityBug;
    v["fix_negative_scale"] = s->m_fixNegativeScale;
    v["fix_robot_jump"] = s->m_fixRobotJump;
    return v;
}

}  // namespace

namespace bridge {
static LevelEditorLayer* g_backedUp = nullptr;
void backupBeforeEdit(LevelEditorLayer* ed) {
    if (g_backedUp == ed || !setting("auto-backup")) return;
    g_backedUp = ed;
    auto dir = Mod::get()->getSaveDir() / "backups";
    std::error_code ec;
    std::filesystem::create_directories(dir, ec);
    std::string name;
    for (char c : std::string(ed->m_level->m_levelName))
        name.push_back(std::isalnum((unsigned char)c) ? c : '_');
    char ts[32];
    auto t = std::time(nullptr);
    std::strftime(ts, sizeof(ts), "%Y%m%d-%H%M%S", std::localtime(&t));
    auto path = dir / (name + "-" + ts + ".txt");
    (void)utils::file::writeString(path, std::string(ed->getLevelString()));
    logEvent("backup: " + path.filename().string());
}
}  // namespace bridge

// --- команды ------------------------------------------------------------------------------------

// editor_open {name, create=true, song_id?, save_current=true}: открыть локальный уровень в редакторе.
BRIDGE_COMMAND(editor_open) {
    if (runActive()) return r->set(dumpErr("bot run is active"));
    auto name = req["name"].asString().unwrapOr("");
    if (name.empty()) return r->set(dumpErr("need name"));
    auto level = findLocalLevel(name);
    bool created = false;
    if (!level) {
        if (!req["create"].asBool().unwrapOr(true)) return r->set(dumpErr("level not found: " + name));
        level = GameLevelManager::get()->createNewLevel();
        level->m_levelName = name;
        level->m_isEditable = true;
        created = true;
    }
    if (int song = (int)req["song_id"].asInt().unwrapOr(0); song > 0) {
        level->m_songID = song;
        level->m_audioTrack = 0;
    }
    if (auto ed = LevelEditorLayer::get()) {
        if (ed->m_level == level && !req["reopen"].asBool().unwrapOr(false)) {
            auto v = settingsJson(ed);
            v["already_open"] = true;
            return r->set(dumpOk(v));
        }
        exitEditor(ed, req["save_current"].asBool().unwrapOr(true));
    } else if (PlayLayer::get()) {
        quitPlayLayer();
    }
    level->retain();
    waitUntil(sceneSettled, [=]() {
        CCDirector::get()->replaceScene(LevelEditorLayer::scene(level, false));
        waitUntil([]() { return LevelEditorLayer::get() && EditorUI::get(); }, [=]() {
            level->release();
            auto v = settingsJson(LevelEditorLayer::get());
            v["created"] = created;
            v["objects"] = (int)LevelEditorLayer::get()->m_objects->count();
            r->set(dumpOk(v));
        }, r, "editor to open");
    }, r, "previous scene to close");
}

// editor_exit {save=true}
BRIDGE_COMMAND(editor_exit) {
    auto ed = editorOr(r);
    if (!ed) return;
    exitEditor(ed, req["save"].asBool().unwrapOr(true));
    waitUntil([]() { return !LevelEditorLayer::get(); }, [=]() { r->set(dumpOk(matjson::Value::object())); },
              r, "editor to close");
}

// editor_save {disk=true}: как кнопка Save; disk — сразу записать CCLocalLevels.dat
BRIDGE_COMMAND(editor_save) {
    auto ed = editorOr(r);
    if (!ed) return;
    EditorPauseLayer::create(ed)->saveLevel();
    if (req["disk"].asBool().unwrapOr(true)) LocalLevelManager::get()->save();
    auto v = matjson::Value::object();
    v["objects"] = (int)ed->m_objects->count();
    r->set(dumpOk(v));
}

BRIDGE_COMMAND(editor_info) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto v = settingsJson(ed);
    v["objects"] = (int)ed->m_objects->count();
    v["selected"] = (int)selectedSet(ed).size();
    v["history"] = (int)(g_histEditor == ed ? g_hist.size() : 0);
    auto layer = ed->m_objectLayer;
    auto win = CCDirector::get()->getWinSize();
    float s = layer->getScale();
    v["zoom"] = s;
    v["view_x"] = (win.width / 2 - layer->getPositionX()) / s;
    v["view_y"] = (win.height / 2 - layer->getPositionY()) / s - kGround;
    r->set(dumpOk(v));
}

// editor_add {objects: "1,1,2,15,3,15;1,8,2,45,3,15" | [строки], undo=false, select=false, label?}
BRIDGE_COMMAND(editor_add) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto objs = joinObjects(req["objects"]);
    if (objs.empty()) return r->set(dumpErr("need objects"));
    backupBeforeEdit(ed);
    CCArray* arr = nullptr;
    auto uids = createFrom(ed, objs, req["undo"].asBool().unwrapOr(false), &arr);
    if (req["select"].asBool().unwrapOr(false) && arr) {
        ed->m_editorUI->deselectAll();
        ed->m_editorUI->selectObjects(arr, true);
    }
    auto label = req["label"].asString().unwrapOr("add");
    pushHistory(ed, Action{label, uids, {}});
    if (setting("notifications")) notify(fmt::format("Claude: {} (+{})", label, uids.size()));
    auto v = matjson::Value::object();
    v["created"] = (int)uids.size();
    if (req["return_uids"].asBool().unwrapOr(true)) v["uids"] = intArr(uids);
    v["objects"] = (int)ed->m_objects->count();
    r->set(dumpOk(v));
}

// editor_list {фильтр: x0 x1 y0 y1 ids uids groups selected all, full=false, limit=5000}
BRIDGE_COMMAND(editor_list) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto f = Filter::from(req);
    bool full = req["full"].asBool().unwrapOr(false);
    size_t limit = (size_t)req["limit"].asInt().unwrapOr(5000);
    auto objs = collect(ed, f);
    std::sort(objs.begin(), objs.end(), [](auto a, auto b) { return a->getPositionX() < b->getPositionX(); });
    auto list = matjson::Value::array();
    for (size_t i = 0; i < objs.size() && i < limit; ++i) list.push(objRow(ed, objs[i], full));
    auto v = matjson::Value::object();
    v["count"] = (int)objs.size();
    v["objects"] = list;
    r->set(dumpOk(v));
}

// editor_remove {фильтр (uids / ids / x0..x1 / groups / selected / all)}
BRIDGE_COMMAND(editor_remove) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto f = Filter::from(req);
    if (!f.any) return r->set(dumpErr("empty filter: pass uids/ids/x0..x1/groups/selected or all=true"));
    auto objs = collect(ed, f);
    backupBeforeEdit(ed);
    Action a{req["label"].asString().unwrapOr("remove"), {}, {}};
    removeObjs(ed, objs, &a.removed);
    if (setting("notifications")) notify(fmt::format("Claude: {} (-{})", a.what, objs.size()));
    pushHistory(ed, std::move(a));
    auto v = matjson::Value::object();
    v["removed"] = (int)objs.size();
    v["objects"] = (int)ed->m_objects->count();
    r->set(dumpOk(v));
}

// editor_modify {фильтр, set: {"6": 45, "57": "3.4", ...}, unset: ["128"], dx, dy}
// Любое свойство: объект пересоздаётся с изменённой строкой (uid меняется — ответ: старый->новый).
BRIDGE_COMMAND(editor_modify) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto f = Filter::from(req);
    if (!f.any) return r->set(dumpErr("empty filter"));
    auto objs = collect(ed, f);
    double dx = req["dx"].asDouble().unwrapOr(0), dy = req["dy"].asDouble().unwrapOr(0);
    std::vector<std::pair<std::string, std::string>> sets;
    if (req["set"].isObject())
        for (auto& [k, val] : req["set"]) sets.push_back({k, jsonToStr(val)});
    std::vector<std::string> unset;
    if (auto arr = req["unset"].asArray())
        for (auto& it : arr.unwrap()) unset.push_back(jsonToStr(it));
    std::string out;
    std::vector<int> oldUids;
    backupBeforeEdit(ed);
    Action a{req["label"].asString().unwrapOr("modify"), {}, {}};
    for (auto o : objs) {
        auto p = Props::parse(saveString(ed, o));
        if (dx != 0) p.set("2", fmtNum(std::atof(p.get("2", "0").c_str()) + dx));
        if (dy != 0) p.set("3", fmtNum(std::atof(p.get("3", "0").c_str()) + dy));
        for (auto& [k, val] : sets) p.set(k, val);
        for (auto& k : unset) p.erase(k);
        if (!out.empty()) out.push_back(';');
        out += p.str();
        oldUids.push_back(o->m_uniqueID);
    }
    removeObjs(ed, objs, &a.removed);
    a.created = createFrom(ed, out, false);
    auto v = matjson::Value::object();
    v["modified"] = (int)a.created.size();
    if (setting("notifications")) notify(fmt::format("Claude: {} ({})", a.what, a.created.size()));
    v["old_uids"] = intArr(oldUids);
    v["uids"] = intArr(a.created);
    pushHistory(ed, std::move(a));
    r->set(dumpOk(v));
}

// editor_undo {steps=1}: откат действий ИИ (add/remove/modify/clear) этой сессии редактора
BRIDGE_COMMAND(editor_undo) {
    auto ed = editorOr(r);
    if (!ed) return;
    if (g_histEditor != ed || g_hist.empty()) return r->set(dumpErr("nothing to undo"));
    backupBeforeEdit(ed);
    int steps = (int)req["steps"].asInt().unwrapOr(1);
    auto labels = matjson::Value::array();
    for (int i = 0; i < steps && !g_hist.empty(); ++i) {
        auto a = std::move(g_hist.back());
        g_hist.pop_back();
        auto m = uidMap(ed);
        std::vector<GameObject*> objs;
        for (int uid : a.created)
            if (auto it = m.find(uid); it != m.end()) objs.push_back(it->second);
        removeObjs(ed, objs, nullptr);
        std::string s;
        for (auto& str : a.removed) {
            if (!s.empty()) s.push_back(';');
            s += str;
        }
        createFrom(ed, s, false);
        labels.push(a.what);
    }
    auto v = matjson::Value::object();
    v["undone"] = labels;
    v["objects"] = (int)ed->m_objects->count();
    r->set(dumpOk(v));
}

// editor_history: список меток действий ИИ (для интерфейса и для «что я сделала»)
BRIDGE_COMMAND(editor_history) {
    auto arr = matjson::Value::array();
    if (g_histEditor == LevelEditorLayer::get())
        for (auto& a : g_hist) {
            auto e = matjson::Value::object();
            e["label"] = a.what;
            e["created"] = (int)a.created.size();
            e["removed"] = (int)a.removed.size();
            arr.push(e);
        }
    auto v = matjson::Value::object();
    v["history"] = arr;
    r->set(dumpOk(v));
}

// editor_select {фильтр, add=false}: выделить (видно человеку в редакторе)
BRIDGE_COMMAND(editor_select) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto objs = collect(ed, Filter::from(req));
    auto arr = CCArray::create();
    for (auto o : objs) arr->addObject(o);
    if (!req["add"].asBool().unwrapOr(false)) ed->m_editorUI->deselectAll();
    if (arr->count()) ed->m_editorUI->selectObjects(arr, true);
    auto v = matjson::Value::object();
    v["selected"] = (int)objs.size();
    r->set(dumpOk(v));
}

// editor_selected {full=true}: что выделил человек — со всеми свойствами (учиться по примеру)
BRIDGE_COMMAND(editor_selected) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto list = matjson::Value::array();
    bool full = req["full"].asBool().unwrapOr(true);
    for (auto o : selectedSet(ed)) list.push(objRow(ed, o, full));
    auto v = matjson::Value::object();
    v["objects"] = list;
    r->set(dumpOk(v));
}

// editor_view {x, y, zoom?}: камера редактора на точку (в координатах уровня)
BRIDGE_COMMAND(editor_view) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto layer = ed->m_objectLayer;
    if (req.contains("zoom")) ed->m_editorUI->updateZoom((float)req["zoom"].asDouble().unwrapOr(1.0));
    float s = layer->getScale();
    auto win = CCDirector::get()->getWinSize();
    double x = req["x"].asDouble().unwrapOr((win.width / 2 - layer->getPositionX()) / s);
    double y = req["y"].asDouble().unwrapOr((win.height / 2 - layer->getPositionY()) / s - kGround);
    layer->setPosition(CCPoint(win.width / 2 - (float)x * s, win.height / 2 - (float)(y + kGround) * s));
    auto v = matjson::Value::object();
    v["zoom"] = s;
    r->set(dumpOk(v));
}

// editor_settings {set?: {start_mode, start_speed, start_mini, start_dual, flipped_gravity, platformer,
//   song_id, song_offset, fade_in, fade_out, background, ground, middleground, ground_line, font}}
BRIDGE_COMMAND(editor_settings) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto s = ed->m_levelSettings;
    auto const& set = req["set"];
    if (set.isObject()) {
        backupBeforeEdit(ed);
        auto b = [&](char const* k, bool& dst) { if (set.contains(k)) dst = set[k].asBool().unwrapOr(dst); };
        auto i = [&](char const* k, int& dst) { if (set.contains(k)) dst = (int)set[k].asInt().unwrapOr(dst); };
        i("start_mode", s->m_startMode);
        if (set.contains("start_speed")) s->m_startSpeed = (Speed)speedToEnum(set["start_speed"].asDouble().unwrapOr(1));
        b("start_mini", s->m_startMini);
        b("start_dual", s->m_startDual);
        b("flipped_gravity", s->m_isFlipped);
        b("platformer", s->m_platformerMode);
        b("two_player", s->m_twoPlayerMode);
        b("fade_in", s->m_fadeIn);
        b("fade_out", s->m_fadeOut);
        if (set.contains("song_offset")) s->m_songOffset = (float)set["song_offset"].asDouble().unwrapOr(0);
        i("background", s->m_backgroundIndex);
        i("ground", s->m_groundIndex);
        i("middleground", s->m_middleGroundIndex);
        i("ground_line", s->m_groundLineIndex);
        i("font", s->m_fontIndex);
        b("allow_multi_rotation", s->m_allowMultiRotation);
        b("player_squeeze", s->m_enablePlayerSqueeze);
        b("fix_gravity_bug", s->m_fixGravityBug);
        b("fix_negative_scale", s->m_fixNegativeScale);
        b("fix_robot_jump", s->m_fixRobotJump);
        if (set.contains("song_id")) {
            ed->m_level->m_songID = (int)set["song_id"].asInt().unwrapOr(0);
            ed->m_level->m_audioTrack = 0;
        }
        if (set.contains("audio_track")) {
            ed->m_level->m_audioTrack = (int)set["audio_track"].asInt().unwrapOr(0);
            ed->m_level->m_songID = 0;
        }
    }
    r->set(dumpOk(settingsJson(ed)));
}

// editor_string: полная строка уровня (несжатая: заголовок;объект;объект...)
BRIDGE_COMMAND(editor_string) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto v = matjson::Value::object();
    v["level_string"] = std::string(ed->getLevelString());
    r->set(dumpOk(v));
}

// editor_playtest {action: start|stop}
BRIDGE_COMMAND(editor_playtest) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto act = req["action"].asString().unwrapOr("start");
    if (act == "stop") ed->m_editorUI->onStopPlaytest(nullptr);
    else ed->m_editorUI->onPlaytest(nullptr);
    r->set(dumpOk(matjson::Value::object()));
}

// object_catalog: все ID объектов игры с именами кадров (что вообще можно ставить)
BRIDGE_COMMAND(object_catalog) {
    auto list = matjson::Value::array();
    for (auto& [id, frame] : ObjectToolbox::sharedState()->m_allKeys)
        list.push(matjson::Value(std::vector<matjson::Value>{id, std::string(frame)}));
    auto v = matjson::Value::object();
    v["objects"] = list;
    r->set(dumpOk(v));
}

// object_probe {ids}: создать объект в редакторе далеко за уровнем, прочитать тип, хитбокс и
// свойства по умолчанию (какие ключи есть у триггера), удалить. Нужен открытый редактор.
BRIDGE_COMMAND(object_probe) {
    auto ed = editorOr(r);
    if (!ed) return;
    auto out = matjson::Value::object();
    if (auto arr = req["ids"].asArray()) {
        for (auto& it : arr.unwrap()) {
            int id = (int)it.asInt().unwrapOr(0);
            auto o = ed->createObject(id, CCPoint(-3000.f, 3000.f), true);
            if (!o) {
                out[std::to_string(id)] = nullptr;
                continue;
            }
            auto v = objectJson(o);
            v["props"] = saveString(ed, o);
            v["frame"] = std::string(ObjectToolbox::sharedState()->m_allKeys[id]);
            ed->removeObject(o, true);
            out[std::to_string(id)] = v;
        }
    }
    ed->m_editorUI->deselectAll();
    auto v = matjson::Value::object();
    v["objects"] = out;
    r->set(dumpOk(v));
}

// level_list {source: local|saved}: локальные уровни или сохранённые/скачанные онлайн-уровни
BRIDGE_COMMAND(level_list) {
    auto src = req["source"].asString().unwrapOr("saved");
    CCArray* arr = src == "local" ? LocalLevelManager::get()->m_localLevels
                                  : GameLevelManager::get()->getSavedLevels(false, 0);
    auto list = matjson::Value::array();
    if (arr)
        for (auto lvl : CCArrayExt<GJGameLevel*>(arr)) {
            auto e = matjson::Value::object();
            e["id"] = lvl->m_levelID.value();
            e["name"] = std::string(lvl->m_levelName);
            e["creator"] = std::string(lvl->m_creatorName);
            e["song_id"] = lvl->m_songID;
            e["demon_difficulty"] = lvl->m_demonDifficulty;
            e["has_data"] = !std::string(lvl->m_levelString).empty();
            list.push(e);
        }
    auto v = matjson::Value::object();
    v["levels"] = list;
    r->set(dumpOk(v));
}

// level_delete {name, confirm: name}: удалить ЛОКАЛЬНЫЙ уровень штатной функцией GD (как кнопка
// Delete). Только по явной просьбе пользователя; клиент сначала сохраняет копию (level_export).
BRIDGE_COMMAND(level_delete) {
    auto name = req["name"].asString().unwrapOr("");
    if (name.empty() || req["confirm"].asString().unwrapOr("") != name)
        return r->set(dumpErr("need name and confirm (= name)"));
    auto lvl = findLocalLevel(name);
    if (!lvl) return r->set(dumpErr("local level not found: " + name));
    if (auto ed = LevelEditorLayer::get(); ed && ed->m_level == lvl)
        return r->set(dumpErr("level is open in the editor: editor_exit first"));
    if (auto pl = PlayLayer::get(); pl && pl->m_level == lvl) return r->set(dumpErr("level is being played"));
    GameLevelManager::get()->deleteLevel(lvl);
    LocalLevelManager::get()->save();
    logEvent("level deleted: " + name);
    auto v = matjson::Value::object();
    v["deleted"] = name;
    r->set(dumpOk(v));
}

// level_export {name | id | current=true}: строка уровня (как хранится — обычно сжатая k4)
BRIDGE_COMMAND(level_export) {
    GJGameLevel* lvl = nullptr;
    if (req.contains("name")) lvl = findLocalLevel(req["name"].asString().unwrapOr(""));
    else if (req.contains("id")) lvl = GameLevelManager::get()->getSavedLevel((int)req["id"].asInt().unwrapOr(0));
    else if (auto pl = PlayLayer::get()) lvl = pl->m_level;
    else if (auto ed = LevelEditorLayer::get()) lvl = ed->m_level;
    else if (auto sc = CCDirector::get()->getRunningScene())
        if (auto info = sc->getChildByType<LevelInfoLayer>(0)) lvl = info->m_level;
    if (!lvl) return r->set(dumpErr("level not found"));
    auto v = matjson::Value::object();
    v["id"] = lvl->m_levelID.value();
    v["name"] = std::string(lvl->m_levelName);
    v["creator"] = std::string(lvl->m_creatorName);
    v["song_id"] = lvl->m_songID;
    v["audio_track"] = lvl->m_audioTrack;
    v["level_string"] = std::string(lvl->m_levelString);
    if (v["level_string"].asString().unwrapOr("").empty())
        return r->set(dumpErr("level has no data (open/download it in GD first)"));
    r->set(dumpOk(v));
}
