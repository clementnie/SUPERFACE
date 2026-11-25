#!/bin/sh
# Quartus rewrites reports, programming files and project databases.
set -eu
if [ "$#" -gt 2 ]; then
    echo "Usage: $0 [NEW_BUILD_DIRECTORY [synthetic|phy|wire]]" >&2
    exit 2
fi
source=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -gt 0 ]; then
    mkdir -- "$1"
    build=$(CDPATH='' cd -- "$1" && pwd)
else
    build=$(mktemp -d)
fi
printf 'Quartus build directory %s\n' "$build"
for suffix in bdf bsf qpf qsf qip sdc vhd tdf inc mif; do
    cp -- "$source"/*."$suffix" "$build/"
done
cd "$build"
case "${2:-board}" in
    board) ;;
    synthetic)
        cat >> LAB8.qsf <<'QSF'
set_global_assignment -name EDA_SIMULATION_TOOL "ModelSim-Altera (Verilog)"
set_global_assignment -name EDA_OUTPUT_DATA_FORMAT "VERILOG HDL" -section_id eda_simulation
set_global_assignment -name EDA_GENERATE_FUNCTIONAL_NETLIST ON -section_id eda_simulation
QSF
        python3 "$source/tools/verify_phase5.py" phase5_scenario.svh \
            --synthetic --patch-synthetic-bdf LAB8.bdf
        touch SYNTHETIC_SIMULATION_ONLY
        ;;
    phy|wire)
        cat > LAB8.qsf <<'QSF'
set_global_assignment -name FAMILY "Cyclone II"
set_global_assignment -name DEVICE EP2C20F484C7
set_global_assignment -name TOP_LEVEL_ENTITY UART_PHY
set_global_assignment -name BDF_FILE UART_PHY.bdf
set_global_assignment -name VHDL_FILE Uart_Reset.vhd
set_global_assignment -name VHDL_FILE Uart_Rx.vhd
set_global_assignment -name VHDL_FILE Uart_Tx.vhd
set_global_assignment -name VHDL_FILE Uart_Status.vhd
set_global_assignment -name QIP_FILE Uart_Fifo.qip
set_global_assignment -name SDC_FILE LAB8.sdc
QSF
        cat > LAB8.sdc <<'SDC'
create_clock -name board50 -period 20.000 [get_ports clk50]
create_clock -name board24 -period 41.666 [get_ports clk24]
set_clock_groups -asynchronous -group {board50} -group {board24}
set_false_path -from [get_ports serial_rx] -to [get_registers {*Uart_Rx*|rx_meta}]
SDC
        if [ "$2" = wire ]; then
            sed -i 's/TOP_LEVEL_ENTITY UART_PHY/TOP_LEVEL_ENTITY Phase5_Wire_Test/' LAB8.qsf
            cat >> LAB8.qsf <<'QSF'
set_global_assignment -name BDF_FILE Phase5_Wire_Test.bdf
set_global_assignment -name BDF_FILE Display_Reset.bdf
set_global_assignment -name VHDL_FILE Uart_Wire_Test.vhd
set_location_assignment PIN_L1 -to CLOCK_50
set_location_assignment PIN_B12 -to CLOCK_24
set_location_assignment PIN_T21 -to KEY3_N
set_location_assignment PIN_B13 -to UART_RX
set_location_assignment PIN_A14 -to UART_TX
set_instance_assignment -name IO_STANDARD LVTTL -to CLOCK_50
set_instance_assignment -name IO_STANDARD LVTTL -to CLOCK_24
set_instance_assignment -name IO_STANDARD LVTTL -to KEY3_N
set_instance_assignment -name IO_STANDARD LVTTL -to UART_RX
set_instance_assignment -name IO_STANDARD LVTTL -to UART_TX
set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to UART_RX
QSF
            sed -e 's/{CLOCK_24\[0\]}/CLOCK_24/g' -e 's/{KEY\[3\]}/KEY3_N/g' "$source/LAB8.sdc" > LAB8.sdc
            touch WIRE_RATE_BENCH_ONLY
        else
            touch PHY_SIMULATION_ONLY
        fi
        ;;
    *) exit 2 ;;
esac
export QUARTUS_64BIT=1
quartus_sh --64bit --flow compile LAB8
