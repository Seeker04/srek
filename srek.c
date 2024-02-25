/*
 * srek - Structural RegEx Kit
 *
 * MIT License
 * Copyright (c) 2022 Barnabás Zahorán, see LICENSE
 *
 * For usage details, run with --help or see README.md
 */

/*
 * TODO: cmd_sub: handle capture groups with pmatch[1-9]
 * TODO: if input is larger than 139264 bytes, then write() hangs in cmd_extcmd_io()
 *       e.g.: ./srek '|/tr a-z A-Z/' tests/large_input.txt
 */

#include <ctype.h>
#include <getopt.h>
#include <regex.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if __linux__
#include <sys/prctl.h>
#endif
#include <sys/wait.h>
#include <unistd.h>

#define ARRAY_SIZE(arr) (sizeof(arr)/sizeof(*(arr)))

#define ERR_NO_CMDLINE          1
#define ERR_INVALID_CMDLINE     2
#define ERR_CANNOT_READ_INPUT   3
#define ERR_CANNOT_WRITE_OUTPUT 4
#define ERR_REGCOMP_FAILED      5
#define ERR_MEM_ALLOC_FAILED    6
#define ERR_EXTCMD_RUN_FAILED   7
#define ERR_EMPTY_ARG           8

#define RE_SUBMATCH_CNT 9     /* support up to 9 submatches: \1,...,\9 */
#define ERRBUF_SIZE     256
#define READ_CHUNK_SIZE 65536 /* 64 KB */

static const char *VERSION = "srek - Structural RegEx Kit\nVersion: v1.0";

static const char *HELP[] = {
	"Usage: srek [OPTION...] COMMAND-LINE [FILE...]\n\n"

	"When FILE is missing, srek will read from stdin.\n\n",

	"OPTIONS\n"
	"-B, --basic-regexp	Use POSIX Basic regular expressions\n"
	"-E, --extended-regexp	Use POSIX Extended regular expressions (this is the default)\n"
	"-f, --file=<file>	Read COMMAND-LINE from <file>\n"
	"-h, --help		Display this help\n"
	"-i, --ignorecase	Ignore case when matching regex\n"
	"-n, --quiet		Do not put an implicit print command at the end\n"
	"-N, --reg-newline	Match-any-character operators don't match a newline\n"
	"-v, --version		Display version information\n\n",

	"COMMAND-LINE may contain a list of commands separated by optional whitespaces:\n\n"
	"x/regexp/		Extract matches from input to a set of selections\n"
	"y/regexp/		Like x, but extract the non-matching parts instead\n"
	"g/regexp/		Filter selections with <regexp>\n"
	"v/regexp/		Like g, but keep the non-matching selections instead\n"
	"~			Flip selections (everything selected becomes unselected and vice versa)\n"
	"L			Extract lines, shorthand for x/[^\\n]*\\n/\n"
	"u			Undo all selections\n\n",

	"p			Print all selection to stdout\n"
	"d			Delete selected text, selection resets\n"
	"c/replacement/		Replace each selection with <replacement>, selection resets\n"
	"s/regexp/replacement/	Replace matching parts of each selection with <replacement>\n"
	"i/prefix/		Prefix selections with <prefix>, shorthand for s/^/text/\n"
	"a/suffix/		Suffix selections with <suffix>, shorthand for s/$/text/\n"
	"S/prefix/suffix/	Surround selections, shorthand for i/prefix/a/suffix/\n\n",

	"r/file/			Replace selections with contents read from <file>\n"
	"R/file/			Like r, but append instead\n"
	"w/file/sep/		Write selections to <file>, each separated by <sep>\n"
	"W/file/sep/		Like w, but append to file instead\n\n",

	"!/cmd/			Run <cmd> once for each selection\n"
	"</cmd/			Run <cmd> once, and replace selections with its stdout\n"
	">/cmd/			Run <cmd> once for each selection by passing the selection to its stdin\n"
	"|/cmd/			Run <cmd> on each selection by taking it as stdin and replacing it with stdout\n"
	"t/cmd/			Keep only those selections for which <cmd> returned with success (zero)\n"
	"T/cmd/			Keep only those selections for which <cmd> returned with error (non-zero)\n"
	"			Note: <cmd> must be a valid shell command\n\n",

	"#comment		Comment till next newline\n"
};

typedef int bool;
enum { false, true };

typedef enum {
	CMD_PRINT,     /* print current selections */
	CMD_DELETE,    /* delete selections */
	CMD_CHANGE,    /* change selections to arbitrary string */
	CMD_SUB,       /* regex replace on selections */
	CMD_GUARD,     /* regex test on selections to deselect or keep */
	CMD_VGUARD,    /* negated guard */
	CMD_XTRACT,    /* extract regex matches from selections to new selections */
	CMD_YTRACT,    /* like extract, but only select the non-matching */
	CMD_INSERT,    /* prefix selections with arbitrary string */
	CMD_APPEND,    /* suffix selections with arbitrary string */
	CMD_SURROUND,  /* prefix and suffix selections with arbitrary string */
	CMD_FLIP,      /* flip selections (take complement of the intervals) */
	CMD_UNDOX,     /* undo all selections */
	CMD_READ,      /* replace selections with file content */
	CMD_READAPP,   /* append selections with file content */
	CMD_WRITE,     /* overwrite file with selections separated by a separator */
	CMD_WRITEAPP,  /* append file with selections separated by a separator */
	CMD_EXTCMD,    /* run external command for each selection */
	CMD_EXTCMD_I,  /* replace selections with output of external command */
	CMD_EXTCMD_O,  /* run external command with selections as input */
	CMD_EXTCMD_IO, /* pass each selection to external command then replace it with the output */
	CMD_EXTCMD_T,  /* deselect those for which the command returned with error */
	CMD_EXTCMD_TN, /* deselect those for which the command returned with success */
	CMD_LINES,     /* extract lines to selections */
	CMD_MAX
} CmdId;

