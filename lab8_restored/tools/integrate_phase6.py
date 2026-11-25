#!/usr/bin/env python3
"""Apply once to pristine First Light source; preserve original lab circuits."""
from pathlib import Path
import phase5_schematics as b
root = Path(__file__).resolve().parents[1]
b.ROOT = root
p = root / 'LAB8.bdf'
s = p.read_text()
assert 'Physical_Set2' not in s
s = s[:s.index('(symbol (rect 680 2340')]
for old,new,y in [('Phase6_Off','PS2_Valid',2096),('Phase6_Off','PS2_Error',2120),
                  ('Phase6_Byte[7..0]','PS2_Byte[7..0]',2144),('Phase6_Off','PS2_Idle',2168)]:
    lines=s.splitlines(True)
    found=0
    for i,l in enumerate(lines):
        if '(connector ' in l and f'(pt 1560 {y})' in l:
            assert old in l
            lines[i]=l.replace(old,new); found+=1
    assert found == 1
    s=''.join(lines)
# Label the original pin-connected PS/2 receiver wires; retain seven-seg path.
for y,name in [(104,'PS2_CLK'),(120,'PS2_DAT')]: s += b.wire(name,1,8,-172,y)
s += b.symbol('PS2_Receiver','Physical_Set2',680,2340,dict(clk='CLOCK_50',reset='Link_Reset',
    ps2_clk='PS2_CLK',ps2_dat='PS2_DAT',source_valid='PS2_Valid',source_error='PS2_Error',
    source_byte='PS2_Byte[7..0]',idle_qualified='PS2_Idle'))
p.write_text(s)
(root/'PS2_Receiver.bsf').write_text('(header "symbol" (version "1.1"))\n'+b.symbol('PS2_Receiver','inst',0,0))
with (root/'LAB8.qsf').open('a') as f:
    f.write('\nset_global_assignment -name VHDL_FILE PS2_Receiver.vhd\n')
with (root/'LAB8.sdc').open('a') as f:
    f.write('''
# Only raw pin to first stage is asynchronous; stage two remains timed.
set_false_path -from [get_ports PS2_CLK] -to [get_registers {*PS2_Receiver*|clock_meta}]
set_false_path -from [get_ports PS2_DAT] -to [get_registers {*PS2_Receiver*|data_meta}]
''')
