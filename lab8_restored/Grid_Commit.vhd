library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Font_CRC.all;

entity Grid_Commit is
    port (Clk, Reset, VBlank_Entry, In_VBlank, Font_OK, Cmd_Valid : in std_logic;
          Cursor_On, Invalidate, Push, Grid_Q_Valid : in std_logic;
          Col, Count : in std_logic_vector(6 downto 0);
          Font_Count : in std_logic_vector(14 downto 0);
          Grid_Q, Push_Cell : in std_logic_vector(23 downto 0);
          Op : in std_logic_vector(2 downto 0);
          Row : in std_logic_vector(4 downto 0);
          Ready, Push_Ready, Done, Shown, Cursor_Visible, Rd_Req, Wr_Req : out std_logic;
          Cursor_Col : out std_logic_vector(6 downto 0);
          Cursor_Row : out std_logic_vector(4 downto 0);
          Rd_Addr : out std_logic_vector(11 downto 0);
          Result : out std_logic_vector(2 downto 0);
          Wr_Addr : out std_logic_vector(11 downto 0);
          Wr_Data : out std_logic_vector(23 downto 0));
end entity;

architecture rtl of Grid_Commit is
    subtype cell is std_logic_vector(23 downto 0);
    type grid_ram is array (0 to 2399) of cell;
    type row_ram is array (0 to 79) of cell;
    signal shadow : grid_ram;
    signal payload : row_ram;
    signal shadow_data, patch_data : cell;
    signal shadow_addr : natural range 0 to 2399;
    signal patch_addr : natural range 0 to 79;
    signal shadow_write, patch_write, can_push : std_logic;

    type mode_type is (await_snapshot, snapshot, active);
    type state_type is (idle, read_cell, check_cell, patch_read, patch_write_cell,
                        blank_wait, copy_read, copy_write);
    signal mode : mode_type := await_snapshot;
    signal state : state_type := idle;
    signal extended_cells : std_logic := '0';
    signal frames_staged : std_logic := '0';
    signal hide_pending : std_logic := '0';
    signal staged : natural range 0 to 80 := 0;
    signal expected_row : natural range 0 to 30 := 0;
    signal base : natural range 0 to 2320;
    signal first, last : natural range 0 to 80;
    signal index : natural range 0 to 79;
    signal copy_addr : natural range 0 to 2399;
    signal operation : std_logic_vector(2 downto 0);
    signal cursor_next : std_logic;
    signal row_next : std_logic_vector(4 downto 0);
    signal col_next : std_logic_vector(6 downto 0);
    signal need_tail : std_logic;
    signal lead_color : std_logic_vector(7 downto 0);
