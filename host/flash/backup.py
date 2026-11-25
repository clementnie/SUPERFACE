#!/usr/bin/env python3
"""Read-only maintenance SOF capture. Never sends NOR erase/program commands."""
import array,fcntl,hashlib,json,os,select,struct,sys,termios,time,zlib
from pathlib import Path
repeat = 1 if sys.argv[2:] == ['--once'] else 2
assert sys.argv[2:] in ([], ['--once'])
p=Path(sys.argv[1]); p.mkdir(mode=0o700,parents=False,exist_ok=False)
fd=os.open('/dev/ttyS2',os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.ioctl(fd,termios.TIOCEXCL)
def counters():
    c=array.array('i',[0]*20)
    fcntl.ioctl(fd,0x545D,c,True)
    return list(c)
a=termios.tcgetattr(fd); a[0]=0; a[1]=0; a[2]=termios.CS8|termios.CREAD|termios.CLOCAL; a[3]=0
a[4]=termios.B3000000; a[5]=termios.B3000000; a[6][termios.VMIN]=0; a[6][termios.VTIME]=0
termios.tcsetattr(fd,termios.TCSANOW,a); termios.tcflush(fd,termios.TCIOFLUSH)
before=counters()
def read_n(n):
    b=bytearray(); deadline=time.monotonic()+40
    while len(b)<n:
        if time.monotonic()>deadline: raise TimeoutError(f'UART capture {len(b)}/{n}')
        if select.select([fd],[],[],1)[0]:
            try: b.extend(os.read(fd,min(65536,n-len(b))))
            except BlockingIOError: pass
    return b
records=[]; first=None
for run in range(1, repeat + 1):
    os.write(fd,b'B')
    h=read_n(12); assert h[:8]==b'SFBAK1\r\n',h.hex()
    n=struct.unpack_from('<I',h,8)[0]; assert n==4194304,n
    b=read_n(n); wire_crc=struct.unpack('<I',read_n(4))[0]
    assert zlib.crc32(b)==wire_crc, 'CRC mismatch'
    if first is None: first=b
    else: assert first==b,'Independent full-array reads differ'
    out=p/f'flash-read{run}.bin'
    with out.open('xb') as f: os.chmod(out,0o600); f.write(b); f.flush(); os.fsync(f.fileno())
    record=dict(run=run,bytes=n,sha256=hashlib.sha256(b).hexdigest(),crc32=f'{wire_crc:08x}',non_ff=sum(v!=255 for v in b))
    records.append(record); print(json.dumps(record),flush=True)
    time.sleep(.1)
after=counters(); assert before[6:11]==after[6:11],(before[6:11],after[6:11])
os.close(fd)
result=dict(status='PASS',device_reported='Spansion S29AL032D70TFI04',records=records,
            byte_equal=True if repeat == 2 else None,counters_before=before,counters_after=after)
(p/'backup-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'PASS {repeat} complete 4MiB read(s), wire CRC, SHA-256 and unchanged UART error counters', flush=True)
