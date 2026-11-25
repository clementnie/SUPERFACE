CC ?= cc
PKG_CONFIG ?= pkg-config
PYTHON ?= python3
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror
VTERM_PREFIX ?= $(HOME)/.local/superface/libvterm-0.3.3
VTERM_CONFIG = PKG_CONFIG_PATH="$(VTERM_PREFIX)/lib/pkgconfig:$(PKG_CONFIG_PATH)" $(PKG_CONFIG)
VTERM_CFLAGS = $(shell $(VTERM_CONFIG) --cflags superface-vterm)
VTERM_LIBS = $(shell $(VTERM_CONFIG) --libs superface-vterm)
VTERM_DIR = $(shell $(VTERM_CONFIG) --variable=libdir superface-vterm)
VTERM_ARCHIVE = $(wildcard $(VTERM_DIR)/libvterm.a)
FONT = ../assets/fonts
COMMON = terminal.c keyboard.c display.c simulator.c

.PHONY: all check clean check-vterm
all: build/superface build/superface-uart

build:
	mkdir -p $@

build/font.inc: generate-font-table.py $(FONT)/glyph_map.csv $(FONT)/font_manifest.json | build
	$(PYTHON) $^ $@.tmp
	mv $@.tmp $@

check-vterm:
	@$(VTERM_CONFIG) --exists 'superface-vterm = 0.3.3' || 	    { echo "Build the pinned dependency with sh deps/build-libvterm.sh" >&2; exit 1; }

build/superface: main.c session.c view.c uart_link.c $(COMMON) superface.h session.h view.h uart_link.h build/font.inc $(VTERM_ARCHIVE) | check-vterm
	$(CC) $(CPPFLAGS) -Ibuild $(VTERM_CFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ main.c session.c view.c uart_link.c $(COMMON) $(VTERM_LIBS)

build/superface-uart: uart/diagnostic.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $<

build/test: test.c $(COMMON) superface.h build/font.inc $(VTERM_ARCHIVE) | check-vterm
	$(CC) $(CPPFLAGS) -Ibuild $(VTERM_CFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ test.c $(COMMON) $(VTERM_LIBS)

check: all build/test
	./build/test
	$(PYTHON) test-session.py
	$(PYTHON) test-uart.py
	$(PYTHON) test-uart-link.py
	$(PYTHON) test-batch.py

clean:
	rm -rf build
