library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity Uart_Reset is
    port (clk50, clk24, board_reset, phy_fault : in std_logic;
          fifo_clear, reset50, reset24, run50, run24 : out std_logic);
end entity;

architecture rtl of Uart_Reset is
    signal clear_request : std_logic;
    signal hold_count : unsigned(4 downto 0) := (others => '0');
    signal fault_meta, fault_sync : std_logic := '0';
    signal release50, release24 : std_logic_vector(1 downto 0) := "00";
    signal peer50, peer24 : std_logic_vector(1 downto 0) := "00";
begin
    clear_request <= '1' when board_reset = '1' or hold_count < 16 else '0';
    fifo_clear <= clear_request;
    reset50 <= not release50(1);
    reset24 <= not release24(1);
    run50 <= release50(1) and peer24(1);
    run24 <= release24(1) and peer50(1);

    process(clk50)
    begin
        if rising_edge(clk50) then
            fault_meta <= phy_fault;
            fault_sync <= fault_meta;
            if board_reset = '1' or (fault_sync = '1' and release50(1) = '1') then
                hold_count <= (others => '0');
            elsif hold_count < 16 then
                hold_count <= hold_count + 1;
            end if;
        end if;
    end process;

    process(clk50, clear_request)
    begin
        if clear_request = '1' then
            release50 <= "00";
            peer24 <= "00";
        elsif rising_edge(clk50) then
            release50 <= release50(0) & '1';
            peer24 <= peer24(0) & release24(1);
        end if;
    end process;

    process(clk24, clear_request)
    begin
        if clear_request = '1' then
            release24 <= "00";
            peer50 <= "00";
        elsif rising_edge(clk24) then
            release24 <= release24(0) & '1';
            peer50 <= peer50(0) & release50(1);
        end if;
    end process;
end architecture;
