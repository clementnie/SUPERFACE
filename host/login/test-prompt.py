"""Check the installed SUPERFACE login prompt without entering credentials."""

import errno
import os
from pathlib import Path
import pty
import pwd
import select
import subprocess
import termios
import time

UNIT = "superface-private-login.service"
LAUNCHER = "/opt/superface/bin/run-private"


def main_pid():
    result = subprocess.check_output(
        ["systemctl", "show", "--property=MainPID", "--value", UNIT], text=True
    )
    return int(result.strip())


def receive(fd, deadline):
    if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
        raise TimeoutError("timed out waiting for launcher")
    try:
        return os.read(fd, 32768)
    except OSError as error:
        if error.errno != errno.EIO:
            raise
        return b""


def identity(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("Uid:"):
            return tuple(int(value) for value in line.split()[1:])
    raise RuntimeError("missing process UID")


def expect_screen(fd, marker, description):
    deadline = time.monotonic() + 10
    screen = bytearray()
    while marker not in screen:
        data = receive(fd, deadline)
        if not data:
            raise RuntimeError(f"launcher ended before {description}")
        screen.extend(data)
        if len(screen) > 65536:
            del screen[:-32768]


def verify_prompt(fd):
    expect_screen(fd, b"login:", "the login prompt")
    renderer = main_pid()
    renderer_uid = pwd.getpwnam("superface").pw_uid
    if not renderer or identity(renderer) != (renderer_uid,) * 4:
        raise RuntimeError("renderer did not drop its UID")
    children = Path(f"/proc/{renderer}/task/{renderer}/children").read_text().split()
    if len(children) != 1:
        raise RuntimeError("expected one login child before authentication")
    login = int(children[0])
    if Path(f"/proc/{login}/comm").read_text().strip() != "login" or identity(login) != (0,) * 4:
        raise RuntimeError("the child is not the privileged system login")

    inner = os.readlink(f"/proc/{login}/fd/0")
    slave = os.open(inner, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        if not inner.startswith("/dev/pts/") or termios.tcgetwinsize(slave) != (30, 80):
            raise RuntimeError("system login PTY is not 30 rows by 80 columns")
    finally:
        os.close(slave)


def run_once():
    if main_pid():
        raise RuntimeError("a private login service is already active")
    child, fd = pty.fork()
    if child == 0:
        termios.tcsetwinsize(0, (40, 100))
        os.execv(LAUNCHER, [LAUNCHER])
    reaped = False
    try:
        verify_prompt(fd)
        # Verify echo without submitting a username or attempting authentication.
        marker = b"sf-smoke-input"
        os.write(fd, marker)
        expect_screen(fd, marker, "the unsubmitted test input echo")
        subprocess.run(["systemctl", "stop", UNIT], check=True, capture_output=True, timeout=10)
        deadline = time.monotonic() + 12
        while receive(fd, deadline):
            pass
        while True:
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid:
                reaped = True
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("launcher did not exit after the supervisor stopped it")
            time.sleep(.02)
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) not in (0, 1, 143) or main_pid():
            raise RuntimeError("launcher did not clean up after the supervisor stopped it")
    finally:
        os.close(fd)
        if not reaped:
            subprocess.run(["systemctl", "stop", UNIT], capture_output=True, timeout=10)
            os.waitpid(child, 0)


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("The installed launcher test requires a private sudo session")
    for attempt in range(3):
        run_once()
        print(f"Run {attempt + 1}: login prompt, 30x80 inner PTY, UID boundary, input echo and shutdown passed",
              flush=True)
