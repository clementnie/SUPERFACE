#!/usr/bin/env python3
"""Focused header failures plus two full physical bus-model fault paths."""
import argparse,json,subprocess,zlib
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--ghdl',required=True); a=p.parse_args()
root=Path(__file__).resolve().parents[2]
base=(root/'assets/fonts/superface_font.bin').read_bytes()
mapping=json.loads((root/'assets/fonts/font_manifest.json').read_text())['mapping']
def crc(b): b[60:64]=zlib.crc32(b[:60]).to_bytes(4,'little'); return b
cases=[('valid',base,0)]
b=bytearray(base); b[:64]=b'\xff'*64; cases.append(('missing',b,2))
b=bytearray(base); b[60]^=1; cases.append(('header-crc',b,3))
b=bytearray(base); b[20]^=1; cases.append(('mapping',crc(b),4))
b=bytearray(base); b[16:20]=(524289).to_bytes(4,'little'); cases.append(('bounds',crc(b),4))
b=bytearray(base); b[12:14]=(mapping['sram_count']+1).to_bytes(2,'little'); cases.append(('count',crc(b),4))
b=bytearray(base); b[40]=1; cases.append(('reserved',crc(b),3))
b=bytearray(base); b[64+24]=1; cases.append(('padding',b,3))
b=bytearray(base); b[64+mapping['chinese_count']*32+31]=1; cases.append(('single-high-byte',b,3))
limit=mapping.get('narrow_id_limit',mapping['last_sram_id']+1)
if limit<=mapping['last_sram_id']:
    b=bytearray(base); b[64+(limit-0x8000)*32+24]=1; cases.append(('extended-wide-padding',b,3))
b=bytearray(base); b[100]^=1; cases.append(('payload-crc',b,3))
cases.append(('sram-readback',base,1))
for name,data,fault in cases:
    f=Path(f'{name}.hex'); f.write_text(''.join(f'{x:02x}\n' for x in data))
    with Path(f'{name}.log').open('w') as log:
        r=subprocess.run([a.ghdl,'-r','--std=08','phase7_font_tb',f'-gimage_file={f}',f'-gfault={fault}','--assert-level=error'],stdout=log,stderr=subprocess.STDOUT)
    print(name, 'PASS' if r.returncode==0 else 'FAIL',flush=True)
    if r.returncode: raise SystemExit(r.returncode)
