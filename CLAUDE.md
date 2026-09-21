# CLAUDE.md

Property Desk — a single-file research and tracking tool for a Bengaluru property
search. The entire app is `index.html` (~2,600 lines).

## Hard rules

These are not preferences. Breaking any of them breaks how the tool is used and
shared.

### 1. One self-contained file

`index.html` is the whole app. Never split it into separate `.js`, `.css`, or
ES-module files. Markup, styles, and scripts all stay inline in that one file.
New functionality goes into the existing `<style>` and `<script>` blocks.

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

- **`AREAS`** (line ~1621) — zone heat map data, one entry per micro-market:
  `n` name, `z` zone, `cor` corridor, `ask`/`lo`/`hi` ₹ per sqft, `reg`, `py`
  price-growth %, `rent`, `ry` rental-yield-ish %, `c` confidence, `drv` the
  written read.
- **`SOC`** (line ~1363) — the listings directory, one entry per society:
  `n` name, `a` micro-market, `z` zone, `b` builder, `t` tier 1–3, `age` years
  (0 = new build), `st` status, `seg` possession segment, `sz` 2BHK sqft,
  `psf` ₹/sqft, `lo`/`hi` indicative price, `rent`, `c` 1 = seen listed,
  `r` the written read.

Both arrays also carry fields written by `tools/enrich.py` — do not hand-edit
these, re-run the script instead: `lat`/`lng`, `dt` (drive times per hub, as
`[free-flow min, peak estimate min, road km]`), `mx`/`mkm` (nearest metro and
straight-line km). `SOC` additionally carries `geoPrecision`: `'building'` where
Nominatim resolved the complex itself, `'area'` where it fell back to the
micro-market's coordinates. Area-level entries are labelled as approximate in
the UI; keep that distinction visible.

## Tabs

Seventeen tabs, wired by `data-t` on `nav.rail button` to `#p-<name>` panels:
`brief`, `map`, `heat`, `areas`, `visits`, `photos`, `compare`, `resale`, `uc`,
`money`, `yield`, `negotiate`, `prices`, `verify`, `plan`, `sources`, `setup`.
Some re-render on activation in the tab click handler — add a case there if a new
tab needs it.

## After any change

Confirm all of the following before reporting the work done:

1. `index.html` still opens standalone from the filesystem, with no server.
2. The browser console is clean — no errors.
3. Every tab still renders when clicked.
4. Local mode still works with no `#cfg` in the URL.
