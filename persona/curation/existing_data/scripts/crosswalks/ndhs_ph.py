#!/usr/bin/env python3
"""Crosswalk: Philippines NDHS 2022 (DHS recode) → observed 1290-dim fields.

Obtain the file yourself under DHS terms (free account, state a research
purpose): https://dhsprogram.com/data/ — the Philippines 2022 standard DHS.
A mirror exists at https://microdata.worldbank.org/index.php/catalog/5846.

Prefer the **household member recode (PR)** file. The women's (IR) file is
women 15-49 only, so it cannot carry a population margin; the PR file covers
every household member of both sexes at all ages, which is what makes NDHS
usable for `highest_education` and `socioeconomic_band` targets.

DHS recode names are standardised across every DHS survey worldwide, so this
module is written against the standard variables and accepts both the PR
(``hv*``) and IR/MR (``v*``) spellings. Confirm against the PH-2022 codebook on
arrival — the country-specific items (religion ``v130``, ethnicity ``v131``)
carry per-country code lists, so those are matched on decoded labels only and
never on raw numbers.

    python persona/curation/existing_data/scripts/microdata_to_jsonl.py \\
      --src persona/curation/existing_data/raw/ndhs_ph/PHPR82FL.DTA \\
      --out persona/curation/existing_data/raw/ndhs_ph/ndhs_ph.jsonl \\
      --check ndhs_ph

    python persona/curation/existing_data/scripts/run_pipeline.py \\
      --source persona/curation/existing_data/raw/ndhs_ph/ndhs_ph.jsonl \\
      --dataset persona/curation/existing_data/scripts/crosswalks/ndhs_ph.py \\
      --schema persona/schema/dimensions.json \\
      --out persona/curation/existing_data/raw/ndhs_ph/extraction_v1/shard_00.jsonl.gz \\
      --observed-only

NDHS is a **sample**, not a census. Any target derived from it must be
weighted, or it describes the sample design rather than the Philippines:

    python persona/curation/existing_data/scripts/derive_targets_ph.py ... \\
      --weight-col hv005      # v005 on the IR/MR file

Two deliberate gaps, both documented at their mapping below: DHS tops education
out at "higher" with no degree detail, and it carries no province/city, so
urbanicity cannot reach Suburban the way ``psa_ph.py`` does. Run
``python crosswalks/ndhs_ph.py --selftest``.
"""

from __future__ import annotations

NCR_TOKENS = {
    "ncr",
    "national capital region",
    "metro manila",
    "metropolitan manila",
    "manila",
}

# DHS reserves the top of each numeric range for "don't know" / missing. On
# hv105 that is 98/99 against a real range of 0-95, so an unguarded cast turns
# a refusal into a 98-year-old.
DHS_MISSING_AGE = 96

TAGALOG_HOME = {
    "tagalog",
    "filipino",
    "pilipino",
    "filipino/tagalog",
    "tagalog/filipino",
}

CHRISTIAN_RELIGION = {
    "roman catholic",
    "catholic",
    "protestant",
    "iglesia ni cristo",
    "inc",
    "aglipay",
    "aglipayan",
    "philippine independent church",
    "iglesia filipina independiente",
    "born again",
    "evangelical",
    "baptist",
    "methodist",
    "seventh day adventist",
    "seventh-day adventist",
    "jehovah's witness",
    "jehovahs witness",
    "christian",
    "other christian",
}

SEA_ETHNICITY = {
    "tagalog",
    "cebuano",
    "bisaya",
    "binisaya",
    "ilocano",
    "ilokano",
    "hiligaynon",
    "ilonggo",
    "bicol",
    "bikol",
    "bicolano",
    "waray",
    "kapampangan",
    "pampango",
    "pangasinan",
    "pangasinense",
    "maranao",
    "maguindanao",
    "tausug",
    "boholano",
    "ibanag",
    "zamboangueno",
    "filipino",
}


def _token(row, *keys):
    for key in keys:
        v = row.get(key)
        if v is None:
            continue
        try:
            if v != v:
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(v, bool):
            return str(v).lower()
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        if isinstance(v, int):
            return str(v)
        s = str(v).strip().lower()
        if s and s not in {"nan", "none", "null", ""}:
            return s
    return None


