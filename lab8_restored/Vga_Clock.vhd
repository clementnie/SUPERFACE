library ieee;
use ieee.std_logic_1164.all;

-- Cyclone II ALTPLL IP. Quartus selects the physical VCO and counters.
entity Vga_Clock is
    port (clock_50, reset : in std_logic;
          pixel_clk, locked : out std_logic);
end entity;

architecture rtl of Vga_Clock is
    -- Declare only the generics used by the synthesis megafunction. The
    -- full simulation component defaults include unsupported test settings.
    component altpll is
        generic (intended_device_family : string;
                 inclk0_input_frequency : natural;
                 operation_mode, compensate_clock : string;
                 clk0_multiply_by, clk0_divide_by : natural;
                 port_areset, port_locked, port_inclk0, port_inclk1, port_clk0 : string;
                 width_clock : natural);
        port (inclk : in std_logic_vector(1 downto 0);
              areset : in std_logic;
              clk : out std_logic_vector(width_clock - 1 downto 0);
              locked : out std_logic);
    end component;
    signal clocks : std_logic_vector(4 downto 0);
begin
    pll : altpll
        generic map (intended_device_family => "Cyclone II",
                     inclk0_input_frequency => 20000,
                     operation_mode => "NORMAL", compensate_clock => "CLK0",
                     clk0_multiply_by => 13, clk0_divide_by => 10,
                     port_areset => "PORT_USED", port_locked => "PORT_USED",
                     port_inclk0 => "PORT_USED", port_inclk1 => "PORT_UNUSED",
                     port_clk0 => "PORT_USED", width_clock => 5)
        port map (inclk => '0' & clock_50, areset => reset, clk => clocks, locked => locked);
    pixel_clk <= clocks(0);
end architecture;
