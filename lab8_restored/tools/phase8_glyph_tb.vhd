library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.Font_CRC.all;

entity phase8_glyph_tb is
end entity;

architecture bench of phase8_glyph_tb is
    signal glyph, neighbor : std_logic_vector(15 downto 0);
    signal local_y, font_row : std_logic_vector(3 downto 0);
    signal enabled, wide, chinese, orphan, read_sram : std_logic;
    signal ascii : std_logic_vector(6 downto 0);
    signal mask_left, mask_right : std_logic_vector(7 downto 0);
begin
    classify: entity work.Cell_Classify
        port map(x"72" & glyph, x"72" & neighbor, "0000000", enabled,
            std_logic_vector(to_unsigned(glyphs, 15)), ascii, wide, chinese, orphan);
    masks: entity work.Font_Row_Select
        port map(glyph, local_y, "0101", enabled, chinese, wide, x"A5",
            x"21", x"12", font_row, read_sram, mask_left, mask_right);

    process
    begin
        local_y <= "1111";
        enabled <= '0';
        glyph <= x"003F";
        neighbor <= x"0020";
        wait for 1 ns;
        assert ascii = "0111111" and read_sram = '0' and mask_left = x"21" severity failure;
        glyph <= x"007F";
        wait for 1 ns;
        assert read_sram = '0' and wide = '0' and mask_left = x"FF" severity failure;
        glyph <= x"0080";
        neighbor <= x"FFFF";
        wait for 1 ns;
        assert wide = '1' and read_sram = '0' and mask_left = x"FF" and mask_right = x"FF" severity failure;
        neighbor <= x"0020";
        wait for 1 ns;
        assert wide = '0' and mask_left = x"21" severity failure;
        enabled <= '1';
        glyph <= std_logic_vector(to_unsigned(16#8000# + wide_glyphs, 16));
        wait for 1 ns;
        assert wide = '0' and read_sram = '1' and font_row = "1111" and mask_left = x"A5" severity failure;
        glyph <= std_logic_vector(to_unsigned(16#8000# + glyphs, 16));
        wait for 1 ns;
        assert read_sram = '0' severity failure;
        glyph <= std_logic_vector(to_unsigned(16#8000# + wide_glyphs - 1, 16));
        neighbor <= x"FFFF";
        wait for 1 ns;
        assert wide = '1' and read_sram = '1' and font_row = "0101" severity failure;
        if narrow_end < glyphs then
            glyph <= std_logic_vector(to_unsigned(16#8000# + narrow_end - 1, 16));
            wait for 1 ns;
            assert wide = '0' and read_sram = '1' and font_row = "1111" severity failure;
            glyph <= std_logic_vector(to_unsigned(16#8000# + narrow_end, 16));
            wait for 1 ns;
            assert wide = '1' and read_sram = '1' and font_row = "0101" severity failure;
            glyph <= std_logic_vector(to_unsigned(16#8000# + glyphs - 1, 16));
            wait for 1 ns;
            assert wide = '1' and read_sram = '1' and font_row = "0101" severity failure;
            neighbor <= x"0020";
            wait for 1 ns;
            assert wide = '0' and read_sram = '0' severity failure;
        end if;
        report "PASS SRAM width boundaries and last glyph, ASCII question mark and both internal placeholders";
        finish;
    end process;
end architecture;
