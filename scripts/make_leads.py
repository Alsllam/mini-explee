"""Generate a list of FICTIONAL companies to score in step 3.

Every name is made up from random syllables and every website ends in
".example" (a domain reserved for examples), so no real company or person
appears in the project. A fixed random seed gives the same 200 rows every time.

Run from the project root:
    python -m scripts.make_leads            # writes data/leads_sample.csv (200 rows)
    python -m scripts.make_leads --n 50 --seed 7
"""
import argparse
import csv
import random
from pathlib import Path

SYLLABLES = ["zar", "nub", "qal", "tem", "vor", "sad", "lum", "rak", "fen", "dor",
             "mir", "hax", "bel", "tis", "gor", "wan", "kel", "pru", "sol", "yam"]

# (industry, name suffix, weight) - weights give a realistic mix, not all fits.
INDUSTRIES = [
    ("Banking", "Bank", 14), ("Insurance", "Insurance", 8), ("Retail", "Retail Group", 12),
    ("Quick-service restaurants", "Foods", 8), ("Hospitality", "Hotels", 7),
    ("Government", "Authority", 8), ("Telecommunications", "Telecom", 6),
    ("Healthcare", "Health", 7), ("Logistics", "Logistics", 7), ("Education", "Academy", 5),
    ("Oil and gas", "Petroleum", 5), ("Construction", "Contracting", 6),
    ("Industrial manufacturing", "Industries", 5), ("Software", "Labs", 2),
]

COUNTRIES = [("Saudi Arabia", ["Riyadh", "Jeddah", "Dammam"], 35),
             ("United Arab Emirates", ["Dubai", "Abu Dhabi"], 20),
             ("Egypt", ["Cairo", "Alexandria"], 12), ("Kuwait", ["Kuwait City"], 6),
             ("Qatar", ["Doha"], 6), ("Jordan", ["Amman"], 6),
             ("Germany", ["Berlin", "Munich"], 5), ("United States", ["Austin", "Chicago"], 5),
             ("India", ["Bengaluru", "Pune"], 5)]

SIZES = [(15, 49), (50, 199), (200, 999), (1000, 4999), (5000, 30000)]

GOOD_SIGNALS = [
    "Active Arabic social media accounts",
    "Hiring a customer experience manager",
    "Recently launched a customer mobile app",
    "Many customer complaints visible on X",
    "Runs a 24/7 contact center",
    "Publishes an annual customer satisfaction report",
]
BAD_SIGNALS = [
    "No social media presence",
    "Sells only to other factories (B2B industrial)",
    "English-only website and support",
    "Recently cut marketing budget",
]


def weighted(rng, items):
    return rng.choices(items, weights=[w for *_, w in items], k=1)[0]


def company_name(rng, suffix):
    word = "".join(rng.choice(SYLLABLES) for _ in range(2)).capitalize()
    return f"{word} {suffix}"


def make_lead(rng, i, used_names):
    industry, suffix, _ = weighted(rng, INDUSTRIES)
    country, cities, _ = weighted(rng, COUNTRIES)
    low, high = rng.choice(SIZES)
    name = company_name(rng, suffix)
    while name in used_names:
        name = company_name(rng, suffix)
    used_names.add(name)
    consumer_facing = industry not in {"Oil and gas", "Construction", "Industrial manufacturing"}

    signals = rng.sample(GOOD_SIGNALS, k=rng.randint(0, 3)) if consumer_facing else []
    if rng.random() < (0.2 if consumer_facing else 0.7):
        signals.append(rng.choice(BAD_SIGNALS))

    audience = "consumers" if consumer_facing else "other businesses"
    article = "an" if industry[0].lower() in "aeiou" else "a"
    return {
        "lead_id": f"L{i:03d}",
        "company": name,
        "industry": industry,
        "country": country,
        "city": rng.choice(cities),
        "employees": rng.randint(low, high),
        "website": name.lower().replace(" ", "") + ".example",
        "description": f"{name} is {article} {industry.lower()} company in {country} serving {audience}.",
        "signals": "; ".join(signals),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate fictional leads.")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/leads_sample.csv")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    used: set[str] = set()
    rows = [make_lead(rng, i + 1, used) for i in range(args.n)]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} fictional leads to {out}")


if __name__ == "__main__":
    main()
