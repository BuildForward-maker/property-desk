# CLAUDE.md

Property Desk — a single-file research and tracking tool for a Bengaluru property
search. The entire app is `index.html` (~2,600 lines).

## Hard rules

These are not preferences. Breaking any of them breaks how the tool is used and
shared.

### 1. One self-contained file, plus data beside it

`index.html` is the whole app. Never split the *app* into separate `.js`,
`.css`, or ES-module files. Markup, styles, and scripts all stay inline in that
one file. New functionality goes into the existing `<style>` and `<script>`
blocks.

Large **data** may live in `data/` and be fetched on demand. `LOCALITIES` was
~370KB of a 780KB file and none of it was needed to render the first screen, so
it now loads from `data/localities.app.json` the first time somebody searches.

**No further data may be inlined above ~100KB.** Anything larger goes in
`data/` and loads lazily. Three conditions on any such split:

- the app must still boot and be useful with the fetch failing
- the failure must be stated in the UI, not swallowed
- `AREAS`, `SOC` and the metro tables stay inline — they are needed immediately

Note the consequence for rule 2: opened straight from the filesystem, a browser
will not `fetch()` a sibling file, so a `file://` open gets the app minus the
lazy data. That is why the fallback has to be real rather than theoretical.

### 2. No build tools

No npm, no `package.json`, no webpack, vite, rollup, esbuild, TypeScript, JSX, or
any other bundler or transpiler. The file must run by double-clicking it or
opening it from a `file://` URL. Write plain browser-ready HTML, CSS, and
JavaScript only.

### 3. One external dependency

The only external JS dependency is the Supabase client from jsdelivr:

```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
```

(Google Fonts stylesheets are also loaded and are fine to keep.) Do not add other
libraries, frameworks, or CDN scripts without being asked.

### 4. Maps: Leaflet + a keyless basemap

For maps, use Leaflet with a keyless raster basemap (currently Esri World Light
Gray Canvas + Reference labels). Never Google Maps, CARTO, or Stadia — all now
require an API key or billing account.

Leaflet's CSS and JS may be loaded from a CDN as an exception to rule 3.

### 5. Supabase config lives in the URL hash

Config travels inside the link as `#cfg=<base64 json>` with `{u, k, w, n}`, read
by `readCfg()` and written by `writeCfgLink()`. Never hardcode a Supabase URL,
anon key, or workspace into the file. **Never commit API keys.** If you need to
test against a real backend, put the config in the hash locally and keep it out
of the commit.

### 6. Local mode must keep working

`MODE` is `'local'` or `'shared'`. When no config is present, the Supabase library
fails to load, or the connection check in `initSupabase()` throws, the app falls
back to local mode and remains fully usable. Preserve this. Every Supabase call
must be guarded (`if(MODE!=='shared')return;`) and wrapped so a failure degrades
quietly instead of throwing.

### 7. `tools/` and `data/` are offline tooling, not app code

`tools/` holds one-time data-prep scripts, run by hand. They are never loaded by
`index.html` and never run at build time or page load — there is still no build
step. `data/` holds their inputs and outputs.

`data/geocache.json` **must be preserved.** It is the record of every Nominatim
query already made. The script reads it before requesting anything, so a re-run
costs zero requests for places already resolved. Nominatim forbids systematic
querying; deleting the cache means hitting them all over again. Misses are
cached too, deliberately — an unresolvable name should not be re-asked.

`tools/enrich.py` carries two safeguards worth knowing before editing it:

- `GEO_FIX` holds corrections for places Nominatim resolves to the right name
  in the wrong part of the city — Bengaluru has two Kothanurs and two Bagalurs.
  Each fix is candidate queries **plus the box the answer must land in**; a
  candidate outside the box is rejected and the run says so, so a manual
  override is a checked one rather than merely a hand-typed one. Where no query
  can satisfy the box, `anchor` adopts the coordinate of another real OSM
  locality in the same micro-market from `data/localities.json`. Never type a
  coordinate in from memory.
- A pin that **moves** invalidates everything derived from it. Drive times, the
  nearest station and the metro journey all describe wherever the old
  coordinate was, so a correction drops them rather than inheriting them, and
  `patch_index` removes a field that no longer has a value instead of leaving
  the previous one in place. The "never downgrade on a failed stage" rule still
  holds; this is the separate case.

`--areas=A,B` re-runs a named handful. It merges into `data/enrichment.json`
rather than replacing it, and leaves the Tier 2 set alone entirely: parent
areas are assigned by nearest-of-all-86, so re-deriving them from a subset
re-parents every locality to it.

Rules 1 and 2 are about the app. A `tools/` script is not a violation of either.

## Third-party services — swap plan

Current (all keyless, free, non-commercial):
- Tiles: Esri World Light Gray Canvas + Reference labels
- Geocoding: Nominatim, one-time offline enrichment only
- Routing: OSRM demo server, one-time offline enrichment only
- POIs: Overpass API (kumi.systems mirror), one-time only

RULE: none may be called from the browser at runtime. All results are
precomputed by `tools/enrich.py` and baked into `index.html` as plain data. This
keeps providers swappable and running costs zero.

BEFORE CHARGING MONEY: the OSRM demo server and Nominatim are non-commercial use
only. Self-host OSRM or move to a paid routing provider before taking payment.

Swapping tiles is a one-line change. Swapping geocoders means re-running
`tools/enrich.py`, not a migration.

