#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <atomic>
#include <thread>
#include "net.hpp"

namespace bridge_net {

static std::atomic<int> g_clients{0};
static std::atomic<bool> g_listening{false};
int clientCount() { return g_clients.load(); }
bool listening() { return g_listening.load(); }

static void serveClient(SOCKET c, std::function<std::string(std::string const&)> const& handler) {
    std::string buf;
    char chunk[65536];
    for (;;) {
        int n = recv(c, chunk, sizeof(chunk), 0);
        if (n <= 0) break;
        buf.append(chunk, n);
        size_t pos;
        while ((pos = buf.find('\n')) != std::string::npos) {
            std::string line = buf.substr(0, pos);
            buf.erase(0, pos + 1);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;
            std::string out = handler(line);
            out.push_back('\n');
            size_t sent = 0;
            while (sent < out.size()) {
                int k = send(c, out.data() + sent, (int)std::min<size_t>(out.size() - sent, 1 << 20), 0);
                if (k <= 0) return;
                sent += k;
            }
        }
    }
}

void start(unsigned short port, std::function<std::string(std::string const&)> handler) {
    std::thread([port, handler]() {
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return;
        SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (s == INVALID_SOCKET) return;
        BOOL yes = TRUE;
        setsockopt(s, SOL_SOCKET, SO_REUSEADDR, (char const*)&yes, sizeof(yes));
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
        if (bind(s, (sockaddr*)&addr, sizeof(addr)) != 0 || listen(s, 4) != 0) {
            closesocket(s);
            return;
        }
        g_listening = true;
        for (;;) {
            SOCKET c = accept(s, nullptr, nullptr);
            if (c == INVALID_SOCKET) continue;
            BOOL nd = TRUE;
            setsockopt(c, IPPROTO_TCP, TCP_NODELAY, (char const*)&nd, sizeof(nd));
            // поток на клиента: ping/abort отвечают, пока другой клиент ждёт длинный play
            std::thread([c, handler]() {
                g_clients++;
                serveClient(c, handler);
                closesocket(c);
                g_clients--;
            }).detach();
        }
    }).detach();
}

}
