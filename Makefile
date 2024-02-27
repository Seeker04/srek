# MIT License
# Copyright (c) 2022 Barnabás Zahorán, see LICENSE

#================================ Parameters ==================================

CC            ?= cc  # use $CC if set, otherwise fall back to cc
CSTD           = c89
WFLAGS         = -ansi -pedantic -pedantic-errors -W -Wall -Wextra -Wconversion -Wfloat-equal -Wshadow
OFLAGS         = -O3
DFLAGS         = -D_POSIX_C_SOURCE=2
DEBUGFLAGS     = -Og -ggdb3 -fno-inline -fno-eliminate-unused-debug-symbols
SFLAGS         = -fsanitize=address,leak,undefined
INSTALLDIR     = /usr/local/bin
INSTALLDIR_MAN = /usr/local/share/man/man1

CFLAGS  = -std=$(CSTD) $(WFLAGS) $(OFLAGS) $(DFLAGS)
LDFLAGS =

INC = $(wildcard *.h)
SRC = $(wildcard *.c)
OBJ = $(SRC:%.c=%.o)
BIN = srek

VERSION = ${shell sed -n 's/^#define VERSION "\([^"]*\)"$$/\1/p' srek.c}

#================================== Build =====================================

build: $(BIN)

build-debug: CFLAGS += $(DEBUGFLAGS)
build-debug: rebuild

build-sanitized: CFLAGS  += $(SFLAGS) $(DEBUGFLAGS)
build-sanitized: LDFLAGS += $(SFLAGS)
build-sanitized: rebuild

$(BIN): $(OBJ)
	$(CC) $(LDFLAGS) $(OBJ) -o $(BIN)

%.o : %.c
	$(CC) -c $(CFLAGS) $< -o $@

clean:
	rm -f $(OBJ) $(BIN)

rebuild: clean build


#============================== Static checks =================================

cppcheck:
	cppcheck -q --enable=all --language=c --std=$(CSTD) --suppress=missingIncludeSystem $(SRC) $(INC)

clang-tidy:
	clang-tidy --checks='clang-analyzer-*' --header-filter=.* --extra-arg="-std=$(CSTD)" $(SRC) --


#============================= Runtime checks =================================

test:
	./runtests.py

#============================ Install/uninstall ===============================

install: $(BIN)
	install -D --mode=755 srek $(INSTALLDIR)/srek
	mkdir -p $(INSTALLDIR_MAN)
	sed 's/VERSION/$(VERSION)/' < srek.1 > $(INSTALLDIR_MAN)/srek.1
	chmod 644 $(INSTALLDIR_MAN)/srek.1

uninstall:
	rm -f $(INSTALLDIR)/$(BIN)

