#!/usr/bin/env python3
"""
logscan.py - stream-based log analysis helper.

Never loads a whole file into memory: every source (plain file, .gz, .zip/.tar
member) is read line by line. Multi-line entries (stack traces, XML bodies) are
glued to the timestamped line that started them, so a match on any line of an
entry returns the whole entry.

Subcommands
  inventory  PATH...                 list log sources, sizes, first/last timestamp
  vocab      PATH... [--filter RE] [--level L] [--since/--until TS]
                                     most common loggers / message templates (to learn the log's vocabulary)
  grep       PATH... -e RE [-e RE]   entries matching ALL -e patterns (use --any for OR)
             [--exclude RE] [--since TS] [--until TS] [-i]
             [--extract RE] [--format text|csv|json] [--count] [--max N]
             [--max-chars N] [--first-line]

PATH may be a directory (recursed), a file, a .gz, a .zip, or a .tar(.gz).
"""
import argparse, collections, csv, gzip, io, json, os, re, sys, tarfile, zipfile

TS_RE = re.compile(
    r"^\s*\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)"   # 2026-01-02 10:11:12,345
    r"|^\s*\[?(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})"                 # 02/Jan/2026:10:11:12
    r"|^\s*(\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2})"                       # Jan  2 10:11:12 (syslog)
)
LOG_EXT = (".log", ".txt", ".out", ".err", ".json", ".jsonl", ".csv")


# ---------------------------------------------------------------- sources
def _text(binary):
    return io.TextIOWrapper(binary, encoding="utf-8", errors="replace", newline="")


def iter_sources(paths):
    """Yield (name, size_bytes, opener) for every log stream under paths."""
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    yield from iter_sources([os.path.join(root, f)])
            continue
        low = p.lower()
        if zipfile.is_zipfile(p) and low.endswith(".zip"):
            zf = zipfile.ZipFile(p)
            for info in sorted(zf.infolist(), key=lambda i: i.filename):
                if info.is_dir():
                    continue
                n = info.filename.lower()
                if n.endswith(".gz"):
                    yield (f"{p}!{info.filename}", info.file_size,
                           lambda zf=zf, i=info: _text(gzip.GzipFile(fileobj=zf.open(i))))
                else:
                    yield (f"{p}!{info.filename}", info.file_size,
                           lambda zf=zf, i=info: _text(zf.open(i)))
        elif low.endswith((".tar", ".tar.gz", ".tgz")):
            tf = tarfile.open(p)
            for m in tf.getmembers():
                if m.isfile():
                    yield (f"{p}!{m.name}", m.size,
                           lambda tf=tf, m=m: _text(tf.extractfile(m)))
        elif low.endswith(".gz"):
            yield (p, os.path.getsize(p), lambda p=p: _text(gzip.open(p, "rb")))
        else:
            yield (p, os.path.getsize(p), lambda p=p: open(p, "r", encoding="utf-8", errors="replace", newline=""))


def ts_of(line):
    m = TS_RE.match(line)
    if not m:
        return None
    return next(g for g in m.groups() if g).replace("T", " ")


def iter_entries(opener):
    """Yield (line_no, timestamp, entry_text). Continuation lines join the previous entry."""
    buf, start, ts = [], 0, None
    with opener() as fh:
        for n, line in enumerate(fh, 1):
            line = line.rstrip("\r\n")
            t = ts_of(line)
            if t is not None or not buf:
                if buf:
                    yield start, ts, "\n".join(buf)
                buf, start, ts = [line], n, t
            else:
                buf.append(line)
                if len(buf) > 5000:            # runaway entry guard
                    yield start, ts, "\n".join(buf)
                    buf, start = [], n + 1
        if buf:
            yield start, ts, "\n".join(buf)


# ---------------------------------------------------------------- commands
def cmd_inventory(a):
    total, count = 0, 0
    w = csv.writer(sys.stdout)
    w.writerow(["source", "bytes", "first_ts", "last_ts"])
    for name, size, op in iter_sources(a.paths):
        first = last = None
        with op() as fh:
            for line in fh:
                t = ts_of(line)
                if t:
                    first = first or t
                    last = t
        w.writerow([name, size, first, last])
        total += size; count += 1
    print(f"# {count} sources, {total/1e6:.1f} MB total", file=sys.stderr)


NORMALIZERS = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<uuid>"),
    (re.compile(r"'[^']*'"), "'<s>'"),
    (re.compile(r"\b\d[\d.,:-]*\b"), "<n>"),
]


def template(msg):
    for rx, rep in NORMALIZERS:
        msg = rx.sub(rep, msg)
    return msg[:160]


