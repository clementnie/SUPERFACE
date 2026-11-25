"""Exercise the diagnostic transfer engine with an independent PTY echo relay."""
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import subprocess
import struct
import time
import zlib

EXE = str(Path(__file__).resolve().parent / "build/superface-uart")

def relay(count, corrupt=False):
    master, slave = pty.openpty()
    os.set_blocking(master, False)
    with subprocess.Popen([EXE, "--pty-test", os.ttyname(slave), str(count)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        deadline = time.monotonic() + 10
        recorded = bytearray()
        pending = bytearray()
        try:
            while process.poll() is None:
                assert time.monotonic() < deadline
                rd, wr, _ = select.select([master], [master] if pending else [], [], .05)
                if rd:
                    data = os.read(master, 4096)
                    offset = len(recorded)
                    pending += data
                    recorded += data
                    if corrupt and offset <= 8192 < len(recorded):
                        pending[len(pending) - len(data) + 8192 - offset] ^= 1
                if wr:
                    del pending[:os.write(master, pending)]
            out, err = process.communicate(timeout=2)
        finally:
            if process.poll() is None:
                process.kill()
            os.close(master)
            os.close(slave)
    assert len(recorded) == count, (out, err)
    assert recorded[:16384] == b"".join(bytes([x]) * 4096 for x in (0, 255, 85, 170))
    tx = f"tx={count} crc32={zlib.crc32(recorded):08x}".encode()
    assert tx in out, (out, err)
    if corrupt:
        assert process.returncode == 1 and b"first_offset=8192" in err, (out, err)
    else:
        assert process.returncode == 0 and tx.replace(b"tx=", b"rx=") in out, (out, err)
    return re.search(rb"tx=.*", out)[0].decode()

def duplex(count, bad_crc=False):
    def stream(mask):
        return bytes(((i ^ (i >> 8) ^ (i >> 16)) & 255) ^ mask for i in range(count))

    host_data, fpga_data = stream(0x5a), stream(0xa5)
    reply = struct.pack("<4sIIII", b"SF5R", count,
                        zlib.crc32(host_data) ^ bad_crc, zlib.crc32(fpga_data), 0)
    master, slave = pty.openpty()
    os.set_blocking(master, False)
    with subprocess.Popen([EXE, "--pty-wire-test", os.ttyname(slave), str(count)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        deadline = time.monotonic() + 10
        received = bytearray()
        offset = 0
        try:
            while process.poll() is None:
                assert time.monotonic() < deadline
                available = len(fpga_data) if len(received) >= 2 else 0
                if len(received) == count + 2:
                    available += len(reply)
                rd, wr, _ = select.select([master], [master] if available > offset else [], [], .05)
                if rd:
                    received += os.read(master, 4096)
                    assert len(received) <= count + 2
                if wr:
                    data = fpga_data if offset < count else reply
                    pos = offset if offset < count else offset - count
                    offset += os.write(master, data[pos:pos + 1024])
            out, err = process.communicate(timeout=2)
        finally:
            if process.poll() is None:
                process.kill()
            os.close(master)
            os.close(slave)
    assert received == b"SF" + host_data
    assert f"fpga rx={count}".encode() in out, (out, err)
    assert b"mismatches=0" in out and process.returncode == int(bad_crc), (out, err)


master, slave = pty.openpty()
try:
    fcntl.flock(slave, fcntl.LOCK_EX | fcntl.LOCK_NB)
    blocked = subprocess.run([EXE, "--pty-test", os.ttyname(slave), "16384"],
                             capture_output=True, timeout=3)
    assert blocked.returncode == 1 and b"exclusive tty ownership" in blocked.stderr
    assert not select.select([master], [], [], 0)[0]
finally:
    os.close(slave)
    os.close(master)

print(relay(4 * 1024 * 1024))
print(relay(32768, corrupt=True))
print("Diagnostic PTY transport and corruption detection passed")

duplex(131072)
duplex(32768, bad_crc=True)
print("Independent PTY wire-rate streams and CRC trailer checks passed")
