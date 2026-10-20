// Автозапуск Claude по кнопке «Send to Claude»: мод запускает команду из настроек (по умолчанию
// tools/start_claude.py в папке проекта) скрытым процессом в job-объекте.
// Остановка: job-объект не всегда держит claude.exe (найдено 18.10 — прогон выжил после Stop),
// поэтому запускальщик пишет номера процессов в <project>/out/claude_runs/current.json, а Stop
// убивает деревья этих процессов (с проверкой имени exe — защита от переиспользования номера).
#include <Geode/Geode.hpp>
#include <tlhelp32.h>
#include <chrono>
#include <map>
#include "bridge.hpp"

using namespace geode::prelude;

namespace {
HANDLE g_job = nullptr;
HANDLE g_proc = nullptr;
std::chrono::steady_clock::time_point g_started;
std::string g_state = "idle";

void closeHandles() {
    if (g_proc) CloseHandle(g_proc);
    if (g_job) CloseHandle(g_job);  // KILL_ON_JOB_CLOSE: добивает оставшихся детей в job
    g_proc = g_job = nullptr;
}

std::filesystem::path pidFile() {
    return std::filesystem::path(Mod::get()->getSettingValue<std::string>("project-dir")) / "out" / "claude_runs" /
           "current.json";
}

std::string exeName(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return "";
    wchar_t buf[MAX_PATH];
    DWORD n = MAX_PATH;
    std::string out;
    if (QueryFullProcessImageNameW(h, 0, buf, &n)) out = utils::string::wideToUtf8(std::wstring(buf, n));
    CloseHandle(h);
    for (auto& c : out) c = (char)std::tolower((unsigned char)c);
    return out;
}

// Номера живых процессов прогона из current.json (runner — python, claude — claude.exe).
std::vector<DWORD> runPids() {
    std::vector<DWORD> pids;
    auto txt = utils::file::readString(pidFile());
    if (!txt) return pids;
    auto j = matjson::parse(txt.unwrap());
    if (!j) return pids;
    auto v = j.unwrap();
    for (auto [key, want] : {std::pair<char const*, char const*>{"runner", "python"}, {"claude", "claude"}}) {
        auto pid = (DWORD)v[key].asInt().unwrapOr(0);
        if (pid && exeName(pid).find(want) != std::string::npos) pids.push_back(pid);
    }
    return pids;
}

void killTree(DWORD root) {
    std::multimap<DWORD, DWORD> kids;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap != INVALID_HANDLE_VALUE) {
        PROCESSENTRY32W pe{};
        pe.dwSize = sizeof(pe);
        if (Process32FirstW(snap, &pe))
            do kids.insert({pe.th32ParentProcessID, pe.th32ProcessID});
            while (Process32NextW(snap, &pe));
        CloseHandle(snap);
    }
    std::vector<DWORD> order, stack{root};
    while (!stack.empty()) {
        auto p = stack.back();
        stack.pop_back();
        order.push_back(p);
        auto [a, b] = kids.equal_range(p);
        for (auto it = a; it != b; ++it)
            if (it->second != p) stack.push_back(it->second);
    }
    for (auto it = order.rbegin(); it != order.rend(); ++it) {  // сначала дети
        if (HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, *it)) {
            TerminateProcess(h, 1);
            CloseHandle(h);
        }
    }
}
}  // namespace

namespace bridge {

bool claudeRunning() {
    if (g_proc && WaitForSingleObject(g_proc, 0) == WAIT_OBJECT_0) {
        DWORD code = 0;
        GetExitCodeProcess(g_proc, &code);
        g_state = fmt::format("finished (exit {})", code);
        logEvent("Claude run " + g_state);
        closeHandles();
    }
    if (g_proc) return true;
    return !runPids().empty();  // запускальщик умер, а claude.exe живёт — всё равно «идёт»
}

std::string runState() {
    if (claudeRunning()) {
        if (!g_proc) return "running (detached)";
        auto s = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - g_started).count();
        return fmt::format("running {:02}:{:02}", s / 60, s % 60);
    }
    return g_state;
}

bool startClaude(std::string& err) {
    if (claudeRunning()) {
        err = "Claude is already running";
        return false;
    }
    auto cmd = Mod::get()->getSettingValue<std::string>("claude-command");
    auto dir = Mod::get()->getSettingValue<std::string>("project-dir");
    if (cmd.empty()) {
        err = "claude-command is empty in mod settings";
        return false;
    }
    std::wstring wcmd = utils::string::utf8ToWide(cmd);
    std::wstring wdir = utils::string::utf8ToWide(dir);
    g_job = CreateJobObjectW(nullptr, nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    SetInformationJobObject(g_job, JobObjectExtendedLimitInformation, &info, sizeof(info));
    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    std::vector<wchar_t> buf(wcmd.begin(), wcmd.end());
    buf.push_back(0);
    if (!CreateProcessW(nullptr, buf.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW | CREATE_SUSPENDED, nullptr,
                        wdir.empty() ? nullptr : wdir.c_str(), &si, &pi)) {
        err = fmt::format("cannot start '{}' (error {})", cmd, GetLastError());
        CloseHandle(g_job);
        g_job = nullptr;
        g_state = "failed to start";
        return false;
    }
    AssignProcessToJobObject(g_job, pi.hProcess);
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);
    g_proc = pi.hProcess;
    g_started = std::chrono::steady_clock::now();
    g_state = "running";
    logEvent("Claude run started");
    return true;
}

void stopClaude() {
    auto pids = runPids();
    if (g_job) TerminateJobObject(g_job, 1);
    for (auto pid : pids) killTree(pid);
    closeHandles();
    std::error_code ec;
    std::filesystem::remove(pidFile(), ec);
    g_state = "stopped by user";
    logEvent(fmt::format("Claude run stopped by user (killed {} process trees)", pids.size()));
}

}  // namespace bridge

// run_start: запустить автономный прогон (как кнопка Send при включённом автозапуске)
BRIDGE_COMMAND(run_start) {
    std::string err;
    if (!bridge::startClaude(err)) return r->set(bridge::dumpErr(err));
    auto v = matjson::Value::object();
    v["state"] = bridge::runState();
    r->set(bridge::dumpOk(v));
}

// run_stop: остановить автономный прогон (как кнопка Stop AI)
BRIDGE_COMMAND(run_stop) {
    bool was = bridge::claudeRunning();
    bridge::stopClaude();
    if (was) bridge::markRequestStopped();
    auto v = matjson::Value::object();
    v["stopped"] = was;
    r->set(bridge::dumpOk(v));
}

// run_status: состояние автозапуска (видно и в панели)
BRIDGE_COMMAND(run_status) {
    auto v = matjson::Value::object();
    v["state"] = bridge::runState();
    v["running"] = bridge::claudeRunning();
    r->set(bridge::dumpOk(v));
}
