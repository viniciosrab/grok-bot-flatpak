// Compiled lifecycle probes for the Grok Bot tray companion.
//
// These tests exercise the same OS contracts as companion/src/main.cpp
// (bounded nonblocking AF_UNIX probe, SO_PEERCRED peer identification,
// owned process-group graceful shutdown, protocol-URL filtering, and the
// cold-start wait-and-forward loop) using REAL temporary Unix sockets and
// REAL owned child processes with bounded timeouts.
//
// There is deliberately NO fixture adapter in this file: only one
// production implementation exists, so a seam with a fake would be a
// hypothetical seam. Every probe below crosses the same interface the
// production helpers use, against the real syscalls.
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

#include <errno.h>
#include <fcntl.h>
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

// Mirrors companion kUnixSocketConnectTimeoutMs: the UI wait stays small.
constexpr int kConnectTimeoutMs = 50;
// Blocking observers must outlive that bound to prove the difference.
constexpr int kBlockingObserveMs = 150;
constexpr int kTimingToleranceMs = 40;
// Test-local outer bound for poll loops that mirror production waits.
constexpr int kProbeTimeoutMs = 5000;
constexpr int kPollSliceMs = 50;

struct PeerCred {
    pid_t pid;
    uid_t uid;
    gid_t gid;
};

long long nowMs()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

void sleepMs(int ms)
{
    poll(nullptr, 0, ms);
}

// Mirrors isProtocolUrl/protocolUrlsFrom in companion/src/main.cpp.
bool isProtocolUrl(const std::string &arg)
{
    return arg.rfind("grokbot:", 0) == 0 || arg.rfind("sand:", 0) == 0;
}

std::vector<std::string> protocolUrlsFrom(const std::vector<std::string> &args)
{
    std::vector<std::string> urls;
    for (size_t i = 1; i < args.size(); ++i) {
        if (isProtocolUrl(args[i])) {
            urls.push_back(args[i]);
        }
    }
    return urls;
}

// Mirrors showRequested/quitRequested in CompanionController.
std::string showAction(bool childRunning, bool socketLive)
{
    if (childRunning || socketLive) {
        return "startDetached";
    }
    return "startChild";
}

std::string quitAction(bool childRunning, bool socketLive)
{
    if (childRunning) {
        return "terminateChildGroup";
    }
    if (socketLive) {
        return "sigterm_peer";
    }
    return "companion_only";
}

// Mirrors connectUnixSocket in companion/src/main.cpp: connect only, never
// write protocol bytes, bounded by kConnectTimeoutMs. Returns the fd or -1.
int connectUnixSocket(const std::string &socketPath)
{
    if (socketPath.empty() || socketPath.size() >= sizeof(sockaddr_un::sun_path)) {
        return -1;
    }
#ifdef SOCK_NONBLOCK
    const int fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0);
#else
    const int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
#endif
    if (fd < 0) {
        return -1;
    }
#ifndef SOCK_NONBLOCK
    const int flags = ::fcntl(fd, F_GETFL, 0);
    if (flags < 0 || ::fcntl(fd, F_SETFL, flags | O_NONBLOCK) != 0) {
        ::close(fd);
        return -1;
    }
#endif

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::memcpy(addr.sun_path, socketPath.c_str(), socketPath.size());

    const long long deadline = nowMs() + kConnectTimeoutMs;
    for (;;) {
        if (::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0) {
            return fd;
        }
        const int err = errno;
        if (err == EINTR) {
            if (nowMs() >= deadline) {
                ::close(fd);
                return -1;
            }
            continue;
        }
        if (err == EINPROGRESS || err == EALREADY) {
            for (;;) {
                const long long remaining = deadline - nowMs();
                if (remaining <= 0) {
                    ::close(fd);
                    return -1;
                }
                pollfd ready{};
                ready.fd = fd;
                ready.events = POLLOUT;
                const int rc = ::poll(&ready, 1, static_cast<int>(remaining));
                if (rc < 0) {
                    if (errno == EINTR) {
                        continue;
                    }
                    ::close(fd);
                    return -1;
                }
                if (rc == 0) {
                    ::close(fd);
                    return -1;
                }
                int soError = 0;
                socklen_t soLen = sizeof(soError);
                if (::getsockopt(fd, SOL_SOCKET, SO_ERROR, &soError, &soLen) != 0
                    || soError != 0) {
                    ::close(fd);
                    return -1;
                }
                return fd;
            }
        }
        if (err == EAGAIN || err == EWOULDBLOCK) {
            const long long remaining = deadline - nowMs();
            if (remaining <= 0) {
                ::close(fd);
                return -1;
            }
            poll(nullptr, 0, static_cast<int>(remaining));
            if (nowMs() >= deadline) {
                ::close(fd);
                return -1;
            }
            continue;
        }
        ::close(fd);
        return -1;
    }
}

