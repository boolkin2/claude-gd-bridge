// Интерфейс мода в игре: панель Claude (статус сервера и ИИ, журнал, откат действий ИИ), окно заявки
// «новый уровень» (имя, песня, сложность, упор), кнопки в редакторе и в меню Create; команды ui_*,
// request_*. Шрифты GD без кириллицы — русский текст показывается транслитом.
#include <Geode/Geode.hpp>
#include <Geode/modify/CreatorLayer.hpp>
#include <Geode/modify/EditorUI.hpp>
#include <Geode/ui/GeodeUI.hpp>
#include <Geode/ui/Notification.hpp>
#include <Geode/ui/Popup.hpp>
#include <Geode/ui/ScrollLayer.hpp>
#include <Geode/ui/TextInput.hpp>
#include <chrono>
#include <ctime>
#include "bridge.hpp"
#include "net.hpp"

using namespace geode::prelude;
using namespace bridge;

namespace {

std::string toLatin(std::string const& s) {
    static char const* map[] = {
        "A", "B", "V", "G", "D", "E", "Zh", "Z", "I", "Y", "K", "L", "M", "N", "O", "P",
        "R", "S", "T", "U", "F", "Kh", "Ts", "Ch", "Sh", "Shch", "", "Y", "", "E", "Yu", "Ya",
        "a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
        "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"};
    std::string out;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        if (c < 0x80) {
            out.push_back((char)c);
            ++i;
            continue;
        }
        if ((c & 0xE0) == 0xC0 && i + 1 < s.size()) {
            unsigned cp = ((c & 0x1F) << 6) | ((unsigned char)s[i + 1] & 0x3F);
            i += 2;
            if (cp >= 0x410 && cp <= 0x44F) out += map[cp - 0x410];
            else if (cp == 0x401) out += "Yo";
            else if (cp == 0x451) out += "yo";
            else out.push_back('?');
            continue;
        }
        int len = (c & 0xF0) == 0xE0 ? 3 : (c & 0xF8) == 0xF0 ? 4 : 1;
        out.push_back(len == 3 ? '-' : '?');  // тире, кавычки-ёлочки и т.п.
        i += len;
    }
    return out;
}

std::string g_status = "idle";
float g_progress = -1.f;
std::chrono::steady_clock::time_point g_lastNotify{};

// --- заявка «новый уровень» (одна, в save-папке мода) -----------------------------------------
matjson::Value g_request;
bool g_requestLoaded = false;

std::filesystem::path requestPath() { return Mod::get()->getSaveDir() / "request.json"; }

matjson::Value& request() {
    if (!g_requestLoaded) {
        g_requestLoaded = true;
        if (auto txt = utils::file::readString(requestPath()))
            if (auto p = matjson::parse(txt.unwrap())) g_request = p.unwrap();
    }
    return g_request;
}

void saveRequest() { (void)utils::file::writeString(requestPath(), g_request.dump()); }

std::vector<std::string> const kDiffs = {"Auto", "Easy", "Normal", "Hard", "Harder", "Insane",
                                         "Easy Demon", "Medium Demon", "Hard Demon", "Insane Demon",
                                         "Extreme Demon"};
std::vector<std::string> const kFocus = {"Balanced", "Difficulty", "Beauty"};
// модель для автостройки: подпись в окне -> ID для Claude Code (--model)
std::vector<std::pair<std::string, std::string>> const kModels = {{"Sonnet 5.5", "claude-sonnet-5-5"},
                                                                  {"Opus 5.5", "claude-opus-5-5"}};
// уровень размышлений Claude Code (--effort)
std::vector<std::pair<std::string, std::string>> const kEfforts = {
    {"Low", "low"}, {"Medium", "medium"}, {"High", "high"}, {"Extra", "xhigh"}, {"Max", "max"}};
bool needsFocus(int d) { return d >= 8; }  // Hard / Insane / Extreme Demon — спросить упор

CCLabelBMFont* makeLabel(CCNode* parent, Anchor a, CCPoint off, float scale, char const* font = "chatFont.fnt") {
    auto l = CCLabelBMFont::create("", font);
    l->setAnchorPoint({0.f, 0.5f});
    l->setScale(scale);
    parent->addChildAtPosition(l, a, off);
    return l;
}

void setText(CCLabelBMFont* l, std::string const& s, float width, float scale) {
    l->setString(s.c_str());
    l->limitLabelWidth(width, scale, 0.2f);
}

