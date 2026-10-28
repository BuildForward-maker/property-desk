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

### 3. Three external scripts, and no more

The Supabase client from jsdelivr:

```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
```

Leaflet, by the exception in rule 4. And **one analytics tag**, injected by
`startAnalytics()` rather than written into the head, so that empty constants
mean no tag at all. (Google Fonts stylesheets are also loaded and are fine to
keep.) Do not add other libraries, frameworks or CDN scripts without being
asked.

`ANALYTICS_SRC` and `ANALYTICS_SITE` sit beside `SB_URL`. Both empty is a
supported state and is what ships until they are filled; a `file://` open
never loads the tag whatever they say, because a page opened from the
filesystem has no business calling anything.

**`logEvent()` is the only caller of the vendor's function**, so there is
exactly one place to read to know what leaves the page. It is not called
`track`: `track` is the tracked-properties store, and naming the function that
collided and took the whole script down with it, which is rule "grep before
naming" doing its job the hard way. It cannot throw: no
constants, a blocked script or an ad blocker all leave it a no-op. Props are
filtered to strings and numbers, and **every value is written by hand at the
call site**; nothing is ever read off a record, which is the mechanical
reason no event can carry a name, an email or a flat.

Eight events, and the list in the privacy article has to stay equal to the
list in the code:

    section view        {section}   which of the five
    intake started
    question completed  {n}         the number, never the answer
    intake finished
    lock sheet shown    {lock}      the kind of lock, never the flat
    sign-in started
    sign-in completed               only when a link was just followed,
    sign-in failed                  read off the URL before Supabase
                                    cleans it, so a stored session on an
                                    ordinary load does not count as one
    feedback sent       {rating,section}   never the body

**Adding an event means editing the privacy article in the same commit.** The
article names the events and claims the list is complete; an event that is
not in it makes that a lie.

### 4. Maps: Leaflet + a keyless basemap

For maps, use Leaflet with a keyless raster basemap (currently Esri World Light
Gray Canvas + Reference labels). Never Google Maps, CARTO, or Stadia — all now
require an API key or billing account.

Leaflet's CSS and JS may be loaded from a CDN as an exception to rule 3.

### 5. Two public constants, and the hash still works

`SB_URL` and `SB_KEY` sit at the top of the script and name the backend this
copy talks to. **The anon key belongs there.** It is designed to sit in a web
page, it is not an admin key, and since rule 8 the policies behind it check
membership rather than `using (true)` — publishing it was unsafe before that
and is safe now. They are set, to project `xhzdnetooocjqumqjvun`, and that is
what makes the bare domain show a sign-in screen instead of dropping a visitor
into local mode. Emptying them restores the older behaviour exactly.

**Decode any key before committing it.** The middle segment must read
`"role":"anon"` and its `ref` must match the project ref in `SB_URL`. That one
check is the whole difference between publishing a public key and leaking an
admin one.

**The `service_role` key is the opposite and must never appear in this file.**
It ignores every policy.

Config still travels inside a link as `#cfg=<base64 json>` with `{u, k, w, n}`,
and **a link beats the constants**, so every link already sent keeps working,
including one pointing at a different project. `CFGSRC` records which won:

    link   #cfg= in the hash or the query. writeCfgToUrl() keeps it in the
           address bar, because that address is the credential-shaped thing
           somebody was given.
    baked  the constants. The address bar is left alone — somebody who typed
           the bare domain keeps a bare domain, and the share link is built
           on demand in settings instead.
    none   neither, so there is no backend at all.

A baked config carries **no workspace**. Which one a person belongs to is not
knowable until they have signed in, so `CFG.w` is empty until
`enterWorkspace()` adopts their first membership or creates one.

**Opened as a file there is no gate**, whatever the constants say. A magic
link has to come back to an address Supabase will redirect to and `file:///`
is not one, so a sign-in screen there could never complete. That case says so
and runs locally, which is rule 1 intact.

### 6. Local mode must keep working

`MODE` is `'local'` or `'shared'`. When no config is present, the Supabase library
fails to load, the connection check in `initSupabase()` throws, **or nobody is
signed in**, the app falls back to local mode and remains fully usable. Preserve
this. Every Supabase call must be guarded (`if(MODE!=='shared')return;`) and
wrapped so a failure degrades quietly instead of throwing.

Signing out is not a downgrade to a broken app, it is local mode. So is
declining to sign in at all. The sign-in screen's own exit says so in words:
"Browse without an account".

### 12. Admin is a condition, not a portal

One section in the same file, `AUTH.isAdmin`, read from `profiles.role` on
sign-in. A second portal means two codebases drifting apart, or a routing
split in a 780KB file.

**Be honest about what the hiding achieves: nothing.** This code ships to
every user and is readable in view-source. `AUTH.isAdmin` decides whether a
nav item is drawn and whether `goSection('admin')` is allowed through, and
that is all it decides. The protection is RLS: `is_admin()` and
`profiles_admin_read` run in the database, so a non-admin reading `profiles`
from the console gets their own row whatever they do in the UI. **Never build
anything here that depends on the UI being hidden.**

**There is no control that grants or revokes the role.** A button that makes
somebody an admin is a button that can be found and misused. Promotion is a
deliberate SQL statement. The People tab displays the role, it does not edit
it, and `saveProfile()` carries the existing role through its upsert so a
profile save cannot quietly demote anybody.

