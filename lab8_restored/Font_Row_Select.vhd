library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Font_CRC.all;

entity Font_Row_Select is
    port (glyph : in std_logic_vector(15 downto 0);
          local_y, wide_row : in std_logic_vector(3 downto 0);
          font_ok, need_wide, wide_pair : in std_logic;
          sram_bits : in std_logic_vector(7 downto 0);
          base_left, base_right : in std_logic_vector(7 downto 0);
          font_row : out std_logic_vector(3 downto 0);
          need_sram : out std_logic;
          left_mask, right_mask : out std_logic_vector(7 downto 0));
end entity;

architecture rtl of Font_Row_Select is
    type narrow_rows is array(0 to 15) of std_logic_vector(7 downto 0);
    constant narrow_missing : narrow_rows := (
        x"FF", x"81", x"99", x"A5", x"85", x"89", x"91", x"91",
        x"81", x"91", x"81", x"A5", x"99", x"99", x"A5", x"FF");
    type wide_rows is array(0 to 15) of std_logic_vector(15 downto 0);
    constant wide_missing : wide_rows := (
        x"FFFF", x"8001", x"87E1", x"8C31", x"8031", x"8061", x"80C1", x"80C1",
        x"8001", x"80C1", x"8001", x"8241", x"8181", x"8181", x"8241", x"FFFF");
    signal single_cell : boolean;
    signal y : natural range 0 to 15;
begin
    single_cell <= font_ok = '1' and unsigned(glyph) >= 16#8000# + wide_glyphs and
                   unsigned(glyph) < 16#8000# + glyphs;
    y <= to_integer(unsigned(local_y));
    need_sram <= '1' when single_cell else need_wide;
    font_row <= local_y when single_cell else wide_row;
    left_mask <= narrow_missing(y) when glyph = x"007F" else
                 wide_missing(y)(15 downto 8) when glyph = x"0080" and wide_pair = '1' else
                 sram_bits when single_cell else base_left;
    right_mask <= wide_missing(y)(7 downto 0) when glyph = x"0080" and wide_pair = '1' else
                  base_right;
end architecture;
