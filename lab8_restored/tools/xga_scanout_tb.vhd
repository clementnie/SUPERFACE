library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

-- Exercise the queue with the production BDF builder's fixed 19-cycle
-- schedule for each of 80 SRAM glyphs. The model writes distinct rows/columns
-- so early reads, wrong slots, lost rows, and wraparound show up as bad pixels.
entity xga_scanout_tb is
end entity;

architecture test of xga_scanout_tb is
    signal clk, pixel_clk, reset : std_logic := '0';
    signal col, read_col : std_logic_vector(6 downto 0);
    signal wr_addr, target : std_logic_vector(8 downto 0);
    signal slot : std_logic_vector(1 downto 0);
    signal lx, ly : std_logic_vector(9 downto 0);
    signal data, wr_data, pixel_word : std_logic_vector(15 downto 0);
    signal busy, done, write_cell : std_logic := '0';
    signal ready, check_line, release_line, frame_blank, blank_entry, line_wrap : std_logic;
    signal build_reset, start, sys_blank, commit_tick, wr_en, valid, hs_n, vs_n : std_logic;
    signal cycles : natural range 0 to 1520 := 0;
    signal builds, commits : natural := 0;
    type completion_times is array (0 to 479) of time;
    signal completed : completion_times := (others => 0 ns);

    function word(y, x : natural) return std_logic_vector is
    begin
        return std_logic_vector(to_unsigned((y * 131 + x * 239) mod 65536, 16));
    end function;
begin
    clk <= not clk after 10 ns;
    pixel_clk <= not pixel_clk after 7692 ps;
    reset <= '1', '0' after 116 ns;

    raster : entity work.Xga_Raster
        port map (pixel_clk, reset, ready, read_col, check_line, release_line,
                  frame_blank, blank_entry, line_wrap, lx, ly, valid, hs_n, vs_n);
    queue : entity work.Xga_Line_Queue
        port map (clk, reset, pixel_clk, reset, frame_blank, '1', '1',
                  busy, done, write_cell, "00101", "0000111", col, data,
                  check_line, release_line, sys_blank, commit_tick, build_reset,
                  start, ready, target, wr_en, wr_addr, wr_data, slot);
    ram : entity work.Xga_Line_RAM
        port map (clk, pixel_clk, wr_en, wr_addr, wr_data, slot, read_col, pixel_word);

    col <= std_logic_vector(to_unsigned(cycles / 19, 7));
    data <= word(to_integer(unsigned(target)), cycles / 19);
    write_cell <= '1' when busy = '1' and cycles mod 19 = 14 else '0';
    process(clk)
    begin
        if rising_edge(clk) then
            if commit_tick = '1' then
                assert sys_blank = '1' and busy = '0' severity failure;
                commits <= commits + 1;
            end if;
            if build_reset = '1' then
                cycles <= 0;
                busy <= '0';
                done <= '0';
            elsif start = '1' then
                assert busy = '0' severity failure;
                assert to_integer(unsigned(target)) = builds mod 480 severity failure;
                builds <= builds + 1;
                cycles <= 0;
                busy <= '1';
                done <= '0';
            elsif busy = '1' then
                if cycles = 1519 then
                    busy <= '0';
                    done <= '1';
                    completed(to_integer(unsigned(target))) <= now;
                else
                    cycles <= cycles + 1;
                end if;
            end if;
        end if;
    end process;

    process
        variable x, y, sx, sy, c : natural;
        variable expected : std_logic_vector(15 downto 0);
        variable min_headroom : time := 1 ms;
    begin
        wait until reset = '0';
        -- The raster starts at VBlank, allowing both pointer domains to reset.
        y := 768;
        x := 0;
        for tick in 0 to 1344 * (38 + 2 * 806) - 1 loop
            wait until rising_edge(pixel_clk);
            if y >= 768 then assert frame_blank = '1' severity failure;
            else assert frame_blank = '0' severity failure; end if;
            if x = 0 and y = 768 then assert blank_entry = '1' severity failure;
            else assert blank_entry = '0' severity failure; end if;
            if x = 16 and y >= 24 and y < 744 then
                sy := 2 * (y - 24) / 3;
                if (y - 24) mod 3 /= 1 then
                    assert now > completed(sy) severity failure;
                    if now - completed(sy) < min_headroom then
                        min_headroom := now - completed(sy);
                    end if;
                end if;
            end if;
            wait for 1 ps;
            assert (hs_n = '0') = (x >= 1048 and x < 1184)
                report "horizontal sync mismatch" severity failure;
            assert (vs_n = '0') = (y >= 771 and y < 777)
                report "vertical sync mismatch" severity failure;
            if x >= 32 and x < 992 and y >= 24 and y < 744 then
                assert valid = '1' report "missed scanline at output row " & integer'image(y)
                    severity failure;
                sx := 2 * (x - 32) / 3;
                sy := 2 * (y - 24) / 3;
                c := sx / 8;
                assert to_integer(unsigned(lx)) = sx and to_integer(unsigned(ly)) = sy
                    report "nearest-neighbor coordinate mismatch" severity failure;
                expected := word(sy, c);
                if sy / 16 = 5 and sy mod 16 >= 14 and c = 7 then
                    expected(15 downto 8) := not expected(15 downto 8);
                end if;
                assert pixel_word = expected report "cache or cursor mismatch" severity failure;
            else
                assert valid = '0' and unsigned(ly) >= 480
                    report "non-black margin coordinates" severity failure;
            end if;
            x := (x + 1) mod 1344;
            if x = 0 then y := (y + 1) mod 806; end if;
        end loop;
        assert builds = 960 and commits = 2 severity failure;
        report "PASS: two complete XGA frames, worst-case 80 SRAM slots per source line, both syncs, margins, scaling, line cache and cursor";
        report "Minimum build-to-line-admission headroom " & time'image(min_headroom);
        finish;
    end process;
end architecture;
