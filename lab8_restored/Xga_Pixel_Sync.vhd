library ieee;
use ieee.std_logic_1164.all;

entity Xga_Pixel_Sync is
    port (pixel_clk, system_reset, pll_locked : in std_logic;
          linked, font_ready, shown : in std_logic;
          pixel_reset, pixel_linked, pixel_font_ready, pixel_shown : out std_logic);
end entity;

architecture rtl of Xga_Pixel_Sync is
    signal reset_request : std_logic;
    signal reset_meta, reset_sync : std_logic := '1';
    signal status_meta, status_sync : std_logic_vector(2 downto 0) := (others => '0');
begin
    reset_request <= system_reset or not pll_locked;
    pixel_reset <= reset_sync;
    pixel_linked <= status_sync(2);
    pixel_font_ready <= status_sync(1);
    pixel_shown <= status_sync(0);

    process(pixel_clk, reset_request)
    begin
        if reset_request = '1' then
            reset_meta <= '1';
            reset_sync <= '1';
        elsif rising_edge(pixel_clk) then
            reset_meta <= '0';
            reset_sync <= reset_meta;
        end if;
    end process;

    process(pixel_clk)
    begin
        if rising_edge(pixel_clk) then
            status_meta <= linked & font_ready & shown;
            status_sync <= status_meta;
        end if;
    end process;
end architecture;
