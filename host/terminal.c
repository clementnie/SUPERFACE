#define _XOPEN_SOURCE 700
#include "superface.h"

#include <limits.h>
#include <string.h>
#include <wchar.h>

#include "font.inc"

static const uint8_t palette[16][3] = {
    {0,0,0}, {170,0,0}, {0,170,0}, {170,85,0},
    {0,0,170}, {170,0,170}, {0,170,170}, {170,170,170},
    {85,85,85}, {255,85,85}, {85,255,85}, {255,255,85},
    {85,85,255}, {255,85,255}, {85,255,255}, {255,255,255}
};

uint16_t sf_chinese_count(void)
{
    return LEGACY_WIDE_COUNT;
}

uint16_t sf_font_count(void)
{
    return sizeof(chinese_scalars) / sizeof(*chinese_scalars);
}

uint16_t sf_glyph(uint32_t code)
{
    if (code >= 0x20 && code <= 0x7e)
        return (uint16_t)code;
    size_t lo = 0, hi = sf_font_count();
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        if (chinese_scalars[mid] == code)
            return chinese_glyph_ids[mid];
        if (chinese_scalars[mid] < code)
            lo = mid + 1;
        else
            hi = mid;
    }
    return 0;
}

uint32_t sf_scalar(uint16_t glyph)
{
    if (glyph >= CHINESE_FIRST && glyph - CHINESE_FIRST < sf_font_count())
        return scalars_by_glyph[glyph - CHINESE_FIRST];
    return glyph >= 0x20 && glyph <= 0x7e ? glyph : 0xfffd;
}

uint16_t cell_id(const uint8_t *cell)
{
    return (uint16_t)(cell[0] | (unsigned)cell[1] << 8);
}

static void put_cell(uint8_t *cell, uint16_t id, uint8_t color)
{
    cell[0] = (uint8_t)id;
    cell[1] = (uint8_t)(id >> 8);
    cell[2] = color;
}

static unsigned color_index(Terminal *terminal, VTermColor color)
{
    if (VTERM_COLOR_IS_DEFAULT_FG(&color))
        return 7;
    if (VTERM_COLOR_IS_DEFAULT_BG(&color))
        return 0;
    if (VTERM_COLOR_IS_INDEXED(&color) && color.indexed.idx < 16)
        return color.indexed.idx;

    vterm_screen_convert_color_to_rgb(terminal->screen, &color);
    unsigned best = 0, distance = UINT_MAX;
    for (unsigned i = 0; i < 16; ++i) {
        int r = (int)color.rgb.red - palette[i][0];
        int g = (int)color.rgb.green - palette[i][1];
        int b = (int)color.rgb.blue - palette[i][2];
        unsigned candidate = (unsigned)(r*r + g*g + b*b);
        if (candidate < distance) {
            best = i;
            distance = candidate;
        }
    }
    return best;
}

bool terminal_input(Terminal *terminal, const void *bytes, size_t length)
{
    InputQueue *q = &terminal->input;
    if (length > sizeof(q->data) - q->length)
        return false;
    if (q->head + q->length + length > sizeof(q->data)) {
        memmove(q->data, q->data + q->head, q->length);
        q->head = 0;
    }
    memcpy(q->data + q->head + q->length, bytes, length);
    q->length += length;
    return true;
}

void input_consume(InputQueue *q, size_t length)
{
    q->length -= length;
    q->head = q->length ? q->head + length : 0;
}

static void output(const char *bytes, size_t length, void *user)
{
    Terminal *terminal = user;
    if (!terminal_input(terminal, bytes, length))
        terminal->overflow = true;
}

static int damage(VTermRect rect, void *user)
{
    Terminal *terminal = user;
    for (int row = rect.start_row; row < rect.end_row; ++row)
        terminal->dirty[row] = true;
    return 1;
}

static int move_rect(VTermRect dest, VTermRect src, void *user)
{
    damage(dest, user);
    return damage(src, user);
}

static int move_cursor(VTermPos pos, VTermPos old, int visible, void *user)
{
    (void)old;
    Terminal *terminal = user;
    terminal->cursor = pos;
    terminal->cursor_visible = visible;
    return 1;
}

static int property(VTermProp prop, VTermValue *value, void *user)
{
    Terminal *terminal = user;
    switch (prop) {
    case VTERM_PROP_CURSORVISIBLE:
        terminal->cursor_visible = value->boolean;
        break;
    case VTERM_PROP_CURSORBLINK:
        terminal->cursor_blink = value->boolean;
        break;
    case VTERM_PROP_REVERSE:
    case VTERM_PROP_ALTSCREEN:
        memset(terminal->dirty, 1, sizeof(terminal->dirty));
        break;
    default:
        break;
    }
    return 1;
}

