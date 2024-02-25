#!/usr/bin/env python3

# srek - Structural RegEx Kit
#
# MIT License
# Copyright (c) 2022 Barnabás Zahorán, see LICENSE
#
# Test tool for running dynamic tests

import os
import subprocess
from colorama import Fore, Back, Style

TIMEOUT_TRESHOLD          = 5
TIMEOUT_TRESHOLD_VALGRIND = 30

VALGRIND_CMD = ["valgrind", "--leak-check=full", "--show-leak-kinds=all", "--error-exitcode=1", "-q"]

passedcnt = 0
failedcnt = 0
index = 0
failedlist = []

def testexec(testcase, usevalgrind = False, inputtostdin = False, fromscript = False):
    global passedcnt, failedcnt, index, failedlist

    print("[#" + str(index) + "] Testcase:", testcase["name"])
    index += 1
    failed = False

    stdin = ""
    if inputtostdin:
        if testcase.get("stdin_test_not_applicable", False):
            print(Back.BLUE + Fore.WHITE + "Not applicable" + Style.RESET_ALL)
            return

        for fname in testcase.get("files", []):
            if fname.startswith("file_that_probably_dont_exist") or fname == ".":
                continue
            f = open(fname, "r")
            stdin += f.read()
            f.close()

    if fromscript:
        if testcase.get("script_test_not_applicable", False):
            print(Back.BLUE + Fore.WHITE + "Not applicable" + Style.RESET_ALL)
            return
        f = open("temp_testscript_temp", "w")
        f.write(testcase.get("cmdline", ""))
        f.close()

    try:
        procinfo = subprocess.run(
            args = (VALGRIND_CMD if usevalgrind else []) +
                   ["./srek"] +
                   testcase.get("options", []) + (["--file=temp_testscript_temp"] if fromscript else []) +
                   (([testcase.get("cmdline")] if "cmdline" in testcase else []) if not fromscript else []) +
                   (testcase.get("files", []) if not inputtostdin else []),
            input = bytes(stdin, "ASCII") if inputtostdin else None,
            capture_output = True,
            timeout = testcase.get("timeout", TIMEOUT_TRESHOLD_VALGRIND if usevalgrind else TIMEOUT_TRESHOLD)
        )
        # uncomment these line for "debugging" output mismatches
        # print(procinfo.stdout)
        # print(procinfo.stderr)

        if procinfo.returncode != testcase.get("expectederr", 0):
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "srek exited with error",
                  str(procinfo.returncode) + ", stderr: ", procinfo.stderr)
            failed = True

        elif testcase.get("expectederr", 0) != 0 and procinfo.stderr == b"":
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "exited with error, but stderr is empty")
            failed = True

        elif procinfo.stdout != testcase["expectedout"]:
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "output differs from expected")
            failed = True

        elif testcase.get("shouldprinterr", False) and procinfo.stderr == b"":
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "some error message was expected but not given")
            failed = True

        else:
            i = 0
            for fname in testcase.get("newfilenames", []):
                f = open(fname, "r")
                if not os.path.exists(fname):
                    print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "output file was not created")
                    failed = True
                    break
                if f.read() != testcase["newfilecontents"][i]:
                    print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "output file differs from expected")
                    failed = True
                    break
                i += 1
                f.close()
    except subprocess.TimeoutExpired:
        print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "timed out")
        failed = True

    for fname in testcase.get("newfilenames", []): # cleanup generated files
        os.remove(fname)
    if fromscript:
        os.remove("temp_testscript_temp")

    if failed:
        failedcnt += 1
        failedlist.append({ "index": index, "name": testcase["name"] })
    else:
        print(Back.GREEN + Fore.BLACK + "Passed" + Style.RESET_ALL)
        passedcnt += 1


