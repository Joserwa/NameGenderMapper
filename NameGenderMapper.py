#!/usr/bin/env python3
"""
add_gender_improved.py
- Streaming, memory-friendly.
- Produces Gender, GenderConfidence (0..1), GenderSource columns.
- Creates ambiguous_first_names.csv for manual review.
"""

import csv, re, sys
from collections import defaultdict, Counter

# Optional dependency
try:
    from gender_guesser.detector import Detector as GGDetector
    GG_AVAILABLE = True
    gg = GGDetector()
except Exception:
    GG_AVAILABLE = False
    gg = None

# ---------- CONFIG ----------
GENDER_FILE = "referance-names.csv"   # your dataset to act as reference, this one has 2.1M entries
INPUT_FILE  = "file-to-sort.csv"             # your file you intend to add column of gender
OUTPUT_FILE = "people_with_gender.csv" # output file after adding gender
AUDIT_FILE  = "ambiguous_first_names.csv"
CONF_THRESHOLD = 0.65   # mapping confidence threshold to accept mapping (0..1)
MIN_COUNT_FOR_CONFIDENCE = 5  # names with fewer than this count are considered low-confidence
ENCODING = 'utf-8'
# ----------------------------

# Accept accented letters and apostrophes/hyphens in names (basic range)
_valid_chars_re = re.compile(r"[^A-Za-zÀ-ÖØ-öø-ÿ'\-\s]")

def detect_delimiter(path, sample_size=8192):
    with open(path, 'r', encoding=ENCODING, errors='replace') as f:
        sample = f.read(sample_size)
    candidates = [',','\t',';','|']
    return max(candidates, key=lambda c: sample.count(c))

def normalize_gender(g):
    if not g: return 'Unknown'
    s = str(g).strip().lower()
    if s == 'm' or s.startswith('m'): return 'M'
    if s == 'f' or s.startswith('f'): return 'F'
    return 'Unknown'

def get_first_name(full_name):
    if not full_name: return ''
    s = str(full_name).strip()
    s = _valid_chars_re.sub('', s)    # remove weird chars
    tokens = [t for t in s.split() if t]
    if not tokens:
        return ''
    # If first token is a single initial, take the next token if present and longer than 1
    if len(tokens[0]) == 1:
        if len(tokens) > 1 and len(tokens[1]) > 1:
            return tokens[1].lower()
        else:
            return ''   # e.g. "K N Johnson" -> unknown first name
    return tokens[0].lower()

def gg_guess(first):
    """Use gender-guesser if available. Returns (gender_letter, confidence_float)."""
    if not GG_AVAILABLE or not first:
        return ('Unknown', 0.0)
    g = gg.get_gender(first)  # categories: male, female, mostly_male, mostly_female, andy, unknown
    if g == 'male': return ('M', 1.0)
    if g == 'mostly_male': return ('M', 0.85)
    if g == 'female': return ('F', 1.0)
    if g == 'mostly_female': return ('F', 0.85)
    if g == 'andy': return ('Unknown', 0.5)
    return ('Unknown', 0.0)

print("Building mapping from gender reference...")
delim_g = detect_delimiter(GENDER_FILE)
print("Gender file delimiter:", repr(delim_g))

# We'll try to detect columns in the gender file: name, gender, optional country
name_idx = 0; gender_idx = 1; country_idx = None
counts_global = defaultdict(Counter)          # first -> Counter({'M':n,'F':n,'Unknown':n})
counts_by_country = defaultdict(lambda: defaultdict(Counter))  # country -> first -> Counter

with open(GENDER_FILE, newline='', encoding=ENCODING, errors='replace') as gf:
    reader = csv.reader(gf, delimiter=delim_g)
    first_row = next(reader, None)
    headers = []
    if first_row:
        lower = [c.strip().lower() for c in first_row]
        if 'name' in lower:
            headers = lower
            name_idx = lower.index('name')
            # find gender column
            for label in ('gender','sex'):
                if label in lower:
                    gender_idx = lower.index(label)
                    break
            # optional country
            if 'country' in lower:
                country_idx = lower.index('country')
        else:
            # assume default positions; treat first row as data
            name = first_row[name_idx] if len(first_row) > name_idx else ''
            gender = first_row[gender_idx] if len(first_row) > gender_idx else ''
            fname = get_first_name(name)
            if fname:
                counts_global[fname][normalize_gender(gender)] += 1

    for row in reader:
        if not row: continue
        name = row[name_idx] if len(row) > name_idx else ''
        gender = row[gender_idx] if len(row) > gender_idx else ''
        fname = get_first_name(name)
        if not fname: continue
        gnorm = normalize_gender(gender)
        counts_global[fname][gnorm] += 1
        if country_idx is not None:
            country = row[country_idx].strip().upper() if len(row) > country_idx else ''
            if country:
                counts_by_country[country][fname][gnorm] += 1

# Build final mapping with confidence
mapping = {}       # fname -> (gender, confidence, total_count)
mapping_country = {}  # (country, fname) -> (gender, confidence, total_count)

for fname, ctr in counts_global.items():
    total = sum(ctr.values())
    if total == 0:
        continue
    top_gender, top_count = ctr.most_common(1)[0]
    conf = top_count / total if total > 0 else 0.0
    # treat very small counts as low confidence
    if total < MIN_COUNT_FOR_CONFIDENCE and conf < 1.0:
        conf = conf * 0.7  # penalize low counts
    mapping[fname] = (top_gender, conf, total)

