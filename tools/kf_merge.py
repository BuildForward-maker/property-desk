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
  10  the area sits on a funded alignment opening within a year (Blue Line
       Phase 2B, June 2027), OR metro runs today AND a funded line opens
       within 3 years
   8  metro runs today, nothing sooner committed
   6  a funded line opening within 3 years serves this corridor (suburban
       rail Corridor 2, December 2028)
   4  a funded line opening 3-6 years (suburban rail Corridors 1, 3 and 4,
       2029-2030), or funded and building with no published date (Pink Line,
       Blue Line Phase 2A)
   2  approved but unfunded (Red Line / Sarjapur)
   0  nothing committed
  +1  a major employment anchor under construction within 5 km
      (KIADB Aerospace Park, Devanahalli). Capped at 10.

What sets the band is which funded line SERVES an area, not how far it is
from a station that happens to already be running. Hebbal and Yelahanka have
no operational station within 4.9 km and 10.0 km respectively, and both score
10: they sit on the Blue Line 2B alignment, funded and dated June 2027, which
is why Knight Frank call North the fastest-growing corridor and why Yelahanka
went from 8% to 18%. A line eight months out is a stronger signal than a
mature line with nothing new coming, and the bands say so.

"Metro runs today" is still read off the enriched mkm — a station on an
operational line (Purple, Green, Yellow) within 2.0 km — because a station
inside the area is the one case where distance IS the alignment. Every funded
line is a named set instead.
"""
import re, sys, os

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
# H1 2024 is Knight Frank's own back-calculation from the stated 12-month
# change, reproduced from the data file rather than recomputed here.
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

# --------------------------------------------------------- infra pipeline sets
BLUE2B = {  # Blue Line Phase 2B, KR Puram - KIA, target June 2027
    'Hebbal', 'Sahakar Nagar', 'Jakkur', 'Yelahanka', 'Bagalur',
    'Shettigere', 'Devanahalli',
}
BLUE2A = {  # Blue Line Phase 2A, Central Silk Board - KR Puram, along the ORR.
            # Funded and building; the data file dates only 2B, so this scores
            # as 3-6 years rather than 3.
    'Marathahalli', 'Bellandur', 'Panathur / Balagere', 'Mahadevapura',
    'KR Puram', 'HSR Layout',
}
PINK = {   # Pink Line, Kalena Agrahara - Nagawara. Funded and building, no
           # published opening date, so it scores as 3-6 years, not 3.
           # Membership at the Nagawara end is every entry within 2.5 km of it
           # measured on our own coordinates, which is Thanisandra, Thanisandra
           # Main Road, Kothanur and Hennur Road. The last two only qualified
           # once their geocodes were corrected; before that Kothanur sat 20 km
           # south of where it belongs.
    'Nagawara / RT Nagar', 'Thanisandra', 'Thanisandra Main Road',
    'Kothanur / Kothnur', 'Hennur Road',
    'Frazer Town / Cooke Town', 'Sudhama Nagar', 'Arekere / Hulimavu',
}
SUB_C2 = {  # Corridor 2, Chikkabanavara - Yeshwanthpur - Bennigenahalli,
            # December 2028. Two years and two months out, so it counts as
            # within three years rather than beyond them.
    'Jalahalli', 'Yeshwanthpur', 'Mathikere / Sanjay Nagar',
    'Tumkur Road / Peenya', 'Banaswadi / Kammanahalli', 'Kasturi Nagar',
    'CV Raman Nagar', 'Horamavu', 'Hebbal',
}
SUB_LATER = {  # Corridors 4 (Mar 2029), 1 and 3 (Mar 2030)
    'Hosa Road', 'Kudlu / Kudlu Gate', 'Bommasandra / Chandapura',
    'Bommanahalli', 'Doddaballapur Road', 'Yelahanka', 'Jakkur',
    'Devanahalli', 'Shettigere',
    'Kengeri', 'Rajarajeshwari Nagar', 'Nagarbhavi', 'Mysore Road',
}
UNFUNDED = {  # Red Line / Sarjapur corridor: approved, awaiting clearance
    'Sarjapur Road', 'Sarjapur town', 'Harlur / Haralur',
    'Carmelaram / Dommasandra', 'HSR Layout',
}
ANCHOR = {'Devanahalli', 'Shettigere'}   # KIADB Aerospace Park, within 5 km

OPERATIONAL_KM = 2.0


def infra(name, mkm):
    """Returns (score, note). See the rubric in the module docstring."""
    live = mkm is not None and mkm <= OPERATIONAL_KM
    blue2b = name in BLUE2B            # on the alignment, June 2027
    soon = name in SUB_C2              # funded, December 2028
    later = name in SUB_LATER or name in PINK or name in BLUE2A

    if blue2b:
        base = 10
        why = ('On the Blue Line Phase 2B alignment, funded and opening June 2027'
               + (', with metro already running %.1f km away.' % mkm if live
                  else '. No metro runs here yet.'))
    elif live and soon:
        base = 10
        why = ('Metro running today, %.1f km away, and suburban rail Corridor 2 '
               'opens here December 2028.' % mkm)
    elif live:
        base, why = 8, 'Metro running today, %.1f km away. Nothing sooner committed.' % mkm
    elif soon:
        base = 6
        why = 'No metro yet; suburban rail Corridor 2 serves this corridor from December 2028.'
    elif later:
        if name in BLUE2A:
            why = 'Blue Line ORR section funded and building, no published opening date.'
        elif name in SUB_LATER and name in PINK:
            why = 'Suburban rail and the Pink Line both committed, neither before 2029.'
        elif name in SUB_LATER:
            why = 'Suburban rail committed on this corridor, 2029 to 2030.'
        else:
            why = 'Pink Line funded and building, no published opening date.'
        base = 4
    elif name in UNFUNDED:
        base, why = 2, 'Sarjapur corridor metro approved but unfunded and uncleared.'
    else:
        base = 0
        if mkm is not None and mkm <= 4.0:
            why = ('Nothing committed, and the nearest running metro is %.1f km away '
                   '\u2014 close, but not walkable.' % mkm)
        elif mkm is not None:
            why = 'No committed rail link; the nearest running metro is %.1f km away.' % mkm
        else:
            why = 'No committed rail link within reach.'
    if name in ANCHOR:
        return min(10, base + 1), why + ' KIADB Aerospace Park under construction within 5 km.'
    return base, why


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


def main():
    src = open(HTML, encoding='utf-8').read()
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
    infra_hist = {}
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
        isc, inote = infra(name, mkm)
        infra_hist[isc] = infra_hist.get(isc, 0) + 1

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
                    ',kfSeries:{y2024:%d,y2025:%d,y2026:%d}' % (mid(y24), mid(y25), mid(y26)),
                    ",dataTier:'verified'",
                    ",kfLoc:'%s'" % kfname[name],
                    ",scorePrecision:'verified+zone'"]
            report.append((name, kfz, py, g26, g25, trend, isc))
            # Part B: the verified reading replaces the portal one.
            ent = re.sub(r"(,py:)-?\d+", r"\g<1>%d" % g26, ent, count=1)
        else:
            add += [',growthPortal:%d' % py,
                    ',growth26:null,growth25:null',
                    ",trend:null,kfSeries:null",
                    ",dataTier:'portal'",
                    ",scorePrecision:'portal+zone'"]

        add += [',infraScore:%d' % isc,
                ",infraNote:'%s'" % inote.replace("'", "\\'"),
                ",kfSrc:'knightfrank',kfAsOf:'2026-06'"]

        ent = ent[:-1] + ''.join(add) + '}'
        out.append(blk[cursor:s] + ent)
        cursor = e
    out.append(blk[cursor:])

    missing = [o for (_k, o, *_r) in KFPRICE if o not in seen]
    if missing:
        sys.exit('These KF locations did not match an AREAS entry: %s' % missing)

    src = src[:a0] + ''.join(out) + src[a1:]
    open(HTML, 'w', encoding='utf-8').write(src)

    if remerged[0]:
        print('re-merged over a previous run: %d entries reset first' % remerged[0])
    print('verified: %d   portal: %d' % (len(report), len(seen) - len(report)))
    print()
    print('%-26s %-8s %5s %5s %5s  %-13s %s' % ('area', 'kfZone', 'was', '26', '25', 'trend', 'infra'))
    for r in sorted(report, key=lambda x: -(x[3] - x[4])):
        print('%-26s %-8s %5d %5d %5d  %-13s %d' % r)
    print()
    print('infra bands: ' + '  '.join(
        '%d:%d' % (b, infra_hist.get(b, 0)) for b in sorted(infra_hist)))


if __name__ == '__main__':
    main()