typedef struct Cmd {
	CmdId       id;
	char      **args;
	regex_t    *regex;
	struct Cmd *next;
} Cmd;

typedef struct {
	char   ch;
	size_t argcnt;
	void   (*callback)(const Cmd*);
} CmdDesc;

typedef struct Intval {
	size_t from;
	size_t len;
	struct Intval *next;
} Intval;

typedef struct StrList {
	char *str;
	struct StrList *next;
} StrList;

static Cmd*    addcmd(CmdId id);
static Intval* addintv(size_t from, size_t len, Intval **list, Intval **last);
static void*   alloc(size_t size);
static CmdId   chtocmdid(char ch);
static void    cleanupall(void);
static void    cleanupcmds(void);
static void    cleanupsels(void);
static void    compileregexes(void);
static void    emptyargerr(const Cmd *cmd);
static void    escapechars(char **str, bool freeorig);
static void    flipintvals(const Intval *bound, Intval **intvs, Intval **lastintv);
static void    guardinternal(const Cmd *cmd, bool negated);
static void    parsecmds(char *cmdline);
static char*   readfullfile(FILE * file, size_t *size);
static char*   readfullnamedfile(const char *fname, size_t *size);
static void    removebackslashes(char **str);
static void    run(void);
static void    testinternal(const char *cmdline, bool negated);
static void    writeinternal(const char *fname, const char *sep, bool append);
static Intval* xtractinternal(regex_t *regex, Intval **prevsel, Intval *sel, bool negated);

static void cmd_print(const Cmd *cmd); /* command callbacks */
static void cmd_delete(const Cmd *cmd);
static void cmd_change(const Cmd *cmd);
static void cmd_sub(const Cmd *cmd);
static void cmd_guard(const Cmd *cmd);
static void cmd_vguard(const Cmd *cmd);
static void cmd_xtract(const Cmd *cmd);
static void cmd_ytract(const Cmd *cmd);
static void cmd_insert(const Cmd *cmd);
static void cmd_append(const Cmd *cmd);
static void cmd_surround(const Cmd *cmd);
static void cmd_flip(const Cmd *cmd);
static void cmd_undox(const Cmd *cmd);
static void cmd_read(const Cmd *cmd);
static void cmd_readapp(const Cmd *cmd);
static void cmd_write(const Cmd *cmd);
static void cmd_writeapp(const Cmd *cmd);
static void cmd_extcmd(const Cmd *cmd);
static void cmd_extcmd_i(const Cmd *cmd);
static void cmd_extcmd_o(const Cmd *cmd);
static void cmd_extcmd_io(const Cmd *cmd);
static void cmd_extcmd_t(const Cmd *cmd);
static void cmd_extcmd_tn(const Cmd *cmd);
static void cmd_lines(const Cmd *cmd);

static const CmdDesc cmddescs[CMD_MAX] = {
	/* id (index)         ch     argcnt callback */
	/* CMD_PRINT     */ { 'p',   0,     cmd_print     },
	/* CMD_DELETE    */ { 'd',   0,     cmd_delete    },
	/* CMD_CHANGE    */ { 'c',   1,     cmd_change    },
	/* CMD_SUB       */ { 's',   2,     cmd_sub       },
	/* CMD_GUARD     */ { 'g',   1,     cmd_guard     },
	/* CMD_VGUARD    */ { 'v',   1,     cmd_vguard    },
	/* CMD_XTRACT    */ { 'x',   1,     cmd_xtract    },
	/* CMD_YTRACT    */ { 'y',   1,     cmd_ytract    },
	/* CMD_INSERT    */ { 'i',   1,     cmd_insert    },
	/* CMD_APPEND    */ { 'a',   1,     cmd_append    },
	/* CMD_SURROUND  */ { 'S',   2,     cmd_surround  },
	/* CMD_FLIP      */ { '~',   0,     cmd_flip      },
	/* CMD_UNDOX     */ { 'u',   0,     cmd_undox     },
	/* CMD_READ      */ { 'r',   1,     cmd_read      },
	/* CMD_READAPP   */ { 'R',   1,     cmd_readapp   },
	/* CMD_WRITE     */ { 'w',   2,     cmd_write     },
	/* CMD_WRITEAPP  */ { 'W',   2,     cmd_writeapp  },
	/* CMD_EXTCMD    */ { '!',   1,     cmd_extcmd    },
	/* CMD_EXTCMD_I  */ { '<',   1,     cmd_extcmd_i  },
	/* CMD_EXTCMD_O  */ { '>',   1,     cmd_extcmd_o  },
	/* CMD_EXTCMD_IO */ { '|',   1,     cmd_extcmd_io },
	/* CMD_EXTCMD_T  */ { 't',   1,     cmd_extcmd_t  },
	/* CMD_EXTCMD_TN */ { 'T',   1,     cmd_extcmd_tn },
	/* CMD_LINES     */ { 'L',   0,     cmd_lines     },
};

static const struct option long_options[] = {
	{ "basic-regexp"   , no_argument      , NULL, 'B' },
	{ "extended-regexp", no_argument      , NULL, 'E' },
	{ "file"           , required_argument, NULL, 'f' },
	{ "help"           , no_argument      , NULL, 'h' },
	{ "ignorecase"     , no_argument      , NULL, 'i' },
	{ "quiet"          , no_argument      , NULL, 'n' },
	{ "reg-newline"    , no_argument      , NULL, 'N' },
	{ "version"        , no_argument      , NULL, 'v' },
	{ 0                , 0                , 0   ,  0  }
};

static Cmd    *cmds    = NULL; /* globals */
static Cmd    *lastcmd = NULL;
static Intval *sels    = NULL;
static Intval *lastsel = NULL;
static char   *buffer;
static size_t  buflen;

static bool quiet       = false; /* settings */
static bool ignorecase  = false;
static bool extendedreg = true;
static bool regnewline  = false;

