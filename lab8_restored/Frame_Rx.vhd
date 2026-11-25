library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Wire_V1.all;

entity Frame_Rx is
    port (clk, reset, run, fifo_empty : in std_logic;
          fifo_data : in std_logic_vector(8 downto 0);
          fifo_read, framing_error : out std_logic;
          payload_busy, payload_read : in std_logic;
          payload_address : in std_logic_vector(7 downto 0);
          payload_data : out std_logic_vector(7 downto 0);
          valid : out std_logic;
          kind, length : out std_logic_vector(7 downto 0);
          session_id : out std_logic_vector(63 downto 0);
          seq : out std_logic_vector(31 downto 0);
          prefix : out std_logic_vector(143 downto 0);
          request_crc : out std_logic_vector(15 downto 0));
end entity;

architecture rtl of Frame_Rx is
    type ram_type is array (0 to 255) of octet;
    signal ram : ram_type;
    signal ram_write : std_logic;
    signal decoded : octet;
    signal pos : natural range 0 to 260 := 0;
    signal payload_length : natural range 0 to 243 := 0;
    signal armed, escaped, pulsed, pop, normal_byte : std_logic := '0';
    signal version, packet_type : octet;
    signal packet_session : std_logic_vector(63 downto 0);
    signal session_bytes : byte_array(0 to 7);
    signal sequence_bytes : byte_array(0 to 3);
    signal prefix_bytes : byte_array(0 to 17);
    signal crc, transmitted_crc : crc_word;
    signal idle_count : natural range 0 to 4999999 := 0;
begin
    pop <= run and not fifo_empty and not payload_busy and not pulsed;
    fifo_read <= pop;
    framing_error <= pop and fifo_data(8);
    valid <= pulsed;
    kind <= packet_type;
    length <= std_logic_vector(to_unsigned(payload_length, 8));
    session_id <= packet_session;
    session_fields : for i in session_bytes'range generate
        packet_session(8*i+7 downto 8*i) <= session_bytes(i);
    end generate;
    sequence_fields : for i in sequence_bytes'range generate
        seq(8*i+7 downto 8*i) <= sequence_bytes(i);
    end generate;
    payload_fields : for i in prefix_bytes'range generate
        prefix(8*i+7 downto 8*i) <= prefix_bytes(i);
    end generate;
    request_crc <= transmitted_crc;

    decoded <= fifo_data(7 downto 0) xor x"20" when escaped = '1'
               else fifo_data(7 downto 0);
    normal_byte <= '1' when pop = '1' and fifo_data(8) = '0' and armed = '1'
        and fifo_data(7 downto 0) /= delim and
        ((escaped = '1' and (fifo_data(7 downto 0) = x"5E" or fifo_data(7 downto 0) = x"5D"))
         or (escaped = '0' and fifo_data(7 downto 0) /= escape)) else '0';
    ram_write <= '1' when normal_byte = '1' and pos >= 15 and pos < 15 + payload_length else '0';

    process(clk)
    begin
        if rising_edge(clk) then
            if ram_write = '1' then ram(pos - 15) <= decoded; end if;
            if payload_read = '1' then payload_data <= ram(to_integer(unsigned(payload_address))); end if;
        end if;
    end process;

    process(clk)
        variable payload_index : natural range 0 to 245;
    begin
        if rising_edge(clk) then
            pulsed <= '0';
            if reset = '1' then
                armed <= '0';
                escaped <= '0';
                pos <= 0;
                idle_count <= 0;
            elsif pop = '1' then
                idle_count <= 0;
                if fifo_data(8) = '1' then
                    armed <= '0';
                elsif fifo_data(7 downto 0) = delim then
                    if armed = '1' and escaped = '0' and pos = 17 + payload_length
                       and crc = transmitted_crc and version = x"01"
                       and packet_session /= x"0000000000000000" then
                        pulsed <= '1';
                    end if;
                    armed <= '1';
                    escaped <= '0';
                    pos <= 0;
                    crc <= x"FFFF";
                elsif armed = '1' then
                    if normal_byte = '1' then
                        escaped <= '0';
                        if pos < 15 + payload_length then crc <= crc_byte(crc, decoded); end if;
                        case pos is
                            when 0 => version <= decoded;
                            when 1 => packet_type <= decoded;
                            when 2 to 9 =>
                                session_bytes(pos-2) <= decoded;
                            when 10 to 13 =>
                                sequence_bytes(pos-10) <= decoded;
                            when 14 =>
                                if unsigned(decoded) > 243 then armed <= '0';
                                else payload_length <= to_integer(unsigned(decoded));
                                end if;
                            when others =>
                                if pos < 17 + payload_length then
                                    payload_index := pos - 15;
                                    if payload_index = payload_length then
                                        transmitted_crc(7 downto 0) <= decoded;
                                    elsif payload_index = payload_length + 1 then
                                        transmitted_crc(15 downto 8) <= decoded;
                                    elsif payload_index < 18 then
                                        prefix_bytes(payload_index) <= decoded;
                                    end if;
                                else
                                    armed <= '0';
                                end if;
                        end case;
                        if pos < 260 then pos <= pos + 1; end if;
                    elsif escaped = '0' and fifo_data(7 downto 0) = escape then
                        escaped <= '1';
                    else
                        armed <= '0';
                    end if;
                end if;
            elsif armed = '1' and (pos /= 0 or escaped = '1') then
                if idle_count = 4999999 then armed <= '0';
                else idle_count <= idle_count + 1;
                end if;
            end if;
        end if;
    end process;
end architecture;
