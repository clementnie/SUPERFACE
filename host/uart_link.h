#ifndef SUPERFACE_UART_LINK_H
#define SUPERFACE_UART_LINK_H

#include "superface.h"
#include <poll.h>

typedef struct UartLink UartLink;

UartLink *uart_link_open(const char *device, bool want_chinese, Terminal *, Keyboard *, bool legacy_only);
void uart_link_close(UartLink *);
struct pollfd uart_link_pollfd(const UartLink *);
bool uart_link_service(UartLink *, uint64_t now, short revents, bool display_active);
bool uart_link_connected(const UartLink *);
bool uart_link_chinese(const UartLink *);
void uart_link_restart(UartLink *);
Backend uart_link_backend(UartLink *);
bool uart_link_ping_pending(const UartLink *);
void uart_link_heartbeat(UartLink *, uint64_t);

#endif
