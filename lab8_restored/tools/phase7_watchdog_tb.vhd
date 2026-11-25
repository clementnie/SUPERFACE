library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
entity phase7_watchdog_tb is end;
architecture bench of phase7_watchdog_tb is
    signal clk: std_logic:='0'; signal reset: std_logic:='1';
    signal ready,owner,fr,mr,mw: std_logic;
    signal status: std_logic_vector(2 downto 0);
    signal count: std_logic_vector(14 downto 0);
    signal mapping: std_logic_vector(127 downto 0);
begin
    clk<=not clk after 10 ns;
    dut: entity work.Font_Loader port map(clk,reset,'0','0','0',x"00",x"0000",
        fr,mr,mw,open,open,open,ready,owner,status,count,mapping);
    process begin
        wait for 100 ns; reset<='0';
        wait for 999999960 ns;
        assert ready='0' and owner='0' and mr='0' severity failure;
        wait until ready='1';
        assert now=1000000090 ns report "One-second production watchdog deadline" severity failure;
        assert status="100" and owner='0' and unsigned(count)=0 and unsigned(mapping)=0 and mr='0' severity failure;
        reset<='1'; wait for 40 ns;
        assert ready='0' and owner='0' and mr='0' report "Reset clears validation" severity failure;
        report "PASS production 50000000-cycle startup watchdog, safe ASCII fallback, reset";
        finish;
    end process;
    process begin wait for 1001 ms; assert false report "watchdog test stalled" severity failure; end process;
end;
