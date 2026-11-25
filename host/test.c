#include "superface.h"

#include <assert.h>
#include <locale.h>
#include <stdio.h>
#include <string.h>

static void feed(Terminal *term, const char *text)
{
    assert(terminal_feed(term, text, strlen(text)));
}

static void cell(const Terminal *term, unsigned row, unsigned col, uint16_t id, unsigned color)
{
    const uint8_t *c = term->desired.rows[row] + 3 * col;
    if (cell_id(c) != id || c[2] != color)
        fprintf(stderr, "row %u col %u: got %04x %02x expected %04x %02x\n",
                row, col, cell_id(c), c[2], id, color);
    assert(cell_id(c) == id && c[2] == color);
}

static void screen_tests(bool font)
{
    Terminal term;
    assert(terminal_init(&term, font));
    const uint16_t han = sf_glyph(0x4e2d);
    assert(han >= CHINESE_FIRST);
    feed(&term, "A\xe4");
    feed(&term, "\xb8");
    feed(&term, "\xad" "e");
    feed(&term, "\xcc\x81\xf0\x9f\x90\xb1\xc3\xa9");
    // U+589A is listed in missing_zh_hans.csv.
    assert(sf_glyph(0x589a) == 0);
    feed(&term, "\xe5\xa2\x9a");
    terminal_refresh(&term, 0);
    cell(&term, 0, 0, 'A', 7);
    cell(&term, 0, 1, font ? han : '?', 7);
    cell(&term, 0, 2, font ? CONTINUATION : ' ', 7);
    cell(&term, 0, 3, 'e', 7);
    for (unsigned col = 4; col <= 8; ++col)
        cell(&term, 0, col, col == 5 || col == 8 ? ' ' : '?', 7);

    feed(&term, "\033[91;44mA \033[1;31;49mB\033[7mC\033[0;38;2;255;85;85;48;5;21mD\033[0m");
    terminal_refresh(&term, 0);
    cell(&term, 0, 9, 'A', 0x49);
    cell(&term, 0, 10, ' ', 0x49);
    cell(&term, 0, 11, 'B', 0x01);
    cell(&term, 0, 12, 'C', 0x10);
    cell(&term, 0, 13, 'D', 0x49);

    feed(&term, "\033[2;80H\xe4\xb8\xad\033[?7l\033[4;80H\xe4\xb8\xad\033[?7h");
    terminal_refresh(&term, 0);
    cell(&term, 1, 79, ' ', 7);
    cell(&term, 2, 0, font ? han : '?', 7);
    cell(&term, 2, 1, font ? CONTINUATION : ' ', 7);
    cell(&term, 3, 79, '?', 7);

    feed(&term, "\033[1;2HZ\033[3;2H\033[1X\033[5;1Habc\033[5;2H\033[@\033[P");
    terminal_refresh(&term, 0);
    cell(&term, 0, 1, 'Z', 7);
    cell(&term, 0, 2, ' ', 7);
    cell(&term, 2, 0, ' ', 7);
    cell(&term, 2, 1, ' ', 7);
    cell(&term, 4, 1, 'b', 7);

    feed(&term, "\033[?1049h\033[Halt\033[?25l");
    terminal_refresh(&term, 0);
    cell(&term, 0, 0, 'a', 7);
    assert(!term.desired.cursor[2]);
    feed(&term, "\033[?1049l\033[?25h\033[?12l");
    terminal_refresh(&term, BLINK_US);
    cell(&term, 0, 0, 'A', 7);
    assert(term.desired.cursor[2]);

    feed(&term, "\033[5;6r\033[5;1Hfirst\r\nsecond\r\nthird\033[r");
    terminal_refresh(&term, 0);
    cell(&term, 3, 79, '?', 7);
    cell(&term, 4, 0, 's', 7);
    cell(&term, 5, 0, 't', 7);

    feed(&term, "\033[8;2H\033[5;42m\xe4\xb8\xad\033[0m\033[?12h\033[6n");
    terminal_refresh(&term, BLINK_US);
    cell(&term, 7, 1, ' ', 0x27);
    cell(&term, 7, 2, ' ', 0x27);
    assert(!term.desired.cursor[2]);
    terminal_refresh(&term, BLINK_US * 2);
    cell(&term, 7, 1, font ? han : '?', 0x27);
    cell(&term, 7, 2, font ? CONTINUATION : ' ', 0x27);
    assert(term.desired.cursor[2] && term.desired.cursor[0] == 7 && term.desired.cursor[1] == 3);
    assert(term.input.length == 6 && !memcmp(term.input.data, "\033[8;4R", 6));
    terminal_destroy(&term);
}

