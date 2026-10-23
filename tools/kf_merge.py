#!/usr/bin/env python3
"""
kf_merge.py — one-time, run by hand. Merges Knight Frank Research figures
(data/knight-frank.md, India Real Estate H1 2025 and H1 2026) into the AREAS
array inside index.html.

Nothing here runs at page load. index.html keeps no build step; this script
edits the literal in place so the merged figures are plain inline data that
can be read and argued with.

Fields written onto every AREAS entry
-------------------------------------
  kfZone        Knight Frank's own five-zone classification. NOT our z.
                Ours drives the UI; theirs is only the join key for the
                zone-level demand figures below.
  qts           quarters-to-sell, H1 2026, ZONE level
  qtsPrev       quarters-to-sell, H1 2025, ZONE level
  zoneUnsold    unsold units in that KF zone, H1 2026
  qtsThin       true where the zone sample is too small to read as signal
                (Central: 187 units)
  growth26      12-month price growth, H1 2026 — verified areas only
  growth25      12-month price growth, H1 2025 — verified areas only
  growthPortal  the portal-derived py we carried before the merge
  trend         accelerating | steady | easing | decelerating | stalled | flat
  kfSeries      {y2024,y2025,y2026} midpoint of the KF range, verified only
  dataTier      'verified' (Knight Frank tracks it) | 'portal' (ours)
  infraScore    0-10, rubric below
  infraNote     one sentence saying why
  scorePrecision which inputs are area-level and which are zone-level

Part B also REPLACES py with growth26 on the 17 verified areas. The old value
survives as growthPortal. This is the point of the exercise: our figures were
not wrong, they were a year stale.

Infra rubric (judgement, not Knight Frank's — argue with it)

What sets the band is which committed project SERVES an area, and how soon
and how certainly it arrives. It is never how far the area is from a station
that happens to already be running: Hebbal and Yelahanka have no operational
station within 4.9 km and 10.0 km, and both score 10, because they sit on the
Blue Line 2B alignment, funded and dated June 2027. That is why Knight Frank
call North the fastest-growing corridor and why Yelahanka went from 8% to 18%.
A line a year out is a stronger signal than a mature line with nothing new
coming, and the bands say so.

The rule, in full:

    band  = the weight of the best project serving the area
          + 2 where one is running today AND another is funded within the
            near horizon
          + 1 per employment project serving it
          capped at 10

Weights come from status and opening date alone (see HORIZONS): running
today 8, funded and opening next year 10, within three calendar years 6,
beyond that or undated 4, approved but unfunded 2, nothing 0.

Every project is a row in PROJECTS and the scorer reads the rows. No branch
in it names a line, a corridor or an area, so the later round that replaces
this with a broader pipeline score — roads, tunnels, rail and employment
nodes — extends the table and the horizons, not the logic. `kind` is already
carried on every row for exactly that.

The one measured membership is an operational station inside the area
(OPERATIONAL_KM), because there distance IS the alignment. Everything else
lists the areas it serves, by name, so a mis-geocoded pin cannot move a
project to the wrong part of the city.
"""
import re, sys, os, datetime, math

# The year the horizons are measured from. Override with --as-of=YYYY to
# reproduce an earlier run, or to see what the bands look like further out.
AS_OF_YEAR = datetime.date.today().year
for _a in sys.argv[1:]:
    if _a.startswith('--as-of='):
        AS_OF_YEAR = int(_a.split('=', 1)[1][:4])

def load_enrichment():
    import json
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), 'data', 'enrichment.json'),
                encoding='utf-8') as f:
            return json.load(f)
    except Exception:                                       # noqa: BLE001
        return {}


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HTML = os.path.join(ROOT, 'index.html')

# ---------------------------------------------------------------- zone table
# Knight Frank Research, India Real Estate H1 2025 and H1 2026.
KFZONE = {
    'Central': dict(unsold=187,   qts=12.5, qtsPrev=13.0, thin=True),
    'East':    dict(unsold=22878, qts=4.9,  qtsPrev=3.8,  thin=False),
    'North':   dict(unsold=15408, qts=3.9,  qtsPrev=3.4,  thin=False),
    'South':   dict(unsold=33534, qts=7.4,  qtsPrev=6.1,  thin=False),
    'West':    dict(unsold=2291,  qts=3.2,  qtsPrev=2.9,  thin=False),
}

