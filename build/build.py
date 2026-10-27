"""Builds a git history of the Code of the District of Columbia from the DC Council's own dated publications.

    python scripts/state-law/dc/build.py fetch            # robots.txt, repo metadata, and two git clones (cached)
    python scripts/state-law/dc/build.py repo <out>       # write the history with git fast-import
    python scripts/state-law/dc/build.py check [N]        # word-for-word render check on N publications (default 2)

Sources (robots.txt checked 2026-10-28; code.dccouncil.gov is NOT used, its robots.txt disallows ClaudeBot):
- github.com/DCCouncil/law-xml-codified: "the code fully supplemented". Its publication branches carry one commit per
  publication date ("2021-10-18/2021-10-18" ... "2026-10-27/2026-10-27"); each commit is the whole code as published
  that day. The newest branch's first-parent history is the publisher's own list of publications.
- github.com/DCCouncil/law-xml: the laws and acts themselves, read only for each law's short title, effective date and
  District of Columbia Register citation.

Each publication is a snapshot. Between two publications, every section whose rendered text or source note changed is
matched with the laws its History notes gained. A law whose effective date falls between the two publications dates
the commit; otherwise the commit is dated by the publication and says so. A change whose notes name no new law is a
commit of the publication. Standard library only. The repo step reads only the cached clones and is deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CODIFIED = CACHE / "law-xml-codified.git"
LAWS = CACHE / "law-xml.git"
AGENT = "Mozilla/5.0 (compatible; Lexifina state law history; +https://lexifina.com/watch)"
GIT_AGENT = "git/2 (Lexifina state law history; +https://lexifina.com/watch)"
GH = "https://github.com/DCCouncil"
COMMITTER = ("Lexifina", "state-law@lexifina.com")
TITLES = "us/dc/council/code/titles"

NS = "{https://code.dccouncil.us/schemas/dc-library}"
FOREIGN = ("{https://code.dccouncil.us/schemas/codify}", "{https://code.dccouncil.us/schemas/codified}")

READ: dict[str, str] = {}   # name -> sha256 of what was read, for DATA-SHA256SUMS

# ---- Fetching (a handful of requests: robots.txt, repository metadata, and two git clones) ----

URLS = [
    "https://github.com/robots.txt",
    "https://api.github.com/robots.txt",
    "https://api.github.com/repos/DCCouncil/law-xml",
    "https://api.github.com/repos/DCCouncil/law-xml-codified",
    "https://api.github.com/repos/DCCouncil/law-html",
    "https://api.github.com/repos/DCCouncil/law-html/readme",
    "https://api.github.com/repos/DCCouncil/law-xml-codified/readme",
]


def cached_name(url: str) -> Path:
    return CACHE / "http" / re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[1])


def get(url: str) -> bytes:
    """The response body from the cache, or fetched once (one request at a time, 1.5 s apart)."""
    file = cached_name(url)
    if file.exists():
        data = file.read_bytes()
        READ[url] = hashlib.sha256(data).hexdigest()
        return data
    file.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(6):
        time.sleep(1.5)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as error:
            if error.code == 404:
                data = error.read() or b""
                break
            if error.code == 429 or error.code >= 500:
                time.sleep(float(error.headers.get("Retry-After") or 30 * (attempt + 1)))
                continue
            raise
    else:
        raise RuntimeError(f"could not fetch {url}")
    file.write_bytes(data)
    READ[url] = hashlib.sha256(data).hexdigest()
    return data


def log(msg: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / "fetch.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat(timespec='seconds')}Z {msg}\n")
    print(msg, flush=True)


def cmd_fetch(args: argparse.Namespace) -> None:
    for url in URLS:
        get(url)
        log(f"have {url}")
    # The repository URLs without ".git": github.com's robots.txt disallows paths ending in ".git" for ClaudeBot.
    for repo, name in ((CODIFIED, "law-xml-codified"), (LAWS, "law-xml")):
        if repo.exists():
            log(f"have {repo.name} (not fetched again)")
            continue
        log(f"git clone --mirror {GH}/{name}")
        subprocess.run(["git", "-c", f"http.userAgent={GIT_AGENT}", "clone", "--mirror", f"{GH}/{name}", str(repo)], check=True)
        time.sleep(1.5)
    log("fetched")


# ---- Reading the clones ----

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, encoding="utf-8").stdout


class Blobs:
    """Reads blobs (or rev:path) through one `git cat-file --batch` process."""

    def __init__(self, repo: Path):
        self.p = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, spec: str) -> bytes | None:
        self.p.stdin.write((spec + "\n").encode()); self.p.stdin.flush()
        head = self.p.stdout.readline().split()
        if len(head) < 3 or head[1] == b"missing":
            return None
        data = self.p.stdout.read(int(head[2])); self.p.stdout.read(1)
        return data


def newest_ref() -> str:
    """The newest publication branch: the latest base, then the latest date."""
    refs = git(CODIFIED, "for-each-ref", "--format=%(refname:short)", "refs/heads/publication").split()
    return max(refs, key=lambda r: tuple(r.split("/", 1)[1].split(".")))


def publications(ref: str) -> list[tuple[str, str]]:
    """(date, commit) for each publication on the branch's first-parent line, oldest first; on a day with more than one,
    the last of the day."""
    out: dict[str, str] = {}
    for line in git(CODIFIED, "log", "--first-parent", "--reverse", "--format=%H %s", ref).splitlines():
        commit, subject = line.split(" ", 1)
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:-\d+)?/\S+", subject.strip())
        if m:
            out[m.group(1)] = commit
    return sorted(out.items())


# ---- Text ----

_WS = re.compile(r"\s+")
_MD = re.compile(r"([\\*_`<])")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
LAW_ID = re.compile(r"\b(D\.C\. (?:Law|Act) \d+-\d+[A-Za-z]?|Pub\. L\. \d+-\d+)")
BLOCK = {"text", "aftertext", "table", "p", "para", "container", "include", "section", "h1", "h2", "h3", "center"}
SKIP = {"annotations", "annotation", "marginalia", "reason", "TODO"}


def local(e: ET.Element) -> str:
    return e.tag[len(NS):] if isinstance(e.tag, str) and e.tag.startswith(NS) else ""


def foreign(e: ET.Element) -> bool:
    """Codification instructions (codify:/codified: elements) and comments are not text of the code."""
    return not isinstance(e.tag, str) or e.tag.startswith(FOREIGN)


def clean(t: str) -> str:
    return _WS.sub(" ", t).strip()


def esc(t: str) -> str:
    return _MD.sub(r"\\\1", t)


def table_rows(t: ET.Element) -> list[str]:
    """A table's own caption and rows (thead/tbody/tfoot/tr children only, never nested tables twice), one line per
    row with cells joined by " | "."""
    rows: list[str] = []
    for c in t:
        n = local(c)
        if n == "caption":
            rows.extend(inline_lines(c))
        elif n in ("thead", "tbody", "tfoot"):
            for r in c:
                if local(r) == "tr":
                    rows.append(row(r))
        elif n == "tr":
            rows.append(row(c))
        elif not foreign(c):   # a stray th/td or text straight inside the table
            rows.append(" ".join(inline_lines(c)))
    return [r for r in rows if r]


def row(tr: ET.Element) -> str:
    return " | ".join(" ".join(inline_lines(c)) for c in tr if local(c) in ("td", "th"))


def inline_lines(e: ET.Element) -> list[str]:
    """The lines of a text-like element: its inline content, broken at block children (nested text, tables)."""
    lines: list[str] = []
    cur: list[str] = [e.text or ""]

    def flush() -> None:
        t = clean("".join(cur))
        if t:
            lines.append(t)
        cur.clear()

    def walk_inline(x: ET.Element) -> None:
        for c in x:
            if foreign(c) or local(c) in SKIP:
                cur.append(c.tail or "")
                continue
            n = local(c)
            if n == "table":
                flush(); lines.extend(table_rows(c))
            elif n in BLOCK:
                flush(); lines.extend(inline_lines(c))
            elif n == "br":
                cur.append(" ")
            elif n == "img":
                cur.append(f" [Image: {c.get('src', '')}] ")
            else:
                cur.append(c.text or ""); walk_inline(c)
            cur.append(c.tail or "")

    walk_inline(e)
    flush()
    return lines


def body(e: ET.Element, depth: int, out: list[str], top: bool = False) -> None:
    """The lines of a section, para, container or include: designated provisions as list items indented by depth.
    `top`: e is a section whose prefix, number and heading are shown in its heading line, not in the body."""
    for c in e:
        if foreign(c):
            continue
        n = local(c)
        if n in SKIP or (top and n in ("prefix", "num", "heading")):
            continue
        if n in ("para", "container"):
            provision(c, depth, out)
        elif n == "include":
            body(c, depth, out)
        elif n == "table":
            out.extend("  " * depth + esc(r) for r in table_rows(c))
        elif n == "section":   # a whole section quoted inside another
            label = " ".join(clean("".join(x.itertext())) for x in c
                             if local(x) in ("prefix", "heading") or (local(x) == "num" and x.get("undesignated") != "true"))
            if label.strip():
                out.append("  " * depth + esc(label.strip()))
            body(c, depth, out, top=True)
        else:
            out.extend("  " * depth + esc(t) for t in inline_lines(c))


def provision(p: ET.Element, depth: int, out: list[str]) -> None:
    lead: list[str] = []
    rest = list(p)
    while rest and (foreign(rest[0]) or local(rest[0]) in ("prefix", "num", "heading") or local(rest[0]) in SKIP):
        c = rest.pop(0)
        n = local(c)
        if n in ("prefix", "heading") or (n == "num" and c.get("undesignated") != "true"):
            t = clean("".join(c.itertext()))
            if t:
                lead.append(t)
    first: list[str] = []
    if rest and local(rest[0]) == "text":
        first = inline_lines(rest.pop(0))
    head = " ".join(lead + first[:1])
    out.append("  " * depth + "- " + esc(head) if head else "  " * depth + "-")
    out.extend("  " * (depth + 1) + esc(t) for t in first[1:])
    holder = ET.Element(p.tag)
    holder.extend(rest)
    body(holder, depth + 1, out)


def fmt_day(day: str) -> str:
    y, m, d = (int(x) for x in day.split("-"))
    return f"{MON[m - 1]} {d}, {y}"


def fmt_path(path: str) -> str:
    if not path:
        return ""
    parts = path.split("|")
    s = parts[0].replace("§", "§ ") + "".join(parts[1:])
    return s.strip()


def parse_day(text: str) -> str:
    """The first date in a history note ("Dec. 16, 1975, D.C. Law 1-37" -> 1975-12-16), or ""."""
    m = re.search(r"\b([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),\s*(\d{4})", text)
    if not m or m.group(1)[:3].lower() not in MONTHS:
        return ""
    try:
        return datetime(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2))).date().isoformat()
    except ValueError:
        return ""


class Laws:
    """Short title, effective date and Register citation of each D.C. Law and Act, from law-xml."""

    def __init__(self, ref: str = "main"):
        self.ref = ref
        self.blobs = Blobs(LAWS)
        self.memo: dict[str, dict] = {}
        self.commit = git(LAWS, "rev-parse", ref).strip()

    def get(self, law: str) -> dict:
        if law in self.memo:
            return self.memo[law]
        info: dict = {}
        m = re.fullmatch(r"D\.C\. (Law|Act) (\d+)-(\d+[A-Za-z]?)", law)
        if m:
            path = f"us/dc/council/periods/{m.group(2)}/{m.group(1).lower()}s/{m.group(2)}-{m.group(3)}.xml"
            data = self.blobs.read(f"{self.commit}:{path}")
            if data:
                READ[f"{GH}/law-xml/blob/{self.commit}/{path}"] = hashlib.sha256(data).hexdigest()
                try:
                    root = ET.fromstring(data)
                except ET.ParseError:
                    root = None
                if root is not None:
                    for h in root.findall(NS + "heading"):
                        if h.get("type") == "short":
                            info["title"] = clean("".join(h.itertext()))
                    eff = root.find(f"{NS}meta/{NS}effective")
                    if eff is not None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", (eff.text or "").strip()):
                        info["effective"] = eff.text.strip()
                    for c in root.iterfind(f"{NS}meta/{NS}citations/{NS}citation"):
                        if c.get("type") == "register":
                            info["register"] = clean(c.text or "")
        self.memo[law] = info
        return info


Section = dict   # {"text": rendered markdown, "history": {law: eff}, "other": {law: eff}, "repealed": bool}


def history_lines(anns: list[ET.Element], laws: Laws) -> list[str]:
    """The source note: every History annotation, in order; consecutive structured notes of one law make one line."""
    entries: list = []   # a prose note (str), or [head, [paths], register] for structured notes of one law
    last_key = None
    for a in anns:
        if a.get("type") != "History" or a.get("display") == "false":
            continue
        text = clean("".join(a.itertext()))
        if text:
            entries.append(text); last_key = None
            continue
        doc, eff = a.get("doc", ""), a.get("eff", "")
        path = fmt_path(a.get("path", ""))
        if (doc, eff) == last_key:
            if path and path not in entries[-1][1]:
                entries[-1][1].append(path)
            continue
        reg = laws.get(doc).get("register", "") if doc else ""
        head = ", ".join(x for x in (fmt_day(eff) if eff else "", doc) if x)
        entries.append([head, [path] if path else [], reg])
        last_key = (doc, eff)
    return [e if isinstance(e, str) else ", ".join(x for x in [e[0], ", ".join(e[1]), e[2]] if x) for e in entries]


def section(xml: bytes, laws: Laws) -> Section:
    root = ET.fromstring(xml)
    num = clean("".join(root.find(NS + "num").itertext())) if root.find(NS + "num") is not None else ""
    head_el = root.find(NS + "heading")
    heading = clean("".join(head_el.itertext())) if head_el is not None else ""
    lines = [f"# D.C. Code § {esc(num)}." + (f" {esc(heading)}" if heading else ""), ""]
    out: list[str] = []
    body(root, 0, out, top=True)
    lines += out
    anns = [a for a in root.findall(f"{NS}annotations/{NS}annotation")]
    notes = history_lines(anns, laws)
    if notes:
        lines += ["", "Source:"] + [f"- {esc(n)}" for n in notes]
    hist: dict[str, str] = {}
    other: dict[str, str] = {}
    entries: dict[tuple[str, str], str] = {}   # (law, section of the law) of each History note -> effective date
    for a in anns:
        t = a.get("type")
        if t not in ("History", "Emergency Legislation", "Temporary Legislation"):
            continue
        text = "".join(a.itertext())
        ids = [a.get("doc")] if a.get("doc") and LAW_ID.fullmatch(a.get("doc")) else LAW_ID.findall(text)
        for law in ids:
            eff = a.get("eff") or laws.get(law).get("effective") or (parse_day(text) if t == "History" else "")
            target = hist if t == "History" else other
            if law not in target or (eff and eff > target[law]):
                target[law] = eff
            if t == "History":
                entries[(law, a.get("path") or clean(text))] = eff
    reason = root.find(NS + "reason")
    return {"text": "\n".join(lines).rstrip() + "\n", "history": hist, "other": other, "entries": entries,
            "repealed": reason is not None and "repeal" in (reason.text or "").lower()}


def source_words(xml: bytes) -> list[str]:
    """Every word of a section's text nodes that the rendering must show, in document order (for the render check)."""
    root = ET.fromstring(xml)
    words: list[str] = []

    def walk(e: ET.Element, top: bool) -> None:
        for c in e:
            if (foreign(c) or local(c) in SKIP or (top and local(c) in ("prefix", "num", "heading"))
                    or (local(c) == "num" and c.get("undesignated") == "true")):
                words.extend((c.tail or "").split())
                continue
            words.extend((c.text or "").split())
            walk(c, False)
            words.extend((c.tail or "").split())
        # e.text is added by the caller

    words.extend((root.text or "").split())
    walk(root, True)
    return words