Geocode results are cached in `data/geocache.json`. Read the cache first; never
re-query a place already resolved. Nominatim forbids systematic and bulk
querying, so the script must hit it once only. Misses are cached too, so
failures are not re-asked.

Offline data-prep tools live in `tools/` and are written in Python 3 (stdlib
only). The no-npm rule applies to the app; tools must not add any runtime
dependency to `index.html`.

## Data

Two arrays hold the domain data. Keep their shapes consistent when editing.

**One factor set, two weightings.** `W_PERSONAL` and `W_INVEST` draw on the
same registry and differ only in how heavily each factor counts. Both tables
are integers summing to exactly 100, so a buyer can add them up: where a
weight changes, redistribute in proportion and round by largest remainder
rather than leaving a table that displays as 99. A factor
present in one score and missing from the other is the bug that produced the
pipeline asymmetry, so do not reintroduce one without a reason that survives
the question "does the other buyer really not care about this?".

A self-use buyer sells one day, so price growth and liquidity are theirs too.
An investor's exit **is** a self-use buyer, so infrastructure and liveability
are their demand engine rather than a side issue. Only two factors are
genuinely one-sided: the investor has no `commute` (they do not live there,
and `tech` carries that weight instead, at 13% against 8%), and the resident
has no `sweet` (budget fit asks their version of the question).

Both tables carry **current infrastructure alongside future pipeline**, and
they must stay paired. Pipeline can only ever reward places that *lack*
infrastructure, so a table with pipeline and no counterweight structurally
penalises mature areas. `infraNow` is the mirror term — what runs here today,
scored on the same curve from the same project rows plus the operational metro
graph.

A factor that cannot be computed for this person — no workplace chosen, no
budget set — is **dropped and the rest renormalised**, never silently scored
zero, which would punish an area for a question the buyer declined to answer.
The renormalisation is **stated in the breakdown**, naming what was dropped
and why, because otherwise the percentages on screen quietly stop matching the
weights the tool claims to use.

Every score and every factor row carries an **i** that opens `FACTOR_DOC` /
`SCORE_DOC`: what the factor measures, where the number came from and when,
its weight here against its weight on the other score and why they differ, and
whether it is area-level or zone-level. Written for someone who has never
bought a flat. **Two entries exist to admit a limit rather than describe a
strength** — `live` says plainly that it is a hand-assigned judgement and not
built from flooding, water, green or air data, and `infra` says it covers
transport only and holds nothing on hospitals, schools, roads or power. If
either dataset ever arrives, those entries must change with it; if the entries
are ever tidied into confident prose without the data arriving, the tool is
lying to a buyer.

- **`AREAS`** (line ~1621) — zone heat map data, one entry per micro-market:
  `n` name, `z` zone, `cor` corridor, `ask`/`lo`/`hi` ₹ per sqft, `reg`, `py`
  price-growth %, `rent`, `ry` rental-yield-ish %, `c` confidence, `drv` the
  written read.
- **`SOC`** (line ~1363) — the listings directory, one entry per society:
  `n` name, `a` micro-market, `z` zone, `b` builder, `t` tier 1–3, `age` years
  (0 = new build), `st` status, `seg` possession segment, `sz` 2BHK sqft,
  `psf` ₹/sqft, `lo`/`hi` indicative price, `rent`, `c` 1 = seen listed,
  `r` the written read.

`SOC` also carries provenance, which is hand-maintained and must never be
invented or averaged:

- `src` — `rera` | `builder` | `broker` | `portal` | `derived`
- `asOf` — `YYYY-MM`, when the figure was captured
- `rera` — the registration number, or `pending`, or `unknown`
- `inventory` — `available` | `limited` | `soldout`
- `conflict` — optional note where sources disagree
- `possReg` / `possTarget` — registered and marketed possession, where they differ
- `lowconf` — set where the whole entry is disputed

Do not average broker figures. Store the authoritative number, and where
sources disagree store the observed range plus a `conflict` note. An averaged
figure nobody quoted cannot be defended to a buyer. A `rera` figure must read
as visibly more trustworthy in the UI than a `broker` one.

`AREAS` additionally carries the Knight Frank layer, written by
`tools/kf_merge.py` from `data/knight-frank.md` — do not hand-edit these
either, re-run the script:

- `kfZone` — Knight Frank's own five-zone classification. **This is not `z`.**
  It is the join key for their zone-level figures and nothing else; `z` still
  drives every filter, map and zone preference. Nine areas differ between the
  two, Sarjapur Road most consequentially (ours East, theirs South).
- `qts` / `qtsPrev` / `zoneUnsold` — quarters-to-sell and unsold stock for that
  KF zone, H1 2026 and H1 2025. **Zone level, never area level.** `qtsThin`
  marks a zone whose sample is too small to read as signal (Central, 187 units).
- `growth26` / `growth25` / `trend` / `kfSeries` — the tracked price readings.
  Only the 17 locations Knight Frank follow have them; everywhere else they are
  `null`, and must stay `null` rather than being filled from portal data.
- `growthPortal` — the portal figure `py` held before the merge. On those 17,
  `py` is now the Knight Frank reading.
- `dataTier` — `verified` | `portal`. `scorePrecision` says the same thing for
  the investment score, and always names the zone-level inputs.
