/*
   bedops-crossplatform: native Windows replacement for the bash wrapper
   scripts in wrappers/ (gff2bed, bam2starch, ...), which Windows cannot run.

   Built once per wrapper with C2B_WRAPPER_INPUT ("gff") and
   C2B_WRAPPER_OUTPUT ("bed" or "starch"). Like the scripts it accepts the
   options listed for its format (short options may be bundled, long ones
   take "--name=value" or "--name value"), stops at the first argument that
   is not an option, prints `convert2bed --help-<format>` for -h/--help and
   for an unknown option (exit status 1), and otherwise runs

       convert2bed --input=<format> --output=<bed|starch> [options] -

   with its own stdin, stdout and stderr, returning convert2bed's exit
   status. Starch wrappers pass --starch-bzip2 unless --starch-gzip is
   given. convert2bed.exe is taken from this program's directory, else from
   PATH.

   Copyright (C) 2011-2025 Shane Neph, Scott Kuehn and Alex Reynolds;
   this file: released under the same licence (GNU GPL v2), see LICENSE.
*/

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef C2B_WRAPPER_INPUT
#error "define C2B_WRAPPER_INPUT"
#endif
#ifndef C2B_WRAPPER_OUTPUT
#error "define C2B_WRAPPER_OUTPUT"
#endif

typedef struct {
    const char* name;       /* convert2bed long option */
    char letter;            /* the wrapper's short option */
    int takes_value;
    const char* formats;    /* input formats that accept it, or "*" for all */
} c2b_wrapper_option_t;

static const c2b_wrapper_option_t options[] = {
    { "sort-tmpdir",          'r', 1, "*" },
    { "max-mem",              'm', 1, "*" },
    { "do-not-sort",          'd', 0, "*" },
    { "all-reads",            'a', 0, " bam sam " },
    { "keep-header",          'k', 0, " bam sam gff gvf psl rmsk vcf wig " },
    { "split",                's', 0, " bam sam psl " },
    { "split-with-deletions", 'S', 0, " bam sam " },
    { "reduced",              'R', 0, " bam sam " },
    { "attribute-key",        'a', 1, " gtf " },
    { "do-not-split",         'p', 0, " vcf " },
    { "snvs",                 'v', 0, " vcf " },
    { "insertions",           't', 0, " vcf " },
    { "deletions",            'n', 0, " vcf " },
    { "zero-indexed",         'x', 0, " wig " },
    { "multisplit",           'b', 1, " wig " },
    { "starch-bzip2",         'z', 0, "starch" },
    { "starch-gzip",          'g', 0, "starch" },
    { "starch-note",          'e', 1, "starch" },
};
#define OPTION_COUNT (sizeof(options) / sizeof(options[0]))

static int
accepted(const c2b_wrapper_option_t* o)
{
    if (strcmp(o->formats, "*") == 0) {
        return 1;
    }
    if (strcmp(o->formats, "starch") == 0) {
        return strcmp(C2B_WRAPPER_OUTPUT, "starch") == 0;
    }
    return strstr(o->formats, " " C2B_WRAPPER_INPUT " ") != NULL;
}

/* Append one argument to a command line, quoted as the C runtime parses it. */
static void
append_arg(char** line, size_t* len, size_t* cap, const char* arg)
{
    size_t need = *len + 2 * strlen(arg) + 4;
    const char* p;
    size_t backslashes = 0;
    int quote = (*arg == '\0') || (strpbrk(arg, " \t\"") != NULL);

    if (need > *cap) {
        *cap = 2 * need;
        *line = realloc(*line, *cap);
        if (!*line) {
            fprintf(stderr, "Error: out of memory\n");
            exit(1);
        }
    }
    if (*len) {
        (*line)[(*len)++] = ' ';
    }
    if (quote) {
        (*line)[(*len)++] = '"';
    }
    for (p = arg; *p; p++) {
        if (*p == '\\') {
            backslashes++;
        }
        else {
            if (*p == '"') {
                while (backslashes--) {
                    (*line)[(*len)++] = '\\';
                }
                (*line)[(*len)++] = '\\';
            }
            backslashes = 0;
        }
        (*line)[(*len)++] = *p;
    }
    if (quote) {
        while (backslashes--) {
            (*line)[(*len)++] = '\\';
        }
        (*line)[(*len)++] = '"';
    }
    (*line)[*len] = '\0';
}

