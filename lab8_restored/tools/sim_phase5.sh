#!/bin/sh
# Simulate the fitted Cyclone II board netlist or the isolated UART PHY.
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 FIT_DIRECTORY QUARTUS_ROOT [board|synthetic|phy]" >&2
    exit 2
fi
tools=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
build=$(CDPATH='' cd -- "$1" && pwd)
cells=$2/eda/sim_lib/cycloneii_atoms.v
mode=${3:-board}
export QUARTUS_64BIT=1
cd "$build"
"$2/bin/quartus_eda" --64bit LAB8 --simulation=on --tool=modelsim \
    --format=verilog --functional=on --output_directory=phase5_eda
case "$mode" in
    board) python3 "$tools/verify_phase5.py" phase5_scenario.svh ;;
    synthetic) python3 "$tools/verify_phase5.py" phase5_scenario.svh --synthetic ;;
    phy) ;;
    *) exit 2 ;;
esac
if [ "$mode" = phy ]; then
    top=phase5_phy_tb
else
    top=phase5_uart_tb
fi
if [ "${SIMULATOR:-iverilog}" = verilator ]; then
    python3 "$tools/phase5_verilator_model.py" phase5_eda/LAB8.vo "$cells" \
        phase5_eda/LAB8_digital.v phase5_eda/phase5_cells.v
    verilator --binary --timing -j 4 -Wno-fatal --top-module "$top" \
        -I"$build" --Mdir phase5_obj "$tools/$top.sv" phase5_eda/LAB8_digital.v phase5_eda/phase5_cells.v
    "phase5_obj/V$top"
else
    iverilog -g2012 -s "$top" -I "$build" -o phase5_sim "$tools/$top.sv" phase5_eda/LAB8.vo "$cells"
    vvp phase5_sim
fi
