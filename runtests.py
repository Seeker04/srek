#!/usr/bin/env python3

# srek - Structural RegEx Kit
#
# MIT License
# Copyright (c) 2022 Barnabás Zahorán, see LICENSE
#
# Test tool for running dynamic tests

from os         import system, path, remove
from subprocess import run, TimeoutExpired
from json       import load
from colorama   import Fore, Back, Style

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
        procinfo = run(
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

        elif testcase.get("expectederr", 0) != 0 and procinfo.stderr == "":
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "exited with error, but stderr is empty")
            failed = True

        elif procinfo.stdout != bytes(testcase["expectedout"], "ASCII"):
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "output differs from expected")
            failed = True

        elif testcase.get("shouldprinterr", False) and procinfo.stderr == "":
            print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "some error message was expected but not given")
            failed = True

        else:
            i = 0
            for fname in testcase.get("newfilenames", []):
                f = open(fname, "r")
                if not path.exists(fname):
                    print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "output file was not created")
                    failed = True
                    break
                if f.read() != testcase["newfilecontents"][i]:
                    print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "output file differs from expected")
                    failed = True
                    break
                i += 1
                f.close()
    except TimeoutExpired:
        print(Back.RED + Fore.WHITE + "Failed:" + Style.RESET_ALL, "timed out")
        failed = True

    for fname in testcase.get("newfilenames", []): # cleanup generated files
        remove(fname)
    if fromscript:
        remove("temp_testscript_temp")

    if failed:
        failedcnt += 1
        failedlist.append({ "index": index, "name": testcase["name"] })
    else:
        print(Back.GREEN + Fore.BLACK + "Passed" + Style.RESET_ALL)
        passedcnt += 1


try:
    json_file = open("testcases.json")
    testcases = load(json_file)
except:
    print(Back.RED + Fore.WHITE + "FATAL ERROR: could not parse testcases.json!" + Style.RESET_ALL)
    exit(2)
else:
    print("******************************** Building srek *********************************")
    system("make rebuild")

    # Release run

    print("\n*********************** Running release, input as files ************************")
    for testcase in testcases:
        print("[release] ", end="")
        testexec(testcase)

    print("\n*********************** Running release, input as stdin ************************")
    for testcase in testcases:
        print("[release, stdin] ", end="")
        testexec(testcase, inputtostdin=True)

    print("\n***************** Running release, input as files, from script *****************")
    for testcase in testcases:
        print("[release, script] ", end="")
        testexec(testcase, fromscript=True)

    print("\n***************** Running release, input as stdin, from script *****************")
    for testcase in testcases:
        print("[release, stdin, script] ", end="")
        testexec(testcase, inputtostdin=True, fromscript=True)

    # Valgrind run

    print("\n*********************** Running valgrind, input as files ***********************")
    for testcase in testcases:
        print("[valgrind] ", end="")
        testexec(testcase, usevalgrind=True)

    print("\n*********************** Running valgrind, input as stdin ***********************")
    for testcase in testcases:
        print("[valgrind, stdin] ", end="")
        testexec(testcase, usevalgrind=True, inputtostdin=True)

    print("\n**************** Running valgrind, input as files, from script *****************")
    for testcase in testcases:
        print("[valgrind, script] ", end="")
        testexec(testcase, usevalgrind=True, fromscript=True)

    print("\n**************** Running valgrind, input as stdin, from script *****************")
    for testcase in testcases:
        print("[valgrind, stdin, script] ", end="")
        testexec(testcase, usevalgrind=True, inputtostdin=True, fromscript=True)

    # Sanitized run

    print("\n*************************** Building sanitized srek ****************************")
    system("make build-sanitized")

    print("\n********************** Running sanitized, input as files ***********************")
    for testcase in testcases:
        print("[sanitized] ", end="")
        testexec(testcase)

    print("\n********************** Running sanitized, input as stdin ***********************")
    for testcase in testcases:
        print("[sanitized, stdin] ", end="")
        testexec(testcase, inputtostdin=True)

    print("\n**************** Running sanitized, input as files, from script ****************")
    for testcase in testcases:
        print("[sanitized, script] ", end="")
        testexec(testcase, fromscript=True)

    print("\n**************** Running sanitized, input as stdin, from script ****************")
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