# --------------------------------------------------------------- price table
# KF location -> (our AREAS name, 2024 range, 2025 range, 2026 range,
#                 growth25, growth26, trend)
#
# LEVEL_MISMATCH names the mappings where Knight Frank's location is a smaller
# or dearer piece of geography than our micro-market. A growth RATE survives
# that mismatch — the street and the market around it move together. A price
# LEVEL does not: Lavelle Road is the dearest street in the city and our
# MG Road / CBD entry covers the whole CBD, so adopting their midpoint as the
# area's cost basis would tell a buyer a flat there costs 2.55 Cr when our own
# asking data says 1.35 Cr. These keep their growth, trend and chart; they do
# not set the basis.
# H1 2024 is Knight Frank's own back-calculation from the stated 12-month
# change, reproduced from the data file rather than recomputed here.
LEVEL_MISMATCH = {
    'MG Road / CBD': 'Knight Frank price Lavelle Road, the dearest street in '
                     'the CBD, not the wider micro-market this entry covers',
}
KFPRICE = [
    ('KR Puram',        'KR Puram',                 (5094, 9434),  (5400, 10000), (6400, 13400),  6, 20, 'accelerating'),
    ('Yelahanka',       'Yelahanka',                (4259, 8333),  (4600, 9000),  (6300, 12700),  8, 18, 'accelerating'),
    ('Tumkur Road',     'Tumkur Road / Peenya',     (3913, 6522),  (4500, 7500),  (5300, 10200), 15, 16, 'steady'),
    ('Marathahalli',    'Marathahalli',             (5217, 12174), (6000, 14000), (7310, 15500), 15, 15, 'steady'),
    ('Whitefield',      'Whitefield',               (5085, 9322),  (6000, 11000), (7100, 15200), 18, 14, 'easing'),
    ('Malleswaram',     'Malleswaram',              (7798, 15138), (8500, 16500), (9200, 17500),  9, 13, 'accelerating'),
    ('Hebbal',          'Hebbal',                   (6250, 12500), (6500, 13000), (7800, 15000),  4, 11, 'accelerating'),
    ('Hennur',          'Hennur Road',              (5743, 10297), (5800, 10400), (7000, 14000),  1, 10, 'accelerating'),
    ('Electronic City', 'Electronic City Ph 1',     (4587, 7156),  (5000, 7800),  (5700, 8600),   9, 10, 'steady'),
    ('Rajajinagar',     'Rajajinagar',              (9735, 17832), (11000, 20150),(11500, 23200),13,  9, 'easing'),
    ('Yeshwanthpur',    'Yeshwanthpur',             (7300, 12400), (7300, 12400), (7700, 14500),  0,  9, 'accelerating'),
    ('Bannerghatta Rd', 'Bannerghatta Road',        (5085, 9576),  (6000, 11300), (7600, 15500), 18,  7, 'decelerating'),
    ('Kanakapura Rd',   'Kanakapura Road',          (4200, 8800),  (4200, 8800),  (5300, 10100),  0,  6, 'accelerating'),
    ('Thanisandra',     'Thanisandra',              (4825, 10526), (5500, 12000), (5700, 13500), 14,  6, 'decelerating'),
    ('Sarjapur Road',   'Sarjapur Road',            (4310, 9483),  (5000, 11000), (5700, 11300), 16,  3, 'stalled'),
    ('Langford Town',   'Richmond / Langford Town', (15000, 22000),(15000, 22000),(15000, 22000), 0,  0, 'flat'),
    ('Lavelle Road',    'MG Road / CBD',            (21000, 30000),(21000, 30000),(21000, 30000), 0,  0, 'flat'),
]

# ---------------------------------------------------------- KF zone per area
# Knight Frank names anchor localities per zone (data file section 5).
# Anything they do not name is assigned to the nearest named anchor along the
# same corridor. The calls worth arguing with are marked.
KF_EXPLICIT = {
    # KF South, though our z says East - Knight Frank lists Sarjapur Road
    # under South and the whole corridor goes with it.
    'Sarjapur Road': 'South', 'Sarjapur town': 'South',
    'Harlur / Haralur': 'South', 'Carmelaram / Dommasandra': 'South',
    # KF North names Banaswadi. The Banaswadi-Kalyan Nagar-Kasturi Nagar
    # cluster goes with it, though our z calls it East.
    'Banaswadi / Kammanahalli': 'North', 'Kasturi Nagar': 'North',
    'Horamavu': 'North',
    # KF East names Old Airport Road; Indiranagar and Domlur sit on it, though
    # our z calls them Central.
    'Indiranagar': 'East', 'Domlur / Ulsoor': 'East',
}

