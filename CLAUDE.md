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
same registry and differ only in how heavily each factor counts. A factor
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

Two factors currently carry weight on thinner evidence than their names
suggest, and their `FACTOR_DOC` entries say so in the UI:

- **`live` (liveability)** is a hand-written regex table, `LOCQ`. It matches
  41 of 86 areas; the other 45 take the default and are therefore identical to
  each other. It is editorial judgement, not measurement.
- **`infra` (current infrastructure)** covers operational metro only. It is
  close to a restatement of metro distance under a broader name.

What would make them real, none of which we hold:

| Missing | Would feed | Why it matters |
|---|---|---|
| Hospital and school density, with travel time | `live`, `infra` | The two amenities families actually choose on |
| Flooding history by locality | `live` | The single largest downside risk in Bengaluru, and invisible in price until it happens |
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

## Tabs

Seventeen tabs, wired by `data-t` on `nav.rail button` to `#p-<name>` panels:
`brief`, `map`, `heat`, `areas`, `visits`, `photos`, `compare`, `resale`, `uc`,
`money`, `yield`, `negotiate`, `prices`, `verify`, `plan`, `sources`, `setup`.
Some re-render on activation in the tab click handler — add a case there if a new
tab needs it.

## How to verify

Verify features through the user path — real click and input events, asserting
the rendered DOM — not by calling the underlying function directly. Several
bugs have shipped because a function tested correct while its wiring was
broken.

A ranking is only meaningful if the top result is actually good. Where every
candidate scores badly, say so explicitly rather than presenting a sorted list
of bad options.

## After any change

Confirm all of the following before reporting the work done:

1. `index.html` still opens standalone from the filesystem, with no server.
   Lazily-fetched data will not load over `file://` — check the app degrades to
   its stated fallback rather than breaking.
2. The browser console is clean — no errors.
3. Every section still renders when opened.
4. Local mode still works with no `#cfg` in the URL.