Cmd*
addcmd(CmdId id)
{
	size_t i;
	Cmd *cmd = alloc(sizeof(Cmd));

	cmd->id = id;
	if (0 < cmddescs[id].argcnt) {
		cmd->args = alloc(sizeof(char*) * cmddescs[id].argcnt);
		for (i = 0; i < cmddescs[id].argcnt; ++i) {
			cmd->args[i] = NULL;
		}
	}
	else {
		cmd->args = NULL;
	}
	cmd->regex = NULL;
	cmd->next = NULL;

	if (lastcmd) {
		lastcmd->next = cmd;
	}
	else {
		cmds = cmd;
		lastcmd = cmd;
	}
	return cmd;
}

Intval*
addintv(size_t from, size_t len, Intval **list, Intval **last)
{
	Intval *intv = alloc(sizeof(Intval));

	intv->from = from;
	intv->len = len;
	intv->next = NULL;

	if (*list) {
		(*last)->next = intv;
	}
	else {
		*list = intv;
	}
	*last = intv;
	return intv;
}

void*
alloc(size_t size)
{
	void *buf = malloc(size);
	if (buf) {
		return buf;
	}
	perror("malloc()");
	exit(ERR_MEM_ALLOC_FAILED);
}

CmdId
chtocmdid(char ch)
{
	unsigned int i;
	for (i = 0; i < ARRAY_SIZE(cmddescs); ++i) {
		if (cmddescs[i].ch == ch) {
			return i;
		}
	}
	return CMD_MAX; /* not found */
}

void
cleanupall(void)
{
	cleanupsels();
	cleanupcmds();
	free(buffer);
}

void
cleanupcmds(void)
{
	Cmd *cmd;
	Cmd *nextc;
	unsigned int i;

	for (cmd = cmds; cmd != NULL;) {
		nextc = cmd->next;
		for (i = 0; i < cmddescs[cmd->id].argcnt; ++i) {
			free(cmd->args[i]);
		}
		free(cmd->args);
		if (cmd->regex) {
			regfree(cmd->regex);
			free(cmd->regex);
		}
		free(cmd);
		cmd = nextc;
	}
	cmds = NULL;
	lastcmd = NULL;
}

void
cleanupsels(void)
{
	Intval *sel;
	Intval *nexts;

	for (sel = sels; sel != NULL;) {
		nexts = sel->next;
		free(sel);
		sel = nexts;
	}
	sels = NULL;
	lastsel = NULL;
}

void
emptyargerr(const Cmd *cmd)
{
	switch (cmd->id) {
	case CMD_READ:     case CMD_READAPP:  case CMD_WRITE:    case CMD_WRITEAPP:
	case CMD_EXTCMD:   case CMD_EXTCMD_I: case CMD_EXTCMD_O: case CMD_EXTCMD_IO:
	case CMD_EXTCMD_T: case CMD_EXTCMD_TN:
		if (!cmd->args[0]) {
			fprintf(stderr, "Error: argument cannot be empty for '%c'!\n", cmddescs[cmd->id].ch);
			cleanupall(); exit(ERR_EMPTY_ARG);
		}
	default: break;
	}
}

void
escapechars(char **str, bool freeorig)
{
	char *newstr = alloc(strlen(*str) + 1);
	size_t iold = 0;
	size_t inew = 0;

	for (; (*str)[iold] != '\0'; ++iold, ++inew) {
		if ((*str)[iold] == '\\') {
			switch ((*str)[iold + 1]) {
				case 'n': newstr[inew] = '\n'; ++iold; continue;
				case 't': newstr[inew] = '\t'; ++iold; continue;
			}
		}
		newstr[inew] = (*str)[iold];
	}
	newstr[inew] = '\0';
	if (freeorig) {
		free(*str);
	}
	*str = newstr;
}

void
compileregexes(void)
{
	Cmd *cmd;
	int cflags = 0;
	int errcode;
	char errbuf[ERRBUF_SIZE];

	if (ignorecase)  { cflags |= REG_ICASE;    }
	if (extendedreg) { cflags |= REG_EXTENDED; }
	if (regnewline)  { cflags |= REG_NEWLINE;  }

	for (cmd = cmds; cmd != NULL; cmd = cmd->next) {
		switch (cmd->id) {
		case CMD_SUB:
		case CMD_GUARD:
		case CMD_VGUARD:
		case CMD_XTRACT:
		case CMD_YTRACT:
			if (cmd->args[0]) { /* empty args[0] -> NULL regex, which must be handled later */
				cmd->regex = alloc(sizeof(regex_t));
				if ((errcode = regcomp(cmd->regex, cmd->args[0], cflags)) != 0) {
					regerror(errcode, cmd->regex, errbuf, ARRAY_SIZE(errbuf));
					fprintf(stderr, "Error: invalid pattern '%s': %s!\n", cmd->args[0], errbuf);
					cleanupcmds(); exit(ERR_REGCOMP_FAILED);
				}
			}
			break;
		default: break;
		}
	}
}

void
cmd_print(const Cmd *cmd)
{
	Intval *sel;
	for (sel = sels; sel != NULL; sel = sel->next) {
		fwrite(buffer + sel->from, sizeof(char), sel->len, stdout);
	}
}

void
cmd_delete(const Cmd *cmd)
{
	static char *empty = "";
	Cmd proxycmd = {CMD_CHANGE, &empty, NULL, NULL};
	cmd_change(&proxycmd);
}

