#!/usr/bin/env python3
"""Derive a small independent boot mask ROM from the unchanged pinned assets.
Font data remains covered by assets/fonts/LICENSES; no upstream regeneration.
"""
from pathlib import Path
import re,csv
root=Path(__file__).resolve().parents[2]
ascii_data=dict((int(a,16),int(v,2)) for a,v in re.findall(r'^([0-9A-F]+)\s*:\s*([01]{8})',(root/'lab8_restored/ascii_8x16.mif').read_text(),re.M))
mp={int(r['unicode'][2:],16):int(r['glyph_id'],16) for r in csv.DictReader((root/'assets/fonts/glyph_map.csv').open())}
payload=(root/'assets/fonts/superface_font.bin').read_bytes()[64:]
texts=['SUPERFACE','FPGA / LINUX TERMINAL','INITIALIZING FONTS...','WAITING FOR HOST SIGNAL... / 等待主机信号...', 'SIGNAL RECEIVED / 信号已接收','SYNCHRONIZING SCREEN...']
chars=sorted(set(''.join(texts)))
idx={c:i for i,c in enumerate(chars)}
rows=[]
for ch in chars:
 for y in range(16):
  if ord(ch)<128: mask=ascii_data[ord(ch)*16+y]<<8
  elif 2<=y<14:
   off=(mp[ord(ch)]-0x8000)*32+(y-2)*2
   mask=int.from_bytes(payload[off:off+2],'little')<<2
  else: mask=0
  rows.append(mask)
font='\n'.join(f'            when {i} => return x"{x:04X}";' for i,x in enumerate(rows) if x)
layout=[]
for n,t in enumerate(texts):
 cells=[]
 for c in t:
  cells.append((idx[c],False))
  if ord(c)>127: cells.append((idx[c],True))
 left=(80-len(cells))//2
 clauses='\n'.join(f'                    when {left+i} => glyph:={a}; right_half:={str(h).lower()};' for i,(a,h) in enumerate(cells))
 layout.append(f'            when {n} =>\n                case col is\n{clauses}\n                    when others => null;\n                end case;')
s='''library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
-- Independent prevalidated boot glyphs derived from canonical font assets.
-- Does not touch display memory, SRAM, protocol state, RX or command ACKs.
entity Boot_Presentation is
    generic (hold_cycles: natural := 195000000);
    port (clk, reset, pixel_enable, vblank, linked, font_ready, shown : in std_logic;
          x, y : in std_logic_vector(9 downto 0);
          terminal_rgb : in std_logic_vector(11 downto 0);
          terminal_hs_n, terminal_vs_n : in std_logic;
          rgb : out std_logic_vector(11 downto 0);
          hs_n, vs_n : out std_logic);
end entity;
architecture rtl of Boot_Presentation is
    signal was_linked, overlay_on : std_logic := '0';
    signal hold_ticks: natural range 0 to hold_cycles := 0;
    signal boot_rgb: std_logic_vector(11 downto 0) := x"000";
    signal terminal_color : std_logic_vector(11 downto 0);
    signal rom_addr : natural range 0 to 1023;
    signal bit_index : natural range 0 to 15;
    signal glyph_on, border_on : std_logic := '0';
    function bitmap(a: natural) return std_logic_vector is
    begin
        case a is
FONT
            when others => return x"0000";
        end case;
    end;
begin
    rgb<=boot_rgb when overlay_on='1' else terminal_color;
    process(clk)
        variable px,py,col,line_id,glyph: integer;
        variable right_half: boolean;
    begin
        if rising_edge(clk) then
            if reset='1' then
                was_linked<='0'; overlay_on<='1'; hold_ticks<=0;
                glyph_on<='0'; border_on<='0';
            else
                was_linked<=linked;
                if linked='0' then hold_ticks<=0;
                elsif was_linked='0' then hold_ticks<=hold_cycles;
                elsif hold_ticks>0 then hold_ticks<=hold_ticks-1; end if;
                -- Switch screens only at vertical blank after the hold AND full snapshot.
                if vblank='1' then
                    if linked='1' and hold_ticks=0 and shown='1' then overlay_on<='0';
                    else overlay_on<='1'; end if;
                end if;
                if pixel_enable='1' then
                    glyph_on<='0'; border_on<='0';
                    px:=to_integer(unsigned(x)); py:=to_integer(unsigned(y));
                    col:=px/8; line_id:=-1; glyph:=-1; right_half:=false;
                    if py/16=8 then line_id:=0;
                    elsif py/16=10 then line_id:=1;
                    elsif py/16=14 then
                        if font_ready='0' then line_id:=2;
                        elsif linked='0' then line_id:=3;
                        else line_id:=4; end if;
                    elsif py/16=17 and linked='1' then line_id:=5; end if;
                    case line_id is
LAYOUT
                        when others => null;
                    end case;
                    if px<640 and py<480 then
                        if py=108 or py=308 then border_on<='1'; end if;
                        if glyph>=0 then
                            glyph_on<='1';
                            rom_addr<=glyph*16+py mod 16;
                            if right_half then bit_index<=7-px mod 8;
                            else bit_index<=15-px mod 8; end if;
                        end if;
                    end if;
                end if;
            end if;
        end if;
    end process;
    -- Match the boot bitmap lookup stage on the normal video and sync paths.
    process(clk)
        variable mask : std_logic_vector(15 downto 0);
    begin
        if rising_edge(clk) then
            if reset='1' then
                boot_rgb<=x"000"; terminal_color<=x"000"; hs_n<='1'; vs_n<='1';
            elsif pixel_enable='1' then
                boot_rgb<=x"000";
                if border_on='1' then boot_rgb<=x"0A0"; end if;
                mask:=bitmap(rom_addr);
                if glyph_on='1' and mask(bit_index)='1' then boot_rgb<=x"5F5"; end if;
                terminal_color<=terminal_rgb;
                hs_n<=terminal_hs_n;
                vs_n<=terminal_vs_n;
            end if;
        end if;
    end process;
end;
'''.replace('FONT',font).replace('LAYOUT','\n'.join(layout))
(root/'lab8_restored/Boot_Presentation.vhd').write_text(s)
