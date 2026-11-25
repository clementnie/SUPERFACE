library ieee;
use ieee.std_logic_1164.all;

entity Uart_Rx is
    port (clk24, reset24, run24, serial_rx, fifo_full : in std_logic;
          fifo_data : out std_logic_vector(8 downto 0);
          fifo_write, overflow : out std_logic);
end entity;

architecture rtl of Uart_Rx is
    type rx_state is (seek_high, armed, start_bit, data_bits, stop_bit);
    signal state : rx_state := seek_high;
    signal rx_meta, rx_sync : std_logic := '1';
    signal ticks : natural range 0 to 7 := 0;
    signal bit_number : natural range 0 to 7 := 0;
    signal sample_byte : std_logic_vector(7 downto 0);
    signal overrun : std_logic := '0';
    signal send_token : std_logic;
begin
    overflow <= overrun;
    send_token <= '1' when run24 = '1' and state = stop_bit and ticks = 7
                  and overrun = '0' else '0';
    fifo_write <= send_token and not fifo_full;
    fifo_data <= '0' & sample_byte when rx_sync = '1' else '1' & x"00";

    process(clk24)
    begin
        if rising_edge(clk24) then
            rx_meta <= serial_rx;
            rx_sync <= rx_meta;
            if reset24 = '1' then
                state <= seek_high;
                overrun <= '0';
            elsif run24 = '1' then
                case state is
                    when seek_high =>
                        if rx_sync = '1' then state <= armed; end if;
                    when armed =>
                        if rx_sync = '0' then
                            ticks <= 0;
                            state <= start_bit;
                        end if;
                    when start_bit =>
                        if ticks = 3 then
                            ticks <= 0;
                            bit_number <= 0;
                            if rx_sync = '0' then state <= data_bits;
                            else state <= armed;
                            end if;
                        else ticks <= ticks + 1;
                        end if;
                    when data_bits =>
                        if ticks = 7 then
                            ticks <= 0;
                            sample_byte(bit_number) <= rx_sync;
                            if bit_number = 7 then state <= stop_bit;
                            else bit_number <= bit_number + 1;
                            end if;
                        else ticks <= ticks + 1;
                        end if;
                    when stop_bit =>
                        if ticks = 7 then
                            if fifo_full = '1' then overrun <= '1'; end if;
                            if rx_sync = '1' then state <= armed;
                            else state <= seek_high;
                            end if;
                        else ticks <= ticks + 1;
                        end if;
                end case;
            end if;
        end if;
    end process;
end architecture;
