library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
package Font_CRC is
    function crc_byte(crc: unsigned(31 downto 0); data: std_logic_vector(7 downto 0)) return unsigned;
    constant glyphs : natural := 16384;
    constant wide_glyphs : natural := 6844;
    constant narrow_end : natural := 12086;
    constant payload_bytes : natural := glyphs*32;
    function wide_glyph(id: unsigned(15 downto 0)) return boolean;
    function narrow_glyph(id: unsigned(15 downto 0)) return boolean;
    constant mapping : std_logic_vector(127 downto 0) := x"3b16b688374f2ca0af67d2836bc19b16";
    -- Packed UART payload vectors place the first digest byte in bits 7..0.
    constant wire_mapping : std_logic_vector(127 downto 0) := x"169bc16b83d267afa02c4f3788b6163b";
end;
package body Font_CRC is
    function wide_glyph(id: unsigned(15 downto 0)) return boolean is
    begin
        return (id >= 16#8000# and id < 16#8000# + wide_glyphs) or
               (id >= 16#8000# + narrow_end and id < 16#8000# + glyphs);
    end;
    function narrow_glyph(id: unsigned(15 downto 0)) return boolean is
    begin
        return id >= 16#8000# + wide_glyphs and id < 16#8000# + narrow_end;
    end;
    function crc_byte(crc: unsigned(31 downto 0); data: std_logic_vector(7 downto 0)) return unsigned is
        variable c: unsigned(31 downto 0) := crc xor resize(unsigned(data),32);
    begin
        for i in 0 to 7 loop
            if c(0)='1' then c:=shift_right(c,1) xor x"EDB88320";
            else c:=shift_right(c,1); end if;
        end loop;
        return c;
    end;
end;
