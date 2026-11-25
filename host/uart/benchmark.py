#!/usr/bin/env python3
"""Measure command-to-visible-ACK latency on an idle physical SUPERFACE link."""
import argparse
import binascii
import fcntl
import os
import secrets
import select
import struct
import termios
import time
import tty


def packet(kind, session, seq, body):
    raw = struct.pack("<BBQIB", 1, kind, session, seq, len(body)) + body
    raw += struct.pack("<H", binascii.crc_hqx(raw, 0xffff))
    return b"\x7e" + raw.replace(b"\x7d", b"\x7d\x5d").replace(b"\x7e", b"\x7d\x5e") + b"\x7e"


class Link:
    def __init__(self, fd):
        self.fd = fd
        self.session = secrets.randbits(64) or 1
        self.seq = 1
        self.keys = 0
        self.wire_bytes = 0
        self.pending = bytearray()

    def send(self, kind, seq, body):
        frame = packet(kind, self.session, seq, body)
        self.wire_bytes += len(frame)
        assert os.write(self.fd, frame) == len(frame)

    def wait(self, kind, seq, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while b"\x7e" in self.pending:
                frame, _, self.pending = self.pending.partition(b"\x7e")
                raw = frame.replace(b"\x7d\x5e", b"\x7e").replace(b"\x7d\x5d", b"\x7d")
                if len(raw) < 17:
                    continue
                version, received, session, number, size = struct.unpack("<BBQIB", raw[:15])
                if version != 1 or session != self.session or len(raw) != 17 + size:
                    continue
                assert int.from_bytes(raw[-2:], "little") == binascii.crc_hqx(raw[:-2], 0xffff)
                data = raw[15:-2]
                if received == 0x20:
                    self.keys += len(data) - 1
                    self.send(0x7f, number, b"\x20\x00")
                elif received == kind and number == seq:
                    return data
            remaining = max(0, deadline - time.monotonic())
            if select.select([self.fd], [], [], remaining)[0]:
                self.pending.extend(os.read(self.fd, 1024))
        return None

    def command(self, kind, body=b"", expected=0, replay=False):
        tries = 2 if replay else 1
        for _ in range(tries):
            self.send(kind, self.seq, body)
            answer = self.wait(0x7f, self.seq, .25)
            assert answer == bytes((kind, expected)), (kind, self.seq, answer)
        self.seq += 1


def grid_cell(character, color=7):
    return bytes((ord(character), 0, color))


def run(link, batch):
    cursor = bytes((0, 0, 0))
    for _ in range(5):
        link.send(3 if batch else 1, 0, bytes(18))
        hello = link.wait(2, 0, .25)
        if hello is not None:
            break
    assert (hello and hello[0] == 0 and hello[2:6] == bytes((80, 30, 3, 243)) and
           hello[6] in ((15, 31) if batch else (7,))), hello
    link.command(0x18 if hello[6] == 31 else 0x10)
    for row in range(30):
        link.command(0x11, bytes((row,)) + grid_cell(" ") * 80)
    link.command(0x12, cursor)

    def update(spans):
        for row, col, count, ch in spans:
            link.command(0x16 if batch else 0x13, bytes((row, col, count)) + grid_cell(ch) * count)
        if batch:
            link.command(0x17, cursor)

    def measure(name, spans):
        start, old = time.monotonic(), link.wire_bytes
        update(spans)
        print(f"{name} visible_ack_ms={(time.monotonic() - start) * 1000:.2f} "
              f"tx_bytes={link.wire_bytes - old}", flush=True)

    measure("single", [(0, 0, 1, "A")])
    measure("multiline", [(r, 3, 15, "B") for r in range(8)])
    measure("full", [(r, 0, 80, "C") for r in range(30)])
    measure("clear", [(r, 0, 80, " ") for r in range(30)])
    start = time.monotonic()
    for frame in range(60):
        update([(r * 7, frame % 70, 4, "X" if frame % 2 else "O") for r in range(4)])
    duration = time.monotonic() - start
    print(f"sparse_coherent_hz={60 / duration:.2f} workload_seconds={duration:.2f} key_bytes={link.keys}")

    # CRC error is discarded; the same sequence then succeeds and replays an ACK.
    test = packet(0x15, link.session, link.seq, b"")
    bad = test[:2] + bytes((test[2] ^ 1,)) + test[3:]
    os.write(link.fd, bad)
    assert link.wait(0x7f, link.seq, .03) is None
    link.command(0x15, replay=True)
    if batch:
        link.command(0x16, b"\x00\x00\x01\xff\xff\x07", expected=3)
        link.command(0x17, cursor)
    print("CRC discard, duplicate replay and session continuation PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uart", default="/dev/ttyS2")
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()
    with open(args.uart, "r+b", buffering=0) as device:
        fd = device.fileno()
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            raw = termios.tcgetattr(fd)
            raw[2] = (raw[2] & ~(termios.CRTSCTS | termios.CSTOPB | termios.PARENB)) | termios.CLOCAL | termios.CREAD
            raw[4] = raw[5] = termios.B3000000
            termios.tcsetattr(fd, termios.TCSAFLUSH, raw)
            run(Link(fd), args.batch)
        finally:
            termios.tcsetattr(fd, termios.TCSAFLUSH, old)


if __name__ == "__main__":
    main()
