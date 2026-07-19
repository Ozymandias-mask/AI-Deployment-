"""
Alternative to 2_annotate.py when no API key is available.
Generates annotations using a curated entity gazetteer + exact string search.
This simulates the LLM pre-annotation step and produces valid spaCy training data.

For the real pipeline with a live LLM, use 2_annotate.py instead.
"""

import json
import re
from pathlib import Path

# ── Entity gazetteer ──────────────────────────────────────────────────────────
# Patterns are searched as exact substrings (case-sensitive).
# Longer variants listed first to prevent partial matches.

WEAPONS = [
    # Cruise & hypersonic missiles
    "Kh-47M2 Kinzhal", "9M730 Burevestnik", "RS-28 Sarmat", "2M39 Poseidon",
    "Kinzhal", "Zircon", "Burevestnik", "Sarmat", "Avangard",
    "Kalibr-PL", "Kalibr-NK", "Kalibr", "Kh-101", "Kh-22", "Kh-35", "Kh-59",
    "Iskander-K", "Iskander-M", "Iskander",
    "Tochka-U", "ATACMS", "Storm Shadow", "Scalp",
    # Rocket artillery
    "BM-30 Smerch", "Tornado-S", "Tornado-G", "BM-21 Grad", "HIMARS", "M270 MLRS",
    # Coastal / naval missiles
    "Neptune", "Bastion", "Bal",
    # Precision munitions
    "Excalibur", "Krasnopol-M2", "Krasnopol", "HARM",
    # Tanks
    "T-14 Armata", "T-90M Proryv", "T-90M", "T-80BVM", "T-72B3M", "T-72B3",
    "T-72", "Leopard 2A6", "Leopard 2A4", "Leopard 2", "Leopard 1A5",
    "M1A1 Abrams", "M1 Abrams",
    # IFVs & APCs
    "M2A2 Bradley", "Bradley IFV", "Bradley", "BMP-3", "BMP-2", "Stryker", "M113",
    # Thermobaric / engineering
    "TOS-1A Solntsepyok", "TOS-1A", "UR-77 Meteorit", "BMPT Terminator", "Terminator",
    # Fixed-wing aircraft
    "Su-57", "Su-35S", "Su-35", "Su-34", "Su-30SM", "Su-30", "Su-27SM3", "Su-27",
    "Su-25SM3", "Su-25", "Su-24M", "Su-24",
    "MiG-31K", "MiG-31BM", "MiG-31", "MiG-29",
    "Tu-22M3", "Tu-22M", "Tu-95MS", "Tu-95",
    "F-16 Fighting Falcon", "F-16", "F-35A", "F-35",
    "A-50U", "A-50",
    # Rotary-wing
    "Ka-52M", "Ka-52 Alligator", "Ka-52",
    "Mi-28NM Night Hunter", "Mi-28NM", "Mi-28",
    "Mi-8AMTSh", "Mi-8MTV-5", "Mi-8", "Mi-35M", "Mi-35",
    # Drones / loitering munitions
    "Bayraktar TB2", "Bayraktar",
    "Lancet-3", "Lancet",
    "Geran-2", "Geran",
    "Shahed-136", "Shahed",
    "Orlan-30", "Orlan-10", "Orlan",
    "Orion", "Forpost-R",
    "Mugin-5",
    # Air defense (Russian)
    "S-500 Prometheus", "S-400 Triumf", "S-400",
    "S-350E Poliment-Redut", "S-300V4", "S-300",
    "Buk-M3", "Buk-M2", "Buk",
    "Tor-M2DT", "Tor-M2", "Tor",
    "Pantsir-S2", "Pantsir-S1M", "Pantsir-S1", "Pantsir",
    # Air defense (Western)
    "Patriot PAC-3", "Patriot", "NASAMS", "IRIS-T SLM", "IRIS-T", "SAMP/T",
    "Gepard", "HAWK", "Stinger MANPADS", "Stinger",
    # Artillery
    "2S35 Koalitsiya-SV", "Koalitsiya-SV",
    "2S19 Msta-S", "Msta-S",
    "2S43 Malva", "2S7M Malka",
    "2S3 Akatsiya", "2S1 Gvozdika",
    "M777", "Panzerhaubitze 2000", "Caesar",
    # Infantry AT
    "Javelin", "NLAW", "Kornet", "AT4", "Carl Gustaf", "Ataka",
    # Ships
    "Admiral Gorshkov", "Raptor",
    # Electronic warfare
    "Krasukha-4", "Murmansk-BN",
    # Small arms / misc
    "Dragunov", "Kalashnikov", "AK-12",
    "MLRS", "RPG",
]

