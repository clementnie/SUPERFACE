library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity phase5_wire_test_tb is end entity;

architecture bench of phase5_wire_test_tb is
    constant count : positive := 64;
    constant valid_trailer : std_logic_vector(159 downto 0) :=
        x"5346355240000000F315296B7FF1C51100000000";
    constant error_trailer : std_logic_vector(159 downto 0) :=
        x"5346355240000000252B51237FF1C51101000000";
    signal clk, reset, tx_push, rx_pop, frame_done, tx_full, error_case : std_logic := '0';
    signal rx_empty : std_logic := '1';
    signal rx_token, tx_token : std_logic_vector(8 downto 0) := (others => '0');
    signal tx_index : natural := 0;
begin
    clk <= not clk after 10 ns;
    test : entity work.Uart_Wire_Test
        generic map (sample_count => count)
        port map (clk => clk, reset => reset, run => '1', rx_empty => rx_empty,
                  tx_full => tx_full, frame_done => frame_done, rx_token => rx_token,
                  rx_pop => rx_pop, tx_push => tx_push, framing_error => open, tx_token => tx_token);

    process (clk)
        variable index : natural;
        variable expected : std_logic_vector(159 downto 0);
    begin
        if rising_edge(clk) then
            frame_done <= '0';
            if reset = '1' then
                tx_index <= 0;
            elsif tx_push = '1' then
                assert tx_full = '0' severity failure;
                if tx_index < count then
                    assert tx_token(7 downto 0) =
                        (std_logic_vector(to_unsigned(tx_index, 8)) xor x"A5") severity failure;
                    assert (tx_token(8) = '1') = (tx_index = count-1) severity failure;
                else
                    index := tx_index - count;
                    if error_case = '1' then expected := error_trailer; else expected := valid_trailer; end if;
                    assert tx_token(7 downto 0) = expected(159-8*index downto 152-8*index)
                        report "FPGA trailer mismatch" severity failure;
                    assert (tx_token(8) = '1') = (index = 19) severity failure;
                end if;
                if tx_token(8) = '1' then frame_done <= '1'; end if;
                tx_index <= tx_index + 1;
            end if;
        end if;
    end process;

    process
        procedure send_token(value : std_logic_vector(8 downto 0)) is
        begin
            wait until falling_edge(clk);
            rx_empty <= '0';
            rx_token <= value;
            wait until rising_edge(clk) and rx_pop = '1';
            rx_empty <= '1';
        end procedure;
    begin
        for round_number in 0 to 1 loop
            reset <= '1';
            tx_full <= '1';
            if round_number = 1 then error_case <= '1'; end if;
            wait for 40 ns;
            reset <= '0';
            send_token('0' & x"53");
            send_token('0' & x"46");
            for i in 0 to count-1 loop
                if i = 8 then tx_full <= '0'; end if;
                if i = 15 and round_number = 1 then
                    send_token('1' & x"00");
                else
                    send_token('0' & (std_logic_vector(to_unsigned(i, 8)) xor x"5A"));
                end if;
            end loop;
            wait until tx_index = count + 20;
            wait until falling_edge(clk);
        end loop;
        report "PASS independent wire-test streams, CRC report and framing marker";
        std.env.finish;
    end process;

    process
    begin
        wait for 1 ms;
        assert false report "Wire-rate test watchdog" severity failure;
    end process;
end architecture;