- `pipeScore` 0–10, with `pipeTop`, `pipeList` and `pipeNote` — the committed
  pipeline. All four are generated from the `PROJECTS` table in
  `tools/kf_merge.py`: one row per project, carrying `kind`, `status`, an
  opening date and the areas it serves. The scorer reads those rows and names
  no line, corridor or area in any branch, so new kinds are added as rows
  rather than as code.

  `pipeScore` takes the best project at full weight, decays every further one
  on a log curve, and maps the total through a saturating curve rather than
  clipping it:

      raw   = value(best) + Σ value(rest) / log2(rank + 2)
      score = 10 × (1 − exp(−raw / PIPE_SOFT))

  Status is a multiplier, not a band, because a funded project and an
  announcement are not the same thing: building 1.0, funded 0.85, approved
  0.5, planned 0.25, announced 0.1. The curve approaches 10 without reaching
  it, so nothing piles up at a ceiling — a flat half-credit with a hard clip
  put Hebbal's five projects level with a single Blue Line station.
  `PIPE_SOFT` is set so the strongest a single project can be lands at 8.0,
  leaving the top fifth of the scale for areas with more than one. It is
  emitted into the app as `KFPIPESOFT` so the "funded or building only"
  re-score cannot drift from the stored value.
  Operational track is **not** pipeline — it is scored separately as current
  infrastructure — and a project whose opening year has passed drops out of
  the pipeline for the same reason. `--as-of=YYYY` reproduces an earlier run
  or looks ahead.

  **Three honesty rules ride on the rows, not the renderer.** Approved and
  funded never share a colour, because that gap is where buyers get hurt. A
  row may override its status wording with `says`, which is how the Red Line
  always reads "state approved, awaiting Union Cabinet" and the Business
  Corridor always carries the 2007 date it was first promised. A project
  without a published date never displays an implied one.

- `infraNow` 0–10 and `infraNowNote` — what already serves this area, the
  mirror of `pipeScore` and on the same curve, so a line carrying passengers
  can be compared against one that is only promised. Built from the
  operational metro graph in `data/enrichment.json` (every line with a station
  within 3.5 km, valued by how close its nearest station is) plus any project
  row whose opening date has passed. **Road has no independent signal in this
  data** — the only road figures we hold are drive times, and those already
  drive commute and tech-park access, so using them again here would count the
  same minutes three times. That gap is left visible rather than faked.

- `kfLevel` — whether Knight Frank's *level* may set this area's cost basis.
  A growth rate survives a geography mismatch; a price level does not. Their
  "Lavelle Road" reading is the dearest street in the CBD, not our whole
  MG Road / CBD micro-market, so that row keeps its growth, trend and chart
  but is barred from the basis. `LEVEL_MISMATCH` in the merge script holds the
  exceptions with the reason, and the panel states it.

The cost basis is one rule on a quality ladder, not two footings — the same
shape as `dataTier`. `basisOf()` is the only thing that decides it, and every
price-derived figure reads it: the yield, the cost of a flat, budget fit, the
sweet-spot price cut.

  tier 1  Knight Frank transacted midpoint   (the 17 they track, minus
          `kfLevel` exceptions)
  tier 2  blended registered + asking        (everywhere else)

Where tier 1 applies the panel shows whether our own registered deeds
corroborate it — Hebbal's ₹11,535 against their ₹11,400 is within 1%, and
that agreement is the evidence for the ladder. Where they diverge, or where no
registered deeds exist to check against, the panel says so rather than letting
the better source pass unexamined.

Knight Frank track transactions rather than listings, so where they and a
portal figure disagree, theirs wins. The three-year chart draws from `kfSeries`
only: an area without one gets an empty state, never a portal line, because a
chart implies a measured series.

Both arrays also carry fields written by `tools/enrich.py` — do not hand-edit
these, re-run the script instead: `lat`/`lng`, `dt` (drive times per hub, as
`[free-flow min, peak estimate min, road km]`), `mx`/`mkm` (nearest metro and
straight-line km). `SOC` additionally carries `geoPrecision`: `'building'` where
Nominatim resolved the complex itself, `'area'` where it fell back to the
micro-market's coordinates. Area-level entries are labelled as approximate in
the UI; keep that distinction visible.

## Data we do not have

Written down because a brief has already asserted some of it as held, and the
scoring quietly inherited the assertion. **Nothing in this list exists in this
repo.** If a factor description, a weight table or a commit message implies any
of it, that text is wrong and should be corrected rather than the data assumed.

### Flood risk — now partially held, and deliberately not scored

Area-level flood risk **is** held, from BBMP's flood-vulnerability lists and
KSNDMC mapping as reported May 2026. It lives in `FLOOD` and `SOCFLOOD` and is
a **warning layer, not a scoring factor**. Do not move it into a weight table.

The reason is resolution. Our geography is area level and real flood risk is
street level, so scoring it would mark down every flat in Mahadevapura equally
including the ones on high ground, and a few points buried inside a score of
79 hides the fact a buyer most needs to see. Tolerance is personal too — an
eighth-floor flat is not a ground-floor one with basement parking.

Three levels, and they must stay distinguishable:

- **Area** — automatic, from the published lists. 11 high, 6 medium, 7 low,
  62 not listed.
- **Project** — hand-researched, and only where a society sits in a pocket the
  lists actually name. Everything else is left **unmarked rather than
  inheriting its area**, because a tower on high ground inside a flood-prone
  micro-market is not flood-prone.
- **Address** — a checklist and **never a number**. We hold no elevation, no
  drain coordinates and no lake-bed boundaries, and a computed address-level
  score would look authoritative while being a guess.

`unknown` must always read as *absence of evidence, not evidence of safety*.
Most of the city has never been surveyed, and a quiet "low" there would be the
most damaging thing this tool could say.

