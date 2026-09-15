#pragma once

#include <QString>
#include <QStringList>

#include <sys/types.h>

namespace companion::lifecycle {

constexpr int kUnixSocketConnectTimeoutMs = 50;
constexpr int kGroupPollSliceMs = 100;

enum class ShowAction {
    StartDetached,
    StartChild,
};

enum class QuitAction {
    TerminateChildGroup,
    SignalPeer,
    CompanionOnly,
};

bool isProtocolUrl(const QString &arg);
QStringList protocolUrlsFrom(const QStringList &args);

ShowAction showAction(bool childRunning, bool socketLive);
QuitAction quitAction(bool childRunning, bool socketLive);

int connectUnixSocket(const QString &socketPath);
bool unixSocketIsLive(const QString &socketPath);
struct LinuxPeerCredentials {
    pid_t pid;
    uid_t uid;
    gid_t gid;
};

bool linuxPeerCredentials(const QString &socketPath, LinuxPeerCredentials *credentials);
pid_t linuxPeerPid(const QString &socketPath);

bool groupExited(pid_t pgid);
bool waitForProcessGroupExit(pid_t pgid, int timeoutMs);

} // namespace companion::lifecycle