if counts_by_country:
    for country, d in counts_by_country.items():
        for fname, ctr in d.items():
            total = sum(ctr.values())
            if total == 0: continue
            top_gender, top_count = ctr.most_common(1)[0]
            conf = top_count / total
            if total < MIN_COUNT_FOR_CONFIDENCE and conf < 1.0:
                conf = conf * 0.7
            mapping_country[(country, fname)] = (top_gender, conf, total)

print("Mapping built for {} first names (global).".format(len(mapping)))
if mapping_country:
    print("Country-aware mapping built ({} entries).".format(len(mapping_country)))

# Process main file streaming, using mapping, country-aware mapping first, then fallback to gg.
print("Processing input file...")
delim_in = detect_delimiter(INPUT_FILE)
print("Input file delimiter:", repr(delim_in))

written = 0
stats = Counter()
ambiguous_rows = {}  # fname -> (top_gender, second_gender_count, total, conf)

with open(INPUT_FILE, newline='', encoding=ENCODING, errors='replace') as inf, \
     open(OUTPUT_FILE, 'w', newline='', encoding=ENCODING) as outf:
    reader = csv.reader(inf, delimiter=delim_in)
    writer = csv.writer(outf, delimiter=delim_in)

    header = next(reader, None)
    if header:
        writer.writerow(header + ['Gender','GenderConfidence','GenderSource'])
    else:
        writer.writerow(['Name','Country','Address','City','State','Zip','Phone Number','Gender','GenderConfidence','GenderSource'])

    for row in reader:
        if not row: 
            continue
        # skip repeated header lines inside file
        if row[0].strip().lower() == 'name':
            continue

        name = row[0]
        country = row[1].strip().upper() if len(row) > 1 else ''
        fname = get_first_name(name)
        chosen_gender = 'Unknown'
        chosen_conf = 0.0
        source = 'unknown'

        # prefer country-specific mapping if available
        if fname:
            if (country, fname) in mapping_country:
                g, conf, total = mapping_country[(country, fname)]
                if conf >= CONF_THRESHOLD:
                    chosen_gender, chosen_conf, source = g, conf, 'country-mapped'
                else:
                    # keep as candidate but might be overridden
                    cand_g, cand_conf = g, conf
                    # fallback block continues below
            elif fname in mapping:
                g, conf, total = mapping[fname]
                if conf >= CONF_THRESHOLD:
                    chosen_gender, chosen_conf, source = g, conf, 'mapped'
                else:
                    cand_g, cand_conf = g, conf

        # if not decided by mapping, try gender-guesser if available
        if chosen_gender == 'Unknown' and fname:
            # prefer gender-guesser if mapping is missing or low confidence
            use_gg = False
            if fname not in mapping:
                use_gg = True
            else:
                # mapping exists but confidence low
                if mapping[fname][1] < CONF_THRESHOLD:
                    use_gg = True
            if use_gg and GG_AVAILABLE:
                gg_g, gg_conf = gg_guess(fname)
                # if gg gives decent confidence (>=0.85) use it; or if gg_conf > cand_conf use it
                cand_conf = mapping[fname][1] if fname in mapping else 0.0
                if gg_conf >= 0.85 or gg_conf > cand_conf:
                    chosen_gender, chosen_conf, source = gg_g, gg_conf, 'gender-guesser'
                elif fname in mapping:
                    # use candidate mapping if it is better than gg
                    if cand_conf > gg_conf:
                        chosen_gender, chosen_conf, source = mapping[fname][0], cand_conf, 'mapped'
            else:
                # no gg available; accept low-confidence mapping if present
                if fname in mapping:
                    chosen_gender, chosen_conf, source = mapping[fname][0], mapping[fname][1], 'mapped'

        if chosen_gender == 'Unknown' and fname and fname in mapping:
            # final fallback to mapping's top choice
            chosen_gender, chosen_conf, source = mapping[fname][0], mapping[fname][1], 'mapped'

        # if still unknown, remain Unknown.
        writer.writerow(row + [chosen_gender, "{:.3f}".format(chosen_conf), source])
        written += 1
        stats[source] += 1
        if written % 200000 == 0:
            print("Processed", written, "rows...")

print("Done. Output saved to:", OUTPUT_FILE)
print("Rows processed:", written)
print("Breakdown by source:", dict(stats))

# Write ambiguous first names for manual inspection: low confidence or low count or near-ties
print("Generating audit file:", AUDIT_FILE)
with open(AUDIT_FILE, 'w', newline='', encoding=ENCODING) as af:
    aw = csv.writer(af)
    aw.writerow(['first_name','top_gender','top_count','second_count','total_count','confidence'])
    for fname, ctr in counts_global.items():
        total = sum(ctr.values())
        if total == 0:
            continue
        most = ctr.most_common()
        top_gender, top_count = most[0]
        second_count = most[1][1] if len(most) > 1 else 0
        conf = top_count / total
        # flag if low total, low conf, or near tie
        if total < 50 or conf < 0.7 or (len(most) > 1 and (top_count - second_count) < 3):
            aw.writerow([fname, top_gender, top_count, second_count, total, "{:.3f}".format(conf)])

print("Audit file written. Inspect ambiguous_first_names.csv to correct or override names manually.")
if not GG_AVAILABLE:
    print("Note: gender-guesser not available. To enable fallback install: pip install gender-guesser")
