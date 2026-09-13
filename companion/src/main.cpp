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
#include <QPainter>
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

QString resolveElectronCommand(const QApplication &app)
{
    const QStringList args = app.arguments();
    if (args.size() > 1 && !args.at(1).isEmpty() && !isProtocolUrl(args.at(1))) {
        const QFileInfo info(args.at(1));
        if (info.exists() && info.isExecutable()) {
            return args.at(1);
        }
    }
    const QString fromEnv = QString::fromLocal8Bit(qgetenv(kElectronEnvVar)).trimmed();
    if (!fromEnv.isEmpty()) {
        return fromEnv;
    }
    return QString::fromLatin1(kDefaultElectronPath);
}

void forwardProtocolUrls(const QString &electronCommand, const QStringList &urls)
{
    if (urls.isEmpty()) {
        return;
    }
    if (!QProcess::startDetached(electronCommand, urls)) {
        qWarning("grok-bot-companion: failed to forward protocol URL to %s", qPrintable(electronCommand));
    }
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

    void start(const QStringList &protocolUrls = {})
    {
        startChild(protocolUrls);
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
    void startChild(const QStringList &protocolUrls = {})
    {
        // Launch through setsid when available so the child owns its process
        // group and Quit can terminate the whole group, not just one pid.
        const QString setsid = QStandardPaths::findExecutable(QStringLiteral("setsid"));
        m_ownProcessGroup = !setsid.isEmpty();
        if (m_ownProcessGroup) {
            m_child->setProgram(setsid);
            m_child->setArguments(QStringList{m_electronCommand} << protocolUrls);
        } else {
            m_child->setProgram(m_electronCommand);
            m_child->setArguments(protocolUrls);
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
    const QStringList protocolUrls = protocolUrlsFrom(app.arguments());
    if (!instanceLock.tryLock()) {
        // Browser protocol handoff: forward grokbot:// or sand:// to the
        // already-running Electron instead of dropping the URL.
        forwardProtocolUrls(resolveElectronCommand(app), protocolUrls);
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
    // Flatpak exports only icons named after the app-id. Center unpadded
    // upstream artwork on a transparent 22px canvas (KDE SmallMedium tray
    // size) so the visible artwork keeps KDE-style padding instead of
    // filling the whole square. Prefer the preserved unpadded source: the
    // generated app-id icons are already padded, so scaling them again
    // would apply the padding twice.
    tray.setIconByName(QStringLiteral("io.github.viniciosrab.GrokBot"));
    const QStringList pixmapCandidates = {
        QStringLiteral("/app/grok-bot/resources/icon.upstream.png"),
        QStringLiteral("/app/share/icons/hicolor/24x24/apps/io.github.viniciosrab.GrokBot.png"),
        QStringLiteral("/app/share/icons/hicolor/32x32/apps/io.github.viniciosrab.GrokBot.png"),
        QStringLiteral("/app/grok-bot/resources/icon.png"),
    };
    QPixmap traySource;
    for (const QString &path : pixmapCandidates) {
        if (QFileInfo::exists(path)) {
            traySource = QPixmap(path);
            if (!traySource.isNull()) {
                break;
            }
        }
    }
    if (!traySource.isNull()) {
        const QPixmap trayArtwork = traySource.scaled(
            QSize(16, 16),
            Qt::KeepAspectRatio,
            Qt::SmoothTransformation);
        QPixmap trayCanvas(QSize(22, 22));
        trayCanvas.fill(Qt::transparent);
        QPainter trayPainter(&trayCanvas);
        trayPainter.setRenderHint(QPainter::SmoothPixmapTransform);
        const int trayX = (trayCanvas.width() - trayArtwork.width()) / 2;
        const int trayY = (trayCanvas.height() - trayArtwork.height()) / 2;
        trayPainter.drawPixmap(trayX, trayY, trayArtwork);
        trayPainter.end();
        tray.setIconByPixmap(QIcon(trayCanvas));
    }
    tray.setToolTipTitle(QStringLiteral("Grok Bot (Unofficial)"));
    tray.setStandardActionsEnabled(true);

    CompanionController controller(&tray, electronCommand, &app);
    controller.start(protocolUrls);
    return app.exec();
}

#include "main.moc"
