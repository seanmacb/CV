#!/usr/bin/env python3
"""
Fetch all publications from a Google Scholar profile and export them as BibTeX entries.

Usage:
    python scholar_to_bibtex.py "https://scholar.google.com/citations?user=XXXXXXX" -o output.bib
    python scholar_to_bibtex.py XXXXXXX -o output.bib

Requires:
    pip install scholarly
"""

import argparse
import re
import sys
import time
from urllib.parse import urlparse, parse_qs

from scholarly import scholarly, ProxyGenerator


def extract_scholar_id(profile: str) -> str:
    """Extract the Google Scholar user ID from a profile URL, or return the input as-is if it's already an ID."""
    if "scholar.google" in profile:
        parsed = urlparse(profile)
        qs = parse_qs(parsed.query)
        if "user" in qs:
            return qs["user"][0]
        raise ValueError(f"Could not find a 'user' parameter in URL: {profile}")
    return profile.strip()


def setup_proxy():
    """Optional: route requests through a free proxy pool to reduce the chance of being rate-limited/blocked."""
    pg = ProxyGenerator()
    success = pg.FreeProxies()
    if success:
        scholarly.use_proxy(pg)
        print("Proxy configured.")
    else:
        print("Warning: could not configure a free proxy, continuing without one.", file=sys.stderr)


def infer_entry_type(bib: dict) -> str:
    """Guess a BibTeX entry type from the fields Google Scholar gave us.

    Publications filled from an author profile (as opposed to a search
    result) never get a 'pub_type'/'ENTRYTYPE' field set by scholarly,
    which makes scholarly.bibtex() raise KeyError: 'ENTRYTYPE'. We fill
    in a reasonable guess ourselves.
    """
    if "conference" in bib:
        return "inproceedings"
    if "journal" in bib:
        return "article"
    return "misc"


def make_citation_key(bib: dict, fallback: str) -> str:
    """Build a simple 'lastnameYEARfirstword' citation key."""
    author = bib.get("author", "")
    first_author_last = author.split(" and ")[0].split()[-1] if author else "unknown"
    year = str(bib.get("pub_year", "")) or "n.d."
    title_word = re.sub(r"[^A-Za-z0-9]", "", bib.get("title", "").split()[0]) if bib.get("title") else fallback
    return f"{first_author_last}{year}{title_word}".lower()


def truncate_authors(author_field: str, my_name: str, max_authors: int) -> str:
    """Shorten a long BibTeX author list to '<first authors>, ..., <you>, and others'.

    Standard .bst styles (plain/unsrt/abbrv) render a literal trailing
    'others' entry as "et al." automatically -- no custom .bst needed.
    Keeps the first `max_authors` names, and makes sure `my_name` stays
    visible even if their position in the full list would otherwise get
    cut off (common on large-collaboration papers). Wherever it appears,
    it's shown as `my_name` (your canonical Scholar profile name) rather
    than whatever spelling variant that particular paper's byline used
    (e.g. "Sean Macbride" or "Sean Patrick MacBride"), so the name reads
    consistently across the whole publication list -- but it still stays
    at its original position in the sequence, not moved to the front.
    """
    authors = [a.strip() for a in author_field.split(" and ") if a.strip()]
    if len(authors) <= max_authors:
        return author_field  # short enough already, nothing to do

    my_name_norm = my_name.strip().lower()
    my_last = my_name_norm.split()[-1] if my_name_norm else ""

    my_index = None
    for idx, name in enumerate(authors):
        name_norm = name.lower()
        if name_norm == my_name_norm or (my_last and my_last in name_norm):
            my_index = idx
            break

    kept = authors[:max_authors]
    if my_index is not None:
        if my_index < max_authors:
            kept[my_index] = my_name
        else:
            kept.append(my_name)
    kept.append("others")
    return " and ".join(kept)


