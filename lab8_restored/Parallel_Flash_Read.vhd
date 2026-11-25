library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
-- Runtime read-only byte-wide NOR. WE# is never asserted by this module.
entity Parallel_Flash_Read is
    port (clk, reset, request : in std_logic;
          address : in std_logic_vector(21 downto 0);
          flash_data : in std_logic_vector(7 downto 0);
          flash_addr : out std_logic_vector(21 downto 0);
          ce_n, oe_n, we_n, rst_n, ready, done : out std_logic;
          data : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of Parallel_Flash_Read is
    type state_t is (reset_hold, reset_wait, idle, reading);
    signal state: state_t := reset_hold;
    signal ticks: natural range 0 to 4999 := 0;
begin
    we_n<='1';
    rst_n<='0' when state=reset_hold or reset='1' else '1';
    ce_n<='0' when state=reading and reset='0' else '1';
    oe_n<='0' when state=reading and reset='0' else '1';
    ready<='1' when state=idle and reset='0' else '0';
    process(clk) begin
        if rising_edge(clk) then
            done<='0';
            if reset='1' then state<=reset_hold; ticks<=0; flash_addr<=(others=>'0'); data<=(others=>'0');
            else case state is
                when reset_hold | reset_wait =>
                    if ticks=4999 then
                        ticks<=0;
                        if state=reset_hold then state<=reset_wait; else state<=idle; end if;
                    else ticks<=ticks+1; end if;
                when idle =>
                    if request='1' then flash_addr<=address; ticks<=0; state<=reading; end if;
                when reading =>
                    -- 400 ns address and read-enable window.
                    if ticks=19 then data<=flash_data; done<='1'; state<=idle;
                    else ticks<=ticks+1; end if;
            end case; end if;
        end if;
    end process;
end;