**What is still missing for address level:** elevation data, the vulnerable
storm water drain list as coordinates, and lake-bed and rajakaluve boundaries.
Those three would make per-building assessment possible. Until then the
checklist is the honest answer.

### The remaining highest-leverage acquisition

**Bus route density and frequency.** This tool models metro and car and
nothing else, and buses are how most of Bengaluru actually moves. That gap
silently penalises every area that is well served by bus and has no station,
and it is most of the city — `infra` recognises one operational line for 42
areas, two for 17, and none at all for 27.

### Everything else

Two factors carry weight on thinner evidence than their names suggest, and
their `FACTOR_DOC` entries say so in the UI, with a visible **editorial, thin
coverage** tag on `live` wherever it appears:

- **`live` (liveability)** is a hand-written regex table, `LOCQ`. It matches
  41 of 86 areas; the other 45 take the default and are therefore identical to
  each other. It is editorial judgement, not measurement, and carries 4% on
  both scores for that reason.
- **`infra` (transport running today)** covers operational metro only. It was
  two factors, metro access and a broader infrastructure score, which was one
  thing counted twice under two names; they are merged.

What would make them real, none of which we hold:

| Missing | Would feed | Why it matters |
|---|---|---|
| Hospital and school density, with travel time | `live`, `infra` | The two amenities families actually choose on |
| Elevation, drain coordinates, lake-bed boundaries | flood layer | The three inputs that would make address-level flood assessment possible; area level is held already |
| Water supply — Cauvery connection vs tanker dependence | `live` | A recurring monthly cost and a hard constraint in the outer east and north |
| Air quality by locality | `live` | Separates arterial-adjacent stock from interior stock |
| Green cover and tree canopy | `live` | Much of the difference between an old and a new micro-market |
| Footpath and street-lighting quality | `live` | Whether the area is walkable, which is most of day-to-day liveability |
| Bus route density and frequency | `infra` | How most of the city actually moves; we model only metro and car |
| Operational road quality — carriageway width, service roads | `infra` | The project rows hold exactly one road, and it is unbuilt |
| Operational employment nodes with headcount | `infra`, `tech` | `tech` uses drive time to three fixed hubs, not where jobs actually are |
| Power and water outage frequency | `live` | Routinely decides a purchase and appears in no listing |

Two notes on filling these in:

- **Do not substitute a proxy that restates a factor we already weight.**
  Distance to the CBD looks like a maturity proxy for `live`, but commute
  already carries 24% for a CBD worker, so it would count the same kilometres
  twice and inflate whatever the buyer already said mattered.
- **Do not derive coverage from `SOC`.** Society count per area looks like a
  density signal and is a record of where research effort went: 52 of 86 areas
  hold no society at all, and the top of the list is Sarjapur Road and
  Whitefield because that is where the search was focused. Using it would
  encode our own sampling as a property of the city.

## Design tokens and the component library

Every colour, radius and spacing value resolves to a custom property on
`:root`. The previous ledger palette is **gone** — all 462 references were
rewritten and the alias block deleted. These are the only names:

    --bg --card --tile --primary --primary-2 --pop --tint
    --ink --muted --slate --line --line-soft --accent
    --warn-bg --warn-fg --risk-bg --risk-fg --good-bg --good-fg --band-mid
    --grad-bg --grad-primary --shadow-primary

The ground is **never flat**: `--grad-bg` is a three-stop gradient and `--bg`
is only its fallback. Primary buttons, score badges and bar fills all carry
`--grad-primary`, the same 140deg ramp, so they read as one family; a flat
`--primary` fill on any of those breaks that.
    --r-card 22 --r-tile 15 --r-seg 12 --r-chip 999
    --s-screen 18 --s-cards 14 --s-in 14 --tap 44

Two fonts: **Manrope** carries every readable word, **Space Grotesk**
(`--label`) is for caps labels and badges only and never for body text.
Nothing interactive goes under `--tap`.

Every foreground/background pair in use clears 4.5:1. The tightest is the
info dot's ink on the ground at 4.75. Re-check with the ratio helper before
introducing a new pair, and darken the foreground rather than shipping
something short.

### Class names collide the same way function names do

`.pl` was already the pipeline chip, with a dashed border and 5px of padding.
A new panel label reusing the name inherited both and came out 42px tall
instead of 13, on four panels at once. **Grep for a class before you style
it**, exactly as for a function. That one is now `.mpl`.

### One file, no module scope

Every function in this file is a global, and **a declaration later in the file
silently overwrites an earlier one of the same name**. There is no warning and
no error — the earlier one simply stops existing, and the symptom is a feature
that renders nothing.

**Grep before naming any new top-level function.** This has already cost
three names:

- `sourceFooter` — a component was shadowed by the society provenance footer
  declared further down. Renamed to `srcFooter`.
- `badge` and `chip` — the components are shadowed by `const` locals inside
  `tunedChips()` and a results renderer. Harmless because those two functions
  do not need the globals, but do not call `badge()` or `chip()` from inside
  them without renaming the local first.

### Icons

One function, `uiIcon(name, tone, box)`, inline SVG, no font and no library.
Every glyph is 20x20, 1.7 stroke, round caps and joins, no fill. 24 of them.
`box` false draws the glyph bare for use inside a button.

**The tone carries meaning and must not be mixed for looks**: `nav` for
navigation and actions, `data` for data and attributes, `warn` for caution,
`risk` for risk, `good` for verified.

### The info system

Long explanation does not live on the page. A small `i` sits immediately after
the term and opens a sheet — a bottom sheet on a phone, a popover that points
at its button on desktop.

