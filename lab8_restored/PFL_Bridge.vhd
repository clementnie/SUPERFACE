library ieee;
use ieee.std_logic_1164.all;


-- Vendor IP maintenance bridge only. NOT included in the terminal LAB8 QSF.
-- Loading this SOF alone never requests an erase/program operation. Host-side
-- commands must remain identification/examine only until operator authorization.
entity PFL_Bridge is
    port (clock, reset_n : in std_logic;
          flash_data : inout std_logic_vector(7 downto 0);
          flash_addr : out std_logic_vector(21 downto 0);
          flash_ce_n, flash_oe_n, flash_we_n, flash_rst_n : out std_logic;
          sram_ce_n, sram_oe_n, sram_we_n : out std_logic);
end entity;
architecture rtl of PFL_Bridge is
    signal ce: std_logic_vector(0 downto 0);
begin
    sram_ce_n<='1'; sram_oe_n<='1'; sram_we_n<='1';
    flash_ce_n<=ce(0);
    loader: entity work.altparallel_flash_loader
        generic map (features_pgm=>1,features_cfg=>0,flash_type=>"CFI_FLASH",
            flash_data_width=>8,addr_width=>22,n_flash=>1,
            enhanced_flash_programming=>0,tristate_checkbox=>0)
        port map (pfl_clk=>clock,pfl_nreset=>reset_n,pfl_flash_access_granted=>'1',
            flash_data=>flash_data,flash_addr=>flash_addr,
            flash_nce=>ce,flash_noe=>flash_oe_n,flash_nwe=>flash_we_n,
            flash_nreset=>flash_rst_n);
end;