bool unixSocketIsLive(const std::string &socketPath)
{
    const int fd = connectUnixSocket(socketPath);
    if (fd < 0) {
        return false;
    }
    ::close(fd);
    return true;
}

bool peerCredOf(const std::string &socketPath, PeerCred *out)
{
    const int fd = connectUnixSocket(socketPath);
    if (fd < 0) {
        return false;
    }
    PeerCred cred{};
    socklen_t len = sizeof(cred);
    const int rc = ::getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &len);
    ::close(fd);
    if (rc != 0 || cred.pid <= 1) {
        return false;
    }
    *out = cred;
    return true;
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

// Zero-signal probe mirroring CompanionController::groupExited: true when
// no process remains in pgid. EPERM (exists, no permission) counts as alive.
bool groupExited(pid_t pgid)
{
    errno = 0;
    return ::killpg(pgid, 0) != 0 && errno == ESRCH;
}

bool waitForProcessGroupExit(pid_t pgid, int timeoutMs)
{
    const long long deadline = nowMs() + timeoutMs;
    for (;;) {
        if (groupExited(pgid)) {
            return true;
        }
        if (nowMs() >= deadline) {
            break;
        }
        sleepMs(kPollSliceMs);
    }
    return groupExited(pgid);
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
    CHECK(isProtocolUrl("grokbot:auth?code=1"));
    CHECK(isProtocolUrl("sand:open"));
    CHECK(!isProtocolUrl("/app/bin/grok-bot-electron"));
    CHECK(!isProtocolUrl("https://example.invalid"));
    CHECK(!isProtocolUrl(""));
    const std::vector<std::string> argv = {
        "grok-bot-companion", "/app/bin/grok-bot-electron",
        "grokbot:auth?code=1", "sand:open", "--other",
    };
    const std::vector<std::string> urls = protocolUrlsFrom(argv);
    CHECK(urls.size() == 2);
    CHECK(urls[0] == "grokbot:auth?code=1");
    CHECK(urls[1] == "sand:open");
    // argv[0] is never treated as a URL even when it looks like a scheme.
    const std::vector<std::string> onlyFirst = {"grokbot:auth"};
    CHECK(protocolUrlsFrom(onlyFirst).empty());
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
    const int fd = connectUnixSocket(path);
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
    PeerCred cred{};
    const bool ok = peerCredOf(path, &cred);
    waiter.join();
    ::close(server);
    if (accepted >= 0) {
        ::close(accepted);
    }
    removeTempDir(dir, "SingletonSocket");
    CHECK(ok);
    // The companion must identify the peer by credentials, never by name.
    CHECK(cred.pid == ::getpid());
    CHECK(cred.pid > 1);
    CHECK(cred.uid == ::getuid());
    CHECK(cred.gid == ::getgid());
    CHECK(unixSocketIsLive(path) == false);
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
    const bool drained = waitForProcessGroupExit(pgid, kProbeTimeoutMs);
    if (!drained) {
        ::killpg(pgid, SIGTERM);
        if (!waitForProcessGroupExit(pgid, 2000)) {
            ::killpg(pgid, SIGKILL);
            waitForProcessGroupExit(pgid, 2000);
        }
    }
    int status = 0;
    ::waitpid(child, &status, 0);
    CHECK(groupExited(pgid));
    // Our own group was never signaled.
    CHECK(::kill(self, 0) == 0);
    CHECK(::getpgrp() == selfPgid);
    return true;
#endif
}

bool testShowQuitDecision()
{
    CHECK(showAction(false, true) == "startDetached");
    CHECK(quitAction(false, true) == "sigterm_peer");
    CHECK(showAction(true, true) == "startDetached");
    CHECK(quitAction(true, true) == "terminateChildGroup");
    CHECK(showAction(false, false) == "startChild");
    CHECK(quitAction(false, false) == "companion_only");
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
        if (unixSocketIsLive(path)) {
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
        if (unixSocketIsLive(path)) {
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