`infoDot(key)` places one; `TERMS` holds the 19 entries; `openTermSheet` fills
it. Every sheet has **five parts in the same order**, and the shape is the
point — a reader learns it once:

1. the term  2. **one sentence**  3. value here / weight / level tiles
4. what it does not cover  5. source, date and a link to the long method

**Part 2 is capped at one sentence.** Anything needing two belongs behind the
method link. `FACTOR_DOC` still holds the long form and the sheet links to it.

The dot is an 18px ring with a 44px reach from a pseudo-element — **do not
grow the visible ring to meet the tap target**. The sheet joins the existing
`registerOverlay` registry with `top:true`, because registration order is not
stacking order and Escape must reach the topmost thing.

### Component library

Nine builders. **Render through these rather than hand-rolling markup**, so a
radius or a weight changes in one place. They take plain values, return HTML
strings, hold no state.

| Builder | Notes |
|---|---|
| `metricTile(label, value, sub)` | tile background, caps label, 20px/800 value |
| `badge(text, tone)` | `ok` \| `neutral` \| `warn` \| `risk` |
| `segmented(options, active, attr)` | active is a white pill on a tile track |
| `chip(text, active, icon, attr)` | active is `--primary` |
| `scoreBadge(n)` | rounded square, coloured by band |
| `factorBar(label, value, max, right)` | label, track, value |
| `calloutCard(tone, title, body)` | `warn` \| `risk` \| `ok` |
| `srcFooter(src, asOf)` | **not** `sourceFooter` — see below |
| `explainButton(topic, mode, label)` | the "i", 44px reach around a 22px circle |

Two naming hazards, both live:

- `srcFooter` is deliberately not called `sourceFooter`. A provenance footer
  for a society already owns that name further down the file, and the later
  function declaration silently wins — the component returned nothing until it
  was renamed.
- `badge` and `chip` are also declared as **locals** inside `tunedChips()` and
  one results renderer. Those shadow the components within their own scope,
  which is harmless today. Do not call the global `badge` or `chip` from
  inside those two functions without renaming the local first.

### Score bands

Thresholds are unchanged; only the language is. `SCORE_BANDS` reads
80+ **Best available**, 60–79 **Worth a look**, under 60 **Needs a reason** —
"strong / steady / watch" read as verdicts on the place, and with nothing
reaching 80 a city of "watch" sounded like a broken scale rather than a slow
market. `investBand()` keeps its `[label, colour]` shape because several call
sites destructure it.

Every score is shown with a **rank** — `rankLabel(a, scorer)` gives "4th of
86". A number against an invisible scale tells a buyer nothing. The live
spread sentence stays as it is.

## The analytics screens

Three surfaces, all built from the nine components and all charted with
positioned divs — **no chart library, and nothing drawn that the data cannot
support**. Where a figure would have to be guessed, there is an empty state
saying so instead.

- The detail panel's **Score** and **Prices** tabs. Every factor carries the
  **actual value** under its bar, not only a 0–10 number, because "8.1/10"
  tells a buyer nothing on its own. The three-year column chart draws **only**
  where `kfSeries` exists: 17 of 86, and the other 69 get an empty state. Never
  fall back to portal data there — a chart implies a measured series.
  `locAnalytics(name)` survives as `showArea(name,'score')` for the call sites
  that want the breakdown directly.
- `renderTerminal()` — a fourth Explore mode, desktop only. Its filters live in
  `TERMF` and touch no global state, so nothing in Explore or Listings moves
  when they change. On a phone it says it is built for a wide screen rather
  than reflowing a scatter and a nine-column table into something unreadable.
- `kfZoneTable()` derives the Knight Frank zone figures from the fields already
  on `AREAS` rather than restating them as a second copy that could drift.
  It is **lazy on purpose**: an eager IIFE there reads `AREAS` inside its
  temporal dead zone and throws.

Every `FACTOR_DOC` entry carries a `not:` field — **what the factor does not
cover**. That section is as load-bearing as the others: it is where the tool
admits that commute is modelled rather than measured, that liveability knows
almost nothing, and that a high yield says nothing about vacancy.

## The intake

Seven questions for a live-in buyer, **five for an investor**. The flow is
derived from `iqList()` rather than a switch, so the progress dots, the back
button and the step count cannot drift from the questions actually asked.
`iqDef(key)` holds one definition per question; adding or reordering a
question means editing those two and nothing else.

Household, workplace and travel are live-in questions. The desk used to ask an
investor where their *tenants* would work and how those tenants would travel;
nobody buying a ₹1 Cr flat to let knows either, and the questions implied a
precision that does not exist. In their place is the one thing an investor can
answer — **income now, growth later, or both** — and it moves the weights in
`personalWeights()`, which is the only reason to ask it:

    income  yield +6, rent growth +4, asking-vs-deeds +2, price growth −8
    growth  price growth +8, yield −6, rent growth −4, asking-vs-deeds +2
    both    the standard investor weighting, unchanged

`personalWeights()`'s invest branch reads no workplace and no travel mode at
all. A hub stored from an earlier live-in session must not leak into an
investor's weighting now that the question is gone.

**What the goal moves.** `personalWeights()` drives `socFit`, so it changes the
project ranking. `areaFitFull()` reads the purpose too: an investor is scored
on `investTable()` — `W_INVEST`, tilted by their goal — with the `'invest'`
factor values and **no commute penalty**, because they do not live there.

    income  rent 19→24, liq 9→13, taken off growth 21→16 and pipe 15→11
    growth  growth 21→26, pipe 15→19, taken off rent 19→14 and liq 9→5
    both    W_INVEST untouched

