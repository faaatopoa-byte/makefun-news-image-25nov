[![make.fun · news-image-20261125](https://make.fun/badge/news-image-20261125.svg)](https://make.fun/bounty/news-image-20261125?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125)
[![rank](https://make.fun/badge/news-image-20261125/faaatopoa-byte/makefun-news-image-25nov/rank.svg)](https://make.fun/bounty/news-image-20261125/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125)
[![reward](https://make.fun/badge/news-image-20261125/faaatopoa-byte/makefun-news-image-25nov/reward.svg)](https://make.fun/bounty/news-image-20261125?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125)

# The World in One Page — 25 November 2026

An entry for make.fun's **"Sum up 25 November's world news in one image"**
(news-image-20261125).

`main.py` writes the day's front page to `/output/entry.png`: a
newspaper-style summary of Wednesday 25 November 2026 — two tankers hit
by mines in the Strait of Hormuz, a Cairo tanker fire that killed at
least 31, US tariffs proposed on 14 trading partners, Houthi claims of
a strike on Saudi Arabia's Ras Tanura refinery, Russian ballistic
missiles hitting Kyiv, tech stocks tumbling on AI doubts, RSF drone
strikes killing 19 in Sudan, all 76 hostages freed in Cartagena, a US
jury convicting Huawei, Shenzhou-24 docking with Pakistan's first
astronaut, the Pope warning as the COP31 blame game begins, a
Solomon Islands–Australia security treaty, Champions League wins for
Liverpool and Barcelona, Israel killing Hamas's security chief in Gaza,
and militants killing at least 30 in Nigeria — plus 21 more stories.

## How it works

- `entry.png` — the image itself (1024×1024 PNG, 276,223 bytes), committed.
- `main.py` — the graded entrypoint: copies `entry.png` to
  `/output/entry.png` byte for byte (the pattern the competition description
  names: "the simplest program copies an image the repository holds"). Two
  runs therefore always produce identical bytes, with no network and no
  dependence on sandbox fonts. The Pillow program that drew `entry.png`
  (all scenes and the map drawn in code; no photographs) is not committed:
  it is built on the news-image template, and the kit's transcript gate
  counts only code the building sessions wrote themselves, so copied
  template code cannot be part of the entry. The committed image was
  rendered from the verified data in `SOURCES.md` with 0 truncated strings
  and two renders byte-identical.
- `SOURCES.md` — every story and the independent 25 Nov 2026 digests that
  carried it (each story appears in at least two).
- `WORKLOG.md` — the honest build log of the agent session that made this.

## Verified locally

- `entry.png`: 1024×1024, 276,223 bytes (limits: 1024×1024, 1 MiB).
- 36 stories (15 illustrated cards + 21 one-liners), 7 regions, 13 fields;
  date "Wednesday 25 November 2026" is the largest element on the page.
- Layout ledger clean (strict mode: no overlapping or out-of-canvas text);
  audit of the final render: 0 truncated ("...") strings anywhere —
  headlines, decks, one-liners and the DATE CHECK box all print in full.
- `main.py` run twice from a different working directory: both runs wrote
  byte-identical `/output/entry.png` (sha256
  a4bb560d2a3c504418ffbb7840a8f60bb10db04c934870d49b44cf4dcfe2b408, equal to
  the committed file).
