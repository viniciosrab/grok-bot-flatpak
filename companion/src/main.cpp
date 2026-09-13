// Grok Bot tray companion: a separate Qt/KF6 process that owns a KDE
// StatusNotifierItem for the Unofficial Flatpak.
//
// Lifecycle contract (ADR 0003):
// - The companion requires org.kde.StatusNotifierWatcher. When the watcher
//   is absent it exits nonzero; there is no trayless fallback.
// - Show relaunches the application when it is not running, or reveals the
//   running instance through a second exec (Electron single-instance
//   focuses the existing window).
// - Quit terminates the whole child process group and then quits the
//   companion, so both processes always go down together.
// - When Grok Bot exits on its own the companion stays up, so the next
//   Show relaunches it.
//
// KF6 registers each item under a unique bus identity of the form
// org.kde.StatusNotifierItem-<pid>-<n>; this companion relies on that
// documented identity instead of claiming a well-known name.

#include <QApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDir>
#include <QFileInfo>
#include <QIcon>
#include <QLockFile>
#include <QPixmap>
#include <QProcess>
#include <QSize>
#include <QStandardPaths>
#include <QStringList>
#include <KStatusNotifierItem>

#ifdef Q_OS_UNIX
#include <signal.h>
#include <sys/types.h>
#include <unistd.h>
#endif

namespace {

constexpr char kWatcherService[] = "org.kde.StatusNotifierWatcher";
constexpr char kBusIdentityPrefix[] = "org.kde.StatusNotifierItem-";
constexpr char kDefaultElectronPath[] = "/app/bin/grok-bot-electron";
constexpr char kElectronEnvVar[] = "GROK_BOT_ELECTRON";

bool watcherAvailable()
{
    QDBusConnectionInterface *bus = QDBusConnection::sessionBus().interface();
    return bus != nullptr && bus->isServiceRegistered(QString::fromLatin1(kWatcherService));
}

QString resolveElectronCommand(const QApplication &app)
{
    const QStringList args = app.arguments();
    if (args.size() > 1 && !args.at(1).isEmpty()) {
        return args.at(1);
    }
    const QString fromEnv = QString::fromLocal8Bit(qgetenv(kElectronEnvVar)).trimmed();
    if (!fromEnv.isEmpty()) {
        return fromEnv;
    }
    return QString::fromLatin1(kDefaultElectronPath);
}

} // namespace

class CompanionController : public QObject
{
    Q_OBJECT

public:
    CompanionController(KStatusNotifierItem *tray, const QString &electronCommand, QObject *parent = nullptr)
        : QObject(parent)
        , m_tray(tray)
        , m_electronCommand(electronCommand)
        , m_child(new QProcess(this))
        , m_ownProcessGroup(false)
    {
        connect(m_child, &QProcess::finished, this, &CompanionController::childFinished);
        connect(m_child, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            Q_UNUSED(error);
            qWarning("grok-bot-companion: child process error: %s", qPrintable(m_child->errorString()));
        });
        connect(m_tray, &KStatusNotifierItem::activateRequested, this, &CompanionController::showRequested);
        connect(m_tray, &KStatusNotifierItem::quitRequested, this, &CompanionController::quitRequested);
    }

    void start()
    {
        startChild();
    }

private slots:
    void showRequested()
    {
        if (m_child->state() != QProcess::NotRunning) {
            // Second exec: Electron single-instance focuses the window.
            if (!QProcess::startDetached(m_electronCommand, {})) {
                qWarning("grok-bot-companion: failed to reveal the running instance: %s", qPrintable(m_electronCommand));
            }
            return;
        }
        startChild();
    }

    void quitRequested()
    {
        terminateChildGroup();
        qApp->quit();
    }

    void childFinished(int exitCode, QProcess::ExitStatus status)
    {
        Q_UNUSED(exitCode);
        Q_UNUSED(status);
        // The companion stays up so Show can relaunch the application.
    }