# ------------------------------------------------------------ infra pipeline
# Every committed project is a row here, and the scorer reads the rows. It has
# no knowledge of any particular line, so a later round can add roads, tunnels
# and employment nodes by extending this table rather than by editing the
# scorer. Nothing below names a line in an if-statement.
#
#   kind    'rail' today; 'road', 'tunnel' and 'employment' are already
#           understood. Only 'employment' is scored differently (a bonus
#           rather than a band). When the broader pipeline score arrives and
#           a road should count for less than a line, that belongs in a
#           per-kind scale here, not in the scorer.
#   status  'operational' | 'funded' | 'approved'  (approved = not funded)
#   opens   'YYYY-MM', or None where funded and building with no published
#           date. Horizon is computed from this, never assumed from the name.
#   serves  the areas on the alignment, by name. '<measured>' means membership
#           is computed instead — see OPERATIONAL_KM.
PROJECTS = [
    dict(key='metro-now', kind='rail', status='operational', opens=None,
         label='Metro running today', serves='<measured>'),

    dict(key='blue-2b', kind='metro', status='building', opens='2027-06',
         label='the Blue Line Phase 2B airport corridor',
         serves={'Hebbal', 'Sahakar Nagar', 'Jakkur', 'Yelahanka', 'Bagalur',
                 'Shettigere', 'Devanahalli'}),

    # Funded and building; the source dates only 2B, so these carry no date
    # and fall to the undated band rather than being guessed at.
    dict(key='blue-2a', kind='metro', status='building', opens=None,
         label='the Blue Line ORR section',
         serves={'Marathahalli', 'Bellandur', 'Panathur / Balagere',
                 'Mahadevapura', 'KR Puram', 'HSR Layout'}),

    # Pink Line, Kalena Agrahara - Nagawara. Membership at the Nagawara end is
    # every entry within 2.5 km of it on our own coordinates. Kothanur and
    # Hennur Road only qualified once their geocodes were corrected.
    dict(key='pink', kind='metro', status='building', opens=None,
         label='the Pink Line',
         serves={'Nagawara / RT Nagar', 'Thanisandra', 'Thanisandra Main Road',
                 'Kothanur / Kothnur', 'Hennur Road',
                 'Frazer Town / Cooke Town', 'Sudhama Nagar',
                 # the southern half of this line IS Bannerghatta Road —
                 # Kalena Agrahara, Hulimavu, IIM-B, JP Nagar 4th Phase and
                 # Jayadeva are all on it, and both were missing
                 'Arekere / Hulimavu', 'Bannerghatta Road', 'JP Nagar'}),

    dict(key='sub-c2', kind='rail', status='building', opens='2028-12',
         label='suburban rail Corridor 2',
         serves={'Jalahalli', 'Yeshwanthpur', 'Mathikere / Sanjay Nagar',
                 'Tumkur Road / Peenya', 'Banaswadi / Kammanahalli',
                 'Kasturi Nagar', 'CV Raman Nagar', 'Horamavu', 'Hebbal'}),

    dict(key='sub-c4', kind='rail', status='building', opens='2029-03',
         label='suburban rail Corridor 4',
         serves={'Hosa Road', 'Kudlu / Kudlu Gate', 'Bommasandra / Chandapura',
                 'Bommanahalli', 'Doddaballapur Road', 'Hebbal', 'Yelahanka'}),

    dict(key='sub-c1', kind='rail', status='funded', opens='2030-03',
         label='suburban rail Corridor 1',
         serves={'Yelahanka', 'Devanahalli', 'Shettigere', 'Jakkur'}),

    dict(key='sub-c3', kind='rail', status='funded', opens='2030-03',
         label='suburban rail Corridor 3',
         serves={'Kengeri', 'Rajarajeshwari Nagar', 'Nagarbhavi', 'Mysore Road'}),

    # Phase 3 was cleared by the Union Cabinet, so it is funded; no opening
    # date has been published, which puts it in the undated band rather than a
    # guessed one. The ORR-west alignment runs JP Nagar 4th Phase to Kempapura,
    # which is why it reaches Hebbal at its northern end.
    dict(key='orange', kind='metro', status='funded', opens=None,
         label='the Orange Line (Phase 3, ORR west)',
         serves={'Hebbal', 'JP Nagar', 'Nagarbhavi',
                 'Tumkur Road / Peenya', 'Jalahalli'}),

    # Phase 3A, Sarjapur to Hebbal: approved by the state, awaiting central
    # clearance and unfunded. It ends AT Hebbal, which is what makes Hebbal a
    # three-line interchange rather than a single committed station.
    dict(key='red-phase3a', kind='metro', status='approved', opens=None,
         says='state approved, awaiting Union Cabinet',
         label='the Red Line (Phase 3A, Sarjapur to Hebbal)',
         serves={'Sarjapur Road', 'Sarjapur town', 'Harlur / Haralur',
                 'Carmelaram / Dommasandra', 'HSR Layout',
                 'Koramangala', 'Hebbal'}),

    # Bengaluru Business Corridor, the old Peripheral Ring Road. First notified
    # in 2007 and still not built: land acquisition has never completed and no
    # opening date has ever been published. It scores as planned, and the row
    # carries the date it was first promised so the age of the promise travels
    # with it wherever it is shown.
    dict(key='business-corridor', kind='road', status='planned', opens=None,
         label='the Bengaluru Business Corridor',
         says='planned, and first proposed in 2007 without ever being built',
         serves={'Nelamangala', 'Doddaballapur Road', 'Bagalur', 'Hoskote',
                 'Attibele / Anekal'}),

    dict(key='aerospace-park', kind='employment', status='building', opens=None,
         label='KIADB Aerospace Park',
         serves={'Devanahalli', 'Shettigere'}),
]

