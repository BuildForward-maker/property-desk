#!/usr/bin/env python3
"""
One-time location enrichment for Property Desk.

Run by hand:   python3 tools/enrich.py
This is data-prep tooling. It is NOT part of the app, it is never loaded by
index.html, and index.html must never call any of these services at runtime.
Nominatim, OSRM and Overpass are community-run; browser-side calls from a
published page would breach their usage policies. That is the whole point of
baking the results into the file.

Stages
  1  geocode      Nominatim,  cache-first, 1 request / 1100ms
  2  drive times  OSRM demo,  free-flow, x1.6 for a peak ESTIMATE
  3  metro        Overpass,   one query, nearest station computed locally
  4  write        data/enrichment.json
  5  patch        AREAS / SOC inside index.html

The geocode cache (data/geocache.json) is read before anything is requested,
so re-running this never re-queries a place already resolved. Delete the cache
only if you mean to hit Nominatim again.

Stdlib only: no pip, no npm, nothing to install.
"""

import json, math, os, re, ssl, subprocess, sys, time
import urllib.parse, urllib.request, urllib.error

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX    = os.path.join(ROOT, 'index.html')
DATA_DIR = os.path.join(ROOT, 'data')
GEOCACHE = os.path.join(DATA_DIR, 'geocache.json')
OUT      = os.path.join(DATA_DIR, 'enrichment.json')

UA = 'property-desk/1.0 (buildforward-maker.github.io)'

# Bengaluru sanity box. Anything outside it is reported for a human to check.
BBOX = {'south': 12.7, 'north': 13.25, 'west': 77.3, 'east': 77.9}
BLR_CENTRE = (12.9716, 77.5946)

# Employment hubs, as given in the brief.
HUBS = [
    ('itpl',  'ITPL Whitefield',  12.9856, 77.7367),
    ('orr',   'Bellandur ORR',    12.9304, 77.6784),
    ('ecity', 'Electronic City',  12.8452, 77.6602),
    ('cbd',   'MG Road CBD',      12.9752, 77.6069),
]

# OSRM free-flow has no traffic in it. Bengaluru mornings are not free-flow,
# and congestion does not scale linearly with trip length: a 3 km crosstown
# crawl loses proportionally far more time than a 35 km run that is mostly
# highway. A flat multiplier badly under-states the short trips, so the factor
# is banded by road distance.
PEAK_BANDS = [(5, 2.6), (15, 2.2), (30, 1.8), (float('inf'), 1.5)]


def peak_multiplier(km):
    for limit, mult in PEAK_BANDS:
        if km < limit:
            return mult
    return PEAK_BANDS[-1][1]


def round_half_up(x):
    """Python's round() is banker's rounding: round(64.5) is 64, not 65. The
    1.5x band lands on an exact .5 for every odd free-flow minute, so without
    this those estimates come out a minute short of what the stated multiplier
    implies, and disagree with the same arithmetic done in the browser."""
    return int(math.floor(x + 0.5))


def with_peak(free_min, km):
    """Peak is always derived here, from the free-flow time and the road
    distance, so it cannot drift out of step with the band table."""
    mult = peak_multiplier(km) if km is not None else 2.2
    return [free_min, round_half_up(free_min * mult), km]


# Places Nominatim cannot match as written. The value is the exact query to
# send instead. These are spelling and phrasing problems, not missing places.
OVERRIDES = {
    'Kathreguppe':         'Kathriguppe, Bengaluru',
    # "Sarjapur, Bengaluru" matches a BUS ROUTE relation whose midpoint lands in
    # the CBD, 22 km from the town. The spelling Nominatim knows is Sarjapura.
    'Sarjapur town':       'Sarjapura, Karnataka, India',
    # Kumbalgodu is simply not in OSM under any spelling tried. Bidadi is the
    # other half of this entry's name and does resolve, so the pin sits at the
    # western end of the pair rather than its midpoint.
    'Kumbalgodu / Bidadi': 'Bidadi, Karnataka, India',
}

# A locality lookup should never return a transit relation or a lake. Both have
# been observed: a bus route scored above the town it is named after, and a
# lake above the settlement beside it. Rejected wherever they come from,
# cache included, so a bad result already on disk cannot be reused.
REJECT_CLASSES = {'route', 'water', 'waterway'}


def plausible(rec):
    return bool(rec) and rec.get('class') not in REJECT_CLASSES

NOMINATIM_INTERVAL = 1.1   # seconds, strict, per the service's usage policy
OSRM_INTERVAL      = 1.0
OSRM_BATCH         = 20    # origins per /table request, keeps the matrix small


# ---------------------------------------------------------------- utilities

class Pacer:
    """Guarantees a minimum gap between requests, measured from the last one
    actually sent rather than by sleeping a flat amount after each."""
    def __init__(self, interval):
        self.interval = interval
        self.last = 0.0
    def wait(self):
        gap = time.monotonic() - self.last
        if gap < self.interval:
            time.sleep(self.interval - gap)
        self.last = time.monotonic()


# Some hosts (router.project-osrm.org is one) need a TLS stack newer than the
# LibreSSL that ships with macOS system Python. curl handles them fine, so the
# transport falls back to it per-host rather than failing the run. Both paths
# send the same URL and the same User-Agent; only the socket differs.
_USE_CURL = set()


