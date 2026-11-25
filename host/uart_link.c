#define _GNU_SOURCE
#include "uart_link.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/serial.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/random.h>
#include <termios.h>
#include <unistd.h>

enum { HELLO = 1, HELLO_ACK = 2, EXT_HELLO = 3, PING = 0x15, KEY = 0x20, ACK = 0x7f };
enum { FLAG = 0x7e, ESCAPE = 0x7d, HEADER = 15, BODY_MAX = HEADER + PAYLOAD_MAX + 2,
       WIRE_MAX = 2 * BODY_MAX + 2 };
enum { ACK_US = 100000, HELLO_US = 250000, PING_US = 500000, SESSION_US = 2000000 };
typedef enum { NO_TX, PROBE_TX, REQUEST_TX, CONTROL_TX } TxKind;

typedef struct {
    uint8_t wire[WIRE_MAX];
    size_t length;
} Frame;

struct UartLink {
    const char *device;
    Terminal *terminal;
    Keyboard *keyboard;
    struct termios original;
    struct serial_icounter_struct counters;
    int fd;
    bool count_errors, font_requested, want_chinese, ask_chinese, chinese, connected, active;
    bool probe_extended, batch, legacy_only, extended_glyphs, legacy_mapping;
    uint64_t candidate, deadline, last_peer, last_request, reopen_at;
    unsigned sends;
    uint32_t next_seq, request_seq, key_next, key_last;
    uint16_t key_crc;
    uint8_t request_type, key_status;
    bool pending, control_pending, key_cached, renew, end_after_control;
    int result;
    Frame request, outgoing;
    TxKind tx;
    uint32_t tx_seq;
    size_t written;
    uint64_t drain_after;
    uint8_t body[BODY_MAX];
    size_t received;
    unsigned mark;
    bool armed, escaped;
    uint64_t last_rx;
    unsigned crc_errors, framing_errors, overruns, retries, sessions;
    unsigned spans, cursors, batches, staged_rows;
    uint64_t batch_at, batch_total_us, batch_max_us;
    uint64_t snapshot_at, span_total_us, span_max_us, cursor_max_us;
};

static bool temporary_error(void)
{
    return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR;
}

static void store_le(uint8_t *data, uint64_t value, unsigned width)
{
    for (unsigned i = 0; i < width; ++i) {
        data[i] = (uint8_t)value;
        value >>= 8;
    }
}

static uint64_t load_le(const uint8_t *data, unsigned width)
{
    uint64_t value = 0;
    while (width)
        value = (value << 8) | data[--width];
    return value;
}

static uint16_t crc_byte(uint16_t crc, uint8_t byte)
{
    crc ^= (uint16_t)byte << 8;
    for (unsigned i = 0; i < 8; ++i)
        crc = (uint16_t)((crc << 1) ^ (crc & 0x8000 ? 0x1021 : 0));
    return crc;
}

static void encode(Frame *frame, uint8_t type, uint64_t session, uint32_t seq,
                   const uint8_t *payload, size_t length)
{
    uint8_t body[BODY_MAX] = {1, type};
    store_le(body + 2, session, 8);
    store_le(body + 10, seq, 4);
    body[14] = (uint8_t)length;
    if (length)
        memcpy(body + HEADER, payload, length);
    uint16_t crc = 0xffff;
    for (size_t i = 0; i < HEADER + length; ++i)
        crc = crc_byte(crc, body[i]);
    store_le(body + HEADER + length, crc, 2);

    size_t pos = 0;
    frame->wire[pos++] = FLAG;
    for (size_t i = 0; i < HEADER + length + 2; ++i) {
        if (body[i] == FLAG || body[i] == ESCAPE) {
            frame->wire[pos++] = ESCAPE;
            frame->wire[pos++] = body[i] ^ 0x20;
        } else {
            frame->wire[pos++] = body[i];
        }
    }
    frame->wire[pos++] = FLAG;
    frame->length = pos;
}

