# Git for the Code of the District of Columbia

The text of the D.C. Code, section by section, with a commit for each change between the DC Council's dated
publications of the code, from 2021-10-18 to 2026-10-27. Where a section's history notes name the law that
changed it and give its effective date, **the commit is the law taking effect**: its author is the D.C. Law or Act,
and its date is the law's effective date.

| The question | The command |
| --- | --- |
| What did D.C. Code § 1-1001.05 say on 1 January 2024? | `python tools/dc.py on 2024-01-01 title-1/1-1001.05.md` |
| Which law wrote each provision? | `git blame title-1/1-1001.05.md` |
| What changed between two dates? | `python tools/dc.py diff 2022-01-01 2025-01-01 title-1/1-1001.05.md --words` |
| Everything one law changed | `python tools/dc.py law "D.C. Law 24-342"` |
| Every change to a section, with its dates | `python tools/dc.py log title-1/1-1001.05.md` |
| The most amended sections of a title | `git log --format= --name-only -- title-47 \| sort \| uniq -c \| sort -rn \| head` |

`tools/dc.py` needs only Python 3 and git. It picks the text by each commit's `In-force:` date, or its `Published:` date
where no effective date applies (see below), so the answer does not depend on your time zone.

## What is here

54 titles and 24225 section files as of 2026-10-27, from 396 dated
publications. There are 1677 commits: the code as first published on 2021-10-18; 1405
credited to a D.C. Law or Act (or an Act of Congress), 1138 of them dated by the law's effective date and
267 by the publication that first showed the change (see below); 270 publication commits for changes
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

- **Before 2021-10-18.** The first commit is the code as first published in this series. Earlier changes are in the
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
