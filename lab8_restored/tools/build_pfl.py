#!/usr/bin/env python3
"""Prepare isolated vendor PFL maintenance bridge; never runs Programmer."""
import os,sys,shutil
from pathlib import Path
import phase5_schematics as b
source=Path(__file__).resolve().parents[1]; dest=Path(sys.argv[1]); dest.mkdir()
shutil.copy(source/'PFL_Bridge.vhd',dest/'PFL_Bridge.vhd'); b.ROOT=dest
# Generate a native BDF top and BSF, marking the flash-data port bidirectional.
b.PORTS['PFL_Bridge']=[('clock','in',1),('reset_n','in',1),('flash_data','in',8),('flash_addr','out',22),
  *[(f'flash_{v}_n','out',1) for v in ('ce','oe','we','rst')],*[(f'sram_{v}_n','out',1) for v in ('ce','oe','we')]]
nets=dict(clock='CLOCK_50',reset_n='KEY3_N',flash_data='FL_DQ[7..0]',flash_addr='FL_ADDR[21..0]',
 **{f'flash_{v}_n':f'FL_{v.upper()}_N' for v in ('ce','oe','we','rst')},
 **{f'sram_{v}_n':f'SRAM_{v.upper()}_N' for v in ('ce','oe','we')})
ports=[('CLOCK_50','in',1),('KEY3_N','in',1),('FL_DQ','in',8),('FL_ADDR','out',22),
 *[(f'FL_{v}_N','out',1) for v in ('CE','OE','WE','RST')],*[(f'SRAM_{v}_N','out',1) for v in ('CE','OE','WE')]]
b.sheet('PFL_Maintenance',ports,[('PFL_Bridge','Vendor_CFI_JTAG_Bridge',560,100,nets)],
 ['Vendor PFL, 8-bit CFI parallel Flash, separate maintenance SOF',
 'NOT a terminal image. No host erase/program action permitted before explicit authorization.'])
for path in [dest/'PFL_Maintenance.bdf']:
 s=path.read_text();s='\n'.join(l.replace('(input)','(bidir)') if '(port ' in l and '"flash_data[' in l else l for l in s.split('\n'))
 s='\n'.join(l.replace('(pin (input)','(pin (bidir)') if '(pin ' in l and '"FL_DQ[' in l else l for l in s.split('\n'))
 path.write_text(s)
s=b.symbol('PFL_Bridge','inst',0,0)
s='\n'.join(l.replace('(input)','(bidir)') if '(port ' in l and '"flash_data[' in l else l for l in s.split('\n'))
(dest/'PFL_Bridge.bsf').write_text('(header "symbol" (version "1.1"))\n'+s)
quartus_sh = shutil.which("quartus_sh")
quartus_root = os.environ.get("QUARTUS_ROOTDIR")
if not quartus_root and not quartus_sh:
    raise SystemExit("Put quartus_sh on PATH or set QUARTUS_ROOTDIR")
quartus_root = Path(quartus_root) if quartus_root else Path(quartus_sh).resolve().parent.parent
ip = quartus_root / "libraries/megafunctions/altparallel_flash_loader.vhd"
if not ip.is_file():
    raise SystemExit(f"Quartus PFL source missing: {ip}")
q=f'''set_global_assignment -name FAMILY "Cyclone II"
set_global_assignment -name DEVICE EP2C20F484C7
set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"
set_global_assignment -name TOP_LEVEL_ENTITY PFL_Maintenance
set_global_assignment -name BDF_FILE PFL_Maintenance.bdf
set_global_assignment -name VHDL_FILE "{ip}"
set_global_assignment -name VHDL_FILE PFL_Bridge.vhd
set_global_assignment -name SDC_FILE PFL_Maintenance.sdc
set_location_assignment PIN_L1 -to CLOCK_50
set_location_assignment PIN_T21 -to KEY3_N
set_location_assignment PIN_AB15 -to FL_CE_N
'''
for l in (source/'LAB8.qsf').read_text().splitlines():
 if l.startswith('set_location_assignment') and ('-to FL_' in l or any('-to SRAM_'+v+'_N' in l for v in ('CE','OE','WE'))):
  if '-to FL_CE_N' not in l:q+=l+'\n'
for name,_,size in ports:
 q+=f'set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to {name}{"[*]" if size>1 else ""}\n'
(dest/'PFL_Maintenance.qsf').write_text(q)
(dest/'PFL_Maintenance.qpf').write_text('PROJECT_REVISION = "PFL_Maintenance"\n')
(dest/'PFL_Maintenance.sdc').write_text('# Programming-only PFL uses JTAG TCK, not the pruned board clock.\ncreate_clock -name jtag10m -period 100.000 [get_ports altera_reserved_tck]\n')
(dest/'VENDOR_IP_COLLATERAL.txt').write_text('Uses installed Quartus II 13.0 SP1 altparallel_flash_loader megafunction and its standard vendor dependencies. Not application-authored flash programming algorithms.\n')
