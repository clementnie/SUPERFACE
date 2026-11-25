library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity Xga_Raster is
    port (pixel_clk, reset, line_ready : in std_logic;
          read_col : out std_logic_vector(6 downto 0);
          line_check, line_release, frame_blank, blank_entry, line_wrap : out std_logic;
          logical_x, logical_y : out std_logic_vector(9 downto 0);
          pixel_valid, hs_n, vs_n : out std_logic);
end entity;

architecture rtl of Xga_Raster is
    constant h_active : natural := 1024;
    constant h_sync_start : natural := h_active + 24;
    constant h_sync_end : natural := h_sync_start + 136;
    constant h_total : natural := h_sync_end + 160;
    constant v_active : natural := 768;
    constant v_sync_start : natural := v_active + 3;
    constant v_sync_end : natural := v_sync_start + 6;
    constant v_total : natural := v_sync_end + 29;

    constant left : natural := 32;
    constant right : natural := left + 960;
    constant top : natural := 24;
    constant bottom : natural := top + 720;
    signal h : natural range 0 to h_total - 1 := 0;
    signal v : natural range 0 to v_total - 1 := v_active;
    signal source_x : unsigned(9 downto 0) := (others => '0');
    signal source_y : unsigned(8 downto 0) := (others => '0');
    signal x_phase, y_phase : natural range 0 to 2 := 0;
    signal inside_x, inside_y : boolean;
    signal in_blank : std_logic := '1';
begin
    inside_x <= h >= left and h < right;
    inside_y <= v >= top and v < bottom;
    read_col <= std_logic_vector(source_x(9 downto 3));
    line_check <= '1' when h = 16 and inside_y else '0';
    line_release <= '1' when h = right and inside_y and y_phase /= 0 else '0';
    line_wrap <= '1' when h = h_total - 1 else '0';
    blank_entry <= '1' when h = 0 and v = v_active else '0';
    frame_blank <= in_blank or reset;

    process(pixel_clk)
    begin
        if rising_edge(pixel_clk) then
            if reset = '1' then
                h <= 0;
                v <= v_active;
                in_blank <= '1';
                source_x <= (others => '0');
                source_y <= (others => '0');
                x_phase <= 0;
                y_phase <= 0;
                hs_n <= '1';
                vs_n <= '1';
                pixel_valid <= '0';
                logical_x <= (others => '0');
                logical_y <= (others => '1');
            else
                -- Register coordinates and sync beside the synchronous RAM read.
                if h >= h_sync_start and h < h_sync_end then hs_n <= '0'; else hs_n <= '1'; end if;
                if v >= v_sync_start and v < v_sync_end then vs_n <= '0'; else vs_n <= '1'; end if;
                logical_x <= std_logic_vector(source_x);
                logical_y <= (others => '1');
                pixel_valid <= '0';
                if inside_x and inside_y then
                    logical_y <= '0' & std_logic_vector(source_y);
                    pixel_valid <= line_ready;
                end if;

                -- floor(2 * offset / 3), implemented by counting 0,0,1,2,2,3,...
                if inside_x then
                    if x_phase /= 0 then source_x <= source_x + 1; end if;
                    if x_phase = 2 then x_phase <= 0; else x_phase <= x_phase + 1; end if;
                end if;
                if h = h_total - 1 then
                    h <= 0;
                    source_x <= (others => '0');
                    x_phase <= 0;
                    if inside_y then
                        if y_phase /= 0 then source_y <= source_y + 1; end if;
                        if y_phase = 2 then y_phase <= 0; else y_phase <= y_phase + 1; end if;
                    end if;
                    if v = v_total - 1 then
                        v <= 0;
                        source_y <= (others => '0');
                        y_phase <= 0;
                        in_blank <= '0';
                    else
                        v <= v + 1;
                        if v = v_active - 1 then in_blank <= '1'; end if;
                    end if;
                else
                    h <= h + 1;
                end if;
            end if;
        end if;
    end process;
end architecture;
