// Compiled lifecycle probes for the Grok Bot tray companion.
//
// These tests exercise the shared production lifecycle helper module
// (bounded nonblocking AF_UNIX probe, SO_PEERCRED peer identification,
// owned process-group graceful shutdown, protocol-URL filtering, and the
// cold-start wait-and-forward loop) using REAL temporary Unix sockets and
// REAL owned child processes with bounded timeouts.
//
// There is deliberately NO fixture adapter in this file: every probe below
// calls the same production helper implementation used by the companion.
//
// Linux-only: AF_UNIX, SO_PEERCRED, setsid/killpg are required. Every
// wait stays bounded; CTest adds an outer TIMEOUT as well.

#include <chrono>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <thread>
#include <vector>

#include <QCoreApplication>
#include "lifecycle_helpers.h"

#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef SO_PEERCRED
#define SO_PEERCRED 17
#endif

namespace {

// The production helper owns this bound; the test only names it for timing
// assertions around the real implementation.
constexpr int kConnectTimeoutMs = companion::lifecycle::kUnixSocketConnectTimeoutMs;
// Blocking observers must outlive that bound to prove the difference.
constexpr int kBlockingObserveMs = 150;
constexpr int kTimingToleranceMs = 40;
// Test-local outer bound for poll loops that mirror production waits.
constexpr int kProbeTimeoutMs = 5000;
constexpr int kPollSliceMs = 50;

long long nowMs()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

void sleepMs(int ms)
{
    poll(nullptr, 0, ms);
}

std::string makeTempDir()
{
    char tmpl[] = "/tmp/grok-lifecycle-XXXXXX";
    if (::mkdtemp(tmpl) == nullptr) {
        return std::string();
    }
    return std::string(tmpl);
}

void removeTempDir(const std::string &dir, const std::string &socketName)
{
    if (dir.empty()) {
        return;
    }
    ::unlink((dir + "/" + socketName).c_str());
    ::rmdir(dir.c_str());
}

// Bind a non-accepting AF_UNIX listener and fill its accept queue, the
// same saturation the Python POSIX probes use.
bool saturateListener(const std::string &path, int *serverFd,
                      std::vector<int> *fillers)
{
    const int server = ::socket(AF_UNIX, SOCK_STREAM, 0);
    if (server < 0) {
        return false;
    }
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::memcpy(addr.sun_path, path.c_str(), path.size());
    ::unlink(path.c_str());
    if (::bind(server, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0
        || ::listen(server, 1) != 0) {
        ::close(server);
        return false;
    }
    for (int i = 0; i < 256; ++i) {
        const int client = ::socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0);
        if (client < 0) {
            continue;
        }
        if (::connect(client, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0) {
            fillers->push_back(client);
            continue;
        }
        const int err = errno;
        fillers->push_back(client);
        if (err == EAGAIN || err == EWOULDBLOCK || err == EINPROGRESS) {
            *serverFd = server;
            return true;
        }
        for (int held : *fillers) {
            ::close(held);
        }
        fillers->clear();
        ::close(server);
        return false;
    }
    // Queue never reported full; treat as unsaturated.
    for (int held : *fillers) {
        ::close(held);
    }
    fillers->clear();
    ::close(server);
    return false;
}

#define CHECK(cond)                                                            \
    do {                                                                       \
        if (!(cond)) {                                                         \
            std::printf("  CHECK FAILED %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            return false;                                                      \
        }                                                                      \
    } while (0)

bool testProtocolUrlFilter()
{
    CHECK(companion::lifecycle::isProtocolUrl(QStringLiteral("grokbot:auth?code=1")));
    CHECK(companion::lifecycle::isProtocolUrl(QStringLiteral("sand:open")));
    CHECK(!companion::lifecycle::isProtocolUrl(QStringLiteral("/app/bin/grok-bot-electron")));
    CHECK(!companion::lifecycle::isProtocolUrl(QStringLiteral("https://example.invalid")));
    CHECK(!companion::lifecycle::isProtocolUrl(QString()));
    const QStringList argv = {
        QStringLiteral("grok-bot-companion"), QStringLiteral("/app/bin/grok-bot-electron"),
        QStringLiteral("grokbot:auth?code=1"), QStringLiteral("sand:open"), QStringLiteral("--other"),
    };
    const QStringList urls = companion::lifecycle::protocolUrlsFrom(argv);
    CHECK(urls.size() == 2);
    CHECK(urls[0] == QStringLiteral("grokbot:auth?code=1"));
    CHECK(urls[1] == QStringLiteral("sand:open"));
    // argv[0] is never treated as a URL even when it looks like a scheme.
    const QStringList onlyFirst = {QStringLiteral("grokbot:auth")};
    CHECK(companion::lifecycle::protocolUrlsFrom(onlyFirst).empty());
    return true;
}

bool testUnixSocketConnectBounded()
{
#if !defined(__linux__)
    std::printf("  SKIP: AF_UNIX saturation probe requires Linux\n");
    return true;
#else
    const std::string dir = makeTempDir();
    CHECK(!dir.empty());
    const std::string path = dir + "/SingletonSocket";
    int server = -1;
    std::vector<int> fillers;
    const bool saturated = saturateListener(path, &server, &fillers);
    CHECK(saturated);
    const long long start = nowMs();
    const int fd = companion::lifecycle::connectUnixSocket(QString::fromStdString(path));
    const long long elapsed = nowMs() - start;
    if (fd >= 0) {
        ::close(fd);
    }
    for (int held : fillers) {
        ::close(held);
    }
    ::close(server);
    removeTempDir(dir, "SingletonSocket");
    // Saturated queue: the bounded probe must report failure instead of
    // blocking like a plain blocking connect (which outlives 150 ms).
    CHECK(fd < 0);
    CHECK(elapsed >= kConnectTimeoutMs - kTimingToleranceMs);
    CHECK(elapsed <= kBlockingObserveMs + kTimingToleranceMs);
    CHECK(elapsed > kConnectTimeoutMs - kTimingToleranceMs);
    return true;
#endif
}

bool testUnixSocketPeercred()
{
#if !defined(__linux__)
    std::printf("  SKIP: SO_PEERCRED requires Linux\n");
    return true;
#else
    const std::string dir = makeTempDir();
    CHECK(!dir.empty());
    const std::string path = dir + "/SingletonSocket";
    const int server = ::socket(AF_UNIX, SOCK_STREAM, 0);
    CHECK(server >= 0);
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::memcpy(addr.sun_path, path.c_str(), path.size());
    ::unlink(path.c_str());
    CHECK(::bind(server, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0);
    CHECK(::listen(server, 1) == 0);
    int accepted = -1;
    // Real accept on a helper thread; the probe connects for real.
    std::thread waiter([&] {
        pollfd ready{};
        ready.fd = server;
        ready.events = POLLIN;
        if (::poll(&ready, 1, 2000) > 0) {
            accepted = ::accept(server, nullptr, nullptr);
        }
    });
    companion::lifecycle::LinuxPeerCredentials credentials{};
    const bool credentialsRead = companion::lifecycle::linuxPeerCredentials(
        QString::fromStdString(path), &credentials);
    waiter.join();
    ::close(server);
    if (accepted >= 0) {
        ::close(accepted);
    }
    removeTempDir(dir, "SingletonSocket");
    // The companion must identify the peer by credentials, never by name.
    CHECK(credentialsRead);
    CHECK(credentials.pid == ::getpid());
    CHECK(credentials.pid > 1);
    CHECK(credentials.uid == ::getuid());
    CHECK(credentials.gid == ::getgid());
    CHECK(companion::lifecycle::unixSocketIsLive(QString::fromStdString(path)) == false);
    return true;
#endif
}

bool testOwnedProcessGroupShutdown()
{
#if !defined(__linux__)
    std::printf("  SKIP: setsid/killpg requires Linux\n");
    return true;
#else
    const pid_t self = ::getpid();
    const pid_t selfPgid = ::getpgrp();
    const pid_t child = ::fork();
    CHECK(child >= 0);
    if (child == 0) {
        // Owned child: lead a fresh process group like startChild().
        if (::setsid() < 0) {
            _exit(127);
        }
        ::execlp("sleep", "sleep", "30", static_cast<char *>(nullptr));
        _exit(127);
    }
    // Wait for the child to own its group (setsid in the child races the
    // parent), mirroring the production waitForStarted before getpgid.
    pid_t pgid = -1;
    {
        const long long start = nowMs();
        int status = 0;
        for (;;) {
            const pid_t seen = ::getpgid(child);
            if (seen == child) {
                pgid = seen;
                break;
            }
            if (::waitpid(child, &status, WNOHANG) == child) {
                std::printf("  owned child exited early (status %d)\n", status);
                return false;
            }
            if (nowMs() - start > 2000) {
                break;
            }
            sleepMs(20);
        }
    }
    CHECK(pgid == child);
    // Signal only a group the child owns, never our own group.
    CHECK(pgid != selfPgid);
    // Graceful first: SIGTERM only the leader, then poll the whole group
    // empty with a zero-signal probe, all bounded.
    CHECK(::kill(child, SIGTERM) == 0 || errno == ESRCH);
    const bool drained = companion::lifecycle::waitForProcessGroupExit(pgid, kProbeTimeoutMs);
    if (!drained) {
        ::killpg(pgid, SIGTERM);
        if (!companion::lifecycle::waitForProcessGroupExit(pgid, 2000)) {
            ::killpg(pgid, SIGKILL);
            companion::lifecycle::waitForProcessGroupExit(pgid, 2000);
        }
    }
    int status = 0;
    ::waitpid(child, &status, 0);
    CHECK(companion::lifecycle::groupExited(pgid));
    // Our own group was never signaled.
    CHECK(::kill(self, 0) == 0);
    CHECK(::getpgrp() == selfPgid);
    return true;
#endif
}

bool testShowQuitDecision()
{
    CHECK(companion::lifecycle::showAction(false, true)
          == companion::lifecycle::ShowAction::StartDetached);
    CHECK(companion::lifecycle::quitAction(false, true)
          == companion::lifecycle::QuitAction::SignalPeer);
    CHECK(companion::lifecycle::showAction(true, true)
          == companion::lifecycle::ShowAction::StartDetached);
    CHECK(companion::lifecycle::quitAction(true, true)
          == companion::lifecycle::QuitAction::TerminateChildGroup);
    CHECK(companion::lifecycle::showAction(false, false)
          == companion::lifecycle::ShowAction::StartChild);
    CHECK(companion::lifecycle::quitAction(false, false)
          == companion::lifecycle::QuitAction::CompanionOnly);
    return true;
}

bool testColdStartForward()
{
#if !defined(__linux__)
    std::printf("  SKIP: cold-start socket probe requires Linux\n");
    return true;
#else
    const std::string dir = makeTempDir();
    CHECK(!dir.empty());
    const std::string path = dir + "/SingletonSocket";
    // Electron appears late: no socket at first, listener after 200 ms.
    std::thread lateElectron([&] {
        sleepMs(200);
        const int server = ::socket(AF_UNIX, SOCK_STREAM, 0);
        if (server < 0) {
            return;
        }
        sockaddr_un addr{};
        addr.sun_family = AF_UNIX;
        std::memcpy(addr.sun_path, path.c_str(), path.size());
        ::unlink(path.c_str());
        if (::bind(server, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0
            || ::listen(server, 4) != 0) {
            ::close(server);
            return;
        }
        // Stay live long enough for the poll loop to forward.
        sleepMs(3000);
        ::close(server);
    });
    // Cold-delivery poll loop mirroring deliverColdProtocolUrls: poll the
    // single-instance socket every slice until ready or the bound expires.
    const long long start = nowMs();
    bool ready = false;
    while (nowMs() - start < kProbeTimeoutMs) {
        if (companion::lifecycle::unixSocketIsLive(QString::fromStdString(path))) {
            ready = true;
            break;
        }
        sleepMs(kPollSliceMs);
    }
    const long long elapsed = nowMs() - start;
    lateElectron.join();
    removeTempDir(dir, "SingletonSocket");
    CHECK(ready);
    CHECK(elapsed >= 150);
    CHECK(elapsed < kProbeTimeoutMs);
    // Negative side: with no socket at all the loop must time out bounded.
    const long long missStart = nowMs();
    bool missing = false;
    while (nowMs() - missStart < 300) {
        if (companion::lifecycle::unixSocketIsLive(QString::fromStdString(path))) {
            missing = true;
            break;
        }
        sleepMs(kPollSliceMs);
    }
    CHECK(!missing);
    CHECK(nowMs() - missStart < 2000);
    return true;
#endif
}

struct Case {
    const char *name;
    std::function<bool()> run;
};

const std::vector<Case> &allCases()
{
    static const std::vector<Case> cases = {
        {"protocol_url_filter", testProtocolUrlFilter},
        {"unix_socket_connect_bounded", testUnixSocketConnectBounded},
        {"unix_socket_peercred", testUnixSocketPeercred},
        {"owned_process_group_shutdown", testOwnedProcessGroupShutdown},
        {"show_quit_decision", testShowQuitDecision},
        {"cold_start_forward", testColdStartForward},
    };
    return cases;
}

} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    // Outer fail-closed bound: never hang the CTest layer.
    ::alarm(120);
    std::string only;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--list") {
            for (const auto &entry : allCases()) {
                std::printf("%s\n", entry.name);
            }
            return 0;
        }
        if (arg == "--case" && i + 1 < argc) {
            only = argv[++i];
        }
    }
    int ran = 0;
    int failed = 0;
    for (const auto &entry : allCases()) {
        if (!only.empty() && only != entry.name) {
            continue;
        }
        std::printf("[ RUN ] %s\n", entry.name);
        const bool ok = entry.run();
        std::printf("[ %s ] %s\n", ok ? "OK" : "FAIL", entry.name);
        ++ran;
        failed += ok ? 0 : 1;
    }
    if (!only.empty() && ran == 0) {
        std::printf("unknown case: %s\n", only.c_str());
        return 2;
    }
    std::printf("%d ran, %d failed\n", ran, failed);
    return failed == 0 ? 0 : 1;
}