# ── Regex patterns for flexible MIL_UNIT detection ───────────────────────────
# Applied after exact gazetteer matching
MIL_UNIT_PATTERNS = [
    # Russian battlegroups (main TASS terminology for operational groups)
    r"Battlegroup (?:North|West|East|South|Center|Centre|Dnepr|Dnipro)",
    # Numbered formations
    r"\d+(?:st|nd|rd|th) (?:Guards )?(?:Combined Arms|Tank|Air|Airborne|Assault|Motor Rifle|Mechanized|Naval Infantry|Separate) (?:Army|Brigade|Division|Corps|Regiment|Battalion)",
    # Named units without number
    r"(?:Guards )?(?:\w+ ){0,2}(?:Tank|Airborne|Assault|Mechanized|Naval Infantry|Marine|Airmobile|Special Forces|Territorial Defense) (?:Army|Brigade|Division|Corps|Regiment|Battalion|Group)",
]

MIL_UNITS = [
    # Russian operational groups (key TASS terminology)
    "Battlegroup North", "Battlegroup West", "Battlegroup South",
    "Battlegroup Center", "Battlegroup Centre", "Battlegroup East",
    "Battlegroup Dnepr", "Battlegroup Dnipro",
    "joint group of forces",
    # Russian armies / corps
    "1st Guards Tank Army", "2nd Guards Combined Arms Army",
    "3rd Army Corps", "4th Guards Tank Division",
    "6th Combined Arms Army", "8th Guards Combined Arms Army",
    "20th Guards Combined Arms Army", "22nd Army Corps",
    "35th Combined Arms Army", "41st Combined Arms Army",
    "49th Combined Arms Army", "58th Combined Arms Army",
    "90th Guards Tank Division",
    # Airborne / Special Forces
    "7th Guards Mountain Air Assault Division",
    "11th Guards Air Assault Brigade", "31st Guards Air Assault Brigade",
    "45th Guards Special Forces Regiment",
    # DPR / LPR
    "1st Army Corps", "1st Donetsk Corps", "2nd Army Corps",
    "100th Separate Motor Rifle Brigade", "114th Motorized Rifle Brigade",
    # Naval Infantry
    "810th Naval Infantry Brigade", "40th Naval Infantry Brigade",
    "155th Guards Naval Infantry Brigade", "155th Naval Infantry Brigade",
    # Ukrainian units
    "47th Mechanized Brigade", "93rd Mechanized Brigade", "25th Airborne Brigade",
    "79th Air Assault Brigade", "46th Airmobile Brigade",
    "72nd Mechanized Brigade", "65th Mechanized Brigade",
    "33rd Mechanized Brigade", "24th Mechanized Brigade",
    "56th Motorized Infantry Brigade", "57th Motorized Infantry Brigade",
    "53rd Mechanized Brigade", "110th Mechanized Brigade",
    "3rd Assault Brigade", "3rd Separate Assault Brigade", "5th Assault Brigade",
    "10th Army Corps", "27th Artillery Brigade", "28th Mechanized Brigade",
    "126th Territorial Defense Brigade", "125th Territorial Defense Brigade",
]

