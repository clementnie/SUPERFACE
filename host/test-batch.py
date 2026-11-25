#!/usr/bin/env python3
"""Exercise the negotiated host display scheduler against an independent PTY peer."""
import os
from pathlib import Path
import pty
import runpy
import subprocess
import sys
import time

protocol = runpy.run_path(str(Path(__file__).with_name("test-uart-link.py")))
Peer = protocol["Peer"]
snapshot = protocol["snapshot"]
CHILD = """
import os
import tty
tty.setraw(0)
os.write(1, b'\\x1b[?25l')
first = os.read(0, 1)
os.write(1, b'\\x1b[1;1H' + first + '┌⣿☃😀?'.encode()
         + b'\\x1b[5;3Htesting\\x1b[6;4Hdone')
second = os.read(0, 1)
os.write(1, b'\\x1b[5;3H' + second)
"""


def main():
    master, slave = pty.openpty()
    executable = Path(__file__).resolve().parent / "build/superface"
    with subprocess.Popen([executable, "--uart", os.ttyname(slave), "--keyboard", "colemak",
                           "--", sys.executable, "-c", CHILD], stderr=subprocess.PIPE) as process:
        try:
            peer = Peer(master)
            kind, session, seq, wanted = peer.read()
            assert kind == 3 and seq == 0 and any(wanted)
            peer.send(2, session, 0, bytes([1, 0, 80, 30, 3, 243, 31]) + wanted)
            time.sleep(.015)
            snapshot(peer, begin=0x18)
            peer.send(0x20, session, 1, b"\x00\x24")
            assert peer.read() == (0x7f, session, 1, b"\x20\x00")
            first = peer.read()
            assert first[0] == 0x16 and first[3][:3] == bytes((0, 0, 7)), first
            ids = [int.from_bytes(first[3][3+i:5+i], "little") for i in range(0, 21, 3)]
            assert ids[0] == ord("f") and ids[1] >= 0x9abc and ids[2] >= 0x9abc
            assert ids[3:] == [0x7f, 0x80, 0xffff, ord("?")], ids
            # A crossed key must be ACKed while a display staging request waits.
            peer.send(0x20, session, 2, b"\x00\x2c")
            assert peer.read() == (0x7f, session, 2, b"\x20\x00")
            peer.ack(first)
            for expected_row in (4, 5):
                packet = peer.read()
                assert packet[0] == 0x16 and packet[3][0] == expected_row, packet
                peer.ack(packet)
            commit = peer.read()
            assert commit[0] == 0x17 and len(commit[3]) == 3
            peer.ack(commit)
            latest = peer.read()
            assert latest[0] == 0x16 and latest[3] == bytes((4, 2, 1, ord("g"), 0, 7)), latest
            peer.ack(latest)
            commit = peer.read()
            assert commit[0] == 0x17
            peer.ack(commit)
            assert process.wait(timeout=3) == 0, process.stderr.read()
            print("Negotiated host batch, coherent multiline staging, crossed Colemak keys, Unicode widths and latest-state flush PASS")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
            os.close(slave)
            os.close(master)


if __name__ == "__main__":
    main()
