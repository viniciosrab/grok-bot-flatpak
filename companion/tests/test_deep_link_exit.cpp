// Behavioral regression for the companion's lost-lock protocol handoff.
//
// The test holds the same QLockFile used by the production executable, then
// starts that executable with a deliberately invalid Electron command. A URL
// forwarding failure must be observable as exit 1; an invocation without a
// URL remains a successful no-op with exit 0.

#include <QCoreApplication>
#include <QLockFile>
#include <QProcess>
#include <QProcessEnvironment>
#include <QTemporaryDir>

#include <cstdio>

namespace {

bool runCompanion(const QString &program, const QStringList &arguments,
                  const QString &runtimeDir, int expectedExitCode)
{
    QProcess process;
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert(QStringLiteral("XDG_RUNTIME_DIR"), runtimeDir);
    environment.insert(QStringLiteral("GROK_BOT_ELECTRON"),
                       QStringLiteral("/definitely/missing/grok-bot-electron"));
    environment.insert(QStringLiteral("QT_QPA_PLATFORM"), QStringLiteral("offscreen"));
    process.setProcessEnvironment(environment);
    process.start(program, arguments);
    if (!process.waitForFinished(10000)) {
        process.kill();
        process.waitForFinished(2000);
        std::printf("companion did not finish: %s\n",
                    process.errorString().toLocal8Bit().constData());
        return false;
    }
    if (process.exitStatus() != QProcess::NormalExit
        || process.exitCode() != expectedExitCode) {
        std::printf("expected exit %d, observed status=%d code=%d\n",
                    expectedExitCode,
                    static_cast<int>(process.exitStatus()),
                    process.exitCode());
        std::printf("companion output:\n%s\n",
                    process.readAllStandardError().constData());
        return false;
    }
    return true;
}

} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (argc != 2 || !argv[1] || !argv[1][0]) {
        std::fprintf(stderr, "usage: test_deep_link_exit /path/to/grok-bot-companion\n");
        return 2;
    }

    QTemporaryDir runtime;
    if (!runtime.isValid()) {
        std::fprintf(stderr, "failed to create a temporary runtime directory\n");
        return 1;
    }
    const QString lockPath = runtime.filePath(QStringLiteral("grok-bot-companion.lock"));
    QLockFile lock(lockPath);
    if (!lock.tryLock(1000)) {
        std::fprintf(stderr, "failed to hold the companion lock\n");
        return 1;
    }

    const QString program = QString::fromLocal8Bit(argv[1]);
    if (!runCompanion(program,
                     {QStringLiteral("grokbot:test")},
                     runtime.path(),
                     1)) {
        return 1;
    }
    if (!runCompanion(program, {}, runtime.path(), 0)) {
        return 1;
    }
    return 0;
}
