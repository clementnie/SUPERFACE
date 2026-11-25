#!/usr/bin/env python3
"""Integrate loader/ownership and independent boot overlay in the board BDF."""
from pathlib import Path
import re
import phase5_schematics as b
root=Path(__file__).resolve().parents[1]; b.ROOT=root
# Extend symbol discovery only for this script's bidirectional SRAM module.
def ports(name):
    if name not in b.PORTS:
        s=(root/f'{name}.vhd').read_text().split('end entity;')[0]
        declarations=re.search(r'\bport\s*\((.*)\);',s,re.S)[1]
        out=[]
        for d in declarations.split(';'):
            m=re.fullmatch(r'\s*([\w,\s]+):\s*(inout|in|out)\s+std_logic(?:_vector\((\d+) downto 0\))?\s*',d)
            assert m,(name,d)
            names,di,high=m.groups()
            out.extend((p.strip(),'in' if di=='inout' else di,int(high)+1 if high else 1) for p in names.split(','))
        b.PORTS[name]=out
    return b.PORTS[name]
b.module_ports=ports

def bidir(s,name):
    # Generated symbol ports are one line each.
    return '\n'.join(l.replace('(input)','(bidir)') if '(port ' in l and f'"{name}[' in l else l for l in s.split('\n'))

shared=dict(clk='clk',reset='reset')
font=dict(font_ready='font_ready',runtime_owner='runtime_owner',font_status='font_status[2..0]',
          font_count='font_count[14..0]',font_mapping='font_mapping[127..0]')
fp=[('clk','in',1),('reset','in',1),('render_address','in',18),
    *[(f'render_{v}_n','in',1) for v in ('ce','oe','we','lb','ub')],
    ('flash_data','in',8),('sram_dq','in',16),('flash_addr','out',22),
    *[(f'flash_{v}_n','out',1) for v in ('ce','oe','we','rst')],('sram_addr','out',18),
    *[(f'sram_{v}_n','out',1) for v in ('ce','oe','we','lb','ub')],
    ('font_ready','out',1),('runtime_owner','out',1),('font_status','out',3),
    ('font_count','out',15),('font_mapping','out',128)]
b.sheet('Font_Startup',fp,[
 ('Parallel_Flash_Read','Read_Only_NOR',560,100,dict(**shared,request='Flash_Request',address='Flash_Address[21..0]',
  flash_data='flash_data[7..0]',flash_addr='flash_addr[21..0]',ce_n='flash_ce_n',oe_n='flash_oe_n',we_n='flash_we_n',
  rst_n='flash_rst_n',ready='Flash_Ready',done='Flash_Done',data='Flash_Byte[7..0]')),
 ('Font_Loader','Header_CRC_Copy_Readback',560,700,dict(**shared,**font,flash_ready='Flash_Ready',flash_done='Flash_Done',
  flash_data='Flash_Byte[7..0]',flash_request='Flash_Request',flash_address='Flash_Address[21..0]',
  memory_request='Memory_Request',memory_write='Memory_Write',memory_done='Memory_Done',
  memory_address='Memory_Address[17..0]',memory_wdata='Memory_Write_Data[15..0]',memory_data='Memory_Read_Data[15..0]')),
 ('SRAM_Owner','Exclusive_Bus_Owner',1440,100,dict(**shared,runtime_owner='runtime_owner',request='Memory_Request',
  write_word='Memory_Write',address='Memory_Address[17..0]',wdata='Memory_Write_Data[15..0]',
  rdata='Memory_Read_Data[15..0]',done='Memory_Done',sram_dq='sram_dq[15..0]',sram_addr='sram_addr[17..0]',
  render_address='render_address[17..0]',**{f'render_{v}_n':f'render_{v}_n' for v in ('ce','oe','we','lb','ub')},
  **{f'{v}_n':f'sram_{v}_n' for v in ('ce','oe','we','lb','ub')}))
],['Font startup: header + payload CRC32, exact mapping, bounded copy, SRAM readback',
   'WE# on NOR is permanently high. Renderer owns SRAM only after validation.'])
p=root/'Font_Startup.bdf'; s=bidir(p.read_text(),'sram_dq')
# Generated pin definitions occupy one line.
s='\n'.join(l.replace('(pin (input)','(pin (bidir)') if '(pin ' in l and '"sram_dq[' in l else l for l in s.split('\n'))
p.write_text(s)
for n in ('Parallel_Flash_Read','Font_Loader','SRAM_Owner','Font_Startup','Boot_Presentation'):
 s=b.symbol(n,'inst',0,0)
 if n in ('SRAM_Owner','Font_Startup'): s=bidir(s,'sram_dq')
 (root/f'{n}.bsf').write_text('(header "symbol" (version "1.1"))\n'+s)