# ---------------------------------------------------------- pipeline score
# A funded project and an announcement are not the same thing, so status is a
# multiplier rather than a band. The ladder is deliberately steep at the bottom:
# an announcement is worth a tenth of the same project under construction.
STATUS_WEIGHT = {
    'building':  1.0,
    'funded':    0.85,
    'approved':  0.5,
    'planned':   0.25,
    'announced': 0.1,
}
# What the project would be worth to an area if it were certain.
TYPE_VALUE = {
    'metro': 10, 'rail': 7, 'tunnel': 6, 'road': 6, 'employment': 7,
}
# How each status reads in prose. A row may override with its own `says` where
# the bare word would flatter it — the Red Line is "approved" in the same sense
# the Business Corridor was approved in 2007.
STATUS_SAYS = {
    'building':  'under construction',
    'funded':    'funded',
    'approved':  'approved',
    'planned':   'planned',
    'announced': 'announced',
}
# A flat half-credit per extra project, hard-clipped at 10, threw away the
# thing worth knowing: Hebbal has five committed projects including a
# three-line interchange and landed level with a single Blue Line station,
# because one metro under construction already maxes the scale.
#
# So extras decay on a log curve — the second project is worth far more than
# the fifth — and the raw total is mapped through a saturating curve rather
# than clipped:
#
#     raw   = value(best) + SUM over the rest of  value / log2(rank + 2)
#     score = 10 * (1 - exp(-raw / PIPE_SOFT))
#
# The curve approaches 10 and never reaches it, so there is no clip and no
# ceiling for areas to pile up against. PIPE_SOFT is set so the strongest a
# single project can be — a metro under construction, raw 10 — lands at 8.0,
# which leaves the top fifth of the scale for areas that have more than one.
PIPE_SINGLE_BEST_AT = 8.0
PIPE_SOFT = 10.0 / math.log(1.0 / (1.0 - PIPE_SINGLE_BEST_AT / 10.0))


def project_value(pr):
    """What one project is worth before any area context."""
    return STATUS_WEIGHT.get(pr['status'], 0) * TYPE_VALUE.get(pr['kind'], 0)


def project_says(pr):
    return pr.get('says') or STATUS_SAYS.get(pr['status'], pr['status'])


# ------------------------------------------------- current infrastructure
# The mirror of pipeline: what already serves this area, scored on the same
# curve so the two are directly comparable. A resident gets credit for a line
# that is running, not only for one that is promised.
#
# It is built from the rows and the graph already here — no new dataset:
#   * every OPERATIONAL metro line with a station in reach, valued by how
#     close its nearest station is
#   * any project row whose opening date has passed, which is the same thing
#     one year later
#
# Road has no independent signal in this data. The only road figures we hold
# are drive times, and those already drive commute and tech-park access; using
# them a third time here would be counting the same minutes three times. That
# is a gap in the data, and it is left visible rather than faked.
INFRA_REACH_KM = 3.5


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def station_lines(html):
    """station name -> line, read from the MLINES table already in the app."""
    m = re.search(r'var MLINES=\{(.*?)\};', html, re.S)
    if not m:
        return {}
    return dict(re.findall(r"'((?:[^'\\]|\\.)*)':'(\w+)'", m.group(1)))


