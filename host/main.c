#define _GNU_SOURCE
#include "session.h"
#include "superface.h"
#include "view.h"
#include "uart_link.h"

#include <errno.h>
#include <fcntl.h>
#include <langinfo.h>
#include <locale.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static struct termios saved_input;
static bool restore_input;

static void on_stop(int signal)
{
    stopped = signal;
}

static void restore(void)
{
    if (restore_input)
        tcsetattr(STDIN_FILENO, TCSANOW, &saved_input);
}

static bool configure_input(void)
{
    if (!isatty(STDIN_FILENO))
        return true;
    if (tcgetattr(STDIN_FILENO, &saved_input) < 0)
        return false;
    struct termios raw = saved_input;
    cfmakeraw(&raw);
    if (atexit(restore) != 0 || tcsetattr(STDIN_FILENO, TCSANOW, &raw) < 0)
        return false;
    restore_input = true;
    return true;
}

static uint64_t clock_us(void)
{
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0)
        exit(1);
    return (uint64_t)time.tv_sec * 1000000 + time.tv_nsec / 1000;
}

static bool transient(void)
{
    return errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK;
}

typedef enum { PTY_READ, PTY_WAIT_FOR_SLAVE, PTY_END, PTY_READ_ERROR } PtyRead;

static PtyRead pty_read(Session *session, Terminal *terminal)
{
    char buffer[PTY_CHUNK];
    for (unsigned chunk = 0; chunk < 16; ++chunk) {
        ssize_t read_bytes = read(session->master, buffer, sizeof(buffer));
        if (read_bytes > 0) {
            if (!terminal_feed(terminal, buffer, (size_t)read_bytes))
                return PTY_READ_ERROR;
            if (terminal->input.length > INPUT_CAPACITY - INPUT_RESERVE)
                break;
        } else if (!read_bytes || errno == EIO) {
            // login can close and reopen the slave. Keep its master alive.
            return session->reaped ? PTY_END : PTY_WAIT_FOR_SLAVE;
        } else {
            return transient() ? PTY_READ : PTY_READ_ERROR;
        }
    }
    return PTY_READ;
}

static bool pty_write(Session *session, InputQueue *queue)
{
    ssize_t written = write(session->master, queue->data + queue->head, queue->length);
    if (written > 0)
        input_consume(queue, (size_t)written);
    return written >= 0 || transient() || errno == EIO;
}

static bool dump_grid(const Simulator *sim)
{
    if (sim->state != SIM_ACTIVE)
        return false;
    for (unsigned row = 0; row < ROWS; ++row) {
        for (unsigned col = 0; col < COLS; ++col) {
            const uint8_t *p = sim->grid.rows[row] + col * CELL_BYTES;
            if (printf("%02x%02x%02x%s", p[0], p[1], p[2], col + 1 == COLS ? "\n" : " ") < 0)
                return false;
        }
    }
    return printf("cursor %u %u %u\n", sim->grid.cursor[0], sim->grid.cursor[1],
                  sim->grid.cursor[2]) >= 0 && fflush(stdout) == 0;
}

