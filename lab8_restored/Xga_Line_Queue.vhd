library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Four slots, including the slot currently being displayed. The clocks share
-- an oscillator but the crossings use Gray pointers and two-stage sampling.
entity Xga_Line_Queue is
    port (clk, reset, pixel_clk, pixel_reset, frame_blank : in std_logic;
          shown, cursor_visible, build_busy, build_complete, build_we : in std_logic;
          cursor_row : in std_logic_vector(4 downto 0);
          cursor_col, build_col : in std_logic_vector(6 downto 0);
          build_data : in std_logic_vector(15 downto 0);
          line_check, line_release : in std_logic;
          sys_blank, commit_tick, build_reset, build_start, line_ready : out std_logic;
          build_target : out std_logic_vector(8 downto 0);
          wr_en : out std_logic;
          wr_addr : out std_logic_vector(8 downto 0);
          wr_data : out std_logic_vector(15 downto 0);
          rd_slot : out std_logic_vector(1 downto 0));
end entity;

architecture rtl of Xga_Line_Queue is
    subtype pointer is unsigned(2 downto 0);
    function gray(n : pointer) return pointer is
    begin
        return n xor shift_right(n, 1);
    end function;
    signal wr_ptr, wr_gray, wr_meta, wr_sync : pointer := (others => '0');
    signal rd_ptr, rd_gray, rd_meta, rd_sync : pointer := (others => '0');
    signal blank_meta, blank_sync, blank_last : std_logic := '1';
    signal target : unsigned(8 downto 0) := (others => '0');
    signal rendering, render_fault, scan_fault, row_present : std_logic := '0';
    signal space, start : std_logic;
begin
    sys_blank <= blank_sync;
    commit_tick <= blank_sync and not blank_last;
    build_reset <= reset or blank_sync;
    build_target <= std_logic_vector(target);
    space <= '1' when wr_gray /= (not rd_sync(2 downto 1) & rd_sync(0)) else '0';
    start <= '1' when reset = '0' and blank_sync = '0' and shown = '1' and
                      target < 480 and space = '1' and rendering = '0' and
                      render_fault = '0' else '0';
    build_start <= start;
    wr_en <= build_we and rendering and not blank_sync and not reset;
    wr_addr <= std_logic_vector(wr_ptr(1 downto 0)) & build_col;
    -- The cursor and the committed image stay in the system clock domain.
    wr_data <= build_data(15 downto 8) & (not build_data(7 downto 0))
        when cursor_visible = '1' and target(8 downto 4) = unsigned(cursor_row) and
             target(3 downto 0) >= 14 and build_col = cursor_col else build_data;

    process(clk)
    begin
        if rising_edge(clk) then
            blank_meta <= frame_blank;
            blank_sync <= blank_meta;
            blank_last <= blank_sync;
            rd_meta <= rd_gray;
            rd_sync <= rd_meta;
            if reset = '1' or blank_sync = '1' then
                wr_ptr <= (others => '0');
                wr_gray <= (others => '0');
                target <= (others => '0');
                rendering <= '0';
                render_fault <= '0';
            elsif start = '1' then
                rendering <= '1';
            elsif rendering = '1' and build_busy = '0' then
                rendering <= '0';
                if build_complete = '1' then
                    wr_ptr <= wr_ptr + 1;
                    wr_gray <= gray(wr_ptr + 1);
                    target <= target + 1;
                else
                    -- Hold our place. The reader will blank on a missing row.
                    render_fault <= '1';
                end if;
            end if;
        end if;
    end process;

    rd_slot <= std_logic_vector(rd_ptr(1 downto 0));
    line_ready <= row_present;
    process(pixel_clk)
    begin
        if rising_edge(pixel_clk) then
            wr_meta <= wr_gray;
            wr_sync <= wr_meta;
            if pixel_reset = '1' or frame_blank = '1' then
                rd_ptr <= (others => '0');
                rd_gray <= (others => '0');
                row_present <= '0';
                scan_fault <= '0';
            elsif line_check = '1' then
                if scan_fault = '0' and rd_gray /= wr_sync then
                    row_present <= '1';
                else
                    row_present <= '0';
                    scan_fault <= '1';
                end if;
            elsif line_release = '1' and row_present = '1' then
                rd_ptr <= rd_ptr + 1;
                rd_gray <= gray(rd_ptr + 1);
                row_present <= '0';
            end if;
        end if;
    end process;
end architecture;
