library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Wire_V1.all;

entity phase5_session_tb is
    generic (check_expiry : boolean := false);
end entity;

architecture bench of phase5_session_tb is
    signal clk, reset, rx_valid, tx_done, display_complete, event_valid : std_logic := '0';
    signal tx_start, dispatch, invalidate, linked, key_active, key_idle, take_event, reset_acked : std_logic;
    constant candidate : std_logic_vector(63 downto 0) := x"0807060504030201";
    signal rx_kind, rx_length, tx_kind, tx_length : octet := x"00";
    signal rx_prefix : std_logic_vector(143 downto 0) := (others => '0');
    signal rx_seq, tx_seq : std_logic_vector(31 downto 0) := (others => '0');
    signal tx_session : std_logic_vector(63 downto 0);
    signal tx_payload : std_logic_vector(199 downto 0);
    signal event_byte : octet := x"1C";
begin
    clk <= not clk after 10 ns;
    dut : entity work.Uart_Session
        port map (
            clk => clk, reset => reset, font_ready => '1', font_status => "010",
            font_count => (others => '0'), font_mapping => (others => '0'),
            rx_valid => rx_valid, rx_kind => rx_kind, rx_length => rx_length,
            rx_session => candidate, rx_seq => rx_seq, rx_prefix => rx_prefix, rx_crc => x"A5A5",
            tx_ready => '1', tx_done => tx_done, tx_start => tx_start, tx_kind => tx_kind,
            tx_length => tx_length, tx_session => tx_session, tx_seq => tx_seq, tx_payload => tx_payload,
            dispatch => dispatch, invalidate => invalidate, chinese => open, linked => linked,
            key_active => key_active, key_idle => key_idle, display_complete => display_complete,
            display_status => "000", event_valid => event_valid, event_reset => '0',
            event_byte => event_byte, take_event => take_event, reset_acked => reset_acked);

    process
        procedure inject(kind : octet; seq, size : natural; prefix : natural := 0) is
        begin
            wait until falling_edge(clk);
            rx_valid <= '1';
            rx_kind <= kind;
            rx_seq <= std_logic_vector(to_unsigned(seq, 32));
            rx_length <= std_logic_vector(to_unsigned(size, 8));
            rx_prefix <= std_logic_vector(to_unsigned(prefix, 144));
            wait until falling_edge(clk);
            rx_valid <= '0';
        end procedure;

        procedure expect(kind : octet; seq, size, prefix : natural) is
        begin
            wait until rising_edge(clk) and tx_start = '1';
            assert tx_kind = kind and tx_length = std_logic_vector(to_unsigned(size, 8)) and
                   tx_seq = std_logic_vector(to_unsigned(seq, 32)) and tx_session = candidate and
                   tx_payload(15 downto 0) = std_logic_vector(to_unsigned(prefix, 16))
                report "Unexpected TX descriptor" severity failure;
        end procedure;

        procedure drain(variable stamp : out time) is
        begin
            wait until falling_edge(clk);
            tx_done <= '1';
            wait until rising_edge(clk);
            stamp := now;
            wait until falling_edge(clk);
            tx_done <= '0';
        end procedure;

        variable last_stop, unused_stamp : time;
    begin
        reset <= '1';
        wait for 80 ns;
        reset <= '0';
        inject(hello_type, 0, 18);
        expect(offer_type, 0, 25, 16#0200#);
        drain(unused_stamp);
        assert linked = '1' and key_active = '0' severity failure;

        -- Supply the successful Phase 3 completion from the display interface.
        inject(end_type, 1, 3);
        assert dispatch = '1' severity failure;
        wait until falling_edge(clk);
        display_complete <= '1';
        wait until falling_edge(clk);
        display_complete <= '0';
        expect(ack_type, 1, 2, 16#0012#);
        drain(unused_stamp);
        assert key_active = '1' severity failure;

        event_valid <= '1';
        expect(key_type, 1, 2, 16#1C00#);
        assert take_event = '1' severity failure;
        event_valid <= '0';
        drain(last_stop);

        inject(ping_type, 2, 0);
        expect(ack_type, 2, 2, 16#0015#);
        drain(unused_stamp);
        assert key_idle = '0' severity failure;

        for retry in 1 to 3 loop
            expect(key_type, 1, 2, 16#1C00#);
            assert now - last_stop = 100 ms + 20 ns
                report "Key retry did not start 100 ms after the previous stop" severity failure;
            drain(last_stop);
        end loop;

        wait until linked = '0';
        assert now - last_stop = 100 ms and invalidate = '1'
            report "Retry exhaustion must invalidate the session" severity failure;

        report "PASS exact key retry deadlines, crossed control ACK and retry exhaustion";
        if check_expiry then
            inject(hello_type, 0, 18);
            expect(offer_type, 0, 25, 16#0200#);
            drain(unused_stamp);
            wait until linked = '0';
            assert invalidate = '1' and key_active = '0' severity failure;
            report "PASS independent peer inactivity expiry";
        end if;
        std.env.finish;
    end process;

    process
    begin
        wait for 2500 ms;
        assert false report "Session test watchdog" severity failure;
    end process;
end architecture;