static bool configure(UartLink *link)
{
    int fd = link->fd;
    if (tcgetattr(fd, &link->original))
        return false;
    struct termios tty = link->original;
    cfmakeraw(&tty);
    tty.c_iflag = INPCK | PARMRK;
    tty.c_oflag = tty.c_lflag = 0;
    tty.c_cflag &= ~(CSIZE | PARENB | PARODD | CSTOPB | CRTSCTS);
    tty.c_cflag |= CS8 | CLOCAL | CREAD;
    tty.c_cc[VMIN] = 1;
    tty.c_cc[VTIME] = 0;
    if (cfsetispeed(&tty, B3000000) || cfsetospeed(&tty, B3000000) ||
        tcsetattr(fd, TCSANOW, &tty))
        return false;
    if (!tcgetattr(fd, &tty) && cfgetispeed(&tty) == B3000000 &&
        cfgetospeed(&tty) == B3000000 && tty.c_iflag == (INPCK | PARMRK) &&
        !tty.c_lflag && !tty.c_oflag && tty.c_cc[VMIN] == 1 && !tty.c_cc[VTIME] &&
        (tty.c_cflag & (CSIZE | PARENB | CSTOPB | CRTSCTS | CLOCAL | CREAD))
        == (CS8 | CLOCAL | CREAD) && !tcflush(fd, TCIOFLUSH))
        return true;
    tcsetattr(fd, TCSANOW, &link->original);
    errno = EINVAL;
    return false;
}

static bool open_device(UartLink *link)
{
    int fd = open(link->device, O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0)
        return false;
    if (flock(fd, LOCK_EX | LOCK_NB) || ioctl(fd, TIOCEXCL)) {
        int saved = errno;
        close(fd);
        errno = saved;
        return false;
    }
    link->fd = fd;
    if (!configure(link)) {
        int saved = errno;
        ioctl(fd, TIOCNXCL);
        close(fd);
        link->fd = -1;
        errno = saved;
        return false;
    }
    link->count_errors = ioctl(fd, TIOCGICOUNT, &link->counters) == 0;
    link->tx = NO_TX;
    link->armed = link->escaped = false;
    link->received = link->mark = 0;
    return true;
}

static void close_device(UartLink *link)
{
    if (link->fd >= 0) {
        tcflush(link->fd, TCIOFLUSH);
        tcsetattr(link->fd, TCSANOW, &link->original);
        ioctl(link->fd, TIOCNXCL);
        close(link->fd);
        link->fd = -1;
    }
    link->tx = NO_TX;
}

UartLink *uart_link_open(const char *device, bool want_chinese, Terminal *terminal, Keyboard *keyboard, bool legacy_only)
{
    UartLink *link = calloc(1, sizeof(*link));
    if (!link)
        return NULL;
    link->fd = -1;
    link->device = device;
    link->terminal = terminal;
    link->keyboard = keyboard;
    link->legacy_only = legacy_only;
    link->probe_extended = !legacy_only;
    link->font_requested = link->want_chinese = link->ask_chinese = want_chinese;
    if (!open_device(link)) {
        free(link);
        return NULL;
    }
    return link;
}

void uart_link_close(UartLink *link)
{
    close_device(link);
    fprintf(stderr, "UART totals sessions=%u retries=%u crc_errors=%u framing_errors=%u overruns=%u\n",
            link->sessions, link->retries, link->crc_errors, link->framing_errors, link->overruns);
    if (link->spans)
        fprintf(stderr, "UART spans=%u mean_us=%" PRIu64 " max_us=%" PRIu64 "\n",
                link->spans, link->span_total_us / link->spans, link->span_max_us);
    if (link->cursors)
        fprintf(stderr, "UART cursors=%u max_us=%" PRIu64 "\n",
                link->cursors, link->cursor_max_us);
    if (link->batches)
        fprintf(stderr, "UART batches=%u staged_rows=%u mean_us=%" PRIu64 " max_us=%" PRIu64 "\n",
                link->batches, link->staged_rows, link->batch_total_us / link->batches, link->batch_max_us);
    free(link);
}

