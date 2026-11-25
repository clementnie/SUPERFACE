#ifndef SUPERFACE_H
#define SUPERFACE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <vterm.h>

enum { ROWS = 30, COLS = 80, CELL_BYTES = 3, PAYLOAD_MAX = 243 };
enum { CHINESE_FIRST = 0x8000, CONTINUATION = 0xffff, MISSING_SINGLE = 0x7f, MISSING_DOUBLE = 0x80, SYMBOL_FIRST = 0x9abc };
enum { SNAP_BEGIN = 0x10, SNAP_ROW, SNAP_END, WRITE_SPAN, CURSOR, STAGE_SPAN = 0x16, FRAME_COMMIT, EXT_SNAP_BEGIN };
enum { FRAME_US = 16800, BLINK_US = 500000 };

typedef uint8_t Row[COLS * CELL_BYTES];
typedef struct {
    Row rows[ROWS];
    uint8_t cursor[3];
} Grid;

typedef struct {
    uint8_t type;
    size_t length;
    uint8_t payload[PAYLOAD_MAX];
} Command;

/*
 * One command in flight. submit copies the command, and poll returns zero
 * pending, one successful completion, or minus one on rejection/session loss.
 * A transport reports idle session loss through poll too. Reinitialize both
 * sides after a fresh handshake, then call display_connect and reset keyboard.
 * Timestamp arguments are monotonic microseconds. Only successful commits
 * advance the host's acknowledged state.
 */
typedef struct {
    void *context;
    bool (*submit)(void *, const Command *, uint64_t);
    int (*poll)(void *, uint64_t);
    bool batch, extended_glyphs;
} Backend;

typedef struct {
    Backend backend;
    Grid acknowledged, snapshot;
    Command pending;
    enum { OFFLINE, BEGIN, RECEIVE_ROWS, END, ACTIVE } state;
    bool in_flight, cursor_turn, batch_open;
    unsigned snapshot_row, scan_row;
    uint64_t visible_after;
} Display;

void display_connect(Display *, Backend);
bool display_tick(Display *, const Grid *, uint64_t);
bool display_synced(const Display *, const Grid *);

typedef struct {
    Grid grid, staging;
    Command pending;
    enum { SIM_WAIT, SIM_RECEIVING, SIM_ACTIVE } state;
    bool busy, fail_next;
    unsigned next_row, submitted, commits, spans, cursors;
    uint16_t chinese_count;
    uint64_t due, next_frame, delay;
} Simulator;

Backend simulator_backend(Simulator *);
void simulator_reset(Simulator *, uint16_t, uint64_t);

enum { INPUT_CAPACITY = 16384, PTY_CHUNK = 512, INPUT_RESERVE = 8192 };
typedef struct {
    uint8_t data[INPUT_CAPACITY];
    size_t head, length;
} InputQueue;

typedef struct {
    VTerm *vt;
    VTermScreen *screen;
    Grid logical, desired;
    InputQueue input;
    bool dirty[ROWS], text_blink[ROWS][COLS];
    bool font, extended, cursor_visible, cursor_blink, overflow;
    bool phase;
    VTermPos cursor;
} Terminal;

extern const uint8_t sf_mapping[16], sf_legacy_mapping[16];
uint16_t sf_font_count(void);
uint16_t sf_chinese_count(void);
uint16_t sf_glyph(uint32_t);
uint32_t sf_scalar(uint16_t);
uint16_t cell_id(const uint8_t *);
bool terminal_init(Terminal *, bool);
void terminal_destroy(Terminal *);
void terminal_set_font(Terminal *, bool);
void terminal_set_extended(Terminal *, bool);
bool terminal_feed(Terminal *, const char *, size_t);
void terminal_refresh(Terminal *, uint64_t);
bool terminal_input(Terminal *, const void *, size_t);
void input_consume(InputQueue *, size_t);

typedef struct {
    bool held[2][256], caps, num, extended, release, colemak;
    uint8_t special[8];
    size_t special_length;
    uint64_t last_byte;
} Keyboard;

void keyboard_reset(Keyboard *);
void keyboard_expire(Keyboard *, uint64_t);
void keyboard_byte(Keyboard *, VTerm *, uint8_t, uint64_t);
bool terminal_keys(Terminal *, Keyboard *, const uint8_t *, size_t, uint64_t);

#endif
