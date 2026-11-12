# BEDOPS — patched, cross-platform build

A minimal patched copy of [**BEDOPS**](https://github.com/bedops/bedops)
(upstream `master` at `009c10c0` = release v2.4.42 plus two CI-only commits)
that builds and runs natively on **Linux, macOS (Intel + Apple Silicon), and
Windows (x64 + ARM64)**.

For BEDOPS' documentation, options and canonical source, see the upstream
repository <https://github.com/bedops/bedops> and the
[documentation](https://bedops.readthedocs.io). **This README covers only how
to build this tree and what was changed**; everything else is unchanged from
upstream.

Upstream BEDOPS builds only on Unix-like systems. This tree adds a native
Windows build (MSYS2, no Cygwin runtime) of

- the nine core programs — `bedops`, `bedmap`, `bedextract`,
  `closest-features`, `sort-bed`, `starch`, `unstarch`, `starchcat` and
  `starchstrip` — fixing what broke them there: text-mode I/O, the 1 MB
  Windows main-thread stack (`starch` crashed), a `sort-bed --tmpdir` check
  that cannot see an existing directory, and three compile errors;
- `convert2bed`, whose pipeline stages (`samtools`, `sort-bed`, `starch`)
  are started with `CreateProcess()` instead of `fork()`/`exec()`;
- the 18 conversion wrappers (`bam2bed`, `gff2starch`, `vcf2bed`, …), bash
  scripts upstream, as small native programs that run `convert2bed` the
  way the scripts do.

**Not ported:** the cluster scripts (`bam2bed_sge`, `*_slurm`,
`*_gnuParallel`, `starchcluster_*`, `update-sort-bed-*`), which drive a job
scheduler or GNU Parallel through bash.

---

## Building from source

Run every command **from this directory** (the one containing `Makefile`). The
build compiles the bundled zlib, bzip2 and jansson (`third-party/`) and links
every program statically, so the Windows programs need no DLLs beyond
Windows' own C runtime.

### Linux and macOS

Unchanged from upstream:

```bash
make all          # the three binary types: typical, megarow, float128
make install      # copies the typical type to bin/
```

### Windows x64 (MSYS2 **UCRT64** shell) and ARM64 (MSYS2 **CLANGARM64** shell)

Install the toolchain (`<env>` = `ucrt-x86_64` or `clang-aarch64`):

```bash
pacman -S --needed make mingw-w64-<env>-gcc   # UCRT64; on CLANGARM64: mingw-w64-<env>-clang
```

Then build the typical binary type:

```bash
# UCRT64
make typical
# CLANGARM64
make typical CC=clang CXX=clang++
```

The programs are `applications/bed/*/bin/<program>-typical.exe` (28: the nine
core programs, `convert2bed` and the 18 wrappers). Copy them under their plain
names (`bedops.exe`, `gff2bed.exe`, …) to one directory: a wrapper runs the
`convert2bed.exe` next to it, else the one on `PATH`, and `convert2bed`
finds `sort-bed`, `starch` and `samtools` (for BAM input) on `PATH`. Windows
has no symbolic links for upstream's `switch-BEDOPS-binary-type`, so pick one
binary type; `megarow` and `float128` build the same way (`make megarow`,
`make float128`).

### Verify (any platform)

Upstream's top-level `tests` target is broken (it looks for `tests/tests`), so
run the test groups directly. On Windows, first copy the programs to `bin/`
under their plain names, and put `bin/` first on `PATH`; the starch group needs
a `python` on `PATH` (the MSYS2 environment's own, e.g.
`PATH=$PWD/bin:/usr/bin:/clangarm64/bin:$PATH`):

```bash
cd tests
make -k -C bedops all BUILDTYPE=typical
make -k -C starch all BUILDTYPE=typical
make -k -C starch starchcat BUILDTYPE=typical
make -k -C conversion all BUILDTYPE=typical
```

On Windows ARM64 and x64 the same 67 `bedops` checks run as on macOS, with the
same results except `named-pipe`: it passes a bash process substitution
(`<(...)`, a `/proc/<pid>/fd/<n>` path only MSYS2 programs can open) to a
native program. `--ec` Test 001 passes although it is meant to fail, as on
macOS and Linux (an upstream bug). The six `starch` checks pass. The
`conversion` group (`wig2bed`) gives the same results as on macOS: 12 checks
pass and two `--keep-header` checks stop with error 22, as upstream does on
macOS.
`xplat_tests/` compares the Windows and macOS builds byte for byte (see below).

---

## Patches (vs upstream `009c10c0`)

Every edit to an upstream file carries a `bedops-crossplatform:` comment, so

```bash
grep -rn "bedops-crossplatform:" applications interfaces
```

lists them. Code changes are guarded by `#if defined(_WIN32)`, Makefile
changes by `ifeq ($(OS),Windows_NT)`; Linux and macOS builds are unchanged.

| File | Change | Reason |
|------|--------|--------|
| `applications/bed/{bedops,bedmap,bedextract,closestfeats,sort-bed}/src/*.cpp` (`main()`), `applications/bed/starch/src/{starch,unstarch,starchcat,starchstrip}.c` | At the top of `main()`, `_fmode = _O_BINARY` and binary stdin/stdout/stderr (+ `<fcntl.h>`/`<io.h>`) | Windows text mode turned every `\n` written into `\r\n` and would corrupt Starch archives streamed through stdin and stdout. `_fmode` makes every file opened afterwards binary too, so no call site needed changing. |
| `applications/bed/{starch,bedops,bedmap,bedextract,closestfeats,sort-bed}/src/Makefile` | Link with `-Wl,--stack,8388608` (added to `SFLAGS`) | Windows gives the main thread a 1 MB stack, Linux and macOS 8 MB. `starch` keeps several 1 MB buffers on the stack and died with a stack overflow (`0xC00000FD`) without writing anything. All nine programs get the 8 MB that Unix gives them. |
| `applications/bed/sort-bed/src/SortDetails.cpp` | `createDir()`: test that `--tmpdir` exists with `stat()`; close the probe file before removing it; `mkdir()` with one argument | `ifstream` cannot open a directory on Windows, so an existing `--tmpdir` (or `TMPDIR`) looked missing and `sort-bed` stopped with "Unknown problem creating directory"; Windows cannot remove an open file; Windows' `mkdir()` takes no mode. |
| `interfaces/src/data/starch/starchMetadataHelpers.c` | No `<sys/utsname.h>`; the host name in the per-run tag comes from `COMPUTERNAME` | Windows has no `uname()`. The tag (`pid<N>.<host>`) only makes the names of the temporary per-chromosome files unique. |
| `applications/bed/bedops/src/Input.hpp` | `#undef DIFFERENCE` before the `ModeType` enum | `bzlib.h` (through `starchApi.hpp`) includes `<windows.h>`, whose `winuser.h` defines `DIFFERENCE` as 11 and replaced the enumerator. |
| `applications/bed/conversion/src/convert2bed.{c,h}` | Windows process layer: `c2b_popen4()` starts a stage with `CreateProcess()`, passing the child only its three pipe ends (`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`); `c2b_waitpid()` replaces `waitpid()` and shapes the status as on Unix; the `cat` stage runs as a thread; pipes are binary, non-inheritable `_pipe()`s; dependencies are searched on `PATH` split at `;` with `.exe`; binary stdio; a no-op invalid-parameter handler | Windows has no `fork()`, `exec()`, `/bin/sh` or `<sys/wait.h>`. Only the pipe ends of one stage may be inherited, or a stage never sees end-of-file on its input. The no-op handler stops the C runtime from ending the process when upstream closes a pipe end twice (harmless on Unix). |
| `applications/bed/conversion/src/c2b_wrapper_win.c` *(new)* | A native launcher, built once per wrapper (`gff2bed.exe`, …), that parses the wrapper's options as the bash script does and runs `convert2bed --input=<fmt> --output=<bed\|starch> [options] -` | Windows cannot run the bash wrapper scripts. A note given with `--starch-note` is passed whole; the upstream scripts keep only its first word. |
| `applications/bed/conversion/src/Makefile` | Link with an 8 MB stack; on Windows also build the wrapper launchers | As for the other programs; one launcher per script in `wrappers/` (`*2bed`, `*2starch`). |
| `xplat_tests/` *(new)* | Parity harness: dumps 190 cases (all nine programs, `convert2bed` and every wrapper format; stdin, Starch input from this and an upstream build, CRLF input, spaces and non-ASCII paths, `sort-bed --tmpdir`) and compares a Windows dump with a macOS one byte for byte, Starch archives through `unstarch` | Checks that the Windows build behaves exactly like macOS, beyond the pass/fail of the upstream tests. See `xplat_tests/README.md`. |
| `README.md` | This file | The upstream README's citation and copyright are kept below. |

### Upstream behaviour kept as it is

- **CRLF input is not normalised.** Files are read in binary mode, as on Unix,
  so a BED file with Windows line endings keeps a trailing `\r` in its last
  field — exactly what upstream BEDOPS does on Linux. Convert such files to LF
  first (`dos2unix`).
- **Non-ASCII paths on Windows** (outside the ANSI code page) need a UTF-8
  application manifest (`<activeCodePage>UTF-8</activeCodePage>`) embedded in
  each `.exe`, as BEDOPS uses the narrow-character file APIs; without it
  `zażółć/ą.bed` reaches the program as `zazólc/a.bed`. The ngs-tools
  installer embeds one.
- **`starchcat` with a missing input archive** stops through `assert()`, as
  upstream does; on Windows the process ends with status `0xC0000409`.
- **Which `convert2bed` stage reports a failed `samtools`** is a race
  upstream: one stage waits with `waitpid(0, …)`, i.e. for any child. On
  Windows that wait finds no child, so the stage that started `samtools`
  always reports it.

---

## Citation

If you use BEDOPS in your research, please cite the following manuscript:

> Shane Neph, M. Scott Kuehn, Alex P. Reynolds, et al.
> [**BEDOPS: high-performance genomic feature operations**](http://bioinformatics.oxfordjournals.org/content/28/14/1919.abstract)
> *Bioinformatics* (2012) 28 (14): 1919-1920.

## Copyright & licensing

> Copyright (C) 2011-2025 Shane J. Neph, M. Scott Kuehn and Alex P. Reynolds
>
> Source code, documentation and media assets released under the
> [GNU Public License Version 2](LICENSE) (GPL v2).

The changes in this tree are released under the same licence. The bundled
third-party libraries keep their own licences (zlib: zlib licence; bzip2: BSD-style; jansson:
MIT) — see `third-party/`.