Both tilts are integers summing to exactly 100, like the tables they come
from. `investScore()` is deliberately **not** tilted: it is the desk's
comparable number for every buyer, and the goal belongs to the personal fit.

Anything that states the weights has to read the table that was used, not the
one it was tilted from. `openScoreDoc(mode, goal)` takes the goal and shows
the tilted table with a callout naming the change; the personal-fit line on a
location's Score tab passes it. A sheet showing 21% beside a score computed on
26% is the stale copy the "reads the live table" rule exists to prevent.

### Screen zero: say it instead of filling a form

Before question 1 sits a screen that lets somebody describe their situation.
`IPHASE` is `'voice' | 'caught' | 'q'` and sits in front of `iStep` in
`renderIntake()`. It is offered once per session, never to somebody editing an
answer, and **never in a browser without SpeechRecognition** — that browser
gets the questions with one line saying voice needs Chrome, not a mic that
does nothing.

The microphone asks for permission **on the tap and never on load**. Handlers
are attached before `start()` so a `start()` that throws is still reported:
a blocked mic says so in `VERR` rather than sitting there.

`voiceExtract()` is **patterns only, and the screen says so**: a number
followed by cr/crore/lakh/lac/L, a few purpose phrases, the four hubs the desk
already measures, and timing words. Anything else is not understood and is not
claimed to be. The full transcript is stored in `INTAKE.voice` so a model can
read it properly later without asking anybody to speak again, and the caught
screen shows it verbatim.

After the caught screen, `nextUnanswered()` routes to the first question that
still has no answer, and `iNext` keeps skipping answered ones while `VCAUGHT`
is set. Somebody who said four things is not walked through all seven.

A 38px microphone sits in every section header. It opens a sheet that says
asking arrives with the next release and offers search instead — the
affordance now, the asking later. It hides its "set up by voice" button where
SpeechRecognition is missing.

An option tap writes the answer and re-renders in place. **Advancing is the
Continue button's job** — a mis-tap must never jump someone forward a screen.

### One way out, and somewhere to land

There is never both a Skip and an X on the same screen. `hasProfile()` decides
which one exists:

- **With a stored profile**, the X in the corner, and nothing else. They have
  somewhere to return to, so closing returns them there — the section
  underneath is untouched, so Market > Compare is still Market > Compare.
- **Without one**, no X at all. One named exit, **"Browse without answering"**,
  at the foot of screen zero and of question 1 only. Not "Skip": that implies
  losing nothing, and what is lost is every personalised thing downstream.
  After question 1 there is no exit, because they have started and Back is the
  way back. The review screen and the placard have none either.

Taking that exit lands on Explore in the **generic state**: all 86 ranked on
the investment score, the mode control relabelled **"Ranked for everyone"**
rather than "Your 5", and a card at the top saying so with a way back into the
questions. `genericCard()` **does not close**. Without it the screen is just a
list and nothing explains why it is not the five they were promised. Answering
the questions is what removes it.

Between the last question and the placard sits the **profile confirmation**.
Nothing is recommended until the person agrees we understood them, each row
jumps back to its own question, and the "what this rules out" card counts the
exclusions off the same filters the shortlist uses rather than estimating.

Two placards from one data set: `placardLive()` and `placardInvest()`. Both
carry rank out of 86 and a flood tier where one exists, and both link to the
weights through a card that **reads the live table** rather than restating it,
so a weight change cannot leave stale copy behind.

## Navigation

Five sections in `SECTIONS`, wired by `data-sec` on `.sb-item` to `<section
class="sec" id="sec-<name>">`:

**Home · Explore · Market · Listings · Your activity**

The fifth section is still `shortlist` in every id, hash and `SUB` key — only
its label changed. Do not rename the key; persistence and deep links ride on it.

`goSection()` is the single entry point. It sets `SEC`, toggles the `.sec`
containers, calls `paintPanels()`, then calls that section's renderer. Add a
case there if a new section needs one.

Sub-state is split across three variables, which is deliberate and is the thing
most likely to trip you up:

- `SUB` is keyed by section — `SUB.explore`, `SUB.shortlist`, and `SUB.guide`.
  `SUB.guide` is the open article, not a section of its own.
- `EXMODE` is Explore's mode: `five` | `position` | `discover`. `search`,
  `momentum` and `terminal` are still accepted by `setExploreMode()` and
  reachable, but are not on the three-button control.
- `MSUB` is Market's sub-tab: `moving` | `compare` | `coming`. It is outside
  `SUB` because `SUB` is keyed by section and the guide already owns a key
  inside Shortlist.

### Panels

A `<section class="panel" data-sec data-sub>` is shown by `paintPanels()`
toggling `.on`. Three rules, not one:

- `data-sec="guide"` shows when Shortlist is on its `guide` sub-tab *and*
  `data-sub` matches `SUB.guide`. Guide panels are mounted into `#artBody`.
- `data-sec="market"` shows when Market is open *and* `data-sub` matches `MSUB`.
- everything else matches `SEC` and `SUB[sec]`.

Panels are relocated into their section at boot by the `put()` block. **Any new
market panel is picked up automatically** by
`put('section.panel[data-sec="market"]','sec-market')` — do not append one by
id. A panel left where it was authored will sit outside every `.sec` and never
appear, which is silent: `paintPanels()` will still give it `.on`.

