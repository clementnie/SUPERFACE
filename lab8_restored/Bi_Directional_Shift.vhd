LIBRARY ieee ;
USE ieee.std_logic_1164.all ;
USE ieee.std_logic_unsigned.all ;

ENTITY Bi_Directional_Shift IS
	Generic (n: Integer := 18);
	PORT (	Data		: IN 		STD_LOGIC_VECTOR(n-1 DOWNTO 0);
			Clear, Clk	: IN 		STD_LOGIC ; -- Synchronous Clear
			Enb			: IN 		STD_LOGIC ; -- synchronous enable
			Load		: IN 		STD_LOGIC ; -- Load
			Left_NRight	: IN 		STD_LOGIC ; -- Right for 0 Left for 1
			Shift_in	: IN 		STD_LOGIC ; -- Shift input
			Q			: Buffer	STD_LOGIC_VECTOR(n-1 DOWNTO 0)) ;
END Bi_Directional_Shift ;

ARCHITECTURE Behavior OF Bi_Directional_Shift IS
BEGIN
	Process (Clk,Clear)
	BEGIN
	
		IF (Clk'EVENT AND Clk = '1') THEN -- Synchronous controls start here			
			IF Clear = '1' THEN Q <= (Others => '0'); -- synch Clear
			ELSIF (Enb = '0') THEN  Q <= Q; -- Hold
			ELSIF (Load = '1') THEN Q <= Data; -- Load Data - dominates all other options
			ElSIF (Left_NRight='1') THEN Q <= Q(n-2 DOWNTO 0) & Shift_in ; -- Left Shift
			ElSIF (Left_NRight='0') THEN Q <= Shift_in & Q(n-1 DOWNTO 1); -- Right Shift
			END IF;
		END IF;
	END PROCESS;
END Behavior ;
