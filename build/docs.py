"""The documentation files of the D.C. Code git history, filled in by build.py with the figures of each build."""

from __future__ import annotations

import json


def _robots(text: str) -> str:
    """The group of github.com's robots.txt that names ClaudeBot, quoted."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "User-agent: GPTBot")
    except StopIteration:
        return text[:1500]
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].strip()), len(lines))
    group = lines[start:end]
    keep = [l for l in group if l.startswith("User-agent") or l.startswith("Crawl-delay")
            or any(k in l for k in ("/*.git$", "*/.git/", "/.git/", "/*/raw/", "/*/archive/", "tarball", "zipball", "/*/*/branches", "/*/*/commits/"))]
    return "\n".join(keep)


def readme(i: dict) -> str:
    ex = "title-1/1-1001.05.md"
    return f"""# Git for the Code of the District of Columbia

The text of the D.C. Code, section by section, with a commit for each change between the DC Council's dated
publications of the code, from {i['first']} to {i['record_to']}. Where a section's history notes name the law that
changed it and give its effective date, **the commit is the law taking effect**: its author is the D.C. Law or Act,
and its date is the law's effective date.

| The question | The command |
| --- | --- |
| What did D.C. Code § 1-1001.05 say on 1 January 2024? | `python tools/dc.py on 2024-01-01 {ex}` |
| Which law wrote each provision? | `git blame {ex}` |
| What changed between two dates? | `python tools/dc.py diff 2022-01-01 2025-01-01 {ex} --words` |
| Everything one law changed | `python tools/dc.py law "D.C. Law 24-342"` |
| Every change to a section, with its dates | `python tools/dc.py log {ex}` |
| The most amended sections of a title | `git log --format= --name-only -- title-47 \\| sort \\| uniq -c \\| sort -rn \\| head` |

`tools/dc.py` needs only Python 3 and git. It picks the text by each commit's `In-force:` date, or its `Published:` date
where no effective date applies (see below), so the answer does not depend on your time zone.

## What is here

{i['titles']} titles and {i['sections']} section files as of {i['record_to']}, from {i['publications']} dated
publications. There are {i['commits']} commits: the code as first published on {i['first']}; {i['law_commits']}
credited to a D.C. Law or Act (or an Act of Congress), {i['law_dated']} of them dated by the law's effective date and
{i['law_pub_dated']} by the publication that first showed the change (see below); {i['pub_commits']} publication commits for changes
whose notes name no new law; and this documentation. Each section is one Markdown file, `title-<n>/<section>.md`, with
one designated provision per line (`- (a) ...`, indented two spaces per level), so `git blame` names a law for every
provision. The last lines are the section's source note: its History notes, one per law, each naming a law, its
effective date and its District of Columbia Register citation.

## How a change is dated and credited

The DC Council publishes the code as XML, a whole new snapshot each time it codifies new laws (often several times a
month). Between two publications, each section whose text or source note changed is matched with the laws its History
notes gained (or, if none, a law already named that gained a note for another of its provisions, or else the laws
its emergency and temporary legislation notes gained):

- **The law's effective date is known.** The commit is dated that day, authored by the law, with an `In-force:`
  trailer, even when the Council codified the law some weeks later (as it usually does); `Published:` names the
  publication that first showed it.
