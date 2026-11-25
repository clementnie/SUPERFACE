#!/usr/bin/env python3
"""Independent v1 peer for the production host backend over a Linux PTY."""
import binascii
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import termios
import time


def frame(kind, session, seq, payload=b""):
    data = struct.pack("<BBQIB", 1, kind, session, seq, len(payload)) + payload
    data += struct.pack("<H", binascii.crc_hqx(data, 0xFFFF))
    return b"\x7e" + data.replace(b"\x7d", b"\x7d\x5d").replace(b"\x7e", b"\x7d\x5e") + b"\x7e"


def unpack(wire):
    data = wire.replace(b"\x7d\x5e", b"\x7e").replace(b"\x7d\x5d", b"\x7d")
    version, kind, session, seq, length = struct.unpack_from("<BBQIB", data)
    assert version == 1 and session and len(data) == 17 + length, data
    assert binascii.crc_hqx(data[:-2], 0xFFFF) == int.from_bytes(data[-2:], "little")
    return kind, session, seq, data[15:-2]


class Peer:
    def __init__(self, fd):
        self.fd = fd
        self.buffer = bytearray()

    def read(self, seconds=2):
        end = time.monotonic() + seconds
        while True:
            if 0x7e in self.buffer:
                mark = self.buffer.index(0x7e)
                data = bytes(self.buffer[:mark])
                del self.buffer[:mark + 1]
                if data:
                    return unpack(data)
                continue
            ready, _, _ = select.select([self.fd], [], [], max(0, end - time.monotonic()))
            if not ready:
                raise TimeoutError("Timed out waiting for a host frame")
            self.buffer.extend(os.read(self.fd, 256))

    def send(self, kind, session, seq, payload):
        wire = frame(kind, session, seq, payload)
        for pos in range(0, len(wire), 7):
            assert os.write(self.fd, wire[pos:pos+7]) == len(wire[pos:pos+7])

    def ack(self, packet):
        kind, session, seq, _ = packet
        self.send(0x7f, session, seq, bytes([kind, 0]))


def snapshot(peer, *, retry=False, begin=0x10):
    request = peer.read()
    assert request[0] == begin and request[2:] == (1, b""), request
    session = request[1]
    peer.ack(request)
    grid = []
    for row in range(30):
        request = peer.read()
        assert request[:3] == (0x11, session, row+2) and len(request[3]) == 241, request[:3]
        assert request[3][0] == row
        if retry and row == 4:
            peer.send(0x7f, session ^ 1, row+2, b"\x11\x00")
            broken = bytearray(frame(0x7f, session, row+2, b"\x11\x00"))
            broken[1] ^= 1
            os.write(peer.fd, broken)
            assert peer.read() == request
        peer.ack(request)
        grid.append(request[3][1:])
    end = peer.read()
    assert end[:3] == (0x12, session, 32) and len(end[3]) == 3
    peer.ack(end)
    return grid