bool terminal_init(Terminal *terminal, bool font)
{
    static const VTermScreenCallbacks callbacks = {
        .damage = damage, .moverect = move_rect, .movecursor = move_cursor,
        .settermprop = property
    };
    memset(terminal, 0, sizeof(*terminal));
    terminal->font = font;
    terminal->vt = vterm_new(ROWS, COLS);
    if (!terminal->vt)
        return false;
    vterm_set_utf8(terminal->vt, 1);
    vterm_output_set_callback(terminal->vt, output, terminal);
    terminal->screen = vterm_obtain_screen(terminal->vt);
    vterm_screen_set_callbacks(terminal->screen, &callbacks, terminal);
    vterm_screen_set_damage_merge(terminal->screen, VTERM_DAMAGE_SCROLL);
    vterm_screen_enable_altscreen(terminal->screen, 1);
    vterm_state_set_bold_highbright(vterm_obtain_state(terminal->vt), 0);
    vterm_screen_reset(terminal->screen, 1);
    memset(terminal->dirty, 1, sizeof(terminal->dirty));
    return true;
}

void terminal_destroy(Terminal *terminal)
{
    vterm_free(terminal->vt);
    memset(terminal, 0, sizeof(*terminal));
}

void terminal_set_font(Terminal *terminal, bool font)
{
    if (terminal->font != font) {
        terminal->font = font;
        memset(terminal->dirty, 1, sizeof(terminal->dirty));
    }
}

void terminal_set_extended(Terminal *terminal, bool extended)
{
    if (terminal->extended != extended) {
        terminal->extended = extended;
        memset(terminal->dirty, 1, sizeof(terminal->dirty));
    }
}

bool terminal_feed(Terminal *terminal, const char *bytes, size_t length)
{
    for (size_t offset = 0; offset < length;) {
        size_t used = vterm_input_write(terminal->vt, bytes + offset, length - offset);
        if (!used || terminal->overflow)
            return false;
        offset += used;
    }
    vterm_screen_flush_damage(terminal->screen);
    return true;
}

static void translate_row(Terminal *terminal, int row)
{
    for (int col = 0; col < COLS; ++col) {
        VTermScreenCell source = {0};
        vterm_screen_get_cell(terminal->screen, (VTermPos){row, col}, &source);
        unsigned fg = color_index(terminal, source.fg);
        unsigned bg = color_index(terminal, source.bg);
        if (source.attrs.reverse) {
            unsigned swap = fg;
            fg = bg;
            bg = swap;
        }
        uint8_t color = (uint8_t)((bg << 4) | fg);
        uint32_t scalar = source.chars[0];
        // A partial overwrite can leave a libvterm continuation beside a narrow glyph.
        int width = scalar <= 0x10ffff ? wcwidth((wchar_t)scalar) : 0;
        bool wide = source.width == 2 && col + 1 < COLS && scalar >= 0x7f &&
                    scalar != UINT32_MAX && width != 1 && width != 0;

        uint16_t id = ' ';
        if (scalar && scalar != UINT32_MAX && !source.attrs.conceal) {
            id = sf_glyph(scalar);
            bool narrow_glyph = id >= NARROW_FIRST && id < NARROW_LIMIT;
            bool external_glyph = id >= CHINESE_FIRST;
            if (!id || (external_glyph &&
                (!terminal->font || (id >= NARROW_FIRST && !terminal->extended) ||
                 wide == narrow_glyph))) {
                if (terminal->extended)
                    id = wide ? MISSING_DOUBLE : MISSING_SINGLE;
                else
                    id = '?'; // Legacy firmware only renders the ASCII fallback.
            }
            if (!wide && width == 2 && col != COLS - 1)
                id = ' ';
        }
        put_cell(terminal->logical.rows[row] + col * CELL_BYTES, id, color);
        terminal->text_blink[row][col] = source.attrs.blink;
        if (wide) {
            ++col;
            put_cell(terminal->logical.rows[row] + col * CELL_BYTES,
                     (id >= CHINESE_FIRST || id == MISSING_DOUBLE) ? CONTINUATION : ' ', color);
            terminal->text_blink[row][col] = source.attrs.blink;
        }
    }
}

void terminal_refresh(Terminal *terminal, uint64_t now)
{
    bool on = (now / BLINK_US) % 2 == 0;
    for (int row = 0; row < ROWS; ++row) {
        bool dirty = terminal->dirty[row];
        if (dirty) {
            translate_row(terminal, row);
            terminal->dirty[row] = false;
        }
        if (!dirty && on == terminal->phase)
            continue;
        memcpy(terminal->desired.rows[row], terminal->logical.rows[row], sizeof(Row));
        if (on)
            continue;
        for (int col = 0; col < COLS; ++col) {
            if (!terminal->text_blink[row][col])
                continue;
            uint8_t *cell = terminal->desired.rows[row] + col * CELL_BYTES;
            put_cell(cell, ' ', cell[2]);
        }
    }
    terminal->phase = on;
    terminal->desired.cursor[0] = (uint8_t)(terminal->cursor.row < ROWS ? terminal->cursor.row : ROWS - 1);
    terminal->desired.cursor[1] = (uint8_t)(terminal->cursor.col < COLS ? terminal->cursor.col : COLS - 1);
    terminal->desired.cursor[2] = terminal->cursor_visible && (!terminal->cursor_blink || on);
}
