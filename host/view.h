#ifndef SUPERFACE_VIEW_H
#define SUPERFACE_VIEW_H
#include "superface.h"

typedef struct {
    int fd;
    char output[65536];
    size_t sent, length;
    unsigned commits;
    bool visible;
} View;

bool view_open(View *);
bool view_update(View *, const Simulator *);
bool view_flush(View *);
void view_close(View *);
#endif
