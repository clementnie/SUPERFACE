library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Font_CRC.all;
-- NON-DESTRUCTIVE maintenance image. Receive ASCII B to read the complete
-- 4 MiB array. Raw UART response: SFBAK1\r\n, u32 length, data, CRC32 LE.
-- No Flash command writes, query commands, erase or programming exist here.
entity Flash_Backup_Stream is
    generic (dump_bytes: positive := 4194304);
    port (clk, reset, run, rx_empty, tx_full, frame_done, flash_ready, flash_done : in std_logic;
          rx_token : in std_logic_vector(8 downto 0);
          flash_data : in std_logic_vector(7 downto 0);
          rx_pop, tx_push, flash_request : out std_logic;
          tx_token : out std_logic_vector(8 downto 0);
          flash_address : out std_logic_vector(21 downto 0);
          sram_ce_n, sram_oe_n, sram_we_n, ground : out std_logic);
end entity;
architecture rtl of Flash_Backup_Stream is
    type state_t is (idle, prefix, request_byte, wait_byte, send_byte, checksum, drain);
    signal push: std_logic := '0';
    signal state: state_t := idle;
    signal idx: natural range 0 to 11 := 0;
    signal pos: natural range 0 to dump_bytes-1 := 0;
    signal crc: unsigned(31 downto 0) := (others=>'1');
    signal byte: std_logic_vector(7 downto 0) := x"00";
    constant magic: std_logic_vector(63 downto 0) := x"0A0D314B41424653";
    constant size: unsigned(31 downto 0) := to_unsigned(dump_bytes,32);
begin
    tx_push<=push; ground<='0';
    sram_ce_n<='1'; sram_oe_n<='1'; sram_we_n<='1';
    flash_address<=std_logic_vector(to_unsigned(pos,22));
    rx_pop<='1' when run='1' and rx_empty='0' else '0';
    flash_request<='1' when state=request_byte and flash_ready='1' and tx_full='0' and run='1' else '0';
    process(clk) begin
        if rising_edge(clk) then
            push<='0';
            if reset='1' or run='0' then state<=idle; pos<=0; idx<=0; crc<=(others=>'1');
            else case state is
                when idle => if rx_empty='0' and rx_token='0' & x"42" then
                    pos<=0; idx<=0; crc<=(others=>'1'); state<=prefix;
                end if;
                when prefix => if tx_full='0' and push='0' then
                    if idx<8 then tx_token<='0' & magic(idx*8+7 downto idx*8);
                    else tx_token<='0' & std_logic_vector(size((idx-8)*8+7 downto (idx-8)*8)); end if;
                    push<='1';
                    if idx=11 then state<=request_byte; else idx<=idx+1; end if;
                end if;
                when request_byte => if flash_ready='1' and tx_full='0' then state<=wait_byte; end if;
                when wait_byte => if flash_done='1' then byte<=flash_data; state<=send_byte; end if;
                when send_byte => if tx_full='0' and push='0' then
                    tx_token<='0' & byte; push<='1'; crc<=crc_byte(crc,byte);
                    if pos=dump_bytes-1 then idx<=0; state<=checksum;
                    else pos<=pos+1; state<=request_byte; end if;
                end if;
                when checksum => if tx_full='0' and push='0' then
                    push<='1';
                    if idx=3 then tx_token<='1' & std_logic_vector(not crc(idx*8+7 downto idx*8)); state<=drain;
                    else tx_token<='0' & std_logic_vector(not crc(idx*8+7 downto idx*8)); idx<=idx+1; end if;
                end if;
                when drain => if frame_done='1' then state<=idle; end if;
            end case; end if;
        end if;
    end process;
end;