CCMenuItemSpriteExtra* arrow(bool right, geode::Function<void(CCMenuItemSpriteExtra*)> cb) {
    auto spr = CCSprite::createWithSpriteFrameName("GJ_arrow_01_001.png");
    spr->setScale(0.45f);
    spr->setFlipX(right);
    return CCMenuItemExt::createSpriteExtra(spr, std::move(cb));
}

// --- референсы для анализа: черновик выбора и окно -------------------------------------------------
struct RefEntry {
    int id = 0;  // 0 — вписан текстом (название)
    std::string name, creator, text;
    bool downloaded = false;
    bool selected = false;
};
std::vector<RefEntry> g_refs;

void loadRefsFromRequest() {
    g_refs.clear();
    auto& rq = request();
    if (!rq.isObject() || !rq.contains("references")) return;  // operator[] создал бы ключ
    if (auto arr = rq["references"].asArray())
        for (auto& it : arr.unwrap()) {
            RefEntry e;
            e.id = (int)it["id"].asInt().unwrapOr(0);
            e.name = it["name"].asString().unwrapOr("");
            e.creator = it["creator"].asString().unwrapOr("");
            e.text = it["text"].asString().unwrapOr("");
            e.downloaded = it["downloaded"].asBool().unwrapOr(false);
            e.selected = true;
            g_refs.push_back(e);
        }
}

matjson::Value refsJson() {
    auto arr = matjson::Value::array();
    for (auto& e : g_refs) {
        if (!e.selected) continue;
        auto o = matjson::Value::object();
        if (e.id) {
            o["id"] = e.id;
            o["name"] = e.name;
            o["creator"] = e.creator;
            o["downloaded"] = e.downloaded;
        } else {
            o["text"] = e.text;
        }
        arr.push(o);
    }
    return arr;
}

int refsSelected() {
    int n = 0;
    for (auto& e : g_refs) n += e.selected;
    return n;
}

// Окно «Reference levels»: отметить скачанные уровни и/или вписать ID/название.
class ReferencesPopup : public Popup {
protected:
    TextInput* m_input = nullptr;
    ScrollLayer* m_list = nullptr;
    std::function<void()> m_onDone;

    void mergeSaved() {
        auto arr = GameLevelManager::get()->getSavedLevels(false, 0);
        if (!arr) return;
        for (auto lvl : CCArrayExt<GJGameLevel*>(arr)) {
            int id = lvl->m_levelID.value();
            bool has = !std::string(lvl->m_levelString).empty();
            auto it = std::find_if(g_refs.begin(), g_refs.end(), [&](auto& e) { return e.id == id; });
            if (it != g_refs.end()) {
                it->name = std::string(lvl->m_levelName);
                it->creator = std::string(lvl->m_creatorName);
                it->downloaded = has;
                continue;
            }
            RefEntry e;
            e.id = id;
            e.name = std::string(lvl->m_levelName);
            e.creator = std::string(lvl->m_creatorName);
            e.downloaded = has;
            g_refs.push_back(e);
        }
    }

    void rebuildList() {
        auto content = m_list->m_contentLayer;
        content->removeAllChildren();
        for (size_t i = 0; i < g_refs.size(); ++i) {
            auto& e = g_refs[i];
            auto row = CCNode::create();
            row->setContentSize({360.f, 22.f});
            auto menu = CCMenu::create();
            menu->setContentSize({360.f, 22.f});
            menu->setPosition({0.f, 0.f});
            auto tog = CCMenuItemExt::createTogglerWithStandardSprites(0.5f, [i](CCMenuItemToggler* t) {
                if (i < g_refs.size()) g_refs[i].selected = !t->isToggled();  // в колбэке — старое состояние
            });
            tog->toggle(e.selected);
            tog->setPosition({14.f, 11.f});
            menu->addChild(tog);
            row->addChild(menu);
            std::string text = e.id ? fmt::format("{}  ({})  by {}{}", toLatin(e.name), e.id, toLatin(e.creator),
                                                  e.downloaded ? "" : "  - not downloaded")
                                    : fmt::format("\"{}\"  (typed)", toLatin(e.text));
            auto lbl = CCLabelBMFont::create(text.c_str(), "chatFont.fnt");
            lbl->setAnchorPoint({0.f, 0.5f});
            lbl->setPosition({30.f, 11.f});
            lbl->limitLabelWidth(320.f, 0.5f, 0.2f);
            if (e.id && !e.downloaded) lbl->setColor({170, 170, 170});
            row->addChild(lbl);
            content->addChild(row);
        }
        content->updateLayout();
        m_list->scrollToTop();
        handleTouchPriority(this);
    }

