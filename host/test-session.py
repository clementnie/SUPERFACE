"""End-to-end tests through real child processes, Linux PTYs and simulated FPGA."""
import csv
import os
from pathlib import Path
import pty
import re
import select
import signal
import subprocess
import sys
import time

EXE = str(Path(__file__).resolve().parent / "build/superface")
FONTS = Path(__file__).resolve().parents[1] / "assets/fonts"
GLYPHS = {int(row["unicode"][2:], 16): int(row["glyph_id"], 16)
          for row in csv.DictReader((FONTS / "glyph_map.csv").open())}

CHILD = r"""
import fcntl, os, struct, termios, time, tty
assert os.isatty(0) and os.isatty(1) and os.isatty(2)
assert os.getpid() == os.getsid(0) == os.tcgetpgrp(0)
assert struct.unpack("HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0"*8))[:2] == (30, 80)
expected_term = "superface" if os.access("/usr/share/terminfo/s/superface", os.R_OK) else "xterm"
assert os.environ["LC_ALL"] == "C.UTF-8" and os.environ["TERM"] == expected_term
tty.setraw(0)
os.write(1, b"\x1b[?25l\x1b[4;2H\x1b[91;44mA\xe4")
time.sleep(.035)
os.write(1, b"\xb8")
time.sleep(.035)
os.write(1, b"\xad")
os.write(1, "墚".encode())
os.write(1, b"\x1b[0m\x1b[6n")
reply = b""
while not reply.endswith(b"R"):
    reply += os.read(0, 1)
assert reply == b"\x1b[4;7R", reply
os.write(1, b"\x1b[6;1HREPLY OK")
"""

def assert_grid(stdout, font):
    expected = [["200007"] * 80 for _ in range(30)]
    han = f'{GLYPHS[ord("中")]:04x}'
    expected[3][1:6] = ["410049", han[2:] + han[:2] + "49" if font else "3f0049",
                        "ffff49" if font else "200049", "3f0049", "200049"]
    expected[5][:8] = [f"{c:02x}0007" for c in b"REPLY OK"]
    lines = stdout.splitlines()
    assert [line.split() for line in lines[:-1]] == expected
    assert lines[-1] == "cursor 5 8 0"

for font in (True, False):
    option = [] if font else ["--ascii"]
    result = subprocess.run([EXE, *option, "--dump", "--", sys.executable, "-c", CHILD],
                            check=True, text=True, capture_output=True, timeout=8)
    assert_grid(result.stdout, font)

environment = {**os.environ, "SHELL": "/bin/sh", "PS1": "sf$ ", "ENV": "/dev/null"}
result = subprocess.run([EXE, "--stdin", "--dump"],
                        input="printf '\\033[2J\\033[H'; stty size; printf '%s' shell-ok; exit 7\n",
                        env=environment, text=True, capture_output=True, timeout=8)
assert result.returncode == 7, result.stderr
rows = result.stdout.splitlines()
assert rows[0].split()[:5] == [f"{c:02x}0007" for c in b"30 80"]
assert rows[1].split()[:8] == [f"{c:02x}0007" for c in b"shell-ok"]

# Supervise both a normally terminating real command and clean signal handling.
with subprocess.Popen([EXE, "--", "sleep", "60"]) as proc:
    deadline = time.monotonic() + 3
    children = Path(f"/proc/{proc.pid}/task/{proc.pid}/children")
    while not (pids := children.read_text().split()):
        assert time.monotonic() < deadline
        time.sleep(.01)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=3) == 128 + signal.SIGTERM
    assert all(not Path(f"/proc/{pid}").exists() for pid in pids)

# The login utility can close every slave descriptor while reopening its tty.
# Reproduce that gap without authenticating or changing the system login program.
reopen = r"""
import os, time
slave = os.ttyname(0)
for fd in range(3):
    os.close(fd)
time.sleep(.15)
fd = os.open(slave, os.O_RDWR | os.O_NOCTTY)
os.write(fd, b"PTY REOPEN OK")
"""
result = subprocess.run([EXE, "--dump", "--", sys.executable, "-c", reopen],
                        check=True, text=True, capture_output=True, timeout=8)
assert result.stdout.splitlines()[0].split()[:13] == [f"{c:02x}0007" for c in b"PTY REOPEN OK"]

assert subprocess.run([EXE, "--login"], capture_output=True, timeout=3).returncode == 2

# Live display and keyboard use a separate outer PTY without recording a login.
master, slave = pty.openpty()
try:
    with subprocess.Popen([EXE, "--view", "--", "/bin/sh", "-c",
                           "printf 'private development view'; read line; test \"$line\" = exit"],
                          stdin=slave, stdout=slave, stderr=slave) as proc:
        deadline = time.monotonic() + 3
        received = b""
        while b"private development view" not in received:
            assert time.monotonic() < deadline
            if select.select([master], [], [], .1)[0]:
                received += os.read(master, 65536)
        os.write(master, b"exit\r")
        assert proc.wait(timeout=3) == 0
        received = b""
        while select.select([master], [], [], 0)[0]:
            received += os.read(master, 65536)
        assert re.search(rb"\x1b\[\?1049l", received)
finally:
    os.close(slave)
    os.close(master)

print("PTY shell, command, terminal replies, both simulated grids, view and signal cleanup passed")
