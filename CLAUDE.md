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

### 4. Maps: Leaflet + OpenStreetMap only

If a map is added, use Leaflet with OpenStreetMap tiles. **Never Google Maps** —
it requires a billing account, which defeats the point of a file anyone can open.
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

## Data

Two arrays hold the domain data. Keep their shapes consistent when editing.

- **`AREAS`** (line ~1621) — zone heat map data, one entry per micro-market:
  `n` name, `z` zone, `cor` corridor, `ask`/`lo`/`hi` ₹ per sqft, `reg`, `py`
  price-growth %, `rent`, `ry` rental-yield-ish %, `c` confidence, `drv` the
  written read.
- **`SOC`** (line ~1363) — the listings directory, one entry per society:
  `n` name, `a` micro-market, `z` zone, `b` builder, `t` tier 1–3, `age` years
  (0 = new build), `st` status, `sz` 2BHK sqft, `psf` ₹/sqft, `lo`/`hi`
  indicative price, `rent`, `c` 1 = seen listed, `r` the written read.

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