void
cmd_change(const Cmd *cmd)
{
	Intval *sel;
	size_t iold = 0;
	size_t inew = 0;
	size_t newbuflen = buflen;
	char *newbuffer;
	const char *tostr = cmd->args[0];
	size_t tostrlen = tostr ? strlen(tostr) : 0;

	for (sel = sels; sel != NULL; sel = sel->next) {
		newbuflen += (tostrlen - sel->len);
	}

	if (newbuflen == 0) { /* empty buffer needs no new memory or copying */
		buffer[0] = '\0';
		buflen = 0;
		cleanupsels();
		return;
	}

	newbuffer = alloc(newbuflen + 1);
	for (sel = sels; sel != NULL;) {
		if (iold < sel->from) {
			memcpy(newbuffer + inew, buffer + iold, sel->from - iold);
			inew += sel->from - iold;
			iold = sel->from;
		}
		else {
			memcpy(newbuffer + inew, tostr, tostrlen);
			inew += tostrlen;
			iold += sel->len;
			sel = sel->next;
		}
	}
	if (inew < newbuflen) {
		memcpy(newbuffer + inew, buffer + iold, buflen - iold);
	}

	free(buffer);
	buffer = newbuffer;
	buflen = newbuflen;
	cleanupsels(); /* selection should be reset after a change */
	addintv(0, buflen, &sels, &lastsel);
}

void
cmd_sub(const Cmd *cmd)
{
	Intval *sel;
	char tmp;
	char *str;
	regmatch_t pmatch[1 + RE_SUBMATCH_CNT]; /* 0th is entire match, rest are submatches */
	Intval *intv;
	Intval *tmpintv;
	Intval *matchintvs = NULL;
	Intval *lastintv = NULL;
	unsigned int matchcnt = 0;
	unsigned int matchcnt_sel;
	const char *tostr = cmd->args[1];
	size_t tostrlen = tostr ? strlen(tostr) : 0;
	size_t replacedlen = 0;
	size_t replacedlen_sel;
	size_t newbuflen;
	size_t iold;
	size_t inew;
	size_t offs;
	size_t newseloffs = 0;
	char *newbuffer;

	if (!cmd->regex && (!cmd->args[0] || (strcmp(cmd->args[0], "^") && strcmp(cmd->args[0], "$")))) {
		return; /* empty regex matches nothing -> no match -> no sub to do */
	}

	for (sel = sels; sel != NULL; sel = sel->next) {
		tmp = buffer[sel->from + sel->len];
		buffer[sel->from + sel->len] = '\0';
		str = buffer + sel->from;

		matchcnt_sel = 0;
		replacedlen_sel = 0;

		/* handle some special cases (e.g. zero size regexes) */
		if (!strcmp(cmd->args[0], "^")) {
			addintv((size_t)(str - buffer), 0, &matchintvs, &lastintv);
			++matchcnt_sel;
		}
		else if (!strcmp(cmd->args[0], "$")) {
			addintv(sel->from + sel->len, 0, &matchintvs, &lastintv);
			++matchcnt_sel;
		}
		else if (!strcmp(cmd->args[0], "^$")) {
			if (sel->len == 0) { /* should only match an empty range */
				intv = addintv(sel->from, 0, &matchintvs, &lastintv);
				++matchcnt_sel;
				replacedlen_sel += intv->len;
			}
		}
		else {
			while (regexec(cmd->regex, str, ARRAY_SIZE(pmatch), pmatch, 0) == 0) {
				intv = addintv(
				  (size_t)(str - buffer) + (size_t)pmatch[0].rm_so,
				  (size_t)(pmatch[0].rm_eo - pmatch[0].rm_so),
				  &matchintvs,
				  &lastintv
				);
				++matchcnt_sel;
				replacedlen_sel += intv->len;
				str += pmatch[0].rm_eo;
				if (*str == '\0') {
					break;
				}
			}
		}
		buffer[sel->from + sel->len] = tmp;

		matchcnt += matchcnt_sel;
		replacedlen += replacedlen_sel;

		sel->from += newseloffs; /* update selection intervals */
		offs = matchcnt_sel * tostrlen - replacedlen_sel;
		sel->len += offs;
		newseloffs += offs;
	}

	if (matchcnt == 0) {
		return; /* no match, nothing to substitute */
	}

	newbuflen = buflen - replacedlen + matchcnt * tostrlen;
	newbuffer = alloc(newbuflen + 1);

	iold = 0;
	inew = 0;
	for (intv = matchintvs; intv != NULL;) {
		if (iold < intv->from) {
			memcpy(newbuffer + inew, buffer + iold, intv->from - iold);
			inew += intv->from - iold;
			iold = intv->from;
		}
		else {
			if (tostrlen != 0) {
				memcpy(newbuffer + inew, tostr, tostrlen);
				inew += tostrlen;
			}
			iold += intv->len;
			intv = intv->next;
		}
	}
	if (inew < newbuflen) {
		memcpy(newbuffer + inew, buffer + iold, buflen - iold);
	}

	free(buffer);
	buffer = newbuffer;
	buflen = newbuflen;

	/* cleanup */
	for (intv = matchintvs; intv != NULL;) {
		tmpintv = intv;
		intv = intv->next;
		free(tmpintv);
	}
}

void
cmd_guard(const Cmd *cmd)
{
	guardinternal(cmd, false);
}

void
cmd_vguard(const Cmd *cmd)
{
	guardinternal(cmd, true);
}

void
cmd_xtract(const Cmd *cmd)
{
	Intval *sel;
	Intval *prevsel = NULL;

	/* zero length extractions should result in no extraction */
	if (!cmd->args[0] || !strcmp(cmd->args[0], "^") || !strcmp(cmd->args[0], "$") || !strcmp(cmd->args[0], "^$")) {
		cleanupsels();
		return;
	}

	for (sel = sels; sel != NULL;) {
		prevsel = xtractinternal(cmd->regex, &prevsel, sel, false);
		sel = prevsel ? prevsel->next : NULL;
	}
	lastsel = prevsel;
}

void
cmd_ytract(const Cmd *cmd)
{
	Intval *sel;
	Intval *prevsel = NULL;

	/* complement of zero length extractions should imply full extraction */
	if (!cmd->args[0] || !strcmp(cmd->args[0], "^") || !strcmp(cmd->args[0], "$") || !strcmp(cmd->args[0], "^$")) {
		return;
	}

	for (sel = sels; sel != NULL;) {
		prevsel = xtractinternal(cmd->regex, &prevsel, sel, true);
		sel = prevsel ? prevsel->next : NULL;
	}
	lastsel = prevsel;
}

