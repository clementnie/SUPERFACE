library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Font_CRC.all;
-- Header/payload control; separate BDF-visible NOR port, SRAM owner and CRC
-- datapath. One-second startup watchdog is independent of external responses.
entity Font_Loader is
    port (clk, reset, flash_ready, flash_done, memory_done : in std_logic;
          flash_data : in std_logic_vector(7 downto 0);
          memory_data : in std_logic_vector(15 downto 0);
          flash_request, memory_request, memory_write : out std_logic;
          flash_address : out std_logic_vector(21 downto 0);
          memory_address : out std_logic_vector(17 downto 0);
          memory_wdata : out std_logic_vector(15 downto 0);
          font_ready, runtime_owner : out std_logic;
          font_status : out std_logic_vector(2 downto 0);
          font_count : out std_logic_vector(14 downto 0);
          font_mapping : out std_logic_vector(127 downto 0));
end entity;
architecture rtl of Font_Loader is
    type state_t is (header_request, header_wait, header_check, payload_request,
        payload_wait, write_request, write_wait, payload_check, read_request,
        read_wait, read_high, read_check, release_bus, finished);
    type bytes_t is array(0 to 63) of std_logic_vector(7 downto 0);
    signal h: bytes_t := (others=>(others=>'0'));
    signal state: state_t := header_request;
    signal hi: natural range 0 to 63 := 0;
    signal pos: natural range 0 to payload_bytes := 0;
    signal word_pos: natural range 0 to payload_bytes/2-1 := 0;
    signal crc: unsigned(31 downto 0) := (others=>'1');
    signal low_byte: std_logic_vector(7 downto 0) := x"00";
    signal word: std_logic_vector(15 downto 0) := x"0000";
    signal watchdog: natural range 0 to 49999999 := 0;
    signal status: std_logic_vector(2 downto 0) := "100";
    signal valid: std_logic := '0';
    function u32(a,b,c,d: std_logic_vector(7 downto 0)) return unsigned is
    begin return unsigned(std_logic_vector'(d & c & b & a)); end;
begin
    flash_request<='1' when (state=header_request or state=payload_request) and flash_ready='1' and reset='0' else '0';
    flash_address<=std_logic_vector(to_unsigned(hi,22)) when state=header_request or state=header_wait
                   else std_logic_vector(to_unsigned(64+pos,22));
    memory_request<='1' when (state=write_request or state=read_request) and reset='0' else '0';
    memory_write<='1' when state=write_request or state=write_wait else '0';
    memory_address<=std_logic_vector(to_unsigned(word_pos,18));
    memory_wdata<=word;
    font_ready<='1' when state=finished else '0';
    runtime_owner<=valid when state=finished and reset='0' else '0';
    font_status<=status;
    font_count<=std_logic_vector(to_unsigned(glyphs,15)) when valid='1' else (others=>'0');
    font_mapping<=wire_mapping when valid='1' else (others=>'0');
    process(clk)
        variable missing, incompatible, reserved_bad: boolean;
        variable map_header: std_logic_vector(127 downto 0);
        variable expected: unsigned(31 downto 0);
    begin
        if rising_edge(clk) then
            if reset='1' then
                state<=header_request; hi<=0; pos<=0; word_pos<=0;
                crc<=(others=>'1'); watchdog<=0; status<="100"; valid<='0';
            elsif state/=finished and watchdog=49999999 then
                state<=finished; status<="100"; valid<='0';
            else
                if state/=finished then watchdog<=watchdog+1; end if;
                case state is
                    when header_request => if flash_ready='1' then state<=header_wait; end if;
                    when header_wait => if flash_done='1' then
                        h(hi)<=flash_data;
                        if hi<60 then crc<=crc_byte(crc,flash_data); end if;
                        if hi=63 then state<=header_check;
                        else hi<=hi+1; state<=header_request; end if;
                    end if;
                    when header_check =>
                        missing:=true; reserved_bad:=false;
                        for i in 0 to 63 loop if h(i)/=x"FF" then missing:=false; end if; end loop;
                        for i in 40 to 59 loop if h(i)/=x"00" then reserved_bad:=true; end if; end loop;
                        for i in 0 to 15 loop map_header(127-i*8 downto 120-i*8):=h(20+i); end loop;
                        incompatible := (h(7)&h(6)&h(5)&h(4)&h(3)&h(2)&h(1)&h(0))/=x"0031544E4F464653" or
                            h(8)/=x"01" or h(9)/=x"00" or h(10)/=x"40" or h(11)/=x"00" or
                            unsigned(std_logic_vector'(h(13)&h(12)))/=glyphs or map_header/=mapping or
                            u32(h(16),h(17),h(18),h(19))/=payload_bytes;
                        if missing then status<="001"; state<=finished;
                        elsif (not crc)/=u32(h(60),h(61),h(62),h(63)) or reserved_bad or h(14)/=x"00" or h(15)/=x"00" then
                            status<="011"; state<=finished;
                        elsif incompatible then status<="010"; state<=finished;
                        else crc<=(others=>'1'); pos<=0; state<=payload_request; end if;
                    when payload_request => if flash_ready='1' then state<=payload_wait; end if;
                    when payload_wait => if flash_done='1' then
                        crc<=crc_byte(crc,flash_data); pos<=pos+1;
                        if pos mod 2=0 then low_byte<=flash_data; state<=payload_request;
                        else
                            word<=flash_data & low_byte; word_pos<=pos/2;
                            -- Wide slots contain twelve 12-bit rows and four zero words.
                            -- Single-cell slots contain sixteen 8-bit rows without row padding.
                            if (pos < wide_glyphs*32 and
                                (flash_data(7 downto 4)/="0000" or
                                 ((pos/2) mod 16>=12 and (flash_data/=x"00" or low_byte/=x"00")))) or
                               (pos >= wide_glyphs*32 and flash_data/=x"00") then
                                status<="011"; state<=finished;
                            else state<=write_request; end if;
                        end if;
                    end if;
                    when write_request => state<=write_wait;
                    when write_wait => if memory_done='1' then
                        if pos=payload_bytes then state<=payload_check; else state<=payload_request; end if;
                    end if;
                    when payload_check =>
                        if (not crc)/=u32(h(36),h(37),h(38),h(39)) then status<="011"; state<=finished;
                        else crc<=(others=>'1'); word_pos<=0; state<=read_request; end if;
                    when read_request => state<=read_wait;
                    when read_wait => if memory_done='1' then
                        word<=memory_data; crc<=crc_byte(crc,memory_data(7 downto 0)); state<=read_high;
                    end if;
                    when read_high =>
                        crc<=crc_byte(crc,word(15 downto 8));
                        if word_pos=payload_bytes/2-1 then state<=read_check;
                        else word_pos<=word_pos+1; state<=read_request; end if;
                    when read_check =>
                        if (not crc)/=u32(h(36),h(37),h(38),h(39)) then status<="011"; state<=finished;
                        else state<=release_bus; end if;
                    when release_bus => status<="000"; valid<='1'; state<=finished;
                    when finished => null;
                end case;
            end if;
        end if;
    end process;
end;