- **The effective date cannot be used**: it is not given, it is before the first publication or before an earlier
  change to the same section (dating by it would put the section's history out of order), or it is after the
  publication. The commit is then dated by the publication that first shows the change, with `Published:` and
  `Effective:` trailers and no `In-force:` trailer.
- **No new law named.** A commit of the publication ("D.C. Code publication of ..."), dated by it: editorial and
  conforming changes, and changes whose notes the publisher had not yet updated.

Where one section gained notes for several laws between two publications, the commit is credited to the one that took
effect last, and its message names the others. Commits are dated at noon UTC.

## What it does not show

- **Before {i['first']}.** The first commit is the code as first published in this series. Earlier changes are in the
  source notes, not in the history.
- **Text in force between publications.** If two laws changed a section between two publications, only the later text
  is shown, from the later law's effective date. A law codified late is shown from its effective date, so the history
  can show text before the Council's website did.
- **Future and contingent changes.** Amendments that await funding ("subject to appropriations") or a later date are
  codification instructions in the publisher's XML and are not shown until a publication applies them.
- **Annotations.** Editor's notes, cross references, emergency/temporary legislation notes and other annotations are left
  out; only the text and the History notes are kept. Images in a few sections are named, not included.
- **Official status.** The DC Council's online code is the unofficial, current compilation; for anything that matters,
  read the law itself.

## How it is built

From the DC Council's own bulk repositories on GitHub, [DCCouncil/law-xml-codified](https://github.com/DCCouncil/law-xml-codified)
(the code at each publication) and [DCCouncil/law-xml](https://github.com/DCCouncil/law-xml) (the laws' titles and
effective dates), read with `git clone`. The Council's website asks for bulk download instead of scraping, and its
robots.txt disallows ClaudeBot, so the website is not used at all. The build script is in [`build/`](build/), with
checksums of what it read; the same clones give the same commits. [REPRODUCE.md](REPRODUCE.md) records the sources,
the commands and what AI models did; [CHANGES.md](CHANGES.md) records how the history changes.

Lexifina keeps the US Code ([lexifina/united-states-law](https://github.com/lexifina/united-states-law)) and other
bodies of law in the same form, all part of [lexifina/global-law](https://github.com/lexifina/global-law).

Built by [Lexifina](https://lexifina.com). For corrections, open an issue.

## License

The DC Council states that the codes and laws it publishes are in the public domain. The history, commit messages,
tools and documentation are released under [CC BY 4.0](LICENSE.md).
"""


def reproduce(i: dict) -> str:
    mb = {k: round(v / 1e6, 1) for k, v in i["sizes"].items()}
    return f"""# How this history was made, and how to make it again

## Short version

```sh
mkdir -p dc/cache && cp build/build.py build/docs.py build/tool.py dc/ && cd dc
python build.py fetch                  # robots.txt, repo metadata, and two git clones (all cached)
python build.py repo ../rebuilt --ref {i['ref']}
git -C ../rebuilt log --format=%H      # the same commits, with the same hashes
```

The history was built from `{i['ref']}` at commit `{i['head']}` of law-xml-codified and from law-xml at commit
`{i['laws_commit']}`. Both repositories keep growing; a later clone gives the same history up to {i['record_to']} as
long as those commits are used (`--ref <commit>` works too). The last commit before the documentation is `{i['last']}`.

## Sources

| What | Where | Requests | Retrieved |
| --- | --- | ---: | --- |
| robots.txt | `https://github.com/robots.txt`, `https://api.github.com/robots.txt` | 2 | 2026-10-28 |
| Repository metadata and READMEs (for the licence statement; none is present) | `https://api.github.com/repos/DCCouncil/<repo>` and `/readme`, for law-xml, law-xml-codified, law-html | 5 | 2026-10-28 |
| The code at every publication | `git clone --mirror https://github.com/DCCouncil/law-xml-codified` ({mb.get('law-xml-codified.git')} MB on disk) | 1 clone (2 HTTP requests) | 2026-10-28 |
| The laws and acts (short title, effective date, Register citation) | `git clone --mirror https://github.com/DCCouncil/law-xml` ({mb.get('law-xml.git')} MB on disk) | 1 clone (2 HTTP requests) | 2026-10-28 |

Nothing was read from code.dccouncil.gov. `build/DATA-SHA256SUMS` lists the sha256 of every HTTP response, of the
`git ls-tree` listing of the code at each publication commit (which pins every file by its git hash), and of every law
file read (sha256 of that list: `{i['data_sha256']}`).

**robots.txt, checked 28 October 2026.**

- **code.dccouncil.gov** (recorded in Lexifina's source survey, not fetched again for this build) names ClaudeBot:
  `User-agent: ClaudeBot` / `Disallow: /`, and carries `Content-signal: search=yes,ai-train=no`. **Not used.** The site's
  footer says: "The codes and laws on this website are in the public domain. Please do not scrape. Instead, bulk download
  the HTML or XML", linking to the GitHub repositories used here.
- **github.com**, the group that names ClaudeBot (relevant lines):

```
{_robots(i['robots_github'])}
```

  The clones use the repository URLs without `.git` (`/DCCouncil/law-xml-codified/info/refs`, `.../git-upload-pack`),
  which no rule disallows; no archive, tarball, raw, tree, commits or branches page was requested. Requests were made one
  at a time, at least 1.5 seconds apart (Crawl-delay: 1). User agent for HTTP:
  `Mozilla/5.0 (compatible; Lexifina state law history; +https://lexifina.com/watch)`; for git:
  `git/2 (Lexifina state law history; +https://lexifina.com/watch)`.
- **api.github.com** has no robots.txt (404).

## The build, step by step

1. `python build.py fetch` fetched the robots.txt files and metadata above and cloned both repositories (Python
   {i['python']}).
2. `python build.py check 6` rendered every section at six publications (the first, the last and four between) and
   compared the rendering with every text node of its source XML, character for character with whitespace removed: no
   section differs.
3. `python build.py repo <out>` wrote the history with `git fast-import` (git {i['git']}), then the documentation commit,
   dated {i['record_to']}.

`build/build.py` has git blob `{i['blob']}`, the same file as `scripts/state-law/dc/build.py` in Lexifina's repository.

## Decisions made by hand

1. **The publications.** law-xml-codified has {i['publications']} dated publications on the first-parent line of its
   newest branch (the publisher rebuilt the whole series on 2026-05-23; its trees match the older `publication/2021-10-18.*`
   branches on every date sampled). Three older branches (2023-11-05, 2025-04-02, 2025-04-09) are not in the rebuilt
   series and are not used; their changes appear in the next publication. Where a day had two publications, the later is
   used.
2. **Dating.** A commit is dated by the effective date of the law it is credited to (`In-force:`) when that date is
   after the section's previous commit (the first publication, or the last change to it) and on or before the
   publication that first shows the change. Laws are usually codified some weeks after they take effect, so most
   effective dates fall before the publication that shows them; dating by the law keeps `tools/dc.py on` true to the law
   in force. Otherwise the commit is dated by that publication (`Published:`), with the law's effective date, when known,
   in `Effective:`. The effective date
   comes from the History note's `eff` attribute, else law-xml's `<effective>` for the law, else the date that opens the
   prose note (for D.C. Laws, the effective date; for Acts of Congress, the approval date).
3. **Crediting.** The laws credited are those a section's History notes name at the newer publication but not at the
   older one; where none, a law already named that gained a note for another of its provisions (often a delayed
   repeal or amendment reaching its date); where none, the laws its new emergency and temporary legislation notes name.
   A difference with none of these is a publication commit.
4. **What is text.** Section text, designations, headings and tables (one row per line, cells joined by ` | `). Left
   out: annotations other than History notes, codification instructions (`codify:` elements: pending find/replace,
   insert, repeal and applicability markers), margin notes and the `reason` field (its words also appear in the text).
   The publisher's own notes inside the text (such as "NOTE: This section was created by emergency legislation ...")
   are kept. Images are named (`[Image: file]`), not copied.
5. **Source note.** Prose History notes are kept as written. Structured notes (newer laws) are written
   "<effective date>, <law>, <sections of the law>, <DC Register citation>", one line per law, with the Register citation
   from law-xml. Notes the publisher marks `display="false"` are not shown.
6. **File names** follow the publisher's: `title-<n>/<section>.md` (the Uniform Commercial Code sections in title 28 are
   `28~1-101.md` for § 28:1-101, as in the source).

## What AI models did

This repository was built on 28 October 2026 in **Claude Code**, Anthropic's coding tool, by the model **Claude Opus
5.5** (model id `claude-opus-5-5`), from a goal set by the user at Lexifina: to bring all US law into git, in the same
form as the US Code history. The model wrote `build/build.py`, `tools/dc.py` and these documents and ran the commands
above. **No model wrote or edited any legal text, and no model is called when the history is built.** Every word comes
from the DC Council's XML; every date from its publications and its History notes; every law's title from law-xml. The
work has not been reviewed line by line by a lawyer.
"""


CHANGES = """# Changes and updates

Newest first. Lexifina's global-law repository keeps the log for every corpus (`CHANGELOG.md` there).

## 28 October 2026

First build: the D.C. Code as first published by the DC Council on 2021-10-18, then each change between its dated
publications to 2026-10-27, credited to the D.C. Law or Act its history notes name and dated by the law's effective date
where that falls between the two publications. Built from the Council's GitHub repositories; the code.dccouncil.gov
website, whose robots.txt disallows ClaudeBot, was not used.
"""

LICENSE = """# License

The Council of the District of Columbia states on its code website that "The codes and laws on this website are in the
public domain", and publishes the XML used here on GitHub for bulk download. The repositories carry no licence file.
The text of the D.C. Code in the `title-*` folders is therefore given here as public domain text.

The arrangement of the history (which commits exist, their dates and authors), the commit messages, the source-note
formatting of structured history notes, the tools and the documentation are © Lexifina, released under the Creative
Commons Attribution 4.0 International License (CC BY 4.0): https://creativecommons.org/licenses/by/4.0/
"""


def corpus(i: dict) -> str:
    return json.dumps({
        "corpus": "us/district-of-columbia/statutes", "code": "DC", "name": "Code of the District of Columbia",
        "label": "D.C. Code", "language": "en",
        "history_from": i["first"], "record_to": i["record_to"],
        "record_note": f"The D.C. Code at each of the DC Council's {i['publications']} dated publications from {i['first']} to {i['record_to']}, via DCCouncil/law-xml-codified; built 2026-10-28.",
        "in_force_trailer": "In-force", "baseline_trailer": "Consolidated", "has_future_branch": False,
        "author": "the D.C. Law or Act (or Act of Congress) the section's new History notes name (Law trailer); otherwise the publication",
        "granularity": "the law's effective date where it falls between two publications; otherwise the publication date (Published trailer)",
        "scope": {
            "when_absent": "the D.C. Code records applicability in each law's notes (Applicability annotations), not case by case",
            "default_reach": {"rule": "presumption against retroactivity: a statute is not applied to events completed before its enactment absent clear legislative intent",
                              "authority": "Landgraf v. USI Film Products, 511 U.S. 244 (1994), applied by the D.C. Court of Appeals",
                              "decided_here": False},
        },
        "citation": {"file": "(title-[0-9A-Z]+)/([0-9][0-9A-Za-z.-]*)\\.md", "cites": "§ ?{n}([^0-9a-zA-Z.:-]|\\.([^0-9a-zA-Z]|$)|$)"},
        "tool": "tools/dc.py",
    }, indent=2, ensure_ascii=False) + "\n"
