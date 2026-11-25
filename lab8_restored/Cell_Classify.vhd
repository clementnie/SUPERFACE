library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.Font_CRC.all;

entity Cell_Classify is
    port (Cell, Neighbor : in std_logic_vector(23 downto 0);
          Col : in std_logic_vector(6 downto 0);
          Font_OK : in std_logic;
          Font_Count : in std_logic_vector(14 downto 0);
          ASCII_Code : out std_logic_vector(6 downto 0);
          Is_Wide, Use_Chinese, Orphan : out std_logic);
end entity;

architecture rtl of Cell_Classify is
    signal id : unsigned(15 downto 0);
    signal han, pair, missing : boolean;
begin
    id <= unsigned(Cell(15 downto 0));
    han <= id >= 16#8000# and id < 16#8000# + wide_glyphs;
    missing <= id = 16#80#;
    pair <= (han or missing) and unsigned(Col) < 79 and
            Neighbor(15 downto 0) = x"FFFF" and Cell(23 downto 16) = Neighbor(23 downto 16);
    Is_Wide <= '1' when pair else '0';
    Use_Chinese <= '1' when han and pair and Font_OK = '1' else '0';
    Orphan <= '1' when id = 16#ffff# else '0';
    ASCII_Code <= Cell(6 downto 0) when id >= 16#20# and id <= 16#7e# else "0111111";
end architecture;