Three sub-tabs, built from the existing table, card, badge and callout
components. There is no admin design language and there must not be one.
Health says "Nothing looks wrong" in a sentence rather than showing four
zeros, because four zeros make a reader count them.

**Two things the schema does not have yet**, both rendered honestly rather
than faked:

- `feedback` has no read column, so "mark as read" is a list of ids in
  `desk_prefs` under `fb_read`. That is per workspace, not per row, and the
  one line that fixes it is in SETUP.md.
- `profiles` has no last-seen column, so that cell is a dash and the table
  says why underneath it. A derived "last seen" from the activity feed would
  have been a guess wearing a timestamp.

### 13. How a feature ships live but hidden

`AUTH.isAdmin` is the mechanism. One condition around the thing, deleted when
it goes public. **No flag system, no cohorts, no user-facing beta toggle.**

A toggle invites somebody to opt in, and somebody who opts in is braced for
roughness and forgives it. We want the confusion of a user meeting a rough
feature cold, because that confusion is the signal we are after, and a beta
label spends it. Ship it to admins, watch, fix, then delete the condition.

### 9. Browsing reads everything and saves nothing

Somebody should be able to judge the product before handing over an email, so
without an account the whole of Explore, Market, Listings, every detail panel,
the guide, all seven questions and the placard work fully. What an account
buys is the work surviving the tab, so the things that save are the things
that ask: tracking, the status and visit fields, notes, scores, target dates,
the legal checklist and Compare.

`requireAccount(line)` is the only gate, and `KEEP` holds one line per action
saying what would be kept. The control **stays visible and enabled-looking**:
a greyed-out button teaches nothing, and a wall in front of the product
teaches less. The tap is what explains the cost, once, in `#keep`, which is
registered `top:true` so it sits above a detail panel it was opened from and
Escape reaches it first.

**`canSave()` is `signedIn() || AUTH.state === 'off'`.** Where there is no
backend at all there is nothing to sign in to, and saving locally is the whole
product, so nothing is gated there. Gating it would be asking for an account
that cannot exist, against rule 6.

Every handler that writes returns **before mutating**, and the ones bound to a
form control re-render so the control snaps back. A guard placed after the
mutation would gate the save and keep the change on screen, which is the worst
of both.

**What is locked, in full.** Eleven call sites and three surfaces:

    track short status visit notes score target   the board and the panels
    checks                                        the legal checklist
    compare                                       Your activity > Compare
    export                                        the only lock in settings
    five                                          Explore's Your 5 tab
    placard areas|projects|locations              the four behind the first

**What is deliberately not locked, and why.** The whole of Market: three
sub-tabs, all ten metric sheets, the ranked 86 and Coming. That openness is
the evidence the product knows something, and taking it away takes away the
reason to sign up. Listings, Explore's Position and map, every detail panel,
the guide and all seven questions are open for the same reason. Export is the
one locked thing on that side, because it is a file somebody takes away.

**Explore's Your 5 keeps its tab**, with a small lock on the label, because
hiding it would hide what an account is for. `fiveLockCard()` fills the left
column; Position, the map and the rest of Explore sit beside it, so it is a
card in one column and not a wall. The button reads "Answer 7 questions"
before the questions and "Sign in to see your five" after, and the line under
it changes with it: "Takes four minutes" is true of the questions and not of
signing in.

**The top 20 is a tab of its own where Your 5 is locked**, and that is not
decoration. "Browse without answering" exists to hand somebody a working
product without the intake, so it cannot land them on a card asking them to
answer the questions they just declined. Signed out with no answers,
`skipIntake()` and `goSection('explore')` both land on `ranked`: the top 20
of 86 with `genericCard()` above it, and Your 5 one tap away with its lock.

One implementation, two homes. `fillGeneric20(host)` is called by
`renderGeneric20()` into `#gen20Pane` for the Ranked tab, and by
`renderYourFive()` into `#fivePane` for the signed-in-without-answers case,
where the Your 5 tab relabels itself "Ranked for everyone" and there is no
second tab beside it. Two controls for one column would be the duplication
the restructure exists to remove.

The glyph is sized to 13px in the tab. At its native 20px it made every
Explore mode one to two pixels taller, which the height sweep caught.

### The badge has three shapes and the third is empty

    browsing   --warn pill, "Browsing. Nothing is saved." + Sign in
    signed in  --good pill, "Saved to your account.", for eight seconds
    after      nothing at all
    failure    --risk pill, and it stays, because that one needs acting on

A permanent "you are signed in" is noise. `CONNTIMER` is cleared on every
`setConn` so two calls in quick succession cannot leave a stale pill behind.

### 11. The placard gives the first result and locks the rest

Answering all seven questions is free and so is the first answer, because a
locked screen that shows nothing teaches nothing about whether the product is
any good. The top card renders in full, as `fiveCard` rather than the smaller
`loccard`, so it carries the things that make a result worth having: the rank,
what the budget buys with its bar, the commute with its superlative, and the
risk callout if there is one. A `Best fit` badge sits above it.

The rest sit under `lockWrap()`: `blur(3.5px)` at `opacity:.5`, which leaves a
card you can see the shape of and cannot read, with `placardLocked()` centred
over them. Live hides four areas and four projects, investment hides two
locations, and the copy counts in words off the actual array rather than
being written out.

