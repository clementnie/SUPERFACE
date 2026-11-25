library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Wire_V1.all;

entity Display_Adapter is
    port (clk, reset, cancel, dispatch, key_idle : in std_logic;
          kind, length : in std_logic_vector(7 downto 0);
          fields : in std_logic_vector(23 downto 0);
          payload_data : in std_logic_vector(7 downto 0);
          payload_address : out std_logic_vector(7 downto 0);
          payload_busy, payload_read : out std_logic;
          ready, push_ready, done : in std_logic;
          result : in std_logic_vector(2 downto 0);
          cmd_valid, push, cursor_on : out std_logic;
          op : out std_logic_vector(2 downto 0);
          row : out std_logic_vector(4 downto 0);
          col, count : out std_logic_vector(6 downto 0);
          push_cell : out std_logic_vector(23 downto 0);
          complete : out std_logic;
          status : out std_logic_vector(2 downto 0));
end entity;

architecture rtl of Display_Adapter is
    type adapter_state is (idle, prime, copy_payload, issue, wait_done);
    signal state : adapter_state := idle;
    signal next_address : unsigned(7 downto 0);
    signal cells_left : natural range 0 to 80;
    signal phase : natural range 0 to 2;
    signal glyph_lo, glyph_hi : octet;
    signal admitted_op : std_logic_vector(2 downto 0);
    signal advance : std_logic;
begin
    op <= admitted_op;
    cmd_valid <= '1' when state = issue and cancel = '0'
                    and (admitted_op /= "011" or key_idle = '1') else '0';
    payload_busy <= '1' when state = prime or state = copy_payload else '0';
    payload_address <= std_logic_vector(next_address);
    advance <= '1' when state = copy_payload and cancel = '0' and
                        (phase /= 2 or push_ready = '1') else '0';
    payload_read <= '1' when state = prime or (advance = '1' and (phase /= 2 or cells_left > 1))
                    else '0';
    push <= '1' when state = copy_payload and phase = 2 and cancel = '0' else '0';
    push_cell <= payload_data & glyph_hi & glyph_lo;

    process(clk)
        variable first, second, third, len : natural range 0 to 255;
        variable valid_fields : boolean;
        variable command_op : natural range 0 to 7;
        variable staged, start_col : natural range 0 to 80;
    begin
        if rising_edge(clk) then
            complete <= '0';
            if reset = '1' or cancel = '1' then
                state <= idle;
            else
                case state is
                    when idle =>
                        if dispatch = '1' then
                            first := to_integer(unsigned(fields(7 downto 0)));
                            second := to_integer(unsigned(fields(15 downto 8)));
                            third := to_integer(unsigned(fields(23 downto 16)));
                            len := to_integer(unsigned(length));
                            staged := 0;
                            start_col := 0;
                            command_op := 0;
                            valid_fields := false;
                            row <= (others => '0');
                            cursor_on <= '0';
                            case kind is
                                when begin_type | extended_begin_type =>
                                    if kind = begin_type then command_op := 1;
                                    else command_op := 0; end if;
                                    valid_fields := len = 0;
                                when row_type =>
                                    command_op := 2;
                                    valid_fields := len = 241 and first < 30;
                                    staged := 80;
                                    next_address <= to_unsigned(1, 8);
                                when end_type | cursor_type | commit_type =>
                                    if kind = end_type then command_op := 3;
                                    elsif kind = cursor_type then command_op := 5;
                                    else command_op := 7;
                                    end if;
                                    valid_fields := len = 3 and first < 30 and second < 80 and third <= 1;
                                    if valid_fields then start_col := second; end if;
                                    cursor_on <= fields(16);
                                when span_type | stage_span_type =>
                                    if kind = span_type then command_op := 4;
                                    else command_op := 6; end if;
                                    valid_fields := first < 30 and second < 80 and third > 0
                                        and second + third <= 80 and len = 3 + 3*third;
                                    if valid_fields then
                                        start_col := second;
                                        staged := third;
                                    end if;
                                    next_address <= to_unsigned(3, 8);
                                when others => null;
                            end case;
                            if valid_fields then
                                if command_op /= 1 then row <= fields(4 downto 0); end if;
                                col <= std_logic_vector(to_unsigned(start_col, 7));
                                count <= std_logic_vector(to_unsigned(staged, 7));
                                admitted_op <= std_logic_vector(to_unsigned(command_op, 3));
                                if staged > 0 then
                                    cells_left <= staged;
                                    phase <= 0;
                                    state <= prime;
                                else
                                    state <= issue;
                                end if;
                            else
                                status <= "001";
                                complete <= '1';
                            end if;
                        end if;
                    when prime =>
                        next_address <= next_address + 1;
                        state <= copy_payload;
                    when copy_payload =>
                        if advance = '1' then
                            next_address <= next_address + 1;
                            case phase is
                                when 0 => glyph_lo <= payload_data; phase <= 1;
                                when 1 => glyph_hi <= payload_data; phase <= 2;
                                when 2 =>
                                    if cells_left = 1 then state <= issue;
                                    else cells_left <= cells_left - 1; phase <= 0;
                                    end if;
                            end case;
                        end if;
                    when issue =>
                        if ready = '1' and (admitted_op /= "011" or key_idle = '1') then
                            state <= wait_done;
                        end if;
                    when wait_done =>
                        if done = '1' then
                            status <= result;
                            complete <= '1';
                            state <= idle;
                        end if;
                end case;
            end if;
        end if;
    end process;
end architecture;
