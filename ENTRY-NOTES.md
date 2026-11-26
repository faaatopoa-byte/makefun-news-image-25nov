# Entry notes — news-image-20261125

## Requirements as verified (2026-11-26, from make.fun itself)
- Source: GET https://make.fun/api/competitions/news-image-20261125/requirements,
  the bounty page https://make.fun/bounty/news-image-20261125, and this
  competition's own kit (RULES.txt / competition.yaml), downloaded fresh.
- Entrypoint at repo root: `main.ts` (Node 22) or `main.py` (Python 3.13).
  This entry uses `main.py`.
- The program writes one image to `/output/entry.png`.
- Image: whole PNG or JPEG, at most 1 MiB, at most 1024x1024 px.
- No network at run time; the program runs twice and both runs must write
  the same bytes.
- LICENSE with an OSI-approved license at the submitted commit (MIT here).
- Repo created after the competition opened (2026-11-25T00:00:00Z);
  transcripts of the building sessions are a required submission
  deliverable (bundle made with this competition's own kit CLI).
- Judging: AI pairwise on the image alone, blind rounds; 50 places share
  $100 ($20 / $12 / $6 / $2 x7 / $1.20 x40).
- Entries close 2026-11-27T00:00:00Z (07:00 WIB). The reward is locked in
  escrow at open, so the entry is signed with the entrant's wallet keypair.

## How this entry meets them
- main.py copies the committed entry.png to /output/entry.png byte for
  byte (deterministic by construction; verified: two runs from a foreign
  cwd, identical sha256 3a072d6f850266621962833c7f13d3b68f1b1bdb2613073dfa46ba253da89b02,
  equal to the committed file; render.py also reproduces it byte for byte).
- entry.png is 1024x1024 and 276,486 bytes — inside both caps.
- The news content was researched on 26 Nov 2026 from public digests of
  25 Nov 2026 reporting; every story is backed by at least two independent
  digests (SOURCES.md). No story was invented. The page names its day
  ("Wednesday 25 November 2026") as its largest element, as the judge's
  instructions ask, and its DATE CHECK box names five earlier-day events
  deliberately left out.
- WORKLOG.md is the genuine session log of this build.

## Submission-stage notes
- The staging repo under ~/workspace/makefun-entries/news-image-25nov/
  carries this competition's three-badge block prepended to the README and
  the .makefun/owner.json claim file (Faa's account is wallet-only).
- handed_over_places for this competition is "none": the bundle is made
  from the harness's recorded session files with the kit's CLI, not from
  a hand-written export.
- The renderer (render.py + scene_kit.py) is the news-image template
  built for this entry series and kept in the workspace; the data it
  draws (entry_data) was written fresh in this session from verified
  25 Nov 2026 reporting.
