library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Synchronous simple dual-port RAM, inferred into two Cyclone II M4Ks.
-- Pixel reads may address an unpublished slot during blanking. Valid gating
-- discards those reads. An in-use slot is never written.
entity Xga_Line_RAM is
    port (clk, pixel_clk, wr_en : in std_logic;
          wr_addr : in std_logic_vector(8 downto 0);
          wr_data : in std_logic_vector(15 downto 0);
          rd_slot : in std_logic_vector(1 downto 0);
          rd_col : in std_logic_vector(6 downto 0);
          pixel_word : out std_logic_vector(15 downto 0));
end entity;

architecture rtl of Xga_Line_RAM is
    type memory is array (0 to 511) of std_logic_vector(15 downto 0);
    signal words : memory;
    attribute ramstyle : string;
    attribute ramstyle of words : signal is "M4K, no_rw_check";
begin
    process(clk)
    begin
        if rising_edge(clk) then
            if wr_en = '1' then words(to_integer(unsigned(wr_addr))) <= wr_data; end if;
        end if;
    end process;

    process(pixel_clk)
    begin
        if rising_edge(pixel_clk) then
            pixel_word <= words(to_integer(unsigned(rd_slot) & unsigned(rd_col)));
        end if;
    end process;
end architecture;
