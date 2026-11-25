library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
entity phase6_ps2_tb is end;
architecture bench of phase6_ps2_tb is
    signal clk : std_logic := '0';
    signal reset, take_event, reset_acked : std_logic := '0';
    signal active, pc, pd : std_logic := '1';
    signal valid, error, idle, ev, er : std_logic;
    signal data, eb : std_logic_vector(7 downto 0);
    signal valids, errors : natural := 0;
begin
    clk <= not clk after 10 ns;
    dut: entity work.PS2_Receiver port map(clk, reset, pc, pd, valid, error, idle, data);
    fifo: entity work.Key_Queue port map(clk, reset, active, valid, error, idle, data,
                                         take_event, reset_acked, ev, er, eb);
    process(clk) begin
        if rising_edge(clk) then
            if valid='1' then valids<=valids+1; end if;
            if error='1' then errors<=errors+1; end if;
        end if;
    end process;
    process
        procedure bit_send(v: std_logic) is begin
            pd<=v; wait for 15 us; pc<='0'; wait for 30 us; pc<='1'; wait for 15 us;
        end;
        procedure frame(v: natural; bad_parity: boolean:=false; bad_stop: boolean:=false) is
            variable d: std_logic_vector(7 downto 0);
            variable p: std_logic := '1';
        begin
            d:=std_logic_vector(to_unsigned(v,8)); bit_send('0');
            for i in 0 to 7 loop bit_send(d(i)); p:=p xor d(i); end loop;
            if bad_parity then p:=not p; end if;
            bit_send(p);
            if bad_stop then bit_send('0'); else bit_send('1'); end if;
            pd<='1'; wait for 1 us;
        end;
        procedure pop(v: natural) is begin
            assert ev='1' and er='0' and unsigned(eb)=v report "FIFO byte/order" severity failure;
            wait until falling_edge(clk); take_event<='1'; wait until falling_edge(clk);
            take_event<='0'; wait for 100 ns;
        end;
        procedure recover is begin
            assert ev='1' and er='1' report "Missing stream reset" severity failure;
            take_event<='1'; wait for 100 ns; take_event<='0';
            wait for 100 ns; reset_acked<='1'; wait for 100 ns; reset_acked<='0';
            wait for 110 us;
            assert ev='0' report "Recovery FIFO not empty" severity failure;
        end;
        variable before: natural;
    begin
        reset<='1'; wait for 100 ns; reset<='0'; wait for 110 us;
        assert idle='1' severity failure;
        frame(16#1c#); frame(16#f0#); frame(16#1c#);
        assert valids=3 and errors=0 severity failure;
        -- Pop must assert for one clock, not two.
        pop(16#1c#); pop(16#f0#); pop(16#1c#);
        assert ev='0' severity failure;
        before:=valids; frame(16#55#,true); assert valids=before and errors=1 severity failure; recover;
        frame(16#aa#,false,true); assert valids=before and errors=2 severity failure; recover;
        bit_send('1'); wait for 100 ns; assert errors=3 severity failure; recover;
        bit_send('0'); bit_send('1'); wait for 2100 us;
        assert errors=4 and valids=before severity failure; recover;
        frame(16#75#); pop(16#75#);
        bit_send('0'); bit_send('1'); reset<='1'; wait for 100 ns;
        pc<='1'; pd<='1'; reset<='0'; wait for 110 us;
        assert ev='0' and idle='1' severity failure;
        -- No draining: fill exact capacity, then overflow flushes every byte.
        for i in 0 to 31 loop frame(i); end loop;
        assert ev='1' and er='0' and eb=x"00" severity failure;
        frame(32); recover;
        frame(16#e0#); active<='0'; wait for 100 ns;
        assert ev='0' severity failure;
        active<='1'; wait for 110 us; frame(16#f0#); pop(16#f0#);
        report "PASS PS2 framing, parity, stop, timeout, reset, 32-byte FIFO, overflow, session loss";
        finish;
    end process;
    process begin wait for 40 ms; assert false report "watchdog" severity failure; end process;
end;