static void keys(Terminal *term, Keyboard *keyboard, const uint8_t *data, size_t size,
                 const char *expected, size_t length, uint64_t *time)
{
    for (size_t i = 0; i < size; ++i) {
        *time += 1000;
        keyboard_byte(keyboard, term->vt, data[i], *time);
    }
    assert(term->input.length == length);
    assert(!memcmp(term->input.data + term->input.head, expected, length));
    input_consume(&term->input, length);
}

#define KEYS(sequence, expected) keys(&term, &keyboard, sequence, sizeof(sequence), expected, sizeof(expected) - 1, &now)
static void keyboard_tests(void)
{
    Terminal term;
    Keyboard keyboard = {0};
    uint64_t now = 0;
    assert(terminal_init(&term, true));
    keyboard_reset(&keyboard);
    const uint8_t shift_repeat[] = {0x12, 0x1c, 0x1c, 0xf0, 0x1c, 0xf0, 0x12, 0x1c};
    KEYS(shift_repeat, "AAa");
    const uint8_t caps[] = {0x58, 0x58, 0x1c, 0xf0, 0x58, 0x58, 0x1c};
    KEYS(caps, "Aa");
    const uint8_t mods[] = {0xe0, 0x14, 0x21, 0xe0, 0xf0, 0x14, 0x11, 0x1c, 0xf0, 0x11};
    KEYS(mods, "\003\033a");
    const uint8_t prefix[] = {0xe0};
    const uint8_t up[] = {0x75};
    const uint8_t f1[] = {0x05};
    KEYS(prefix, "");
    KEYS(up, "\033[A");
    feed(&term, "\033[?1h");
    KEYS(prefix, "");
    KEYS(up, "\033OA");
    KEYS(f1, "\033OP");
    const uint8_t special[] = {0xe0, 0x12, 0xe0, 0x7c, 0xe0, 0xf0, 0x7c,
                               0xe0, 0xf0, 0x12, 0xe1, 0x14, 0x77, 0xe1, 0xf0, 0x14, 0xf0, 0x77};
    KEYS(special, "");
    const uint8_t keypad[] = {0x77, 0x69};
    feed(&term, "\033=");
    KEYS(keypad, "\033Oq");
    KEYS(prefix, "");
    now += 250000;
    const uint8_t a[] = {0x1c};
    KEYS(a, "a");
    const uint8_t bat[] = {0x59, 0xaa, 0x1c};
    KEYS(bat, "a");
    KEYS(prefix, "");
    keyboard_reset(&keyboard);
    KEYS(a, "a");
    terminal_destroy(&term);
}

static void converge(Display *d, Simulator *s, const Grid *desired, uint64_t *now)
{
    for (unsigned i = 0; i < 500 && !display_synced(d, desired); ++i) {
        *now += 1000;
        assert(display_tick(d, desired, *now));
    }
    assert(display_synced(d, desired));
    assert(s->state == SIM_ACTIVE && !memcmp(&s->grid, desired, sizeof(*desired)));
}

