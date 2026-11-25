library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Input is the validated byte/error interface for the future PS/2 receiver.
entity Key_Queue is
    port (clk, reset, active, source_valid, source_error, idle_qualified : in std_logic;
          source_byte : in std_logic_vector(7 downto 0);
          take_event, reset_acked : in std_logic;
          event_valid, event_reset : out std_logic;
          event_byte : out std_logic_vector(7 downto 0));
end entity;

architecture rtl of Key_Queue is
    type queue_type is array (0 to 31) of std_logic_vector(7 downto 0);
    type capture_state is (wait_idle, capture, report_error, wait_ack);
    signal queue : queue_type;
    signal state : capture_state := wait_idle;
    signal head, tail : unsigned(4 downto 0) := (others => '0');
    signal used : natural range 0 to 32 := 0;
    signal push_byte, pop_byte, overrun : std_logic;
begin
    event_valid <= '1' when active = '1' and
        (state = report_error or (state = capture and used > 0 and source_error = '0' and
         overrun = '0')) else '0';
    event_reset <= '1' when state = report_error else '0';
    event_byte <= queue(to_integer(head));
    pop_byte <= '1' when state = capture and take_event = '1' and used > 0 else '0';
    overrun <= '1' when source_valid = '1' and used = 32 else '0';
    push_byte <= '1' when state = capture and source_valid = '1' and used < 32 else '0';

    process(clk)
    begin
        if rising_edge(clk) then
            if push_byte = '1' then queue(to_integer(tail)) <= source_byte; end if;
            if reset = '1' or active = '0' then
                state <= wait_idle;
                used <= 0;
                head <= (others => '0');
                tail <= (others => '0');
            else
                case state is
                    when wait_idle =>
                        if idle_qualified = '1' then state <= capture; end if;
                    when capture =>
                        if source_error = '1' or overrun = '1' then
                            used <= 0;
                            head <= tail;
                            state <= report_error;
                        else
                            if push_byte = '1' then tail <= tail + 1; end if;
                            if pop_byte = '1' then head <= head + 1; end if;
                            if push_byte = '1' and pop_byte = '0' then used <= used + 1;
                            elsif push_byte = '0' and pop_byte = '1' then used <= used - 1;
                            end if;
                        end if;
                    when report_error =>
                        if take_event = '1' then state <= wait_ack; end if;
                    when wait_ack =>
                        if reset_acked = '1' then state <= wait_idle; end if;
                end case;
            end if;
        end if;
    end process;
end architecture;
