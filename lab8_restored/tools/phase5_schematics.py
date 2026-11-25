#!/usr/bin/env python3
"""Generate the Phase 5 BDF hierarchy and module symbols from VHDL ports."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HEADER = '(header "graphic" (version "1.4"))\n'
FONT = '(font "Arial" (font_size 8))'
PORTS = {}


def bits(name, width):
    return name if width == 1 else f"{name}[{width - 1}..0]"


def module_ports(name):
    if name not in PORTS:
        entity = (ROOT / f"{name}.vhd").read_text().split("end entity;")[0]
        declarations = re.search(r"\bport\s*\((.*)\);", entity, re.S)[1]
        ports = []
        for declaration in declarations.split(";"):
            match = re.fullmatch(
                r"\s*([\w,\s]+):\s*(in|out)\s+std_logic"
                r"(?:_vector\((\d+) downto 0\))?\s*", declaration
            )
            names, direction, high = match.groups()
            ports.extend((p.strip(), direction, int(high) + 1 if high else 1)
                         for p in names.split(","))
        PORTS[name] = ports
    return PORTS[name]


def label(value, x, y):
    return f'(text "{value}" (rect {x} {y} {x+8*len(value)} {y+13}){FONT})'


def wire(name, width, x1, x2, y):
    return (f'(connector {label(name, min(x1,x2)+4, y-15)}'
            f' (pt {x1} {y})(pt {x2} {y})'
            f'{" (bus)" if width > 1 else ""})\n')


def symbol(name, instance, x, y, nets=None):
    width = 336
    ports = module_ports(name)
    height = 54 + 24 * max(sum(d == k for _, d, _ in ports) for k in ("in", "out"))
    text = (f'(symbol (rect {x} {y} {x+width} {y+height})\n'
            f' {label(name,16,0)} {label(instance,16,height-15)}\n')
    links = ""
    levels = {"in": 36, "out": 36}
    for port, direction, size in ports:
        left = direction == "in"
        dy = levels[direction]
        levels[direction] += 24
        dx = 0 if left else width
        name_text = bits(port, size)
        tag = label(name_text, 21 if left else width-21-8*len(name_text), dy-12)
        text += (f' (port (pt {dx} {dy}) ({"input" if left else "output"}) '
                 f'{tag} {tag} (line (pt {dx} {dy})(pt {16 if left else width-16} {dy})'
                 f'{" (line_width 3)" if size > 1 else ""}))\n')
        if nets is not None and port in nets:
            links += wire(nets[port], size, x+dx, x+dx+(-240 if left else 240), y+dy)
    return text + f" (drawing (rectangle (rect 16 16 {width-16} {height-16})))\n)\n" + links


def pin(name, direction, size, x, y):
    left = direction == "in"
    template = (
        '(pin (input) (rect {x} {y} {right} {bottom}) '
        '(text "INPUT" (rect 133 0 162 10)(font "Arial" (font_size 6))) '
        '(text "{name}" (rect 9 0 140 11)(font "Arial" )) '
        '(pt 168 8) (drawing (line (pt 92 12)(pt 117 12)) '
        '(line (pt 92 4)(pt 117 4)) (line (pt 121 8)(pt 168 8)) '
        '(line (pt 92 12)(pt 92 4)) (line (pt 117 4)(pt 121 8)) '
        '(line (pt 117 12)(pt 121 8))) '
        '(text "VCC" (rect 136 7 157 17)(font "Arial" (font_size 6))))\n'
        if left else
        '(pin (output) (rect {x} {y} {right} {bottom}) '
        '(text "OUTPUT" (rect 1 0 41 10)(font "Arial" (font_size 6))) '
        '(text "{name}" (rect 90 0 220 11)(font "Arial" )) '
        '(pt 0 8) (drawing (line (pt 0 8)(pt 52 8)) '
        '(line (pt 52 4)(pt 78 4)) (line (pt 52 12)(pt 78 12)) '
        '(line (pt 52 12)(pt 52 4)) (line (pt 78 4)(pt 82 8)) '
        '(line (pt 82 8)(pt 78 12)) (line (pt 78 12)(pt 78 4))))\n'
    )
    point = x + 168 if left else x
    return (template.format(x=x, y=y, right=x + (168 if left else 176), bottom=y+16, name=name)
            + wire(name, size, point, point+(224 if left else -224), y+8))


def sheet(name, ports, blocks, notes):
    PORTS[name] = ports
    data = HEADER + "".join(label(note, 30, 20+i*20) + "\n" for i, note in enumerate(notes))
    positions = {"in": 100, "out": 100}
    for port, direction, size in ports:
        data += pin(bits(port, size), direction, size, -340 if direction == "in" else 2352,
                    positions[direction])
        positions[direction] += 24
    for kind, instance, x, y, nets in blocks:
        by_port = {p: (d, n) for p, d, n in module_ports(kind)}
        if set(nets) - by_port.keys():
            raise ValueError((kind, set(nets) - by_port.keys()))
        data += symbol(kind, instance, x, y, nets)
    (ROOT / f"{name}.bdf").write_text(data)


def generate():
    phy_ports = [
        ("clk50","in",1), ("clk24","in",1), ("board_reset","in",1),
        ("serial_rx","in",1), ("rx_pop","in",1), ("tx_push","in",1),
        ("tx_token","in",9), ("framing_error","in",1),
        ("serial_tx","out",1), ("rx_empty","out",1), ("rx_token","out",9),
        ("tx_full","out",1), ("frame_done","out",1), ("reset50","out",1),
        ("run50","out",1), ("overflow_seen","out",1), ("starvation_seen","out",1), ("framing_seen","out",1)
    ]
    sheet("UART_PHY", phy_ports, [
        ("Uart_Reset", "Clock_Reset", 560, 96, dict(clk50="clk50", clk24="clk24",
            board_reset="board_reset", phy_fault="Phy_Fault", fifo_clear="Fifo_Clear",
            reset50="reset50", reset24="Reset24", run50="run50", run24="Run24")),
        ("Uart_Rx", "Receiver_8N1", 560, 368, dict(clk24="clk24", reset24="Reset24",
            run24="Run24", serial_rx="serial_rx", fifo_full="Rx_Full",
            fifo_data="Rx_Write_Token[8..0]", fifo_write="Rx_Write", overflow="Rx_Overflow")),
        ("Uart_Tx", "Transmitter_8N1", 560, 600, dict(clk24="clk24", reset24="Reset24",
            run24="Run24", fifo_empty="Tx_Empty", fifo_used="Tx_Fill[4..0]",
            fifo_data="Tx_Read_Token[8..0]", fifo_read="Tx_Read", serial_tx="serial_tx",
            done_toggle="Tx_Done_Toggle", starved="Tx_Starved")),
        ("Uart_Fifo", "RX_CDC_16x9", 1440, 368, dict(aclr="Fifo_Clear", wrclk="clk24",
            rdclk="clk50", wrreq="Rx_Write", rdreq="rx_pop", data="Rx_Write_Token[8..0]",
            q="rx_token[8..0]", wrfull="Rx_Full", rdempty="rx_empty")),
        ("Uart_Fifo", "TX_CDC_16x9", 1440, 600, dict(aclr="Fifo_Clear", wrclk="clk50",
            rdclk="clk24", wrreq="tx_push", rdreq="Tx_Read", data="tx_token[8..0]",
            q="Tx_Read_Token[8..0]", wrfull="tx_full", rdempty="Tx_Empty", rdusedw="Tx_Fill[4..0]")),
        ("Uart_Status", "Wire_Status", 1440, 96, dict(clk50="clk50", board_reset="board_reset",
            reset50="reset50", run50="run50", overflow="Rx_Overflow", starved="Tx_Starved",
            done_toggle="Tx_Done_Toggle", frame_error="framing_error", phy_fault="Phy_Fault",
            frame_done="frame_done", overflow_seen="overflow_seen", starvation_seen="starvation_seen", framing_seen="framing_seen"))
    ], ["24 MHz UART PHY and 50 MHz clock-domain crossings",
        "RX token bit 8 marks a bad stop. TX token bit 8 marks the closing delimiter."])

    link_ports = [
        ("clk","in",1), ("reset","in",1), ("run","in",1), ("rx_empty","in",1),
        ("rx_token","in",9), ("tx_full","in",1), ("frame_done","in",1),
        ("font_ready","in",1), ("font_status","in",3), ("font_count","in",15),
        ("font_mapping","in",128), ("source_valid","in",1), ("source_error","in",1),
        ("source_byte","in",8), ("idle_qualified","in",1), ("display_ready","in",1),
        ("push_ready","in",1), ("done","in",1), ("result","in",3),
        ("rx_pop","out",1), ("framing_error","out",1), ("tx_token","out",9),
        ("tx_push","out",1), ("chinese","out",1), ("linked","out",1),
        ("invalidate","out",1), ("cmd_valid","out",1), ("push","out",1),
        ("cursor_on","out",1), ("op","out",3), ("row","out",5),
        ("col","out",7), ("count","out",7), ("push_cell","out",24)
    ]
    shared = dict(clk="clk", reset="reset")
    receive = dict(kind="Rx_Kind[7..0]", length="Rx_Length[7..0]",
                   session_id="Rx_Session[63..0]", seq="Rx_Seq[31..0]")
    scratch = dict(payload_busy="Scratch_Busy", payload_read="Scratch_Read",
                   payload_address="Scratch_Address[7..0]", payload_data="Scratch_Data[7..0]")
    tx = dict(kind="Tx_Kind[7..0]", length="Tx_Length[7..0]", session_id="Tx_Session[63..0]",
              seq="Tx_Seq[31..0]", payload="Tx_Payload[199..0]", start="Tx_Start", ready="Tx_Ready")
    events = dict(event_valid="Event_Valid", event_reset="Event_Reset",
                  event_byte="Event_Byte[7..0]", reset_acked="Reset_Acked", take_event="Take_Event")
    sheet("UART_Link", link_ports, [
        ("Frame_Rx", "Decode_And_Scratch", 560, 96, dict(**shared, **receive, **scratch,
            run="run", fifo_empty="rx_empty", fifo_data="rx_token[8..0]", fifo_read="rx_pop",
            framing_error="framing_error", valid="Rx_Valid", prefix="Rx_Prefix[143..0]",
            request_crc="Rx_CRC[15..0]")),
        ("Frame_Tx", "Encode_And_Drain", 560, 484, dict(**shared, **tx,
            run="run", fifo_full="tx_full", frame_done="frame_done", fifo_data="tx_token[8..0]",
            fifo_write="tx_push")),
        ("Key_Queue", "Set2_Queue", 560, 812, dict(**shared, **events, active="Key_Active",
            source_valid="source_valid", source_error="source_error", idle_qualified="idle_qualified",
            source_byte="source_byte[7..0]")),
        ("Uart_Session", "Reliable_Transactions", 1440, 96, dict(**shared, **events,
            font_ready="font_ready", font_status="font_status[2..0]", font_count="font_count[14..0]",
            font_mapping="font_mapping[127..0]", rx_valid="Rx_Valid",
            rx_kind=receive["kind"], rx_length=receive["length"], rx_session=receive["session_id"],
            rx_seq=receive["seq"], rx_prefix="Rx_Prefix[143..0]", rx_crc="Rx_CRC[15..0]",
            **{f"tx_{k}": v for k, v in tx.items() if k != "session_id"},
            tx_session=tx["session_id"], tx_done="frame_done", dispatch="Dispatch",
            invalidate="invalidate", chinese="chinese", linked="linked", key_active="Key_Active",
            key_idle="Key_Idle", display_complete="Adapter_Complete", display_status="Adapter_Status[2..0]")),
        ("Display_Adapter", "Phase3_Command_Adapter", 1440, 720, dict(**shared, **scratch,
            cancel="invalidate", dispatch="Dispatch", key_idle="Key_Idle", kind=receive["kind"],
            length=receive["length"], fields="Rx_Prefix[23..0]", ready="display_ready",
            push_ready="push_ready", done="done", result="result[2..0]", cmd_valid="cmd_valid",
            push="push", cursor_on="cursor_on", op="op[2..0]", row="row[4..0]",
            col="col[6..0]", count="count[6..0]", push_cell="push_cell[23..0]",
            complete="Adapter_Complete", status="Adapter_Status[2..0]"))
    ], ["50 MHz SUPERFACE v1 link", "Receive scratch is released after staging. Display completion drives ACK."])
    wire_test_ports = [
        ("CLOCK_50","in",1), ("CLOCK_24","in",1), ("KEY3_N","in",1),
        ("UART_RX","in",1), ("UART_TX","out",1)
    ]
    PORTS["Display_Reset"] = [("Clk","in",1), ("KEY3_N","in",1), ("Reset","out",1)]
    sheet("Phase5_Wire_Test", wire_test_ports, [
        ("Display_Reset", "Bench_Reset", 560, 96, dict(Clk="CLOCK_50", KEY3_N="KEY3_N",
            Reset="Board_Reset")),
        ("UART_PHY", "Terminal_UART", 560, 280, dict(clk50="CLOCK_50", clk24="CLOCK_24",
            board_reset="Board_Reset", serial_rx="UART_RX", serial_tx="UART_TX",
            rx_pop="Rx_Pop", rx_empty="Rx_Empty", rx_token="Rx_Token[8..0]",
            tx_push="Tx_Push", tx_full="Tx_Full", tx_token="Tx_Token[8..0]",
            frame_done="Frame_Done", reset50="Link_Reset", run50="Link_Run",
            framing_error="Framing_Error")),
        ("Uart_Wire_Test", "Sustained_Duplex", 1440, 280, dict(clk="CLOCK_50", reset="Link_Reset",
            run="Link_Run", rx_pop="Rx_Pop", rx_empty="Rx_Empty", rx_token="Rx_Token[8..0]",
            tx_push="Tx_Push", tx_full="Tx_Full", tx_token="Tx_Token[8..0]",
            frame_done="Frame_Done", framing_error="Framing_Error"))
    ], ["Phase 5 bench wire-rate image",
        "Independent streams through the release PHY. Program the board image for terminal use."])
    del PORTS["Display_Reset"]
    for name in (*PORTS, "Phase5_Font", "Uart_Wire_Test"):
        (ROOT / f"{name}.bsf").write_text('(header "symbol" (version "1.1"))\n'
                                        + symbol(name, "inst", 0, 0))


if __name__ == "__main__":
    generate()
