library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.STD_LOGIC_ARITH.ALL;
use IEEE.STD_LOGIC_UNSIGNED.ALL;
 
entity SW_Encoder is
   port ( SW_in : in std_logic_vector(9 downto 0);
 	  Switch : out std_logic_vector(3 downto 0);
 	             Valid : out std_logic);
end SW_Encoder;
 
architecture LOGIC of SW_Encoder is
begin
   Switch <= "1001" when SW_in(9)='1' else
 	        "1000" when SW_in(8)='1' else
			"0111" when SW_in(7)='1' else
			"0110" when SW_in(6)='1' else
			"0101" when SW_in(5)='1' else
			"0100" when SW_in(4)='1' else
			"0011" when SW_in(3)='1' else
			"0010" when SW_in(2)='1' else
			"0001" when SW_in(1)='1' else
			"0000" when SW_in(0)='1' else
 		    "0000";
   Valid <= '0' when SW_in="0000" else '1';
end LOGIC;