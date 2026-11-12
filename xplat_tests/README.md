# Cross-platform parity tests

The upstream tests (`tests/`) check each build against expected results. These
scripts add a byte-level check that a native Windows build writes exactly what
the macOS (or Linux) build writes for the same command lines.

- `parity.py dump BIN_DIR DATA_DIR WORK_DIR OUT.json [case-substring]` runs
  every case in `CASES` with one build, each in its own empty directory under
  `WORK_DIR`, and records the exit code, stdout, stderr and every file the case
  wrote. `BIN_DIR` holds the nine programs (`bedops`, `bedmap`, `bedextract`,
  `closest-features`, `sort-bed`, `starch`, `unstarch`, `starchcat`,
  `starchstrip`), `convert2bed` and the 18 wrappers (`bam2bed`, `gff2starch`,
  …), with or without `.exe`; it is put first on `PATH`, where `convert2bed`
  finds `sort-bed` and `starch`. The BAM cases also need `samtools` on `PATH`.
  `DATA_DIR` is the tree's `tests/` directory (the upstream test data).
- `parity.py cmp A.json B.json` compares two dumps and prints `SAME`,
  `EXPECTED-DIFF` (listed in `EXPECTED_XPLAT`, with the reason) or `DIFF` with
  a diff per case, then the counts. The exit status is 1 if any case differs
  unexpectedly.
- `run_parity.sh BIN_DIR OUT.json [WORK_DIR] [case-substring]` runs the dump
  with the tree's `tests/` data and a temporary working directory.

What is compared:

- The working directory and `DATA_DIR` are replaced by `<CWD>` and `<DATA>`,
  in every spelling: as given and resolved, with `/` or `\`, and as `C:\…`,
  `C:/…` and `/c/…`. A `\` inside a path after these tags counts as `/`. All
  other bytes must be equal. Line endings are not normalised, so a CR the macOS
  build does not write is a difference (shown as `\r`).
- A Starch archive (on stdout or in a file) is compared as what the same
  build's `unstarch` and `unstarch --list-json` print for it. Every archive
  records its creation time and a temporary-file tag made of the process id and
  the host name; these change on every run, so they are masked (`<TIME>`,
  `pid<PID>.<HOST>`) when the dump is written, together with the metadata
  signature that covers them and the padding `unstarch --list` adds after the
  tag. No host name is stored in a dump. Everything else in the metadata
  (compressed sizes, per-chromosome signatures, counts, notes) must match.

The 190 cases cover all nine programs with their common options (every
`bedops` operation, `--range`, `--chrom`, `--ec`, `--header`; the `bedmap`
score, echo and overlap options, `--sci`/`--prec`, delimiters, `--faster`,
`--min-memory`; `closest-features` options; `bedextract` modes; `starch`
`--bzip2`/`--gzip`, notes, headers, a 60,000-line input; the `unstarch`
queries; `starchcat` with disjoint and shared chromosomes; `starchstrip`), and
these inputs: stdin, Starch archives made by the build itself and by an
upstream build (from `tests/starch/data`), CRLF input, a file without a final
newline, empty and missing files, unsorted input, a header, a directory with a
space and a non-ASCII directory (`zażółć`), and `sort-bed --tmpdir`/`TMPDIR`
with a new and an existing directory.

For `convert2bed` they run every wrapper on upstream's samples in
`applications/bed/conversion/src/tests/` (BAM, GFF, GTF, GVF, PSL, RepeatMasker,
SAM, VCF, WIG; `*2bed` and `*2starch`) with the format's options, bundled short
options, `--help`, an unknown option, an option of another format, empty input,
`--max-mem`/`--sort-tmpdir`, and `convert2bed` called directly. Upstream's
`bam/sample.bam` and `bam/split.bam` are truncated (samtools rejects them on
every platform), so they serve only as the failing-input cases; `data/sample.bam`
and `data/split.bam` were made from upstream's `sam/sample.sam` and
`sam/split.sam` with `samtools view -b --no-PG`.

`sort-bed --max-mem` accepts no less than 500 MB, so its temporary-file merge
is not reached by these small inputs. It was checked separately on Windows
with a 1.2 GB input: the output equals the in-memory sort and the temporary
files are removed.

## macOS / Linux

```bash
make typical
mkdir parity-bin
for p in bedops bedmap bedextract closest-features sort-bed starch unstarch starchcat starchstrip convert2bed; do
  cp applications/bed/*/bin/$p-typical parity-bin/$p
done
cp applications/bed/conversion/src/wrappers/*2bed applications/bed/conversion/src/wrappers/*2starch parity-bin/
xplat_tests/run_parity.sh parity-bin mac.json
```

## Windows (MSYS2)

Build the tree as described in the main `README.md` and collect the programs
the same way: every `applications/bed/*/bin/*-typical.exe` to
`parity-bin/` without `-typical` (the wrappers are built `.exe`s there). Then,
in the CLANGARM64 or UCRT64 shell, with that environment's Python and a
`samtools.exe` on `PATH`:

```bash
PATH=/clangarm64/bin:$PATH:/path/to/samtools-dir PYTHON=/clangarm64/bin/python \
    xplat_tests/run_parity.sh parity-bin win.json
```

Copy `win.json` next to `mac.json` and compare:
`python3 xplat_tests/parity.py cmp win.json mac.json`.

## Expected differences (`EXPECTED_XPLAT`)

- `sort-nonascii-path`, `bedops-nonascii-path`: the programs get their
  arguments in the ANSI code page unless the executable embeds a UTF-8
  code-page manifest (`<activeCodePage>UTF-8</activeCodePage>`); `zażółć`
  arrives as `zazólc`. A plain build has no manifest; the ngs-tools installer
  embeds one.
- `unstarch-corrupt`: the same errors and exit status. After the failed seek on
  the too-short file the C libraries leave the file position differently, so
  the byte count in one message differs.
- `starchcat-missing`: upstream reports a missing input archive through
  `assert()`. The C library words the assertion message differently, and
  `abort()` ends the process with SIGABRT on Unix and status `0xC0000409` on
  Windows.
- `gff2starch-gzip-note`: the upstream bash wrapper splits `--starch-note` at
  spaces and keeps only the first word (`two`); the Windows launcher passes the
  whole note (`two words`), as `convert2bed --starch-note` does on every
  platform.
- `bam2bed-truncated`, `bam2starch-truncated`: `samtools.exe` writes its error
  messages with CRLF line endings, and which `convert2bed` stage reports the
  failure is a race upstream (one stage waits with `waitpid(0, …)`, for any
  child); on Windows the stage that started `samtools` always reports it.
