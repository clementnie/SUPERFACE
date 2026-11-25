library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Wire_V1.all;

entity Uart_Session is
    port (clk, reset, font_ready : in std_logic;
          font_status : in std_logic_vector(2 downto 0);
          font_count : in std_logic_vector(14 downto 0);
          font_mapping : in std_logic_vector(127 downto 0);
          rx_valid : in std_logic;
          rx_kind, rx_length : in std_logic_vector(7 downto 0);
          rx_session : in std_logic_vector(63 downto 0);
          rx_seq : in std_logic_vector(31 downto 0);
          rx_prefix : in std_logic_vector(143 downto 0);
          rx_crc : in std_logic_vector(15 downto 0);
          tx_ready, tx_done : in std_logic;
          tx_start : out std_logic;
          tx_kind, tx_length : out std_logic_vector(7 downto 0);
          tx_session : out std_logic_vector(63 downto 0);
          tx_seq : out std_logic_vector(31 downto 0);
          tx_payload : out std_logic_vector(199 downto 0);
          dispatch, invalidate, chinese, linked, key_active, key_idle : out std_logic;
          display_complete : in std_logic;
          display_status : in std_logic_vector(2 downto 0);
          event_valid, event_reset : in std_logic;
          event_byte : in std_logic_vector(7 downto 0);
          take_event, reset_acked : out std_logic);
end entity;

architecture rtl of Uart_Session is
    constant no_session : std_logic_vector(63 downto 0) := (others => '0');
    constant no_mapping : std_logic_vector(127 downto 0) := (others => '0');
    signal candidate : std_logic_vector(63 downto 0) := no_session;
    signal offer_request : std_logic_vector(143 downto 0);
    signal offer_body : std_logic_vector(199 downto 0);
    signal accepted, active, chinese_mode : std_logic := '0';
    signal extended : std_logic := '0';
    signal offer_pending, ack_pending, command_pending : std_logic := '0';
    signal offer_flight, ack_flight, key_flight : std_logic := '0';
    signal cache_status : octet;
    signal cache_seq : std_logic_vector(31 downto 0);
    signal cache_kind : octet;
    signal cache_crc : crc_word;
    signal cache_valid : std_logic := '0';
    signal expected : unsigned(31 downto 0) := to_unsigned(1, 32);
    signal silence : natural range 0 to 100000000 := 0;
    signal key_seq : unsigned(31 downto 0) := to_unsigned(1, 32);
    type key_state is (key_empty, key_send, key_on_wire, key_wait);
    signal key_state_now : key_state := key_empty;
    signal key_reset_kind : std_logic;
    signal key_byte : octet;
    signal key_timer : natural range 0 to 5000000 := 0;
    signal retries : natural range 0 to 3 := 0;
    signal schedule, send_offer, send_ack, send_key, new_key : std_logic;
    signal invalidated : std_logic := '0';
