library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
entity flash_backup_tb is end;
architecture bench of flash_backup_tb is
    signal clk: std_logic:='0'; signal reset: std_logic:='1';
    signal empty: std_logic:='1'; signal full: std_logic:='0';
    signal pop,push,fq,fr,fd: std_logic;
    signal token: std_logic_vector(8 downto 0);
    signal fa,ba: std_logic_vector(21 downto 0);
    signal fb,bd: std_logic_vector(7 downto 0);
    signal ce,oe,we,rst: std_logic;
    signal seen: natural:=0;
    constant header: std_logic_vector(95 downto 0):=x"000000400A0D314B41424653";
    constant checksum: std_logic_vector(31 downto 0):=x"060B0BB3";
begin
    clk<=not clk after 10 ns;
    dut: entity work.Flash_Backup_Stream generic map(64) port map(clk,reset,'1',empty,full,'0',fr,fd,
        '0' & x"42",fb,pop,push,fq,token,fa,open,open,open,open);
    flash_port: entity work.Parallel_Flash_Read port map(clk,reset,fq,fa,bd,ba,ce,oe,we,rst,fr,fd,fb);
    bd<=std_logic_vector(to_unsigned((to_integer(unsigned(ba))*13+7) mod 256,8)) after 150 ns;
    process
    begin
        wait for 100 ns; reset<='0'; wait for 210 us;
        empty<='0'; wait for 20 ns; empty<='1'; wait;
    end process;
    process(clk)
        variable cycles: natural:=0;
    begin
        if rising_edge(clk) then
            cycles:=cycles+1;
            if cycles mod 7<3 then full<='1'; else full<='0'; end if;
            assert we='1' severity failure;
            if push='1' then
                if seen<12 then assert token(7 downto 0)=header(seen*8+7 downto seen*8) report "header" severity failure;
                elsif seen<76 then assert unsigned(token(7 downto 0))=((seen-12)*13+7) mod 256 report "data" severity failure;
                else assert token(7 downto 0)=checksum((seen-76)*8+7 downto (seen-76)*8) report "crc" severity failure; end if;
                if seen=79 then
                    assert token(8)='1' severity failure;
                    report "PASS read-only Flash backup stream, byte order, CRC, backpressure, final stop tag"; finish;
                else assert token(8)='0' severity failure; end if;
                seen<=seen+1;
            end if;
        end if;
    end process;
    process begin wait for 1 ms; assert false report "watchdog" severity failure; end process;
end;
