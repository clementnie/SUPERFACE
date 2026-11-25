library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Wire_V1.all;

entity Frame_Tx is
    port (clk, reset, run, fifo_full, frame_done : in std_logic;
          fifo_data : out std_logic_vector(8 downto 0);
          fifo_write, ready : out std_logic;
          start : in std_logic;
          kind, length : in std_logic_vector(7 downto 0);
          session_id : in std_logic_vector(63 downto 0);
          seq : in std_logic_vector(31 downto 0);
          payload : in std_logic_vector(199 downto 0));
end entity;

architecture rtl of Frame_Tx is
    type tx_state is (idle, opening, select_byte, emit, suffix, closing, draining);
    signal state : tx_state := idle;
    signal header : std_logic_vector(119 downto 0);
    signal body_data : std_logic_vector(199 downto 0);
    signal pos : natural range 0 to 41 := 0;
    signal end_pos : natural range 15 to 40;
    signal crc : crc_word;
    signal data_byte : octet;
    signal stuffed, put : std_logic;
begin
    ready <= '1' when state = idle and run = '1' else '0';
    stuffed <= '1' when data_byte = delim or data_byte = escape else '0';
    put <= run and not fifo_full;
    fifo_write <= put when state = opening or state = emit or state = suffix or state = closing else '0';
    fifo_data <= '1' & delim when state = closing else
                 '0' & delim when state = opening else
                 '0' & escape when state = emit and stuffed = '1' else
                 '0' & (data_byte xor x"20") when state = suffix else
                 '0' & data_byte;

    process(clk)
    begin
        if rising_edge(clk) then
            if reset = '1' then
                state <= idle;
            else
                case state is
                    when idle =>
                        if start = '1' and run = '1' then
                            header <= length & seq & session_id & kind & x"01";
                            body_data <= payload;
                            end_pos <= 15 + to_integer(unsigned(length));
                            pos <= 0;
                            crc <= x"FFFF";
                            state <= opening;
                        end if;
                    when opening =>
                        if put = '1' then state <= select_byte; end if;
                    when select_byte =>
                        if pos < 15 then
                            data_byte <= header(7 downto 0);
                            header <= x"00" & header(119 downto 8);
                        elsif pos < end_pos then
                            data_byte <= body_data(7 downto 0);
                            body_data <= x"00" & body_data(199 downto 8);
                        elsif pos = end_pos then data_byte <= crc(7 downto 0);
                        else data_byte <= crc(15 downto 8);
                        end if;
                        state <= emit;
                    when emit =>
                        if put = '1' and stuffed = '1' then state <= suffix;
                        elsif put = '1' then
                            if pos < end_pos then crc <= crc_byte(crc, data_byte); end if;
                            if pos = end_pos + 1 then state <= closing;
                            else pos <= pos + 1; state <= select_byte;
                            end if;
                        end if;
                    when suffix =>
                        if put = '1' then
                            if pos < end_pos then crc <= crc_byte(crc, data_byte); end if;
                            if pos = end_pos + 1 then state <= closing;
                            else pos <= pos + 1; state <= select_byte;
                            end if;
                        end if;
                    when closing =>
                        if put = '1' then state <= draining; end if;
                    when draining =>
                        if frame_done = '1' then state <= idle; end if;
                end case;
            end if;
        end if;
    end process;
end architecture;