static int
run_convert2bed(int argc, const char** args)
{
    char exe[32768];
    char* line = NULL;
    size_t len = 0, cap = 0;
    DWORD n = GetModuleFileNameA(NULL, exe, sizeof(exe));
    char* slash;
    const char* program = exe;
    STARTUPINFOA startup;
    PROCESS_INFORMATION process;
    DWORD code = 1;
    int i;

    slash = (n > 0 && n < sizeof(exe)) ? strrchr(exe, '\\') : NULL;
    if (slash && (size_t) (slash - exe) + sizeof("\\convert2bed.exe") <= sizeof(exe)) {
        strcpy(slash, "\\convert2bed.exe");
    }
    if (!slash || GetFileAttributesA(exe) == INVALID_FILE_ATTRIBUTES) {
        program = "convert2bed.exe";  /* CreateProcess searches PATH */
    }
    append_arg(&line, &len, &cap, program);
    for (i = 0; i < argc; i++) {
        append_arg(&line, &len, &cap, args[i]);
    }

    memset(&startup, 0, sizeof(startup));
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    if (!CreateProcessA(program == exe ? exe : NULL, line, NULL, NULL, TRUE, 0, NULL, NULL, &startup, &process)) {
        fprintf(stderr, "Error: could not start convert2bed (Windows error %lu)\n", (unsigned long) GetLastError());
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    free(line);
    return (int) code;
}

static int
help(int status)
{
    const char* args[] = { "--help-" C2B_WRAPPER_INPUT };
    run_convert2bed(1, args);
    return status;
}

int
main(int argc, char** argv)
{
    const char** args = malloc((2 * OPTION_COUNT + 4) * sizeof(char *));
    char** values = calloc(OPTION_COUNT, sizeof(char *));
    int set[OPTION_COUNT] = { 0 };
    int count = 0;
    int i;
    size_t k;

    if (!args || !values) {
        fprintf(stderr, "Error: out of memory\n");
        return 1;
    }
    for (i = 1; i < argc; i++) {
        const char* a = argv[i];
        if (a[0] != '-' || a[1] == '\0') {
            break;                      /* first non-option: stop, as getopts does */
        }
        if (strcmp(a, "--") == 0) {
            break;
        }
        if (a[1] == '-') {              /* --name, --name=value, --name value */
            const char* name = a + 2;
            const char* eq = strchr(name, '=');
            size_t name_len = eq ? (size_t) (eq - name) : strlen(name);
            if ((name_len == 4 && strncmp(name, "help", 4) == 0)
                || (strncmp(name, "help-" C2B_WRAPPER_INPUT, name_len) == 0
                    && name_len == strlen("help-" C2B_WRAPPER_INPUT))) {
                return help(0);
            }
            for (k = 0; k < OPTION_COUNT; k++) {
                if (accepted(&options[k]) && strlen(options[k].name) == name_len
                    && strncmp(options[k].name, name, name_len) == 0) {
                    break;
                }
            }
            if (k == OPTION_COUNT || (eq && !options[k].takes_value)) {
                return help(1);
            }
            set[k] = 1;
            if (options[k].takes_value) {
                if (eq) {
                    values[k] = (char *) eq + 1;
                }
                else if (i + 1 < argc) {
                    values[k] = argv[++i];
                }
                else {
                    values[k] = "";
                }
            }
            continue;
        }
        for (a = a + 1; *a; a++) {      /* bundled short options */
            if (*a == 'h') {
                return help(0);
            }
            for (k = 0; k < OPTION_COUNT; k++) {
                if (accepted(&options[k]) && options[k].letter == *a) {
                    break;
                }
            }
            if (k == OPTION_COUNT) {
                return help(1);
            }
            set[k] = 1;
            if (options[k].takes_value) {
                if (a[1]) {
                    values[k] = (char *) a + 1;
                }
                else if (i + 1 < argc) {
                    values[k] = argv[++i];
                }
                else {
                    return help(1);     /* missing value */
                }
                break;
            }
        }
    }

    args[count++] = "--input=" C2B_WRAPPER_INPUT;
    args[count++] = "--output=" C2B_WRAPPER_OUTPUT;
    if (strcmp(C2B_WRAPPER_OUTPUT, "starch") == 0) {
        for (k = 0; k < OPTION_COUNT; k++) {
            if (strcmp(options[k].name, "starch-gzip") == 0 && !set[k]) {
                size_t z;
                for (z = 0; z < OPTION_COUNT; z++) {
                    if (strcmp(options[z].name, "starch-bzip2") == 0) {
                        set[z] = 1;
                    }
                }
            }
        }
    }
    for (k = 0; k < OPTION_COUNT; k++) {
        if (!set[k]) {
            continue;
        }
        if (options[k].takes_value) {
            char* arg = malloc(strlen(options[k].name) + strlen(values[k]) + 4);
            if (!arg) {
                fprintf(stderr, "Error: out of memory\n");
                return 1;
            }
            sprintf(arg, "--%s=%s", options[k].name, values[k]);
            args[count++] = arg;
        }
        else {
            char* arg = malloc(strlen(options[k].name) + 3);
            if (!arg) {
                fprintf(stderr, "Error: out of memory\n");
                return 1;
            }
            sprintf(arg, "--%s", options[k].name);
            args[count++] = arg;
        }
    }
    args[count++] = "-";
    return run_convert2bed(count, args);
}
