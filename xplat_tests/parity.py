"""Cross-platform parity of the BEDOPS core programs: run the same command
lines with two builds (e.g. native Windows and macOS) and compare the results
byte for byte.

usage: python3 parity.py dump BIN_DIR DATA_DIR WORK_DIR OUT.json [case-substring]
       python3 parity.py cmp A.json B.json      (e.g. Windows vs macOS)

BIN_DIR holds the programs (bedops, bedmap, ..., unstarch; `.exe` is added on
Windows when needed). DATA_DIR is the tree's tests/ directory. `dump` runs every
case in its own empty directory under WORK_DIR, after writing the shared inputs
(INPUTS) there, and records exit code, stdout, stderr and every file the case
wrote. The working directory and DATA_DIR are replaced by <CWD> and <DATA> (as
given or resolved, with either separator, and in the C:\\ C:/ /c/ drive forms).
Line endings are NOT normalised: a CR that macOS does not write is a
difference. A Starch archive (in stdout or a file) is recorded as the output of
the same build's `unstarch` and `unstarch --list-json`, with the creation time
and the per-run temporary tag (process id and host name) masked: these differ
on every run. `cmp` prints SAME, EXPECTED-DIFF (listed in EXPECTED_XPLAT with
the reason) or DIFF per case; exit status 1 means an unexpected difference.
"""
import difflib, json, os, re, shutil, subprocess, sys

D, C = "{D}", "{CWD}"
NZ = C + "/za\u017c\u00f3\u0142\u0107"          # a non-ASCII directory
SP = C + "/a b"                                 # a directory with a space
BD = D + "/bedops/data/"
SD = D + "/starch/data/"
SIG1 = SD + "001.unstarch.signature.001.test"   # Starch archives written by an upstream build
CAT1 = SD + "001.starchcat.disjoint_chrs.chr1.001.test"
CAT2 = SD + "001.starchcat.disjoint_chrs.chr2.001.test"

# Inputs written into every case's working directory (bytes, LF, sorted unless named otherwise).
A = (b"chr1\t10\t50\ta\t1\n"
     b"chr1\t40\t90\tb\t2.5\n"
     b"chr1\t200\t300\tc\t-3\n"
     b"chr2\t0\t100\td\t4\n"
     b"chr2\t150\t160\te\t0.125\n"
     b"chrX\t5\t15\tf\t7\n")
B = (b"chr1\t0\t20\tm1\t10\n"
     b"chr1\t45\t60\tm2\t20\n"
     b"chr1\t55\t58\tm2b\t1e-3\n"
     b"chr1\t250\t260\tm3\t30.5\n"
     b"chr2\t50\t155\tm4\t0.001\n"
     b"chr2\t150\t151\tm5\t2\n"
     b"chr3\t0\t10\tm6\t5\n")
UNSORTED = (b"chr2\t5\t10\tx\t1\n"
            b"chr10\t1\t2\ty\t2\n"
            b"chr1\t100\t200\tz\t3\n"
            b"chr1\t100\t200\tz\t3\n"
            b"chr1\t50\t300\tn\t4\n"
            b"chr1\t120\t130\tw\t5\n"
            b"chr2\t5\t9\tv\t6\n"
            b"chr1\t100\t200\tz2\t3\n")
HEADER = b"track name=t1 description=\"x y\"\n#comment\n" + A
INPUTS = {"a.bed": A, "b.bed": B, "u.bed": UNSORTED, "h.bed": HEADER,
          "crlf.bed": A.replace(b"\n", b"\r\n"), "nonl.bed": A.rstrip(b"\n"), "empty.bed": b""}


def starch_of(name, *opts):
    """Pre-step: archive one of the INPUTS with this build's starch."""
    return ("starch", list(opts) + [name], name.rsplit(".", 1)[0] + ".starch")