void
cmd_insert(const Cmd *cmd)
{
	static char *patternstart = "^";
	Cmd proxycmd = {CMD_SUB, NULL, NULL, NULL};
	char *args[2];
	args[0] = patternstart;
	args[1] = cmd->args[0]; /* prefix */
	proxycmd.args = args;
	cmd_sub(&proxycmd);
}

void
cmd_append(const Cmd *cmd)
{
	static char *patternend = "$";
	Cmd proxycmd = {CMD_SUB, NULL, NULL, NULL};
	char *args[2];
	args[0] = patternend;
	args[1] = cmd->args[0]; /* suffix */
	proxycmd.args = args;
	cmd_sub(&proxycmd);
}

void
cmd_surround(const Cmd *cmd)
{
	Cmd proxyins = {CMD_INSERT, NULL, NULL, NULL};
	Cmd proxyapp = {CMD_APPEND, NULL, NULL, NULL};

	proxyins.args = &(cmd->args[0]); /* prefix */
	proxyapp.args = &(cmd->args[1]); /* suffix */

	cmd_insert(&proxyins);
	cmd_append(&proxyapp);
}

void
cmd_flip(const Cmd *cmd)
{
	Intval bound; bound.from = 0; bound.len = buflen; bound.next = NULL;
	flipintvals(&bound, &sels, &lastsel);
}

void
cmd_undox(const Cmd *cmd)
{
	cleanupsels();
	addintv(0, buflen, &sels, &lastsel);
}

void
cmd_read(const Cmd *cmd)
{
	char *fcontent = readfullnamedfile(cmd->args[0], NULL);
	Cmd proxycmd = {CMD_CHANGE, NULL, NULL, NULL};
	if (fcontent) {
		proxycmd.args = &fcontent;
		cmd_change(&proxycmd);
		free(fcontent);
	}
	else {
		cleanupall(); exit(ERR_CANNOT_READ_INPUT);
	}
}

void
cmd_readapp(const Cmd *cmd)
{
	char *fcontent = readfullnamedfile(cmd->args[0], NULL);
	Cmd proxycmd = {CMD_APPEND, NULL, NULL, NULL};
	if (fcontent) {
		proxycmd.args = &fcontent;
		cmd_append(&proxycmd);
		free(fcontent);
	}
	else {
		cleanupall(); exit(ERR_CANNOT_READ_INPUT);
	}
}

void
cmd_write(const Cmd *cmd)
{
	writeinternal(cmd->args[0], cmd->args[1], false);
}

void
cmd_writeapp(const Cmd *cmd)
{
	writeinternal(cmd->args[0], cmd->args[1], true);
}

void
cmd_extcmd(const Cmd *cmd)
{
	Intval *sel;
	for (sel = sels; sel != NULL; sel = sel->next) {
		system(cmd->args[0]);
	}
}

void
cmd_extcmd_i(const Cmd *cmd)
{
	Cmd proxycmd = {CMD_CHANGE, NULL, NULL, NULL};
	FILE *cmdf = popen(cmd->args[0], "r");
	char *cmdout = NULL;

	if (!cmdf) {
		perror("popen()");
		cleanupall(); exit(ERR_EXTCMD_RUN_FAILED);
	}
	if (!(cmdout = readfullfile(cmdf, NULL))) {
		cleanupall(); exit(ERR_CANNOT_READ_INPUT);
	}
	pclose(cmdf);

	proxycmd.args = &cmdout;
	cmd_change(&proxycmd);
	free(cmdout);
}

void
cmd_extcmd_o(const Cmd *cmd)
{
	Intval *sel;
	FILE *cmdf;

	for (sel = sels; sel != NULL; sel = sel->next) {
		if (!(cmdf = popen(cmd->args[0], "w"))) {
			perror("popen()");
			cleanupall(); exit(ERR_EXTCMD_RUN_FAILED);
		}
		fwrite(buffer + sel->from, sizeof(char), sel->len, cmdf);
		pclose(cmdf);
	}
}

