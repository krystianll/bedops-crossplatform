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
Windows build (MSYS2, no Cygwin runtime) of the nine core programs —
`bedops`, `bedmap`, `bedextract`, `closest-features`, `sort-bed`, `starch`,
`unstarch`, `starchcat` and `starchstrip` — and fixes what broke them there:
text-mode I/O, the 1 MB Windows main-thread stack (`starch` crashed), a
`sort-bed --tmpdir` check that cannot see an existing directory, and three
compile errors.

**Not ported yet:** `convert2bed` and the conversion wrapper scripts
(`bam2bed`, `gff2bed`, `vcf2bed`, …), which run their pipelines through
`fork()`/`exec()`, and the cluster scripts (`starchcluster_*`,
`update-sort-bed-*`). On Windows the build reports `convert2bed` as failed;
everything else builds.

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

Then build the typical binary type (`-k` keeps going past `convert2bed`):

```bash
# UCRT64
make -k typical
# CLANGARM64
make -k typical CC=clang CXX=clang++
```

The programs are `applications/bed/*/bin/<program>-typical.exe`. Copy the nine
of them under their plain names (`bedops.exe`, …) to wherever you install
them. Windows has no symbolic links for upstream's `switch-BEDOPS-binary-type`,
so pick one binary type; `megarow` and `float128` build the same way
(`make -k megarow`, `make -k float128`).

### Verify (any platform)

Upstream's top-level `tests` target is broken (it looks for `tests/tests`), so
run the test groups directly. On Windows, first copy the nine programs to
`bin/` under their plain names; the starch group needs a `python` on `PATH`
(the MSYS2 environment's own, e.g. `PATH=/usr/bin:/clangarm64/bin:$PATH`):

```bash
cd tests
make -k -C bedops all BUILDTYPE=typical
make -k -C starch all BUILDTYPE=typical
make -k -C starch starchcat BUILDTYPE=typical
```

On Windows ARM64 and x64 the same 67 `bedops` checks run as on macOS, with the
same results except `named-pipe`: it passes a bash process substitution
(`<(...)`, a `/proc/<pid>/fd/<n>` path only MSYS2 programs can open) to a
native program. `--ec` Test 001 passes although it is meant to fail, as on
macOS and Linux (an upstream bug). The six `starch` checks pass.
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
| `xplat_tests/` *(new)* | Parity harness: dumps 139 cases (all nine programs; stdin, Starch input from this and an upstream build, CRLF input, spaces and non-ASCII paths, `sort-bed --tmpdir`) and compares a Windows dump with a macOS one byte for byte, Starch archives through `unstarch` | Checks that the Windows build behaves exactly like macOS, beyond the pass/fail of the upstream tests. See `xplat_tests/README.md`. |
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