def _via_curl(url, ua, timeout):
    out = subprocess.run(
        ['curl', '-sS', '--compressed', '--max-time', str(timeout), '-A', ua, url],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError('curl: %s' % (out.stderr.strip() or out.returncode))
    return json.loads(out.stdout)


def get(url, ua=UA, tries=3, timeout=30):
    host = urllib.parse.urlsplit(url).netloc
    last = None
    for attempt in range(tries):
        try:
            if host in _USE_CURL:
                return _via_curl(url, ua, timeout)
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except ssl.SSLError:
            if host not in _USE_CURL:
                _USE_CURL.add(host)
                print('  (TLS handshake failed for %s, falling back to curl)' % host)
                continue
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLError) and host not in _USE_CURL:
                _USE_CURL.add(host)
                print('  (TLS handshake failed for %s, falling back to curl)' % host)
                continue
            last = e
            if attempt < tries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 502, 503, 504) and attempt < tries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except TimeoutError as e:
            last = e
            if attempt < tries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
    raise last


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def in_bbox(lat, lon):
    return (BBOX['south'] <= lat <= BBOX['north']) and (BBOX['west'] <= lon <= BBOX['east'])


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    """Write via a temp file so an interrupt can never truncate the cache."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


# ------------------------------------------------------------ parse the app

ROW = re.compile(r"^\{n:'((?:[^']|\\')*)'")

def read_arrays():
    """Pull AREAS and SOC out of index.html without executing anything."""
    with open(INDEX, encoding='utf-8') as f:
        lines = f.read().split('\n')

    def block(name):
        start = next(i for i, l in enumerate(lines) if l.startswith('const %s=[' % name))
        end   = next(i for i, l in enumerate(lines) if i > start and l.strip() == '];')
        out = []
        for i in range(start, end):
            m = ROW.match(lines[i])
            if not m:
                continue
            row = {'_line': i, '_name': m.group(1).replace("\\'", "'")}
            for key in ('a', 'z', 'cor'):
                km = re.search(r"[,{]%s:'((?:[^']|\\')*)'" % key, lines[i])
                if km:
                    row[key] = km.group(1).replace("\\'", "'")
            for key in ('lat', 'lng'):
                km = re.search(r",%s:(-?[\d.]+)" % key, lines[i])
                if km:
                    row[key] = float(km.group(1))
            out.append(row)
        return out, start, end

    areas, a0, a1 = block('AREAS')
    socs,  s0, s1 = block('SOC')
    return lines, areas, socs


# ------------------------------------------------------------- 1. geocoding

def geocode_all(items, cache, pacer, dry_run=False):
    """Cache-first. Only unseen queries ever reach Nominatim."""
    resolved, unresolved, outside, fetched, cached = {}, [], [], 0, 0

    for it in items:
        # The brief's query shape. A second, more specific attempt is made only
        # if this one fails, so a miss costs at most one extra request.
        if it['_name'] in OVERRIDES:
            queries = [OVERRIDES[it['_name']]]
        else:
            queries = ['%s, Bengaluru, Karnataka, India' % it['_name']]
        if it['_name'] not in OVERRIDES and it.get('a') and it['a'] != it['_name']:
            queries.append('%s, %s, Bengaluru, Karnataka, India' % (it['_name'], it['a']))
        # Several AREAS are compound labels ("Banaswadi / Kammanahalli",
        # "Banashankari overall") that Nominatim cannot parse as written.
        # Fall back to the first place named in them.
        plain = re.split(r'\s*/\s*', it['_name'])[0]
        plain = re.sub(r'\s+overall$', '', plain, flags=re.I).strip()
        if it['_name'] not in OVERRIDES and plain and plain != it['_name']:
            queries.append('%s, Bengaluru, Karnataka, India' % plain)

        hit = None
        for qi, q in enumerate(queries):
            if q in cache:
                cached += 1
                rec = cache[q]
            elif dry_run:
                print('  would query: %s' % q)
                rec = None
            else:
                pacer.wait()
                url = ('https://nominatim.openstreetmap.org/search?'
                       + urllib.parse.urlencode({'q': q, 'format': 'json', 'limit': 1}))
                try:
                    res = get(url)
                except Exception as e:                      # noqa: BLE001
                    print('  ! %s -> %s' % (q, e))
                    res = []
                rec = None
                if res:
                    r = res[0]
                    rec = {'lat': float(r['lat']), 'lon': float(r['lon']),
                           'display_name': r.get('display_name', ''),
                           'class': r.get('class', ''), 'type': r.get('type', ''),
                           'query_variant': qi}
                # A miss is cached too, so it is never asked again.
                cache[q] = rec
                save_json(GEOCACHE, cache)
                fetched += 1

            if rec and not plausible(rec):
                print('  ~ %s -> rejected %s/%s (%s)'
                      % (q, rec.get('class'), rec.get('type'), rec['display_name'][:48]))
                rec = None
            if rec:
                hit = dict(rec)
                hit['query'] = q
                break

        if not hit:
            unresolved.append(it['_name'])
            continue
        if not in_bbox(hit['lat'], hit['lon']):
            outside.append((it['_name'], hit['lat'], hit['lon'], hit.get('display_name', '')))
        resolved[it['_name']] = hit

    return resolved, unresolved, outside, fetched, cached


# ----------------------------------------------------------- 2. drive times

def drive_times(points, pacer):
    """OSRM /table: one request per batch of origins rather than one per
    origin-hub pair. Same numbers, a fraction of the load on a free server."""
    out = {}
    names = list(points.keys())
    hub_coords = ['%f,%f' % (h[3], h[2]) for h in HUBS]   # OSRM wants lon,lat

    for i in range(0, len(names), OSRM_BATCH):
        batch = names[i:i + OSRM_BATCH]
        coords = ['%f,%f' % (points[n][1], points[n][0]) for n in batch] + hub_coords
        # OSRM separates index lists with semicolons, not commas. Commas here
        # are rejected with a misleading "Query string malformed" InvalidQuery.
        srcs = ';'.join(str(j) for j in range(len(batch)))
        dsts = ';'.join(str(len(batch) + j) for j in range(len(HUBS)))
        # Distances as well as durations: the peak multiplier is banded by road
        # distance, so the durations alone are not enough.
        url = ('https://router.project-osrm.org/table/v1/driving/' + ';'.join(coords)
               + '?sources=%s&destinations=%s&annotations=duration,distance' % (srcs, dsts))
        pacer.wait()
        try:
            res = get(url, timeout=60)
        except Exception as e:                              # noqa: BLE001
            print('  ! OSRM batch %d-%d failed: %s' % (i, i + len(batch), e))
            continue
        if res.get('code') != 'Ok':
            print('  ! OSRM batch %d-%d: %s' % (i, i + len(batch), res.get('code')))
            continue
        for row_i, name in enumerate(batch):
            row = res['durations'][row_i]
            drow = (res.get('distances') or [[None] * len(HUBS)] * len(batch))[row_i]
            rec = {}
            for hub_i, hub in enumerate(HUBS):
                secs = row[hub_i]
                if secs is None:
                    continue
                free = round_half_up(secs / 60.0)
                metres = drow[hub_i] if drow and drow[hub_i] is not None else None
                # band on the same rounded km that gets written out, so the
                # stored numbers are self-consistent and auditable
                km = round(metres / 1000.0, 1) if metres is not None else None
                rec[hub[0]] = with_peak(free, km)
            if rec:
                out[name] = rec
        print('  batch %d-%d ok (%d origins)' % (i, i + len(batch), len(batch)))
    return out


# ------------------------------------------------------------- 3. metro

# Mirrors are tried in order. Some networks block the main endpoint outright
# (it answers 406 to every request, even /api/status), so a fallback list is
# the difference between "works on your laptop" and "works nowhere".
OVERPASS_MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass.osm.jp/api/interpreter',
]


def metro_stations():
    """One Overpass query for every subway station in the box."""
    q = """[out:json][timeout:90];