    void onAdd() {
        std::string t = m_input->getString();
        if (t.empty()) return;
        bool digits = std::all_of(t.begin(), t.end(), [](char c) { return c >= '0' && c <= '9'; });
        if (digits) {
            int id = std::atoi(t.c_str());
            auto it = std::find_if(g_refs.begin(), g_refs.end(), [&](auto& e) { return e.id == id; });
            if (it != g_refs.end()) it->selected = true;
            else {
                RefEntry e;
                e.id = id;
                e.name = "level " + t;
                e.selected = true;
                g_refs.insert(g_refs.begin(), e);
            }
        } else {
            RefEntry e;
            e.text = t;
            e.selected = true;
            g_refs.insert(g_refs.begin(), e);
        }
        m_input->setString("");
        rebuildList();
    }

    bool init(std::function<void()> onDone) {
        if (!Popup::init(400.f, 280.f)) return false;
        this->setTitle("Reference levels", "goldFont.fnt", .65f, 18.f);
        m_onDone = std::move(onDone);
        mergeSaved();
        m_input = TextInput::create(250.f, "level ID or name (latin)", "chatFont.fnt");
        m_input->setScale(0.85f);
        m_mainLayer->addChildAtPosition(m_input, Anchor::Top, ccp(-40, -45));
        auto addSpr = ButtonSprite::create("Add", "goldFont.fnt", "GJ_button_01.png", .6f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(addSpr, [this](auto) { onAdd(); }),
                                         Anchor::Top, ccp(130, -45));
        auto hint = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, -68), 0.38f);
        setText(hint, "Tick levels Claude may study. Nothing ticked = Claude picks from your downloaded levels.",
                360.f, 0.38f);
        auto bg = CCLayerColor::create({0, 0, 0, 70}, 360.f, 150.f);
        m_mainLayer->addChildAtPosition(bg, Anchor::Center, ccp(-180, -98));
        m_list = ScrollLayer::create(CCSize(360.f, 150.f));
        m_list->m_contentLayer->setLayout(ScrollLayer::createDefaultListLayout(1.f));
        m_mainLayer->addChildAtPosition(m_list, Anchor::Center, ccp(-180, -98));
        auto doneSpr = ButtonSprite::create("Done", "goldFont.fnt", "GJ_button_01.png", .7f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(doneSpr, [this](auto) {
            if (m_onDone) m_onDone();
            this->onClose(nullptr);
        }), Anchor::Bottom, ccp(0, 20));
        rebuildList();
        return true;
    }

public:
    static ReferencesPopup* create(std::function<void()> onDone) {
        auto ret = new ReferencesPopup();
        if (ret->init(std::move(onDone))) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }
};

// Окно «Claude settings»: модель и уровень размышлений для автостройки.
class AiPopup : public Popup {
protected:
    int* m_model = nullptr;
    int* m_effort = nullptr;
    CCLabelBMFont* m_modelLabel = nullptr;
    CCLabelBMFont* m_effortLabel = nullptr;
    std::function<void()> m_onDone;

    void row(char const* label, float y, CCLabelBMFont*& value, geode::Function<void(int)> step) {
        auto lbl = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, y), 0.5f, "goldFont.fnt");
        lbl->setString(label);
        auto sl = std::make_shared<geode::Function<void(int)>>(std::move(step));
        m_buttonMenu->addChildAtPosition(arrow(false, [sl](auto) { (*sl)(-1); }), Anchor::TopRight, ccp(-205, y));
        m_buttonMenu->addChildAtPosition(arrow(true, [sl](auto) { (*sl)(+1); }), Anchor::TopRight, ccp(-30, y));
        value = CCLabelBMFont::create("", "bigFont.fnt");
        value->setScale(0.45f);
        m_mainLayer->addChildAtPosition(value, Anchor::TopRight, ccp(-117, y));
    }

    void update() {
        setText(m_modelLabel, kModels[*m_model].first, 150.f, 0.45f);
        setText(m_effortLabel, kEfforts[*m_effort].first, 150.f, 0.45f);
    }

    bool init(int* model, int* effort, std::function<void()> onDone) {
        if (!Popup::init(340.f, 190.f)) return false;
        this->setTitle("Claude settings", "goldFont.fnt", .65f, 18.f);
        m_model = model;
        m_effort = effort;
        m_onDone = std::move(onDone);
        row("Model", -50, m_modelLabel, [this](int d) {
            *m_model = (*m_model + d + (int)kModels.size()) % (int)kModels.size();
            update();
        });
        row("Thinking", -85, m_effortLabel, [this](int d) {
            *m_effort = (*m_effort + d + (int)kEfforts.size()) % (int)kEfforts.size();
            update();
        });
        auto hint = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, -112), 0.36f);
        setText(hint, "More thinking = better levels, slower, uses more of your plan limit.", 300.f, 0.36f);
        auto spr = ButtonSprite::create("Done", "goldFont.fnt", "GJ_button_01.png", .7f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(spr, [this](auto) {
            if (m_onDone) m_onDone();
            this->onClose(nullptr);
        }), Anchor::Bottom, ccp(0, 24));
        update();
        return true;
    }

