#define _GNU_SOURCE
#include "view.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <wchar.h>

bool view_open(View *view)
{
    memset(view, 0, sizeof(*view));
    const char *name = ttyname(STDOUT_FILENO);
    view->fd = name ? open(name, O_WRONLY | O_NOCTTY | O_NONBLOCK | O_CLOEXEC) : -1;
    return view->fd >= 0;
}

bool view_update(View *view, const Simulator *sim)
{
    if (view->fd < 0 || view->length || view->commits == sim->commits)
        return true;
    if (!view->visible && sim->state != SIM_ACTIVE)
        return true;
    char *out = view->output;
    size_t length = 0;
#define APPEND(...) do { \
    size_t available = sizeof(view->output) - length; \
    int added = snprintf(out + length, available, __VA_ARGS__); \
    if (added < 0 || (size_t)added >= available) return false; \
    length += (size_t)added; \
} while (0)
    if (!view->visible)
        APPEND("\033[?1049h\033[?7l");
    APPEND("\033[?25l");
    unsigned last = 256;
    if (sim->state == SIM_ACTIVE) {
        for (unsigned row = 0; row < ROWS; ++row) {
            APPEND("\033[%u;1H", row + 1);
            for (unsigned col = 0; col < COLS; ++col) {
                const uint8_t *cell = sim->grid.rows[row] + CELL_BYTES * col;
                uint16_t id = cell_id(cell);
                if (id == CONTINUATION)
                    continue;
                if (cell[2] != last) {
                    unsigned fg = cell[2] & 15, bg = cell[2] >> 4;
                    APPEND("\033[%u;%um", fg < 8 ? 30 + fg : 82 + fg,
                           bg < 8 ? 40 + bg : 92 + bg);
                    last = cell[2];
                }
                APPEND("%lc", (wint_t)sf_scalar(id));
            }
        }
        const uint8_t *cursor = sim->grid.cursor;
        if (cursor[2])
            APPEND("\033[%u;%uH\033[?25h", cursor[0] + 1u, cursor[1] + 1u);
    } else {
        APPEND("\033[0m\033[2J");
    }
#undef APPEND
    view->commits = sim->commits;
    view->visible = true;
    view->sent = 0;
    view->length = length;
    return true;
}

bool view_flush(View *view)
{
    ssize_t n = write(view->fd, view->output + view->sent, view->length - view->sent);
    if (n < 0)
        return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR;
    view->sent += (size_t)n;
    if (view->sent == view->length)
        view->sent = view->length = 0;
    return true;
}

void view_close(View *view)
{
    if (view->fd >= 0) {
        if (view->visible) {
            static const char reset[] = "\033[0m\033[?25h\033[?7h\033[?1049l";
            if (write(view->fd, reset, sizeof(reset) - 1) < 0) {
                // The peer may already have disconnected.
            }
        }
        close(view->fd);
    }
}
