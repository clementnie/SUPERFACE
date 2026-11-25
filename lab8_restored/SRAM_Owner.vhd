library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
-- Exclusive boot writer/readback and runtime read-only bus mux.
entity SRAM_Owner is
    port (clk, reset, runtime_owner, request, write_word : in std_logic;
          address, render_address : in std_logic_vector(17 downto 0);
          wdata : in std_logic_vector(15 downto 0);
          render_ce_n, render_oe_n, render_we_n, render_lb_n, render_ub_n : in std_logic;
          done : out std_logic;
          rdata : out std_logic_vector(15 downto 0);
          sram_addr : out std_logic_vector(17 downto 0);
          ce_n, oe_n, we_n, lb_n, ub_n : out std_logic;
          sram_dq : inout std_logic_vector(15 downto 0));
end entity;
architecture rtl of SRAM_Owner is
    type state_t is (idle, setup_write, pulse_write, hold_write, reading, complete);
    signal state: state_t := idle;
    signal ticks: natural range 0 to 7 := 0;
    signal addr: std_logic_vector(17 downto 0) := (others=>'0');
    signal data: std_logic_vector(15 downto 0) := (others=>'0');
    signal writing, selected: std_logic;
begin
    writing<='1' when (state=setup_write or state=pulse_write or state=hold_write) and runtime_owner='0' and reset='0' else '0';
    selected<='1' when (writing='1' or state=reading) and runtime_owner='0' and reset='0' else '0';
    sram_dq<=data when writing='1' else (others=>'Z');
    sram_addr<=render_address when runtime_owner='1' else addr;
    ce_n<='1' when reset='1' else render_ce_n when runtime_owner='1' else not selected;
    oe_n<='1' when reset='1' else render_oe_n when runtime_owner='1' else '0' when state=reading else '1';
    -- Runtime port is read-only regardless of a faulty renderer WE signal.
    we_n<='0' when state=pulse_write and runtime_owner='0' and reset='0' else '1';
    lb_n<='1' when reset='1' else render_lb_n when runtime_owner='1' else not selected;
    ub_n<='1' when reset='1' else render_ub_n when runtime_owner='1' else not selected;
    process(clk) begin
        if rising_edge(clk) then
            done<='0';
            if reset='1' or runtime_owner='1' then state<=idle; ticks<=0;
            else case state is
                when idle => if request='1' then
                    addr<=address; data<=wdata; ticks<=0;
                    if write_word='1' then state<=setup_write; else state<=reading; end if;
                end if;
                when setup_write =>
                    if ticks=1 then ticks<=0; state<=pulse_write; else ticks<=ticks+1; end if;
                when pulse_write =>
                    if ticks=3 then ticks<=0; state<=hold_write; else ticks<=ticks+1; end if;
                when hold_write =>
                    if ticks=1 then state<=complete; else ticks<=ticks+1; end if;
                when reading =>
                    if ticks=7 then rdata<=sram_dq; state<=complete; else ticks<=ticks+1; end if;
                when complete => done<='1'; state<=idle;
            end case; end if;
        end if;
    end process;
end;
