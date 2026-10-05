---
name: log-analyzer
description: Answer questions about application/server log files - find specific events, trace a customer, invoice, order, request or ID through the logs, count or list occurrences, find errors and their causes, or reconstruct what happened in a time window. Works on loose .log/.txt files, folders, and .zip/.gz/.tar archives of logs, streaming the content so large files (10 MB to multiple GB) never get loaded into memory. Use this skill whenever the user uploads or points at log files or a log archive and asks anything about them ("find all X that...", "which invoices were matched", "why did Y fail", "how often does Z happen", "what happened to order 123"), even if they don't say "analyse logs".
---

# Log analyzer

Answer the user's question about a set of log files with evidence, without loading
big files into memory.

The core difficulty with logs is not searching, it's **knowing what to search for**.
The user describes things in business terms ("invoices matched with a journal entry");
the logs use the developer's terms (`Matched invoiceRef='…' with payment entry …`).
So the workflow is: inventory → learn the vocabulary → targeted search → verify → report.

## Tool: `scripts/logscan.py`

A streaming helper (stdlib-only Python). It reads plain files, folders, `.gz`, and members
of `.zip` / `.tar(.gz)` archives line by line, **without extracting them**, and glues
multi-line entries (stack traces, XML/JSON bodies) to the timestamped line that started
them, so a match anywhere in a stack trace returns the whole entry.

```bash
S=<skill-dir>/scripts/logscan.py
python3 $S inventory <paths>                   # sources, bytes, first/last timestamp (CSV)
python3 $S vocab <paths> --filter 'acme' [--level ERROR] [--since …] [--until …] --top 40
                                               # common message templates, numbers/ids normalised
python3 $S grep <paths> -e 'RE1' -e 'RE2'      # entries matching ALL patterns (--any = OR)
    [-i] [--exclude RE] [--since '2026-09-01'] [--until '2026-09-30 12:00']
    [--first-line] [--max-chars 400] [--max 50] [--count]
    [--extract '(?P<invoice>…)…(?P<entry>\d+)' --format csv|json]
```

Notes:
- Patterns are Python regexes applied to the whole (multi-line) entry. Use `-i` for
  case-insensitive search (customer names are often cased inconsistently, e.g. `Vallei53`).
- Always cap output while exploring (`--max`, `--first-line`, `--max-chars`). One entry can be
  a 50 KB JSON payload; dumping thousands of them floods the context.
- `--extract` turns each matching entry into a row of named fields. This is the best way to
  produce the final list once you know the right line.
- Plain `grep -c` / `zgrep` / `unzip -p … | grep` are fine for quick counts too; they also
  stream. Prefer logscan when entries span multiple lines or you need structured output.
- Never `cat` whole files or `read()` them in Python. If you write ad-hoc Python, iterate
  `for line in fh`.

## Workflow

### 1. Inventory
Run `inventory` (or `unzip -l` / `ls -laS` for a quick look). Note the number of files, total
size, biggest file, date range, and whether there are rotated parts (`.0.log`, `.1.log`), which
all belong to the same day. Mention this scope in the answer ("searched 280 files, Jan 1–Oct 5").
Don't extract archives to disk unless a tool truly needs it; logscan reads them in place.

### 2. Learn the vocabulary
Before writing the "real" search, find out how the concepts in the question appear in the logs:
- `vocab --filter '<entity>'` shows the message types that mention the customer/ID.
- Grep for each business word **and its likely synonyms/translations** with `--count`
  first, then look at a handful of examples (`--max 5 --max-chars 600`). For example,
  "matched" could be `matched`, `MatchSet`, `reconciled`, `afgeletterd` (Dutch), `paired`.
- Read a few complete entries around one example to understand the flow: what is logged
  before (request received), during (resolve, upload), and after (success line, API response).
  `grep -n` plus `sed -n 'A,Bp'` on one file (or `unzip -p archive file | sed -n …`) is a
  good way to view a window of lines.

For "what errors / what went wrong" questions, `vocab --filter <entity> --level ERROR`
(plus WARN) groups the errors by message type in one pass. Then grep one example of each
top type to read its stack trace or payload and explain the cause in plain words.

### 3. Pick the line that proves the outcome
Choose the log line that means the event **actually happened**, not that it was attempted.
Common traps, worth checking explicitly:
- **Dry runs / test mode**: lines like "Would create…", "[test mode]", `testMode=true`.
- **Attempts vs. outcomes**: "Uploading…", "Sending…", "Retrying…" are not success.
- **Flags in payloads**: `matched=false` inside an object is a state, not an event.
- **Duplicates/retries**: the same ID can be processed several times; also look for
  "already matched/processed" lines and dedupe by the business key.
- **Different client/sub-account names** for the same customer (`X_main`, `X_kiosk`,
  `X_mainSlave01`). Match on the shared part and report which variants appear.

If a downstream response confirms success (HTTP status, API XML/JSON message), check that too,
e.g. count responses with a non-success status among the relevant entries.

### 4. Extract the answer
Use `grep … --extract … --format csv` (or json) to get one row per event with the fields the
user cares about (timestamp, ID, amounts, related entries, source file:line). Dedupe on the
business key. If the result is large (>~50 rows), save it as a CSV in
`/mnt/user-data/outputs/` (or the working dir in non-chat environments) and summarise in the reply.

### 5. Report
Lead with the direct answer (count + list/table), then briefly:
- **How it was identified**: the exact log message used as evidence, with one sample line.
- **Scope**: files/date range searched.
- **Caveats and near-misses**: excluded dry runs, skipped/duplicate events, failures,
  gaps in the date range, anything ambiguous. Give counts.
- Offer a natural follow-up only if useful (e.g. "want the 46 test-mode runs too?").

Keep it concise. Quote log lines trimmed to the relevant part; don't paste huge payloads.
If the question can't be answered from the logs (concept not logged, date range missing),
say so plainly and show what you searched for.

## Example

Question: "Find all vallei53 invoices that were matched with a journal entry" on a zip of
280 Java service logs (244 MB).

1. `inventory` → 280 files, 2026-01-01 … 2026-10-05, largest 10.7 MB.
2. `grep -i -e vallei53 -e match --count`, then sample → finds `CreateJournalEntry` lines:
   `Resolved invoiceRef=… matched=false` (state), `[invoiceRef test mode] Would create journal
   entry … then match` (dry run), `MatchSetService Uploading MatchSet` (attempt),
   `MatchSets upload response … Afgeletterd` (Exact confirmation),
   `Matched invoiceRef='1-5068-7292' (entry 267061279) with payment entry 26903590` (outcome).
3. Evidence line = `Matched invoiceRef=…`; all MatchSet responses are success (type 2).
4. Extract:
   ```bash
   python3 $S grep archived.zip -i -e vallei53 -e "Matched invoiceRef" --format csv --extract \
     "\[(?P<client>[^\]]+)\] Matched invoiceRef='(?P<invoice>[^']+)' \(entry (?P<invoice_entry>\d+)\) with payment entry (?P<payment_entry>\d+)"
   ```
5. Report: 15 invoices (25 Sep – 4 Oct), table of invoice / Exact entry / payment entry / date /
   client; caveats: 46 test-mode dry runs excluded, 2 "already matched" skips, no failed uploads.