def rendered_words(text: str) -> list[str]:
    lines = text.split("\n")
    body_lines = []
    for l in lines[2:]:
        if l == "Source:":
            break
        body_lines.append(l)
    out = []
    for l in body_lines:
        l = re.sub(r"^\s*- ?", "", l) if re.match(r"^\s*-( |$)", l) else l
        l = re.sub(r"\\([\\*_`<])", r"\1", l)
        l = re.sub(r" \[Image: [^\]]*\] ", " ", f" {l} ")
        out.extend(w for w in l.split() if w != "|")
    return out


def file_of(path: str) -> str:
    title, name = re.match(rf"{TITLES}/([^/]+)/sections/(.+)\.xml$", path).groups()
    return f"title-{title}/{name}.md"


def section_paths(listing: str) -> dict[str, str]:
    out = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        if path.endswith(".xml") and "/sections/" in path:
            out[path] = meta.split()[2]
    return out


# ---- Commands ----

def cmd_check(args: argparse.Namespace) -> None:
    ref = args.ref or newest_ref()
    pubs = publications(ref)
    picks = [pubs[0], pubs[-1]] + pubs[1:-1][:: max(1, len(pubs) // max(1, args.n - 1))][: max(0, args.n - 2)]
    laws = Laws()
    blobs = Blobs(CODIFIED)
    bad = 0
    for day, commit in picks:
        paths = section_paths(git(CODIFIED, "ls-tree", "-r", commit, TITLES))
        n = 0
        for path, sha in sorted(paths.items()):
            xml = blobs.read(sha)
            # Text nodes split words at element boundaries, so the words are compared with whitespace removed.
            src, got = "".join(source_words(xml)), "".join(rendered_words(section(xml, laws)["text"]))
            n += 1
            if src != got:
                bad += 1
                if bad <= 15:
                    i = next((k for k, (a, b) in enumerate(zip(src, got)) if a != b), min(len(src), len(got)))
                    print(f"{day} {path}: source {len(src)} characters, rendered {len(got)}; first difference at {i}: "
                          f"{src[max(0, i - 40):i + 60]!r} vs {got[max(0, i - 40):i + 60]!r}")
        print(f"{day}: {n} sections checked", flush=True)
    print(f"{bad} sections differ")


def cmd_repo(args: argparse.Namespace) -> None:
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()) and not (out / ".git").exists():
        sys.exit(f"{out} is not empty and is not a git repository; refusing to overwrite it")
    ref = args.ref or newest_ref()
    pubs = publications(ref)
    laws = Laws()
    blobs = Blobs(CODIFIED)
    for url in URLS:
        get(url)
    head = git(CODIFIED, "rev-parse", ref).strip()

    def load(sha: str) -> Section:
        return section(blobs.read(sha), laws)

    # Phase 1: changes as (date, kind, key) -> files.  kind 0 baseline, 1 law in force that day, 2 law effective
    # outside the window (dated by publication), 3 publication with no new law named.
    groups: dict[tuple[str, int, str], dict] = {}

    def add(day: str, kind: int, key: str, pub: tuple[str, str], fname: str, text: str | None, what: str, note: str = "") -> None:
        g = groups.setdefault((day, kind, key), {"files": {}, "what": {}, "notes": [], "pubs": set()})
        g["files"][fname] = text
        g["what"][fname] = what
        g["pubs"].add(pub)
        if note:
            g["notes"].append(note)

    first_day, first_commit = pubs[0]
    listing = git(CODIFIED, "ls-tree", "-r", first_commit, TITLES)
    READ[f"{GH}/law-xml-codified/commit/{first_commit} ({TITLES})"] = hashlib.sha256(listing.encode()).hexdigest()
    state: dict[str, tuple[str, Section]] = {}
    for path, sha in sorted(section_paths(listing).items()):
        sec = load(sha)
        state[path] = (sha, sec)
        add(first_day, 0, "baseline", pubs[0], file_of(path), sec["text"], "")
    last: dict[str, str] = {file_of(p): first_day for p in state}   # each file's latest commit date so far
    print(f"baseline {first_day}: {len(state)} sections", flush=True)
    effective_outside = 0
    for (d0, c0), (d1, c1) in zip(pubs, pubs[1:]):
        listing = git(CODIFIED, "ls-tree", "-r", c1, TITLES)
        READ[f"{GH}/law-xml-codified/commit/{c1} ({TITLES})"] = hashlib.sha256(listing.encode()).hexdigest()
        now = section_paths(listing)
        changed = [p for p in sorted(set(now) | set(state)) if now.get(p) != (state[p][0] if p in state else None)]
        for path in changed:
            before = state.get(path, (None, None))[1]
            if path in now:
                after = load(now[path])
                state[path] = (now[path], after)
            else:
                after = None
                del state[path]
            if before is not None and after is not None and before["text"] == after["text"]:
                continue
            fname = file_of(path)
            what = "adds" if before is None else "removes" if after is None else (
                "repeals" if after["repealed"] and not before["repealed"] else "amends")
            new = {k: v for k, v in (after["history"] if after else {}).items() if k not in (before["history"] if before else {})}
            if not new:   # a law already named that gained a note for another of its provisions (a delayed part)
                new = {k[0]: v for k, v in (after["entries"] if after else {}).items() if k not in (before["entries"] if before else {})}
            if not new:
                new = {k: v for k, v in (after["other"] if after else {}).items() if k not in (before["other"] if before else {})}
            text = after["text"] if after else None
            if not new:
                add(d1, 3, f"publication:{d1}", (d1, c1), fname, text, what)
                last[fname] = d1
                continue
            # The law's effective date, when it keeps this file's commits in order: after the file's last commit and
            # not after the publication that first shows the change (laws are usually codified some weeks late).
            inside = {k: v for k, v in new.items() if v and last.get(fname, first_day) < v <= d1}
            if inside:
                law = max(inside, key=lambda k: (inside[k], k))
                day, kind = inside[law], 1
                if day <= d0:
                    effective_outside += 1
            else:
                law = max(new, key=lambda k: (new[k] or "", k))
                day, kind = d1, 2
            note = ""
            if len(new) > 1:
                note = f"§ {fname.split('/')[1][:-3]}: notes also name " + ", ".join(
                    f"{k}{' (effective ' + v + ')' if v else ''}" for k, v in sorted(new.items()) if k != law)
            add(day, kind, f"law:{law}:{new[law] or ''}:{'' if kind == 1 else d1}", (d1, c1), fname, text, what, note)
            last[fname] = day
        print(f"{d1}: {len(changed)} files differ", flush=True)

    # Phase 2: fast-import in date order.
    out.mkdir(parents=True, exist_ok=True)
    if not (out / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    fi = subprocess.Popen(["git", "fast-import", "--quiet", "--done", "--force"], cwd=out, stdin=subprocess.PIPE)
    w = fi.stdin
    mark = [0]

    def blob(b: bytes) -> None:
        w.write(b"data %d\n" % len(b)); w.write(b); w.write(b"\n")

    def epoch(day: str) -> int:
        return int((datetime.strptime(day, "%Y-%m-%d") - datetime(1970, 1, 1)).total_seconds()) + 12 * 3600

    def commit(author: tuple[str, str], day: str, message: str, files: dict[str, str | None]) -> None:
        mark[0] += 1
        w.write(f"commit refs/heads/main\nmark :{mark[0]}\nauthor {author[0]} <{author[1]}> {epoch(day)} +0000\n"
                f"committer {COMMITTER[0]} <{COMMITTER[1]}> {epoch(day)} +0000\n".encode())
        blob(message.encode())
        if mark[0] > 1:
            w.write(f"from :{mark[0] - 1}\n".encode())
        for path in sorted(files):
            if files[path] is None:
                w.write(f"D {path}\n".encode())
            else:
                w.write(f"M 100644 inline {path}\n".encode()); blob(files[path].encode())
        w.write(b"\n")

    def summary(g: dict) -> str:
        by: dict[str, list[str]] = defaultdict(list)
        for f, what in sorted(g["what"].items()):
            by[what].append("§ " + f.split("/")[1][:-3])
        parts = []
        for what in ("adds", "amends", "repeals", "removes"):
            s = by.get(what)
            if s:
                parts.append(f"{what} {s[0]}" + (f" and {len(s) - 1} more" if len(s) > 1 else ""))
        return "; ".join(parts)

    def listing_of(g: dict) -> str:
        names = [("§ " + f.split("/")[1][:-3], g["what"][f]) for f in sorted(g["files"])]
        shown = "\n".join(f"- {what} {n}" for n, what in names[:60])
        return shown + (f"\n- and {len(names) - 60} more" if len(names) > 60 else "")

    def src(g: dict) -> str:
        d, c = max(g["pubs"])
        return f"{GH}/law-xml-codified/commit/{c}"

    counts = defaultdict(int)
    for (day, kind, key) in sorted(groups):
        g = groups[(day, kind, key)]
        counts[kind] += 1
        if kind == 0:
            commit((f"D.C. Code, publication of {day}", f"publication-{day}@dc-code.invalid"), day,
                   f"The Code of the District of Columbia as published on {day}\n\n"
                   f"Every section of the D.C. Code in the DC Council's first dated publication ({len(g['files'])} sections).\n\n"
                   f"Consolidated: {day}\nPrinted-in: D.C. Code, publication of {day} (DCCouncil/law-xml-codified)\nSource: {src(g)}\n",
                   g["files"])
            continue
        if kind == 3:
            d1 = key.split(":", 1)[1]
            commit((f"D.C. Code, publication of {d1}", f"publication-{d1}@dc-code.invalid"), day,
                   f"D.C. Code publication of {d1}: {summary(g)}\n\n"
                   f"These sections read differently in the publication of {d1}, and their history notes name no law "
                   f"they did not name before (an editorial or conforming change, or a change not yet noted). Dated by "
                   f"the publication.\n\n{listing_of(g)}\n\n"
                   f"Published: {d1}\nPrinted-in: D.C. Code, publication of {d1} (DCCouncil/law-xml-codified)\nSource: {src(g)}\n",
                   g["files"])
            continue
        _, law, eff, d1 = key.split(":", 3)
        info = laws.get(law)
        title = info.get("title", "")
        label = f"{law} ({title})" if title else law
        email = re.sub(r"[^a-z0-9]+", "-", law.lower()).strip("-")
        domain = "congress.invalid" if law.startswith("Pub.") else "dc-council.invalid"
        notes = ("\n\nOther laws named in the same sections' new notes:\n" + "\n".join(f"- {x}" for x in g["notes"])) if g["notes"] else ""
        trailers = []
        shown_in = sorted(d for d, _ in g["pubs"])
        if kind == 1:
            body_text = (f"{law} took effect on {day}. The changes first appear in the DC Council's publication"
                         + (f" of {shown_in[0]}" if len(shown_in) == 1 else f"s of {', '.join(shown_in[:-1])} and {shown_in[-1]} (sections codified at different times)")
                         + "; this commit is dated by the law, not the publication.")
            trailers.append(f"In-force: {day}")
        else:
            body_text = (f"Dated by the publication of {d1}, the first to show these changes: "
                         + (f"the law's effective date, {eff}, is before the first publication or an earlier change "
                            f"to the same section, or after this publication, so it cannot date this commit." if eff else
                            "the data gives no effective date for the law."))
        trailers += [f"Law: {law}"] + ([f"Short-title: {title}"] if title else [])
        trailers += ([f"Effective: {eff}"] if eff and kind != 1 else []) + [f"Published: {', '.join(shown_in)}", f"Source: {src(g)}"]
        commit((label, f"{email}@{domain}"), day,
               f"{label}: {summary(g)}\n\n{body_text}\n\n{listing_of(g)}{notes}\n\n" + "\n".join(trailers) + "\n",
               g["files"])
    w.write(b"done\n"); w.close(); fi.wait()
    tip = subprocess.run(["git", "rev-parse", "main"], cwd=out, capture_output=True, text=True).stdout.strip()
    record_to = pubs[-1][0]

    from docs import CHANGES, LICENSE, corpus, readme, reproduce

    files_now = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=out, capture_output=True, text=True).stdout.split()
    emails = subprocess.run(["git", "log", "--format=%ae", "main"], cwd=out, capture_output=True, text=True).stdout.split()
    in_force = subprocess.run(["git", "log", "--format=%(trailers:key=In-force,valueonly)", "main"], cwd=out, capture_output=True, text=True).stdout.split()
    manifest = "".join(f"{h}  {u}\n" for u, h in sorted(READ.items()))
    titles = sorted({f.split("/")[0] for f in files_now}, key=lambda t: (len(t), t))
    info = {
        "titles": len(titles), "sections": len(files_now), "first": first_day, "record_to": record_to,
        "publications": len(pubs), "commits": len(emails) + 1, "law_commits": counts[1] + counts[2],
        "law_dated": counts[1], "law_pub_dated": counts[2], "pub_commits": counts[3],
        "laws": len({e for e in emails if e.endswith("@dc-council.invalid") or e.endswith("@congress.invalid")}),
        "last_in_force": max(in_force) if in_force else first_day,
        "ref": ref, "head": head, "laws_commit": laws.commit, "data_sha256": hashlib.sha256(manifest.encode()).hexdigest(),
        "last": tip, "python": sys.version.split()[0],
        "git": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.split()[-1],
        "blob": subprocess.run(["git", "hash-object", str(Path(__file__).resolve())], capture_output=True, text=True).stdout.strip(),
        "robots_github": get("https://github.com/robots.txt").decode("utf-8", "replace"),
        "sizes": {r.name: sum(f.stat().st_size for f in r.rglob("*") if f.is_file()) for r in (CODIFIED, LAWS)},
    }
    docs = {
        "README.md": readme(info), "REPRODUCE.md": reproduce(info), "CHANGES.md": CHANGES, "LICENSE.md": LICENSE,
        "corpus.json": corpus(info), "tools/dc.py": (HERE / "tool.py").read_text(encoding="utf-8"),
        "build/build.py": Path(__file__).read_text(encoding="utf-8"), "build/docs.py": (HERE / "docs.py").read_text(encoding="utf-8"),
        "build/tool.py": (HERE / "tool.py").read_text(encoding="utf-8"), "build/DATA-SHA256SUMS": manifest,
    }
    fi = subprocess.Popen(["git", "fast-import", "--quiet", "--done", "--force"], cwd=out, stdin=subprocess.PIPE)
    w = fi.stdin
    w.write(f"commit refs/heads/main\nmark :1\nauthor {COMMITTER[0]} <{COMMITTER[1]}> {epoch(record_to)} +0000\n"
            f"committer {COMMITTER[0]} <{COMMITTER[1]}> {epoch(record_to)} +0000\n".encode())
    blob(b"Documentation, the tool, and the build with the checksums of its data\n\nKind: documentation\n")
    w.write(f"from {tip}\n".encode())
    for path in sorted(docs):
        w.write(f"M 100644 inline {path}\n".encode()); blob(docs[path].encode("utf-8"))
    w.write(b"\ndone\n"); w.close(); fi.wait()
    subprocess.run(["git", "checkout", "-q", "-f", "main"], cwd=out, check=True)
    count = subprocess.run(["git", "rev-list", "--count", "main"], cwd=out, capture_output=True, text=True).stdout.strip()
    print(f"{count} commits ({dict(counts)}), {first_day} to {record_to}; {effective_outside} dated by a law effective before the publication before -> {out}")


def main() -> None:
    sys.path.insert(0, str(HERE))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    r = sub.add_parser("repo"); r.add_argument("out"); r.add_argument("--ref")
    c = sub.add_parser("check"); c.add_argument("n", nargs="?", type=int, default=2); c.add_argument("--ref")
    a = ap.parse_args()
    {"fetch": cmd_fetch, "repo": cmd_repo, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
