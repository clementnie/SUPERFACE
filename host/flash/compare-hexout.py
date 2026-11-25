#!/usr/bin/env python3
"""Strict vendor readback decoder: checksum, address coverage, exact bytes."""
import hashlib,json,sys,zlib
from pathlib import Path
expected=Path(sys.argv[2]).read_bytes(); decoded=bytearray(); high=0; eof=False
for line in Path(sys.argv[1]).read_text().splitlines():
 if not line.startswith(':'):continue
 b=bytes.fromhex(line[1:]);assert len(b)==b[0]+5 and sum(b)%256==0,'Intel HEX checksum/length'
 if b[3]==4:assert b[0]==2;high=int.from_bytes(b[4:-1],'big')<<16
 elif b[3]==0:
  address=high+int.from_bytes(b[1:3],'big');assert address==len(decoded),'Missing/overlapping/out-of-order data'
  decoded.extend(b[4:-1])
 elif b[3]==1:eof=True
 else:raise ValueError(f'Unexpected record type {b[3]}')
assert eof and len(decoded)==4194304 and decoded==expected,'Flash readback differs'
print(json.dumps(dict(status='PASS',bytes=len(decoded),sha256=hashlib.sha256(decoded).hexdigest(),crc32=f'{zlib.crc32(decoded):08x}',byte_equal=True)))