def main():
    master, slave = pty.openpty()
    device = os.ttyname(slave)
    executable = Path(__file__).resolve().parent / "build/superface"
    child = (
        "import os,tty,time; tty.setraw(0); "
        "os.write(1,b'\\x1b[2J\\x1b[H\\x1b[91;44mA~\\xe4\\xb8\\xad\\x1b[?25l'); "
        "b=os.read(0,1); time.sleep(.1); "
        "os.write(1,b'\\x1b[2;4H'+b+b'\\x1b[4;9H\\x1b[?25h'); "
        "b=os.read(0,1); time.sleep(.2); os.write(1,b'!')"
    )
    with subprocess.Popen([executable, "--uart", device, "--", sys.executable, "-c", child],
                          stderr=subprocess.PIPE) as proc:
        try:
            peer = Peer(master)
            geometry = bytes([80, 30, 3, 243, 7]) + bytes(18)
            extended = peer.read()
            assert extended[0] == 3 and peer.read() == extended
            kind, first, seq, wanted = peer.read()
            assert kind == 1 and seq == 0 and len(wanted) == 18 and any(wanted)
            settings = termios.tcgetattr(slave)
            assert settings[4:6] == [termios.B3000000] * 2
            assert settings[0] == termios.INPCK | termios.PARMRK
            try:
                os.open(device, os.O_RDWR | os.O_NONBLOCK)
            except OSError as error:
                assert error.errno == errno.EBUSY, error
            else:
                raise AssertionError("TIOCEXCL did not prevent a second opener")
            try:
                fcntl.flock(slave, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                raise AssertionError("cooperative tty lock is missing")
            peer.send(2, first, 0, bytes([2, 2]) + geometry)
            kind, session, seq, wanted = peer.read()
            assert kind == 1 and session != first and seq == 0 and wanted == bytes(18)
            peer.send(2, session, 0, bytes([0, 2]) + geometry)
            grid = snapshot(peer, retry=True)
            expected = bytes.fromhex("41 00 49 7e 00 49 3f 00 49 20 00 49")
            for _ in range(5):
                if grid[0].startswith(expected):
                    break
                request = peer.read()
                assert request[0] == 0x13 and request[3][0] == 0
                row, col, count = request[3][:3]
                grid[row] = (grid[row][:col*3] + request[3][3:] + grid[row][(col+count)*3:])
                peer.ack(request)
            assert grid[0].startswith(expected), grid[0][:12]

            # Deliver one key twice and a different byte with the same sequence.
            # The second key read in the child must remain blocked.
            peer.send(0x20, session, 1, b"\x00\x1c\xf0\x1c\xff")
            peer.send(0x20, session, 1, b"\x00\x32")
            assert peer.read() == (0x7f, session, 1, b"\x20\x00")
            time.sleep(.01)  # Let the first ACK leave the local serializer.
            peer.send(0x20, session, 1, b"\x00\x1c\xf0\x1c\xff")
            assert peer.read() == (0x7f, session, 1, b"\x20\x00")
            dirty = cursor = False
            for _ in range(8):
                if dirty and cursor:
                    break
                packet = peer.read()
                if packet[0] == 0x13:
                    dirty |= packet[3][:6] == b"\x01\x03\x01a\x00\x49"
                if packet[0] == 0x14:
                    cursor |= packet[3][:2] == bytes([3, 8])
                peer.ack(packet)
            assert dirty and cursor

            # Emulate a reset that forgets the session and all screen state.
            first_retry = peer.read()
            assert first_retry[0] in (0x14, 0x15)
            assert [peer.read() for _ in range(3)] == [first_retry] * 3
            extended = peer.read()
            assert extended[0] == 3 and peer.read() == extended
            kind, rejected, seq, wanted = peer.read()
            assert kind == 1 and rejected != session and seq == 0 and any(wanted)
            peer.send(2, rejected, 0, bytes([2, 2]) + geometry)
            kind, renewed, seq, wanted = peer.read()
            assert kind == 1 and renewed != rejected and seq == 0 and wanted == bytes(18)
            peer.send(2, renewed, 0, bytes([0, 2]) + geometry)
            grid = snapshot(peer)
            assert grid[0].startswith(expected) and grid[1][9:12] == b"a\x00\x49"
            # Cross an FPGA-originated event with a host reliable request.
            peer.send(0x20, renewed, 1, b"\x00\x32")
            assert peer.read() == (0x7f, renewed, 1, b"\x20\x00")
            deadline = time.monotonic() + 3
            while proc.poll() is None and time.monotonic() < deadline:
                try:
                    peer.ack(peer.read(.2))
                except TimeoutError:
                    pass
            assert proc.wait(timeout=1) == 0
            output = proc.stderr.read().decode()
            assert "sessions=2" in output and "retries=4" in output and "crc_errors=1" in output, output
            print("Host real backend PTY: 3 Mbaud settings, ownership, fallback, snapshot, CRC drop, retry, keys, dirty/cursor, reconnect")
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
            os.close(slave)
            os.close(master)


if __name__ == "__main__":
    main()