(
  node["railway"="station"]["station"="subway"](%(south)s,%(west)s,%(north)s,%(east)s);
  way["railway"="station"]["station"="subway"](%(south)s,%(west)s,%(north)s,%(east)s);
);
out center tags;""" % BBOX
    qs = urllib.parse.urlencode({'data': q})
    res, last = None, None
    for base in OVERPASS_MIRRORS:
        try:
            res = get(base + '?' + qs, timeout=120)
            print('  via %s' % urllib.parse.urlsplit(base).netloc)
            break
        except Exception as e:                              # noqa: BLE001
            print('  ! %s: %s' % (urllib.parse.urlsplit(base).netloc, str(e)[:60]))
            last = e
    if res is None:
        raise last if last else RuntimeError('no Overpass mirror reachable')
    out = []
    for el in res.get('elements', []):
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        name = (el.get('tags') or {}).get('name')
        if lat and lon and name:
            out.append({'name': name, 'lat': lat, 'lon': lon})
    # de-duplicate stations mapped as both node and way
    seen, uniq = set(), []
    for s in out:
        k = s['name'].strip().lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    return uniq


STATIONS_FILE = os.path.join(DATA_DIR, 'stations.json')


def load_stations_file():
    """A raw Overpass element dump kept on disk. Overpass mirrors are the least
    reliable dependency here, so the station list is preserved separately
    rather than being re-fetched on every run."""
    raw = load_json(STATIONS_FILE, None)
    if not raw:
        return []
    els = raw.get('elements', raw) if isinstance(raw, dict) else raw
    out, seen = [], set()
    for el in els:
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        name = (el.get('tags') or {}).get('name')
        if not (lat and lon and name):
            continue
        k = name.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        out.append({'name': name, 'lat': lat, 'lon': lon})
    return out


def nearest_metro(points, stations):
    out = {}
    for name, (lat, lon) in points.items():
        best, bestd = None, 1e9
        for s in stations:
            d = haversine_km(lat, lon, s['lat'], s['lon'])
            if d < bestd:
                best, bestd = s, d
        if best:
            out[name] = {'name': best['name'], 'km': round(bestd, 2)}
    return out


# ------------------------------------------------ 3b2. metro journeys
#
# A metro commuter's journey is not the drive time. It is walk + ride +
# interchange + walk, and scoring them on a car number describes somebody
# else's commute. These are the only modelled constants; the network itself
# comes from OSM route relations.
WALK_MIN_PER_KM   = 12
WALK_CAP_MIN      = 25     # past this nobody walks to a station
RIDE_MIN_PER_STOP = 2.5
INTERCHANGE_MIN   = 8
DEST_WALK_MIN     = 8
HUB_STATION_MAX_KM = 2.5

# Bellandur / ORR sits on the Blue Line, which is under construction. There is
# no journey to model and inventing one would be worse than saying so.
HUB_METRO_OVERRIDE = {'orr': False}


def fetch_metro_routes():
    """Namma Metro route relations, in member order, so stations carry a line
    and a position along it."""
    q = """[out:json][timeout:200];
