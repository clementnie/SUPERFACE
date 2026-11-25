#!/usr/bin/env python3
"""Prepare zero-delay copies of the fitted netlist and cell models for Verilator."""
from pathlib import Path
import re
import sys

# LUT and carry truth tables use the fitted primitive's mask and input ordering.
LOGIC = """
module cycloneii_lcell_comb #(parameter lut_mask = 16'hffff,
    parameter sum_lutc_input = "datac", parameter lpm_type = "cycloneii_lcell_comb")
    (input dataa, datab, datac, datad, cin, output combout, cout);
    assign combout = lut_mask[{datad, (sum_lutc_input == "cin" ? cin : datac), datab, dataa}];
    assign cout = lut_mask[{1'b0, cin, datab, dataa}];
endmodule

module cycloneii_lcell_ff #(parameter x_on_violation = "on",
    parameter lpm_type = "cycloneii_lcell_ff")
    (input datain, clk, aclr, sclr, sload, sdata, ena, devclrn, devpor,
     output reg regout = 1'b0);
    always @(posedge clk or posedge aclr or negedge devclrn or negedge devpor)
        if (aclr || !devclrn || !devpor) regout <= 1'b0;
        else if (ena)
            regout <= sclr ? 1'b0 : sload ? sdata : datain;
endmodule
"""


def pad(match):
    ports, parameters = match.group("ports", "parameters")

    def port(name):
        return re.search(rf"\.{name}\(([^)]*)\)", ports)[1]

    def parameter(name):
        return re.search(rf'\.{name} = "([^"]+)"', parameters)[1]

    for name in ("input", "output", "oe"):
        if parameter(f"{name}_register_mode") != "none":
            raise ValueError("Unexpected registered I/O primitive")
    mode = parameter("operation_mode")
    if mode == "input":
        combout = port("combout")
        return f'assign {combout} = {port("padio")} ;' if combout.strip() else ""
    if mode == "output":
        if port("oe") != "vcc":
            raise ValueError("Unexpected output enable")
        return f'assign {port("padio")} = {port("datain")} ;'
    raise ValueError(f"Unsupported I/O mode {mode}")


def main(paths):
    netlist, vendor, out_netlist, out_models = map(Path, paths)
    source = netlist.read_text()
    # Verilator otherwise treats the input-side inout pads as sources at the
    # board boundary. Keep this transformation in copies used for simulation.
    pattern = (r"cycloneii_io \\[^\n]+\(\n(?P<ports>.*?)\);\n"
               r"// synopsys translate_off\n(?P<parameters>.*?)// synopsys translate_on")
    flat, count = re.subn(pattern, pad, source, flags=re.S)
    if count != source.count("\ncycloneii_io "):
        raise ValueError("A fitted I/O instance was missed")
    out_netlist.write_text(flat)
    cells = vendor.read_text()
    for name in ("cycloneii_lcell_comb", "cycloneii_lcell_ff"):
        cells, count = re.subn(rf"^module {name}\b.*?^endmodule", "", cells, flags=re.S | re.M)
        if count != 1:
            raise ValueError(f"Expected one vendor primitive {name}")
    out_models.write_text(cells + LOGIC)


if __name__ == "__main__":
    main(sys.argv[1:])
