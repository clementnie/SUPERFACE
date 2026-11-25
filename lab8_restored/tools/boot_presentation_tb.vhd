library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
entity boot_presentation_tb is end;
architecture bench of boot_presentation_tb is
    signal clk,reset,blank,linked,ready,shown: std_logic:='0';
    signal rgb: std_logic_vector(11 downto 0);
begin
    clk<=not clk after 10 ns;
    dut: entity work.Boot_Presentation generic map(100) port map(clk,reset,'1',blank,linked,ready,shown,
        std_logic_vector(to_unsigned(0,10)),std_logic_vector(to_unsigned(108,10)),x"F00",rgb);
    process
        procedure boundary is begin
            wait until falling_edge(clk); blank<='1';
            wait until falling_edge(clk); blank<='0'; wait for 1 ns;
        end;
    begin
        reset<='1'; wait for 100 ns; reset<='0'; wait for 100 ns;
        assert rgb=x"0A0" report "Boot visible before fonts" severity failure;
        ready<='1'; linked<='1'; shown<='1'; wait for 1 us; boundary;
        assert rgb=x"0A0" report "Handshake presentation held" severity failure;
        shown<='0'; wait for 2 us; boundary;
        assert rgb=x"0A0" report "Incomplete snapshot must stay hidden" severity failure;
        shown<='1'; wait for 100 ns;
        assert rgb=x"0A0" report "No mid-frame handover" severity failure;
        boundary; assert rgb=x"F00" report "Handover after timer and snapshot at blank" severity failure;
        linked<='0'; boundary; assert rgb=x"0A0" report "Disconnect recovery" severity failure;
        report "PASS startup hold, font independence, complete snapshot gating, vblank switch, disconnect";
        finish;
    end process;
end;
