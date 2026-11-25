library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
package Font_CRC is
    function crc_byte(crc: unsigned(31 downto 0); data: std_logic_vector(7 downto 0)) return unsigned;
    constant glyphs : natural := 7496;
    constant wide_glyphs : natural := 6844;
    constant payload_bytes : natural := glyphs*32;
    constant mapping : std_logic_vector(127 downto 0) := x"fa474ce2216d13d42cab9638c2541ab0";
    -- Packed UART payload vectors place the first digest byte in bits 7..0.
    constant wire_mapping : std_logic_vector(127 downto 0) := x"b01a54c23896ab2cd4136d21e24c47fa";
end;
package body Font_CRC is
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