public:
    static AiPopup* create(int* model, int* effort, std::function<void()> onDone) {
        auto ret = new AiPopup();
        if (ret->init(model, effort, std::move(onDone))) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }
};

// --- окно заявки -----------------------------------------------------------------------------------
class RequestPopup : public Popup {
protected:
    TextInput* m_name = nullptr;
    TextInput* m_song = nullptr;
    TextInput* m_file = nullptr;
    TextInput* m_notes = nullptr;
    CCLabelBMFont* m_diffLabel = nullptr;
    CCLabelBMFont* m_focusLabel = nullptr;
    CCMenuItemSpriteExtra* m_focusL = nullptr;
    CCMenuItemSpriteExtra* m_focusR = nullptr;
    int m_diff = 5;
    int m_focus = 0;
    int m_model = 0;
    int m_effort = 2;   // High
    ButtonSprite* m_aiBtn = nullptr;
    ButtonSprite* m_refsBtn = nullptr;

    void updateRefsButton() {
        int n = refsSelected();
        m_refsBtn->setString(n ? fmt::format("Choose ({})", n).c_str() : "Choose (auto)");
    }

    TextInput* addInput(char const* label, char const* ph, float y, CommonFilter f) {
        auto lbl = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, y), 0.45f, "goldFont.fnt");
        lbl->setString(label);
        auto in = TextInput::create(250.f, ph, "chatFont.fnt");
        in->setCommonFilter(f);
        in->setScale(0.9f);
        m_mainLayer->addChildAtPosition(in, Anchor::TopRight, ccp(-140, y));
        return in;
    }

    void addSelector(char const* label, float y, CCLabelBMFont*& value, CCMenuItemSpriteExtra** l,
                     CCMenuItemSpriteExtra** r, geode::Function<void(int)> step) {
        auto lbl = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, y), 0.45f, "goldFont.fnt");
        lbl->setString(label);
        auto sl = std::make_shared<geode::Function<void(int)>>(std::move(step));
        auto left = arrow(false, [sl](auto) { (*sl)(-1); });
        auto right = arrow(true, [sl](auto) { (*sl)(+1); });
        m_buttonMenu->addChildAtPosition(left, Anchor::TopRight, ccp(-245, y));
        m_buttonMenu->addChildAtPosition(right, Anchor::TopRight, ccp(-35, y));
        value = CCLabelBMFont::create("", "bigFont.fnt");
        value->setScale(0.45f);
        m_mainLayer->addChildAtPosition(value, Anchor::TopRight, ccp(-140, y));
        if (l) *l = left;
        if (r) *r = right;
    }

    void updateSelectors() {
        setText(m_diffLabel, kDiffs[m_diff], 180.f, 0.45f);
        bool f = needsFocus(m_diff);
        setText(m_focusLabel, f ? kFocus[m_focus] : "Beauty (auto)", 180.f, 0.45f);
        m_focusL->setVisible(f);
        m_focusR->setVisible(f);
        if (m_aiBtn) m_aiBtn->setString((kModels[m_model].first + " - " + kEfforts[m_effort].first).c_str());
    }

    bool init() {
        if (!Popup::init(400.f, 292.f)) return false;
        this->setTitle("New level for Claude", "goldFont.fnt", .65f, 18.f);
        m_name = addInput("Name", "level name", -40, CommonFilter::Any);
        m_song = addInput("Song ID", "Newgrounds / library ID", -66, CommonFilter::Uint);
        m_file = addInput("Song file", "optional: path to .mp3 (latin letters)", -92, CommonFilter::Any);
        addSelector("Difficulty", -118, m_diffLabel, nullptr, nullptr, [this](int d) {
            m_diff = (m_diff + d + (int)kDiffs.size()) % (int)kDiffs.size();
            updateSelectors();
        });
        addSelector("Focus", -142, m_focusLabel, &m_focusL, &m_focusR, [this](int d) {
            m_focus = (m_focus + d + (int)kFocus.size()) % (int)kFocus.size();
            updateSelectors();
        });
        m_notes = addInput("Notes", "style, ideas for Claude (latin)", -168, CommonFilter::Any);
        auto cl = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, -220), 0.45f, "goldFont.fnt");
        cl->setString("Claude");
        m_aiBtn = ButtonSprite::create("Sonnet 5.5 - High", 190, true, "goldFont.fnt", "GJ_button_04.png", 26.f, .5f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(m_aiBtn, [this](auto) {
            AiPopup::create(&m_model, &m_effort, [this]() { updateSelectors(); })->show();
        }), Anchor::TopRight, ccp(-140, -220));
        auto rl = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(20, -194), 0.45f, "goldFont.fnt");
        rl->setString("References");
        m_refsBtn = ButtonSprite::create("Choose (auto)", 150, true, "goldFont.fnt", "GJ_button_04.png", 26.f, .5f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(m_refsBtn, [this](auto) {
            ReferencesPopup::create([this]() { updateRefsButton(); })->show();
        }), Anchor::TopRight, ccp(-140, -194));
        auto spr = ButtonSprite::create("Send to Claude", "goldFont.fnt", "GJ_button_01.png", .7f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(spr, [this](auto) { onSend(); }),
                                         Anchor::Bottom, ccp(0, 24));
        // заполнить из прошлой заявки
        auto& rq = request();
        if (rq.isObject() && rq.contains("name")) {
            m_name->setString(rq["name"].asString().unwrapOr(""));
            if (auto s = rq["song_id"].asInt().unwrapOr(0)) m_song->setString(std::to_string(s));
            m_file->setString(rq["song_file"].asString().unwrapOr(""));
            m_notes->setString(rq["notes"].asString().unwrapOr(""));
            auto d = rq["difficulty"].asString().unwrapOr("");
            for (size_t i = 0; i < kDiffs.size(); ++i) if (kDiffs[i] == d) m_diff = (int)i;
            auto f = rq["focus"].asString().unwrapOr("");
            for (size_t i = 0; i < kFocus.size(); ++i) if (kFocus[i] == f) m_focus = (int)i;
            auto mo = rq["model"].asString().unwrapOr("");
            for (size_t i = 0; i < kModels.size(); ++i) if (kModels[i].second == mo) m_model = (int)i;
            auto ef = rq["effort"].asString().unwrapOr("");
            for (size_t i = 0; i < kEfforts.size(); ++i) if (kEfforts[i].second == ef) m_effort = (int)i;
        }
        loadRefsFromRequest();
        updateRefsButton();
        updateSelectors();
        return true;
    }

    void onSend() {
        std::string name = m_name->getString();
        if (name.empty()) {
            Notification::create("Enter a level name", NotificationIcon::Error, 2.f)->show();
            return;
        }
        auto rq = matjson::Value::object();
        rq["name"] = name;
        rq["song_id"] = std::atoi(std::string(m_song->getString()).c_str());
        rq["song_file"] = std::string(m_file->getString());
        rq["difficulty"] = kDiffs[m_diff];
        rq["focus"] = needsFocus(m_diff) ? kFocus[m_focus] : "Beauty";
        rq["focus_asked"] = needsFocus(m_diff);
        rq["notes"] = std::string(m_notes->getString());
        rq["references"] = refsJson();
        rq["model"] = kModels[m_model].second;
        rq["model_name"] = kModels[m_model].first;
        rq["effort"] = kEfforts[m_effort].second;
        rq["effort_name"] = kEfforts[m_effort].first;
        rq["status"] = "pending";
        rq["message"] = "";
        rq["created"] = (int64_t)std::time(nullptr);
        bool autoStart = setting("auto-start");
        rq["auto_start"] = autoStart;
        request() = rq;
        saveRequest();
        logEvent("request: " + name + " (" + kDiffs[m_diff] + ")");
        if (autoStart) {
            std::string err;
            if (startClaude(err)) {
                request()["message"] = "Claude is starting";
                saveRequest();
                Notification::create("Claude started - progress in the Claude panel", NotificationIcon::Success, 4.f)
                    ->show();
            } else {
                request()["message"] = err;
                saveRequest();
                Notification::create("Cannot start Claude: " + err, NotificationIcon::Error, 5.f)->show();
            }
        } else {
            Notification::create("Saved. Tell Claude in chat: take the request from GD", NotificationIcon::Success, 4.f)
                ->show();
        }
        this->onClose(nullptr);
    }