rel["route"="subway"]["network"="Namma Metro"];
out body;""" % BBOX
    qs = urllib.parse.urlencode({'data': q})
    last = None
    for base in OVERPASS_MIRRORS:
        try:
            res = get(base + '?' + qs, timeout=240)
            print('  routes via %s' % urllib.parse.urlsplit(base).netloc)
            return res.get('elements', [])
        except Exception as e:                              # noqa: BLE001
            print('  ! %s: %s' % (urllib.parse.urlsplit(base).netloc, str(e)[:55]))
            last = e
    raise last if last else RuntimeError('no Overpass mirror reachable')


def line_name(tags):
    for k in ('colour', 'ref', 'name'):
        v = (tags.get(k) or '').strip()
        if not v:
            continue
        for c in ('Purple', 'Green', 'Yellow', 'Blue', 'Pink', 'Orange', 'Red'):
            if c.lower() in v.lower():
                return c
    return (tags.get('ref') or tags.get('name') or 'Metro').strip()[:14]


STOPS_FILE = os.path.join(DATA_DIR, 'metro_stops_raw.json')


def load_stop_names():
    """Route relations reference stop_position nodes, not the railway=station
    node, so member ids never match the station list directly. These carry the
    same names, which is the join."""
    raw = load_json(STOPS_FILE, None)
    if not raw:
        return {}
    els = raw.get('elements', raw) if isinstance(raw, dict) else raw
    out = {}
    for e in els:
        nm = (e.get('tags') or {}).get('name')
        if not nm:
            continue
        # Interchange stops are suffixed with the line: "Nadaprabhu Kempegowda
        # Station, Majestic (Purple Line)". The station node carries the bare
        # name, so without stripping this the join fails at exactly the
        # interchanges, and half the network looks unreachable.
        out[e['id']] = re.sub(r'\s*\([^)]*\bLine\)\s*$', '', nm).strip()
    return out


def build_metro_graph(station_elems, relations):
    """Returns (stations, lines, adjacency). Nodes are (station, line) so a
    change of line costs a real interchange rather than being free."""
    byid, stations = {}, {}
    byid.update(load_stop_names())          # stop_position ids -> station name
    for el in station_elems:
        nm = (el.get('tags') or {}).get('name')
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        if not (nm and lat and lon):
            continue
        byid[el['id']] = nm
        stations.setdefault(nm, {'lat': lat, 'lon': lon, 'lines': set()})

    lines = {}
    for rel in relations:
        tags = rel.get('tags') or {}
        if tags.get('route') != 'subway':
            continue
        ln = line_name(tags)
        seq = []
        for m in rel.get('members', []):
            if m.get('type') != 'node':
                continue
            nm = byid.get(m.get('ref'))
            if nm and (not seq or seq[-1] != nm):
                seq.append(nm)
        if len(seq) < 2:
            continue
        # both directions of a line are separate relations; keep the longest
        if ln not in lines or len(seq) > len(lines[ln]):
            lines[ln] = seq

    for ln, seq in lines.items():
        for nm in seq:
            if nm in stations:
                stations[nm]['lines'].add(ln)
    # drop any sequence entries we have no station record for, so the graph
    # only ever contains places we can actually route from
    for ln in list(lines):
        lines[ln] = [n for n in lines[ln] if n in stations]

    adj = {}
    def link(a, b, w):
        adj.setdefault(a, {})
        if b not in adj[a] or adj[a][b] > w:
            adj[a][b] = w
    for ln, seq in lines.items():
        for i in range(len(seq) - 1):
            a, b = (seq[i], ln), (seq[i + 1], ln)
            link(a, b, RIDE_MIN_PER_STOP)
            link(b, a, RIDE_MIN_PER_STOP)
    for nm, st in stations.items():
        ls = sorted(st['lines'])
        for i in range(len(ls)):
            for j in range(len(ls)):
                if i != j:
                    link((nm, ls[i]), (nm, ls[j]), INTERCHANGE_MIN)
    return stations, lines, adj


def ride_times_from(adj, stations, dest_name):
    """Dijkstra out from every platform of the destination station. Returns
    {station: (minutes, interchanges)}."""
    import heapq
    starts = [(dest_name, ln) for ln in stations.get(dest_name, {}).get('lines', [])]
    if not starts:
        return {}
    best, pq = {}, []
    for s in starts:
        best[s] = (0.0, 0)
        heapq.heappush(pq, (0.0, 0, s))
    while pq:
        d, ic, node = heapq.heappop(pq)
        if best.get(node, (1e9,))[0] < d:
            continue
        for nxt, w in (adj.get(node) or {}).items():
            nic = ic + (1 if w == INTERCHANGE_MIN else 0)
            nd = d + w
            if nd < best.get(nxt, (1e9, 0))[0]:
                best[nxt] = (nd, nic)
                heapq.heappush(pq, (nd, nic, nxt))
    out = {}
    for (nm, ln), (d, ic) in best.items():
        if nm not in out or d < out[nm][0]:
            out[nm] = (d, ic)
    return out


def metro_journeys(points, nearest, stations, adj, hub_station):
    """points: key -> (lat,lon); nearest: key -> {'name','km'}"""
    rides = {h: ride_times_from(adj, stations, st) for h, st in hub_station.items() if st}
    out = {}
    for k, near in nearest.items():
        if not near:
            continue
        walk = near['km'] * WALK_MIN_PER_KM
        rec = {}
        for h, st in hub_station.items():
            if not st or walk > WALK_CAP_MIN:
                continue
            r = rides.get(h, {}).get(near['name'])
            if r is None:
                continue
            rec[h] = [int(round(walk + r[0] + DEST_WALK_MIN)), int(r[1])]
        if rec:
            out[k] = rec
    return out


# ------------------------------------------------ 3c. Tier 2 localities

# Every other named Bengaluru locality, so search can answer for places the
# 86 researched AREAS do not cover. These carry real geography (coordinates,
# commute, metro) and INHERITED pricing from their nearest researched area,
# which the UI must render as an inference, never as a researched figure.
# The full set. Browsers open a multi-megabyte HTML file without complaint, so
# there is no size budget worth trading coverage against: a locality somebody
# searches for and cannot find is a real failure, a larger file is not.
PLACE_TYPES = ('suburb', 'neighbourhood', 'village', 'town', 'quarter', 'hamlet')


def fetch_localities():
    q = """[out:json][timeout:180];
