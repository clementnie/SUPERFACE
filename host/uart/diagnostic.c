#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/serial.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

enum { BLOCK = 4096, WINDOW = 16384, PATTERN_BYTES = 4 * BLOCK };
static volatile sig_atomic_t stop;

static void interrupt(int sig)
{
    stop = sig;
}

static uint64_t millis(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) < 0)
        exit(1);
    return (uint64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static uint8_t pattern(size_t offset, bool tx_only)
{
    static const uint8_t patterns[] = {0x00, 0xff, 0x55, 0xaa};
    if (tx_only)
        return 0x55;
    if (offset < PATTERN_BYTES)
        return patterns[offset / BLOCK];
    // Counter-based deterministic stream, independent of syscall boundaries.
    uint32_t value = (uint32_t)offset;
    value ^= value >> 16;
    value *= UINT32_C(0x7feb352d);
    value ^= value >> 15;
    value *= UINT32_C(0x846ca68b);
    return (uint8_t)(value ^ (value >> 16));
}

static uint32_t crc_update(uint32_t crc, uint8_t byte)
{
    static const uint32_t nibble[16] = {
        0, 0x1db71064, 0x3b6e20c8, 0x26d930ac, 0x76dc4190, 0x6b6b51f4,
        0x4db26158, 0x5005713c, 0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
        0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c
    };
    crc ^= byte;
    crc = (crc >> 4) ^ nibble[crc & 15];
    return (crc >> 4) ^ nibble[crc & 15];
}

static bool is_uart2(int fd)
{
    struct stat statbuf;
    if (fstat(fd, &statbuf) || !S_ISCHR(statbuf.st_mode))
        return false;
    char syslink[128], device[PATH_MAX], path[PATH_MAX + 16], link[PATH_MAX];
    snprintf(syslink, sizeof(syslink), "/sys/dev/char/%u:%u",
             major(statbuf.st_rdev), minor(statbuf.st_rdev));
    if (!realpath(syslink, device))
        return false;
    // Recent serial-base kernels put the 8250 controller above wrapper devices.
    while (!strncmp(device, "/sys/devices/", 13)) {
        snprintf(path, sizeof(path), "%s/of_node", device);
        ssize_t length = readlink(path, link, sizeof(link) - 1);
        if (length > 0) {
            link[length] = 0;
            const char *name = strrchr(link, '/');
            if (name && !strcmp(name, "/serial@5000800")) {
                snprintf(path, sizeof(path), "%s/driver", device);
                return readlink(path, link, sizeof(link) - 1) > 0;
            }
        }
        *strrchr(device, '/') = 0;
    }
    return false;
}

static bool configure(int fd, const struct termios *original)
{
    struct termios current = *original;
    current.c_iflag = current.c_oflag = current.c_lflag = 0;
    current.c_cflag &= ~(CSIZE | PARENB | PARODD | CSTOPB | CRTSCTS);
    current.c_cflag |= CS8 | CLOCAL | CREAD;
    current.c_cc[VMIN] = 1;
    current.c_cc[VTIME] = 0;
    if (cfsetispeed(&current, B3000000) || cfsetospeed(&current, B3000000) ||
        tcsetattr(fd, TCSANOW, &current) || tcgetattr(fd, &current))
        return false;
    if (cfgetispeed(&current) != B3000000 || cfgetospeed(&current) != B3000000 ||
        (current.c_cflag & (CSIZE | PARENB | CSTOPB | CRTSCTS | CLOCAL | CREAD))
            != (CS8 | CLOCAL | CREAD) ||
        current.c_iflag || current.c_lflag || current.c_oflag ||
        current.c_cc[VMIN] != 1 || current.c_cc[VTIME] != 0) {
        errno = EINVAL;
        return false;
    }
    return tcflush(fd, TCIOFLUSH) == 0;
}

static bool retry(void)
{
    return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR;
}

static bool transfer(int fd, size_t count, bool tx_only)
{
    size_t sent = 0, received = 0, first_error = SIZE_MAX, differences = 0;
    uint32_t sent_crc = UINT32_MAX, received_crc = UINT32_MAX;
    uint64_t began = millis(), deadline = began + 3000;
    while (!stop && millis() < deadline && (sent < count || (!tx_only && received < count))) {
        size_t limit = count - sent;
        if (!tx_only) {
            size_t outstanding = sent - received;
            if (limit > WINDOW - outstanding)
                limit = WINDOW - outstanding;
        }
        struct pollfd event = {.fd = fd, .events = POLLIN | (limit ? POLLOUT : 0)};
        int ready = poll(&event, 1, 50);
        if (ready < 0 && retry())
            continue;
        if (ready < 0 || event.revents & (POLLNVAL | POLLERR | POLLHUP))
            break;
        uint8_t bytes[BLOCK];
        if (event.revents & POLLIN) {
            ssize_t n = read(fd, bytes, sizeof(bytes));
            if (n < 0 && !retry())
                break;
            if (n > 0 && !tx_only) {
                for (ssize_t i = 0; i < n; ++i) {
                    if (bytes[i] != pattern(received, false) || received >= sent) {
                        if (!differences)
                            first_error = received;
                        ++differences;
                    }
                    ++received;
                    received_crc = crc_update(received_crc, bytes[i]);
                }
                if (received > sent)
                    break;
                deadline = millis() + 3000;
            }
        }
        if (event.revents & POLLOUT) {
            if (limit > sizeof(bytes))
                limit = sizeof(bytes);
            for (size_t i = 0; i < limit; ++i)
                bytes[i] = pattern(sent + i, tx_only);
            ssize_t n = write(fd, bytes, limit);
            if (n < 0 && !retry())
                break;
            if (n > 0) {
                sent += (size_t)n;
                for (ssize_t i = 0; i < n; ++i)
                    sent_crc = crc_update(sent_crc, bytes[i]);
                deadline = millis() + 3000;
            }
        }
    }

    bool empty = !tx_only;
    while (tx_only && !stop && sent == count && millis() < deadline) {
        int pending, state;
        if (ioctl(fd, TIOCOUTQ, &pending) < 0)
            break;
        if (!pending) {
            if (ioctl(fd, TIOCSERGETLSR, &state) == 0) {
                if ((state & TIOCSER_TEMT) != 0) {
                    empty = true;
                    break;
                }
            } else if (errno == ENOTTY || errno == EINVAL) {
                // Allow an entire hardware FIFO to shift at the configured rate.
                poll(NULL, 0, 100);
                empty = !stop;
                break;
            } else {
                break;
            }
        }
        poll(NULL, 0, 2);
    }
    printf("tx=%zu crc32=%08" PRIx32 " rx=%zu crc32=%08" PRIx32 " elapsed_ms=%" PRIu64 "\n",
           sent, ~sent_crc, received, ~received_crc, millis() - began);
    if (differences)
        fprintf(stderr, "mismatches=%zu first_offset=%zu\n", differences, first_error);
    return !stop && sent == count && (tx_only ? empty :
           (received == count && !differences && sent_crc == received_crc));
}

enum { WIRE_TEST_BYTES = 18300000, WIRE_TEST_HEADER = 2, WIRE_TEST_TRAILER = 20 };

static uint8_t wire_pattern(size_t index, uint8_t direction)
{
    return (uint8_t)(index ^ (index >> 8) ^ (index >> 16)) ^ direction;
}

static uint32_t wire_u32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static bool full_duplex(int fd, size_t count)
{
    const uint8_t header[WIRE_TEST_HEADER] = {'S', 'F'};
    uint8_t trailer[WIRE_TEST_TRAILER] = {0};
    size_t sent = 0, received = 0, mismatches = 0;
    const size_t write_limit = count + sizeof(header), read_limit = count + sizeof(trailer);
    uint32_t sent_crc = UINT32_MAX, received_crc = UINT32_MAX;
    uint64_t began = millis(), deadline = began + 3000;

    while (!stop && millis() < deadline && (sent < write_limit || received < read_limit)) {
        struct pollfd fd_to_poll = {.fd = fd, .events = POLLIN | (sent < write_limit ? POLLOUT : 0)};
        int ready = poll(&fd_to_poll, 1, 50);
        if (ready < 0 && retry())
            continue;
        if (ready < 0 || fd_to_poll.revents & (POLLNVAL | POLLERR | POLLHUP))
            break;
        uint8_t bytes[BLOCK];
        if (fd_to_poll.revents & POLLIN) {
            ssize_t used = read(fd, bytes, sizeof(bytes));
            if (used < 0 && !retry())
                break;
            if (used > 0 && (size_t)used > read_limit - received) {
                ++mismatches;
                break;
            }
            for (ssize_t i = 0; i < used; ++i, ++received) {
                if (received < count) {
                    mismatches += bytes[i] != wire_pattern(received, 0xa5);
                    received_crc = crc_update(received_crc, bytes[i]);
                } else {
                    trailer[received - count] = bytes[i];
                }
            }
            if (used > 0)
                deadline = millis() + 3000;
        }
        if (fd_to_poll.revents & POLLOUT) {
            size_t chunk = write_limit - sent;
            if (chunk > sizeof(bytes))
                chunk = sizeof(bytes);
            for (size_t i = 0; i < chunk; ++i) {
                size_t offset = sent + i;
                bytes[i] = offset < sizeof(header) ? header[offset] :
                           wire_pattern(offset - sizeof(header), 0x5a);
            }
            ssize_t used = write(fd, bytes, chunk);
            if (used < 0 && !retry())
                break;
            for (ssize_t i = 0; i < used; ++i, ++sent)
                if (sent >= sizeof(header))
                    sent_crc = crc_update(sent_crc, bytes[i]);
            if (used > 0)
                deadline = millis() + 3000;
        }
    }

    uint64_t elapsed = millis() - began;
    size_t sent_data = sent > sizeof(header) ? sent - sizeof(header) : 0;
    size_t received_data = received < count ? received : count;
    printf("duplex tx=%zu crc32=%08" PRIx32 " rx=%zu crc32=%08" PRIx32
           " elapsed_ms=%" PRIu64 " mismatches=%zu\n",
           sent_data, ~sent_crc, received_data, ~received_crc, elapsed, mismatches);
    if (elapsed)
        printf("mean_payload_byte_rate tx=%.1f/s rx=%.1f/s\n",
               1000.0 * sent_data / elapsed, 1000.0 * received_data / elapsed);
    if (memcmp(trailer, "SF5R", 4) || received != read_limit) {
        fputs("Missing FPGA wire-test trailer. Check FPGA reset and the bench image.\n", stderr);
        return false;
    }
    uint32_t peer_count = wire_u32(trailer + 4);
    uint32_t peer_rx_crc = wire_u32(trailer + 8), peer_tx_crc = wire_u32(trailer + 12);
    uint32_t peer_framing = wire_u32(trailer + 16);
    printf("fpga rx=%" PRIu32 " rx_crc32=%08" PRIx32 " tx_crc32=%08" PRIx32
           " framing_errors=%" PRIu32 "\n", peer_count, peer_rx_crc, peer_tx_crc, peer_framing);
    return !stop && sent == write_limit && !mismatches && peer_count == count &&
           !peer_framing && peer_rx_crc == ~sent_crc && peer_tx_crc == ~received_crc;
}

int main(int argc, char **argv)
{
    bool check = argc == 3 && !strcmp(argv[1], "--check");
    bool loop = argc == 4 && !strcmp(argv[1], "--loopback");
    bool scope = argc == 4 && !strcmp(argv[1], "--scope-55");
    bool wire = argc == 3 && !strcmp(argv[1], "--wire-rate");
    bool pty_wire = argc == 4 && !strcmp(argv[1], "--pty-wire-test");
    bool test_pty = argc == 4 && (!strcmp(argv[1], "--pty-test") || pty_wire) &&
                    !strncmp(argv[2], "/dev/pts/", 9) && strspn(argv[2] + 9, "0123456789") &&
                    strspn(argv[2] + 9, "0123456789") == strlen(argv[2] + 9);
    size_t count = wire ? WIRE_TEST_BYTES : 0;
    if (!check && !loop && !scope && !wire && !test_pty)
        goto usage;
    if (!check && !wire) {
        char *end;
        errno = 0;
        unsigned long value = strtoul(argv[3], &end, 10);
        if (*end || errno || value < PATTERN_BYTES || value > 100000000)
            goto usage;
        count = value;
    }
    struct sigaction action = {.sa_handler = interrupt};
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL) ||
        sigaction(SIGHUP, &action, NULL)) {
        perror("signal handlers");
        return 1;
    }
    int fd = open(argv[2], O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) {
        perror("open tty");
        return 1;
    }
    if ((!test_pty && !is_uart2(fd)) || !isatty(fd)) {
        fputs("TTY must resolve to Orange Pi UART2 at serial@5000800.\n", stderr);
        close(fd);
        return 1;
    }
    if (flock(fd, LOCK_EX | LOCK_NB) || ioctl(fd, TIOCEXCL)) {
        perror("exclusive tty ownership");
        close(fd);
        return 1;
    }
    struct termios original;
    if (tcgetattr(fd, &original)) {
        perror("read original termios");
        ioctl(fd, TIOCNXCL);
        close(fd);
        return 1;
    }
    bool ok = configure(fd, &original);
    if (!ok) {
        perror("configure 3000000 baud");
    } else {
        puts("termios readback 3000000 8N1 raw, no flow control");
        struct serial_struct serial;
        if (ioctl(fd, TIOCGSERIAL, &serial) == 0 && serial.baud_base > 0) {
            uint64_t base = (unsigned)serial.baud_base;
            uint64_t divisor = (base + 1500000) / 3000000;
            printf("TIOCGSERIAL baud_base=%d reference_hz=%" PRIu64 " divisor=%" PRIu64 "\n",
                   serial.baud_base, base * 16, divisor);
            ok = divisor && base >= 2970000 * divisor && base <= 3030000 * divisor;
            if (divisor)
                printf("predicted_integer_baud=%.3f\n", (double)base / divisor);
        } else if (!test_pty) {
            ok = false;
        }
        if (!ok)
            fputs("Driver clock evidence does not support 3 Mbaud with integer divisors.\n", stderr);
        struct serial_icounter_struct before, after;
        bool counters = ioctl(fd, TIOCGICOUNT, &before) == 0;
        if (ok && !check)
            ok = (wire || pty_wire) ? full_duplex(fd, count) : transfer(fd, count, scope);
        if (counters && ioctl(fd, TIOCGICOUNT, &after) == 0) {
#define DELTA(field) ((unsigned)after.field - (unsigned)before.field)
            printf("counters tx=%u rx=%u frame=%u overrun=%u parity=%u break=%u buf_overrun=%u\n",
                   DELTA(tx), DELTA(rx), DELTA(frame), DELTA(overrun), DELTA(parity),
                   DELTA(brk), DELTA(buf_overrun));
            ok = ok && !(DELTA(frame) || DELTA(overrun) || DELTA(parity) ||
                         DELTA(brk) || DELTA(buf_overrun));
#undef DELTA
        } else {
            puts("TIOCGICOUNT unavailable");
        }
    }
    if (!ok) // Discard unfinished diagnostics before restoring the old configuration.
        tcflush(fd, TCIOFLUSH);
    if (tcsetattr(fd, TCSANOW, &original)) {
        perror("restore termios");
        ok = false;
    }
    // Release exclusivity even when another process retained an earlier descriptor.
    if (ioctl(fd, TIOCNXCL) < 0)
        ok = false;
    close(fd);
    return ok && !stop ? 0 : 1;

usage:
    fputs("Usage: superface-uart --check TTY\n"
          "       superface-uart --loopback TTY BYTES\n"
          "       superface-uart --scope-55 TTY BYTES\n"
          "       superface-uart --wire-rate TTY\n"
          "       superface-uart --pty-test /dev/pts/N BYTES\n", stderr);
    return 2;
}
