#pragma once
#include <functional>
#include <string>

namespace bridge_net {
    // Сервер 127.0.0.1:port, поток на клиента; строка запроса -> handler -> строка ответа.
    // handler вызывается в потоке клиента.
    void start(unsigned short port, std::function<std::string(std::string const&)> handler);
    // Сколько клиентов подключено сейчас; удалось ли открыть порт.
    int clientCount();
    bool listening();
}