def _alias_src_fields(row):
    out = dict(row)
    aliases = {
        # PR (household member) first, then IR/MR, then upper-case variants.
        "AGE": ("hv105", "HV105", "v012", "V012", "age"),
        "SEX": ("hv104", "HV104", "v151", "V151", "sex"),
        "URBAN": ("hv025", "HV025", "v025", "V025"),
        "REGION": ("hv024", "HV024", "v024", "V024", "region"),
        # hv109/v149 are the harmonised attainment items and are strictly more
        # informative than the hv106/v106 level items, so they win.
        "EDUC": ("hv109", "HV109", "v149", "V149", "hv106", "HV106", "v106", "V106"),
        "WEALTH": ("hv270", "HV270", "v190", "V190"),
        "MSTAT": ("hv115", "HV115", "v501", "V501"),
        "CHILDREN": ("v218", "V218"),
        "RELIGION": ("v130", "V130", "sh_religion", "religion"),
        "ETHNICITY": ("v131", "V131", "ethnicity"),
        "LANGUAGE": ("v045c", "V045C", "v045b", "V045B", "language"),
        "WEIGHT": ("hv005", "HV005", "v005", "V005"),
    }
    for dest, sources in aliases.items():
        if out.get(dest) is not None:
            continue
        for src in sources:
            if out.get(src) is not None:
                out[dest] = out[src]
                break
    return out


def flatten(row):
    out = _alias_src_fields(row)
    uid = row.get("user_id") or row.get("caseid") or row.get("CASEID")
    if uid is None:
        # PR rows are identified by household id + line number, not one column.
        hh = row.get("hhid") or row.get("HHID")
        line = row.get("hvidx") or row.get("HVIDX")
        if hh is not None and line is not None:
            uid = f"{str(hh).strip()}-{line}"
    if uid is not None:
        out["user_id"] = str(uid)
    return out


def render(row):
    bits = ["Philippines NDHS 2022 household member"]
    age = _token(row, "AGE")
    if age:
        bits.append(f"age {age}")
    sex = _token(row, "SEX")
    if sex:
        bits.append(str(sex))
    region = _token(row, "REGION")
    if region:
        bits.append(f"region {region}")
    return ", ".join(bits) + "."


def _age_bracket(row):
    raw = row.get("AGE")
    if raw is None:
        return None
    try:
        if raw != raw:
            return None
        age = float(raw)
    except (TypeError, ValueError):
        return None
    # 96-99 are DHS don't-know / missing codes, not ages.
    if age < 0 or age >= DHS_MISSING_AGE:
        return None
    if age < 5:
        return "Under 5"
    if age <= 12:
        return "5-12"
    if age <= 17:
        return "13-17"
    for lo, hi, lab in (
        (18, 24, "18-24"),
        (25, 34, "25-34"),
        (35, 44, "35-44"),
        (45, 54, "45-54"),
        (55, 64, "55-64"),
        (65, 74, "65-74"),
        (75, 84, "75-84"),
    ):
        if lo <= age <= hi:
            return lab
    return "85+"


def _region(_row):
    return "Southeast Asia"


def _cult_philippines(_row):
    return "Native"


def _is_ncr(row):
    token = _token(row, "REGION")
    return token in NCR_TOKENS if token else False


def _urbanicity(row):
    if _is_ncr(row):
        return "Dense urban"
    urb = _token(row, "URBAN")
    if urb in {"2", "rural"}:
        return "Rural"
    if urb in {"1", "urban"}:
        # Unlike psa_ph.py there is no province/city column here, so the HUC and
        # commuter-belt rules cannot run and Suburban is unreachable from DHS.
        return "Small town"
    return None


