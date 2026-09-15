#include "lifecycle_helpers.h"

#include <QElapsedTimer>
#include <QFile>

#include <cstring>

#ifdef Q_OS_UNIX
#include <cerrno>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#endif

namespace companion::lifecycle {

bool isProtocolUrl(const QString &arg)
{
    return arg.startsWith(QLatin1String("grokbot:"))
        || arg.startsWith(QLatin1String("sand:"));
}

QStringList protocolUrlsFrom(const QStringList &args)
{
    QStringList urls;
    for (int i = 1; i < args.size(); ++i) {
        if (isProtocolUrl(args.at(i))) {
            urls.append(args.at(i));
        }
    }
    return urls;
}

ShowAction showAction(bool childRunning, bool socketLive)
{
    if (childRunning || socketLive) {
        return ShowAction::StartDetached;
    }
    return ShowAction::StartChild;
}

QuitAction quitAction(bool childRunning, bool socketLive)
{
    if (childRunning) {
        return QuitAction::TerminateChildGroup;
    }
    if (socketLive) {
        return QuitAction::SignalPeer;
    }
    return QuitAction::CompanionOnly;
}

int connectUnixSocket(const QString &socketPath)
{
#ifdef Q_OS_UNIX
    // Connect only: callers must close the fd. Do not write protocol bytes.
    const QByteArray encoded = QFile::encodeName(socketPath);
    sockaddr_un addr{};
    if (encoded.isEmpty() || static_cast<size_t>(encoded.size()) >= sizeof(addr.sun_path)) {
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

    addr.sun_family = AF_UNIX;
    ::memcpy(addr.sun_path, encoded.constData(), static_cast<size_t>(encoded.size()));

    QElapsedTimer clock;
    clock.start();
    for (;;) {
        if (::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0) {
            return fd;
        }
        const int connectErr = errno;
        if (connectErr == EINTR) {
            if (clock.hasExpired(kUnixSocketConnectTimeoutMs)) {
                ::close(fd);
                return -1;
            }
            continue;
        }
        if (connectErr == EINPROGRESS || connectErr == EALREADY) {
            for (;;) {
                const qint64 remaining = kUnixSocketConnectTimeoutMs - clock.elapsed();
                if (remaining <= 0) {
                    ::close(fd);
                    return -1;
                }
                pollfd ready{};
                ready.fd = fd;
                ready.events = POLLOUT;
                const int pollRc = ::poll(&ready, 1, static_cast<int>(remaining));
                if (pollRc < 0) {
                    if (errno == EINTR) {
                        continue;
                    }
                    ::close(fd);
                    return -1;
                }
                if (pollRc == 0) {
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
        if (connectErr == EAGAIN || connectErr == EWOULDBLOCK) {
            const qint64 remaining = kUnixSocketConnectTimeoutMs - clock.elapsed();
            if (remaining <= 0) {
                ::close(fd);
                return -1;
            }
            pollfd waiter{};
            waiter.fd = -1;
            const int waitRc = ::poll(&waiter, 1, static_cast<int>(remaining));
            if (waitRc < 0 && errno != EINTR) {
                ::close(fd);
                return -1;
            }
            if (clock.hasExpired(kUnixSocketConnectTimeoutMs)) {
                ::close(fd);
                return -1;
            }
            continue;
        }
        ::close(fd);
        return -1;
    }
#else
    Q_UNUSED(socketPath);
    return -1;
#endif
}

bool unixSocketIsLive(const QString &socketPath)
{
    const int fd = connectUnixSocket(socketPath);
    if (fd < 0) {
        return false;
    }
#ifdef Q_OS_UNIX
    ::close(fd);
#endif
    return true;
}

bool linuxPeerCredentials(const QString &socketPath, LinuxPeerCredentials *credentials)
{
#if defined(Q_OS_UNIX) && defined(__linux__)
#ifndef SO_PEERCRED
#define SO_PEERCRED 17
#endif
    const int fd = connectUnixSocket(socketPath);
    if (fd < 0) {
        return false;
    }
    LinuxPeerCredentials cred{};
    socklen_t len = sizeof(cred);
    const int rc = ::getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &len);
    ::close(fd);
    if (rc != 0 || cred.pid <= 1) {
        return false;
    }
    if (credentials != nullptr) {
        *credentials = cred;
    }
    return true;
#else
    Q_UNUSED(socketPath);
    Q_UNUSED(credentials);
    return false;
#endif
}

pid_t linuxPeerPid(const QString &socketPath)
{
    LinuxPeerCredentials credentials{};
    return linuxPeerCredentials(socketPath, &credentials) ? credentials.pid : 0;
}

bool groupExited(pid_t pgid)
{
#ifdef Q_OS_UNIX
    errno = 0;
    return ::killpg(pgid, 0) != 0 && errno == ESRCH;
#else
    Q_UNUSED(pgid);
    return true;
#endif
}

bool waitForProcessGroupExit(pid_t pgid, int timeoutMs)
{
    QElapsedTimer clock;
    clock.start();
    for (;;) {
        if (groupExited(pgid)) {
            return true;
        }
        if (clock.hasExpired(timeoutMs)) {
            break;
        }
#ifdef Q_OS_UNIX
        ::usleep(static_cast<useconds_t>(kGroupPollSliceMs) * 1000U);
#endif
    }
    return groupExited(pgid);
}

} // namespace companion::lifecycle
