#include "superface.h"

#include <string.h>

static unsigned decode_id(const uint8_t *bytes)
{
    return bytes[0] + 256u * bytes[1];
}

static bool valid_row(const Simulator *sim, const uint8_t *row)
{
    for (unsigned col = 0; col < COLS; ++col) {
        const uint8_t *cell = row + 3 * col;
        unsigned id = decode_id(cell);
        if (id >= 0x20 && id <= 0x7e)
            continue;
        if (id < 0x8000 || id - 0x8000 >= sim->chinese_count || col == COLS - 1)
            return false;
        const uint8_t *next = cell + 3;
        if (next[0] != 255 || next[1] != 255 || next[2] != cell[2])
            return false;
        ++col;
    }
    return true;
}

static bool valid_cursor(const Command *command)
{
    return command->length == 3 && command->payload[0] < ROWS &&
           command->payload[1] < COLS && command->payload[2] <= 1;
}

static bool execute(Simulator *sim)
{
    const Command *command = &sim->pending;
    const uint8_t *p = command->payload;
    switch (command->type) {
    case SNAP_BEGIN:
        if (command->length || sim->state == SIM_RECEIVING)
            return false;
        sim->state = SIM_RECEIVING;
        sim->next_row = 0;
        return true;
    case SNAP_ROW:
        if (command->length != 1 + sizeof(Row) || p[0] >= ROWS ||
            sim->state != SIM_RECEIVING || p[0] != sim->next_row ||
            !valid_row(sim, p + 1))
            return false;
        memcpy(sim->staging.rows[p[0]], p + 1, sizeof(Row));
        ++sim->next_row;
        return true;
    case SNAP_END:
        if (!valid_cursor(command) || sim->state != SIM_RECEIVING || sim->next_row != ROWS)
            return false;
        memcpy(sim->staging.cursor, p, 3);
        sim->grid = sim->staging;
        sim->state = SIM_ACTIVE;
        return true;
    case WRITE_SPAN: {
        if (command->length < 3 || p[0] >= ROWS || p[1] >= COLS || !p[2] ||
            p[1] + p[2] > COLS || command->length != 3u + p[2] * 3u ||
            sim->state != SIM_ACTIVE)
            return false;
        Row candidate;
        memcpy(candidate, sim->grid.rows[p[0]], sizeof(candidate));
        memcpy(candidate + 3 * p[1], p + 3, 3 * p[2]);
        if (!valid_row(sim, candidate))
            return false;
        memcpy(sim->grid.rows[p[0]], candidate, sizeof(candidate));
        ++sim->spans;
        return true;
    }
    case CURSOR:
        if (!valid_cursor(command) || sim->state != SIM_ACTIVE)
            return false;
        memcpy(sim->grid.cursor, p, 3);
        ++sim->cursors;
        return true;
    }
    return false;
}

static bool submit(void *context, const Command *command, uint64_t now)
{
    Simulator *sim = context;
    if (sim->busy || command->length > sizeof(command->payload))
        return false;
    sim->pending = *command;
    sim->busy = true;
    sim->due = now + sim->delay;
    if (command->type != SNAP_ROW) {
        uint64_t frame = (sim->due / FRAME_US + 1) * FRAME_US;
        sim->due = frame < sim->next_frame ? sim->next_frame : frame;
    }
    ++sim->submitted;
    return true;
}

static int poll_sim(void *context, uint64_t now)
{
    Simulator *sim = context;
    if (!sim->busy || now < sim->due)
        return 0;
    sim->busy = false;
    if (sim->fail_next) {
        sim->fail_next = false;
        return -1;
    }
    if (!execute(sim))
        return -1;
    if (sim->pending.type != SNAP_ROW) {
        sim->next_frame = (now / FRAME_US + 1) * FRAME_US;
        ++sim->commits;
    }
    return 1;
}

Backend simulator_backend(Simulator *sim)
{
    return (Backend){.context = sim, .submit = submit, .poll = poll_sim};
}

void simulator_reset(Simulator *sim, uint16_t chinese_count, uint64_t delay)
{
    memset(sim, 0, sizeof(*sim));
    sim->chinese_count = chinese_count;
    sim->delay = delay;
}