Anything that changes `MSUB` must call `paintPanels()` as well as
`renderMarket()`. `renderMarket()` only fills `#marketPane`; it does not touch
the static panels beside it.

### Nothing is persistent except the nav

There is no masthead. A bar carrying the local-mode status, "Change my answers",
Settings and five counts used to sit above every section, which cost about a
third of a screen on all sixteen of them. Its pieces live where each one is
about:

- the profile and its Edit link — Home, as one pill
- the five counts and the progress bar — Your activity
- sharing status — the foot of Home, plus a green dot in the Home heading
  when a workspace is live. Amber and red stay at the foot, where the text
  that explains them is.
- Settings — the nav, Your activity, and the command palette

Resist putting anything back up there. If something seems to need to be on
every screen, it probably belongs on Home.

### Home answers "what next", not "what exists"

Five parts, in order: the profile pill, one gradient hero, your three areas,
what moved, the sharing foot. There were four counter tiles as well; they
restated Your activity, which has its own nav item and its own sub-tabs, and
the hero already names the state in words. `nextAction()` picks the hero
from state and returns `{state, line, cta, go}` — four states, and each one
names an action rather than describing the situation:

    empty      nothing tracked          → Explore
    tracked    tracked, none visited    → the route plan
    visited    visited, none shortlisted→ Your activity
    short      something shortlisted    → that property, with checks outstanding

### Where things live

Explore is the three modes and nothing else. It is not a page to scroll.

- Market owns every full-city table and all market commentary.
- The guide owns prose that teaches rather than ranks — including the returns
  arithmetic and why the portals disagree.
- Shortlist owns the costs, legal checks, negotiation and the guide articles.

Two screens showing the same 86 rows is the failure mode this structure exists
to prevent. Before adding a list or a chart, check whether Market > Compare or
Explore > Position already carries it.

## Market is a dashboard, not a page

Market > Moving is an analytics surface and has a harder budget than any other
screen: **one screen at 375, no scroll.** Everything on it is a tap target and
nothing on it is long. The long content — the full chart, the ranked list,
how to read it, the source — lives in the sheet behind each tile.

One markup, two grids, breaking at **1024px**. The same DOM lays out as a
phone dashboard and as a twelve-column desktop one; there is no second design
and no second template:

    .mgrid    hero + four tiles   2 columns on a phone, 5 equal across the
                                  full width on desktop
    .mwide2   momentum quadrant   stacked on a phone; 7 columns and 5 on
              + ranked gap bars   desktop, quadrant at least 270px tall
    .mhalf    flood, supply,      3 across on a phone showing their headline
              zone health         only; 3, 5 and 4 columns on desktop with
                                  the charts

A dashboard is not prose, so `#sec-market` drops the 820px reading width on
desktop. The header carries the title, the sub-tabs, the zone filter, the
period selector and Export on one row: `marketCtl()` renders into `#mktCtl`
inside the header, not on top of the pane, and clears on the other sub-tabs.

**Mobile minimums, which are floors and not targets:** 14px tile padding,
19px value, 9.5px label at .07em, 9px gaps, every tappable tile at least
64px, the quadrant at least 104px with no circle under 21px. When all of that
would not fit, **a panel moves into its sheet rather than shrinking below
them** — which is why flood, supply and zone health show one figure each on a
phone and keep their charts for the sheet behind them. The sheets are the
same on both widths.

Both widths measure **1.00 screens**: 812px at 375×812, 800px at 1280×800.
Anything added to either has to come out of something else.

`.mdesk` is the one panel that is desktop-only — the ranked asking-over-deeds
bars, which on a phone are the hero's sheet rather than a second copy on the
dashboard.

`openMetricSheet(key)` builds every sheet, and each one has the same four
parts: the chart, the ranked list, a **Read it this way** line, and the source.
`METRICS` holds the titles. The sheets reuse `openSlide`, so they inherit the
dismissal registry; they are not a new overlay.

**The ranked 86 lives in exactly one place** — the `rank` sheet, reached from
Compare's "See all N ranked" and from the analytics panels. Compare itself is
pick-up-to-three with the same ten rows every time. Do not put a table of 86
on a tab again.

A period selector and a zone filter sit in the header on desktop. The period
genuinely re-reads `KFCITY`; the zone filter touches only the location-level
panels, and the header says so in a line, because a filter that silently fails
to filter the big numbers is worse than no filter.

Central is greyed in zone health and labelled with its unit count rather than
its quarters-to-sell, because 187 units cannot carry that figure. The same
rule governs the hero: below `FROTH_FLOOR` (5) locations with registered
deeds, **no median is shown at all**. The big slot carries words rather than a
percentage — at 23px a number is read before its caption, so "+43%" over two
locations would land as a finding whatever the sub-line said. The count is
stated, and the per-location gaps still appear in the sheet, because each of
those is a real observed figure; only the summary needs the sample. Absence
and thinness read differently: zero locations says no deeds are published. Flood sits
here as market exposure — a donut of the published tiers across the city. It
is the same data as the per-area warning doing a different job, and it is
still not scored.

## The detail panel

An area, a project and a locality all open in the same shell: a head that does
not scroll, a strip of five tabs, a scrolling middle, and an action bar pinned
to the bottom. Only `.so-body` scrolls — the head, the strip and `.so-actions`
sit outside it in the flex column, which is what keeps them put.

**Overview · Score · Prices · Coming · Risk**, always those five and always in
that order, so the shape is learned once.