static void display_tests(bool font)
{
    Terminal term;
    Display d;
    Simulator s;
    uint64_t now = 0;
    assert(terminal_init(&term, font));
    feed(&term, "\033[1;79H\xe4\xb8\xad");
    terminal_refresh(&term, 0);
    simulator_reset(&s, font ? sf_chinese_count() : 0, 2000);
    Backend backend = simulator_backend(&s);
    display_connect(&d, backend);
    assert(display_tick(&d, &term.desired, now));
    assert(d.state == BEGIN && d.acknowledged.rows[0][0] == 0 && s.state == SIM_WAIT);
    feed(&term, "\033[2;1HZ");
    terminal_refresh(&term, 0);
    converge(&d, &s, &term.desired, &now);
    assert(s.submitted >= 33 && s.spans == 1);

    // Replacing only the glyph ID still requires the unchanged continuation.
    feed(&term, "\033[1;79H\xe6\x96\x87");
    terminal_refresh(&term, 0);
    now += FRAME_US;
    assert(display_tick(&d, &term.desired, now));
    if (font) {
        assert(d.in_flight && d.pending.type == WRITE_SPAN);
        assert(d.pending.payload[1] == 78 && d.pending.payload[2] == 2);
    }
    converge(&d, &s, &term.desired, &now);

    // The peer rejects a split pair transaction atomically.
    if (font) {
        Grid before = s.grid;
        Command split = {.type = WRITE_SPAN, .length = 6, .payload = {0, 79, 1, 'X', 0, 7}};
        assert(backend.submit(backend.context, &split, now));
        now += 2 * FRAME_US;
        assert(backend.poll(backend.context, now) == -1);
        assert(!memcmp(&before, &s.grid, sizeof(before)));
    }
    Grid acknowledged = d.acknowledged;
    s.fail_next = true;
    feed(&term, "\033[1;80H\033[1X\033[4;1Hreconnect");
    terminal_refresh(&term, 0);
    for (unsigned i = 0; i < 100 && d.state != OFFLINE; ++i) {
        now += 1000;
        display_tick(&d, &term.desired, now);
    }
    assert(d.state == OFFLINE && !memcmp(&acknowledged, &d.acknowledged, sizeof(Grid)));
    simulator_reset(&s, font ? sf_chinese_count() : 0, 1500);
    backend = simulator_backend(&s);
    Command early_end = {.type = SNAP_END, .length = 3};
    assert(backend.submit(backend.context, &early_end, now));
    now += 2 * FRAME_US;
    assert(backend.poll(backend.context, now) == -1 && s.state == SIM_WAIT);
    display_connect(&d, backend);
    converge(&d, &s, &term.desired, &now);
    assert(s.submitted == 33 && s.next_row == ROWS);

    // Continually move the cursor while a full-screen erase is draining.
    feed(&term, "\033[43m\033[2J");
    for (unsigned i = 0; i < 150; ++i) {
        terminal_refresh(&term, 0);
        term.desired.cursor[1] = (uint8_t)(i % COLS);
        now += 10000;
        assert(display_tick(&d, &term.desired, now));
    }
    assert(!memcmp(s.grid.rows, term.desired.rows, sizeof(s.grid.rows)));
    assert(s.cursors && s.spans == ROWS);
    converge(&d, &s, &term.desired, &now);
    terminal_destroy(&term);
}

static void punctuation_tests(bool font)
{
    assert(sf_glyph(0x4f60) == 0x80c8); /* verified Han ID */
    assert(sf_glyph(0xff0c) == 0x9a69);
    for (unsigned i = 0; i < sf_chinese_count(); ++i)
        assert(sf_glyph(sf_scalar((uint16_t)(CHINESE_FIRST + i))) == CHINESE_FIRST + i);
    Terminal term;
    assert(terminal_init(&term, font));
    feed(&term, "\033[31;44m，。！？");
    terminal_refresh(&term, 0);
    const uint16_t expected[] = {0x9a69, 0x9a48, 0x9a5e, 0x9a7c};
    for (unsigned i = 0; i < 4; ++i) {
        cell(&term, 0, 2*i, font ? expected[i] : '?', 0x41);
        cell(&term, 0, 2*i+1, font ? CONTINUATION : ' ', 0x41);
    }
    feed(&term, "\033[2;79H，\033[3;80H！");
    terminal_refresh(&term, 0);
    cell(&term, 1, 78, font ? 0x9a69 : '?', 0x41);
    cell(&term, 1, 79, font ? CONTINUATION : ' ', 0x41);
    cell(&term, 3, 0, font ? 0x9a5e : '?', 0x41);
    cell(&term, 3, 1, font ? CONTINUATION : ' ', 0x41);
    terminal_destroy(&term);
}

int main(void)
{
    assert(setlocale(LC_ALL, "C.UTF-8"));
    punctuation_tests(true);
    punctuation_tests(false);
    screen_tests(true);
    screen_tests(false);
    keyboard_tests();
    display_tests(true);
    display_tests(false);
    puts("libvterm, cells, keyboard, snapshot, spans, cursor, failure and reconnect passed");
    return 0;
}
