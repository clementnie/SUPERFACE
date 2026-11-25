#!/bin/sh
# Run at the authenticated physical terminal after successful Chinese negotiation.
# No privileged commands or configuration changes.
printf '\033[2J\033[H'
printf 'SUPERFACE bilingual acceptance: 80 x 30, ANSI16\n\n'
printf '你好，世界！\nSUPERFACE 中文终端\nLinux + FPGA = 中文终端\n'
printf '我们度过的每个平凡的日常，也许就是连续发生的奇迹。\n\n'
printf '\033[31;44m红色中文 / red on blue\033[0m\n'
printf '\033[92;45m绿色中文 / bright green on magenta\033[0m\n'
printf '\033[10;79H中文边界\033[12;1H'
printf 'Wide update: 中文'; sleep 1
printf '\rWide update: 中A\033[K\n'
printf 'Unsupported: 😀 𠀀 (expected fallback)\n'
printf 'Unsupported punctuation is also fallback under the pinned Han-only map.\n'
printf '\033[29;79H中文滚动\n第二行\n第三行\n'
printf '\033[?25h'
# Retain all primary examples after the scrolling demonstration.
printf '\033[2J\033[HSUPERFACE - PHYSICAL CHINESE ACCEPTANCE\n\n'
printf '你好，世界！\nSUPERFACE 中文终端\nLinux + FPGA = 中文终端\n\n'
printf '我们度过的每个平凡的日常，也许就是连续发生的奇迹。\n\n'
printf '\033[31;44m红色中文 / red on blue\033[0m\n'
printf '\033[92;45m绿色中文 / bright green on magenta\033[0m\n\n'
printf 'Unsupported punctuation/emoji use the documented fallback.\n'
printf '\033[18;79H中文边界\033[22;1HWide replacement result: 中A\033[K\n'
printf '\033[?25h'