def infra_now(name, lat, lng, stations, lines):
    """What runs here today, 0-10, on the same curve as pipeline."""
    items, by_line = [], {}
    if lat is not None:
        for st in stations:
            d = haversine_km(lat, lng, st['lat'], st['lon'])
            if d > INFRA_REACH_KM:
                continue
            line = lines.get(st['name'])
            if not line:
                continue
            if line not in by_line or d < by_line[line][0]:
                by_line[line] = (d, st['name'])
    for line, (d, st) in by_line.items():
        prox = max(0.0, min(1.0, (INFRA_REACH_KM - d) / 3.0))
        items.append((TYPE_VALUE['metro'] * prox, '%s Line, %.1f km' % (line, d)))
    # a project whose year has passed is infrastructure, not a promise
    for pr in serving(name, None):
        if pr['serves'] == '<measured>' or not pr['opens']:
            continue
        if int(pr['opens'][:4]) < AS_OF_YEAR:
            items.append((project_value(pr), pr['label'].replace('the ', '')))
    if not items:
        return dict(score=0.0, note='Nothing runs here yet.')
    items.sort(key=lambda x: -x[0])
    raw = items[0][0]
    for rank, it in enumerate(items[1:]):
        raw += it[0] / math.log(rank + 2, 2)
    score = round(10.0 * (1.0 - math.exp(-raw / PIPE_SOFT)), 2)
    note = 'Served today by ' + ', '.join(i[1] for i in items[:3]) + '.'
    return dict(score=score, note=note)


def pipeline(name, mkm):
    """pipeScore and the rows behind it. Operational track is NOT pipeline —
    it is what exists today, and it is scored as its own factor. Everything
    here is forward-looking."""
    # A project whose opening year has passed is not pipeline any more — it is
    # infrastructure, and it is scored as current infra instead. Without this
    # the table would go on calling 2027 "under construction" forever.
    rows = [pr for pr in serving(name, mkm)
            if pr['serves'] != '<measured>' and pr['status'] != 'operational'
            and not (pr['opens'] and int(pr['opens'][:4]) < AS_OF_YEAR)]
    if not rows:
        return dict(score=0.0, top=None, list=[],
                    note='Nothing committed here, on any published plan.')
    rows.sort(key=lambda pr: (-project_value(pr),
                              pr['opens'] or '9999', pr['key']))
    best = rows[0]
    raw = project_value(best)
    for rank, pr in enumerate(rows[1:]):
        raw += project_value(pr) / math.log(rank + 2, 2)
    score = round(10.0 * (1.0 - math.exp(-raw / PIPE_SOFT)), 2)

    # A date is only ever shown where one has actually been published.
    when = (' opening %s' % _when(best['opens'])) if best['opens'] else ''
    rest = len(rows) - 1
    note = '%s is %s%s.' % (_cap(best['label']), project_says(best), when)
    if rest:
        note += ' %d other committed project%s serve%s this area.' % (
            rest, '' if rest == 1 else 's', 's' if rest == 1 else '')
    return dict(score=score, top=best, list=[pr['key'] for pr in rows], note=note)


# The one measured membership: an operational station inside the area, because
# there distance IS the alignment. Every other project lists the areas it
# serves by name, so a mis-geocoded pin cannot move a line across the city.
OPERATIONAL_KM = 2.0

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']


def _cap(label):
    """Labels are written to read mid-sentence ('the Pink Line'), so they need
    capitalising wherever one starts a sentence."""
    return label[0].upper() + label[1:] if label else label


def _when(opens):
    y, m = opens.split('-')
    return '%s %s' % (MONTHS[int(m) - 1], y)


def serving(name, mkm):
    """Every project that serves this area, measured or listed."""
    out = []
    for pr in PROJECTS:
        if pr['serves'] == '<measured>':
            if mkm is not None and mkm <= OPERATIONAL_KM:
                out.append(pr)
        elif name in pr['serves']:
            out.append(pr)
    return out