void uart_link_restart(UartLink *link)
{
    if (link->connected) {
        link->probe_extended = !link->legacy_only;
        link->want_chinese = link->ask_chinese = link->font_requested;
        link->legacy_mapping = false;
    }
    link->connected = false;
    link->batch_at = 0;
    link->pending = link->control_pending = link->key_cached = false;
    link->renew = link->end_after_control = false;
    link->result = 0;
    link->candidate = 0;
    link->deadline = 0;
    link->sends = 0;
    link->next_seq = link->key_next = 1;
    keyboard_reset(link->keyboard);
}

bool uart_link_connected(const UartLink *link)
{
    return link->connected;
}

bool uart_link_chinese(const UartLink *link)
{
    return link->chinese;
}

static bool new_probe(UartLink *link)
{
    uint64_t candidate;
    do {
        if (getrandom(&candidate, sizeof(candidate), 0) != (ssize_t)sizeof(candidate))
            return false;
    } while (!candidate);
    link->candidate = candidate;
    link->sends = 0;
    uint8_t wanted[18] = {0};
    if (link->ask_chinese) {
        store_le(wanted, link->legacy_mapping ? sf_chinese_count() : sf_font_count(), 2);
        memcpy(wanted + 2, link->legacy_mapping ? sf_legacy_mapping : sf_mapping, 16);
    }
    encode(&link->request, link->probe_extended ? EXT_HELLO : HELLO, candidate, 0, wanted, sizeof(wanted));
    return true;
}

static void handle_offer(UartLink *link, const uint8_t *p, size_t length, uint64_t now)
{
    static const uint8_t geometry[] = {COLS, ROWS, CELL_BYTES, PAYLOAD_MAX};
    static const uint8_t zero_mapping[16];
    if (length != 25 || p[1] > 4 || memcmp(p + 2, geometry, sizeof(geometry)) ||
        (link->probe_extended ? (p[6] != 15 && p[6] != 31) : p[6] != 7))
        goto reject;
    unsigned count = (unsigned)load_le(p + 7, 2);
    bool any_mapping = memcmp(p + 9, zero_mapping, 16) != 0;
    if ((p[1] == 0 && (!count || count > 16384 || !any_mapping)) ||
        (p[1] != 0 && (count || any_mapping)))
        goto reject;
    if (p[0] == 2 && link->ask_chinese) {
        link->legacy_mapping = p[1] == 0 && !link->legacy_mapping &&
                               count == sf_chinese_count() && !memcmp(p + 9, sf_legacy_mapping, 16);
        if (!link->legacy_mapping) {
            fprintf(stderr, "UART font status %u (loaded=%u, requested=%u), requesting ASCII mode\n",
                    p[1], count, sf_font_count());
            link->want_chinese = false;
        }
        goto reject;
    }
    if (link->ask_chinese) {
        if (p[0] != 1 || p[1] != 0 || count != (link->legacy_mapping ? sf_chinese_count() : sf_font_count()) ||
            memcmp(p + 9, link->legacy_mapping ? sf_legacy_mapping : sf_mapping, 16))
            goto reject;
    } else if (p[0] != 0) {
        goto reject;
    }
    link->chinese = link->ask_chinese;
    link->batch = link->probe_extended;
    link->extended_glyphs = (p[6] & 16) != 0;
    link->connected = true;
    link->next_seq = link->key_next = 1;
    link->last_peer = link->last_request = now;
    ++link->sessions;
    fprintf(stderr, "UART session %016" PRIx64 " established (%s)%s\n",
            link->candidate, link->chinese ? "Chinese" : "ASCII", link->batch ? " with frame batching" : "");
    return;

reject:
    uart_link_restart(link);
    link->ask_chinese = link->want_chinese;
}