public:
    static RequestPopup* create() {
        auto ret = new RequestPopup();
        if (ret->init()) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }
};

// --- панель Claude --------------------------------------------------------------------------------
class ClaudePanel : public Popup {
protected:
    CCLabelBMFont* m_server = nullptr;
    CCLabelBMFont* m_ai = nullptr;
    CCLabelBMFont* m_req = nullptr;
    CCLabelBMFont* m_editor = nullptr;
    CCLabelBMFont* m_run = nullptr;
    std::vector<CCLabelBMFont*> m_log;

    void addBtn(char const* text, float x, geode::Function<void(CCMenuItemSpriteExtra*)> cb) {
        auto spr = ButtonSprite::create(text, 70, true, "goldFont.fnt", "GJ_button_04.png", 26.f, .5f);
        spr->setScale(0.9f);
        m_buttonMenu->addChildAtPosition(CCMenuItemExt::createSpriteExtra(spr, std::move(cb)), Anchor::Bottom,
                                         ccp(x, 20));
    }

    bool init() {
        if (!Popup::init(400.f, 245.f)) return false;
        this->setTitle("Claude Bridge", "goldFont.fnt", .65f, 18.f);
        m_server = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -38), 0.42f);
        m_run = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -52), 0.42f);
        m_ai = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -66), 0.42f);
        m_req = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -80), 0.42f);
        m_editor = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -94), 0.42f);
        auto t = makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -110), 0.38f, "goldFont.fnt");
        t->setString("Recent AI actions");
        for (int i = 0; i < 6; ++i) m_log.push_back(makeLabel(m_mainLayer, Anchor::TopLeft, ccp(16, -123 - 12.f * i), 0.36f));
        addBtn("Undo AI", -152, [](auto) { undoAI(); });
        addBtn("New Level", -76, [](auto) { RequestPopup::create()->show(); });
        addBtn("Stop AI", 0, [](auto) { stopAI(); });
        addBtn("Settings", 76, [](auto) { openSettingsPopup(Mod::get()); });
        addBtn("Help", 152, [](auto) {
            FLAlertLayer::create(
                "Claude Bridge",
                "1. <cy>New Level</c>: name, song, difficulty, reference levels -> <cg>Send to Claude</c>.\n"
                "2. Claude starts by itself (setting <cy>Start Claude on Send</c>) and builds in the editor.\n"
                "3. Progress is shown here. <cr>Stop AI</c> cancels, <cy>Undo AI</c> reverts the last AI action.",
                "OK")->show();
        });
        this->refresh(0.f);
        this->schedule(schedule_selector(ClaudePanel::refresh), 0.5f);
        return true;
    }

    static void stopAI() {
        if (!claudeRunning()) {
            Notification::create("Claude is not running", NotificationIcon::Info, 2.f)->show();
            return;
        }
        stopClaude();
        markRequestStopped();
        Notification::create("Claude stopped", NotificationIcon::Warning, 2.f)->show();
    }

    static void undoAI() {
        if (!LevelEditorLayer::get()) {
            Notification::create("Open the level in the editor first", NotificationIcon::Warning, 2.f)->show();
            return;
        }
        auto out = runCommandSync("editor_undo", matjson::Value::object());
        auto p = matjson::parse(out);
        bool ok = p && p.unwrap()["ok"].asBool().unwrapOr(false);
        Notification::create(ok ? "Last AI action undone" : "Nothing to undo",
                             ok ? NotificationIcon::Success : NotificationIcon::Info, 2.f)->show();
    }

    void refresh(float) {
        bool on = setting("server-enabled");
        auto port = Mod::get()->getSettingValue<int64_t>("port");
        setText(m_server,
                fmt::format("Server: {}   port {}   clients {}{}",
                            !on ? "OFF" : (bridge_net::listening() ? "ON" : "FAILED (port busy?)"), port,
                            bridge_net::clientCount(), setting("read-only") ? "   [read-only]" : ""),
                370.f, 0.42f);
        setText(m_run, std::string("Claude run: ") + runState() +
                            (setting("auto-start") ? "" : "   (auto start off)"), 370.f, 0.42f);
        auto prog = aiProgress();
        setText(m_ai, "AI: " + toLatin(aiStatus()) + (prog >= 0 ? fmt::format("   {:.0f}%", prog * 100) : ""), 370.f,
                0.42f);
        auto& rq = request();
        if (rq.isObject() && rq.contains("name"))
            setText(m_req,
                    fmt::format("Request: {}  [{}, {}, {}]  - {} {}", toLatin(rq["name"].asString().unwrapOr("")),
                                rq["difficulty"].asString().unwrapOr(""), rq["focus"].asString().unwrapOr(""),
                                rq["model_name"].asString().unwrapOr("Sonnet 5.5") + " " +
                                    rq["effort_name"].asString().unwrapOr(""),
                                rq["status"].asString().unwrapOr(""),
                                toLatin(rq["message"].asString().unwrapOr(""))),
                    370.f, 0.42f);
        else
            setText(m_req, "Request: none (press New Level)", 370.f, 0.42f);
        if (auto ed = LevelEditorLayer::get()) {
            int n = 0;
            if (auto p = matjson::parse(runCommandSync("editor_history", matjson::Value::object())))
                if (auto arr = p.unwrap()["history"].asArray()) n = (int)arr.unwrap().size();
            setText(m_editor,
                    fmt::format("Editor: {}   objects {}   AI actions {}", toLatin(ed->m_level->m_levelName),
                                ed->m_objects->count(), n),
                    370.f, 0.42f);
        } else {
            setText(m_editor, "Editor: closed", 370.f, 0.42f);
        }
        auto log = recentLog(m_log.size());
        for (size_t i = 0; i < m_log.size(); ++i) setText(m_log[i], i < log.size() ? toLatin(log[i]) : "", 370.f, 0.36f);
    }