# ------------------------------------------------------------------ patching
def entries(blk):
    """Yield (start, end) of each top-level {...} entry, brace-matched so a
    stray brace inside a quoted drv string cannot split an entry."""
    i, n = 0, len(blk)
    while i < n:
        if blk[i] == '{':
            depth, j, q = 0, i, None
            while j < n:
                c = blk[j]
                if q:
                    if c == '\\':
                        j += 2; continue
                    if c == q:
                        q = None
                elif c in "'\"":
                    q = c
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        yield i, j + 1
                        i = j + 1
                        break
                j += 1
            else:
                return
        else:
            i += 1


def num(s):
    return ('%g' % s)


PIPE_START = '/* --- KFPIPE: written by tools/kf_merge.py, do not hand-edit --- */'
PIPE_END   = '/* --- end KFPIPE --- */'


def patch_pipeline(src):
    """Emit the project rows the UI needs to name a committed line. One table,
    the same rows the scorer reads, so a panel can never disagree with the
    score it is showing."""
    rows = []
    for pr in PROJECTS:
        if pr['serves'] == '<measured>':
            continue
        rows.append("'%s':{l:'%s',k:'%s',s:'%s',o:%s,says:'%s',v:%g}" % (
            pr['key'], pr['label'].replace("'", "\\'"), pr['kind'], pr['status'],
            ("'%s'" % pr['opens']) if pr['opens'] else 'null',
            project_says(pr).replace("'", "\\'"), project_value(pr)))
    order = ','.join("'%s'" % k for k in
                     sorted(STATUS_WEIGHT, key=lambda k: -STATUS_WEIGHT[k]))
    block = (PIPE_START + '\nconst KFPIPE={' + ',\n '.join(rows) + '};\n'
             + 'const KFSTATUS=[' + order + '];\n'
             # the curve constant, emitted so the app's "funded or building
             # only" re-score cannot drift from the stored pipeScore
             + 'const KFPIPESOFT=%.6f;\n' % PIPE_SOFT + PIPE_END)
    a = src.index(PIPE_START)
    b = src.index(PIPE_END) + len(PIPE_END)
    return src[:a] + block + src[b:]