static int run_loop(Session *session, Terminal *terminal, bool local_input, bool dump,
                    View *view, UartLink *uart, Keyboard *keyboard)
{
    Display display;
    Simulator simulator;
    simulator_reset(&simulator, terminal->font ? sf_chinese_count() : 0, 0);
    display_connect(&display, simulator_backend(&simulator));
    if (uart)
        display.state = OFFLINE;
    short uart_events = 0;
    bool eof = false, input_eof = !local_input;
    uint64_t reaped_at = 0, eof_at = 0, master_retry_at = 0;
    while (!stopped) {
        uint64_t now = clock_us();
        if (!session_reap(session))
            return 1;
        if (session->reaped && !reaped_at)
            reaped_at = now;
        if (reaped_at && now - reaped_at > 1000000 && !eof)
            return 1; // A descendant is still holding or flooding the slave.
        if (eof && !eof_at)
            eof_at = now;
        if (uart) {
            if (!uart_link_service(uart, now, uart_events, display.state == ACTIVE))
                return 1;
            if (!uart_link_connected(uart)) {
                display.state = OFFLINE;
            } else if (display.state == OFFLINE) {
                terminal_set_font(terminal, uart_link_chinese(uart));
                Backend backend = uart_link_backend(uart);
                terminal_set_extended(terminal, backend.extended_glyphs);
                display_connect(&display, backend);
            }
        }
        // Use a steady final image for the explicit development dump.
        terminal_refresh(terminal, eof && dump ? 0 : now);
        if (display.state != OFFLINE && (!uart || !uart_link_ping_pending(uart)) &&
            !display_tick(&display, &terminal->desired, now)) {
            if (uart) {
                uart_link_restart(uart);
            } else {
                simulator_reset(&simulator, simulator.chinese_count, simulator.delay);
                display_connect(&display, simulator_backend(&simulator));
                keyboard_reset(keyboard);
                view->commits = 0;
            }
        }
        if (uart) {
            uart_link_heartbeat(uart, now);
            // Start a newly submitted command before yielding to poll.
            if (!uart_link_service(uart, now, 0, display.state == ACTIVE))
                return 1;
        }
        if (!view_update(view, &simulator))
            return 1;
        if (eof && session->reaped && display_synced(&display, &terminal->desired) && !view->length) {
            if (dump && !dump_grid(&simulator))
                return 1;
            if (WIFEXITED(session->status))
                return WEXITSTATUS(session->status);
            return 128 + WTERMSIG(session->status);
        }
        if (eof_at && now - eof_at > 3000000)
            return 1;

        int master = now >= master_retry_at || session->reaped ? session->master : -1;
        struct pollfd fds[] = {{.fd = master}, {.fd = -1},
                               {.fd = view->length ? view->fd : -1, .events = POLLOUT},
                               uart ? uart_link_pollfd(uart) : (struct pollfd){.fd = -1}};
        if (terminal->input.length <= INPUT_CAPACITY - INPUT_RESERVE)
            fds[0].events = POLLIN;
        if (terminal->input.length)
            fds[0].events |= POLLOUT;
        if (!input_eof && !eof && terminal->input.length < INPUT_CAPACITY - INPUT_RESERVE) {
            fds[1].fd = STDIN_FILENO;
            fds[1].events = POLLIN;
        }
        int ready = poll(fds, sizeof(fds) / sizeof(fds[0]),
                         uart ? 2 : display.in_flight ||
                         !display_synced(&display, &terminal->desired) ? 4 : 50);
        uart_events = ready > 0 ? fds[3].revents : 0;
        if (ready < 0 && errno != EINTR)
            return 1;
        if (ready <= 0)
            continue;
        if ((fds[2].revents & POLLOUT) && !view_flush(view))
            return 1;
        if (fds[2].revents & (POLLERR | POLLHUP | POLLNVAL))
            return 1;
        if (fds[0].revents & POLLNVAL)
            return 1;
        if (fds[0].revents & (POLLIN | POLLHUP | POLLERR)) {
            switch (pty_read(session, terminal)) {
            case PTY_READ:
                break;
            case PTY_WAIT_FOR_SLAVE:
                master_retry_at = now + 20000;
                break;
            case PTY_END:
                close(session->master);
                session->master = -1;
                eof = true;
                break;
            case PTY_READ_ERROR:
                return 1;
            }
        }
        if (!eof && now >= master_retry_at && terminal->input.length && fds[0].revents & POLLOUT &&
            !pty_write(session, &terminal->input))
            return 1;
        if (!eof && fds[1].revents & (POLLIN | POLLHUP)) {
            char input[PTY_CHUNK];
            ssize_t n = read(STDIN_FILENO, input, sizeof(input));
            if (n == 0)
                input_eof = true;
            else if (n < 0 && !transient())
                return 1;
            else if (n > 0 && !terminal_input(terminal, input, (size_t)n))
                return 1;
        }
        if (fds[1].revents & (POLLERR | POLLNVAL))
            return 1;
    }
    return 128 + stopped;
}