void
cmd_extcmd_io(const Cmd *cmd)
{
	Intval *sel;
	int inpipefd[2];
	int outpipefd[2];
	pid_t pid;
	int childret;
	ssize_t rwret;
	size_t rwcnt;
	size_t bsize;
	char *buf;
	char *bptr;
	void *reallocret;
	StrList *rstr = NULL;
	StrList *rstrtmp;
	StrList *replacestrs = NULL;
	StrList *lastreplacestr = NULL;
	long newbuflen = (signed)buflen;
	char *newbuffer;
	size_t iold;
	size_t inew;

	for (sel = sels; sel != NULL; sel = sel->next) {
		/* use two pipes for I/O communication */
		if (pipe(inpipefd) != 0 || pipe(outpipefd) != 0) {
			perror("pipe()");
			cleanupall(); exit(ERR_EXTCMD_RUN_FAILED);
		}

		pid = fork();
		if (pid == -1) {
			perror("fork()");
			cleanupall(); exit(ERR_EXTCMD_RUN_FAILED);
		}

		if (pid == 0) {
			dup2(outpipefd[0], STDIN_FILENO);
			dup2(inpipefd[1], STDOUT_FILENO);
			dup2(inpipefd[1], STDERR_FILENO);

			close(outpipefd[0]);
			close(outpipefd[1]);
			close(inpipefd[0]);
			close(inpipefd[1]);

#if __linux__
			prctl(PR_SET_PDEATHSIG, SIGTERM); /* send SIGTERM if the parent dies */
#endif

			execl("/bin/sh", "sh", "-c", cmd->args[0], (char*)NULL);
			exit(ERR_EXTCMD_RUN_FAILED); /* exec returned meaning an error occured */
		}

		close(outpipefd[0]); /* close unused pipe ends */
		close(inpipefd[1]);

		/* write selection to cmd's stdin */
		rwcnt = 0;
		while (0 < (rwret = write(outpipefd[1], buffer + sel->from + rwcnt, sel->len - rwcnt))) {
			rwcnt += (size_t)rwret;
		}
		if (rwret == -1) {
			perror("write()");
			cleanupall(); exit(ERR_CANNOT_WRITE_OUTPUT);
		}
		close(outpipefd[1]);

		/* read cmd's stdout and replace selection with it */
		bsize = READ_CHUNK_SIZE; /* will get doubled for each new realloc */
		buf = alloc(bsize);      /* with 64 KB chunk size: 100 MB input needs 11 reallocs, 1 GB needs 14 */
		bptr = buf;
		rwcnt = 0; rwret = 0;
		do {
			rwcnt += (size_t)rwret;
			bptr += rwret;
			if (bsize < rwcnt + READ_CHUNK_SIZE) {
				if ((reallocret = realloc(buf, bsize *= 2))) {
					buf = reallocret;
					bptr = buf + rwcnt;
				}
				else {
					perror("realloc()");
					cleanupall(); exit(ERR_MEM_ALLOC_FAILED);
				}
			}
		} while (0 < (rwret = read(inpipefd[0], bptr, READ_CHUNK_SIZE)));
		if (rwret == -1) {
			perror("read()");
			cleanupall(); exit(ERR_CANNOT_WRITE_OUTPUT);
		}
		close(inpipefd[0]);

		*bptr = '\0';
		rstr = alloc(sizeof(StrList));
		rstr->str = buf;
		rstr->next = NULL;
		if (lastreplacestr) {
			lastreplacestr->next = rstr;
		}
		else {
			replacestrs = rstr;
		}
		lastreplacestr = rstr;

		newbuflen += ((bptr - buf) - (long)sel->len);

		waitpid(pid, &childret, 0);
	}

	newbuffer = alloc((size_t)newbuflen + 1);
	iold = 0;
	inew = 0;
	sel = sels;
	rstr = replacestrs;
	while (inew < (size_t)newbuflen) {
		if (!sel) {
			memcpy(newbuffer + inew, buffer + iold, (size_t)newbuflen - inew);
			break;
		}
		if (iold < sel->from) {
			memcpy(newbuffer + inew, buffer + iold, sel->from - iold);
			inew += sel->from - iold;
			iold += sel->from - iold;
		}
		else {
			memcpy(newbuffer + inew, rstr->str, strlen(rstr->str));
			inew += strlen(rstr->str);
			iold += sel->len;
			sel = sel->next;
			rstr = rstr->next;
		}
	}

	for (rstr = replacestrs; rstr != NULL;) { /* cleanup */
		rstrtmp = rstr;
		rstr = rstr->next;
		free(rstrtmp->str);
		free(rstrtmp);
	}

	free(buffer);
	buffer = newbuffer;
	buflen = (size_t)newbuflen;
	cleanupsels(); /* selection should be reset after a change */
	addintv(0, buflen, &sels, &lastsel);
}

void
cmd_extcmd_t(const Cmd *cmd)
{
	testinternal(cmd->args[0], false);
}

void
cmd_extcmd_tn(const Cmd *cmd)
{
	testinternal(cmd->args[0], true);
}

void
cmd_lines(const Cmd *cmd)
{
	static char *LINES_REGX = "[^\n]*\n";
	regex_t reg;
	Cmd proxycmd = {CMD_XTRACT, NULL, NULL, NULL};

	proxycmd.args = &LINES_REGX;
	proxycmd.regex = &reg;
	regcomp(&reg, LINES_REGX, 0); /* note: we can assume the above regex will always compile */
	cmd_xtract(&proxycmd);
	regfree(&reg);
}

void
flipintvals(const Intval *bound, Intval **intvs, Intval **lastintv)
{
	size_t start;
	size_t end;
	Intval *newintvs = NULL;
	Intval *newlastintv = NULL;
	Intval *previntv;
	Intval *intv;
	Intval *tmpintv;

	if (!(*intvs)) { /* empty interval flipped is the whole interval */
		addintv(bound->from, bound->len, &newintvs, &newlastintv);
	}
	else if ((*intvs)->from == bound->from && (*intvs)->len == bound->len) { /* whole interval flipped is empty */
		newintvs = NULL;
		newlastintv = NULL;
	}
	else {
		start = bound->from; /* before first intv */
		end = (*intvs)->from;
		if (bound->from < (*intvs)->from) {
			addintv(start, end - start, &newintvs, &newlastintv);
		}

		for (previntv = (*intvs), intv = (*intvs)->next; intv != NULL;) { /* gaps inbetween intvs */
			start = previntv->from + previntv->len;
			end = intv->from - 1;
			if (start <= end) {
				addintv(start, end - start + 1, &newintvs, &newlastintv);
			}
			previntv = intv;
			intv = intv->next;
		}

		start = (*lastintv)->from + (*lastintv)->len; /* after last intv */
		end = bound->from + bound->len - 1;
		if (start < end) {
			addintv(start, end - start, &newintvs, &newlastintv);
		}
	}

	for (intv = *intvs; intv != NULL;) { /* cleanup old intervals */
		tmpintv = intv->next;
		free(intv);
		intv = tmpintv;
	}
	*intvs = newintvs; /* replace with new intervals */
	*lastintv = newlastintv;
}

void
guardinternal(const Cmd *cmd, bool negated)
{
	Intval *sel;
	Intval *prevsel = NULL;
	Intval *tmpsel;
	char tmp;
	regmatch_t pmatch[1];

	for (sel = sels; sel != NULL;) { /* delete selections that do not match (or match if negated is set) */
		tmp = buffer[sel->from + sel->len];
		buffer[sel->from + sel->len] = '\0';

		if ((cmd->regex && regexec(cmd->regex, buffer + sel->from, ARRAY_SIZE(pmatch), pmatch, 0))
		    == (negated ? 0 : REG_NOMATCH)) {
			if (prevsel == NULL) {
				sels = sel->next;
			}
			else {
				prevsel->next = sel->next;
			}
			tmpsel = sel->next;
			buffer[sel->from + sel->len] = tmp;
			free(sel);
			sel = tmpsel;
		}
		else {
			prevsel = sel;
			buffer[sel->from + sel->len] = tmp;
			sel = sel->next;
		}
	}
}

