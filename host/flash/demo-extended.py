#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Show the extended font on the authenticated VGA console."""
import sys

rows = (
    ("Suits", "[\u2660][\u2661][\u2662][\u2663][\u2664][\u2665][\u2666][\u2667]"),
    ("Chess", "\u2654\u2655\u2656\u2657\u2658\u2659 \u265a\u265b\u265c\u265d\u265e\u265f"),
    ("Dice", "\u2680 \u2681 \u2682 \u2683 \u2684 \u2685"),
    ("Music", "\u2669 \u266a \u266b \u266c \u266d \u266e \u266f"),
    ("Shapes", "\u2605 \u2606 \u2713 \u2717 \u25cf \u25cb \u25b2 \u25a0 \u25c6"),
    ("Arrows and keys", "\u2190 \u2191 \u2192 \u2193 \u21d4 \u27f6 \u2325 \u2328 \u2318"),
    ("Box, blocks, Braille", "\u250c\u2500\u252c\u2500\u2510 \u2581\u2584\u2588\u2591\u2592\u2593 \u2801\u2812\u28ff"),
    ("Math", "\u2200 \u2203 \u2208 \u222b \u2211 \u03c0 \u221a \u211d \u27e8x\u27e9 \u210f x\u00b2 a\u2083"),
    ("Currency", "\u00a2 \u00a3 \u00a5 \u20ac \u20b9 \u20bd \u20a9"),
    ("Latin and IPA", "\u010c \u0142 \u01b5 \u011f \u0259 \u0283 \u0292 \u014b"),
    ("Greek and Cyrillic", "\u0391\u03b2\u03b3\u03b4\u03a9 \u041f\u0440\u0438\u0432\u0435\u0442"),
    ("Kana and Bopomofo", "\u304b\u306a \u30ab\u30ca \u30fb \u3105\u3106\u3107"),
    ("Simplified Chinese", "\u7b80\u4f53\u4e2d\u6587\uff1a\u9f99\u9a6c\u7cbe\u795e"),
    ("Traditional Chinese", "\u7e41\u9ad4\u4e2d\u6587\uff1a\u9f8d\u99ac\u7cbe\u795e"),
    ("Width and last ID", "[\u2660][\u4e2d][\u794c][A]"),
    ("Missing 1 / 2 cells", "[\u05d0][\U0001f600]"),
)
sys.stdout.reconfigure(encoding="utf-8")
print("\x1b[0m\x1b[2J\x1b[HSUPERFACE v1.2.0 extended pixel font\n")
for label, sample in rows:
    print(f"{label:<22} {sample}")