begin
    Ready <= '1' when state = idle and Invalidate = '0' else '0';
    Push_Ready <= can_push;
    can_push <= '1' when state = idle and staged < 80 and
                            Cmd_Valid = '0' and Invalidate = '0' else '0';
    Rd_Req <= '0';
    Rd_Addr <= (others => '0');
    Wr_Req <= '1' when state = copy_write and Invalidate = '0' and Reset = '0' else '0';
    Wr_Addr <= std_logic_vector(to_unsigned(copy_addr, 12));
    Wr_Data <= shadow_data;
    shadow_addr <= copy_addr when state = copy_read or state = copy_write else base + index;
    shadow_write <= '1' when state = patch_write_cell and Invalidate = '0' and Reset = '0' else '0';
    patch_addr <= index - first when index >= first and index < last else 0;
    patch_write <= Push and can_push;

    process(Clk)
    begin
        if rising_edge(Clk) then
            if shadow_write = '1' then shadow(shadow_addr) <= patch_data; end if;
            if state = read_cell or state = copy_read then shadow_data <= shadow(shadow_addr); end if;
            if patch_write = '1' then payload(staged) <= Push_Cell; end if;
            if state = read_cell or state = patch_read then patch_data <= payload(patch_addr); end if;
        end if;
    end process;

    process(Clk)
        variable r, c, n : natural;
        variable current : cell;
        variable id : unsigned(15 downto 0);
        variable valid, wide, single : boolean;
        procedure finish(constant status : in std_logic_vector(2 downto 0)) is
        begin
            Done <= '1';
            Result <= status;
            staged <= 0;
            state <= idle;
        end procedure;
        procedure set_cursor is
        begin
            Cursor_Visible <= cursor_next;
            Cursor_Row <= row_next;
            Cursor_Col <= col_next;
        end procedure;
    begin
        if rising_edge(Clk) then
            Done <= '0';
            if Reset = '1' then
                mode <= await_snapshot;
                state <= idle;
                staged <= 0;
                expected_row <= 0;
                frames_staged <= '0';
                hide_pending <= '0';
                Shown <= '0';
                Cursor_Visible <= '0';
                Cursor_Row <= (others => '0');
                Cursor_Col <= (others => '0');
                Result <= (others => '0');
            elsif Invalidate = '1' then
                if state /= idle then finish("100"); end if;
                mode <= await_snapshot;
                staged <= 0;
                frames_staged <= '0';
                hide_pending <= '1';
                if In_VBlank = '1' then
                    hide_pending <= '0';
                    Shown <= '0';
                    Cursor_Visible <= '0';
                end if;
            else
                if hide_pending = '1' and VBlank_Entry = '1' then
                    hide_pending <= '0';
                    Shown <= '0';
                    Cursor_Visible <= '0';
                end if;
                if patch_write = '1' then staged <= staged + 1; end if;
                case state is
                    when idle =>
                        if Cmd_Valid = '1' then
                            r := to_integer(unsigned(Row));
                            c := to_integer(unsigned(Col));
                            n := to_integer(unsigned(Count));
                            operation <= Op;
                            row_next <= Row;
                            col_next <= Col;
                            cursor_next <= Cursor_On;
                            case Op is
                                when "000" | "001" =>
                                    if staged /= 0 then finish("001");
                                    elsif mode = snapshot then finish("010");
                                    else state <= blank_wait;
                                    end if;
                                when "010" | "100" | "110" =>
                                    if r >= 30 or c + n > 80 or n = 0 or
                                       staged /= n or (Op = "010" and (n /= 80 or r /= expected_row)) then
                                        finish("001");
                                    elsif (Op = "010" and mode /= snapshot) or
                                          (Op /= "010" and mode /= active) or
                                          (Op = "100" and frames_staged = '1') then
                                        finish("010");
                                    else
                                        base <= r * 80;
                                        first <= c;
                                        last <= c + n;
                                        index <= 0;
                                        need_tail <= '0';
                                        state <= read_cell;
                                    end if;
                                when "011" | "101" | "111" =>
                                    if r >= 30 or c >= 80 or staged /= 0 then finish("001");
                                    elsif (Op = "011" and (mode /= snapshot or expected_row /= 30)) or
                                          (Op /= "011" and mode /= active) or
                                          (Op = "101" and frames_staged = '1') then finish("010");
                                    else state <= blank_wait;
                                    end if;
                                when others => finish("001");
                            end case;
                        end if;
                    when read_cell =>
                        state <= check_cell;
                    when check_cell =>
                        if index >= first and index < last then current := patch_data;
                        else current := shadow_data;
                        end if;
                        id := unsigned(current(15 downto 0));
                        wide := (Font_OK = '1' and id >= 16#8000# and id < 16#8000# + wide_glyphs) or
                                (extended_cells = '1' and id = 16#80#);
                        single := extended_cells = '1' and (id = 16#7f# or
                                  (Font_OK = '1' and id >= 16#8000# + wide_glyphs and id < 16#8000# + glyphs));
                        if need_tail = '1' then
                            valid := id = 16#ffff# and current(23 downto 16) = lead_color;
                        else
                            valid := (id >= 16#20# and id <= 16#7e#) or single or (wide and index < 79);
                        end if;
                        if not valid then finish("011");
                        elsif index = 79 then
                            index <= first;
                            state <= patch_read;
                        else
                            if wide then need_tail <= '1'; else need_tail <= '0'; end if;
                            lead_color <= current(23 downto 16);
                            index <= index + 1;
                            state <= read_cell;
                        end if;
                    when patch_read =>
                        state <= patch_write_cell;
                    when patch_write_cell =>
                        if index + 1 /= last then
                            index <= index + 1;
                            state <= patch_read;
                        elsif operation = "010" then
                            expected_row <= expected_row + 1;
                            finish("000");
                        elsif operation = "110" then
                            frames_staged <= '1';
                            finish("000");
                        else
                            state <= blank_wait;
                        end if;
                    when blank_wait =>
                        if VBlank_Entry = '1' then
                            case operation is
                                when "000" | "001" =>
                                    if operation = "000" then extended_cells <= '1';
                                    else extended_cells <= '0'; end if;
                                    mode <= snapshot;
                                    Shown <= '0';
                                    Cursor_Visible <= '0';
                                    expected_row <= 0;
                                    frames_staged <= '0';
                                    finish("000");
                                when "101" =>
                                    set_cursor;
                                    finish("000");
                                when "111" =>
                                    if frames_staged = '0' then
                                        set_cursor;
                                        finish("000");
                                    else
                                        copy_addr <= 0;
                                        state <= copy_read;
                                    end if;
                                when others =>
                                    copy_addr <= 0;
                                    state <= copy_read;
                            end case;
                        end if;
                    when copy_read =>
                        state <= copy_write;
                    when copy_write =>
                        if copy_addr = 2399 then
                            if operation /= "100" then set_cursor; end if;
                            mode <= active;
                            Shown <= '1';
                            frames_staged <= '0';
                            finish("000");
                        else
                            copy_addr <= copy_addr + 1;
                            state <= copy_read;
                        end if;
                end case;
            end if;
        end if;
    end process;
end architecture;
