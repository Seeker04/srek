<!---
srek - Structural RegEx Kit

MIT License
Copyright (c) 2022 Barnabás Zahorán, see LICENSE
--->

# srek - Structural RegEx Kit

## About

This command-line tool is based on Structural Regular Expressions by Rob Pike. You can [read his paper here](http://doc.cat-v.org/bell_labs/structural_regexps/), and here is [another good article](https://what.happens.when.computer/2016-08-30/structural-res/) about the topic.

Note that this tool is **not** a 100% match to the legacy SRE language developed for [sam](http://sam.cat-v.org/) and [acme](http://acme.cat-v.org/), but srek's language is heavily inspired by them.

This is a really simple program written in a single C file with about 1500 lines of code. The project aims to remain accessible (MIT license), simple, easy to understand and use. More than 2300 test scenarios aim to check correctness. It provides a nice coverage and a 100% result builds a lot of confidence after a new commit. Portability was also a top priority in mind, hence the use of C89 and strict compatibility options. For example, it compiles and works on Solaris 10 (an OS from 2005).

**So what can you use this for?**

srek is a text processing and manipulation language, similar to sed. What differentiates it from sed and most Unix tools: it does not presume that the input is structured in lines. Instead, with commands like `x`, the user can define the input's structure in an arbitrary way. For example, `x/"[^"]*"/p` will extract and print all quoted text from the input. A quoted part may be contained in a line without spanning the entire line; or it may begin and end on different lines. A similar regex can be used to extract parenthesized parts, or texts between certain XML tags. Note that a lot of file formats (JSON, XML, C sources, etc.) are forgiving about whitespaces, so whatever we wish to work on can be contained within or span multiple lines. Standard Unix tools like grep, sed or awk are all line based and thus not well suited for these problems. The above example: `x/"[^"]*"/p` would be really cumbersome to implement with any of these tools.

The structural regex approach is more general, because it can easily simulate what line based tools do. All we need is an extraction like: `x/[^\n]*\n/` (there is an alias command for this: `L`). For example, for `grep 'pattern'` the equivalent is `srek 'x/[^\n]*\n/ g/pattern/ p'` or in shorter: `srek 'Lg/pattern/'`.

Extractions may be refined by consecutive `x` commands, for example:

`srek 'x/"[^"]*"/ x/[a-zA-Z]+/ a/\n/'`

will first select all quoted text, then it will select all words within them and finally, print them each in a new line.

**What's it not suited for?**

srek is not ideal for processing continuous, "infinite", input like a lot of Unix tools (grep, sed, etc.), because it needs to read the whole input before processing it. As a result, processing a 1 GB file will require roughly 1 GB memory. This is good to keep in mind.

## How to build

Requires GNU Make.

Run:

`$ make`

For a debug build, run:

`$ make build-debug`

For further options, e.g. adjusting build parameters or running tests, see [Makefile](Makefile).

## How to install

Run:

`$ sudo make install`

Uninstall with:

`$ sudo make uninstall`

By default, the install location is /usr/local/bin/. This can be adjusted in the [Makefile](Makefile).

## How to use

For usage instructions, run:

`$ srek --help`

Here is an excerpt:

```
Usage: srek [OPTION...] COMMAND-LINE [FILE...]

When FILE is missing, srek will read from stdin.

OPTIONS
-B, --basic-regexp      Use POSIX Basic regular expressions
-E, --extended-regexp   Use POSIX Extended regular expressions (this is the default)
-f, --file=<file>       Read COMMAND-LINE from <file>
-h, --help              Display this help
-i, --ignorecase        Ignore case when matching regex
-n, --quiet             Do not put an implicit print command at the end
-N, --reg-newline       Match-any-character operators don't match a newline
-v, --version           Display version information

COMMAND-LINE may contain a list of commands separated by optional whitespaces:

x/regexp/               Extract matches from input to a set of selections
y/regexp/               Like x, but extract the non-matching parts instead
g/regexp/               Filter selections with <regexp>
v/regexp/               Like g, but keep the non-matching selections instead
~                       Flip selections (everything selected becomes unselected and vice versa)
L                       Extract lines, shorthand for x/[^\n]*\n/
u                       Undo all selections

p                       Print all selection to stdout
d                       Delete selected text, selection resets
c/replacement/          Replace each selection with <replacement>, selection resets
s/regexp/replacement/   Replace matching parts of each selection with <replacement>
i/prefix/               Prefix selections with <prefix>, shorthand for s/^/text/
a/suffix/               Suffix selections with <suffix>, shorthand for s/$/text/
S/prefix/suffix/        Surround selections, shorthand for i/prefix/a/suffix/

r/file/                 Replace selections with contents read from <file>
R/file/                 Like r, but append instead
w/file/sep/             Write selections to <file>, each separated by <sep>
W/file/sep/             Like w, but append to file instead

!/cmd/                  Run <cmd> once for each selection
</cmd/                  Run <cmd> once, and replace selections with its stdout
>/cmd/                  Run <cmd> once for each selection by passing the selection to its stdin
|/cmd/                  Run <cmd> on each selection by taking it as stdin and replacing it with stdout
t/cmd/                  Keep only those selections for which <cmd> returned with success (zero)
T/cmd/                  Keep only those selections for which <cmd> returned with error (non-zero)
                        Note: <cmd> must be a valid shell command

#comment                Comment till next newline
```

**Examples:**

`x/#[^\n]*\n/ d` delete Python comments

`x/#[^\n]*\n/ w/commented.txt/\n/ ` output comments separated by newlines to a new file

`y/#[^\n]*\n/ w/not_commented.txt/\n/ ` same, except now output the not commented parts

`x/[a-zA-Z]+:/ S/**/**/ u` turn words followed by colons to bold for Markdown

`x/todo|readme|license/ |/tr a-z A-Z/` turn some words to uppercase

`s/ +/ /` condense consecutive spaces to a single one

Further examples can be found [among the tests](runtests.py).

## For contributors

Feel free to create a merge request for any contribution, but please, consider the following:

- srek should keep its base goals: be small, portable, simple with clean and easy to understand code (following the KISS principle and the Unix philosophy).
- No strict coding standards, but please, try to stick with the existing style.
- Running `$ make test` must continue to give a 100% success result.
- Preferably no new warning is introduced for cc, clang-tidy or cppcheck. There are already a few, so if you think, yours are reasonable too, feel free to negotiate;)

**Note:** the static checks have the following dependencies:
```bash
cppcheck
clang-tidy
```
Runtime tests need:
```bash
valgrind
python3
colorama           # python package, install with OS package manager or pip3
libsanitizer-devel # sanitized execution needs this separate pkg on some distros
```

## Similar projects

- [sregx](https://github.com/zyedidia/sregx) : a similar tool written in Go
- [sam, ssam](https://tools.suckless.org/9base/) : sam and a stream interface for it, Plan9 ports from the suckless team
- [vis](https://github.com/martanne/vis) : a vim-like editor with sam's structural regular expressions
- [kakoune](https://kakoune.org/) : a modern modal editor with similar editing features to SREs

