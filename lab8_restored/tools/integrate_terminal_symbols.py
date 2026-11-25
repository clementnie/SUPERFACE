#!/usr/bin/env python3
"""Connect terminal glyph classes and the existing SRAM slot to scanline masks."""
from pathlib import Path

import phase5_schematics as schematic

root = Path(__file__).resolve().parents[1]
builder = root / "Scanline_Builder.bdf"
sheet = builder.read_text()
wide_symbol = root / "Wide_Render.bsf"
(root / "Cell_Classify.bsf").write_text(wide_symbol.read_text().replace('"Wide_Render"', '"Cell_Classify"'))

if '"Font_Row_Select"' not in sheet:
    sheet = sheet.replace('"Wide_Render"', '"Cell_Classify"')
    sheet = sheet.replace('"Need_Chinese_Bitmap"', '"Need_Wide_Bitmap"')
    sheet = sheet.replace('"Cell_Q[13..0],Chinese_Row[3..0]"', '"Cell_Q[13..0],Font_Row[3..0]"')
    sheet = sheet.replace('"Left_Mask[7..0]"', '"Base_Final_Left[7..0]"')
    sheet = sheet.replace('"Right_Mask[7..0]"', '"Base_Final_Right[7..0]"')
    sheet += schematic.symbol("Font_Row_Select", "SRAM_Symbols_And_Missing_Glyphs", 900, 9770, {
        "glyph": "Cell_Q[15..0]", "local_y": "Line_Tag[3..0]", "wide_row": "Chinese_Row[3..0]",
        "font_ok": "Font_OK", "need_wide": "Need_Wide_Bitmap", "wide_pair": "Wide_Q",
        "sram_bits": "Chinese_Q[7..0]", "base_left": "Base_Final_Left[7..0]",
        "base_right": "Base_Final_Right[7..0]", "font_row": "Font_Row[3..0]",
        "need_sram": "Need_Chinese_Bitmap", "left_mask": "Left_Mask[7..0]",
        "right_mask": "Right_Mask[7..0]",
    })
    builder.write_text(sheet)
(root / "Font_Row_Select.bsf").write_text(
    '(header "symbol" (version "1.1"))\n' + schematic.symbol("Font_Row_Select", "inst", 0, 0)
)
for project in root.glob("*.qsf"):
    settings = project.read_bytes()
    if b"Scanline_Builder.bdf" in settings and b"Font_Row_Select.vhd" not in settings:
        project.write_bytes(settings + b"\nset_global_assignment -name VHDL_FILE Cell_Classify.vhd\n"
                            b"set_global_assignment -name VHDL_FILE Font_Row_Select.vhd\n")