testcases = [
# cmd-line related
    {
    "name"        : "no cmdline",
    "files"       : [],
    "expectedout" : b"",
    "expectederr" : 1,
    "script_test_not_applicable" : True
    },
    {
    "name"        : "empty cmdline, implicit p",
    "cmdline"     : "",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "empty cmdline, quiet",
    "options"     : ["-n"],
    "cmdline"     : "",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "invalid cmdline, non-existent cmd",
    "cmdline"     : "n/foo/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 2
    },
    {
    "name"        : "invalid cmdline, arg list without cmd",
    "cmdline"     : "/foo/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 2
    },
    {
    "name"        : "invalid cmdline, unterminated cmd",
    "cmdline"     : "x/foo",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 2
    },
    {
    "name"        : "invalid cmdline, incorrect regex #1",
    "cmdline"     : "x/[abc/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 5
    },
    {
    "name"        : "invalid cmdline, incorrect regex #2",
    "cmdline"     : "x/*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 5
    },

# negative file I/O tests
    {
    "name"        : "input file does not exist",
    "cmdline"     : "p",
    "files"       : ["file_that_probably_dont_exist"],
    "expectedout" : b"",
    "expectederr" : 3,
    "stdin_test_not_applicable" : True
    },
    {
    "name"        : "input file unreadable (dir)",
    "cmdline"     : "p",
    "files"       : ["."],
    "expectedout" : b"",
    "expectederr" : 3,
    "stdin_test_not_applicable" : True
    },
    {
    "name"        : "script file does not exist",
    "options"     : ["--file=file_that_probably_dont_exist"],
    "cmdline"     : "p",
    "files"       : [],
    "expectedout" : b"",
    "expectederr" : 1,
    "script_test_not_applicable" : True
    },
    {
    "name"        : "script file unreadable (dir)",
    "options"     : ["--file=."],
    "cmdline"     : "p",
    "files"       : [],
    "expectedout" : b"",
    "expectederr" : 1,
    "script_test_not_applicable" : True
    },

# cmd: p
    {
    "name"        : "p",
    "options"     : ["-n"],
    "cmdline"     : "p",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "p, multiple adjacent",
    "options"     : ["-n"],
    "cmdline"     : "ppp",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!hello world!hello world!"
    },
    {
    "name"        : "p, multiple separated with all kinds of whitespaces",
    "options"     : ["-n"],
    "cmdline"     : "p     p\np p",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!hello world!hello world!hello world!"
    },
    {
    "name"        : "p, multiple input files",
    "options"     : ["-n"],
    "cmdline"     : "p",
    "files"       : ["tests/helloworld.txt", "tests/meaning_of_life.txt"],
    "expectedout" : b"hello world!42"
    },

# cmd: x
    {
    "name"        : "x, empty regex",
    "cmdline"     : "x//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "x, empty input",
    "cmdline"     : "x/\\\\([^\\\\)]*\\\\)/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "x, parenthesised",
    "cmdline"     : "x/\\\\([^\\\\)]*\\\\)/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"(20)(40)(foo)(hello world)()()()(This is 1 test\nsentence that spans\nmultiple lines.)"
    },
    {
    "name"        : "x, consecutive x's: numbers in parenthesis",
    "cmdline"     : "x/\\\\([^\\\\)]*\\\\)/ x/[0-9]\\+/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"20401"
    },
    {
    "name"        : "x, python comments",
    "cmdline"     : "x/#[^\\n]*\\n/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"# Full line comment\n# EoL comment\n#\n# Another full line comment\n#\n"
    },
    {
    "name"        : "x, C comments",
    "cmdline"     : "x/\\\\/\\\\*[^\\\\*]*\\\\*\\\\//",
    "files"       : ["tests/code.c"],
    "expectedout" : b"/* unimportant *//* ### some comment ### *//* this\n   is a\n   mult line\n   comment\n*//* some other comment */"
    },

# cmd: y
    {
    "name"        : "y, empty regex",
    "cmdline"     : "y//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "y, empty input",
    "cmdline"     : "y/\\\\([^\\\\)]*\\\\)/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "y, non-parenthesised",
    "cmdline"     : "y/\\\\([^\\\\)]*\\\\)/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"Test ints: 10, , 30, \nTest strings: , bar, , baz, \n <-- empty at line start\nempty at line end  --> \nMulti line:  end"
    },
    {
    "name"        : "y, consecutive y's: numbers not in parenthesis",
    "cmdline"     : "y/\\\\([^\\\\)]*\\\\)/ y/[a-zA-Z:,<> \n-]\\+/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"1030"
    },
    {
    "name"        : "y, python non-commented",
    "cmdline"     : "y/#[^\\n]*\\n/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"a = 10\nb = 20 c = 30\nd = 42\ne = 50 "
    },
    {
    "name"        : "y, C non-commented",
    "cmdline"     : "y/\\\\/\\\\*[^\\\\*]*\\\\*\\\\//",
    "files"       : ["tests/code.c"],
    "expectedout" : b"#include <stdio.h>\n#include <stdlib.h>\n#include \"vars.h\"\n x = 10; \ny = 20;\n\nz = 30; "
    },

# cmd: g
    {
    "name"        : "g, empty regex",
    "cmdline"     : "g//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "g, empty input",
    "cmdline"     : "g/dummy/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "g, match anything regex",
    "cmdline"     : "g/.*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "g, extract C code lines, keep preprocessor lines",
    "cmdline"     : "x/[^\\n]*\\n/ g/^#/",
    "files"       : ["tests/code.c"],
    "expectedout" : b"#include <stdio.h>\n#include <stdlib.h>\n#include \"vars.h\"\n"
    },
    {
    "name"        : "g, extract csv lines, keep those with 'false' at last field",
    "cmdline"     : "x/[^\\n]*\\n/ g/;false\\n$/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red;north;10;false\nblue;south;-5;false\ngreen;east;42;false\n"
    },
    {
    "name"        : "g, extract json objects, keep 'in' types",
    "cmdline"     : "x/\\\\{[^\\\\}]*\\\\}/ g/\"in\"/",
    "files"       : ["tests/hardware.json"],
    "expectedout" : b'{\n	"device": "Keyboard",\n	"type": "in",\n	"price": 50\n}{\n	"device": "Mouse",\n	"type": "in",\n	"price": 20\n}'
    },

# cmd: v
    {
    "name"        : "v, empty regex",
    "cmdline"     : "v//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "v, empty input",
    "cmdline"     : "v/dummy/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "v, match anything regex",
    "cmdline"     : "v/.*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "v, extract C code lines, discard preprocessor lines",
    "cmdline"     : "x/[^\\n]*\\n/ v/^#/",
    "files"       : ["tests/code.c"],
    "expectedout" : b"/* unimportant */ x = 10; /* ### some comment ### */\ny = 20;\n/* this\n   is a\n   mult line\n   comment\n*/\nz = 30; /* some other comment */\n"
    },
    {
    "name"        : "v, extract csv lines, discard those with 'false' at last field",
    "cmdline"     : "x/[^\\n]*\\n/ v/;false\\n$/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"yellow;south;117;true\npurple;north;31415;true\n"
    },
    {
    "name"        : "v, extract json objects, discard 'in' types",
    "cmdline"     : "x/\\\\{[^\\\\}]*\\\\}/ v/\"in\"/",
    "files"       : ["tests/hardware.json"],
    "expectedout" : b'{\n	"device": "Latop",\n	"type": "computer",\n	"price": 1000\n}{\n	"device": "Monitor",\n	"type": "out",\n	"price": 200\n}'
    },

# cmd: ~
    {
    "name"        : "~, empty input",
    "cmdline"     : "~",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "~, on full selection",
    "cmdline"     : "~",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "~, on empty selection",
    "cmdline"     : "x// ~",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "~, complement x, print the unquoted",
    "cmdline"     : "x/\"[^\"]*\"/ ~",
    "files"       : ["tests/quotes.txt"],
    "expectedout" : b"BoL  EoL\nBoL  EoF\nEmpty quote: "
    },
    {
    "name"        : "~, complement y, print the quoted",
    "cmdline"     : "y/\"[^\"]*\"/ ~",
    "files"       : ["tests/quotes.txt"],
    "expectedout" : b"\"inline quote\"\"multi\nline\nquote\"\"\""
    },

# cmd: L
    {
    "name"        : "L, empty input",
    "cmdline"     : "L",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "L, multi-line input",
    "cmdline"     : "L",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red;north;10;false\nblue;south;-5;false\nyellow;south;117;true\ngreen;east;42;false\npurple;north;31415;true\n"
    },
    {
    "name"        : "L, with a filter",
    "cmdline"     : "L g/true/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"yellow;south;117;true\npurple;north;31415;true\n"
    },
    {
    "name"        : "L, consecutive L's",
    "cmdline"     : "L L L g/true/ L L L",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"yellow;south;117;true\npurple;north;31415;true\n"
    },

# cmd: u
    {
    "name"        : "u, empty input",
    "cmdline"     : "u",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "u, on full selection",
    "cmdline"     : "u",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "u, on empty selection",
    "cmdline"     : "x// u",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "u, on non-empty selection",
    "cmdline"     : "x/l/ u",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },

# cmd: d
    {
    "name"        : "d, empty input",
    "cmdline"     : "d",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "d, on full selection",
    "cmdline"     : "d",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "d, on empty selection",
    "cmdline"     : "x/[0-9]/ d",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "d, delete quoted parts",
    "cmdline"     : "x/\"[^\"]*\"/ d",
    "files"       : ["tests/quotes.txt"],
    "expectedout" : b"BoL  EoL\nBoL  EoF\nEmpty quote: \n"
    },
    {
    "name"        : "d, delete python comments",
    "cmdline"     : "x/#[^\\n]*\\n/ d",
    "files"       : ["tests/code.py"],
    "expectedout" : b"a = 10\nb = 20 c = 30\nd = 42\ne = 50 "
    },

# cmd: c
    {
    "name"        : "c, empty input",
    "cmdline"     : "c/test/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"test"
    },
    {
    "name"        : "c, on full selection",
    "cmdline"     : "c/test/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"test"
    },
    {
    "name"        : "c, on empty selection",
    "cmdline"     : "x/[0-9]/ c/test/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "c, empty replacement (will delete)",
    "cmdline"     : "x/[ !]/ c//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"helloworld"
    },
    {
    "name"        : "c, multiple c's, capitalize (in a dumb way)",
    "cmdline"     : "x/h/c/H/ x/e/c/E/ x/l/c/L/ x/o/c/O/ x/w/c/W/ x/r/c/R/ x/d/c/D/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"HELLO WORLD!"
    },
    {
    "name"        : 'c, change "in" types to "input" in json (in a dumb way)',
    "cmdline"     : 'L g/"type": "in"/ x/in/ c/input/',
    "files"       : ["tests/hardware.json"],
    "expectedout" : b'[\n{\n	"device": "Latop",\n	"type": "computer",\n	"price": 1000\n},\n{\n	"device": "Keyboard",\n	"type": "input",\n	"price": 50\n},\n{\n	"device": "Monitor",\n	"type": "out",\n	"price": 200\n},\n{\n	"device": "Mouse",\n	"type": "input",\n	"price": 20\n},\n]\n'
    },

# cmd: s
    {
    "name"        : "s, empty input",
    "cmdline"     : "s/from/to/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "s, empty regex, empty replacement",
    "cmdline"     : "s///",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "s, empty regex, non-empty replacement",
    "cmdline"     : "s//to/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "s, non-empty regex with zero matches",
    "cmdline"     : "s/[xyz]/to/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "s, matching regex, empty replacement (will delete)",
    "cmdline"     : "s/\\\\/\\\\*[^\\\\*]*\\\\*\\\\///",
    "files"       : ["tests/code.c"],
    "expectedout" : b"#include <stdio.h>\n#include <stdlib.h>\n#include \"vars.h\"\n x = 10; \ny = 20;\n\nz = 30; \n"
    },
    {
    "name"        : "s, replace ; with \\t",
    "cmdline"     : "s/;/\\t/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red	north	10	false\nblue	south	-5	false\nyellow	south	117	true\ngreen	east	42	false\npurple	north	31415	true\n"
    },
    {
    "name"        : "s, consecutive s's, replacements same length as matches (non-zero)",
    "cmdline"     : "s/east/EAST/ s/north/NORTH/ s/south/SOUTH/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red;NORTH;10;false\nblue;SOUTH;-5;false\nyellow;SOUTH;117;true\ngreen;EAST;42;false\npurple;NORTH;31415;true\n"
    },
    {
    "name"        : "s, consecutive s's, replacements shorter than matches (non-zero)",
    "cmdline"     : "s/east/E/ s/north/N/ s/south/S/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red;N;10;false\nblue;S;-5;false\nyellow;S;117;true\ngreen;E;42;false\npurple;N;31415;true\n"
    },
    {
    "name"        : "s, consecutive s's, replacements longer than matches (non-zero)",
    "cmdline"     : "s/east/EEAASSTT/ s/north/NNOORRTTHH/ s/south/SSOOUUTTHH/",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red;NNOORRTTHH;10;false\nblue;SSOOUUTTHH;-5;false\nyellow;SSOOUUTTHH;117;true\ngreen;EEAASSTT;42;false\npurple;NNOORRTTHH;31415;true\n"
    },

# cmd: i
    {
    "name"        : "i, empty input",
    "cmdline"     : "i/pre/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"pre"
    },
    {
    "name"        : "i, empty input, empty prefix",
    "cmdline"     : "i//",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "i, non-empty input, empty prefix",
    "cmdline"     : "i//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "i, consecutive i's",
    "cmdline"     : "i/pre1-/ i/pre2-/ i/pre3-/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"pre3-pre2-pre1-hello world!"
    },
    {
    "name"        : "i, prefix numbers (prices) with '$'",
    "cmdline"     : "x/[0-9]\\+/ i/$/ u",
    "files"       : ["tests/hardware.json"],
    "expectedout" : b'[\n{\n	"device": "Latop",\n	"type": "computer",\n	"price": $1000\n},\n{\n	"device": "Keyboard",\n	"type": "in",\n	"price": $50\n},\n{\n	"device": "Monitor",\n	"type": "out",\n	"price": $200\n},\n{\n	"device": "Mouse",\n	"type": "in",\n	"price": $20\n},\n]\n'
    },

# cmd: a
    {
    "name"        : "a, empty input",
    "cmdline"     : "a/suf/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"suf"
    },
    {
    "name"        : "a, empty input, empty suffix",
    "cmdline"     : "a//",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "a, non-empty input, empty suffix",
    "cmdline"     : "a//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "a, consecutive a's",
    "cmdline"     : "a/-suf1/ a/-suf2/ a/-suf3/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!-suf1-suf2-suf3"
    },
    {
    "name"        : "a, suffix numbers (distances) with 'km'",
    "cmdline"     : "x/[0-9]\\+/ a/km/ u",
    "files"       : ["tests/hardware.json"],
    "expectedout" : b'[\n{\n	"device": "Latop",\n	"type": "computer",\n	"price": 1000km\n},\n{\n	"device": "Keyboard",\n	"type": "in",\n	"price": 50km\n},\n{\n	"device": "Monitor",\n	"type": "out",\n	"price": 200km\n},\n{\n	"device": "Mouse",\n	"type": "in",\n	"price": 20km\n},\n]\n'
    },

# cmd: S
    {
    "name"        : "S, empty input, empty prefix and suffix",
    "cmdline"     : "S///",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "S, empty input, empty prefix",
    "cmdline"     : "S//suf/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"suf"
    },
    {
    "name"        : "S, empty input, empty suffix",
    "cmdline"     : "S/pre//",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"pre"
    },
    {
    "name"        : "S, empty input",
    "cmdline"     : "S/pre/suf/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"presuf"
    },
    {
    "name"        : "S, non-empty input, empty prefix and suffix",
    "cmdline"     : "S///",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "S, non-empty input, empty prefix",
    "cmdline"     : "S//suf/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!suf"
    },
    {
    "name"        : "S, non-empty input, empty suffix",
    "cmdline"     : "S/pre//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"prehello world!"
    },
    {
    "name"        : "S, non-empty input",
    "cmdline"     : "S/pre/suf/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"prehello world!suf"
    },
    {
    "name"        : "S, consecutive S's",
    "cmdline"     : "S/ / / S/***/***/ S/***/***/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"****** hello world! ******"
    },
    {
    "name"        : "S, surround true and false with double quotes",
    "cmdline"     : 'x/false|true/ S/"/"/ u',
    "files"       : ["tests/data.csv"],
    "expectedout" : b'red;north;10;"false"\nblue;south;-5;"false"\nyellow;south;117;"true"\ngreen;east;42;"false"\npurple;north;31415;"true"\n'
    },

# cmd: r
    {
    "name"        : "r, empty arg",
    "cmdline"     : "r//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8
    },
    {
    "name"        : "r, non-empty arg, file does not exist",
    "cmdline"     : "r/file_that_probably_dont_exist/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 3
    },
    {
    "name"        : "r, empty input, empty r file",
    "cmdline"     : "r/tests\\/empty.txt/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "r, empty input, non-empty r file",
    "cmdline"     : "r/tests\\/helloworld.txt/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "r, non-empty input, empty r file",
    "cmdline"     : "r/tests\\/empty.txt/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "r, non-empty input, non-empty r file",
    "cmdline"     : "r/tests\\/meaning_of_life.txt/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"42"
    },
    {
    "name"        : "r, replace numbers with number read from file",
    "cmdline"     : "x/[0-9]*/ r/tests\\/meaning_of_life.txt/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"# Full line comment\na = 42\nb = 42 # EoL comment\n#\nc = 42\n# Another full line comment\nd = 42\ne = 42 #\n"
    },

# cmd: R
    {
    "name"        : "R, empty arg",
    "cmdline"     : "R//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8
    },
    {
    "name"        : "R, non-empty arg, file does not exist",
    "cmdline"     : "R/file_that_probably_dont_exist/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 3
    },
    {
    "name"        : "R, empty input, empty R file",
    "cmdline"     : "R/tests\\/empty.txt/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b""
    },
    {
    "name"        : "R, empty input, non-empty R file",
    "cmdline"     : "R/tests\\/helloworld.txt/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "R, non-empty input, empty R file",
    "cmdline"     : "R/tests\\/empty.txt/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!"
    },
    {
    "name"        : "R, non-empty input, non-empty R file",
    "cmdline"     : "R/tests\\/meaning_of_life.txt/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!42"
    },
    {
    "name"        : "R, append numbers with number read from file",
    "cmdline"     : "x/[0-9]*/ R/tests\\/meaning_of_life.txt/ u",
    "files"       : ["tests/code.py"],
    "expectedout" : b"# Full line comment\na = 1042\nb = 2042 # EoL comment\n#\nc = 3042\n# Another full line comment\nd = 4242\ne = 5042 #\n"
    },

# cmd: w
    {
    "name"            : "w, empty arg",
    "cmdline"         : "w///",
    "files"           : ["tests/helloworld.txt"],
    "expectedout"     : b"",
    "expectederr"     : 8
    },
    {
    "name"            : "w, empty input",
    "cmdline"         : "w/file_that_probably_dont_exist.txt/sep/",
    "files"           : ["tests/empty.txt"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : [""]
    },
    {
    "name"            : "w, on full selection",
    "options"         : ["-n"],
    "cmdline"         : "w/file_that_probably_dont_exist.txt/sep/",
    "files"           : ["tests/helloworld.txt"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["hello world!"]
    },
    {
    "name"            : "w, output all numbers with empty separator",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ w/file_that_probably_dont_exist.txt//",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["1020304250"]
    },
    {
    "name"            : "w, output all numbers with triple comma separator",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ w/file_that_probably_dont_exist.txt/,,,/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["10,,,20,,,30,,,42,,,50"]
    },
    {
    "name"            : "w, output all numbers with newline separator",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ w/file_that_probably_dont_exist.txt/\n/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["10\n20\n30\n42\n50"]
    },
    {
    "name"            : "w, consecutive w's to same file",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ w/file_that_probably_dont_exist.txt/,,,/ w/file_that_probably_dont_exist.txt/\n/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["10\n20\n30\n42\n50"]
    },
    {
    "name"            : "w, consecutive w's to separate files",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ w/file_that_probably_dont_exist.txt/,,,/ w/file_that_probably_dont_exist2.txt/\n/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt", "file_that_probably_dont_exist2.txt"],
    "newfilecontents" : ["10,,,20,,,30,,,42,,,50", "10\n20\n30\n42\n50"]
    },

# cmd: W
    {
    "name"            : "W, empty arg",
    "cmdline"         : "W///",
    "files"           : ["tests/helloworld.txt"],
    "expectedout"     : b"",
    "expectederr"     : 8
    },
    {
    "name"            : "W, empty input",
    "cmdline"         : "W/file_that_probably_dont_exist.txt/sep/",
    "files"           : ["tests/empty.txt"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : [""]
    },
    {
    "name"            : "W, on full selection",
    "options"         : ["-n"],
    "cmdline"         : "W/file_that_probably_dont_exist.txt/sep/",
    "files"           : ["tests/helloworld.txt"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["hello world!"]
    },
    {
    "name"            : "W, output all numbers with empty separator",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ W/file_that_probably_dont_exist.txt//",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["1020304250"]
    },
    {
    "name"            : "W, output all numbers with triple comma separator",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ W/file_that_probably_dont_exist.txt/,,,/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["10,,,20,,,30,,,42,,,50"]
    },
    {
    "name"            : "W, output all numbers with newline separator",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ W/file_that_probably_dont_exist.txt/\n/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["10\n20\n30\n42\n50"]
    },
    {
    "name"            : "W, consecutive W's to same file",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ W/file_that_probably_dont_exist.txt/,,,/ W/file_that_probably_dont_exist.txt/\n/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt"],
    "newfilecontents" : ["10,,,20,,,30,,,42,,,5010\n20\n30\n42\n50"]
    },
    {
    "name"            : "W, consecutive W's to separate files",
    "options"         : ["-n"],
    "cmdline"         : "x/[0-9]+/ W/file_that_probably_dont_exist.txt/,,,/ W/file_that_probably_dont_exist2.txt/\n/",
    "files"           : ["tests/code.py"],
    "expectedout"     : b"",
    "newfilenames"    : ["file_that_probably_dont_exist.txt", "file_that_probably_dont_exist2.txt"],
    "newfilecontents" : ["10,,,20,,,30,,,42,,,50", "10\n20\n30\n42\n50"]
    },

# cmd: !
    {
    "name"        : "!, empty arg",
    "cmdline"     : "!//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8,
    },
    {
    "name"        : "!, empty input",
    "options"     : ["-n"],
    "cmdline"     : "!/echo foo/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"foo\n",
    },
    {
    "name"        : "!, single extraction",
    "options"     : ["-n"],
    "cmdline"     : "!/echo foo/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"foo\n",
    },
    {
    "name"        : "!, multiple extractions",
    "options"     : ["-n"],
    "cmdline"     : "x/[eo]/ !/echo foo/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"foo\nfoo\nfoo\n",
    },
    {
    "name"        : "!, more complex sh command",
    "options"     : ["-n"],
    "cmdline"     : "x/[eo]/ !/echo foo | tr a-z A-Z | rev/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"OOF\nOOF\nOOF\n",
    },

# cmd: <
    {
    "name"        : "<, empty arg",
    "cmdline"     : "<//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8,
    },
    {
    "name"        : "<, empty input",
    "cmdline"     : "</echo foo/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"foo\n",
    },
    {
    "name"        : "<, single extraction",
    "cmdline"     : "</echo foo/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"foo\n",
    },
    {
    "name"        : "<, multiple extractions",
    "cmdline"     : "x/[0-9]+/ </echo -n 42/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"# Full line comment\na = 42\nb = 42 # EoL comment\n#\nc = 42\n# Another full line comment\nd = 42\ne = 42 #\n",
    },
    {
    "name"        : "<, more complex sh command",
    "cmdline"     : 'x/"[^"]*"/ </echo \"[redacted]\" | tr a-z A-Z/',
    "files"       : ["tests/quotes.txt"],
    "expectedout" : b"BoL [REDACTED]\n EoL\nBoL [REDACTED]\n EoF\nEmpty quote: [REDACTED]\n\n",
    },

# cmd: >
    {
    "name"        : ">, empty arg",
    "cmdline"     : ">//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8,
    },
    {
    "name"        : ">, empty input",
    "options"     : ["-n"],
    "cmdline"     : ">/tr a-z A-Z/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : ">, single extraction",
    "options"     : ["-n"],
    "cmdline"     : ">/tr a-z A-Z/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"HELLO WORLD!",
    },
    {
    "name"        : ">, multiple extractions",
    "options"     : ["-n"],
    "cmdline"     : "x/[0-9]+/ >/rev/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"0102032405",
    },
    {
    "name"        : ">, more complex sh command",
    "options"     : ["-n"],
    "cmdline"     : '>/grep "[0-9]" | cut -d: -f2/',
    "files"       : ["tests/hardware.json"],
    "expectedout" : b" 1000\n 50\n 200\n 20\n",
    },

# cmd: |
    {
    "name"        : "|, empty arg",
    "cmdline"     : "|//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8,
    },
    {
    "name"        : "|, empty input",
    "cmdline"     : "|/tr a-z A-Z/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "|, single extraction",
    "cmdline"     : "|/rev/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"!dlrow olleh",
    },
    {
    "name"        : "|, multiple extractions",
    "cmdline"     : "x/east|north|south/ |/tr a-z A-Z/ u",
    "files"       : ["tests/data.csv"],
    "expectedout" : b"red;NORTH;10;false\nblue;SOUTH;-5;false\nyellow;SOUTH;117;true\ngreen;EAST;42;false\npurple;NORTH;31415;true\n",
    },
    {
    "name"        : "|, more complex sh command",
    "cmdline"     : '|/awk -F";" "{print \\\\$2, \\\\$3}" OFS="\t" | sed "="/',
    "files"       : ["tests/data.csv"],
    "expectedout" : b"1\nnorth	10\n2\nsouth	-5\n3\nsouth	117\n4\neast	42\n5\nnorth	31415\n",
    },
    {
    "name"        : "|, capitalize commented texts in C",
    "cmdline"     : "x/\\\\/\\\\*[^\\\\*]*\\\\*\\\\// |/tr a-z A-Z/",
    "files"       : ["tests/code.c"],
    "expectedout" : b"#include <stdio.h>\n#include <stdlib.h>\n#include \"vars.h\"\n/* UNIMPORTANT */ x = 10; /* ### SOME COMMENT ### */\ny = 20;\n/* THIS\n   IS A\n   MULT LINE\n   COMMENT\n*/\nz = 30; /* SOME OTHER COMMENT */\n",
    },

# cmd: t
    {
    "name"        : "t, empty arg",
    "cmdline"     : "t//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8,
    },
    {
    "name"        : "t, empty input",
    "cmdline"     : "t/grep -q 'foo'/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "t, false for all extractions",
    "cmdline"     : "x/[0-9]+/ t/grep -q '9'/ a/|/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"",
    },
    {
    "name"        : "t, true for all extractions",
    "cmdline"     : "x/[0-9]+/ t/grep -q '[0-9]'/ a/|/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"10|20|30|42|50|",
    },
    {
    "name"        : "t, true for some, false for others",
    "cmdline"     : "x/[0-9]+/ t/grep -q '[12]'/ a/|/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"10|20|42|",
    },

# cmd: T
    {
    "name"        : "T, empty arg",
    "cmdline"     : "T//",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    "expectederr" : 8,
    },
    {
    "name"        : "T, empty input",
    "cmdline"     : "T/grep -q 'foo'/",
    "files"       : ["tests/empty.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "T, false for all extractions",
    "cmdline"     : "x/[0-9]+/ T/grep -q '9'/ a/|/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"10|20|30|42|50|",
    },
    {
    "name"        : "T, true for all extractions",
    "cmdline"     : "x/[0-9]+/ T/grep -q '[0-9]'/ a/|/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"",
    },
    {
    "name"        : "T, true for some, false for others",
    "cmdline"     : "x/[0-9]+/ T/grep -q '[12]'/ a/|/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"30|50|",
    },

# comments
    {
    "name"        : "comments, single hashmark",
    "cmdline"     : "#",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "comments, many consecutive hashmarks",
    "cmdline"     : "#######",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "comments, many consecutive hashmarks with whitespaces",
    "cmdline"     : "##   #\n#  #           # #\n\n#",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "comments, all lines fully commented",
    "cmdline"     : "# p\n# x/[a-z]/\n# u",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "comments, some lines fully, some partially commented",
    "cmdline"     : "# first line\n x/[0-9]+/ # extract numbers\n S/<</>>/ # surround them\n# last line",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"<<10>><<20>><<30>><<40>><<1>>",
    },
    {
    "name"        : "comments, cmd contains hashmark",
    "cmdline"     : "x/[0-9]+/ S/### / ###/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"### 10 ###### 20 ###### 30 ###### 40 ###### 1 ###",
    },

# options (only those that are not covered by other tests)
    {
    "name"           : "options, invalid short option",
    "options"        : ["-w"],
    "cmdline"        : "",
    "files"          : ["tests/helloworld.txt"],
    "expectedout"    : b"hello world!",
    "shouldprinterr" : True,
    },
    {
    "name"           : "options, invalid long option",
    "options"        : ["--foo"],
    "cmdline"        : "",
    "files"          : ["tests/helloworld.txt"],
    "expectedout"    : b"hello world!",
    "shouldprinterr" : True,
    },
    {
    "name"        : "options, -B, + not escaped",
    "options"     : ["-B"],
    "cmdline"     : "x/[0-9]+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"",
    },
    {
    "name"        : "options, -B, + escaped",
    "options"     : ["-B"],
    "cmdline"     : "x/[0-9]\\\\+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"1020304250",
    },
    {
    "name"        : "options, -E, + not escaped",
    "options"     : ["-E"],
    "cmdline"     : "x/[0-9]+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"1020304250",
    },
    {
    "name"        : "options, -E, + escaped",
    "options"     : ["-E"],
    "cmdline"     : "x/[0-9]\\\\+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"",
    },
    {
    "name"        : "options, --basic-regexp, + not escaped",
    "options"     : ["--basic-regexp"],
    "cmdline"     : "x/[0-9]+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"",
    },
    {
    "name"        : "options, --basic-regexp, + escaped",
    "options"     : ["--basic-regexp"],
    "cmdline"     : "x/[0-9]\\\\+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"1020304250",
    },
    {
    "name"        : "options, --extended-regexp, + not escaped",
    "options"     : ["--extended-regexp"],
    "cmdline"     : "x/[0-9]+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"1020304250",
    },
    {
    "name"        : "options, --extended-regexp, + escaped",
    "options"     : ["--extended-regexp"],
    "cmdline"     : "x/[0-9]\\\\+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"",
    },
    {
    "name"        : "options, -i",
    "options"     : ["-i"],
    "cmdline"     : "x/[A-Z]/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"helloworld",
    },
    {
    "name"        : "options, --ignorecase",
    "options"     : ["--ignorecase"],
    "cmdline"     : "x/[A-Z]/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"helloworld",
    },
    {
    "name"        : "options, -N",
    "options"     : ["-N"],
    "cmdline"     : "x/.*\n/ g/--/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"() <-- empty at line start\nempty at line end  --> ()\n",
    },
    {
    "name"        : "options, --reg-newline",
    "options"     : ["--reg-newline"],
    "cmdline"     : "x/.*\n/ g/--/",
    "files"       : ["tests/parenthesis.txt"],
    "expectedout" : b"() <-- empty at line start\nempty at line end  --> ()\n",
    },

# error-prone regexes
    {
    "name"        : "error-prone regexes, ^ with x",
    "cmdline"     : "x/^/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, ^ with y",
    "cmdline"     : "y/^/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, ^ with g",
    "cmdline"     : "g/^/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, ^ with v",
    "cmdline"     : "v/^/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, ^ with s",
    "cmdline"     : "s/^/!/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"!hello world!",
    },
    {
    "name"        : "error-prone regexes, $ with x",
    "cmdline"     : "x/$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, $ with y",
    "cmdline"     : "y/$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, $ with g",
    "cmdline"     : "g/$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, $ with v",
    "cmdline"     : "v/$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, $ with s",
    "cmdline"     : "s/$/!/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!!",
    },
    {
    "name"        : "error-prone regexes, ^$ with x",
    "cmdline"     : "x/^$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, ^$ with y",
    "cmdline"     : "y/^$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, ^$ with g",
    "cmdline"     : "g/^$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, ^$ with v",
    "cmdline"     : "v/^$/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, ^$ with s",
    "cmdline"     : "s/^$/!/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, .* with x",
    "cmdline"     : "x/.*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, .* with y",
    "cmdline"     : "y/.*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, .* with g",
    "cmdline"     : "g/.*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"hello world!",
    },
    {
    "name"        : "error-prone regexes, .* with v",
    "cmdline"     : "v/.*/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"",
    },
    {
    "name"        : "error-prone regexes, .* with s",
    "cmdline"     : "s/.*/!/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : b"!",
    },

# stress tests (kind of, not too big sizes to keep valgrind execution times bearable...)
    {
    "name"        : "stress, large input",
    "cmdline"     : "L g/[^0-9]424[0-9]/",
    "files"       : ["tests/large_input.txt"],
    "expectedout" : b"  4240\tThis line is a little redundant...\n  4241\tThis line is a little redundant...\n  4242\tThis line is a little redundant...\n  4243\tThis line is a little redundant...\n  4244\tThis line is a little redundant...\n  4245\tThis line is a little redundant...\n  4246\tThis line is a little redundant...\n  4247\tThis line is a little redundant...\n  4248\tThis line is a little redundant...\n  4249\tThis line is a little redundant...\n",
    "timeout"     : 1200,
    },
    {
    "name"        : "stress, long cmdline",
    "cmdline"     : "x/[0-9]+/ u x/[0-9]+/ u  x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/ u x/[0-9]+/",
    "files"       : ["tests/code.py"],
    "expectedout" : b"1020304250",
    },
    {
    "name"        : "stress, many input files",
    "cmdline"     : "x/1[02468]/",
    "files"       : ["tests/small1", "tests/small2", "tests/small3", "tests/small4", "tests/small5",
                     "tests/small6", "tests/small7", "tests/small8", "tests/small9", "tests/small10",
                     "tests/small11", "tests/small12", "tests/small13", "tests/small14", "tests/small15",
                     "tests/small16", "tests/small17", "tests/small18", "tests/small19", "tests/small20"],
    "expectedout" : b"1012141618",
    },
    {
    "name"        : "stress, extcmd <, large output",
    "cmdline"     : "</seq 1000000/",
    "files"       : ["tests/helloworld.txt"],
    "expectedout" : bytes(("\n".join([str(i) for i in range(1, 1000001)]) + "\n"), "ASCII"),
    },
    {
    "name"        : "stress, extcmd >, large input",
    "options"     : ["-n"],
    "cmdline"     : ">/tail -5/",
    "files"       : ["tests/large_input.txt"],
    "expectedout" : b" 19996	This line is a little redundant...\n 19997	This line is a little redundant...\n 19998	This line is a little redundant...\n 19999	This line is a little redundant...\n 20000	This line is a little redundant...\n",
    },
    {
    "name"        : "stress, extcmd |, large input",
    "cmdline"     : "|/tail -5/ L g/199/",
    "files"       : ["tests/large_input.txt"],
    "expectedout" : b" 19996	This line is a little redundant...\n 19997	This line is a little redundant...\n 19998	This line is a little redundant...\n 19999	This line is a little redundant...\n",
    },
    # TODO: this one doesn't work yet
    # {
    # "name"        : "stress, extcmd |, large output",
    # "cmdline"     : "|/seq 1000000/",
    # "files"       : ["tests/large_input.txt"],
    # "expectedout" : bytes(("\n".join([str(i) for i in range(1, 1000001)]) + "\n"), "ASCII"),
    # },
]

# Release run

print("******************************** Building srek *********************************")
os.system("make rebuild")

print("\n******************** Running release, input as files *********************")
for testcase in testcases:
    print("[release] ", end="")
    testexec(testcase)

print("\n******************** Running release, input as stdin *********************")
for testcase in testcases:
    print("[release, stdin] ", end="")
    testexec(testcase, inputtostdin=True)

print("\n******************** Running release, input as files, from script *********************")
for testcase in testcases:
    print("[release, script] ", end="")
    testexec(testcase, fromscript=True)

print("\n******************** Running release, input as stdin, from script *********************")
for testcase in testcases:
    print("[release, stdin, script] ", end="")
    testexec(testcase, inputtostdin=True, fromscript=True)

# Valgrind run

print("\n******************** Running valgrind, input as files ********************")
for testcase in testcases:
    print("[valgrind] ", end="")
    testexec(testcase, usevalgrind=True)

print("\n******************** Running valgrind, input as stdin ********************")
for testcase in testcases:
    print("[valgrind, stdin] ", end="")
    testexec(testcase, usevalgrind=True, inputtostdin=True)

print("\n******************** Running valgrind, input as files, from script ********************")
for testcase in testcases:
    print("[valgrind, script] ", end="")
    testexec(testcase, usevalgrind=True, fromscript=True)

print("\n******************** Running valgrind, input as stdin, from script ********************")
for testcase in testcases:
    print("[valgrind, stdin, script] ", end="")
    testexec(testcase, usevalgrind=True, inputtostdin=True, fromscript=True)

# Sanitized run

print("\n*************************** Building sanitized srek ****************************")
os.system("make build-sanitized")

print("\n******************** Running sanitized, input as files *******************")
for testcase in testcases:
    print("[sanitized] ", end="")
    testexec(testcase)

print("\n******************** Running sanitized, input as stdin *******************")
for testcase in testcases:
    print("[sanitized, stdin] ", end="")
    testexec(testcase, inputtostdin=True)

print("\n******************** Running sanitized, input as files, from script *******************")
for testcase in testcases:
    print("[sanitized, script] ", end="")
    testexec(testcase, fromscript=True)

print("\n******************** Running sanitized, input as stdin, from script *******************")
for testcase in testcases:
    print("[sanitized, stdin, script] ", end="")
    testexec(testcase, inputtostdin=True, fromscript=True)

# Results

print("\n*********************************** Results ************************************")
print("Passed:", passedcnt)
print("Failed:", failedcnt)
print("Success: " + Style.BRIGHT + format(passedcnt / (passedcnt + failedcnt) * 100, ".2f"), "%" + Style.RESET_ALL)

if len(failedlist) != 0:
    print("\nThe following testcases failed:")
    for fail in failedlist:
        print("[#" + str(fail["index"]) + "]", fail["name"])


exit(0 if failedcnt == 0 else 1)

