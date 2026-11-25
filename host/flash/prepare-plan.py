#!/usr/bin/env python3
"""Prepare private preservation/recovery images and a complete sector inventory.
This script never opens hardware and never erases/programs anything.
"""
import hashlib,json,sys,zlib
from pathlib import Path
backup=Path(sys.argv[1]); font=Path(sys.argv[2]); out=Path(sys.argv[3]);out.mkdir(mode=0o700,exist_ok=True)
a=backup.read_bytes(); f=font.read_bytes()
assert len(a)==4194304 and hashlib.sha256(a).hexdigest()=='89d89e047d50f2535c5275d1e404486cd7a6c3ebedfb0d2106b4c38340759ba0'
assert len(f)==215328 and hashlib.sha256(f).hexdigest()=='46bba61583b33306037cc2a995b152f83ead2f7b5dcb6f95b8549a193f9c9852'
assert zlib.crc32(f[:60])==int.from_bytes(f[60:64],'little') and zlib.crc32(f[64:])==int.from_bytes(f[36:40],'little')
b=f+a[len(f):]; assert b[len(f):]==a[len(f):]
def sha(d):return hashlib.sha256(d).hexdigest()
def intelhex(data):
 lines=[]
 def record(address,kind,payload):
  s=bytes([len(payload),address>>8,address&255,kind])+payload
  lines.append(':'+s.hex().upper()+f'{(-sum(s))&255:02X}')
 for high in range((len(data)+65535)//65536):
  record(0,4,high.to_bytes(2,'big'))
  for lo in range(0,min(65536,len(data)-high*65536),32):record(lo,0,data[high*65536+lo:high*65536+lo+32])
 record(0,1,b'');return '\n'.join(lines)+'\n'
for name,data in [('recovery-original',a),('candidate-preserved',b)]:
 (out/f'{name}.bin').write_bytes(data); (out/f'{name}.hex').write_text(intelhex(data))
 # Independent decode of Intel HEX, including record checksums and complete coverage.
 decoded=bytearray();high=0
 for line in (out/f'{name}.hex').read_text().splitlines():
  r=bytes.fromhex(line[1:]);assert sum(r)%256==0
  if r[3]==4:high=int.from_bytes(r[4:-1],'big')<<16
  elif r[3]==0:
   addr=high+int.from_bytes(r[1:3],'big'); assert addr==len(decoded);decoded.extend(r[4:-1])
 assert decoded==data
regions=[(i*8192,(i+1)*8192) for i in range(8)]+[(65536+i*65536,65536+(i+1)*65536) for i in range(63)]
sectors=[]
for i,(start,end) in enumerate(regions):
 sectors.append(dict(sector=i,start=start,end_exclusive=end,bytes=end-start,
  original_sha256=sha(a[start:end]),candidate_sha256=sha(b[start:end]),
  changed_bytes=sum(x!=y for x,y in zip(a[start:end],b[start:end])),
  original_non_ff=sum(x!=255 for x in a[start:end]),font_overlap=max(0,min(end,len(f))-start)))
plan=dict(device='S29AL032D70TFI04',mode='byte-wide',capacity=len(a),
 geometry='8 x 8KiB bottom boot, then 63 x 64KiB',sectors=sectors,
 candidate_sha256=sha(b),recovery_sha256=sha(a),font_bytes=len(f),
 minimum_sector_erase_end=0x40000,minimum_sector_erase_count=11,
 programming_authorized=False,recovery_physical_test='NOT RUN',
 conservative_vendor_operation_scope='All 71 sectors / 4MiB until vendor erase behavior is independently verified. Full candidate preserves every byte beyond font payload.')
(out/'sector-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print('PASS binary and Intel HEX round-trip; 71-sector original/candidate inventory; original backups unchanged')
