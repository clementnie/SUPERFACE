library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Wire_V1.all;

entity phase5_frame_rx_tb is end entity;

architecture bench of phase5_frame_rx_tb is
    constant hello : std_logic_vector(295 downto 0) :=
        x"7E010101020304050607080000000012000000000000000000000000000000000000650D7E";
    signal clk, reset, pop, valid : std_logic := '0';
    signal empty : std_logic := '1';
    signal token : std_logic_vector(8 downto 0) := (others => '0');
    signal kind, length : octet;
    signal session_id : std_logic_vector(63 downto 0);
    signal seq : std_logic_vector(31 downto 0);
    signal request_crc : crc_word;
    signal frames : natural := 0;
begin
    clk <= not clk after 10 ns;
    parser : entity work.Frame_Rx
        port map (clk => clk, reset => reset, run => '1', fifo_empty => empty,
                  fifo_data => token, fifo_read => pop, framing_error => open,
                  payload_busy => '0', payload_read => '0', payload_address => x"00",
                  payload_data => open, valid => valid, kind => kind, length => length,
                  session_id => session_id, seq => seq, prefix => open, request_crc => request_crc);

    process(clk)
    begin
        if rising_edge(clk) and valid = '1' then
            assert kind = hello_type and length = x"12" and request_crc = x"0D65"
                   and seq = x"00000000" and session_id = x"0807060504030201"
                report "Wrong decoded HELLO" severity failure;
            frames <= frames + 1;
        end if;
    end process;

    process
        procedure send(first, last : natural) is
        begin
            for index in first to last loop
                wait until falling_edge(clk);
                token <= '0' & hello(295 - 8*index downto 288 - 8*index);
                empty <= '0';
                wait until rising_edge(clk) and pop = '1';
                empty <= '1';
            end loop;
        end procedure;
    begin
        reset <= '1';
        wait for 40 ns;
        reset <= '0';
        send(0, 2);
        wait for 100 ms + 40 ns;
        send(3, 36);
        wait for 40 ns;
        assert frames = 0 report "Expired partial packet was dispatched" severity failure;
        send(0, 36);
        wait for 40 ns;
        assert frames = 1 report "Parser lost the first valid packet after timeout" severity failure;
        report "PASS 100 ms incomplete-frame timeout and delimiter recovery";
        std.env.finish;
    end process;

    process
    begin
        wait for 101 ms;
        assert false report "Parser test watchdog" severity failure;
    end process;
end architecture;