# (name, program, args, options). Options: stdin = DATA-relative path or bytes
# (b"" = empty input); setup = {working-dir-relative destination: source}, the
# source a {D} path (copied) or bytes; pre = [(program, args, output file)] run
# with this build before the case (their files are inputs, not results);
# env = extra environment (None removes a variable). Every argument may use
# {D} (DATA_DIR) and {CWD}.
CASES = [
    # sort-bed
    ("sort", "sort-bed", ["u.bed"], {}),
    ("sort-stdin", "sort-bed", ["-"], {"stdin": UNSORTED}),
    ("sort-two-files", "sort-bed", ["u.bed", "b.bed"], {}),
    ("sort-unique", "sort-bed", ["--unique", "u.bed"], {}),
    ("sort-duplicates", "sort-bed", ["--duplicates", "u.bed"], {}),
    ("sort-check-sorted", "sort-bed", ["--check-sort", "a.bed"], {}),
    ("sort-check-unsorted", "sort-bed", ["--check-sort", "u.bed"], {}),
    ("sort-crlf", "sort-bed", ["crlf.bed"], {}),
    ("sort-no-final-newline", "sort-bed", ["nonl.bed"], {}),
    ("sort-header", "sort-bed", ["h.bed"], {}),
    ("sort-empty", "sort-bed", ["empty.bed"], {}),
    ("sort-missing", "sort-bed", ["nosuch.bed"], {}),
    ("sort-tmpdir-new", "sort-bed", ["--max-mem", "1G", "--tmpdir", C + "/t", "u.bed"], {}),
    ("sort-tmpdir-existing", "sort-bed", ["--max-mem", "1G", "--tmpdir", C + "/t", "u.bed"],
     {"setup": {"t/.keep": b""}}),
    ("sort-tmpdir-env", "sort-bed", ["--max-mem", "1G", "u.bed"], {"env": {"TMPDIR": C + "/t"},
                                                                   "setup": {"t/.keep": b""}}),
    ("sort-max-mem-too-small", "sort-bed", ["--max-mem", "100M", "u.bed"], {}),
    ("sort-space-path", "sort-bed", [SP + "/u u.bed"], {"setup": {"a b/u u.bed": UNSORTED}}),
    ("sort-nonascii-path", "sort-bed", [NZ + "/\u0105.bed"], {"setup": {"za\u017c\u00f3\u0142\u0107/\u0105.bed": UNSORTED}}),
    ("sort-help", "sort-bed", ["--help"], {}),
    ("sort-version", "sort-bed", ["--version"], {}),
    # bedops
    ("bedops-merge", "bedops", ["-m", "a.bed", "b.bed"], {}),
    ("bedops-union", "bedops", ["-u", "a.bed", "b.bed"], {}),
    ("bedops-intersect", "bedops", ["-i", "a.bed", "b.bed"], {}),
    ("bedops-difference", "bedops", ["-d", "a.bed", "b.bed"], {}),
    ("bedops-symdiff", "bedops", ["-s", "a.bed", "b.bed"], {}),
    ("bedops-complement", "bedops", ["-c", "a.bed", "b.bed"], {}),
    ("bedops-element-of", "bedops", ["-e", "1", "a.bed", "b.bed"], {}),
    ("bedops-element-of-pct", "bedops", ["-e", "50%", "b.bed", "a.bed"], {}),
    ("bedops-not-element-of", "bedops", ["-n", "1", "a.bed", "b.bed"], {}),
    ("bedops-partition", "bedops", ["-p", "a.bed", "b.bed"], {}),
    ("bedops-chop-stagger", "bedops", ["-w", "20", "--stagger", "7", "a.bed"], {}),
    ("bedops-range", "bedops", ["--range", "5", "-m", "a.bed"], {}),
    ("bedops-range-asym", "bedops", ["--range", "-3:8", "-u", "a.bed"], {}),
    ("bedops-chrom", "bedops", ["--chrom", "chr1", "-u", "a.bed", "b.bed"], {}),
    ("bedops-ec-sorted", "bedops", ["--ec", "-u", "a.bed", "b.bed"], {}),
    ("bedops-ec-unsorted", "bedops", ["--ec", "-u", "u.bed"], {}),
    ("bedops-header", "bedops", ["--header", "-u", "h.bed"], {}),
    ("bedops-stdin", "bedops", ["-m", "-", "b.bed"], {"stdin": A}),
    ("bedops-crlf", "bedops", ["-u", "crlf.bed"], {}),
    ("bedops-no-final-newline", "bedops", ["-u", "nonl.bed", "b.bed"], {}),
    ("bedops-empty", "bedops", ["-m", "empty.bed"], {}),
    ("bedops-missing", "bedops", ["-m", "nosuch.bed"], {}),
    ("bedops-starch", "bedops", ["-m", "a.starch", "b.bed"], {"pre": [starch_of("a.bed")]}),
    ("bedops-starch-chrom", "bedops", ["--chrom", "chr2", "-u", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("bedops-upstream-starch", "bedops", ["-m", SIG1], {}),
    ("bedops-upstream-merge", "bedops", ["-m", BD + "006.merge.006a.test", BD + "006.merge.006b.test",
                                         BD + "006.merge.006c.test"], {}),
    ("bedops-upstream-partition", "bedops", ["-p", BD + "002.partition.002a.test", BD + "002.partition.002b.test"], {}),
    ("bedops-bad-option", "bedops", ["--nosuch", "a.bed"], {}),
    ("bedops-space-path", "bedops", ["-u", SP + "/x y.bed"], {"setup": {"a b/x y.bed": A}}),
    ("bedops-nonascii-path", "bedops", ["-u", NZ + "/\u0105.bed"], {"setup": {"za\u017c\u00f3\u0142\u0107/\u0105.bed": A}}),
    ("bedops-help", "bedops", ["--help"], {}),
    ("bedops-version", "bedops", ["--version"], {}),
    # bedmap
    ("bedmap-scores", "bedmap", ["--echo", "--count", "--sum", "--mean", "--min", "--max", "--median",
                                 "--stdev", "--variance", "--cv", "--mad", "--kth", "0.25", "--tmean", "0", "50",
                                 "--wmean", "a.bed", "b.bed"], {}),
    ("bedmap-scores-sci-prec", "bedmap", ["--echo", "--sci", "--prec", "10", "--mean", "--stdev", "--sum",
                                          "a.bed", "b.bed"], {}),
    ("bedmap-echo", "bedmap", ["--echo", "--echo-map", "--echo-map-id", "--echo-map-id-uniq", "--echo-map-score",
                               "--echo-map-range", "--echo-map-size", "--echo-overlap-size", "--echo-ref-name",
                               "--echo-ref-row-id", "--echo-ref-size", "--indicator", "a.bed", "b.bed"], {}),
    ("bedmap-bases", "bedmap", ["--echo", "--bases", "--bases-uniq", "--bases-uniq-f", "a.bed", "b.bed"], {}),
    ("bedmap-elements", "bedmap", ["--echo", "--max-element", "--min-element", "a.bed", "b.bed"], {}),
    ("bedmap-delims", "bedmap", ["--delim", "\t", "--multidelim", ",", "--echo", "--echo-map-id", "--count",
                                 "a.bed", "b.bed"], {}),
    ("bedmap-unmapped", "bedmap", ["--unmapped-val", "NA", "--echo", "--mean", "--echo-map-id", "a.bed", "b.bed"], {}),
    ("bedmap-skip-unmapped", "bedmap", ["--skip-unmapped", "--echo", "--count", "a.bed", "b.bed"], {}),
    ("bedmap-range", "bedmap", ["--range", "100", "--echo", "--echo-map-id", "a.bed", "b.bed"], {}),
    ("bedmap-bp-ovr", "bedmap", ["--bp-ovr", "5", "--echo", "--echo-map-id", "a.bed", "b.bed"], {}),
    ("bedmap-fraction-ref", "bedmap", ["--fraction-ref", "0.2", "--echo", "--echo-map-id", "a.bed", "b.bed"], {}),
    ("bedmap-fraction-map", "bedmap", ["--fraction-map", "0.5", "--echo", "--echo-map-id", "a.bed", "b.bed"], {}),
    ("bedmap-fraction-either", "bedmap", ["--fraction-either", "0.5", "--echo", "--count", "a.bed", "b.bed"], {}),
    ("bedmap-exact", "bedmap", ["--exact", "--echo", "--count", "a.bed", "a.bed"], {}),
    ("bedmap-faster", "bedmap", ["--faster", "--bp-ovr", "1", "--echo", "--count", "a.bed", "b.bed"], {}),
    ("bedmap-min-memory", "bedmap", ["--min-memory", "--echo", "--echo-map-id", "a.bed", "b.bed"], {}),
    ("bedmap-chrom", "bedmap", ["--chrom", "chr1", "--echo", "--count", "a.bed", "b.bed"], {}),
    ("bedmap-single-file", "bedmap", ["--echo", "--count", "--echo-map-id", "a.bed"], {}),
    ("bedmap-stdin", "bedmap", ["--echo", "--count", "-", "b.bed"], {"stdin": A}),
    ("bedmap-starch", "bedmap", ["--echo", "--mean", "a.bed", "b.starch"], {"pre": [starch_of("b.bed")]}),
    ("bedmap-upstream-starch", "bedmap", ["--echo", "--echo-map-id", SD + "001.starch_api.bedmap.001.test"], {}),
    ("bedmap-crlf", "bedmap", ["--echo", "--count", "crlf.bed", "b.bed"], {}),
    ("bedmap-ec-unsorted", "bedmap", ["--ec", "--echo", "--count", "u.bed", "b.bed"], {}),
    ("bedmap-missing", "bedmap", ["--echo", "nosuch.bed", "b.bed"], {}),
    ("bedmap-help", "bedmap", ["--help"], {}),
    # closest-features
    ("closest", "closest-features", ["a.bed", "b.bed"], {}),
    ("closest-closest-dist", "closest-features", ["--closest", "--dist", "a.bed", "b.bed"], {}),
    ("closest-no-overlaps", "closest-features", ["--no-overlaps", "--dist", "a.bed", "b.bed"], {}),
    ("closest-delim-noref", "closest-features", ["--delim", "\t", "--no-ref", "a.bed", "b.bed"], {}),
    ("closest-no-query", "closest-features", ["--no-query", "--dist", "a.bed", "b.bed"], {}),
    ("closest-chrom", "closest-features", ["--chrom", "chr2", "a.bed", "b.bed"], {}),
    ("closest-starch", "closest-features", ["--closest", "a.starch", "b.starch"],
     {"pre": [starch_of("a.bed"), starch_of("b.bed", "--gzip")]}),
    ("closest-stdin", "closest-features", ["-", "b.bed"], {"stdin": A}),
    ("closest-missing", "closest-features", ["nosuch.bed", "b.bed"], {}),
    # bedextract
    ("bedextract-list-chr", "bedextract", ["--list-chr", "b.bed"], {}),
    ("bedextract-chrom", "bedextract", ["chr2", "b.bed"], {}),
    ("bedextract-chrom-absent", "bedextract", ["chr9", "b.bed"], {}),
    ("bedextract-query-target", "bedextract", ["b.bed", "a.bed"], {}),
    ("bedextract-target-stdin", "bedextract", ["b.bed", "-"], {"stdin": A}),
    ("bedextract-starch", "bedextract", ["chr1", "b.starch"], {"pre": [starch_of("b.bed")]}),
    ("bedextract-starch-list-chr", "bedextract", ["--list-chr", SIG1], {}),
    ("bedextract-crlf", "bedextract", ["chr1", "crlf.bed"], {}),
    # starch (archives are compared through unstarch)
    ("starch-bzip2", "starch", ["--bzip2", "a.bed"], {}),
    ("starch-gzip", "starch", ["--gzip", "a.bed"], {}),
    ("starch-stdin", "starch", ["-"], {"stdin": B}),
    ("starch-note", "starch", ["--note=two words", "a.bed"], {}),
    ("starch-omit-signature", "starch", ["--omit-signature", "a.bed"], {}),
    ("starch-header", "starch", ["--header", "h.bed"], {}),
    ("starch-crlf", "starch", ["crlf.bed"], {}),
    ("starch-unsorted", "starch", ["u.bed"], {}),
    ("starch-empty", "starch", ["empty.bed"], {}),
    ("starch-missing", "starch", ["nosuch.bed"], {}),
    ("starch-big", "starch", ["big.bed"], {"setup": {"big.bed": b"".join(
        b"chr%d\t%d\t%d\tid%d\t%d\n" % (c, i * 37, i * 37 + 50 + i % 13, i, i % 7)
        for c in (1, 2, 11) for i in range(20000))}}),
    # unstarch (on archives from this build and from an upstream build)
    ("unstarch", "unstarch", ["a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-gzip", "unstarch", ["a.starch"], {"pre": [starch_of("a.bed", "--gzip")]}),
    ("unstarch-chrom", "unstarch", ["chr1", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-stats", "unstarch", ["--elements", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-bases", "unstarch", ["--bases", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-bases-uniq", "unstarch", ["--bases-uniq", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-list-chr", "unstarch", ["--list-chromosomes", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-has-nested", "unstarch", ["--has-nested", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-has-duplicate", "unstarch", ["--has-duplicate", "u.starch"],
     {"pre": [("sort-bed", ["u.bed"], "us.bed"), ("starch", ["us.bed"], "u.starch")]}),
    ("unstarch-note", "unstarch", ["--note", "a.starch"], {"pre": [starch_of("a.bed", "--note=hello there")]}),
    ("unstarch-signature", "unstarch", ["--signature", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-verify", "unstarch", ["--verify-signature", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-archive-version", "unstarch", ["--archive-version", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-archive-type", "unstarch", ["--archive-type", "a.starch"], {"pre": [starch_of("a.bed", "--gzip")]}),
    ("unstarch-is-starch", "unstarch", ["--is-starch", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-is-starch-bed", "unstarch", ["--is-starch", "a.bed"], {}),
    ("unstarch-list", "unstarch", ["--list", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("unstarch-big", "unstarch", ["--elements", "big.starch"], {"setup": {"big.bed": b"".join(
        b"chr1\t%d\t%d\n" % (i * 10, i * 10 + 5) for i in range(200000))}, "pre": [starch_of("big.bed")]}),
    ("unstarch-upstream", "unstarch", [SIG1], {}),
    ("unstarch-upstream-list-json", "unstarch", ["--list-json", SIG1], {}),
    ("unstarch-upstream-verify", "unstarch", ["--verify-signature", SD + "002.unstarch.signature.001.test"], {}),
    ("unstarch-upstream-chrom", "unstarch", ["chr10", SIG1], {}),
    ("unstarch-corrupt", "unstarch", ["bad.starch"], {"setup": {"bad.starch": b"\xca\x5c\xad\xe5" + b"\0" * 64}}),
    ("unstarch-missing", "unstarch", ["nosuch.starch"], {}),
    ("unstarch-space-path", "unstarch", [SP + "/x y.starch"], {"setup": {"a b/x y.starch": SIG1}}),
    # starchcat (merging archives that share a chromosome goes through temporary files)
    ("starchcat-disjoint", "starchcat", [CAT1, CAT2], {}),
    ("starchcat-shared-chrom", "starchcat", ["a.starch", "b.starch"], {"pre": [starch_of("a.bed"), starch_of("b.bed")]}),
    ("starchcat-gzip-note", "starchcat", ["--gzip", "--note=merged", CAT1, CAT2], {}),
    ("starchcat-upstream-mixed", "starchcat", [SIG1, "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("starchcat-missing", "starchcat", ["nosuch.starch", CAT1], {}),
    # starchstrip
    ("starchstrip-include", "starchstrip", ["--include", "chr1,chrX", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("starchstrip-exclude", "starchstrip", ["--exclude", "chr1", "a.starch"], {"pre": [starch_of("a.bed")]}),
    ("starchstrip-upstream", "starchstrip", ["--include", "chr1,chr10", SIG1], {}),
    ("starchstrip-none-left", "starchstrip", ["--exclude", "chr1,chr2,chrX", "a.starch"], {"pre": [starch_of("a.bed")]}),
]


# ---------------------------------------------------------------- dump
def path_forms(path):
    """Spellings of a directory in output: as given and resolved, both
    separators, and the drive forms C:\\x, C:/x, c:/x, /c/x."""
    forms = set()
    for p in {path, os.path.abspath(path), os.path.realpath(path)}:
        for q in {p, p.replace("\\", "/"), p.replace("/", "\\")}:
            forms.add(q)
            m = re.match(r"^([A-Za-z]):[\\/](.*)$", q)
            if m:
                d, rest = m.group(1), m.group(2)
                for dd in {d.upper(), d.lower()}:
                    forms |= {dd + ":/" + rest.replace("\\", "/"), dd + ":\\" + rest.replace("/", "\\")}
                forms.add("/" + d.lower() + "/" + rest.replace("\\", "/"))
    return forms


# Text that differs on every run, masked at dump time (so no host name is
# stored): the Starch creation time and temporary-file tag (pid + host), the
# padding `unstarch --list` adds after that tag, and the metadata signature
# (the metadata holds the tag).
RUN_TEXT = [
    (rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}", b"<TIME>"),
    (rb"\.pid\d+\.[^\s\"\x00|]+", b".pid<PID>.<HOST>"),
    (rb"<HOST> +\|", b"<HOST> |"),
    (rb"(?m)^metadata\t[A-Za-z0-9+/=]+", b"metadata\t<SIGNATURE>"),
]


def norm(data, cwd):
    """Bytes with the directories replaced by <CWD>/<DATA> (UTF-8, and on
    Windows also the ANSI code page) and RUN_TEXT masked, decoded as latin-1
    (every byte kept)."""
    pairs = []
    for path, tag in ((cwd, b"<CWD>"), (DATA, b"<DATA>")):
        for f in path_forms(path):
            for enc in ("utf-8", "mbcs") if os.name == "nt" else ("utf-8",):
                try:
                    pairs.append((f.encode(enc, "strict"), tag))
                except (UnicodeEncodeError, LookupError):
                    pass
    for form, tag in sorted(set(pairs), key=lambda ft: -len(ft[0])):
        data = data.replace(form, tag)
    for pattern, repl in RUN_TEXT:
        data = re.sub(pattern, repl, data)
    return data.decode("latin-1")


STARCH_MAGIC = b"\xca\x5c\xad\xe5"


def content(raw, cwd):
    """(kind, bytes): a Starch archive becomes its unstarch output and metadata."""
    if raw[:4] != STARCH_MAGIC:
        return "plain", raw
    tmp = os.path.join(os.path.dirname(cwd), os.path.basename(cwd) + ".decode.starch")
    with open(tmp, "wb") as f:
        f.write(raw)
    try:
        body = subprocess.run([prog("unstarch"), tmp], capture_output=True)
        meta = subprocess.run([prog("unstarch"), "--list-json", tmp], capture_output=True)
    finally:
        os.remove(tmp)
    return "starch", (b"#unstarch exit %d\n" % body.returncode + body.stdout + body.stderr +
                      b"#--list-json exit %d\n" % meta.returncode + meta.stdout + meta.stderr)


def prog(name):
    path = os.path.join(BIN, name)
    return path + ".exe" if not os.path.exists(path) and os.path.exists(path + ".exe") else path


def subst(arg, cwd):
    return arg.replace(D, DATA).replace(C, cwd)


def snapshot(cwd):
    files = {}
    for root, _, fs in os.walk(cwd):
        for f in fs:
            full = os.path.join(root, f)
            files[os.path.relpath(full, cwd).replace(os.sep, "/")] = open(full, "rb").read()
    return files


def run(case, cwd):
    name, program, args, opt = case
    shutil.rmtree(cwd, ignore_errors=True)
    os.makedirs(cwd)
    for dst, src in list(INPUTS.items()) + list(opt.get("setup", {}).items()):
        dst = os.path.join(cwd, *dst.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(src if isinstance(src, bytes) else open(subst(src, cwd), "rb").read())
    pre = []
    for p, a, out in opt.get("pre", []):
        with open(os.path.join(cwd, out), "wb") as f:
            r = subprocess.run([prog(p)] + a, cwd=cwd, stdout=f, stderr=subprocess.PIPE)
        pre.append("%s exit %d %s" % (p, r.returncode, norm(r.stderr, cwd)))
    before = snapshot(cwd)
    env = dict(os.environ)
    for k, v in opt.get("env", {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = subst(v, cwd)
    stdin = opt.get("stdin")
    if stdin is None:
        kw = {"stdin": subprocess.DEVNULL}
    else:
        kw = {"input": stdin if isinstance(stdin, bytes) else open(os.path.join(DATA, *stdin.split("/")), "rb").read()}
    p = subprocess.run([prog(program)] + [subst(a, cwd) for a in args], cwd=cwd, capture_output=True, env=env, **kw)
    files = {}
    for rel, data in sorted(snapshot(cwd).items()):
        if before.get(rel) != data:
            kind, data = content(data, cwd)
            files[rel] = [kind, norm(data, cwd)]
    kind, out = content(p.stdout, cwd)
    return {"exit": p.returncode, "pre": pre, "stdout": [kind, norm(out, cwd)],
            "stderr": norm(p.stderr, cwd), "files": files}


# ---------------------------------------------------------------- cmp
# Text that differs by design and is replaced before comparing (both sides):
# the separator inside a path after <CWD>/<DATA> (Windows joins with \ itself).
def xnorm(text):
    return re.sub(r"<(CWD|DATA)>[^\t\r\n\"'<>()]*", lambda m: m.group(0).replace("\\", "/"), text)


# Known differences between the Windows and the macOS build: case -> reason.
EXPECTED_XPLAT = {
    "sort-nonascii-path": "Windows passes arguments in the ANSI code page unless the .exe embeds a UTF-8"
                          " manifest (activeCodePage); a plain build has none, the ngs-tools payload does",
    "bedops-nonascii-path": "same as sort-nonascii-path",
    "unstarch-corrupt": "same error and exit status; after the failed seek on the too-short file the C"
                        " libraries leave the file position differently, so the byte count in the message differs",
    "starchcat-missing": "upstream reports this error with assert(): the C library words the assertion"
                         " message differently and abort() ends with another status (SIGABRT vs 0xC0000409)",
}


def show(text):
    """Lines with CR and other control bytes made visible."""
    return [repr(l)[1:-1] for l in text.split("\n")]


def diff(a, b, label):
    d = list(difflib.unified_diff(show(a), show(b), "A", "B", lineterm="", n=1))
    return [f"    {label}:"] + ["      " + x for x in d[:20]] + (["      ..."] if len(d) > 20 else [])


def compare(a, b):
    problems = []
    if a["exit"] != b["exit"]:
        problems.append(f"    exit: {a['exit']} vs {b['exit']}")
    if a["pre"] != b["pre"]:
        problems.append(f"    pre-steps: {a['pre']} vs {b['pre']}")
    streams = [("stdout", a["stdout"], b["stdout"]), ("stderr", ["plain", a["stderr"]], ["plain", b["stderr"]])]
    streams += [(f"file {f}", a["files"].get(f), b["files"].get(f)) for f in sorted(set(a["files"]) | set(b["files"]))]
    for label, x, y in streams:
        if x is None or y is None:
            problems.append(f"    {label}: only in {'B' if x is None else 'A'}")
            continue
        if x[0] != y[0]:
            problems.append(f"    {label}: kind {x[0]} vs {y[0]}")
        tx, ty = xnorm(x[1]), xnorm(y[1])
        if tx != ty:
            problems += diff(tx, ty, label)
    return problems


def main():
    global BIN, DATA
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "dump" and len(sys.argv) in (6, 7):
        BIN, DATA, work = (os.path.abspath(p) for p in sys.argv[2:5])
        only = sys.argv[6] if len(sys.argv) > 6 else ""
        out = {}
        for case in CASES:
            if only in case[0]:
                out[case[0]] = run(case, os.path.join(work, case[0]))
                print("ran", case[0], "exit", out[case[0]]["exit"], flush=True)
        with open(sys.argv[5], "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, ensure_ascii=True)
        print(len(out), "case(s) written to", sys.argv[5])
        return
    if mode != "cmp" or len(sys.argv) != 4:
        sys.exit(__doc__)
    a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[2:4])
    counts = {"SAME": 0, "EXPECTED-DIFF": 0, "DIFF": 0}
    for name in a:
        if name not in b:
            print(f"MISSING  {name} (only in A)")
            continue
        problems = compare(a[name], b[name])
        status = "SAME" if not problems else ("EXPECTED-DIFF" if name in EXPECTED_XPLAT else "DIFF")
        counts[status] += 1
        print(f"{status}  {name}" + (f"  ({EXPECTED_XPLAT[name]})" if status == "EXPECTED-DIFF" else ""))
        if status == "DIFF":
            print("\n".join(problems))
    for name in b:
        if name not in a:
            print(f"MISSING  {name} (only in B)")
    print(f"\n{counts['SAME']} same, {counts['EXPECTED-DIFF']} expected, {counts['DIFF']} different")
    sys.exit(1 if counts["DIFF"] else 0)


if __name__ == "__main__":
    main()
