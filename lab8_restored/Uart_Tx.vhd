library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity Uart_Tx is
    port (clk24, reset24, run24, fifo_empty : in std_logic;
          fifo_used : in std_logic_vector(4 downto 0);
          fifo_data : in std_logic_vector(8 downto 0);
          fifo_read, serial_tx, done_toggle, starved : out std_logic);
end entity;

architecture rtl of Uart_Tx is
    signal busy, last_byte, take_byte : std_logic := '0';
    signal line_out : std_logic := '1';
    signal complete, underrun : std_logic := '0';
    signal shift : std_logic_vector(7 downto 0);
    signal ticks : natural range 0 to 7 := 0;
    signal bit_number : natural range 0 to 9 := 0;
begin
    serial_tx <= line_out;
    done_toggle <= complete;
    starved <= underrun;
    take_byte <= '1' when run24 = '1' and underrun = '0' and fifo_empty = '0' and
        ((busy = '0' and unsigned(fifo_used) >= 8) or
         (busy = '1' and last_byte = '0' and bit_number = 9 and ticks = 7)) else '0';
    fifo_read <= take_byte;

    process(clk24)
    begin
        if rising_edge(clk24) then
            if reset24 = '1' then
                busy <= '0';
                line_out <= '1';
                complete <= '0';
                underrun <= '0';
            elsif take_byte = '1' then
                busy <= '1';
                ticks <= 0;
                bit_number <= 0;
                shift <= fifo_data(7 downto 0);
                last_byte <= fifo_data(8);
                line_out <= '0';
            elsif busy = '1' then
                if ticks = 7 then
                    ticks <= 0;
                    if bit_number = 9 then
                        busy <= '0';
                        if last_byte = '1' then complete <= not complete;
                        else underrun <= '1';
                        end if;
                    else
                        bit_number <= bit_number + 1;
                        if bit_number = 8 then line_out <= '1';
                        else
                            line_out <= shift(0);
                            shift <= '0' & shift(7 downto 1);
                        end if;
                    end if;
                else ticks <= ticks + 1;
                end if;
            end if;
        end if;
    end process;
end architecture;
