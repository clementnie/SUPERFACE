#!/bin/sh
printf '\033[2J\033[HSUPERFACE - PUNCTUATION ACCEPTANCE\n\n'
printf '你好，世界！\nSUPERFACE 中文终端\nLinux + FPGA = 中文终端\n\n'
printf '常用标点：，。！？；：（）【】《》「」『』、\n'
printf '全角符号：ＡＢＣ１２３％＋－＝＠＃＆＊／＼\n\n'
printf '\033[31;44m红色中文，标点！【测试】\033[0m\n'
printf '\033[92;45m绿色中文。（全角）《符号》\033[0m\n\n'
printf '我们度过的每个平凡的日常，也许就是连续发生的奇迹。\n'
printf '\033[18;79H，。\033[22;1HWide punctuation at column 79 wraps above.\n'
printf 'Unsupported: 😀 𠀀 (fallback remains expected)\n'
printf '\033[?25h'
sleep 1800