**The map takes the same cut.** Its pins carry the area name in a tooltip and
open the area on a tap, so a locked placard is passed `areas.slice(0,1)`.
Blurring four cards while naming them on the map above would be theatre.

**Answers survive, and so does the place in the flow.** The button writes
`placardback` and saves the intake before opening the gate; the magic link
reloads the page, and `boot()` reads the flag and reopens the intake at
`resultsStep()`. Somebody who signs in from the lock lands on the complete
placard, never on Home and never at question one. The flag is cleared on the
way in, including when they arrive signed in without finished answers.

### 10. The mobile number is asked after the shortlist, not at the gate

Optional at sign-up, and deliberately not promoted later to required. An
unverified field in a sign-up form is where people stop, and there is no SMS
provider yet, so asking at the gate would cost sign-ups to collect something
nothing can use. `renderMobAsk()` puts one line at the top of Your activity
once `shortlistCount() > 0`, there is no mobile on the profile, and it has not
already been asked. Dismissing it sets `mobasked` for good.

### 8. Membership, not the link

The anon key is still public in the hash, and that is now safe, because the
policies check membership rather than `using (true)`. The link names a
workspace; it does not grant it. A signed-in person who is not a member of the
workspace in the link is told so.

`AUTH.state` is the one place that decides what a person sees:

    off     no #cfg at all, so there is nothing to sign in to: local mode,
            no gate, the whole app. This is the file:// case and rule 1.
    out     there is a backend and nobody is signed in: local mode, gate
    new     signed in, profile not written: the profile screen
    in      signed in, profile saved, a member: the app, shared
    denied  signed in, not a member of this workspace: said plainly

Three things ride on this and must not be undone:

- **The claim is the migration.** Rows written before accounts carry a
  workspace and no user, so tightening the policies would strand them. A
  workspace with no members at all may be claimed once, by whoever holds its
  code (`ws_unclaimed()` in the SQL); after that only a member can add anybody.
  It is on the profile screen, the first screen an existing user sees, not
  buried in settings. **Do not remove it** without a migration that assigns
  every existing workspace an owner first.
- **Nobody is signed up on somebody else's behalf.** "Add by email" is a
  lookup. A miss says so and stops, because creating an account for a person
  who has not asked puts their address in a table they never agreed to.
  The lookup is the `user_id_by_email` RPC, **not** a select on `profiles`:
  a policy letting any signed-in person read profiles by email would hand
  them every name and mobile in the table to find one uuid. The function is
  security definer and returns a uuid or null and nothing else. Its argument
  is named `email`, so the call is a single literal `rpc`; a schema that
  renames it breaks loudly here rather than quietly reporting that nobody has
  an account. Signed out the function answers `PGRST202`, which is correct —
  it is granted to `authenticated` only.
- **The magic link is implicit flow, deliberately.** PKCE keeps its verifier
  in the browser that asked, and people read email on their phone and work on
  a laptop. The cost is that the redirect comes back with `#access_token=` in
  the hash, which would overwrite `#cfg=`; `emailRedirectTo` therefore carries
  `?cfg=` in the query, `readCfg()` reads the hash first and the query second,
  and `writeCfgToUrl()` puts it back in the hash as soon as the session is in
  hand. The canonical link shape is unchanged.

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

Three fonts. **Manrope** carries every readable word, **Space Grotesk**
(`--label`) is for caps labels and badges only and never for body text, and
**Instrument Serif** (`--serif`) carries exactly two things: the intake
question at 42px on desktop, and the fact card's claim line at 23px. It is
not a UI face and must not spread; if a third place wants it, the question is
why that place is trying to sound like the question.
Nothing interactive goes under `--tap`.

Every foreground/background pair in use clears 4.5:1. The tightest is the
info dot's ink on the ground at 4.75. Re-check with the ratio helper before
introducing a new pair, and darken the foreground rather than shipping
something short.

### The page is in standards mode

`<!doctype html>` is the first line of the file. Without it the page spent its
whole life in quirks mode, which is where the percentage-height bugs came
from, and it also quietly withheld three things the stylesheet declares — all
of them inside tables, because quirks mode resets font properties and
line-height there.

Four rules now **state** what quirks mode used to do by accident, so the
layout does not depend on a parse mode:

- `table{line-height:normal}` — the tables were laid out against `normal`.
  Letting body's 1.55 in added about 2px to every cell line: 211px on
  Listings and 44px on Market > Compare.
- `.dd label small{display:block}` and `.artlist button small{display:block}` —
  the title-then-note pattern. As a block the note keeps the 1.5 that
  `small` asks for, instead of each of its lines being stretched to the row's
  own line-height. 111px on Legal, 15px on the guide list.
- `.field label:has(.hint){line-height:normal}` — a label carrying a hint is
  one dense two-part block.

**One difference was kept, deliberately.** `body` declares
`font-variant-numeric: tabular-nums lining-nums`, and quirks mode was denying
it to every table in the app — the one place a column of figures most needs
digits of equal width. With the doctype the numeric columns take about 3-4px
more and the auto table layout takes it from the prose column beside them, so
6 of 86 rows in the micro-market table wrap one extra line: Listings 12,210 →
12,286px at 1280, 14,476 → 14,480 at 375, and the brief's table +18.5px.
`table{font-variant-numeric:normal}` would undo it in one line; do not, and do
not remove the doctype to recover the pixels either.

