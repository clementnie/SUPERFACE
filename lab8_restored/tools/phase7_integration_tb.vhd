library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use std.env.all;
use work.Font_CRC.all;
entity phase7_integration_tb is
    generic (image_file: string := "font.hex"; fault: natural := 0);
end;
architecture bench of phase7_integration_tb is
    type image_t is array(0 to 215327) of std_logic_vector(7 downto 0);
    impure function image_load return image_t is
        file f: text open read_mode is image_file;
        variable l: line; variable a: image_t; variable v: std_logic_vector(7 downto 0);
    begin
        for i in a'range loop readline(f,l); hread(l,v); a(i):=v; end loop;
        return a;
    end;
    constant image: image_t := image_load;
    type memory_t is array(0 to 107631) of std_logic_vector(15 downto 0);
    signal clk, reset: std_logic := '0';
    signal fr, fd, fq, mq, mw, md, ready, owner: std_logic;
    signal fb, bd: std_logic_vector(7 downto 0);
    signal fa, ba: std_logic_vector(21 downto 0);
    signal ma, sa: std_logic_vector(17 downto 0);
    signal wd, rd, dq: std_logic_vector(15 downto 0);
    signal fc, fo, fw, fx, sc, so, sw, sl, su: std_logic;
    signal status: std_logic_vector(2 downto 0);
    signal count: std_logic_vector(14 downto 0);
    signal identity: std_logic_vector(127 downto 0);
    signal writes: natural:=0;
    signal rxv, txstart, txdone, linked, chinese: std_logic := '0';
    signal sid: std_logic_vector(63 downto 0) := x"0807060504030201";
    signal request_prefix: std_logic_vector(143 downto 0) := (others=>'0');
    signal tx_payload: std_logic_vector(199 downto 0);
    signal tx_kind,tx_length: std_logic_vector(7 downto 0);
    signal boot_rgb: std_logic_vector(11 downto 0);

begin
    clk<=not clk after 10 ns;
    flash_port: entity work.Parallel_Flash_Read port map(clk,reset,fq,fa,bd,ba,fc,fo,fw,fx,fr,fd,fb);
    loader: entity work.Font_Loader port map(clk,reset,fr,fd,md,fb,rd,fq,mq,mw,fa,ma,wd,ready,owner,status,count,identity);
    bus_owner: entity work.SRAM_Owner port map(clk,reset,owner,mq,mw,ma,(17 downto 0=>'0'),wd,
        '1','1','1','1','1',md,rd,sa,sc,so,sw,sl,su,dq);
    protocol: entity work.Uart_Session port map(clk=>clk, reset=>reset,
        font_ready=>ready, font_status=>status, font_count=>count, font_mapping=>identity,
        rx_valid=>rxv, rx_kind=>x"01", rx_length=>x"12", rx_session=>sid,
        rx_seq=>x"00000000",rx_prefix=>request_prefix,rx_crc=>x"1234",
        tx_ready=>'1', tx_done=>txdone, tx_start=>txstart,tx_kind=>tx_kind,tx_length=>tx_length,
        tx_session=>open,tx_seq=>open,tx_payload=>tx_payload,dispatch=>open,invalidate=>open,
        chinese=>chinese,linked=>linked,key_active=>open,key_idle=>open,
        display_complete=>'0',display_status=>"000",event_valid=>'0',event_reset=>'0',
        event_byte=>x"00",take_event=>open,reset_acked=>open);
    overlay: entity work.Boot_Presentation generic map(1000) port map(clk,reset,'1','1',linked,ready,'0',
        std_logic_vector(to_unsigned(0,10)),std_logic_vector(to_unsigned(108,10)),x"F00",boot_rgb);
    bd<=image(to_integer(unsigned(ba))) when unsigned(ba)<image'length and fc='0' and fo='0' else x"FF" after 150 ns;
    process(sc,so,sw,sa,dq)
        variable mem: memory_t := (others=>(others=>'U'));
        variable a: natural;
    begin
        a:=to_integer(unsigned(sa));
        if rising_edge(sw) and sc='0' then
            assert a<107632 report "SRAM write out of bounds" severity failure;
            assert sl='0' and su='0' and so='1' report "SRAM ownership violation" severity failure;
            mem(a):=dq; writes<=writes+1;
        end if;
        if sc='0' and so='0' and sw='1' and a<107632 then
            if fault=1 and a=100 then dq<=mem(a) xor x"0001" after 30 ns;
            else dq<=mem(a) after 30 ns; end if;
        else dq<=(others=>'Z') after 10 ns; end if;
    end process;
    process(clk) begin if rising_edge(clk) then
        assert fw='1' report "Runtime design must never write Flash" severity failure;
        assert not (owner='1' and ready='0') severity failure;
    end if; end process;
    process
        procedure hello(wanted: std_logic_vector(143 downto 0); expected: natural) is
        begin
            wait until falling_edge(clk); request_prefix<=wanted; rxv<='1';
            wait until falling_edge(clk); rxv<='0';
            wait until rising_edge(clk) and txstart='1';
            assert tx_kind=x"02" and unsigned(tx_length)=25 and
                unsigned(tx_payload(7 downto 0))=expected report "HELLO result" severity failure;
            assert tx_payload(199 downto 72)=wire_mapping and unsigned(tx_payload(71 downto 56))=6727
                report "Actual wire-byte mapping identity/count" severity failure;
            assert boot_rgb=x"0A0" report "Boot must remain independent of ACK handling" severity failure;
            wait until falling_edge(clk); txdone<='1';
            wait until falling_edge(clk); txdone<='0'; wait for 100 ns;
        end;
        variable c: unsigned(31 downto 0):=(others=>'1');
        constant check: string:="123456789";
    begin
        for i in check'range loop c:=crc_byte(c,std_logic_vector(to_unsigned(character'pos(check(i)),8))); end loop;
        assert (not c)=x"CBF43926" report "CRC known answer" severity failure;
        reset<='1'; wait for 100 ns; reset<='0';
        wait until ready='1'; wait for 40 ns;
        if fault=0 then
            assert status="000" and owner='1' and unsigned(count)=6727 and identity=wire_mapping severity failure;
            assert writes=107632 report "Exact word count" severity failure;
        elsif fault=1 then
            assert status="011" and owner='0' and unsigned(count)=0 and unsigned(identity)=0 severity failure;
        else
            if fault=2 then assert status="001" severity failure;
            elsif fault=3 then assert status="011" severity failure;
            elsif fault=4 then assert status="010" severity failure; end if;
            assert owner='0' and unsigned(count)=0 and status/="000" severity failure;
        end if;
        -- Literal payload in wire order: 47 1A 55 2F A5 CC A7 73 02 D2 B9 22 D5 0A E4 44 F2 DB.
        hello(x"DBF244E40AD522B9D20273A7CCA52F551A47",1);
        assert chinese='1' and linked='1' severity failure;
        sid<=x"0807060504030202";
        hello(x"DBF244E40AD522B9D20273A7CCA52E551A47",2);
        assert linked='0' severity failure;
        sid<=x"0807060504030203";
        hello((143 downto 0=>'0'),0);
        assert chinese='0' and linked='1' and owner='1' severity failure;
        assert writes=107632 report "Reconnect must not reload font" severity failure;
        report "PASS complete physical-bus font loader -> real UART session identity, mismatch/ASCII fallback, overlay concurrency, no reload";
        finish;
    end process;
    process begin wait for 1100 ms; assert false report "watchdog" severity failure; end process;
end;
