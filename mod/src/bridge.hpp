// Общее для файлов мода claude.bridge: ответы, реестр команд, ожидание переходов сцен, журнал.
#pragma once
#include <Geode/Geode.hpp>
#include <atomic>
#include <functional>
#include <future>
#include <string>
#include <vector>

namespace bridge {

struct Reply {
    std::promise<std::string> p;
    std::atomic<bool> done{false};
    void set(std::string s) {
        if (!done.exchange(true)) p.set_value(std::move(s));
    }
};
using ReplyPtr = std::shared_ptr<Reply>;
using Handler = std::function<void(matjson::Value const&, ReplyPtr)>;

// Команды регистрируются статически (из любого файла) и выполняются в главном потоке.
void registerCommand(std::string const& name, Handler h);
std::vector<std::string> commandNames();

std::string dumpOk(matjson::Value v);
std::string dumpErr(std::string const& e);

char const* typeClass(GameObjectType t);
matjson::Value rectJson(cocos2d::CCRect const& r);
matjson::Value objectJson(GameObject* o);

GJGameLevel* findLocalLevel(std::string const& name, int* index = nullptr);
void quitPlayLayer();
bool runActive();
// Нет ни PlayLayer, ни редактора, и не идёт переход сцен.
bool sceneSettled();

// Функция вызывается каждый кадр в главном потоке, пока не вернёт true (ожидание переходов сцен).
void addWaiter(std::function<bool()> w);

// Журнал команд и событий (для интерфейса в игре).
void logEvent(std::string const& s);
std::vector<std::string> recentLog(size_t n);

// Выполнить зарегистрированную команду из кода мода (интерфейс): ответ, если команда ответила сразу.
std::string runCommandSync(std::string const& name, matjson::Value req);

// Настройки мода (страница настроек Geode).
bool setting(char const* key);

// Игрок: режим строкой; объекты, касающиеся хитбокса игрока (с запасом pad), ближние первыми.
char const* modeName(PlayerObject* p);
matjson::Value contactsJson(GJBaseGameLayer* layer, PlayerObject* p, float pad, size_t limit);
// Сессия бота-поисковика (sim.cpp) открыта.
bool simActive();

// Интерфейс (ui.cpp): уведомление в игре (с ограничением частоты), строка статуса ИИ.
void notify(std::string const& text, bool force = false);
std::string aiStatus();
float aiProgress();

// Бэкап уровня редактора перед первой правкой ИИ в этой сессии редактора (editor.cpp).
void backupBeforeEdit(LevelEditorLayer* ed);

// Автозапуск Claude (runner.cpp): фоновый процесс из настроек мода.
bool startClaude(std::string& err);
void stopClaude();
bool claudeRunning();
std::string runState();
// Пометить заявку «stopped» и сбросить строку статуса ИИ (ui.cpp).
void markRequestStopped();

}  // namespace bridge

// Регистрация команды при загрузке DLL: BRIDGE_COMMAND(editor_add) { ... req, r ... }
#define BRIDGE_CMD_CAT2(a, b) a##b
#define BRIDGE_CMD_CAT(a, b) BRIDGE_CMD_CAT2(a, b)
#define BRIDGE_COMMAND(name)                                                                      \
    static void BRIDGE_CMD_CAT(cmd_, name)(matjson::Value const& req, bridge::ReplyPtr r);       \
    static int BRIDGE_CMD_CAT(reg_, name) = (bridge::registerCommand(#name, BRIDGE_CMD_CAT(cmd_, name)), 0); \
    static void BRIDGE_CMD_CAT(cmd_, name)(matjson::Value const& req, bridge::ReplyPtr r)