def _education(row):
    token = _token(row, "EDUC")
    if token is None:
        return None
    labeled = {
        "no education": "No formal",
        "no education, preschool": "No formal",
        "none": "No formal",
        "preschool": "No formal",
        "incomplete primary": "Primary",
        "complete primary": "Primary",
        "primary": "Primary",
        "elementary": "Primary",
        "incomplete secondary": "Secondary",
        "complete secondary": "Secondary",
        "secondary": "Secondary",
        "high school": "Secondary",
    }
    if token in labeled:
        return labeled[token]
    # DHS "higher" means any post-secondary and carries no degree detail, so it
    # cannot be split across Some college / Bachelor's / Master's / Doctorate.
    # Left unobserved rather than collapsed onto one of them — but note this
    # censors the top of the distribution, so CPH's HGC remains the better
    # source for a highest_education margin.
    if token in {"higher", "tertiary", "college", "university"}:
        return None
    try:
        n = int(float(token))
    except (TypeError, ValueError):
        return None
    # hv109 / v149: 0 none, 1 incomplete primary, 2 complete primary,
    # 3 incomplete secondary, 4 complete secondary, 5 higher, 8/9 dk/missing.
    return {0: "No formal", 1: "Primary", 2: "Primary", 3: "Secondary", 4: "Secondary"}.get(n)


def _socioeconomic_band(row):
    token = _token(row, "WEALTH")
    if token is None:
        return None
    # DHS wealth index is a within-country relative quintile and the schema band
    # is likewise relative, so this is a direct 1:1.
    return {
        "1": "Low income",
        "poorest": "Low income",
        "2": "Lower-middle",
        "poorer": "Lower-middle",
        "3": "Middle",
        "middle": "Middle",
        "4": "Upper-middle",
        "richer": "Upper-middle",
        "5": "High income",
        "richest": "High income",
    }.get(token)


def _children(row):
    raw = row.get("CHILDREN")
    if raw is None:
        return None
    try:
        if raw != raw:
            return None
        n = int(float(raw))
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    if n == 0:
        return "None"
    if n == 1:
        return "1 child"
    if n == 2:
        return "2 children"
    return "3+ children"


def _religion(row):
    token = _token(row, "RELIGION")
    if token is None:
        return None
    # v130 codes are country-specific, so only decoded labels are trusted here.
    if token.isdigit():
        return None
    if token in {"no religion", "none", "atheist"}:
        return "None"
    if token in {"islam", "muslim"}:
        return "Muslim"
    if token in {"buddhist", "buddhism"}:
        return "Buddhist"
    if token in {"hindu", "hinduism"}:
        return "Hindu"
    if "tribal" in token or token in {"animist", "indigenous"}:
        return "Folk / traditional"
    if token in CHRISTIAN_RELIGION or "catholic" in token or "christian" in token:
        return "Christian"
    return None


def _ethnicity(row):
    token = _token(row, "ETHNICITY")
    if token is None or token.isdigit():
        return None
    if "chinese" in token:
        return "East Asian"
    return "Southeast Asian" if token in SEA_ETHNICITY else None


def _lang_tagalog(row):
    return "Native" if _token(row, "LANGUAGE") in TAGALOG_HOME else None


def _english_proficiency(row):
    return "Native" if _token(row, "LANGUAGE") == "english" else None


CROSSWALK = {
    "age_bracket": {"compute": _age_bracket, "prov": "observed"},
    "gender_identity": {
        "src": "SEX",
        "map": {"1": "Man", "male": "Man", "2": "Woman", "female": "Woman"},
        "prov": "observed",
    },
    "region": {"compute": _region, "prov": "observed"},
    "cult_philippines": {"compute": _cult_philippines, "prov": "observed"},
    "urbanicity": {"compute": _urbanicity, "prov": "observed"},
    "highest_education": {"compute": _education, "prov": "observed"},
    "socioeconomic_band": {"compute": _socioeconomic_band, "prov": "observed"},
    "demo_marital_status": {
        "src": "MSTAT",
        "map": {
            "0": "Single",
            "never married": "Single",
            "never in union": "Single",
            "1": "Married",
            "married": "Married",
            "2": "Domestic partnership",
            "living together": "Domestic partnership",
            "living with partner": "Domestic partnership",
            "3": "Widowed",
            "widowed": "Widowed",
            "4": "Divorced",
            "divorced": "Divorced",
            "5": "Separated",
            "separated": "Separated",
            "no longer living together/separated": "Separated",
        },
        "prov": "observed",
    },
    "demo_children_count": {"compute": _children, "prov": "observed"},
    "demo_religion_affiliation": {"compute": _religion, "prov": "observed"},
    "demo_ethnicity_broad": {"compute": _ethnicity, "prov": "observed"},
    "lang_tagalog": {"compute": _lang_tagalog, "prov": "observed"},
    "english_proficiency": {"compute": _english_proficiency, "prov": "observed"},
}