void
parsecmds(char *cmdline)
{
	char *p = cmdline;
	Cmd *currcmd = NULL;
	CmdId cmdid = CMD_MAX;
	bool inarglist = false;
	unsigned int argind = 0;
	size_t pos = 0;
	size_t argbegin = 0;
	size_t arglen;
	bool incomment = false;
	bool escaped = false;

	while (*p != '\0') {
		if (incomment) {
			/* end comment */
			if (*p == '\n') {
				incomment = false;
			}
			/* otherwise: ignore */
		}
		else if (inarglist) {
			/* arg close */
			if (*p == '/' && !escaped) {
				/* store arg to current cmd */
				arglen = pos - argbegin;
				if (0 < arglen) {
					currcmd->args[argind] = alloc(arglen + 1);
					strncpy(currcmd->args[argind], cmdline + argbegin, arglen);
					currcmd->args[argind][arglen] = '\0';
					removebackslashes(&currcmd->args[argind]);
				}
				else {
					currcmd->args[argind] = NULL; /* some cmds like 's' can have empty args */
				}
				argbegin = pos + 1;
				++argind;
				if (0 == cmddescs[currcmd->id].argcnt - argind) {
					currcmd = NULL;
					inarglist = false;
				}
			}
		}
		else if (*p == '/' && !escaped) {
			/* arg open */
			if (currcmd && 0 < cmddescs[currcmd->id].argcnt - argind) {
				inarglist = true;
				argbegin = pos + 1;
			}
			else {
				fprintf(stderr, "Error: Unexpected '/' at %lu!\n", pos);
				goto err;
			}
		}
		else {
			/* all whitespaces are valid separators between commands */
			if (isspace(*p)) {
			}
			/* start comment */
			else if (*p == '#') {
				incomment = true;
			}
			/* cmd open */
			else if ((cmdid = chtocmdid(*p)) != CMD_MAX) {
				currcmd = addcmd(cmdid);
				lastcmd = currcmd;
				if (cmddescs[currcmd->id].argcnt == 0) {
					currcmd = NULL;
				}
				argind = 0;
			}
			else {
				fprintf(stderr, "Error: Unexpected '%c' at %lu!\n", *p, pos);
				goto err;
			}
		}
		escaped = (*p == '\\');
		++p;
		++pos;
	}

	if (currcmd || inarglist) {
		fputs("Error: Last command is unterminated!\n", stderr);
		goto err;
	}

	if (!quiet && (!lastcmd || lastcmd->id != CMD_PRINT)) { /* add an implicit printing to the end */
		addcmd(CMD_PRINT);
	}

	return;
err:
	cleanupcmds();
	exit(ERR_INVALID_CMDLINE);
}

char*
readfullfile(FILE *file, size_t *size)
{
	size_t readsize = 0;
	size_t storedsize = 0;
	size_t bsize = READ_CHUNK_SIZE; /* will get doubled for each new realloc */
	char *buf = alloc(bsize);       /* with 64 KB chunk size: 100 MB input needs 11 reallocs, 1 GB needs 14 */
	char *bptr = buf;
	void *reallocret;

	do {
		storedsize += readsize;
		bptr += readsize;
		if (bsize < storedsize + READ_CHUNK_SIZE) {
			if ((reallocret = realloc(buf, bsize *= 2))) {
				buf = reallocret;
				bptr = buf + storedsize;
			}
			else {
				perror("realloc()");
				goto err;
			}
		}
	} while ((readsize = fread(bptr, 1, READ_CHUNK_SIZE, file)) == READ_CHUNK_SIZE);
	storedsize += readsize;
	bptr += readsize;
	*bptr = '\0';

	/* sanity checks */
	if (ferror(file)) {
		perror("fread() - ferror() set");
		goto err;
	}
	else if (!feof(file)) {
		perror("fread() - feof() unset");
		goto err;
	}

	if (size) {
		*size = storedsize;
	}
	return buf;
err:
	free(buf);
	return NULL;
}

char*
readfullnamedfile(const char *fname, size_t *size)
{
	char *buf = NULL;
	FILE *file;

	if (!fname) {
		fprintf(stderr, "Error: Filename is missing!\n");
		cleanupall(); exit(ERR_EMPTY_ARG);
	}

	file = fopen(fname, "r");
	if (file) {
		buf = readfullfile(file, size);
		fclose(file);
	}
	else {
		perror("fopen()");
		fprintf(stderr, "Error: Could not open '%s'!\n", fname);
	}
	return buf;
}

void
removebackslashes(char **str)
{
	char *p = *str;
	char *newstr = alloc(strlen(*str) + 1);
	size_t iold = 0;
	size_t inew = 0;
	bool escaped = false;

	/* \c -> c, \\ -> \, \\\\ -> \\, etc. */
	while (*p != '\0') {
		if (*p == '\\') {
			if (!escaped) {
				++p;
				++iold;
				escaped = true;
				continue;
			}
		}
		newstr[inew++] = (*str)[iold++];
		escaped = false;
		++p;
	}
	newstr[inew] = '\0';

	free(*str);
	*str = newstr;
}

void
run(void)
{
	Cmd *cmd;

	addintv(0, buflen, &sels, &lastsel);

	for (cmd = cmds; cmd != NULL; cmd = cmd->next) {
		emptyargerr(cmd);
		cmddescs[cmd->id].callback(cmd);
	}

	cleanupsels();
}