int main(int argc, char **argv)
{
    bool font = true, local_input = false, dump = false, login = false, live = false;
    const char *uart_device = NULL;
    bool colemak = false, legacy_wire = false, layout_set = false;
    int i = 1;
    for (; i < argc && strcmp(argv[i], "--"); ++i) {
        if (!strcmp(argv[i], "--ascii"))
            font = false;
        else if (!strcmp(argv[i], "--stdin"))
            local_input = true;
        else if (!strcmp(argv[i], "--dump"))
            dump = true;
        else if (!strcmp(argv[i], "--view"))
            live = true;
        else if (!strcmp(argv[i], "--uart") && !uart_device && i + 1 < argc)
            uart_device = argv[++i];
        else if (!strcmp(argv[i], "--keyboard") && !layout_set && i + 1 < argc) {
            const char *layout = argv[++i];
            if (strcmp(layout, "colemak") && strcmp(layout, "qwerty"))
                goto usage;
            colemak = !strcmp(layout, "colemak");
            layout_set = true;
        } else if (!strcmp(argv[i], "--legacy-wire"))
            legacy_wire = true;
        else if (!strcmp(argv[i], "--login"))
            login = true;
        else
            goto usage;
    }
    if (login) {
        if (getuid() != 0 || geteuid() != 0 ||
            i != argc || !font || local_input || dump || live || legacy_wire ||
            argc != 2 + (uart_device ? 2 : 0) + (layout_set ? 2 : 0) ||
            (uart_device && strcmp(uart_device, "/dev/ttyS2")))
            goto usage;
        local_input = true;
        live = uart_device == NULL;
    } else if (getuid() == 0 || geteuid() != getuid()) {
        fputs("Development mode requires an ordinary unprivileged user.\n", stderr);
        return 2;
    }
    if (uart_device && (live || dump))
        goto usage;
    if (live && (dump || !isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO)))
        goto usage;
    local_input |= live;
    if (i < argc && ++i == argc)
        goto usage;
    if (!setlocale(LC_ALL, "C.UTF-8") || strcmp(nl_langinfo(CODESET), "UTF-8")) {
        fputs("The C.UTF-8 locale is required.\n", stderr);
        return 1;
    }
    if (local_input && !configure_input()) {
        perror("Configure local input");
        return 1;
    }
    struct sigaction action = {.sa_handler = on_stop};
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) || sigaction(SIGHUP, &action, NULL) ||
        sigaction(SIGINT, &action, NULL) || sigaction(SIGQUIT, &action, NULL)) {
        perror("Install signal handlers");
        return 1;
    }
    char *shell = getenv("SHELL");
    if (!shell || !*shell)
        shell = "/bin/sh";
    char *default_args[] = {shell, "-i", NULL};
    View view = {.fd = -1};
    if (live && !view_open(&view)) {
        perror("Open private display tty");
        return 1;
    }
    Session session;
    if (!session_start(&session, i < argc ? argv + i : default_args, login)) {
        view_close(&view);
        perror("Start PTY session");
        return 1;
    }
    Terminal terminal;
    if (!terminal_init(&terminal, font)) {
        view_close(&view);
        session_stop(&session);
        return 1;
    }
    Keyboard keyboard = {.colemak = colemak};
    UartLink *uart = uart_device ? uart_link_open(uart_device, font, &terminal, &keyboard, legacy_wire) : NULL;
    int status;
    if (uart_device && !uart) {
        perror("Open exclusive 3 Mbaud UART");
        status = 1;
    } else {
        status = run_loop(&session, &terminal, local_input, dump, &view, uart, &keyboard);
    }
    if (uart)
        uart_link_close(uart);
    view_close(&view);
    session_stop(&session);
    terminal_destroy(&terminal);
    return status;

usage:
    fputs("Usage: superface [--ascii] [--legacy-wire] [--keyboard qwerty|colemak] [--stdin] [--dump | --view | --uart DEVICE] [-- command [args...]]\n"
          "       superface --login [--keyboard qwerty|colemak] [--uart /dev/ttyS2]\n", stderr);
    return 2;
}
