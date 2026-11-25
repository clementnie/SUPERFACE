#!/usr/bin/env python3
"""Prepare-only: write a reviewable extlinux candidate; never modify /boot.
Any later installation requires explicit operator authorization and backup.
"""
import hashlib,re,sys
from pathlib import Path
source=Path(sys.argv[1]); dest=Path(sys.argv[2]); data=source.read_bytes()
assert sys.argv[3]==hashlib.sha256(data).hexdigest(),'Boot config changed'
s=data.decode(); label='superface-uart2-clock'
assert len(re.findall(r'^\s*LABEL\s+'+label+r'\s*$',s,re.I|re.M))==1
assert len(re.findall(r'^[ \t]*DEFAULT[ \t]+[^\r\n]+',s,re.I|re.M))==1
new=re.sub(r'^([ \t]*DEFAULT[ \t]+)[^\r\n]+',lambda m:m[1]+label,s,flags=re.I|re.M)
assert new!=s,'Already default; inspect rather than changing'
with dest.open('xb') as f:f.write(new.encode())
print('Prepared only:',dest,'SHA256',hashlib.sha256(new.encode()).hexdigest())
