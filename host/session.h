#ifndef SESSION_H
#define SESSION_H
#include <stdbool.h>
#include <sys/types.h>

typedef struct {
    int master;
    pid_t child;
    int status;
    bool reaped;
} Session;

bool session_start(Session *, char *const *, bool);
bool session_reap(Session *);
void session_stop(Session *);
#endif
