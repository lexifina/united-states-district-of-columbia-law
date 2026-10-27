#!/usr/bin/env python3
"""Read the D.C. Code history by date. Needs Python 3.8 or later and git; run it inside the repository.

  python tools/dc.py on 2024-01-01 title-1/1-1001.05.md          the text on a date
  python tools/dc.py diff 2022-01-01 2025-01-01 title-1/1-1001.05.md [--words]
  python tools/dc.py log title-1/1-1001.05.md                    every change to a section, with its dates
  python tools/dc.py law "D.C. Law 25-217"                       every change one law made

A commit's date is its In-force: trailer (the day the law took effect) or, where the law's effective date is not known
or falls outside the time between two publications, its Published: trailer (the day the DC Council published the
text). The first commit is the code as published on 2021-10-18. The text on a date is the file in the last commit dated
on or before it, so the answer does not depend on your time zone or the time of day.
"""
import re
import subprocess
import sys


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def history():
    fmt = ("%H%x1f%ad%x1f%an%x1f%s%x1f%(trailers:key=In-force,valueonly,separator=%x2c)%x1f"
           "%(trailers:key=Published,valueonly,separator=%x2c)%x1f%(trailers:key=Consolidated,valueonly,separator=%x2c)%x1e")
    out = []
    for rec in git("log", "--reverse", "--date=short", "--format=" + fmt, "HEAD").split("\x1e"):
        rec = rec.strip("\n")
        if rec:
            commit, authored, author, subject, in_force, published, consolidated = rec.split("\x1f")
            when = next((x.strip().split(",")[0] for x in (in_force, published, consolidated) if x.strip()), authored)
            out.append((when, commit, author, subject))
    return out


def day(text):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        sys.exit("Dates are written YYYY-MM-DD, not %r." % text)
    return text


def commit_on(date):
    hist = history()
    chosen = [h for h in hist if h[0] <= date]
    if not chosen:
        sys.exit("%s is before this history starts (%s)." % (date, hist[0][0]))
    return chosen[-1]


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):   # the text is UTF-8 ("§"), whatever the console's code page
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd == "on" and len(argv) == 4:
        try:
            sys.stdout.write(git("show", "%s:%s" % (commit_on(day(argv[2]))[1], argv[3])))
            return 0
        except subprocess.CalledProcessError:
            print("%s was not in the D.C. Code on %s." % (argv[3], argv[2]))
            return 1
    if cmd == "log" and len(argv) == 3:
        dates = {h[1]: h[0] for h in history()}
        for line in git("log", "--reverse", "--format=%H%x1f%an%x1f%s", "--", argv[2]).splitlines():
            commit, author, subject = line.split("\x1f")
            print("%s  %s  %s\n            %s" % (dates.get(commit, "?"), commit[:10], author, subject))
        return 0
    if cmd == "diff" and len(argv) in (5, 6):
        a, b = commit_on(day(argv[2]))[1], commit_on(day(argv[3]))[1]
        sys.stdout.write(git("diff", *(["--word-diff"] if argv[-1] == "--words" else []), a, b, "--", argv[4]))
        return 0
    if cmd == "law" and len(argv) == 3:
        sys.stdout.write(git("log", "--stat", "--format=%n%ad  %s", "--date=short", "--author=^" + re.escape(argv[2]) + "[ <]"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