Everything else measures the same to the hundredth of a pixel. Where
`documentElement.scrollHeight` reads 1px lower than it used to, the fractional
body height is identical and only the rounding changed.

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
| `metricTile(label, value, sub)` | tile background, caps label, 20px/800 value. label takes markup |
| `badge(text, tone)` | `ok` \| `neutral` \| `warn` \| `risk` |
| `segmented(options, active, attr)` | active is a white pill on a tile track |
| `chip(text, active, icon, attr)` | active is `--primary` |
| `scoreBadge(n)` | rounded square, coloured by band |
| `factorBar(label, value, max, right)` | label, track, value |
| `calloutCard(tone, title, body)` | `warn` \| `risk` \| `ok`. title takes markup |
| `srcFooter(src, asOf)` | **not** `sourceFooter` — see below |
| `explainButton(topic, mode, label)` | the "i", 44px reach around a 22px circle |

### Two attribute names, one action, and every host must bind both

`data-openanl` and `data-openarea` both mean "open this area's panel". Seventeen
places write one or the other; fifteen bind them. **A host that binds only one
name silently kills every card written with the other** — no error, no console
line, the card simply does nothing.

It has happened once, on the screen where it cost most. `placardLive()` renders
its top card through `fiveCard()`, borrowed from Explore, while the four under
it go through its own `areaCard()`. `fiveCard` carries Explore's attribute, the
placard's wiring knew only its own, and so the **one card the lock gives away
for free** was the single dead card in the app. Every other card on that screen
worked, which is what made it look like a problem with one area rather than
with one binding.

Two rules follow:

- **Bind both names together**, `[data-openanl],[data-openarea]`, in every host
  where a card can land, and read the value as `dataset.openanl||dataset.openarea`.
- **Never narrow a card binding to a class list.** `.fcard[data-openanl],
  .loccard[data-openanl]` was written in the ceiling round to avoid
  double-binding the near-miss rows; it is the same trap one step away.
  `[data-openanl]:not(.cmrow)` says what is meant and survives the next card.

Verifying this is a click, not a read: a listener cannot be inspected, so the
only proof is to click every card on every surface and assert the panel that
opened. 337 clicks across fourteen surfaces, all 86 areas twice over, is about
four minutes of harness time and is worth running whenever a render path moves.

### One escaping rule, and it is the call site's job

**A builder escapes nothing a call site composes. The call site escapes its own
data.** `factorBar`'s label, `metricTile`'s value and sub-line and
`calloutCard`'s body already worked this way, which is why every factor row
carries a working "i".

`metricTile`'s **label** and `calloutCard`'s **title** were the two exceptions,
and they were exactly the two slots a call site wants to put an `infoDot` into.
Four of them shipped the markup as visible text on live panels — the Registered
deeds tile on all 86 areas, the high flood-risk callout, and both `srcTag`
provenance labels on every project, which quietly undid the rule that a RERA
figure must read as more trustworthy than a broker one. A button that is text
is never an element, so those sheets could not be opened at all.

The same asymmetry bit in the other direction: the two call sites that pass
real data into those slots escape it themselves, so they were escaped twice.
`Post & Telegraph Layout` read as `Post &amp; Telegraph Layout` on its locality
panel. Seven of the 1,791 localities carry an `&` or an apostrophe; no area
name does, which is why the project panel's `esc(ar.n)` never showed it.

Before adding an argument to a builder, decide which side escapes it and keep
the whole library on one answer. A scanner over every call site is four lines
of Python and would have caught all four.

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

### The funnel is the progress indicator, and the count is real

The dot row is **gone, not hidden** — `grep iqdots` returns nothing. In its
place, `iqFunnel(i)` draws seven blocks, one per question, each the height of
how much of the field is still in play. `funnelSteps(cur)` computes them, and
`funnelLines(i)` writes the two lines beneath: the count, then why it moved.

Four rules the component carries, each of which cost a pass to find:

- **Height follows the answer, not the position.** `st.done`, never
  `state==='past'`. Going back to question three must not shrink the four
  already answered behind it.
- **A question nobody has reached is not answered**, whatever `iqDef` says.
  `zones` and `work` report `done:true` before anybody has seen them and the
  rest carry a default, so an ungated funnel is full before the first tap.
  `reached = INTAKE.done || i<=cur` is the gate; editing a stored profile is
  the other case, and there everything is answered.
- **The lines read the current screen's answer**, not the previous screen's.
  They walk back from `i` to the last question with a cause, so picking a
  budget updates the count under it rather than one screen later.
- **Question one says nothing has been ruled out yet**, whatever it is
  answered, because it rules nothing out and a zero there reads as a finding.

`.fstep.cut` is the step that actually narrowed the field; its number takes
`--warn-fg`, the same amber as the waterfall's bite, and is declared **before**
`.fstep.now` so the question you are standing on still reads as the one you
are standing on.

