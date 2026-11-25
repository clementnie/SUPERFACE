#define _GNU_SOURCE
#include "session.h"
#include "superface.h"

#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <pwd.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static void run_child(int master, int fd, char *const *argv, bool login)
{
    close(master);
    if (setsid() < 0)
        _exit(126);
    struct winsize size = {.ws_row = ROWS, .ws_col = COLS};
    if (fd < 0 || ioctl(fd, TIOCSCTTY, 0) || ioctl(fd, TIOCSWINSZ, &size) ||
        tcsetpgrp(fd, getpgrp()) < 0)
        _exit(126);
    int flags = fcntl(fd, F_GETFD);
    if (flags == -1 || fcntl(fd, F_SETFD, flags & ~FD_CLOEXEC) == -1)
        _exit(126);
    for (int i = 0; i < 3; ++i)
        if (dup2(fd, i) < 0)
            _exit(126);
    if (fd > 2)
        close(fd);
    const char *term = access("/usr/share/terminfo/s/superface", R_OK) == 0
                     ? "superface" : "xterm";
    if (login) {
        char *const login_args[] = {"login", NULL};
        char *const login_env[] = {"PATH=/usr/bin:/bin", !strcmp(term, "superface") ? "TERM=superface" : "TERM=xterm",
                                  "LANG=C.UTF-8", NULL};
        if (chdir("/") < 0)
            _exit(126);
        execve("/usr/bin/login", login_args, login_env);
    } else {
        if (unsetenv("COLORTERM") < 0 || setenv("TERM", term, 1) < 0 || setenv("LC_ALL", "C.UTF-8", 1) < 0)
            _exit(126);
        execvp(argv[0], argv);
    }
    _exit(127);
}

bool session_start(Session *session, char *const *argv, bool login)
{
    uid_t uid = 0;
    gid_t gid = 0;
    if (login) {
        struct passwd *account = getpwnam("superface");
        if (!account || !account->pw_uid || !account->pw_gid) {
            errno = EINVAL;
            return false;
        }
        uid = account->pw_uid;
        gid = account->pw_gid;
    }

    char slave[128];
    int master = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (master < 0)
        return false;
    int name_error;
    if (grantpt(master) < 0 || unlockpt(master) < 0)
        goto failed;
    name_error = ptsname_r(master, slave, sizeof(slave));
    if (name_error) {
        errno = name_error;
        goto failed;
    }

    // Keep the slave open across fork until the child can take it over.
    int keeper = open(slave, O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (keeper < 0)
        goto failed;
    pid_t pid = fork();
    if (pid == 0)
        run_child(master, keeper, argv, login);
    close(keeper);
    if (pid < 0)
        goto failed;
    *session = (Session){.master = master, .child = pid};

    if (login && (setgroups(0, NULL) < 0 || setresgid(gid, gid, gid) < 0 ||
                  setresuid(uid, uid, uid) < 0 || prctl(PR_SET_DUMPABLE, 0) < 0)) {
        int saved = errno;
        session_stop(session);
        errno = saved;
        return false;
    }
    return true;

failed: {
        int saved = errno;
        close(master);
        errno = saved;
        return false;
    }
}

bool session_reap(Session *session)
{
    if (!session->reaped) {
        pid_t result = waitpid(session->child, &session->status, WNOHANG);
        if (result < 0 && errno != EINTR)
            return false;
        session->reaped = result == session->child;
    }
    return true;
}

void session_stop(Session *session)
{
    if (session->master >= 0) {
        close(session->master);
        session->master = -1;
    }
    if (session->reaped)
        return;

    kill(-session->child, SIGHUP);
    kill(session->child, SIGHUP);
    const struct timespec pause = {.tv_nsec = 20000000};
    for (int i = 0; i < 25; ++i) {
        if (!session_reap(session) || session->reaped)
            return;
        nanosleep(&pause, NULL);
    }
    kill(-session->child, SIGKILL);
    if (kill(session->child, SIGKILL) < 0 && errno != ESRCH)
        return; // After privilege drop, systemd owns final cgroup cleanup.
    while (waitpid(session->child, &session->status, 0) < 0 && errno == EINTR)
        ;
    session->reaped = true;
}
