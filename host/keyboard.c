#include "superface.h"

#include <string.h>

static const char lower[256] = {
    [0x0e] = '`', [0x16] = '1', [0x1e] = '2', [0x26] = '3', [0x25] = '4',
    [0x2e] = '5', [0x36] = '6', [0x3d] = '7', [0x3e] = '8', [0x46] = '9',
    [0x45] = '0', [0x4e] = '-', [0x55] = '=', [0x15] = 'q', [0x1d] = 'w',
    [0x24] = 'e', [0x2d] = 'r', [0x2c] = 't', [0x35] = 'y', [0x3c] = 'u',
    [0x43] = 'i', [0x44] = 'o', [0x4d] = 'p', [0x54] = '[', [0x5b] = ']',
    [0x5d] = '\\', [0x1c] = 'a', [0x1b] = 's', [0x23] = 'd', [0x2b] = 'f',
    [0x34] = 'g', [0x33] = 'h', [0x3b] = 'j', [0x42] = 'k', [0x4b] = 'l',
    [0x4c] = ';', [0x52] = '\'', [0x1a] = 'z', [0x22] = 'x', [0x21] = 'c',
    [0x2a] = 'v', [0x32] = 'b', [0x31] = 'n', [0x3a] = 'm', [0x41] = ',',
    [0x49] = '.', [0x4a] = '/', [0x29] = ' '
};

static const char shifted[256] = {
    [0x0e] = '~', [0x16] = '!', [0x1e] = '@', [0x26] = '#', [0x25] = '$',
    [0x2e] = '%', [0x36] = '^', [0x3d] = '&', [0x3e] = '*', [0x46] = '(',
    [0x45] = ')', [0x4e] = '_', [0x55] = '+', [0x54] = '{', [0x5b] = '}',
    [0x5d] = '|', [0x4c] = ':', [0x52] = '"', [0x41] = '<', [0x49] = '>',
    [0x4a] = '?'
};

static const VTermKey plain[256] = {
    [0x5a] = VTERM_KEY_ENTER, [0x0d] = VTERM_KEY_TAB,
    [0x66] = VTERM_KEY_BACKSPACE, [0x76] = VTERM_KEY_ESCAPE,
    [0x05] = VTERM_KEY_FUNCTION(1), [0x06] = VTERM_KEY_FUNCTION(2),
    [0x04] = VTERM_KEY_FUNCTION(3), [0x0c] = VTERM_KEY_FUNCTION(4),
    [0x03] = VTERM_KEY_FUNCTION(5), [0x0b] = VTERM_KEY_FUNCTION(6),
    [0x83] = VTERM_KEY_FUNCTION(7), [0x0a] = VTERM_KEY_FUNCTION(8),
    [0x01] = VTERM_KEY_FUNCTION(9), [0x09] = VTERM_KEY_FUNCTION(10),
    [0x78] = VTERM_KEY_FUNCTION(11), [0x07] = VTERM_KEY_FUNCTION(12),
};

static const VTermKey extended[256] = {
    [0x75] = VTERM_KEY_UP, [0x72] = VTERM_KEY_DOWN, [0x6b] = VTERM_KEY_LEFT,
    [0x74] = VTERM_KEY_RIGHT, [0x70] = VTERM_KEY_INS, [0x71] = VTERM_KEY_DEL,
    [0x6c] = VTERM_KEY_HOME, [0x69] = VTERM_KEY_END,
    [0x7d] = VTERM_KEY_PAGEUP, [0x7a] = VTERM_KEY_PAGEDOWN,
    [0x5a] = VTERM_KEY_KP_ENTER, [0x4a] = VTERM_KEY_KP_DIVIDE
};

static const VTermKey keypad[256] = {
    [0x70] = VTERM_KEY_KP_0, [0x69] = VTERM_KEY_KP_1, [0x72] = VTERM_KEY_KP_2,
    [0x7a] = VTERM_KEY_KP_3, [0x6b] = VTERM_KEY_KP_4, [0x73] = VTERM_KEY_KP_5,
    [0x74] = VTERM_KEY_KP_6, [0x6c] = VTERM_KEY_KP_7, [0x75] = VTERM_KEY_KP_8,
    [0x7d] = VTERM_KEY_KP_9, [0x71] = VTERM_KEY_KP_PERIOD,
    [0x79] = VTERM_KEY_KP_PLUS, [0x7b] = VTERM_KEY_KP_MINUS,
    [0x7c] = VTERM_KEY_KP_MULT
};

void keyboard_reset(Keyboard *keyboard)
{
    *keyboard = (Keyboard){.colemak = keyboard->colemak};
}

static void clear_prefix(Keyboard *keyboard)
{
    keyboard->extended = keyboard->release = false;
    keyboard->special_length = 0;
}

void keyboard_expire(Keyboard *keyboard, uint64_t now)
{
    if (now - keyboard->last_byte >= 250000)
        clear_prefix(keyboard);
}