void
testinternal(const char *cmdline, bool negated)
{
	Intval *sel;
	Intval *prevsel = NULL;
	FILE *cmdf;
	int pcloseret;

	for (sel = sels; sel != NULL;) {
		if (!(cmdf = popen(cmdline, "w"))) {
			perror("popen()");
			cleanupall(); exit(ERR_EXTCMD_RUN_FAILED);
		}
		fwrite(buffer + sel->from, sizeof(char), sel->len, cmdf);
		pcloseret = pclose(cmdf);
		if ((pcloseret && !negated) || (!pcloseret && negated)) {
			if (prevsel) {
				prevsel->next = sel->next;
				free(sel);
				sel = prevsel->next;
			}
			else {
				sels = sel->next;
				free(sel);
				sel = sels;
			}
		}
		else {
			prevsel = sel;
			sel = sel->next;
		}
	}
}

void
writeinternal(const char *fname, const char *sep, bool append)
{
	FILE *fout;
	size_t seplen = sep ? strlen(sep) : 0;
	Intval *sel;

	if (!fname) {
		fprintf(stderr, "Error: Filename is missing!\n");
		cleanupall(); exit(ERR_EMPTY_ARG);
	}

	fout = fopen(fname, append ? "a" : "w");
	if (!fout) {
		perror("fopen()");
		fprintf(stderr, "Could not open '%s'!\n", fname);
		cleanupall(); exit(ERR_CANNOT_WRITE_OUTPUT);
	}

	for (sel = sels; sel != NULL; sel = sel->next) {
		fwrite(buffer + sel->from, sizeof(char), sel->len, fout);
		if (sel != lastsel) {
			fwrite(sep, sizeof(char), seplen, fout);
		}
	}

	fclose(fout);
}

Intval*
xtractinternal(regex_t *regex, Intval **prevsel, Intval *sel, bool negated)
{
	char tmp;
	char *str;
	regmatch_t pmatch[1];
	Intval *matchintvs = NULL;
	Intval *lastintv = NULL;
	Intval *nextsel = sel->next;

	tmp = buffer[sel->from + sel->len];
	buffer[sel->from + sel->len] = '\0';
	str = buffer + sel->from;

	if (regex) {
		while (regexec(regex, str, ARRAY_SIZE(pmatch), pmatch, 0) == 0) {
			if (pmatch[0].rm_eo == 0) {
				if (*str != '\0') {
					str += 1; /* don't store zero length matches */
					continue;
				}
				break;
			}
			addintv(
			  (size_t)(str - buffer) + (size_t)pmatch[0].rm_so,
			  (size_t)(pmatch[0].rm_eo - pmatch[0].rm_so),
			  &matchintvs,
			  &lastintv
		       );
			str += pmatch[0].rm_eo;
		}
	}

	buffer[sel->from + sel->len] = tmp;

	if (negated) {
		flipintvals(sel, &matchintvs, &lastintv);
	}

	if (matchintvs && !matchintvs->next && matchintvs->from == sel->from && matchintvs->len == sel->len) {
		free(matchintvs);
		return sel; /* single match is the whole input selection, so simply return that */
	}

	/* remove the old selection */
	if (*prevsel != NULL) {
		(*prevsel)->next = nextsel;
	}
	else {
		sels = nextsel;
	}
	free(sel);

	/* link in new sub-selections and return the last (if any) */
	if (matchintvs) {
		lastintv->next = nextsel;
		if (*prevsel != NULL) {
			(*prevsel)->next = matchintvs;
		}
		else {
			sels = matchintvs;
		}
		return lastintv;
	}
	return *prevsel;
}

int
main(int argc, char *argv[])
{
	int opt;
	int exitcode = EXIT_SUCCESS;
	unsigned int i;
	char *scriptfile = NULL;
	char *cmdline = NULL;

	/* parse options */
	while ((opt = getopt_long(argc, argv, "BEf:hinNv", long_options, NULL)) != -1) {
		switch (opt) {
		case 'B':
			extendedreg = false;
			break;
		case 'E':
			extendedreg = true;
			break;
		case 'f':
			free(scriptfile);
			scriptfile = alloc(strlen(optarg) + 1);
			strcpy(scriptfile, optarg);
			break;
		case 'h':
			for (i = 0; i < ARRAY_SIZE(HELP); ++i) {
				printf("%s", HELP[i]);
			}
			free(scriptfile);
			return EXIT_SUCCESS;
		case 'i':
			ignorecase = true;
			break;
		case 'n':
			quiet = true;
			break;
		case 'N':
			regnewline = true;
			break;
		case 'v':
			puts(VERSION);
			free(scriptfile);
			return EXIT_SUCCESS;
		default: break;
		}
	}

	/* read commands from script file (-f, --file) */
	if (scriptfile) {
		if (!(cmdline = readfullnamedfile(scriptfile, NULL))) {
			free(scriptfile);
			exit(ERR_NO_CMDLINE);
		}
	}
	/* read commands from first non-option arg (if any) */
	else {
		if (optind == argc) {
			fputs("Error: No commandline given!\n", stderr);
			exit(ERR_NO_CMDLINE);
		}
		cmdline = argv[optind];
		++optind;
	}

	/* parse commands */
	escapechars(&cmdline, scriptfile != NULL);
	parsecmds(cmdline);
	free(cmdline);
	free(scriptfile);
	compileregexes();

	if (optind == argc) {
		/* no file, run on standard input */
		if ((buffer = readfullfile(stdin, &buflen))) {
			run();
		}
		else {
			fputs("Error: could not read stdin!\n", stderr);
			exitcode = ERR_CANNOT_READ_INPUT;
		}
	}
	else {
		/* run on each file */
		while (optind < argc) {
			if ((buffer = readfullnamedfile(argv[optind], &buflen))) {
				run();
				free(buffer); buffer = NULL;
			}
			else {
				exitcode = ERR_CANNOT_READ_INPUT; /* can still process the other files */
			}
			++optind;
		}
	}

	cleanupall();
	return exitcode;
}

