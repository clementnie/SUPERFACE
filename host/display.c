#include "superface.h"

#include <string.h>

void display_connect(Display *display, Backend backend)
{
    memset(display, 0, sizeof(*display));
    display->backend = backend;
    display->state = BEGIN;
}

static void completed(Display *display)
{
    const Command *cmd = &display->pending;
    const uint8_t *p = cmd->payload;
    switch (cmd->type) {
    case EXT_SNAP_BEGIN:
    case SNAP_BEGIN:
        display->state = RECEIVE_ROWS;
        break;
    case SNAP_ROW:
        if (++display->snapshot_row == ROWS)
            display->state = END;
        break;
    case SNAP_END:
        display->acknowledged = display->snapshot;
        display->state = ACTIVE;
        break;
    case STAGE_SPAN:
        display->scan_row = p[0] + 1;
        break;
    case FRAME_COMMIT:
        display->acknowledged = display->snapshot;
        display->batch_open = false;
        break;
    case WRITE_SPAN:
        memcpy(display->acknowledged.rows[p[0]] + p[1] * CELL_BYTES, p + 3,
               p[2] * CELL_BYTES);
        display->scan_row = (p[0] + 1) % ROWS;
        display->cursor_turn = true;
        break;
    case CURSOR:
        memcpy(display->acknowledged.cursor, p, 3);
        display->cursor_turn = false;
        break;
    }
}

static bool continuation(const uint8_t *row, unsigned col)
{
    return cell_id(row + col * CELL_BYTES) == CONTINUATION;
}

static bool span(Display *display, const Grid *desired, Command *cmd)
{
    unsigned rows = display->backend.batch ? ROWS - display->scan_row : ROWS;
    for (unsigned i = 0; i < rows; ++i) {
        unsigned row = (display->scan_row + i) % ROWS;
        const uint8_t *a = display->acknowledged.rows[row], *b = desired->rows[row];
        if (!memcmp(a, b, sizeof(Row)))
            continue;
        unsigned start = 0, end = COLS;
        while (!memcmp(a + start * CELL_BYTES, b + start * CELL_BYTES, CELL_BYTES))
            ++start;
        while (!memcmp(a + (end - 1) * CELL_BYTES, b + (end - 1) * CELL_BYTES, CELL_BYTES))
            --end;
        while (start && (continuation(a, start) || continuation(b, start)))
            --start;
        while (end < COLS && (continuation(a, end) || continuation(b, end)))
            ++end;
        cmd->type = display->backend.batch ? STAGE_SPAN : WRITE_SPAN;
        cmd->payload[0] = (uint8_t)row;
        cmd->payload[1] = (uint8_t)start;
        cmd->payload[2] = (uint8_t)(end - start);
        cmd->length = 3 + (end - start) * CELL_BYTES;
        memcpy(cmd->payload + 3, b + start * CELL_BYTES, cmd->length - 3);
        return true;
    }
    return false;
}

bool display_tick(Display *display, const Grid *desired, uint64_t now)
{
    if (display->state == OFFLINE)
        return false;
    int result = display->backend.poll(display->backend.context, now);
    if (result < 0 || (result > 0 && !display->in_flight))
        goto lost;
    if (display->in_flight) {
        if (!result)
            return true;
        completed(display);
        display->in_flight = false;
    }

    Command *cmd = &display->pending;
    *cmd = (Command){0};
    switch (display->state) {
    case OFFLINE:
        return false;
    case BEGIN:
        display->snapshot = *desired;
        cmd->type = display->backend.extended_glyphs ? EXT_SNAP_BEGIN : SNAP_BEGIN;
        break;
    case RECEIVE_ROWS:
        cmd->type = SNAP_ROW;
        cmd->payload[0] = (uint8_t)display->snapshot_row;
        cmd->length = 1 + sizeof(Row);
        memcpy(cmd->payload + 1, display->snapshot.rows[display->snapshot_row], sizeof(Row));
        break;
    case END:
        cmd->type = SNAP_END;
        cmd->length = 3;
        memcpy(cmd->payload, display->snapshot.cursor, 3);
        break;
    case ACTIVE: {
        if (display->backend.batch) {
            if (!display->batch_open) {
                if (!memcmp(desired, &display->acknowledged, sizeof(*desired)))
                    return true;
                display->snapshot = *desired;
                display->scan_row = 0;
                display->batch_open = true;
            }
            if (span(display, &display->snapshot, cmd))
                break;
            cmd->type = FRAME_COMMIT;
            cmd->length = 3;
            memcpy(cmd->payload, display->snapshot.cursor, 3);
            break;
        }
        if (now < display->visible_after)
            return true;
        bool cursor_changed = memcmp(desired->cursor, display->acknowledged.cursor, 3);
        if ((!cursor_changed || !display->cursor_turn) && span(display, desired, cmd))
            break;
        if (!cursor_changed)
            return true;
        cmd->type = CURSOR;
        cmd->length = 3;
        memcpy(cmd->payload, desired->cursor, 3);
        break;
    }
    }

    if (!display->backend.submit(display->backend.context, cmd, now))
        goto lost;
    display->in_flight = true;
    if (cmd->type != SNAP_ROW)
        display->visible_after = now + FRAME_US;
    return true;

lost:
    display->state = OFFLINE;
    display->in_flight = false;
    return false;
}

bool display_synced(const Display *display, const Grid *desired)
{
    return display->state == ACTIVE && !display->in_flight && !display->batch_open &&
           !memcmp(&display->acknowledged, desired, sizeof(Grid));
}