static void handle_key(UartLink *link, const uint8_t *p, size_t length,
                       uint32_t seq, uint16_t crc, uint64_t now)
{
    if (seq == link->key_next && seq) {
        uint8_t status = 1;
        if (length == 1 && p[0] == 1) {
            keyboard_reset(link->keyboard);
            status = 0;
        } else if (length >= 2 && length <= 17 && p[0] == 0) {
            if (!link->active || terminal_keys(link->terminal, link->keyboard, p + 1, length - 1, now))
                status = 0;
        }
        link->key_cached = true;
        link->key_last = seq;
        link->key_crc = crc;
        link->key_status = status;
        ++link->key_next;
        link->end_after_control = status != 0 || link->key_next == 0;
        link->control_pending = true;
    } else if (link->key_cached && seq == link->key_last && crc == link->key_crc) {
        if (link->tx != CONTROL_TX || link->tx_seq != seq)
            link->control_pending = true;
    } else {
        return;
    }
    link->last_peer = now;
}

static void handle_body(UartLink *link, uint64_t now)
{
    const uint8_t *body = link->body;
    if (link->received < HEADER + 2 || link->received != HEADER + body[14] + 2u)
        return;
    uint16_t crc = 0xffff;
    for (size_t i = 0; i < link->received - 2; ++i)
        crc = crc_byte(crc, body[i]);
    if (crc != load_le(body + link->received - 2, 2)) {
        ++link->crc_errors;
        return;
    }
    if (body[0] != 1 || !link->candidate || load_le(body + 2, 8) != link->candidate)
        return;
    uint32_t seq = (uint32_t)load_le(body + 10, 4);
    const uint8_t *p = body + HEADER;
    size_t length = body[14];
    if (!link->connected) {
        if (body[1] == HELLO_ACK && seq == 0)
            handle_offer(link, p, length, now);
        return;
    }
    if (body[1] == KEY) {
        handle_key(link, p, length, seq, crc, now);
    } else if (body[1] == ACK && length == 2 && link->pending && seq == link->request_seq &&
               p[0] == link->request_type && p[1] <= 3) {
        link->last_peer = now;
        link->pending = false;
        if (p[1] != 0) {
            fprintf(stderr, "UART command %02x sequence %" PRIu32 " rejected (%u)\n",
                    p[0], seq, p[1]);
            uart_link_restart(link);
        } else if (p[0] != PING) {
            uint64_t elapsed = now - link->last_request;
            if (p[0] == SNAP_END) {
                link->active = true;
                fprintf(stderr, "UART snapshot committed in %" PRIu64 " us\n",
                        now - link->snapshot_at);
            } else if (p[0] == STAGE_SPAN) {
                ++link->staged_rows;
            } else if (p[0] == FRAME_COMMIT) {
                uint64_t duration = now - link->batch_at;
                ++link->batches;
                link->batch_total_us += duration;
                if (duration > link->batch_max_us)
                    link->batch_max_us = duration;
                link->batch_at = 0;
            } else if (p[0] == WRITE_SPAN) {
                ++link->spans;
                link->span_total_us += elapsed;
                if (elapsed > link->span_max_us)
                    link->span_max_us = elapsed;
            } else if (p[0] == CURSOR) {
                ++link->cursors;
                if (elapsed > link->cursor_max_us)
                    link->cursor_max_us = elapsed;
            }
            link->result = 1;
        }
    }
}

static void decode(UartLink *link, uint8_t byte, uint64_t now)
{
    link->last_rx = now;
    if (byte == FLAG) {
        if (link->armed && !link->escaped)
            handle_body(link, now);
        link->armed = true;
        link->escaped = false;
        link->received = 0;
    } else if (link->armed) {
        if (link->escaped) {
            link->escaped = false;
            if (byte != 0x5d && byte != 0x5e) {
                link->armed = false;
                return;
            }
            byte ^= 0x20;
        } else if (byte == ESCAPE) {
            link->escaped = true;
            return;
        }
        if (link->received >= BODY_MAX ||
            (link->received == HEADER - 1 && byte > PAYLOAD_MAX) ||
            (link->received >= HEADER && link->received >= HEADER + link->body[14] + 2u)) {
            link->armed = false;
            return;
        }
        link->body[link->received++] = byte;
    }
}

