# Oscillators on the Cyclone II DE1, in nanoseconds.
create_clock -name board50 -period 20.000 [get_ports CLOCK_50]
create_clock -name board24 -period 41.666 [get_ports {CLOCK_24[0]}]


# Existing shift/sound clock is board24 / 2^22 (about 174.76 ms).
# TimeQuest 13.0 stores periods in a signed picosecond range (up to 2.147 ms).
# Use a conservative / 2^15 proxy here. Every real divider edge belongs
# to this aligned subset of board24 edges, with more time between real edges.
set legacy_slow [get_registers {*Clock_Divider*|*safe_q[21]}]
if {[get_collection_size $legacy_slow] == 1} {
    create_generated_clock -name legacy_shift -source [get_ports {CLOCK_24[0]}] -divide_by 32768 $legacy_slow
}

# The oscillators have independent phases.
set_clock_groups -asynchronous -group {board50} -group {board24 legacy_shift}

# KEY3 uses the 50 MHz release synchronizer. Only the first stage sees the raw pin.
set reset_first [get_registers {*Display_Reset*|*U_Release_Meta*|dffs*}]
if {[get_collection_size $reset_first] > 0} {
    set_false_path -from [get_ports {KEY[3]}] -to $reset_first
}

# The incoming wire is asynchronous; time the second synchronizer stage normally.
set uart_rx_meta [get_registers {*Uart_Rx*|rx_meta}]
if {[get_collection_size $uart_rx_meta] > 0} {
    set_false_path -from [get_ports UART_RX] -to $uart_rx_meta
}


# Quartus II 13.0 SP1 DCFIFO Gray-pointer launch nets. Check every load
# (including the first synchronizer's feeder LUT when the fitter inserts one).
# 10 ns is half the shortest source-clock period. This check does not use
# the setup/hold clock relationships or the FIFO's embedded false paths.
foreach fifo {RX_CDC_16x9 TX_CDC_16x9} {
    foreach source {{rdptr_g[*]} {delayed_wrptr_g[*]}} {
        set pointers [get_nets "Terminal_UART|${fifo}|storage|auto_generated|${source}"]
        if {[get_collection_size $pointers] != 5} {
            error "Expected five Gray-pointer launch nets for ${fifo}/${source}"
        }
        set_net_delay -max -from $pointers 10.000
    }
}

# Only raw pin to first stage is asynchronous; stage two remains timed.
set_false_path -from [get_ports PS2_CLK] -to [get_registers {*PS2_Receiver*|clock_meta}]
set_false_path -from [get_ports PS2_DAT] -to [get_registers {*PS2_Receiver*|data_meta}]

# External asynchronous memory budgets, 50 MHz system. These constrain FPGA
# routing at the pins independently of the multicycle external bus transactions.
# NOR: 20ns output + 70ns device + 20ns input < 400ns read window.
# SRAM: 20ns output + 10ns device + 20ns input < 160ns read window.
# Write pulse 80ns, address/data setup and hold 40ns each.
set_max_delay 20.000 -to [get_ports {FL_ADDR[*] FL_CE_N FL_OE_N FL_WE_N FL_RST_N}]
set_max_delay 20.000 -from [get_ports {FL_DQ[*]}]
set_max_delay 20.000 -to [get_ports {SRAM_ADDR[*] SRAM_CE_N SRAM_OE_N SRAM_WE_N SRAM_LB_N SRAM_UB_N SRAM_DQ[*]}]
set_max_delay 20.000 -from [get_ports {SRAM_DQ[*]}]

# The pixel clock is 50 MHz * 13 / 10 from Cyclone II ALTPLL.
derive_pll_clocks
derive_clock_uncertainty

# Only synchronizer inputs are exempt from synchronous setup/hold.
# Unrelated video/system crossings remain visible to TimeQuest.
foreach name {{*U_Row_Queue*|wr_meta[*]} {*U_Row_Queue*|rd_meta[*]} \
              {*U_Row_Queue*|blank_meta} {*Pixel_Sync*|status_meta[*]}} {
    set ends [get_registers $name]
    if {[get_collection_size $ends] > 0} {
        set_false_path -to $ends
    }
}
# Constrain all Gray-bit routes to less than one period of either launch
# clock. This also bounds inter-bit skew without cutting stage two timing.
foreach name {{*U_Row_Queue*|wr_gray[*]} {*U_Row_Queue*|rd_gray[*]}} {
    set gray_nets [get_nets $name]
    if {[get_collection_size $gray_nets] > 0} {
        set_net_delay -max -from $gray_nets 10.000
    }
}

# Digital VGA outputs all originate in the pixel domain.
set_max_delay 10.000 -to [get_ports {VGA_R[*] VGA_G[*] VGA_B[*] VGA_HS VGA_VS}]

# These two flops asynchronously assert reset and synchronously shift out
# its release. Their asynchronous control is intentionally unclocked.
set pixel_reset_sync [get_registers {*Pixel_Sync*|reset_meta *Pixel_Sync*|reset_sync}]
if {[get_collection_size $pixel_reset_sync] == 2} {
    set_false_path -from [get_clocks board50] -to $pixel_reset_sync
}
