#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from random_trends.booli import (
    BooliBlockedError,
    BooliScrapeError,
    build_output_payload,
    parse_area_ids_from_url,
    scrape_from_html_file,
    scrape_market,
    write_output,
)
from random_trends.config import MARKETS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Booli sold listings for a configured market.")
    parser.add_argument(
        "--market",
        default="kalix_centrum_1rok",
        choices=sorted(MARKETS.keys()),
        help="Configured market to scrape.",
    )
    parser.add_argument(
        "--output",
        default="data/kalix_centrum_1rok.json",
        help="Path to the JSON output file.",
    )
    parser.add_argument(
        "--html-file",
        help="Optional local HTML file to parse instead of scraping live.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run the browser in headful mode. Required for manual captcha solving.",
    )
    parser.add_argument(
        "--manual-captcha-timeout",
        type=int,
        default=300,
        help="Seconds to wait after you press Enter for Booli results to appear.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Optional page limit for debugging.",
    )
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Collapse repeated Booli listing cards into unique listings.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    market = MARKETS[args.market]
    area_ids = list(market.area_ids)

    if args.html_file:
        records = scrape_from_html_file(
            Path(args.html_file),
            page_url=market.search_url,
            area_ids=area_ids,
            deduplicate=args.deduplicate,
        )
    else:
        try:
            records = scrape_market(
                url=market.search_url,
                area_ids=area_ids,
                headless=not args.headful,
                max_pages=args.max_pages,
                manual_captcha_timeout_ms=args.manual_captcha_timeout * 1000,
                deduplicate=args.deduplicate,
            )
        except BooliBlockedError as exc:
            print(f"Blocked: {exc}")
            print("Try a headful run first: scripts/scrape_booli.py --headful")
            return 2
        except BooliScrapeError as exc:
            print(f"Scrape failed: {exc}")
            return 1

    payload = build_output_payload(
        market=market.name,
        source=market.source,
        source_url=market.search_url,
        area_ids=parse_area_ids_from_url(market.search_url),
        object_type=market.object_type,
        max_rooms=market.max_rooms,
        sort=market.sort,
        ascending=market.ascending,
        records=records,
    )
    write_output(Path(args.output), payload)
    print(f"Wrote {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