def main():
    src = open(HTML, encoding='utf-8').read()
    stations = (load_enrichment() or {}).get('stations') or []
    lines = station_lines(src)
    print('metro graph: %d stations, %d named lines'
          % (len(stations), len(set(lines.values()))))
    a0 = src.index('const AREAS=[')
    a1 = src.index('\n];', a0)
    blk = src[a0:a1]

    price = {our: row for (_kf, our, *row) in
             [(k, o, y24, y25, y26, g25, g26, t) for (k, o, y24, y25, y26, g25, g26, t) in KFPRICE]}
    kfname = {o: k for (k, o, *_r) in KFPRICE}

    out, cursor = [], 0
    report = []
    seen = set()
    remerged = [0]
    pipe_hist = {}
    now_hist = {}
    for s, e in entries(blk):
        ent = blk[s:e]
        m = re.match(r"\{n:'((?:[^'\\]|\\.)*)'", ent)
        if not m:
            out.append(blk[cursor:e]); cursor = e; continue
        name = m.group(1)
        seen.add(name)

        # Re-runnable. The merged fields are always the trailing run of the
        # entry, so an earlier merge is removed wholesale before this one is
        # written, and py is put back to the portal figure it replaced. Without
        # this the script could only ever run against a pristine file, which is
        # no use when the rubric or the coordinates change.
        k = ent.find(",kfZone:'")
        if k >= 0:
            prior = re.search(r',growthPortal:(-?\d+)', ent[k:])
            ent = ent[:k] + '}'
            if prior:
                ent = re.sub(r'(,py:)-?\d+', r'\g<1>' + prior.group(1), ent, count=1)
            remerged[0] += 1

        z = re.search(r",z:'([^']+)'", ent).group(1)
        mk = re.search(r"mkm:([0-9.]+)", ent)
        mkm = float(mk.group(1)) if mk else None
        py = int(re.search(r",py:(-?\d+)", ent).group(1))

        kfz = KF_EXPLICIT.get(name, z)
        zi = KFZONE[kfz]
        la = re.search(r'lat:(-?[0-9.]+)', ent)
        ln = re.search(r'lng:(-?[0-9.]+)', ent)
        nw = infra_now(name, float(la.group(1)) if la else None,
                       float(ln.group(1)) if ln else None, stations, lines)
        pl = pipeline(name, mkm)
        pipe_hist[int(pl['score'])] = pipe_hist.get(int(pl['score']), 0) + 1
        now_hist[int(nw['score'])] = now_hist.get(int(nw['score']), 0) + 1

        add = [",kfZone:'%s'" % kfz,
               ',qts:%s' % num(zi['qts']),
               ',qtsPrev:%s' % num(zi['qtsPrev']),
               ',zoneUnsold:%d' % zi['unsold']]
        if zi['thin']:
            add.append(',qtsThin:1')

        if name in price:
            y24, y25, y26, g25, g26, trend = price[name]
            mid = lambda r: int(round((r[0] + r[1]) / 2.0))
            add += [',growthPortal:%d' % py,
                    ',growth26:%d' % g26,
                    ',growth25:%d' % g25,
                    ",trend:'%s'" % trend,
                    # the transacted range Knight Frank actually publish. Our
                    # lo/hi are portal asking quotes and are a different thing;
                    # the panel must never show one under the other's name.
                    ',kfRange:[%d,%d]' % (y26[0], y26[1]),
                    # whether their LEVEL may set this area's cost basis
                    ',kfLevel:%s' % ('0' if name in LEVEL_MISMATCH else '1'),
                    (",kfLevelWhy:'%s'" % LEVEL_MISMATCH[name].replace("'", "\\'"))
                        if name in LEVEL_MISMATCH else '',
                    ',kfSeries:{y2024:%d,y2025:%d,y2026:%d}' % (mid(y24), mid(y25), mid(y26)),
                    ",dataTier:'verified'",
                    ",kfLoc:'%s'" % kfname[name],
                    ",scorePrecision:'verified+zone'"]
            report.append((name, kfz, py, g26, g25, trend, int(pl['score'])))
            # Part B: the verified reading replaces the portal one.
            ent = re.sub(r"(,py:)-?\d+", r"\g<1>%d" % g26, ent, count=1)
        else:
            add += [',growthPortal:%d' % py,
                    ',growth26:null,growth25:null,kfRange:null,kfLevel:0',
                    ",trend:null,kfSeries:null",
                    ",dataTier:'portal'",
                    ",scorePrecision:'portal+zone'"]

        top = pl['top']
        add += [',infraNow:%s' % ('%g' % nw['score']),
                ",infraNowNote:'%s'" % nw['note'].replace("'", "\\'"),
                ',pipeScore:%s' % ('%g' % pl['score']),
                ',pipeList:[%s]' % ','.join("'%s'" % k for k in pl['list']),
                ",pipeTop:%s" % ("null" if not top else
                    "{k:'%s',l:'%s',st:'%s',says:'%s',kind:'%s',o:%s}" % (
                        top['key'], top['label'].replace("'", "\\'"),
                        top['status'], project_says(top).replace("'", "\\'"),
                        top['kind'],
                        ("'%s'" % top['opens']) if top['opens'] else 'null')),
                ",pipeNote:'%s'" % pl['note'].replace("'", "\\'"),
                ",kfSrc:'knightfrank',kfAsOf:'2026-06'"]

        ent = ent[:-1] + ''.join(add) + '}'
        out.append(blk[cursor:s] + ent)
        cursor = e
    out.append(blk[cursor:])

    missing = [o for (_k, o, *_r) in KFPRICE if o not in seen]
    if missing:
        sys.exit('These KF locations did not match an AREAS entry: %s' % missing)

    src = src[:a0] + ''.join(out) + src[a1:]
    src = patch_pipeline(src)
    open(HTML, 'w', encoding='utf-8').write(src)

    if remerged[0]:
        print('re-merged over a previous run: %d entries reset first' % remerged[0])
    print('verified: %d   portal: %d' % (len(report), len(seen) - len(report)))
    print()
    print('%-26s %-8s %5s %5s %5s  %-13s %s' % ('area', 'kfZone', 'was', '26', '25', 'trend', 'pipe'))
    for r in sorted(report, key=lambda x: -(x[3] - x[4])):
        print('%-26s %-8s %5d %5d %5d  %-13s %d' % r)
    print()
    print('pipeline score, rounded down: ' + '  '.join(
        '%d:%d' % (b, pipe_hist.get(b, 0)) for b in sorted(pipe_hist)))
    print('current infra,  rounded down: ' + '  '.join(
        '%d:%d' % (b, now_hist.get(b, 0)) for b in sorted(now_hist)))


if __name__ == '__main__':
    main()