`openPanel({kind, key, name, meta, tabs, actions, wire, wireActions, hash, tab})`
is the only way in. `tabs` is an object of five keys; a value may be an HTML
string or a function taking the body element, which is how the project's Prices
tab borrows the three calculator panels. A missing key renders an empty state
rather than a blank tab. `setPanelTab()` hands the calculators back before it
wipes the body — they are borrowed DOM, not copies.

Three builders fill it: `areaPanelTabs`, `socPanelTabs`, `locPanelTabs`.

- **Overview** — what the thing is. Three tiles, the commute block, and one
  dark "the one thing" card holding a single derived sentence (`oneThing`,
  `socOneThing`), picked in priority order: flood, then froth, then pipeline,
  then rent-against-price, then stage.
- **Score** — the factor bars with their real values. This is what the old
  "full read" panel was; `locAnalytics(name)` is now just `showArea(name,'score')`.
- **Prices** — the basis, the Knight Frank series or its empty state, and the
  comparison against the city median.
- **Coming** — the pipeline, and nothing else anywhere.
- **Risk** — flood, the address checklist, and zone supply and liquidity.

**Nothing may appear in two tabs.** This is the rule the panel exists to
enforce, and it has already caught three breaches: `commuteHTML` printed the
whole pipeline list inside Overview (it takes a `noPipe` flag now, and Coming
owns it), the asking-above-deeds gap was stated three times on one panel, and
`showArea` and `locAnalytics` were two panels restating each other.

Deep links carry the tab: `#/area/Hebbal/prices`, `#/soc/<id>/risk`,
`#/loc/<name>/overview`. `readHash` reads a third segment and `setPanelTab`
writes it.

A tap on a card opens **Overview**. `data-openanl` used to go to the full read;
it goes to the panel now, and a reader starts at the beginning.

## Screen length

No section should need more than about two screens of scroll at 375×812.
Measure it; do not estimate. Where a screen runs long, the cause is almost
always a second copy of something rather than genuinely dense content — find
the duplicate rather than shrinking type.

A detail-panel tab has its own budget: **about 1.2 screens**, measured as
`#soBody.scrollHeight / 812`. Over that and something belongs in another tab or
behind a fold. **Market > Moving has the hardest budget of all: 1.0.**

Known and accepted exceptions: **Explore > Your 5** (~2.65 — five cards at
about 230px each), **Listings** (the full directory of 106), the long-form
**guide articles**, and **Home** at ~1.36. Screen zero fits one screen with no
scroll, and must stay that way.

Market's head is the sub-tabs and the microphone on one row, with the heading
visually hidden and the section's top padding cut to 18px. Adding anything to
it costs the dashboard its one-screen budget: the header mic alone put Moving
over until the row was shared.
A calculator opened from a project's Prices tab is its own screen and is far
over — which is why none of the three opens until it is asked for.

### Folding is the tool of last resort, and only for method

Where a panel runs long the first question is what is duplicated. Only once
that is answered does anything fold, and then only method and checklists, never
a finding: the peak-time estimate note, the basis explanation, the five flood
checks, the footer disclaimer. Each `<details class="foldnote">` keeps the load-
bearing words on the summary line — "Peak times are modelled, not measured" is
the warning, so it stays visible and the arithmetic folds.

Fixed chrome is charged to every screen, so it is worth guarding. The only
thing that persists is the nav — a 65px fixed bar at the bottom on a phone, a
rail on desktop. Everything else fixed is an overlay that is off-screen or
`pointer-events:none` until opened. `.main`'s bottom padding is that bar's
clearance and nothing else; it was 92px for a 65px bar, which charged 27px of
nothing to all sixteen screens.

The footer disclaimer is folded behind a `<details class="foldnote">` whose
summary still carries the warning — keep the warning on the summary line if
you touch it. Market's own `<h1>` is visually hidden rather than deleted: the
nav item already says Market in the same glance, and the dashboard has to fit
one screen.

## How to verify

Verify features through the user path — real click and input events, asserting
the rendered DOM — not by calling the underlying function directly. Several
bugs have shipped because a function tested correct while its wiring was
broken.

A ranking is only meaningful if the top result is actually good. Where every
candidate scores badly, say so explicitly rather than presenting a sorted list
of bad options.

Where a round touches layout but not logic, digest the scores before and after
and prove them identical rather than asserting it. Hash every area's
`sweetScore`, `investScore`, `areaOverall`, `areaFitFull`, `investFull`,
`pipeFor`, `sweetSpotScore`, `liquidityScore`, `corridorScore`, `metroScore`,
`growthOf`, `yieldOf`, `pipeScore`, `infraScore`, and every society's
`priScore`, `locScore` and `priParts`. Run it against `git show HEAD:index.html`
served beside the working copy, not against a remembered number — the digest
only means something if both sides ran the same script.

## After any change

Confirm all of the following before reporting the work done:

1. `index.html` still opens standalone from the filesystem, with no server.
   Lazily-fetched data will not load over `file://` — check the app degrades to
   its stated fallback rather than breaking.
2. The browser console is clean — no errors.
3. Every section still renders when opened — all five, both of Explore's other
   modes, all three Market sub-tabs, every Market tile opening its sheet, and
   every guide article. All five panel
   tabs on an area, on a project and on a locality, reached by clicking, with
   the head and the action bar staying put while the middle scrolls.
4. Local mode still works with no `#cfg` in the URL.
5. No section has grown past about two screens at 375×812, and no panel tab
   past about 1.2, bar the accepted exceptions above.
6. All four of Home's hero states, by creating each state rather than by
   reading `nextAction()`.