static void key(Keyboard *k, VTerm *vt, unsigned code)
{
    bool ext = k->extended, released = k->release, held = k->held[ext][code];
    k->held[ext][code] = !released;
    if (released)
        return;
    if (!ext && code == 0x58) {
        if (!held)
            k->caps = !k->caps;
        return;
    }
    if (!ext && code == 0x77) {
        if (!held)
            k->num = !k->num;
        return;
    }

    bool shift = k->held[0][0x12] || k->held[0][0x59];
    VTermModifier mod = shift ? VTERM_MOD_SHIFT : VTERM_MOD_NONE;
    if (k->held[0][0x14] || k->held[1][0x14])
        mod |= VTERM_MOD_CTRL;
    if (k->held[0][0x11] || k->held[1][0x11])
        mod |= VTERM_MOD_ALT;

    VTermKey symbol = ext ? extended[code] : plain[code];
    if (!ext && keypad[code]) {
        VTermKey pad = keypad[code];
        symbol = !k->num && (pad <= VTERM_KEY_KP_9 || pad == VTERM_KEY_KP_PERIOD)
               ? extended[code] : pad;
    }
    if (symbol) {
        vterm_keyboard_key(vt, symbol, mod);
        return;
    }

    // Standard Colemak letter/punctuation positions, expressed as Set 2 codes.
    static const uint8_t colemak[256] = {
        [0x24] = 0x2b, [0x2d] = 0x4d, [0x2c] = 0x34, [0x35] = 0x3b,
        [0x3c] = 0x4b, [0x43] = 0x3c, [0x44] = 0x35, [0x4d] = 0x4c,
        [0x1b] = 0x2d, [0x23] = 0x1b, [0x2b] = 0x2c, [0x34] = 0x23,
        [0x3b] = 0x31, [0x42] = 0x24, [0x4b] = 0x43, [0x4c] = 0x44,
        [0x31] = 0x42
    };
    if (k->colemak && !ext && colemak[code])
        code = colemak[code];
    char ch = lower[code];
    if (ext || !ch)
        return;
    if (ch >= 'a' && ch <= 'z') {
        if (shift != k->caps && !(mod & VTERM_MOD_CTRL))
            ch = (char)(ch - 'a' + 'A');
    } else if (shift && shifted[code]) {
        ch = shifted[code];
    }
    vterm_keyboard_unichar(vt, (uint32_t)ch, mod & ~VTERM_MOD_SHIFT);
}

static void special_byte(Keyboard *k, uint8_t byte)
{
    static const uint8_t pause[] = {0xe1, 0x14, 0x77, 0xe1, 0xf0, 0x14, 0xf0, 0x77};
    static const uint8_t print_make[] = {0xe0, 0x12, 0xe0, 0x7c};
    static const uint8_t print_break[] = {0xe0, 0xf0, 0x7c, 0xe0, 0xf0, 0x12};
    const uint8_t *pattern;
    size_t size;
    if (k->special[0] == 0xe1) {
        pattern = pause;
        size = sizeof(pause);
    } else if (k->special[1] == 0x12) {
        pattern = print_make;
        size = sizeof(print_make);
    } else {
        pattern = print_break;
        size = sizeof(print_break);
    }
    if (byte != pattern[k->special_length] || ++k->special_length == size)
        clear_prefix(k);
}

void keyboard_byte(Keyboard *k, VTerm *vt, uint8_t byte, uint64_t now)
{
    keyboard_expire(k, now);
    k->last_byte = now;
    if (byte == 0xaa) {
        keyboard_reset(k);
    } else if (k->special_length) {
        special_byte(k, byte);
    } else if (byte == 0xe1) {
        clear_prefix(k);
        k->special[0] = byte;
        k->special_length = 1;
    } else if (byte == 0xe0 && !k->extended && !k->release) {
        k->extended = true;
    } else if (byte == 0xf0 && !k->release) {
        k->release = true;
    } else if (byte == 0xe0 || byte == 0xf0 || byte == 0 || byte >= 0x84) {
        clear_prefix(k);
    } else if (k->extended && ((!k->release && byte == 0x12) || (k->release && byte == 0x7c))) {
        k->special[0] = 0xe0;
        k->special[1] = k->release ? 0xf0 : 0x12;
        k->special_length = k->release ? 3 : 2;
    } else {
        key(k, vt, byte);
        clear_prefix(k);
    }
}

// A transport can withhold acceptance until enough queue space is available.
bool terminal_keys(Terminal *terminal, Keyboard *keyboard,
                   const uint8_t *bytes, size_t length, uint64_t now)
{
    if (!length) {
        keyboard_reset(keyboard);
        return true;
    }
    if (length > 16 || terminal->input.length > INPUT_CAPACITY - 256)
        return false;
    for (size_t i = 0; i < length; ++i)
        keyboard_byte(keyboard, terminal->vt, bytes[i], now);
    return !terminal->overflow;
}