static void tty_byte(UartLink *link, uint8_t byte, uint64_t now)
{
    // PARMRK delivers FF FF for a literal FF and FF 00 xx for a bad byte.
    if (link->mark == 2) {
        link->mark = 0;
        ++link->framing_errors;
        link->armed = false;
    } else if (link->mark == 1) {
        link->mark = 0;
        if (!byte)
            link->mark = 2;
        else if (byte == 0xff)
            decode(link, byte, now);
        else
            link->armed = false;
    } else if (byte == 0xff) {
        link->mark = 1;
    } else {
        decode(link, byte, now);
    }
}

static bool receive(UartLink *link, uint64_t now)
{
    for (unsigned batch = 0; batch < 8; ++batch) {
        uint8_t bytes[1024];
        ssize_t count = read(link->fd, bytes, sizeof(bytes));
        if (count <= 0)
            return count < 0 && temporary_error();
        struct serial_icounter_struct current;
        if (link->count_errors && ioctl(link->fd, TIOCGICOUNT, &current) == 0) {
            if (current.overrun != link->counters.overrun ||
                current.buf_overrun != link->counters.buf_overrun) {
                link->overruns += (unsigned)current.overrun - (unsigned)link->counters.overrun;
                link->overruns += (unsigned)current.buf_overrun - (unsigned)link->counters.buf_overrun;
                uart_link_restart(link);
                link->armed = false;
                link->mark = 0;
                link->counters = current;
                continue;
            }
            link->counters = current;
        }
        for (ssize_t i = 0; i < count; ++i)
            tty_byte(link, bytes[i], now);
    }
    return true;
}

static void start_write(UartLink *link, TxKind tag, const Frame *frame, uint32_t seq)
{
    link->tx = tag;
    link->tx_seq = seq;
    if (frame != &link->outgoing)
        link->outgoing = *frame;
    link->written = 0;
    link->drain_after = 0;
}

static bool write_service(UartLink *link, uint64_t now)
{
    if (link->tx == NO_TX)
        return true;
    if (link->written < link->outgoing.length) {
        ssize_t n = write(link->fd, link->outgoing.wire + link->written,
                          link->outgoing.length - link->written);
        if (n < 0)
            return temporary_error();
        link->written += (size_t)n;
        if (link->written < link->outgoing.length)
            return true;
    }
    int count;
    if (ioctl(link->fd, TIOCOUTQ, &count))
        return false;
    if (count)
        return true;
    int state;
    if (ioctl(link->fd, TIOCSERGETLSR, &state) == 0) {
        if (!(state & TIOCSER_TEMT))
            return true;
    } else {
        if (errno != ENOTTY && errno != EINVAL && errno != EOPNOTSUPP)
            return temporary_error();
        // Some tty implementations report only the driver queue. Bound the
        // remaining hardware drain conservatively by a full frame at 3 Mbaud.
        if (!link->drain_after)
            link->drain_after = now + (10 * link->outgoing.length + 2) / 3;
        if (now < link->drain_after)
            return true;
    }

    if (link->tx == PROBE_TX && link->candidate && !link->connected && link->sends)
        link->deadline = now + HELLO_US;
    if (link->tx == REQUEST_TX && link->pending && link->request_seq == link->tx_seq)
        link->deadline = now + ACK_US;
    if (link->tx == CONTROL_TX && link->end_after_control && link->key_last == link->tx_seq)
        uart_link_restart(link);
    link->tx = NO_TX;
    return true;
}