def _selftest():
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from crosswalk_engine import apply_crosswalk, load_allowed

    schema = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "schema", "dimensions.json")
    )
    allowed = load_allowed(schema)

    # PR file, numeric codes (convert_categoricals=False)
    pr = flatten(
        {
            "hhid": "  001  002",
            "hvidx": 3,
            "hv105": 41,
            "hv104": 2,
            "hv024": "National Capital Region",
            "hv025": 1,
            "hv109": 4,
            "hv270": 5,
            "hv115": 1,
            "hv005": 1_234_567,
        }
    )
    obs, prov, unmapped = apply_crosswalk(pr, CROSSWALK, allowed)
    assert obs["age_bracket"] == "35-44", obs
    assert obs["gender_identity"] == "Woman"
    assert obs["region"] == "Southeast Asia"
    assert obs["cult_philippines"] == "Native"
    assert obs["urbanicity"] == "Dense urban"  # NCR
    assert obs["highest_education"] == "Secondary"
    assert obs["socioeconomic_band"] == "High income"
    assert obs["demo_marital_status"] == "Married"
    assert unmapped == {}
    assert all(p == "observed" for p in prov.values())
    assert pr["user_id"] == "001  002-3"

    # IR file, decoded labels
    ir = flatten(
        {
            "caseid": "        1  2  3",
            "v012": 28,
            "v151": "female",
            "v024": "Central Visayas",
            "v025": "rural",
            "v149": "higher",
            "v190": "poorest",
            "v501": "living together",
            "v218": 2,
            "v130": "Roman Catholic",
            "v131": "Cebuano",
            "v045c": "Tagalog",
        }
    )
    obs2, _, _ = apply_crosswalk(ir, CROSSWALK, allowed)
    assert obs2["age_bracket"] == "25-34"
    assert obs2["urbanicity"] == "Rural"
    assert obs2["socioeconomic_band"] == "Low income"
    assert obs2["demo_marital_status"] == "Domestic partnership"
    assert obs2["demo_children_count"] == "2 children"
    assert obs2["demo_religion_affiliation"] == "Christian"
    assert obs2["demo_ethnicity_broad"] == "Southeast Asian"
    assert obs2["lang_tagalog"] == "Native"
    # "higher" carries no degree detail, so it must not be guessed
    assert "highest_education" not in obs2

    # DHS missing/DK codes must not become ages or categories
    dk = flatten({"hv105": 98, "hv104": 9, "hv025": 9, "hv109": 8, "hv270": 9})
    obs3, _, _ = apply_crosswalk(dk, CROSSWALK, allowed)
    assert "age_bracket" not in obs3, obs3
    assert "gender_identity" not in obs3
    assert "urbanicity" not in obs3
    assert "highest_education" not in obs3
    assert "socioeconomic_band" not in obs3

    # country-specific numeric codes must never be read as labels
    numeric = flatten({"hv105": 30, "v130": 1, "v131": 2})
    obs4, _, _ = apply_crosswalk(numeric, CROSSWALK, allowed)
    assert "demo_religion_affiliation" not in obs4
    assert "demo_ethnicity_broad" not in obs4

    # urban outside NCR is Small town; Suburban is unreachable from DHS
    urban = flatten({"hv105": 30, "hv024": "Calabarzon", "hv025": 1})
    obs5, _, _ = apply_crosswalk(urban, CROSSWALK, allowed)
    assert obs5["urbanicity"] == "Small town"

    print(f"ndhs_ph crosswalk self-test: {len(CROSSWALK)} dims verified ✅")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Philippines NDHS 2022 (DHS recode) crosswalk.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        ap.print_help()
