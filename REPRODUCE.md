# How this history was made, and how to make it again

## Short version

```sh
mkdir -p dc/cache && cp build/build.py build/docs.py build/tool.py dc/ && cd dc
python build.py fetch                  # robots.txt, repo metadata, and two git clones (all cached)
python build.py repo ../rebuilt --ref publication/2026-05-23.2026-10-27
git -C ../rebuilt log --format=%H      # the same commits, with the same hashes
```

The history was built from `publication/2026-05-23.2026-10-27` at commit `08f220516b9eab297629753d8a2b8be02fb82c17` of law-xml-codified and from law-xml at commit
`ad61a5193324fa0818d9a7bf1aec8e71197121e8`. Both repositories keep growing; a later clone gives the same history up to 2026-10-27 as
long as those commits are used (`--ref <commit>` works too). The last commit before the documentation is `c86553b84d5c67455c369cd036c6569aa3022e92`.

## Sources

| What | Where | Requests | Retrieved |
| --- | --- | ---: | --- |
| robots.txt | `https://github.com/robots.txt`, `https://api.github.com/robots.txt` | 2 | 2026-10-28 |
| Repository metadata and READMEs (for the licence statement; none is present) | `https://api.github.com/repos/DCCouncil/<repo>` and `/readme`, for law-xml, law-xml-codified, law-html | 5 | 2026-10-28 |
| The code at every publication | `git clone --mirror https://github.com/DCCouncil/law-xml-codified` (105.4 MB on disk) | 1 clone (2 HTTP requests) | 2026-10-28 |
| The laws and acts (short title, effective date, Register citation) | `git clone --mirror https://github.com/DCCouncil/law-xml` (155.2 MB on disk) | 1 clone (2 HTTP requests) | 2026-10-28 |

Nothing was read from code.dccouncil.gov. `build/DATA-SHA256SUMS` lists the sha256 of every HTTP response, of the
`git ls-tree` listing of the code at each publication commit (which pins every file by its git hash), and of every law
file read (sha256 of that list: `c777ec0d3b6171509fb9bb5541de997f03727ecc4ad72a7f36a4bec734650070`).

**robots.txt, checked 28 October 2026.**

- **code.dccouncil.gov** (recorded in Lexifina's source survey, not fetched again for this build) names ClaudeBot:
  `User-agent: ClaudeBot` / `Disallow: /`, and carries `Content-signal: search=yes,ai-train=no`. **Not used.** The site's
  footer says: "The codes and laws on this website are in the public domain. Please do not scrape. Instead, bulk download
  the HTML or XML", linking to the GitHub repositories used here.
- **github.com**, the group that names ClaudeBot (relevant lines):

```
User-agent: GPTBot
User-agent: OAI-SearchBot
User-agent: ClaudeBot
User-agent: anthropic-ai
User-agent: PerplexityBot
Crawl-delay: 1
Disallow: /*/archive/
Disallow: /*/raw/
Disallow: */tarball/
Disallow: */zipball/
Disallow: /.git/
Disallow: */.git/
Disallow: /*.git$
Disallow: /*/*/commits/
Disallow: /*/*/branches$
Disallow: /*/*/branches?*
Disallow: /*/*/branches/*
```

  The clones use the repository URLs without `.git` (`/DCCouncil/law-xml-codified/info/refs`, `.../git-upload-pack`),
  which no rule disallows; no archive, tarball, raw, tree, commits or branches page was requested. Requests were made one
  at a time, at least 1.5 seconds apart (Crawl-delay: 1). User agent for HTTP:
  `Mozilla/5.0 (compatible; Lexifina state law history; +https://lexifina.com/watch)`; for git:
  `git/2 (Lexifina state law history; +https://lexifina.com/watch)`.
- **api.github.com** has no robots.txt (404).

## The build, step by step

1. `python build.py fetch` fetched the robots.txt files and metadata above and cloned both repositories (Python
   3.12.10).
2. `python build.py check 6` rendered every section at six publications (the first, the last and four between) and
   compared the rendering with every text node of its source XML, character for character with whitespace removed: no
   section differs.
3. `python build.py repo <out>` wrote the history with `git fast-import` (git 2.46.0.windows.1), then the documentation commit,
   dated 2026-10-27.

`build/build.py` has git blob `5b5be7f956926c9b778cf95a5a25d18ecb7dbdd4`, the same file as `scripts/state-law/dc/build.py` in Lexifina's repository.

## Decisions made by hand

1. **The publications.** law-xml-codified has 396 dated publications on the first-parent line of its
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
