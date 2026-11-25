library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Receive-only physical Set 2 interface, 50 MHz. The existing Key_Queue owns
-- buffering, overflow recovery and reliable stream-reset notifications.
entity PS2_Receiver is
    port (clk, reset, ps2_clk, ps2_dat : in std_logic;
          source_valid, source_error, idle_qualified : out std_logic;
          source_byte : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of PS2_Receiver is
    signal clock_meta, clock_sync, clock_last : std_logic := '1';
    signal data_meta, data_sync : std_logic := '1';
    attribute altera_attribute : string;
    attribute altera_attribute of clock_meta, clock_sync, data_meta, data_sync : signal is
        "-name SYNCHRONIZER_IDENTIFICATION FORCED";
    signal qualified : std_logic := '0';
    signal idle_ticks : natural range 0 to 5000 := 0;
    signal age : natural range 0 to 99999 := 0;
    signal bit_index : natural range 1 to 10 := 1;
    signal receiving, parity : std_logic := '0';
    signal data : std_logic_vector(7 downto 0) := (others => '0');
begin
    idle_qualified <= '1' when qualified = '1' and receiving = '0' and
                              clock_sync = '1' and data_sync = '1' else '0';
    process(clk)
    begin
        if rising_edge(clk) then
            clock_meta <= ps2_clk; clock_sync <= clock_meta; clock_last <= clock_sync;
            data_meta <= ps2_dat; data_sync <= data_meta;
            source_valid <= '0'; source_error <= '0';
            if reset = '1' then
                clock_meta <= '1'; clock_sync <= '1'; clock_last <= '1';
                data_meta <= '1'; data_sync <= '1';
                qualified <= '0'; idle_ticks <= 0; receiving <= '0';
                bit_index <= 1; age <= 0; parity <= '0'; source_byte <= (others => '0');
            else
                if receiving = '0' and clock_sync = '1' and data_sync = '1' then
                    if idle_ticks < 5000 then idle_ticks <= idle_ticks + 1;
                    else qualified <= '1'; end if;
                else idle_ticks <= 0;
                end if;
                if receiving = '1' and age = 99999 then
                    receiving <= '0'; qualified <= '0'; idle_ticks <= 0;
                    source_error <= '1'; age <= 0;
                elsif clock_last = '1' and clock_sync = '0' then
                    if receiving = '0' then
                        if qualified = '1' then
                            if data_sync = '0' then
                                receiving <= '1'; bit_index <= 1; parity <= '0'; age <= 0;
                            else
                                source_error <= '1'; qualified <= '0'; idle_ticks <= 0;
                            end if;
                        end if;
                    else
                        age <= 0;
                        case bit_index is
                            when 1 to 8 =>
                                data(bit_index-1) <= data_sync;
                                parity <= parity xor data_sync;
                                bit_index <= bit_index + 1;
                            when 9 =>
                                parity <= parity xor data_sync; bit_index <= 10;
                            when others =>
                                receiving <= '0';
                                if parity = '1' and data_sync = '1' then
                                    source_byte <= data; source_valid <= '1';
                                else
                                    source_error <= '1'; qualified <= '0'; idle_ticks <= 0;
                                end if;
                        end case;
                    end if;
                elsif receiving = '1' then age <= age + 1;
                end if;
            end if;
        end if;
    end process;
end architecture;