public:
    static ClaudePanel* create() {
        auto ret = new ClaudePanel();
        if (ret->init()) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }
};

NotificationIcon iconOf(std::string const& s) {
    if (s == "success") return NotificationIcon::Success;
    if (s == "error") return NotificationIcon::Error;
    if (s == "warning") return NotificationIcon::Warning;
    if (s == "loading") return NotificationIcon::Loading;
    return NotificationIcon::Info;
}

}  // namespace

namespace bridge {
void markRequestStopped() {
    auto& rq = request();
    if (rq.isObject() && rq.contains("name")) {
        rq["status"] = "stopped";
        rq["message"] = "stopped by user";
        saveRequest();
    }
    g_status = "stopped by user";
    g_progress = -1.f;
}

void notify(std::string const& text, bool force) {
    auto now = std::chrono::steady_clock::now();
    if (!force && now - g_lastNotify < std::chrono::milliseconds(1500)) return;
    g_lastNotify = now;
    Notification::create(toLatin(text), NotificationIcon::Info, 2.f)->show();
}
std::string aiStatus() { return g_status; }
float aiProgress() { return g_progress; }
}  // namespace bridge

// --- команды интерфейса -----------------------------------------------------------------------------

// ui_notify {text, icon: info|success|warning|error|loading, time=3}: сообщение игроку в игре
BRIDGE_COMMAND(ui_notify) {
    auto text = req["text"].asString().unwrapOr("");
    Notification::create(toLatin(text), iconOf(req["icon"].asString().unwrapOr("info")),
                         (float)req["time"].asDouble().unwrapOr(3.0))->show();
    r->set(dumpOk(matjson::Value::object()));
}