begin
    invalidate <= invalidated or reset;
    chinese <= chinese_mode and accepted;
    linked <= accepted;
    key_active <= active and accepted;
    key_idle <= '1' when key_state_now = key_empty else '0';

    schedule <= tx_ready and not rx_valid and not display_complete and not invalidated;
    send_offer <= schedule and offer_pending;
    send_ack <= schedule and not offer_pending and ack_pending;
    send_key <= '1' when schedule = '1' and offer_pending = '0' and ack_pending = '0' and
        accepted = '1' and (key_state_now = key_send or
        (key_state_now = key_empty and active = '1' and event_valid = '1')) else '0';
    new_key <= '1' when send_key = '1' and key_state_now = key_empty else '0';
    take_event <= new_key;
    tx_start <= send_offer or send_ack or send_key;
    tx_kind <= offer_type when send_offer = '1' else ack_type when send_ack = '1' else key_type;
    tx_length <= x"19" when send_offer = '1' else x"02" when send_ack = '1' else
                 x"01" when (new_key = '1' and event_reset = '1') or
                            (new_key = '0' and key_reset_kind = '1') else x"02";
    tx_session <= candidate;
    tx_seq <= (others => '0') when send_offer = '1' else cache_seq when send_ack = '1'
              else std_logic_vector(key_seq);
    tx_payload <= offer_body when send_offer = '1' else
        (199 downto 16 => '0') & cache_status & cache_kind when send_ack = '1' else
        (199 downto 16 => '0') & event_byte & "0000000" & event_reset when new_key = '1' else
        (199 downto 16 => '0') & key_byte & "0000000" & key_reset_kind;

    process(clk)
        variable count_requested : unsigned(15 downto 0);
        variable mapping_requested : std_logic_vector(127 downto 0);
        variable result_code : octet;
        variable expire : boolean;
    begin
        if rising_edge(clk) then
            dispatch <= '0';
            reset_acked <= '0';
            invalidated <= '0';
            expire := false;
            if reset = '1' then
                candidate <= no_session;
                accepted <= '0';
                active <= '0';
                chinese_mode <= '0';
                offer_pending <= '0';
                ack_pending <= '0';
                command_pending <= '0';
                offer_flight <= '0';
                ack_flight <= '0';
                key_flight <= '0';
                cache_valid <= '0';
                key_state_now <= key_empty;
                silence <= 0;
            else
                if accepted = '1' then
                    if silence = 99999999 or (chinese_mode = '1' and font_status /= "000") then
                        expire := true;
                    else silence <= silence + 1;
                    end if;
                end if;

                if tx_done = '1' then
                    offer_flight <= '0';
                    ack_flight <= '0';
                    key_flight <= '0';
                    if key_flight = '1' and key_state_now = key_on_wire then
                        key_timer <= 0;
                        key_state_now <= key_wait;
                    end if;
                end if;

                if send_offer = '1' then
                    offer_pending <= '0';
                    offer_flight <= '1';
                elsif send_ack = '1' then
                    ack_pending <= '0';
                    ack_flight <= '1';
                elsif send_key = '1' then
                    if new_key = '1' then
                        retries <= 0;
                        key_byte <= event_byte;
                        key_reset_kind <= event_reset;
                    end if;
                    key_flight <= '1';
                    key_state_now <= key_on_wire;
                end if;

                if key_state_now = key_wait then
                    if key_timer = 4999999 then
                        if retries = 3 then expire := true;
                        else
                            retries <= retries + 1;
                            key_state_now <= key_send;
                        end if;
                    else key_timer <= key_timer + 1;
                    end if;
                end if;

                if display_complete = '1' and command_pending = '1' then
                    command_pending <= '0';
                    cache_status <= "00000" & display_status;
                    cache_valid <= '1';
                    ack_pending <= '1';
                    if display_status = "000" then
                        if cache_kind = begin_type or cache_kind = extended_begin_type then active <= '0';
                        elsif cache_kind = end_type then active <= '1';
                        end if;
                    end if;
                end if;

                if rx_valid = '1' then
                    if (rx_kind = hello_type or rx_kind = extended_hello_type) and font_ready = '1' and rx_seq = x"00000000"
                        and rx_length = x"12" then
                        count_requested := unsigned(rx_prefix(15 downto 0));
                        mapping_requested := rx_prefix(143 downto 16);
                        if (count_requested = 0 and mapping_requested = no_mapping) or
                           (count_requested > 0 and count_requested <= 16384 and
                            mapping_requested /= no_mapping) then
                            if rx_session = candidate then
                                if rx_prefix = offer_request and
                                   ((rx_kind = extended_hello_type and extended = '1') or
                                    (rx_kind = hello_type and extended = '0')) and
                                   (offer_flight = '0' or tx_done = '1') then offer_pending <= '1'; end if;
                            else
                                expire := false;
                                invalidated <= '1';
                                candidate <= rx_session;
                                offer_request <= rx_prefix;
                                active <= '0';
                                silence <= 0;
                                expected <= to_unsigned(1, 32);
                                key_seq <= to_unsigned(1, 32);
                                key_state_now <= key_empty;
                                key_flight <= '0';
                                ack_flight <= '0';
                                offer_flight <= '0';
                                ack_pending <= '0';
                                command_pending <= '0';
                                cache_valid <= '0';
                                offer_pending <= '1';
                                chinese_mode <= '0';
                                if count_requested = 0 then result_code := x"00";
                                elsif font_status = "000" and count_requested = unsigned('0' & font_count)
                                      and mapping_requested = font_mapping then
                                    result_code := x"01";
                                    chinese_mode <= '1';
                                else result_code := x"02";
                                end if;
                                if result_code = x"02" then accepted <= '0';
                                else accepted <= '1';
                                end if;
                                if rx_kind = extended_hello_type then
                                    extended <= '1';
                                    offer_body(55 downto 0) <= x"1FF3031E50" & "00000" & font_status & result_code;
                                else
                                    extended <= '0';
                                    offer_body(55 downto 0) <= x"07F3031E50" & "00000" & font_status & result_code;
                                end if;
                                if font_status = "000" then
                                    offer_body(199 downto 56) <= font_mapping & '0' & font_count;
                                else offer_body(199 downto 56) <= (others => '0');
                                end if;
                            end if;
                        end if;
                    elsif accepted = '1' and rx_session = candidate and rx_seq /= x"00000000" then
                        if rx_kind = ack_type and key_state_now /= key_empty and
                            unsigned(rx_seq) = key_seq and rx_length = x"02" and
                            rx_prefix(7 downto 0) = key_type and unsigned(rx_prefix(15 downto 8)) <= 3 then
                            silence <= 0;
                            expire := rx_prefix(15 downto 8) /= x"00" or key_seq = x"FFFFFFFF";
                            if key_reset_kind = '1' then reset_acked <= '1'; end if;
                            key_state_now <= key_empty;
                            key_seq <= key_seq + 1;
                        elsif unsigned(rx_kind) >= unsigned(begin_type) and
                              (unsigned(rx_kind) <= unsigned(ping_type) or
                               (extended = '1' and unsigned(rx_kind) <= unsigned(extended_begin_type))) then
                            if unsigned(rx_seq) = expected and command_pending = '0' then
                                silence <= 0;
                                expire := false;
                                expected <= expected + 1;
                                cache_seq <= rx_seq;
                                cache_kind <= rx_kind;
                                cache_crc <= rx_crc;
                                ack_pending <= '0';
                                cache_valid <= '0';
                                if rx_kind = ping_type then
                                    if rx_length = x"00" then cache_status <= x"00";
                                    else cache_status <= x"01";
                                    end if;
                                    cache_valid <= '1';
                                    ack_pending <= '1';
                                else
                                    dispatch <= '1';
                                    command_pending <= '1';
                                end if;
                            elsif (cache_valid = '1' or command_pending = '1') and
                                  rx_seq = cache_seq and rx_kind = cache_kind and rx_crc = cache_crc then
                                silence <= 0;
                                expire := false;
                                if cache_valid = '1' and (ack_flight = '0' or tx_done = '1') then
                                    ack_pending <= '1';
                                end if;
                            end if;
                        end if;
                    end if;
                end if;

                if expire then
                    candidate <= no_session;
                    invalidated <= '1';
                    accepted <= '0';
                    active <= '0';
                    offer_pending <= '0';
                    ack_pending <= '0';
                    command_pending <= '0';
                    cache_valid <= '0';
                    key_state_now <= key_empty;
                end if;
            end if;
        end if;
    end process;
end architecture;
