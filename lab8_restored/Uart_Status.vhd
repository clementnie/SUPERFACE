library ieee;
use ieee.std_logic_1164.all;

entity Uart_Status is
    port (clk50, board_reset, reset50, run50, overflow, starved, done_toggle,
          frame_error : in std_logic;
          phy_fault, frame_done, overflow_seen, starvation_seen, framing_seen : out std_logic);
end entity;

architecture rtl of Uart_Status is
    signal done_meta, done_sync, done_seen : std_logic := '0';
    signal error_seen, overrun_seen, underrun_seen : std_logic := '0';
    signal overflow_meta, overflow_sync, starved_meta, starved_sync : std_logic := '0';
    attribute noprune : boolean;
    attribute noprune of error_seen, overrun_seen, underrun_seen : signal is true;
begin
    phy_fault <= overflow or starved;
    frame_done <= (done_sync xor done_seen) and run50;
    overflow_seen <= overrun_seen;
    starvation_seen <= underrun_seen;
    framing_seen <= error_seen;
    process(clk50)
    begin
        if rising_edge(clk50) then
            done_meta <= done_toggle;
            done_sync <= done_meta;
            done_seen <= done_sync;
            if reset50 = '1' then done_seen <= '0'; end if;
            overflow_meta <= overflow;
            overflow_sync <= overflow_meta;
            starved_meta <= starved;
            starved_sync <= starved_meta;
            if board_reset = '1' then
                error_seen <= '0';
                overrun_seen <= '0';
                underrun_seen <= '0';
            else
                if frame_error = '1' then error_seen <= '1'; end if;
                if overflow_sync = '1' then overrun_seen <= '1'; end if;
                if starved_sync = '1' then underrun_seen <= '1'; end if;
            end if;
        end if;
    end process;
end architecture;