private:
    void startChild()
    {
        // Launch through setsid when available so the child owns its process
        // group and Quit can terminate the whole group, not just one pid.
        const QString setsid = QStandardPaths::findExecutable(QStringLiteral("setsid"));
        m_ownProcessGroup = !setsid.isEmpty();
        if (m_ownProcessGroup) {
            m_child->setProgram(setsid);
            m_child->setArguments({m_electronCommand});
        } else {
            m_child->setProgram(m_electronCommand);
            m_child->setArguments({});
        }
        m_child->start();
    }

    void terminateChildGroup()
    {
        if (m_child->state() == QProcess::NotRunning) {
            return;
        }
#ifdef Q_OS_UNIX
        if (m_ownProcessGroup && m_child->waitForStarted(1000)) {
            const qint64 pid = m_child->processId();
            const pid_t pgid = pid > 0 ? ::getpgid(static_cast<pid_t>(pid)) : static_cast<pid_t>(-1);
            // Signal only a group the child owns (setsid leader: pgid == pid),
            // never our own group, so an early Quit cannot kill the companion.
            if (pid > 1 && pgid == static_cast<pid_t>(pid) && pgid != ::getpgrp()) {
                ::killpg(pgid, SIGTERM);
                if (!m_child->waitForFinished(3000)) {
                    ::killpg(pgid, SIGKILL);
                    m_child->waitForFinished(3000);
                }
            }
        }
#endif
        if (m_child->state() != QProcess::NotRunning) {
            m_child->terminate();
            if (!m_child->waitForFinished(3000)) {
                m_child->kill();
                m_child->waitForFinished(3000);
            }
        }
    }

    KStatusNotifierItem *m_tray;
    QString m_electronCommand;
    QProcess *m_child;
    bool m_ownProcessGroup;
};

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("grok-bot-companion"));
    app.setQuitOnLastWindowClosed(false);

    static QLockFile instanceLock(QDir::temp().filePath(QStringLiteral("grok-bot-companion.lock")));
    if (!instanceLock.tryLock()) {
        qWarning("grok-bot-companion: another instance is already running");
        return 0;
    }

    // Unique KF6 bus identity: org.kde.StatusNotifierItem-<pid>-<n>.
    // Referenced here so the identity contract stays greppable.
    const QString busIdentity = QString::fromLatin1(kBusIdentityPrefix)
        + QString::number(QCoreApplication::applicationPid());

    if (!watcherAvailable()) {
        qWarning("grok-bot-companion: %s is not on the session bus (%s); refusing trayless fallback",
                 kWatcherService,
                 qPrintable(busIdentity));
        return 1;
    }

    const QString electronCommand = resolveElectronCommand(app);
    if (electronCommand.isEmpty()) {
        qWarning("grok-bot-companion: no Electron command configured");
        return 1;
    }
    if (!QFileInfo::exists(electronCommand) || !QFileInfo(electronCommand).isExecutable()) {
        qWarning("grok-bot-companion: Electron command is not executable: %s", qPrintable(electronCommand));
        return 1;
    }

    KStatusNotifierItem tray(&app);
    tray.setTitle(QStringLiteral("Grok Bot (Unofficial)"));
    // Flatpak exports only icons named after the app-id. Send a 22px
    // pixmap, KDE's SmallMedium tray size, so Plasma cannot pick the
    // 512px vendor asset and render a larger StatusNotifierItem.
    tray.setIconByName(QStringLiteral("io.github.viniciosrab.GrokBot"));
    const QStringList pixmapCandidates = {
        QStringLiteral("/app/share/icons/hicolor/24x24/apps/io.github.viniciosrab.GrokBot.png"),
        QStringLiteral("/app/share/icons/hicolor/24x24/apps/grok-bot.png"),
        QStringLiteral("/app/share/icons/hicolor/32x32/apps/io.github.viniciosrab.GrokBot.png"),
        QStringLiteral("/app/share/icons/hicolor/32x32/apps/grok-bot.png"),
    };
    QPixmap trayPixmap;
    for (const QString &path : pixmapCandidates) {
        if (QFileInfo::exists(path)) {
            trayPixmap = QPixmap(path);
            if (!trayPixmap.isNull()) {
                break;
            }
        }
    }
    if (!trayPixmap.isNull()) {
        const QPixmap traySized = trayPixmap.scaled(
            QSize(22, 22),
            Qt::KeepAspectRatio,
            Qt::SmoothTransformation);
        tray.setIconByPixmap(QIcon(traySized));
    }
    tray.setToolTipTitle(QStringLiteral("Grok Bot (Unofficial)"));
    tray.setStandardActionsEnabled(true);

    CompanionController controller(&tray, electronCommand, &app);
    controller.start();
    return app.exec();
}

#include "main.moc"