// ui_status {text, progress?: 0..1}: строка «AI: ...» в панели (что ИИ сейчас делает)
BRIDGE_COMMAND(ui_status) {
    g_status = req["text"].asString().unwrapOr(g_status);
    g_progress = req.contains("progress") ? (float)req["progress"].asDouble().unwrapOr(-1) : -1.f;
    logEvent("status: " + g_status);
    r->set(dumpOk(matjson::Value::object()));
}

// ui_open {panel: main|request|settings}: открыть окно мода (для проверки и подсказки игроку)
BRIDGE_COMMAND(ui_open) {
    auto p = req["panel"].asString().unwrapOr("main");
    if (p == "request") RequestPopup::create()->show();
    else if (p == "references") {
        loadRefsFromRequest();
        ReferencesPopup::create(nullptr)->show();
    }
    else if (p == "settings") openSettingsPopup(Mod::get());
    else ClaudePanel::create()->show();
    r->set(dumpOk(matjson::Value::object()));
}

// request_get: заявка «новый уровень» из игры (или null)
BRIDGE_COMMAND(request_get) {
    auto v = matjson::Value::object();
    auto& rq = request();
    v["request"] = rq.isObject() && rq.contains("name") ? rq : matjson::Value(nullptr);
    r->set(dumpOk(v));
}

