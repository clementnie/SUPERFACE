--****** VHDL Design file for a Binary to Seven Segment Driver ***
library IEEE;
use IEEE.std_logic_1164.all;

Entity Huge_Seven_Seg_Driver is 
	port(Data_in: in  STD_LOGIC_VECTOR (4 downto 0);
	     LED: out STD_LOGIC_VECTOR (27 downto 0));
End Huge_Seven_Seg_Driver;

--****** This Case statement is very close to a truth table ***
--- This is a large ROM which as 32 entries and 28 bits of output
-- THis could be used to make patterns across all 7 segements at once
-- The output could be connected to: HEX3[6..0],HEX2[6..0],HEX1[6..0],HEX0[6..0],
-- just cut and paste the above text onto the output for ease of connection
Architecture Structure of Huge_Seven_Seg_Driver is
Begin
	Process(Data_in)
	Begin
		Case Data_in is
		--  A zero turns that Segment 0n and a 1 turns it off
		--   
			
			when "00000" => LED <= "1111111111111111111111111110";
			when "00001" => LED <= "1111111111111111111111111101";
			when "00010" => LED <= "1111111111111111111111111011";
			when "00011" => LED <= "1111111111111111111111110111";
			
			when "00100" => LED <= "1111111111111111111111101111";
			when "00101" => LED <= "1111111111111111111111011111";
			when "00110" => LED <= "1111111111111111111110111111";
			when "00111" => LED <= "1111111111111111111101111111";
			
			when "01000" => LED <= "1111111111111111111011111111";
			when "01001" => LED <= "1111111111111111110111111111";
			when "01010" => LED <= "1111111111111111101111111111";
			when "01011" => LED <= "1111111111111111011111111111";
			
			when "01100" => LED <= "1111111111111110111111111111";
			when "01101" => LED <= "1111111111111101111111111111";
			when "01110" => LED <= "1111111111111011111111111111";
			when "01111" => LED <= "1111111111110111111111111111";
			
			when "10000" => LED <= "1111111111101111111111111111";
			when "10001" => LED <= "1111111111011111111111111111";
			when "10010" => LED <= "1111111110111111111111111111";
			when "10011" => LED <= "1111111101111111111111111111";
			
			when "10100" => LED <= "1111111011111111111111111111";
			when "10101" => LED <= "1111110111111111111111111111";
			when "10110" => LED <= "1111101111111111111111111111";
			when "10111" => LED <= "1111011111111111111111111111";
			
			when "11000" => LED <= "1110111111111111111111111111";
			when "11001" => LED <= "1101111111111111111111111111";
			when "11010" => LED <= "1011111111111111111111111111";
			when "11011" => LED <= "0111111111111111111111111111";
			
			when "11100" => LED <= "1111111111111111111111111111";
			when "11101" => LED <= "1111111111111111111111111111";
			when "11110" => LED <= "1111111111111111111111111111";
			when "11111" => LED <= "1111111111111111111111111111";
			
			when others => LED <= "1111111111111111111111111111";--this is what all others get
		End Case;
	End process;
End Structure;
