library ieee;
use ieee.std_logic_1164.all;

-- Phase 5 font provider. Phase 7 replaces this with the validated loader.
entity Phase5_Font is
    port (font_ready, runtime_owner : out std_logic;
          font_status : out std_logic_vector(2 downto 0);
          font_count : out std_logic_vector(14 downto 0);
          font_mapping : out std_logic_vector(127 downto 0));
end entity;

architecture rtl of Phase5_Font is
begin
    font_ready <= '1';
    runtime_owner <= '0';
    font_status <= "010"; -- This firmware does not implement the image format.
    font_count <= (others => '0');
    font_mapping <= (others => '0');
end architecture;