MIL_ORGS = [
    # Russian — specific first, then shorter
    "Russian Ministry of Defense", "Ministry of Defense of the Russian Federation",
    "Russia's Defense Ministry", "Russia's Ministry of Defense",
    "Russian Aerospace Defense Forces", "Russian Aerospace Forces",
    "Aerospace Forces",
    "General Staff of the Russian Armed Forces", "Russian General Staff",
    "Chief of the General Staff", "General Staff",
    "Russian Airborne Forces", "Russian Ground Forces", "Russian Armed Forces",
    "Armed Forces of Russia",
    "Russian National Guard", "Rosgvardia",
    "Russian Navy", "Black Sea Fleet", "Northern Fleet", "Pacific Fleet",
    "Baltic Fleet", "Caspian Flotilla",
    "Russian Strategic Missile Forces", "Strategic Missile Forces",
    "Federal Security Service", "FSB",
    "Southern Military District", "Central Military District",
    "Western Military District", "Eastern Military District",
    "Northern Military Group",
    # Ukrainian
    "Ukrainian Ministry of Defense", "Ukraine's Defense Ministry",
    "Ukrainian Armed Forces", "Armed Forces of Ukraine",
    "Ukrainian Air Force", "Ukraine's Air Force",
    "Ukrainian Naval Forces", "Ukrainian Navy",
    # Alliances / international
    "NATO", "Allied Command Transformation",
    "Collective Security Treaty Organization", "CSTO",
    "Commonwealth of Independent States", "CIS",
    "Security Council",
    "OSCE",
    # Industry
    "Kalashnikov Group",
]


def find_all_occurrences(text: str, pattern: str) -> list[tuple[int, int]]:
    """Find all non-overlapping occurrences of pattern in text."""
    positions = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx == -1:
            break
        positions.append((idx, idx + len(pattern)))
        start = idx + 1
    return positions


def annotate_article(text: str) -> list[list]:
    """
    Find all entity occurrences in text.
    Returns sorted, non-overlapping spans [[start, end, label], ...]
    """
    candidates = []

    for weapon in WEAPONS:
        for s, e in find_all_occurrences(text, weapon):
            candidates.append((s, e, "WEAPON", weapon))

    for unit in MIL_UNITS:
        for s, e in find_all_occurrences(text, unit):
            candidates.append((s, e, "MIL_UNIT", unit))

    # Regex-based unit detection (catches numbered formations not in gazetteer)
    for pattern in MIL_UNIT_PATTERNS:
        for m in re.finditer(pattern, text):
            candidates.append((m.start(), m.end(), "MIL_UNIT", m.group()))

    for org in MIL_ORGS:
        for s, e in find_all_occurrences(text, org):
            candidates.append((s, e, "MIL_ORG", org))

    # Sort by start, then by length descending (prefer longer matches)
    candidates.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    # Greedy non-overlap selection
    result = []
    occupied: set[int] = set()
    for s, e, label, surface in candidates:
        span_chars = set(range(s, e))
        if span_chars & occupied:
            continue
        occupied |= span_chars
        result.append([s, e, label])

    return sorted(result, key=lambda x: x[0])


def main():
    corpus_path = Path("data/corpus.json")
    out_path    = Path("annotations/annotations.json")

    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    annotations = []
    from collections import Counter
    label_counts = Counter()

    for art in corpus:
        text     = art["text_clean"]
        entities = annotate_article(text)

        # Verify all offsets
        verified = []
        for s, e, label in entities:
            if text[s:e]:
                verified.append([s, e, label])
                label_counts[label] += 1

        annotations.append({
            "text":       text,
            "entities":   verified,
            "article_id": art["id"],
        })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)

    print(f"Annotations saved to {out_path}")
    print(f"Total entities: {sum(label_counts.values())}")
    for label in ["WEAPON", "MIL_UNIT", "MIL_ORG"]:
        print(f"  {label:<12}: {label_counts[label]}")

    # Quick sample verification
    print("\nSample annotations (article 001):")
    for s, e, label in annotations[0]["entities"][:8]:
        span = annotations[0]["text"][s:e]
        print(f"  [{s}:{e}] {label:<12} '{span}'")


if __name__ == "__main__":
    main()