(
  node["place"~"^(%(types)s)$"](%(south)s,%(west)s,%(north)s,%(east)s);
  way["place"~"^(%(types)s)$"](%(south)s,%(west)s,%(north)s,%(east)s);
  relation["place"~"^(%(types)s)$"](%(south)s,%(west)s,%(north)s,%(east)s);
);
out center tags;""" % dict(BBOX, types='|'.join(PLACE_TYPES))
    qs = urllib.parse.urlencode({'data': q})
    res, last = None, None
    for base in OVERPASS_MIRRORS:
        try:
            res = get(base + '?' + qs, timeout=240)
            print('  via %s' % urllib.parse.urlsplit(base).netloc)
            break
        except Exception as e:                              # noqa: BLE001
            print('  ! %s: %s' % (urllib.parse.urlsplit(base).netloc, str(e)[:60]))
            last = e
    if res is None:
        raise last if last else RuntimeError('no Overpass mirror reachable')

    out, seen = [], set()
    for el in res.get('elements', []):
        tags = el.get('tags') or {}
        name = (tags.get('name:en') or tags.get('name') or '').strip()
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        if not name or lat is None or lon is None:
            continue
        if not in_bbox(lat, lon):
            continue
        # the same settlement is often mapped as node and area; and distinct
        # places do share names, so dedupe on name plus rough position
        key = (name.lower(), round(lat, 2), round(lon, 2))
        if key in seen:
            continue
        seen.add(key)
        out.append({'n': name, 'lat': round(lat, 5), 'lon': round(lon, 5),
                    'place': tags.get('place', '')})
    out.sort(key=lambda x: x['n'].lower())
    return out


def nearest_area(lat, lon, area_pts):
    best, bestd = None, 1e9
    for name, (alat, alon) in area_pts.items():
        d = haversine_km(lat, lon, alat, alon)
        if d < bestd:
            best, bestd = name, d
    return best, round(bestd, 2)


# ------------------------------------------- 3b. society -> micro-market

def build_area_index(areas, resolved):
    """name -> (lat, lon) for every AREA that geocoded, plus corridor centroids
    so a society whose micro-market names a corridor rather than an area still
    lands somewhere sensible."""
    by_name, by_corridor = {}, {}
    for a in areas:
        r = resolved.get(a['_name'])
        if not r or not in_bbox(r['lat'], r['lon']):
            continue
        by_name[a['_name']] = (a['_name'], r['lat'], r['lon'])
        if a.get('cor'):
            by_corridor.setdefault(a['cor'], []).append((a['_name'], r['lat'], r['lon']))
    # a corridor resolves to whichever of its areas sits closest to the middle
    corridor_pick = {}
    for cor, members in by_corridor.items():
        clat = sum(m[1] for m in members) / len(members)
        clon = sum(m[2] for m in members) / len(members)
        corridor_pick[cor] = min(members, key=lambda m: haversine_km(clat, clon, m[1], m[2]))
    return by_name, corridor_pick


def match_area(a_field, by_name, corridor_pick):
    """Apartment complexes are largely absent from OpenStreetMap, so an
    unresolved society borrows its micro-market's position. Returns the AREA
    it borrowed from, or None."""
    if not a_field:
        return None
    al = a_field.lower()
    for n, rec in by_name.items():
        if n.lower() == al:
            return rec
    cands = [rec for n, rec in by_name.items() if n.lower() in al]
    if cands:
        return max(cands, key=lambda r: len(r[0]))
    head = re.split(r'[,/]', a_field)[0].strip().lower()
    if head:
        cands = [rec for n, rec in by_name.items()
                 if head in n.lower() or n.lower() in head]
        if cands:
            return max(cands, key=lambda r: len(r[0]))
    for cor, rec in corridor_pick.items():
        if cor.lower() == al or cor.lower() in al:
            return rec
    return None


# --------------------------------------------------------------- 5. patch

def js_str(s):
    return s.replace('\\', '\\\\').replace("'", "\\'")


def patch_index(lines, areas, socs, enrich):
    """Rewrite only the fields this script owns, leaving every line otherwise
    byte-identical. Existing lat/lng is kept when a geocode failed or landed
    outside the box, so a bad lookup can never move a pin silently."""
    changed = {'lat': 0, 'dt': 0, 'metro': 0, 'kept_coords': 0}

    def field(line, key, value):
        """Insert or replace ,key:value, right after the name field."""
        pat = re.compile(r",%s:(?:'(?:[^']|\\')*'|\[[^\]]*\]|\{[^}]*\}|-?[\d.]+)" % key)
        if pat.search(line):
            return pat.sub(',%s:%s' % (key, value), line, count=1)
        m = ROW.match(line)
        return line[:m.end()] + ',%s:%s' % (key, value) + line[m.end():]

    for coll, rows in (('areas', areas), ('socs', socs)):
        for it in rows:
            name = it['_name']
            rec = enrich[coll].get(name)
            if not rec:
                continue
            line = lines[it['_line']]

            g = rec.get('geo')
            if g and g.get('in_bbox'):
                line = field(line, 'lat', repr(round(g['lat'], 6)))
                line = field(line, 'lng', repr(round(g['lon'], 6)))
                changed['lat'] += 1
            elif 'lat' in it:
                changed['kept_coords'] += 1

            dt = rec.get('drive')
            if dt:
                parts = ','.join(
                    '%s:[%d,%d%s]' % (k, v[0], v[1], ',%s' % v[2] if len(v) > 2 and v[2] is not None else '')
                    for k, v in sorted(dt.items()))
                line = field(line, 'dt', '{%s}' % parts)
                changed['dt'] += 1

            gp = rec.get('geoPrecision')
            if gp:
                line = field(line, 'geoPrecision', "'%s'" % gp)

            mj = rec.get('metroJourney')
            if mj:
                line = field(line, 'mt', '{%s}' % ','.join(
                    '%s:[%d,%d]' % (h, v[0], v[1]) for h, v in sorted(mj.items())))
                changed['mt'] = changed.get('mt', 0) + 1

            mx = rec.get('metro')
            if mx:
                line = field(line, 'mx', "'%s'" % js_str(mx['name']))
                line = field(line, 'mkm', repr(mx['km']))
                changed['metro'] += 1

            lines[it['_line']] = line

    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return changed


def patch_tables(hub_info, stations):
    """HUBMETRO (which hubs a line actually reaches) and MLINES (station ->
    line), both small and both needed to name a journey in the UI."""
    with open(INDEX, encoding='utf-8') as f:
        text = f.read()
    hub = '{' + ','.join(
        "%s:{served:%s,station:%s,km:%s,note:%s}" % (
            k, 'true' if v['served'] else 'false',
            ("'%s'" % js_str(v['station'])) if v['station'] else 'null',
            v['km'] if v['km'] is not None else 'null',
            ("'%s'" % js_str(v['note'])) if v['note'] else 'null')
        for k, v in sorted(hub_info.items())) + '}'
    ml = '{' + ','.join("'%s':'%s'" % (js_str(n), js_str(sorted(s['lines'])[0]))
                        for n, s in sorted(stations.items()) if s['lines']) + '}'
    block = ('/* ===== metro tables, written by tools/enrich.py ===== */\n'
             '/* var, not let: this block is written above the scoring code that\n'
             '   declares nothing, so it must hoist. */\n'
             'var HUBMETRO=' + hub + ';\n'
             'var MLINES=' + ml + ';')
    marker = '/* ===== metro tables, written by tools/enrich.py ===== */'
    if marker in text:
        start = text.index(marker)
        end = text.index(';', text.index('var MLINES=', start)) + 1
        text = text[:start] + block + text[end:]
    else:
        anchor = '\n/* ========== Tier 2 localities =========='
        assert anchor in text, 'anchor for metro tables not found'
        text = text.replace(anchor, '\n' + block + '\n' + anchor, 1)
    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write(text)


def patch_localities(locs):
    """Write LOCALITIES as its own array so the researched AREAS data stays
    clean and the two tiers can never be confused in code.

    The place-type cap is applied HERE rather than upstream, so NARROWING
    PLACE_TYPES only rewrites the page. Widening it needs a re-fetch, because
    the same constant drives the Overpass query — the cache holds what was
    asked for, not everything that exists."""
    locs = [l for l in locs if not l.get('place') or l['place'] in PLACE_TYPES]
    with open(INDEX, encoding='utf-8') as f:
        text = f.read()
    rows = []
    for l in locs:
        parts = ["{n:'%s'" % js_str(l['n']), 'lat:%s' % l['lat'], 'lng:%s' % l['lon']]
        if l.get('place'):
            parts.append("pl:'%s'" % js_str(l['place']))
        if l.get('dt'):
            # [free-flow, peak, road km] — the same shape AREAS and SOC use, so
            # commuteHTML renders all three tiers through one code path.
            parts.append('dt:{%s}' % ','.join(
                '%s:[%d,%d%s]' % (k, v[0], v[1], ',%s' % v[2] if len(v) > 2 and v[2] is not None else '')
                for k, v in sorted(l['dt'].items())))
        if l.get('mt'):
            parts.append('mt:{%s}' % ','.join(
                '%s:[%d,%d]' % (h, v[0], v[1]) for h, v in sorted(l['mt'].items())))
        if l.get('mx'):
            parts.append("mx:'%s',mkm:%s" % (js_str(l['mx']), l['mkm']))
        if l.get('pa'):
            parts.append("pa:'%s',pkm:%s" % (js_str(l['pa']), l['pkm']))
        # Inherited pricing is NOT written here. It is a verbatim copy of the
        # parent area's figures, which the page already holds in AREAS, and
        # showLocality() reads them from there via `pa`. Duplicating them cost
        # ~43KB and gave the same number two places to drift apart.
        rows.append(','.join(parts) + '}')
    # The app reads this file lazily; the inline array is gone. Kept compact on
    # purpose — it is fetched over the wire on first search.
    import json as _json
    app=[]
    for l in locs:
        rec={'n':l['n'],'lat':l['lat'],'lng':l['lon']}
        if l.get('place'):rec['pl']=l['place']
        if l.get('dt'):rec['dt']=l['dt']
        if l.get('mx'):rec['mx']=l['mx'];rec['mkm']=l['mkm']
        if l.get('pa'):rec['pa']=l['pa'];rec['pkm']=l['pkm']
        app.append(rec)
    with open(os.path.join(DATA_DIR,'localities.app.json'),'w',encoding='utf-8') as f:
        _json.dump({'generated':time.strftime('%Y-%m-%d'),'count':len(app),
                    'note':'Tier 2 localities for search. Geography is real; pricing is '
                           'inherited at runtime from the nearest researched AREA via pa.',
                    'localities':app},f,ensure_ascii=False,separators=(',',':'))
    return len(app)

def _unused_inline_block(locs, rows):
    block = ('/* ========== Tier 2 localities ==========\n'
             ' Every other named locality in the Bengaluru box, from OSM. Geography is\n'
             ' real (coordinates, commute, metro). Pricing under `inh` is INHERITED from\n'
             ' the nearest researched area `pa` and must never be shown as researched.\n'
             ' Written by tools/enrich.py \u2014 do not hand-edit. */\n'
             'const LOCALITIES=[\n' + ',\n'.join(rows) + '\n];')
    marker = '/* ========== Tier 2 localities =========='
    if marker in text:
        start = text.index(marker)
        end = text.index('\n];', start) + len('\n];')
        text = text[:start] + block + text[end:]
    else:
        anchor = '\n/* ========== conveyancing schedule =========='
        assert anchor in text, 'anchor for LOCALITIES not found'
        text = text.replace(anchor, '\n' + block + '\n' + anchor, 1)
    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write(text)
    return len(rows)


# ------------------------------------------------------------------- main

def main():
    dry_run = '--dry-run' in sys.argv
    skip_geo = '--skip-geocode' in sys.argv
    only = None
    stages = None
    for a in sys.argv[1:]:
        if a.startswith('--limit='):
            only = int(a.split('=', 1)[1])
        if a.startswith('--only='):
            stages = set(a.split('=', 1)[1].split(','))

    def run(stage):
        return stages is None or stage in stages

    os.makedirs(DATA_DIR, exist_ok=True)
    lines, areas, socs = read_arrays()
    if only:
        areas, socs = areas[:only], socs[:only]
    print('parsed %d AREAS, %d SOC from index.html' % (len(areas), len(socs)))

    cache = load_json(GEOCACHE, {})
    print('geocache: %d entries on disk' % len(cache))

    # ---- 1. geocode
    nom = Pacer(NOMINATIM_INTERVAL)
    print('\n[1/5] geocoding via Nominatim (cache-first, 1 req / %.1fs)' % NOMINATIM_INTERVAL)
    if skip_geo:
        print('  --skip-geocode: using coordinates already in index.html')
        a_res = {i['_name']: {'lat': i['lat'], 'lon': i['lng'], 'display_name': '(existing)'}
                 for i in areas if 'lat' in i}
        s_res, a_un, s_un, a_out, s_out = {}, [], [], [], []
        fetched = cached = 0
    else:
        a_res, a_un, a_out, f1, c1 = geocode_all(areas, cache, nom, dry_run)
        s_res, s_un, s_out, f2, c2 = geocode_all(socs,  cache, nom, dry_run)
        fetched, cached = f1 + f2, c1 + c2
    print('  resolved: %d areas, %d societies' % (len(a_res), len(s_res)))
    print('  requests sent: %d   served from cache: %d' % (fetched, cached))

    if dry_run:
        print('\ndry run: nothing written')
        return

    # ---- 1b. societies OSM does not know: borrow the micro-market's position
    by_name, corridor_pick = build_area_index(areas, a_res)
    precision, borrowed_from, borrowed = {}, {}, 0
    for s in socs:
        n = s['_name']
        if n in s_res and in_bbox(s_res[n]['lat'], s_res[n]['lon']):
            precision[n] = 'building'
            continue
        rec = match_area(s.get('a', ''), by_name, corridor_pick)
        if rec:
            area_name, lat, lon = rec
            s_res[n] = {'lat': lat, 'lon': lon,
                        'display_name': 'area-level: %s' % area_name,
                        'query': '(borrowed from AREA %s)' % area_name}
            precision[n] = 'area'
            borrowed_from[n] = area_name
            borrowed += 1
        else:
            precision[n] = None
            print('  ! no micro-market match for %s (a=%r)' % (n, s.get('a', '')))
    print('  area-level fallback used for %d societies' % borrowed)

    # points we have coordinates for. Societies that borrowed a position are
    # left out of the routing batch: their answer is by definition identical to
    # the area they borrowed from, so it is copied rather than re-requested.
    pts = {}
    for n, r in a_res.items():
        if in_bbox(r['lat'], r['lon']):
            pts[('A', n)] = (r['lat'], r['lon'])
    for n, r in s_res.items():
        if precision.get(n) == 'building' and in_bbox(r['lat'], r['lon']):
            pts[('S', n)] = (r['lat'], r['lon'])
    flat = {'%s\x00%s' % k: v for k, v in pts.items()}

    # ---- 2. drive times
    prev = load_json(OUT, {'areas': {}, 'socs': {}, 'stations': []})
    print('\n[2/5] drive times via OSRM demo (1 req / %.0fs, batched)' % OSRM_INTERVAL)
    if run('drive'):
        drive = drive_times(flat, Pacer(OSRM_INTERVAL))
    else:
        drive = {}
        for tag, coll in (('A', 'areas'), ('S', 'socs')):
            for n, r in prev.get(coll, {}).items():
                if r.get('drive'):
                    drive['%s\x00%s' % (tag, n)] = {
                        h: with_peak(t[0], t[2] if len(t) > 2 else None)
                        for h, t in r['drive'].items()}
        print('  --only: reusing %d drive times from %s'
              % (len(drive), os.path.relpath(OUT, ROOT)))
    print('  got drive times for %d places' % len(drive))

    # ---- 3. metro
    print('\n[3/5] metro stations via Overpass')
    stations = []
    if run('metro'):
        try:
            stations = metro_stations()
        except Exception as e:                              # noqa: BLE001
            print('  ! no Overpass mirror reachable: %s' % str(e)[:80])
        if not stations:
            # A flaky mirror must never wipe metro data that is already good.
            # Overpass mirrors go down often enough that this is the normal
            # path, not an edge case.
            stations = prev.get('stations') or load_stations_file()
            if stations:
                print('  falling back to %d stations from the last good run' % len(stations))
    else:
        stations = prev.get('stations') or load_stations_file()
        print('  --only: reusing %d stations' % len(stations))
    print('  %d subway stations in the box' % len(stations))
    metro = nearest_metro(flat, stations) if stations else {}

    # inherit routing and metro for the borrowers, no extra requests
    for n, area_name in borrowed_from.items():
        ak = 'A\x00%s' % area_name
        if ak in drive:
            drive['S\x00%s' % n] = drive[ak]
        if ak in metro:
            metro['S\x00%s' % n] = metro[ak]

    # ---- 3c. metro network and journeys
    print('\n[3a] metro journeys')
    ROUTES_FILE = os.path.join(DATA_DIR, 'metro_routes_raw.json')
    _raw = load_json(ROUTES_FILE, None)
    relations = (_raw.get('elements') if isinstance(_raw, dict) else _raw) if _raw else None
    if relations is None or run('routes'):
        try:
            relations = fetch_metro_routes()
            save_json(ROUTES_FILE, {'elements': relations})
        except Exception as e:                              # noqa: BLE001
            print('  ! route fetch failed: %s' % str(e)[:70])
            relations = relations or []
    else:
        print('  reusing %d cached route relations' % len(relations))
    raw_station_elems = (load_json(STATIONS_FILE, {}) or {}).get('elements') or []
    mstations, mlines, madj = build_metro_graph(raw_station_elems, relations)
    print('  %d stations, %d lines: %s'
          % (len(mstations), len(mlines), ', '.join(sorted(mlines))))

    # which hub each line actually reaches
    hub_station, hub_info = {}, {}
    for key, label, hlat, hlon in HUBS:
        best, bestd = None, 1e9
        for nm, st in mstations.items():
            d = haversine_km(hlat, hlon, st['lat'], st['lon'])
            if d < bestd:
                best, bestd = nm, d
        served = (best is not None and bestd <= HUB_STATION_MAX_KM)
        if key in HUB_METRO_OVERRIDE:
            served = HUB_METRO_OVERRIDE[key]
        hub_station[key] = best if served else None
        hub_info[key] = {'label': label, 'served': served,
                         'station': best if served else None,
                         'km': round(bestd, 2) if best else None,
                         'note': None if served else (
                             'the Blue Line is under construction' if key == 'orr'
                             else 'no line reaches this hub yet')}
        print('  %-6s %-18s %s' % (key, label,
              (best + ' (' + str(round(bestd, 2)) + ' km)') if served
              else 'NOT METRO-SERVED'))

    def near_of(rec):
        m = rec.get('metro') if isinstance(rec, dict) else None
        return {'name': m['name'], 'km': m['km']} if m else None
    # nearest station per point, from the metro pass already computed
    near_all = {}
    for k, m in metro.items():
        near_all[k] = {'name': m['name'], 'km': m['km']}
    mjourney = metro_journeys(flat, near_all, mstations, madj, hub_station)
    print('  metro journeys for %d areas and societies' % len(mjourney))

    # ---- 3d. Tier 2 localities
    print('\n[3b] Tier 2 localities via Overpass')
    LOCOUT = os.path.join(DATA_DIR, 'localities.json')
    locs = []
    if run('localities'):
        try:
            locs = fetch_localities()
            print('  %d named localities in the box' % len(locs))
        except Exception as e:                              # noqa: BLE001
            print('  ! no Overpass mirror reachable: %s' % str(e)[:80])
    else:
        locs = (load_json(LOCOUT, {}) or {}).get('localities') or []
        print('  --only: reusing %d localities from %s'
              % (len(locs), os.path.relpath(LOCOUT, ROOT)))

    if locs:
        # Tier 1 wins any name collision: a researched area must never be
        # shadowed by a thinner Tier 2 record of the same place.
        tier1 = {a['_name'].lower() for a in areas}
        tier1_alias = set()
        for a in areas:
            for part in re.split(r'\s*/\s*', a['_name']):
                tier1_alias.add(re.sub(r'\s+overall$', '', part, flags=re.I).strip().lower())
        locs = [l for l in locs
                if l['n'].lower() not in tier1 and l['n'].lower() not in tier1_alias]
        print('  %d after removing names already covered by Tier 1' % len(locs))

        # Names must be unique: search is by name, and the routing table is
        # keyed by name, so duplicates would hand one place another's commute.
        # Where a name repeats, keep the one closest to the city centre.
        byname = {}
        for l in locs:
            k = l['n'].lower()
            d = haversine_km(l['lat'], l['lon'], BLR_CENTRE[0], BLR_CENTRE[1])
            if k not in byname or d < byname[k][0]:
                byname[k] = (d, l)
        if len(byname) != len(locs):
            print('  %d dropped as duplicate names' % (len(locs) - len(byname)))
        locs = sorted((v[1] for v in byname.values()), key=lambda x: x['n'].lower())
        prevl_all = {x['n']: x for x in ((load_json(LOCOUT, {}) or {}).get('localities') or [])}

        area_pts = {a['_name']: (a_res[a['_name']]['lat'], a_res[a['_name']]['lon'])
                    for a in areas if a['_name'] in a_res}
        area_by_name = {a['_name']: a for a in areas}

        # routing for localities, same batching and pacing as everything else
        lflat = {'L\x00%s' % l['n']: (l['lat'], l['lon']) for l in locs}
        if run('localities'):
            cached_dt = {}
            for l in locs:
                p = prevl_all.get(l['n'])
                if p and p.get('dt'):
                    cached_dt['L\x00%s' % l['n']] = {
                        h: with_peak(t[0], t[2] if len(t) > 2 else None)
                        for h, t in p['dt'].items()}
            todo = {k: v for k, v in lflat.items() if k not in cached_dt}
            print('  %d localities already routed in the cache, %d to route'
                  % (len(cached_dt), len(todo)))
            ldrive = dict(cached_dt)
            if todo:
                ldrive.update(drive_times(todo, Pacer(OSRM_INTERVAL)))
        else:
            prevl = {x['n']: x for x in ((load_json(LOCOUT, {}) or {}).get('localities') or [])}
            ldrive = {}
            for l in locs:
                p = prevl.get(l['n'])
                if p and p.get('dt'):
                    ldrive['L\x00%s' % l['n']] = {
                        h: with_peak(t[0], t[2] if len(t) > 2 else None)
                        for h, t in p['dt'].items()}
            print('  reusing %d locality drive times' % len(ldrive))
        lmetro = nearest_metro(lflat, stations) if stations else {}
        lnear = {k: {'name': m['name'], 'km': m['km']} for k, m in lmetro.items()}
        ljourney = metro_journeys(lflat, lnear, mstations, madj, hub_station)
        print('  metro journeys for %d localities' % len(ljourney))

        for l in locs:
            k = 'L\x00%s' % l['n']
            was = prevl_all.get(l['n'], {})
            l['dt'] = ldrive.get(k) or was.get('dt')
            m = lmetro.get(k)
            l['mx'] = m['name'] if m else was.get('mx')
            l['mkm'] = m['km'] if m else was.get('mkm')
            l['mt'] = ljourney.get(k) or was.get('mt')
            pa, pkm = nearest_area(l['lat'], l['lon'], area_pts) if area_pts else (None, None)
            l['pa'], l['pkm'] = pa, pkm
            # pricing is INHERITED, never researched for this locality
            src_area = area_by_name.get(pa)
            if src_area:
                line = lines[src_area['_line']]
                def num(key, default=0):
                    m2 = re.search(r'[,{]%s:(-?[\d.]+)' % key, line)
                    return float(m2.group(1)) if m2 else default
                l['inherit'] = {'ask': int(num('ask')), 'reg': int(num('reg')),
                                'py': num('py'), 'rent': int(num('rent')), 'ry': num('ry')}
        save_json(LOCOUT, {'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                           'note': 'Tier 2. Geography is real; pricing is inherited from the '
                                   'nearest Tier 1 area and must be shown as an estimate.',
                           'count': len(locs), 'localities': locs})
        print('  wrote %s' % os.path.relpath(LOCOUT, ROOT))

    # ---- 4. write
    print('\n[4/5] writing %s' % os.path.relpath(OUT, ROOT))
    enrich = {'areas': {}, 'socs': {},
              'meta': {'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                       'hubs': [{'key': h[0], 'label': h[1], 'lat': h[2], 'lon': h[3]} for h in HUBS],
                       'peak_bands_km_to_multiplier': [
                           {'under_km': (None if b[0] == float('inf') else b[0]), 'multiplier': b[1]}
                           for b in PEAK_BANDS],
                       'bbox': BBOX,
                       'sources': {'geocode': 'nominatim.openstreetmap.org',
                                   'routing': 'router.project-osrm.org',
                                   'metro': 'overpass-api.de'},
                       'note': 'Peak drive time is a MODELLED ESTIMATE: OSRM free-flow time '
                               'multiplied by a factor banded on road distance. It is not '
                               'measured traffic and no traffic data was used.'},
              'stations': stations or prev.get('stations') or []}
    for tag, coll, res, unres in (('A', 'areas', a_res, a_un), ('S', 'socs', s_res, s_un)):
        for n, r in res.items():
            k = '%s\x00%s' % (tag, n)
            was = prev.get(coll, {}).get(n) or {}
            enrich[coll][n] = {
                'geo': {'lat': r['lat'], 'lon': r['lon'],
                        'display_name': r.get('display_name', ''),
                        'in_bbox': in_bbox(r['lat'], r['lon']),
                        'query': r.get('query', '')},
                # never downgrade: a stage that returned nothing this run keeps
                # whatever the last good run produced
                'drive': drive.get(k) or was.get('drive'),
                'metro': metro.get(k) or was.get('metro'),
                'metroJourney': mjourney.get(k) or was.get('metroJourney')}
            if coll == 'socs':
                enrich[coll][n]['geoPrecision'] = precision.get(n)
                if n in borrowed_from:
                    enrich[coll][n]['borrowedFrom'] = borrowed_from[n]
        for n in unres:
            # A society that borrowed its micro-market's position is not
            # "unresolved" any more; without this guard the fallback written
            # just above would be overwritten with nulls.
            if enrich[coll].get(n, {}).get('geo'):
                continue
            enrich[coll][n] = {'geo': None, 'drive': None, 'metro': None}
            if coll == 'socs':
                enrich[coll][n]['geoPrecision'] = precision.get(n)
    save_json(OUT, enrich)

    # ---- 5. patch
    print('\n[5/5] patching index.html')
    changed = patch_index(lines, areas, socs, enrich)
    patch_tables(hub_info, mstations)
    print('  metro journey fields: %d' % changed.get('mt', 0))
    print('  coordinates written: %d   kept existing: %d' % (changed['lat'], changed['kept_coords']))
    print('  drive-time fields:   %d' % changed['dt'])
    print('  metro fields:        %d' % changed['metro'])
    if locs:
        n_page = patch_localities(locs)
        print('  LOCALITIES written:  %d of %d cached (cap: %s)'
              % (n_page, len(locs), ', '.join(PLACE_TYPES)))
    print('  geoPrecision:        %d building, %d area, %d unset'
          % (sum(1 for v in precision.values() if v == 'building'),
             sum(1 for v in precision.values() if v == 'area'),
             sum(1 for v in precision.values() if not v)))

    # ---- report
    print('\n' + '=' * 62)
    hard = [n for n in s_un if not precision.get(n)]
    print('COULD NOT GEOCODE AT ALL (%d)' % (len(a_un) + len(hard)))
    for n in a_un:
        print('  AREA  %s   (kept the existing approximate coordinate)' % n)
    for n in hard:
        print('  SOC   %s' % n)
    fell = sorted(borrowed_from.items())
    print('\nSOCIETIES PLACED AT MICRO-MARKET LEVEL (%d)' % len(fell))
    for n, src_area in fell:
        print('  %-34s -> %s' % (n[:34], src_area))
    print('\nOUTSIDE THE BENGALURU BOX (%d areas, %d societies)'
          % (len(a_out), len(s_out)))
    for n, la, lo, dn in a_out:
        print('  AREA  %-28s %.4f,%.4f  %s' % (n[:28], la, lo, dn[:60]))
    for n, la, lo, dn in s_out:
        print('  SOC   %-28s %.4f,%.4f  %s' % (n[:28], la, lo, dn[:60]))
    print('=' * 62)


if __name__ == '__main__':
    main()
