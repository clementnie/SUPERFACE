library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Separate bench image. Use the same PHY and FIFOs as LAB8.
entity Uart_Wire_Test is
    generic (sample_count : positive := 18300000);
    port (clk, reset, run, rx_empty, tx_full, frame_done : in std_logic;
          rx_token : in std_logic_vector(8 downto 0);
          rx_pop, tx_push, framing_error : out std_logic;
          tx_token : out std_logic_vector(8 downto 0));
end entity;

architecture rtl of Uart_Wire_Test is
    subtype octet is std_logic_vector(7 downto 0);
    subtype word32 is std_logic_vector(31 downto 0);
    type test_state is (wait_start, wait_confirm, streaming, trailer, finished);
    signal state : test_state := wait_start;
    signal tx_count, rx_count : natural range 0 to sample_count := 0;
    signal tx_crc, rx_crc : word32 := (others => '1');
    signal frame_errors : unsigned(31 downto 0) := (others => '0');
    signal trailer_byte : natural range 0 to 19 := 0;
    signal tx_drained, put, pop : std_logic := '0';
    signal tx_data, rx_data : octet;
    signal tx_last : std_logic;

    function pattern(index : natural) return octet is
        variable offset : unsigned(23 downto 0) := to_unsigned(index mod 16777216, 24);
    begin
        return x"A5" xor std_logic_vector(offset(23 downto 16) xor
               offset(15 downto 8) xor offset(7 downto 0));
    end function;

    function crc32_byte(crc : word32; data : octet) return word32 is
        variable remainder : word32 := crc xor (x"000000" & data);
    begin
        for bit_number in 0 to 7 loop
            if remainder(0) = '1' then
                remainder := ('0' & remainder(31 downto 1)) xor x"EDB88320";
            else
                remainder := '0' & remainder(31 downto 1);
            end if;
        end loop;
        return remainder;
    end function;

    function word_byte(value : word32; index : natural) return octet is
    begin
        case index is
            when 0 => return value(7 downto 0);
            when 1 => return value(15 downto 8);
            when 2 => return value(23 downto 16);
            when others => return value(31 downto 24);
        end case;
    end function;
begin
    assert sample_count >= 16 and sample_count < 16777216*2 severity failure;
    pop <= run and not rx_empty;
    rx_pop <= pop;
    framing_error <= pop and rx_token(8);
    rx_data <= x"00" when rx_token(8) = '1' else rx_token(7 downto 0);

    put <= '1' when run = '1' and tx_full = '0' and
        ((state = streaming and tx_count < sample_count) or state = trailer) else '0';
    tx_push <= put;
    tx_last <= '1' when (state = streaming and tx_count = sample_count-1)
                       or (state = trailer and trailer_byte = 19) else '0';
    tx_token <= tx_last & tx_data;

    process(state, trailer_byte, rx_count, rx_crc, tx_count, tx_crc, frame_errors)
    begin
        if state = trailer then
            case trailer_byte is
                when 0 => tx_data <= x"53"; -- SF5R
                when 1 => tx_data <= x"46";
                when 2 => tx_data <= x"35";
                when 3 => tx_data <= x"52";
                when 4 to 7 => tx_data <= word_byte(std_logic_vector(to_unsigned(rx_count,32)), trailer_byte-4);
                when 8 to 11 => tx_data <= word_byte(not rx_crc, trailer_byte-8);
                when 12 to 15 => tx_data <= word_byte(not tx_crc, trailer_byte-12);
                when 16 to 19 => tx_data <= word_byte(std_logic_vector(frame_errors), trailer_byte-16);
            end case;
        else
            tx_data <= pattern(tx_count);
        end if;
    end process;

    process(clk)
    begin
        if rising_edge(clk) then
            if reset = '1' then
                state <= wait_start;
                tx_count <= 0;
                rx_count <= 0;
                rx_crc <= (others => '1');
                tx_crc <= (others => '1');
                frame_errors <= (others => '0');
                tx_drained <= '0';
                trailer_byte <= 0;
            else
                case state is
                    when wait_start =>
                        if pop = '1' and rx_token = '0' & x"53" then state <= wait_confirm; end if;
                    when wait_confirm =>
                        if pop = '1' then
                            if rx_token = '0' & x"46" then state <= streaming;
                            else state <= wait_start;
                            end if;
                        end if;
                    when streaming =>
                        if pop = '1' and rx_count < sample_count then
                            rx_count <= rx_count + 1;
                            rx_crc <= crc32_byte(rx_crc, rx_data);
                            if rx_token(8) = '1' then frame_errors <= frame_errors + 1; end if;
                        end if;
                        if put = '1' then
                            tx_count <= tx_count + 1;
                            tx_crc <= crc32_byte(tx_crc, tx_data);
                        end if;
                        if frame_done = '1' then tx_drained <= '1'; end if;
                        if tx_drained = '1' and rx_count = sample_count then state <= trailer; end if;
                    when trailer =>
                        if put = '1' then
                            if trailer_byte = 19 then state <= finished;
                            else trailer_byte <= trailer_byte + 1;
                            end if;
                        end if;
                    when finished => null;
                end case;
            end if;
        end if;
    end process;
end architecture;