static bool submit(void *context, const Command *cmd, uint64_t now)
{
    UartLink *link = context;
    if (!link->connected || link->pending || !link->next_seq)
        return false;
    link->request_seq = link->next_seq++;
    link->renew = !link->next_seq;
    link->request_type = cmd->type;
    encode(&link->request, cmd->type, link->candidate, link->request_seq, cmd->payload, cmd->length);
    link->pending = true;
    link->sends = 0;
    link->deadline = 0;
    link->last_request = now;
    if ((cmd->type == STAGE_SPAN || cmd->type == FRAME_COMMIT) && !link->batch_at)
        link->batch_at = now;
    if (cmd->type == SNAP_BEGIN || cmd->type == EXT_SNAP_BEGIN) {
        link->snapshot_at = now;
        link->active = false;
        keyboard_reset(link->keyboard);
    }
    return true;
}

static int result(void *context, uint64_t now)
{
    (void)now;
    UartLink *link = context;
    int value = link->result;
    link->result = 0;
    return link->connected ? value : -1;
}

Backend uart_link_backend(UartLink *link)
{
    return (Backend){link, submit, result, link->batch, link->extended_glyphs};
}

struct pollfd uart_link_pollfd(const UartLink *link)
{
    return (struct pollfd){.fd = link->fd,
        .events = POLLIN | (link->tx != NO_TX && link->written < link->outgoing.length ? POLLOUT : 0)};
}

bool uart_link_service(UartLink *link, uint64_t now, short revents, bool display_active)
{
    if (link->fd < 0) {
        if (now < link->reopen_at)
            return true;
        if (!open_device(link)) {
            link->reopen_at = now + PING_US;
            return true;
        }
    }
    link->active = display_active;
    keyboard_expire(link->keyboard, now);
    if (link->armed && (link->received || link->escaped || link->mark) &&
        now - link->last_rx >= ACK_US) {
        link->armed = false;
        link->mark = 0;
    }
    if (revents & (POLLERR | POLLHUP | POLLNVAL) ||
        ((revents & POLLIN) && !receive(link, now)) || !write_service(link, now)) {
        close_device(link);
        uart_link_restart(link);
        link->reopen_at = now + PING_US;
        return true;
    }
    if (link->connected && now - link->last_peer >= SESSION_US)
        uart_link_restart(link);
    if (link->tx != NO_TX)
        return true;

    if (link->control_pending) {
        uint8_t payload[] = {KEY, link->key_status};
        encode(&link->outgoing, ACK, link->candidate, link->key_last, payload, sizeof(payload));
        start_write(link, CONTROL_TX, &link->outgoing, link->key_last);
        link->control_pending = false;
    } else if (!link->connected && now >= link->deadline) {
        if (link->probe_extended && link->sends == 2) {
            link->probe_extended = false;
            link->candidate = 0;
        } else if (!link->legacy_only && !link->probe_extended && link->sends >= 8) {
            link->probe_extended = true;
        }
        if ((!link->candidate || link->sends >= 8) && !new_probe(link))
            return false;
        ++link->sends;
        start_write(link, PROBE_TX, &link->request, 0);
    } else if (link->pending && now >= link->deadline) {
        if (link->sends == 4) {
            uart_link_restart(link);
            return true;
        }
        if (link->sends)
            ++link->retries;
        ++link->sends;
        start_write(link, REQUEST_TX, &link->request, link->request_seq);
    } else if (link->connected && !link->pending && link->renew && !link->result) {
        uart_link_restart(link);
    }
    if (!write_service(link, now)) {
        close_device(link);
        uart_link_restart(link);
        link->reopen_at = now + PING_US;
    }
    return true;
}

// Schedule heartbeat after display_tick has had a chance to submit work.
bool uart_link_ping_pending(const UartLink *link)
{
    return link->connected && link->pending && link->request_type == PING;
}

void uart_link_heartbeat(UartLink *link, uint64_t now)
{
    if (link->connected && !link->pending && !link->renew && now - link->last_request >= PING_US) {
        const Command ping = {.type = PING};
        submit(link, &ping, now);
    }
}