// request_set {fields...}: создать/дополнить заявку из чата (как окно New Level, без запуска)
BRIDGE_COMMAND(request_set) {
    auto& rq = request();
    if (!rq.isObject() || req["new"].asBool().unwrapOr(false)) rq = matjson::Value::object();
    if (req["fields"].isObject())
        for (auto& [k, val] : req["fields"]) rq[k] = val;
    if (!rq.contains("status")) rq["status"] = "pending";
    if (!rq.contains("created")) rq["created"] = (int64_t)std::time(nullptr);
    saveRequest();
    logEvent("request set: " + rq["name"].asString().unwrapOr("?"));
    r->set(dumpOk(rq));
}

// request_status {status: pending|accepted|building|done|cancelled, message}: видно в панели
BRIDGE_COMMAND(request_status) {
    auto& rq = request();
    if (!rq.isObject() || !rq.contains("name")) return r->set(dumpErr("no request"));
    if (req.contains("status")) rq["status"] = req["status"].asString().unwrapOr("");
    if (req.contains("message")) rq["message"] = req["message"].asString().unwrapOr("");
    saveRequest();
    logEvent("request " + rq["status"].asString().unwrapOr("") + ": " + rq["message"].asString().unwrapOr(""));
    r->set(dumpOk(rq));
}

// ui_nodes {id?}: проверить интерфейс без скриншота — есть ли узел с ID (поиск по всей сцене),
// и верхний уровень сцены (тип и ID детей)
BRIDGE_COMMAND(ui_nodes) {
    auto v = matjson::Value::object();
    auto sc = CCDirector::get()->getRunningScene();
    if (!sc) return r->set(dumpErr("no scene"));
    if (req.contains("id")) {
        auto id = req["id"].asString().unwrapOr("");
        auto n = sc->getChildByIDRecursive(id);
        v["found"] = n != nullptr;
        if (n) {
            v["visible"] = n->isVisible();
            auto p = n->convertToWorldSpaceAR(CCPoint(0, 0));
            v["world"] = matjson::Value(std::vector<matjson::Value>{p.x, p.y});
        }
    }
    auto list = matjson::Value::array();
    for (auto ch : CCArrayExt<CCNode*>(sc->getChildren())) {
        auto e = matjson::Value::object();
        e["type"] = typeid(*ch).name();
        e["id"] = std::string(ch->getID());
        list.push(e);
    }
    v["children"] = list;
    auto win = CCDirector::get()->getWinSize();
    v["win"] = matjson::Value(std::vector<matjson::Value>{win.width, win.height});
    r->set(dumpOk(v));
}

// --- кнопки в игре ---------------------------------------------------------------------------------
class $modify(ClaudeEditorUI, EditorUI) {
    bool init(LevelEditorLayer* lel) {
        if (!EditorUI::init(lel)) return false;
        if (!Mod::get()->getSettingValue<bool>("editor-button")) return true;
        auto spr = ButtonSprite::create("AI", "bigFont.fnt", "GJ_button_04.png", .55f);
        auto btn = CCMenuItemExt::createSpriteExtra(spr, [](auto) { ClaudePanel::create()->show(); });
        btn->setID("claude-button"_spr);
        auto menu = CCMenu::create();
        menu->setID("claude-menu"_spr);
        menu->addChild(btn);
        auto win = CCDirector::get()->getWinSize();
        menu->setPosition(win.width - 125.f, win.height - 22.f);
        this->addChild(menu, 100);
        return true;
    }
};

class $modify(ClaudeCreatorLayer, CreatorLayer) {
    bool init() {
        if (!CreatorLayer::init()) return false;
        auto spr = ButtonSprite::create("Claude AI", "goldFont.fnt", "GJ_button_04.png", .7f);
        auto btn = CCMenuItemExt::createSpriteExtra(spr, [](auto) { ClaudePanel::create()->show(); });
        auto menu = CCMenu::create();
        menu->setID("claude-menu"_spr);
        menu->addChild(btn);
        auto win = CCDirector::get()->getWinSize();
        menu->setPosition(win.width - 75.f, 28.f);
        this->addChild(menu, 10);
        return true;
    }
};
