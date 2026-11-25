-- Quartus IP collateral wrapper for the Cyclone II DCFIFO megafunction.
library ieee;
use ieee.std_logic_1164.all;
library altera_mf;
use altera_mf.altera_mf_components.all;

entity Uart_Fifo is
    port (aclr, wrclk, rdclk, wrreq, rdreq : in std_logic;
          data : in std_logic_vector(8 downto 0);
          q : out std_logic_vector(8 downto 0);
          wrfull, rdempty : out std_logic;
          rdusedw : out std_logic_vector(4 downto 0));
end entity;

architecture ip of Uart_Fifo is
begin
    storage : dcfifo
        generic map (
            intended_device_family => "Cyclone II",
            lpm_type => "dcfifo", lpm_numwords => 16, lpm_width => 9,
            lpm_widthu => 5, add_usedw_msb_bit => "ON", lpm_showahead => "ON",
            overflow_checking => "ON", underflow_checking => "ON",
            rdsync_delaypipe => 4, wrsync_delaypipe => 4,
            read_aclr_synch => "ON", write_aclr_synch => "ON", use_eab => "ON")
        port map (aclr => aclr, wrclk => wrclk, rdclk => rdclk,
                  wrreq => wrreq, rdreq => rdreq, data => data, q => q,
                  wrfull => wrfull, rdempty => rdempty, rdusedw => rdusedw);
end architecture;