def cmd_vocab(a):
    flt = re.compile(a.filter, re.I) if a.filter else None
    lvl = a.level.upper() if a.level else None
    templates = collections.Counter()
    levels = collections.Counter()
    for name, _, op in iter_sources(a.paths):
        for _, ts, entry in iter_entries(op):
            first = entry.split("\n", 1)[0]
            if flt and not flt.search(entry):
                continue
            if a.since and ts and ts < a.since:
                continue
            if a.until and ts and ts > a.until:
                continue
            body = first[len(ts):] if ts and first.startswith(ts) else first
            parts = body.split()
            if parts and parts[0].isupper():
                levels[parts[0]] += 1
            if lvl and (not parts or parts[0] != lvl):
                continue
            templates[template(body.strip())] += 1
    print("== levels ==")
    for k, v in levels.most_common():
        print(f"{v:>9}  {k}")
    print(f"== top {a.top} message templates ==")
    for k, v in templates.most_common(a.top):
        print(f"{v:>9}  {k}")


def cmd_grep(a):
    flags = re.I if a.ignore_case else 0
    pats = [re.compile(p, flags) for p in a.expr]
    excl = [re.compile(p, flags) for p in (a.exclude or [])]
    extract = re.compile(a.extract, flags) if a.extract else None
    hits, out_rows = 0, []
    writer = csv.writer(sys.stdout) if a.format == "csv" else None
    header_done = False

    for name, _, op in iter_sources(a.paths):
        for line_no, ts, entry in iter_entries(op):
            if a.since and ts and ts < a.since:
                continue
            if a.until and ts and ts > a.until:
                continue
            test = [p.search(entry) for p in pats]
            if not (any(test) if a.any else all(test)):
                continue
            if any(x.search(entry) for x in excl):
                continue
            hits += 1
            if a.count:
                continue
            text = entry.split("\n", 1)[0] if a.first_line else entry
            if a.max_chars and len(text) > a.max_chars:
                text = text[: a.max_chars] + " …[truncated]"
            row = {"source": os.path.basename(name), "line": line_no, "ts": ts}
            if extract:
                m = extract.search(entry)
                if not m:
                    continue
                row.update(m.groupdict() or {f"g{i}": g for i, g in enumerate(m.groups(), 1)})
            else:
                row["entry"] = text
            if a.format == "json":
                out_rows.append(row)
            elif a.format == "csv":
                if not header_done:
                    writer.writerow(row.keys()); header_done = True
                writer.writerow(row.values())
            else:
                print(f"--- {row['source']}:{line_no}")
                print(text if not extract else "  ".join(f"{k}={v}" for k, v in row.items() if k not in ("source", "line")))
            if a.max and hits >= a.max:
                break
        if a.max and hits >= a.max:
            print(f"# stopped at --max {a.max}", file=sys.stderr)
            break
    if a.format == "json":
        json.dump(out_rows, sys.stdout, indent=1, default=str)
        print()
    print(f"# {hits} matching entries", file=sys.stderr if not a.count else sys.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("inventory"); s.add_argument("paths", nargs="+"); s.set_defaults(fn=cmd_inventory)

    s = sub.add_parser("vocab"); s.add_argument("paths", nargs="+")
    s.add_argument("--filter", help="only entries matching this regex (case-insensitive)")
    s.add_argument("--level", help="only this log level, e.g. ERROR")
    s.add_argument("--since"); s.add_argument("--until")
    s.add_argument("--top", type=int, default=40); s.set_defaults(fn=cmd_vocab)

    s = sub.add_parser("grep"); s.add_argument("paths", nargs="+")
    s.add_argument("-e", "--expr", action="append", required=True, help="regex; repeat for AND")
    s.add_argument("--any", action="store_true", help="OR the -e patterns instead of AND")
    s.add_argument("--exclude", action="append", help="drop entries matching this regex")
    s.add_argument("-i", "--ignore-case", action="store_true")
    s.add_argument("--since", help="'YYYY-MM-DD[ HH:MM:SS]' inclusive (string compare)")
    s.add_argument("--until", help="'YYYY-MM-DD[ HH:MM:SS]' inclusive (string compare)")
    s.add_argument("--extract", help="regex with (?P<name>...) groups -> structured fields")
    s.add_argument("--format", choices=["text", "csv", "json"], default="text")
    s.add_argument("--count", action="store_true", help="only print number of matches")
    s.add_argument("--max", type=int, help="stop after N matches")
    s.add_argument("--max-chars", type=int, default=2000, help="truncate printed entries (0 = never)")
    s.add_argument("--first-line", action="store_true", help="print only the first line of each entry")
    s.set_defaults(fn=cmd_grep)

    a = ap.parse_args()
    if getattr(a, "until", None) and len(a.until) == 10:
        a.until += " 99"                       # make a bare date inclusive of the whole day
    a.fn(a)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