def load_skip_patterns(skip_file: str, skip_args: list) -> list:
    """Build the list of skip patterns from a file (one per line, '#' comments allowed) and/or --skip flags."""
    patterns = []
    if skip_file:
        with open(skip_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    if skip_args:
        patterns.extend(skip_args)
    return patterns


def matching_skip_pattern(title: str, venue: str, patterns: list):
    """Return the first pattern that matches (case-insensitive substring of title or venue), or None."""
    haystack = f"{title} {venue}".lower()
    for pattern in patterns:
        if pattern.lower() in haystack:
            return pattern
    return None


def fetch_bibtex_entries(scholar_id: str, delay: float = 1.5, max_authors: int = None, my_name: str = None,
                          skip_patterns: list = None):
    """Fetch every publication for the given scholar ID and yield BibTeX strings one at a time."""
    print(f"Looking up author profile: {scholar_id}")
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=["publications"])

    total = len(author["publications"])
    profile_name = author.get("name", scholar_id)
    print(f"Found {total} publications for {profile_name}.")

    if max_authors is not None and not my_name:
        my_name = profile_name

    for i, pub in enumerate(author["publications"], start=1):
        title = pub.get("bib", {}).get("title", "Unknown title")
        venue = pub.get("bib", {}).get("citation", "")

        matched = matching_skip_pattern(title, venue, skip_patterns or [])
        if matched:
            print(f"[{i}/{total}] Skipping (matched '{matched}'): {title}")
            continue

        print(f"[{i}/{total}] Fetching: {title}")
        try:
            filled = scholarly.fill(pub)
            # scholarly.bibtex() requires 'pub_type' and 'bib_id' fields that
            # fill() never sets when the publication came from an author
            # profile (only search results get them) -- so supply them here.
            filled["bib"].setdefault("pub_type", infer_entry_type(filled["bib"]))
            filled["bib"].setdefault("bib_id", make_citation_key(filled["bib"], fallback=f"pub{i}"))
            if "pub_year" in filled["bib"]:
                # scholarly.bibtex() doesn't rename this one, but every standard
                # .bst style expects the field to be called 'year', not 'pub_year'
                # -- otherwise the year is silently dropped from the output.
                filled["bib"]["year"] = filled["bib"].pop("pub_year")
            if "conference" in filled["bib"]:
                # Same issue: standard inproceedings entries expect 'booktitle',
                # not 'conference', or the venue is silently dropped.
                filled["bib"]["booktitle"] = filled["bib"].pop("conference")
            if max_authors is not None and "author" in filled["bib"]:
                original = filled["bib"]["author"]
                filled["bib"]["author"] = truncate_authors(original, my_name, max_authors)
                if my_name.lower().split()[-1] not in original.lower() and len(original.split(" and ")) > max_authors:
                    print(f"  -> Note: couldn't find '{my_name}' in the author list for '{title}'; truncated without it.", file=sys.stderr)
            bibtex = scholarly.bibtex(filled)
            yield bibtex
        except Exception as e:
            print(f"  -> Failed to fetch BibTeX for '{title}': {e}", file=sys.stderr)
        time.sleep(delay)  # be polite to Google Scholar's servers, and avoid triggering blocks


def main():
    parser = argparse.ArgumentParser(description="Export all publications from a Google Scholar profile as BibTeX.")
    parser.add_argument("profile", help="Google Scholar profile URL or raw user ID (the 'user=' value in the URL)")
    parser.add_argument("-o", "--output", default="scholar_export.bib", help="Output .bib file path (default: scholar_export.bib)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between requests (default: 1.5)")
    parser.add_argument("--use-proxy", action="store_true", help="Route requests through a free proxy pool to avoid rate limiting")
    parser.add_argument("--max-authors", type=int, default=None,
                         help="Truncate author lists longer than N to 'First Author, ..., You, and others' "
                              "(renders as 'et al.' in the PDF). Leave unset to keep full author lists.")
    parser.add_argument("--my-name", type=str, default=None,
                         help="Your name, used to keep you visible when author lists are truncated. "
                              "Defaults to the name on the Scholar profile. Only used with --max-authors.")
    parser.add_argument("--skip", action="append", default=[],
                         help="Skip publications whose title or venue contains this text (case-insensitive). "
                              "Repeatable, e.g. --skip 'GCN' --skip 'Zenodo'.")
    parser.add_argument("--skip-file", type=str, default=None,
                         help="Path to a text file of skip patterns, one per line ('#' starts a comment). "
                              "Combined with any --skip flags.")
    args = parser.parse_args()

    if args.use_proxy:
        setup_proxy()

    scholar_id = extract_scholar_id(args.profile)
    skip_patterns = load_skip_patterns(args.skip_file, args.skip)

    entries = list(fetch_bibtex_entries(scholar_id, delay=args.delay, max_authors=args.max_authors,
                                         my_name=args.my_name, skip_patterns=skip_patterns))

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n\n".join(entries))

    print(f"\nDone. Wrote {len(entries)} BibTeX entries to {args.output}")


if __name__ == "__main__":
    main()