**Two things reduce the area count: budget, and the commute ceiling.** Zones
are a preference by `ZONE_PENALTY`, the timeline narrows projects rather than
areas, and the rest move weights, so those say what the question *did* ("This
changes the weighting, not the shortlist") rather than printing a cut of zero.
Every count comes off `areaStages()`, which is the predicate the five are
filtered by, so a funnel line cannot claim a filter the shortlist does not
run.

**The funnel is what "Question 2 of 7" used to say.** On a phone the words are
visually hidden and the numbered blocks carry it, which is where the screen
pays for the two lines beneath the options; the desktop column has room for
both and keeps them. `.iqbody:has(.fnlsay){padding-bottom:0}` for the same
reason: the 29px under the options existed to clear the sticky footer, and the
count now stands in that gap rather than the screen paying for it twice.

On desktop the funnel takes **a row of its own** and Back is absolutely
positioned in the overlay's margin. In the row, Back cost the screen 54px and
moved the funnel 54px between question one and question two, which is the
alignment the row exists to hold.

### The waterfall on the review screen

`areaWaterfall()` folds over `areaStages()` rather than listing the filters a
second time, so a filter added to the five appears here without anything being
kept in step by hand. A stage that removed nothing is shown at full width with
a dash; a stage that is not switched on is not drawn at all, because a labelled
bar tells a buyer that filter ran.

`.wrow` sets `line-height:1.3`. At body's 1.55 the three stages cost the
review screen 15px it does not have.

### Corner marks, not a background

`cornerMarks()` returns two inline SVGs, mounted by `mountCornerMarks()` into
every `[data-cmarks]` host at boot — the intake overlay and Home. A crosshair
circle at the corner, two rules running in and three or four ticks along them;
110px top-left, 130px bottom-right, 1px `--primary` at .3 and .26,
`aria-hidden`, `pointer-events:none`, `z-index:-1`, and **nothing below
1024px**: a phone has no empty corners to decorate.

`z-index:-1` paints them above the host's own background and below everything
in flow, which is the point. `#sec-home` therefore takes `position:relative`
and `z-index:0` in the same media query, so the negative layer stays inside it
rather than escaping to the page. Nothing fixed lives inside `#sec-home`, which
is what makes that stacking context safe.

**On Home the top-left mark is mostly covered, and that is the layout, not a
bug.** The header band and the hero card reach that corner: 84 of 784 sampled
points are clear, in a 14px strip between them. The bottom-right one reads.
Lifting it above the band would put decoration over content, and moving it
would not be a corner. The intake, which is where the empty space actually is,
shows both.

### The commute ceiling is a filter, and the buyer sets it

Question six asks two things, because how you travel and how far you will go
are one decision and an eighth question would have made the flow longer to say
less. `IQ_CMAX` holds the four bands, `INTAKE.commuteMax` holds the answer and
`CMAX_DEFAULT` is `'60'`: a profile written before this round has no answer and
reads as an hour, which the review row labels **as a default** so nobody is
held to a number they never chose. `cmaxBlock()` renders it and **hides itself
where no workplace is set**, because a ceiling with nothing to measure from is
a control that does nothing. Each band carries how many areas survive it, so
the choice is made against the consequence.

**It is a filter, not a weight, and it does not touch the score.** This is the
same shape as budget, and the reason matters: `areaFit` answers how well a
place suits this person, and the ceiling answers whether they would make the
journey. Zeroing the score would conflate the two and would tell a buyer that
Devanahalli is a bad area rather than a far one. The digests prove it: across
all four states `areaFit` and `socFit` are **byte-identical** to before, while
the personal area and project *rankings* both move.

    commuteCeiling()   null for an investor, null with no workplace, else the
                       chosen minutes. Those two nulls are not the same as 'any'
                       and must stay separate in the copy.
    commuteMinsOf(x)   peak minutes on the chosen journey, worse of two hubs,
                       which is exactly how commute is already scored
    overCeiling(x)     minutes past it, 0 inside it, 0 when unknown

**An unknown journey is never excluded.** Absence of a drive time is absence of
evidence, which is the rule the flood layer keeps.

Four places filter on it and all four read the same predicate: `topAreas`,
`socGroups` (a project is scored from its own coordinate, so it takes the
ceiling directly rather than inheriting its area's verdict), `rankedAreas`
**only when `RANKMODE` is `you`**, and `areaStages()` for the funnel and the
waterfall. **`investScore`, `investFull`, `priScore` and `sweetScore` must
never see it** — they are the comparable numbers every buyer reads on every
panel, and Ranked overall is their list.

**What the ceiling removes is shown, not swallowed.** `commuteMisses()` returns
the areas that pass everything else and fail only the commute, nearest first;
`commuteMissHTML()` is the collapsed line under the five ("7 more fit
everything except the commute. The closest is Sahakar Nagar at 63 minutes, 3
over your hour") with the gap per area and the next band one tap away through
`raiseCeiling()`. It shows **through the placard's lock**, because those are
areas the desk is not recommending and rule 9 is that browsing reads
everything. `ceilingVerdict(a)` says the same thing on an excluded area's
Overview, next to the minutes it is about and nowhere else.

**Under three survivors is not a shortlist.** `ceilingThinHTML()` replaces the
ranking with the three closest misses and the next band up, which is CLAUDE.md's
"a ranking is only meaningful if the top result is actually good" applied to a
filter the buyer can undo. `topAreas` still backfills to five, and every
backfilled card names the filter it broke through `fcardWhyIn()` — the budget
backfill had been silent about it, and a second silent reason would have made
the five unreadable.

**At the hour it rarely reaches the five, and that is the honest reading.**
Across 96 hub/budget/travel combinations the 1-hour default changes the top five
areas in **none** of them and the top five projects in 6; 45 minutes changes 6
and 19; 30 minutes changes 56 and 66. The commute penalty already pushes a
74-minute area to 82nd of 86, so what the default buys is a ranked list that
cannot contain it and a line that names what went, not a different top five.
Do not "fix" that by tightening the default.

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

Taking that exit lands on Explore in the **generic state**: the **top 20** on
the investment score, the mode control relabelled **"Ranked for everyone"**
rather than "Your 5", a card at the top saying so with a way back into the
questions, and "See all 86 ranked" into the one ranked sheet. Twenty, not
eighty-six: somebody who skipped the questions has the least frame for what
they are reading, and a screen of 86 rows is the thing the restructure exists
to prevent. `genericCard()` **does not close**. Without it the screen is just
a list and nothing explains why it is not the five they were promised.
Answering the questions is what removes it.

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
- `EXMODE` is Explore's mode: `five` | `ranked` | `position` | `discover`.
  `search`, `momentum` and `terminal` are still accepted by
  `setExploreMode()` and reachable, but are not on the control.
  **`ranked` is a tab only where `five` is locked**, which `paintExploreTabs()`
  decides and `setExploreMode` enforces by rewriting `ranked` to `five` when
  `canSave()`. `defaultExploreMode()` is what somebody lands on rather than
  what they left behind.
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

## Desktop layouts

Every section drops the 820px reading width at **1024px and up** except the
guide articles, which keep it: prose at 1068px is unreadable and line length
beats filling space. Before this, four sections floated in an 820px column
with 106px of dead space either side.

One set of markup throughout. Only the grid changes at the breakpoint, and
`matchMedia` appears exactly once (the Board, below) where a grid could not
express the difference.

    Home        1.65fr / 1fr — hero left, "what moved" right, three area
                cards across beneath. Source order is unchanged, so the phone
                is unchanged; the grid places them by row and column.
    Explore     400px left / map right, a persistent split. The left column
                scrolls on its own and the map is sticky, so changing mode
                never moves the map. **Map is not a mode here** — the toggle
                switches the left column between Your 5 and Position, and
                `setExploreMode` rewrites 'discover' to 'five' above 1024.
                A phone keeps all three.
    Listings    232px sticky filter rail / table. Clear at the rail's top, a
                live match count at its foot.
    Your        232px rail — counts as a 2x2, then the views vertically with
    activity    a divider after Route — and the panels fill the rest. The
                Board becomes three status columns.

**A bare `display:grid` on a section overrides `.sec{display:none}` and leaves
every section on the page at once.** Three rules did this and every page got
two to three screens taller before it was caught. Scope the display to the
open state: `#sec-explore.on`, `#sec-shortlist.on`, `#p-areas.on`.

The map panel is shown or hidden by `#sec-explore[data-mode]`, not by an
inline style, because a media query cannot beat an inline style. That flag is
also what lets the split keep the map up in all three modes. The mobile rule
uses `:not([data-mode="discover"])`, which is more specific than a bare
descendant selector, so the desktop override needs `[data-mode]` on it to win.

Rails use `position:sticky` and set **no `overscroll-behavior`**, so reaching
the end of a rail hands the scroll back to the page rather than trapping it.

**A grid cell is not a stack.** Two items placed in the same named area overlap;
two items given only a `grid-column` are auto-placed into successive *rows*,
which is how Listings ended up with a screen of white between its tabs and its
table and how Explore drew its tuned bar underneath its cards. A column that
holds more than one thing needs a wrapper — `.exleft`, `.lbody` — and the
wrapper is `display:contents` below the breakpoint so the phone never sees it.
Where a rail must span the body's rows, place every child explicitly by row
rather than relying on auto-placement.

### Copy rules

**No em dashes in anything a reader sees.** Each one becomes the punctuation
the sentence actually wants: a comma for an appositive, a full stop where both
halves are independent clauses, a colon where it introduces what was just
announced. Code comments keep theirs, and a lone — in a table cell is a
"no value" placeholder, not prose. Never leave a double space behind one.

**The product is not 2BHK-only.** Copy says "a flat", "typical rent", "a
listing". Where a figure genuinely is a 2BHK figure it keeps the label and
says why: `AREAS.rent` and `SOC.sz` are 2BHK-only, so they read "2BHK rent,
the only size we hold rent data for". Never relabel a 2BHK number as if it
covered every size. Listings has no size filter and never did; the dataset is
2BHK-based, which is a data limit to state, not a filter to remove.

**An empty state says what is missing and why, and never implies fault.** The
sub-registrar publishing no figure for an area is a fact about the record, not
about the area, the seller or the buyer. "not published / none published here"
said the same thing twice and read as an accusation; it is now "Not available"
over "The sub-registrar does not publish a figure for this area". The same goes
for "not quoted" on a project. Where the gap is the tool's, the copy says so:
the voice screen's no-match state names the three patterns the matcher catches
rather than telling somebody that nothing they said counted.

**The foot of the page is one line.** Eleven px, muted, with an asterisk that
opens the full note as a sheet. The long version lives in `FULLNOTE`.

**A caveat names what is uncertain. A disclaimer covers the writer.** The foot
used to end "Nothing here is advice", which spends trust rather than building
it, and `FULLNOTE` opened by listing what its author is not qualified to be.
Both now say what the figures are, when they were captured, which ones are
estimates and which two sources disagreed, and then that a lawyer does the
title and a CA does the tax. If a line ever has to hedge, it names the thing
that is uncertain: "drive times are modelled, not measured" earns its place,
"this is not advice" does not.

### The map's box keeps changing under it

Leaflet measures its container once, and a container with height 0 renders
nothing and throws nothing. In the split the map has a box in every Explore
mode, so it can be created after boot, resized by a mode switch, by the nav
collapsing, or by the window. `mapKick()` builds it if it does not exist and
has real height, otherwise calls `invalidateSize()`; `mapKickSoon()` debounces
that behind a frame. It is called on entering Explore, on every mode change,
on nav collapse and on window resize. **Do not assume the map was built at
boot** — at boot the section is hidden and the container is 0 high.

### The nav rail collapses

`NAVMINI` toggles `body.navmini`, which takes the grid from 212px to 64px,
hides `.sb-lab` (visually, not from screen readers) and puts each item's name
on its `title`. The state is one key through the existing store. It exists
only at 901px and up; a phone uses the bottom bar and never sees the control.
Collapsing changes the map's width, so it calls `mapKickSoon()`.

The Explore filter card is borrowed DOM, like the calculators: `openFilterSheet()`
moves it into the slide-over and `returnFilters()` hands it back, so there is
one filter card and its handlers keep working.

`renderWorkPins()` marks the chosen workplace on the map using the enriched
coordinate of the micro-market each hub sits in — our own data, never a
coordinate typed in from memory — and the tooltip says exactly that.

### Equal heights come from the grid

`min-height` on a card is a number somebody typed, and `height:100%` on a
stretched item clips anything taller than the row. Where cards in a row should
match, `align-items:stretch` on the row is the whole fix: say nothing about
the card's height and it sizes to its content while the grid equalises it.

### The scatter names only what can be read

Eighty-six labels on one plot is not a chart. Position gives a standing label
to the five the desk recommends and to everything in the cheap-and-climbing
quadrant; every other dot names itself on hover, on focus and on tap. If that
corner ever holds enough to overlap again, cut by score inside the quadrant
rather than turning the labels back on everywhere.

A label is centred on its dot, so a dot near either edge had its name sliced
by the plot's own `overflow:hidden` — 17 of 86, up to 57px, twelve of them
standing labels. A dot in the outer fifth now carries `edgeL` or `edgeR` and
anchors its label at the dot's centre instead, reading inwards. The threshold
is a percentage of the plot, so it holds at any width; check it with the
label's box against `.posplot`'s padding box, not by eye.

### Explore's left column scrolls on its own

`.exleft` is `max-height:calc(100vh - 170px)` with `overflow-y:auto`, so a
list of 20 areas in a 630px column is cut at the fold. Two things make the
cut read as "more below" rather than as a fault:

- **The scrollbar is drawn, not borrowed.** The engines this runs on use
  overlay scrollbars: `scrollbar-width`, `scrollbar-color` and
  `::-webkit-scrollbar` all measured `offsetWidth - clientWidth === 0`. The
  native one is hidden outright and `.exbar` draws a thumb instead, sized
  `clientHeight² / scrollHeight` and moved by `scrollTop / room`. It is a
  sticky, zero-height box pinned to the top of the scrollport whose `::after`
  is the thumb, so it costs no layout.
- **A 34px fade at the foot**, `.exfade`, which clears once there is nothing
  left to scroll (`.atend`). The chip row carries the same idea as a mask on
  its right edge, cleared the same way.

`exleftFade()` drives both and is called on scroll, on resize and from
`setExploreMode`. No `overscroll-behavior` is set, so reaching the end hands
the scroll back to the page.

### One prompt, not two

The non-personalised Explore used to stack the quiet `.tuneask` prompt, the
loud `genericCard()` and the "Top 20 of 86" line before a single area. The
loud one carries it on desktop and the quiet one is hidden there; a phone
keeps both, which is why the rule is scoped to the breakpoint rather than
deleted from `renderTuned()`.

### The header band has a gutter wider than its own corner

`.sechead` is a full-bleed white card with `margin:0 -18px` and
`border-radius:0 0 24px 24px`. Explore's right-hand controls — the search row
and the mode toggle — are justified to the content edge, so with the default
18px padding they ended exactly on the padding line, inside the 24px curve,
and read as sitting half outside the card. The desktop rule gives that band
26px on the right and bottom. Measure it as the gap between the control's box
and the band's border box, not against the content box, which is zero by
definition.

### The intake has two columns and a fact that is not about us

Above 1024 `.iwrap` becomes a grid: the question at a 540px cap on the left
with Continue at the foot of its column, and `.iqfact` on the right,
vertically centred. Below it the same markup is the phone screen it always
was, and `.iqfact` collapses to `.iffoot`, two muted lines and a 13px glyph
under Continue.

**The phone must not grow, and it did not.** Every question screen measures
exactly what it measured before the fact existed. The footnote is paid for
out of `.iqbody`'s bottom padding, which was 110px to keep the last option
clear of the sticky footer and is now 29px: a `position:sticky` footer
un-sticks into flow at the end of the scroll, so most of that padding was
never doing anything.

**`FACTS` holds seven, one per question, rotating, and none of them is about
this product.** A fact that sells the thing somebody is already using is an
advertisement wearing a figure, and it makes the other six less believable.
Each carries its source, and where the number is market convention rather
than a statute the source says so rather than dressing it up.

Two specificity traps, both hit while building this:

- `.iwrap h2` is (0,1,1) and beats `.iqh` at (0,1,0), so the desktop rule has
  to be `.iwrap h2.iqh`.
- The desktop `.iqbody{max-width:540px}` caps the placard too, because the
  placard is also an `.iqbody`. It is undone by
  `#intake .iwrap:has(.plgrid) .iqbody{max-width:none}`.

### The review is one card, not seven boxes

Seven floating `.pcard` boxes read as a form somebody has to check. One
`.rvcard` with hairline rows reads as a document about them, which is what it
is. Above 1024 the screen splits 0.78 / 1.42: the heading, the rules-out card
and the confirm button on the left, the card on the right, because the card
is the subject of the screen and gets the wider half.

**All seven rows must render whole.** A half-row at the bottom is worse than
no row, so measure `.rvrows` content against container rather than looking:
`flex:1 1 0` across seven rows rounded down and cost three pixels, which
clipped the last one invisibly. It is `flex:1 0 auto` now, and the screen is
bought back from the chrome around the rows rather than from the rows.

One component, one relaxed rule: `.rvwhy` is `nowrap` with an ellipsis on
desktop and wraps on a phone, where there is vertical room and the page
scrolls. Do not fork it.

Two more specificity traps, both from sharing `.iqbody` and `.iqh` with the
question screens, which is the same mistake the placard made:

- `#intake .iwrap:has(.rvgrid) .iqbody{max-width:none}` undoes the question's
  540px cap.
- `#intake .rvleft h2.iqh` is needed to beat `.iwrap h2.iqh`, which is
  (0,2,1) and sets the question's 42px.

**The rules-out card carries figures, not a sentence.** `rulesStats()`
returns a figure, a unit and a reason per filter, counted off the same
filters the shortlist uses. Nothing in it is written down.

**A zero is turned round rather than printed.** "0 of 86 areas excluded" is
the arithmetic; "All 86 areas reached" is the fact it produced, and it is the
same information read the way somebody wants to hear it. The claim stays
inside what the filter actually tested, which is a 1,000 sqft flat at each
area's own basis price across the 86 researched areas, not every address in
the city. Only the budget's area count does this; the project count prints
its number either way.

**There is no "next fact" teaser.** Teasing a fact is worse than showing one.
The rotation dots stay.

### The placard is a grid, and the map always names all five

Four children of `.plgrid`, **placed** rather than reordered: map and the
how-this-was-worked-out card and the projects in column 1, the ranked areas
spanning column 2. Below 1024 `.plgrid` is `display:contents`, so the phone
sees DOM order, which is the order it has always had.

**The locked placard shows all five pins, named.** It used to show one.
Hiding which five they are was the only thing the lock did that persuaded
nobody: seeing the shape of the answer is what makes the ranked detail behind
it worth signing in for, and the caption says exactly where the line is.
`renderPlacardMap()` is always passed the full five.

### The greeting, and the one rule the sub-line has to keep

`homeGreeting()` returns `{h, sub}` and is the only thing that writes either.

    signed out, or no name on the profile   "Your search", no sub-line
    a name, first session                   "Welcome, Arun"
    a name, since then                      "Welcome back, Arun"

    sub-line, before the questions          "Let's find where you should buy."
    sub-line, after them                    "Your search, day 12"

`GREETED` is read once at boot and written immediately, so the word is the
same for a whole session rather than changing the second time Home is opened.
The day count comes from the profile's own `created_at` and is **dropped
entirely when that is missing** — an invented day one is worse than no day.

`#homeSub` exists again after being deleted, and the rule that deleted it
still stands: it must not repeat the heading. "...and this becomes your
search" under a heading reading "Your search" is what that rule was about.

### Not done, and why

Listings was asked for a three-up card grid. It has no cards: it is a
sortable eleven-column table, and its sort control is the table head.
Building cards would either fork mobile and desktop or change the phone,
both of which the brief ruled out. The rail landed; the table kept its
width. Converting Listings to cards at both widths is its own round.

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
about 230px each) and its generic twin at ~2.81, **Listings** (the full directory of 106), the long-form
**guide articles**, and **Home** at ~1.36. Screen zero fits one screen with no
scroll, and must stay that way.

The intake's own measurements at 375x812: screen zero 812, Q1 812, Q2 1000,
Q3 846, Q4 812, Q5 897, Q6 **967**, Q7 812, review **1304**. The funnel round
held every one of these flat; the commute ceiling then bought Q6 155px for its
own control and the review 88px for the third waterfall stage and the longer
travel row. Both are new content rather than a second copy of something, and
both stay inside the two-screen rule at 1.19 and 1.61. Measure against these,
not against a remembered number.

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

### The console buffer is sticky

A browser console read reports everything that tab has logged since it opened,
including errors from pages that have since been navigated away from. It is
therefore **not evidence about the page currently loaded**, and comparing two
versions by loading them one after the other in the same tab proves nothing:
the older version's errors are still listed under the newer one.

Three `Uncaught SyntaxError` entries were reported as pre-existing on HEAD for
exactly this reason. They were three broken intermediate states of a string
surgery, left in the buffer by three reloads mid-edit; the file was reverted
and they stayed on screen for the rest of the session.

**Read the console in a tab opened for that one version**, and treat an entry
with no `file:line:col` as suspect: a genuine page error carries a source
location, an evaluated snippet does not.

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