# Split top-level BDF objects; respect quoted strings while balancing parens.
def objects(s):
    result=[]; start=0; depth=0; quoted=False
    for i,c in enumerate(s):
        if c=='"': quoted=not quoted
        if not quoted:
            if c=='(':
                if depth==0: start=i
                depth+=1
            elif c==')':
                depth-=1
                if depth==0: result.append(s[start:i+1])
    return result
p=root/'LAB8.bdf'; original=p.read_text(); assert 'Boot_Overlay' not in original
obs=objects(original[original.index('(header '):]); result=[]
for o in obs:
    if o.startswith('(symbol') and '"Phase5_Font"' in o: continue
    if o.startswith('(connector') and '(pt 1016 ' in o and any(f'(pt 1016 {y})' in o for y in (2156,2180,2204,2228,2252)): continue
    if o.startswith('(pin') and '"SRAM_DQ[' in o: o=o.replace('(input)','(bidir)',1)
    if o.startswith('(connector'):
        # Change only the display outputs, leaving physical pin labels intact.
        if '(pt 1244 726)' in o: o=o.replace('Terminal_RGB','Raw_RGB')
        for y,name in [(798,'ADDR'),(822,'CE_N'),(846,'OE_N'),(870,'LB_N'),(894,'UB_N'),(918,'WE_N')]:
            if f'(pt 1244 {y})' in o: o=o.replace(f'SRAM_{name}',f'Render_{name}')
    result.append(o)
s=original[:original.index('(header ')]+ '\n'.join(result)+'\n'
# Existing terminal display already exports the timing and snapshot state.
for name,size,y in [('Boot_Shown',1,1062),('Raster_X[9..0]',10,1086),('Raster_Y[9..0]',10,1110),
                    ('Pixel_Enable',1,1134),('VBlank',1,1182)]: s+=b.wire(name,size,1244,1500,y)
font_nets=dict(clk='CLOCK_50',reset='Display_Reset_High',render_address='Render_ADDR[17..0]',
    flash_data='FL_DQ[7..0]',sram_dq='SRAM_DQ[15..0]',flash_addr='FL_ADDR[21..0]',sram_addr='SRAM_ADDR[17..0]',
    **{f'render_{v}_n':f'Render_{v.upper()}_N' for v in ('ce','oe','we','lb','ub')},
    **{f'sram_{v}_n':f'SRAM_{v.upper()}_N' for v in ('ce','oe','we','lb','ub')},
    **{f'flash_{v}_n':f'FL_{v.upper()}_N' for v in ('ce','oe','we','rst')},
    font_ready='Font_Ready',runtime_owner='Runtime_Owner',font_status='Font_Status[2..0]',
    font_count='Font_Count[14..0]',font_mapping='Font_Mapping[127..0]')
s+=bidir(b.symbol('Font_Startup','Validated_Font_Boot',3000,300,font_nets),'sram_dq')
s+=b.symbol('Boot_Presentation','Boot_Overlay',3000,1300,dict(clk='CLOCK_50',reset='Display_Reset_High',
    pixel_enable='Pixel_Enable',vblank='VBlank',linked='Link_Active',font_ready='Font_Ready',shown='Boot_Shown',
    x='Raster_X[9..0]',y='Raster_Y[9..0]',terminal_rgb='Raw_RGB[11..0]',rgb='Terminal_RGB[11..0]'))
# Verify actual UART session output label spelling.

for i,(name,direction,size) in enumerate([('FL_DQ','in',8),('FL_ADDR','out',22),
                        ('FL_CE_N','out',1),('FL_OE_N','out',1),('FL_WE_N','out',1),('FL_RST_N','out',1)]):
    s+=b.pin(b.bits(name,size),direction,size,2400 if direction=='in' else 4200,2100+i*40)
p.write_text(s)
with (root/'LAB8.qsf').open('a') as f:
 f.write('\nset_location_assignment PIN_AB15 -to FL_CE_N\n')
 for n in ('FL_DQ[*]','FL_ADDR[*]','FL_CE_N','FL_OE_N','FL_WE_N','FL_RST_N'):
  f.write(f'set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to {n}\n')
 for n in ('Font_CRC','Parallel_Flash_Read','Font_Loader','SRAM_Owner','Boot_Presentation'):
  f.write(f'set_global_assignment -name VHDL_FILE {n}.vhd\n')
 f.write('set_global_assignment -name BDF_FILE Font_Startup.bdf\n')
