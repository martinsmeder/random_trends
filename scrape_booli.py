#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from statistics import median
from typing import Optional, Union
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from camoufox.sync_api import Camoufox
from lxml import html

BOOLI_BASE_URL = "https://www.booli.se"
DEFAULT_TIMEOUT_MS = 90_000
DEFAULT_WAIT_AFTER_LOAD_MS = 5_000
DEFAULT_MANUAL_CAPTCHA_TIMEOUT_MS = 300_000


class BooliScrapeError(RuntimeError):
    pass


class BooliBlockedError(BooliScrapeError):
    pass


@dataclass(frozen=True)
class BooliMarketConfig:
    name: str
    source: str
    area_ids: tuple[str, ...]
    object_type: str
    max_rooms: int
    sort: str
    ascending: bool

    @property
    def search_url(self) -> str:
        query = urlencode(
            {
                "areaIds": ",".join(self.area_ids),
                "maxRooms": self.max_rooms,
                "objectType": self.object_type,
                "sort": self.sort,
                "ascending": int(self.ascending),
            }
        )
        return f"{BOOLI_BASE_URL}/sok/slutpriser?{query}"


@dataclass
class ListingRecord:
    listing_id: Optional[str]
    address: str
    sold_date: str
    sold_price: int
    price_per_sqm: int
    size_sqm: float
    rooms: float
    booli_url: str
    source_url: str
    area_ids: list[str]
    scraped_at: str
    rolling_median_price_per_sqm_last_5_sales: Optional[float] = None


@dataclass
class ParsedPage:
    records: list[ListingRecord]
    next_page_url: Optional[str]


KALIX_CENTRUM_1ROK = BooliMarketConfig(
    name="kalix_centrum_1rok",
    source="booli",
    area_ids=(
        "83953",
        "813757",
        "84052",
        "410631",
        "84014",
        "191823",
        "384715",
        "256034",
        "310171",
        "277786",
        "813788",
        "84028",
    ),
    object_type="Lägenhet",
    max_rooms=1,
    sort="soldDate",
    ascending=True,
)

MARKETS = {KALIX_CENTRUM_1ROK.name: KALIX_CENTRUM_1ROK}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Booli sold listings for a configured market.")
    parser.add_argument("--market", default="kalix_centrum_1rok", choices=sorted(MARKETS.keys()))
    parser.add_argument("--output", default="data/kalix_centrum_1rok.json")
    parser.add_argument("--html-file", help="Optional local HTML file to parse instead of scraping live.")
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
    parser.add_argument("--max-pages", type=int, help="Optional page limit for debugging.")
    return parser.parse_args()


def parse_results_page(
    html_text: str,
    *,
    page_url: str,
    area_ids: list[str],
    scraped_at: str,
) -> ParsedPage:
    _raise_for_blocked_page(html_text)

    document = html.fromstring(html_text)
    links = document.xpath("//a[contains(@class, 'object-card-link')]")
    if not links:
        raise BooliScrapeError("No Booli result cards found on the page.")

    records: list[ListingRecord] = []
    for link in links:
        href = link.get("href")
        if not href:
            continue

        address = _first_text(link.xpath(".//h3[contains(@class, 'object-card__heading--logo')]"))
        if not address:
            continue

        price_text = _first_text(link.xpath(".//span[contains(@class, 'object-card__price--logo')]"))
        sold_date_text = _first_text(link.xpath(".//span[contains(@class, 'object-card__date--logo')]"))
        data_items = link.xpath(".//ul[contains(@class, 'object-card__data-list')]/li")

        record = ListingRecord(
            listing_id=_extract_listing_id(href),
            address=address,
            sold_date=_normalize_date(sold_date_text),
            sold_price=int(_parse_number(price_text)),
            price_per_sqm=int(_parse_metric_value(data_items, "kr/kvadratmeter")),
            size_sqm=_parse_metric_value(data_items, "kvadratmeter"),
            rooms=_parse_metric_value(data_items, "rum"),
            booli_url=urljoin(BOOLI_BASE_URL, href),
            source_url=page_url,
            area_ids=area_ids,
            scraped_at=scraped_at,
        )
        records.append(record)

    next_page_href = _extract_next_page_href(document)
    next_page_url = urljoin(BOOLI_BASE_URL, next_page_href) if next_page_href else None
    return ParsedPage(records=records, next_page_url=next_page_url)


def scrape_market(
    *,
    url: str,
    area_ids: list[str],
    headless: Union[bool, str] = True,
    max_pages: Optional[int] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    manual_captcha_timeout_ms: int = DEFAULT_MANUAL_CAPTCHA_TIMEOUT_MS,
) -> list[ListingRecord]:
    scraped_at = _utc_now_iso()
    records: list[ListingRecord] = []
    seen_urls: set[str] = set()
    next_url: Optional[str] = url
    page_number = 0

    with Camoufox(headless=headless, humanize=True, locale="sv-SE", enable_cache=True) as browser:
        page = browser.new_page()
        while next_url:
            if next_url in seen_urls:
                break
            if max_pages is not None and page_number >= max_pages:
                break

            seen_urls.add(next_url)
            page_number += 1
            page.goto(next_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(DEFAULT_WAIT_AFTER_LOAD_MS)

            html_text = _get_page_html_after_manual_verification(
                page,
                page_url=next_url,
                headless=headless,
                manual_captcha_timeout_ms=manual_captcha_timeout_ms,
            )
            parsed = parse_results_page(
                html_text,
                page_url=next_url,
                area_ids=area_ids,
                scraped_at=scraped_at,
            )
            records.extend(parsed.records)
            next_url = parsed.next_page_url

        page.close()

    return _compute_rolling_median(records)


def scrape_from_html_file(
    html_path: Path,
    *,
    page_url: str,
    area_ids: list[str],
) -> list[ListingRecord]:
    parsed = parse_results_page(
        html_path.read_text(),
        page_url=page_url,
        area_ids=area_ids,
        scraped_at=_utc_now_iso(),
    )
    return _compute_rolling_median(parsed.records)


def build_output_payload(
    *,
    market: BooliMarketConfig,
    records: list[ListingRecord],
) -> dict:
    return {
        "market": market.name,
        "source": market.source,
        "scraped_at": _utc_now_iso(),
        "query": {
            "area_ids": list(market.area_ids),
            "object_type": market.object_type,
            "max_rooms": market.max_rooms,
            "sort": market.sort,
            "ascending": market.ascending,
        },
        "records": [asdict(record) for record in records],
        "source_url": market.search_url,
    }


def write_output(output_path: Path, payload: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    args = parse_args()
    market = MARKETS[args.market]
    area_ids = list(market.area_ids)

    try:
        if args.html_file:
            records = scrape_from_html_file(
                Path(args.html_file),
                page_url=market.search_url,
                area_ids=area_ids,
            )
        else:
            records = scrape_market(
                url=market.search_url,
                area_ids=area_ids,
                headless=not args.headful,
                max_pages=args.max_pages,
                manual_captcha_timeout_ms=args.manual_captcha_timeout * 1000,
            )
    except BooliBlockedError as exc:
        print(f"Blocked: {exc}")
        print("Try a headful run first: python3 scrape_booli.py --headful")
        return 2
    except BooliScrapeError as exc:
        print(f"Scrape failed: {exc}")
        return 1

    payload = build_output_payload(market=market, records=records)
    write_output(Path(args.output), payload)
    print(f"Wrote {len(records)} records to {args.output}")
    return 0


def _get_page_html_after_manual_verification(
    page,
    *,
    page_url: str,
    headless: Union[bool, str],
    manual_captcha_timeout_ms: int,
) -> str:
    html_text = page.content()
    try:
        _raise_for_blocked_page(html_text)
        return html_text
    except BooliBlockedError:
        if headless is True:
            raise

    print(f"Cloudflare verification detected for {page_url}")
    print("Solve the verification in the browser window, then press Enter here.")
    input()
    deadline = datetime.now(timezone.utc).timestamp() + (manual_captcha_timeout_ms / 1000)

    while datetime.now(timezone.utc).timestamp() < deadline:
        page.wait_for_timeout(1_000)
        html_text = page.content()
        try:
            _raise_for_blocked_page(html_text)
        except BooliBlockedError:
            continue
        if _page_has_result_cards(html_text):
            return html_text

    raise BooliBlockedError("Timed out waiting for manual Cloudflare verification to complete.")


def _raise_for_blocked_page(html_text: str) -> None:
    plain_text = _plain_text(html_text)
    if "Performing security verification" in plain_text:
        raise BooliBlockedError("Booli is showing a Cloudflare verification page.")
    if "Utför säkerhetsverifiering" in plain_text:
        raise BooliBlockedError("Booli is showing a Cloudflare verification page.")
    if "<title>Just a moment...</title>" in html_text:
        raise BooliBlockedError("Booli returned a Cloudflare challenge page.")
    if "<title>Vänta...</title>" in html_text:
        raise BooliBlockedError("Booli returned a Cloudflare challenge page.")


def _extract_next_page_href(document: html.HtmlElement) -> Optional[str]:
    matches = document.xpath("//a[normalize-space()='Nästa sida']/@href")
    return matches[0] if matches else None


def _extract_listing_id(href: str) -> Optional[str]:
    match = re.search(r"/(?:annons|bostad)/(\d+)", href)
    return match.group(1) if match else None


def _first_text(nodes: list) -> str:
    if not nodes:
        return ""
    node = nodes[0]
    text = node.text_content() if hasattr(node, "text_content") else str(node)
    return _normalize_whitespace(text)


def _parse_metric_value(items: list, needle: str) -> float:
    for item in items:
        candidate = item.get("aria-label") or item.text_content()
        candidate = _normalize_whitespace(unescape(candidate))
        if needle in candidate:
            return _parse_number(candidate)
    raise BooliScrapeError(f"Could not find metric containing '{needle}'.")


def _parse_number(text: str) -> float:
    cleaned = _normalize_whitespace(unescape(text))
    cleaned = cleaned.replace("kr/m²", "").replace("kr/kvadratmeter", "")
    cleaned = cleaned.replace("kr", "").replace("m²", "").replace("rum", "")
    cleaned = cleaned.replace("kvadratmeter", "").strip()
    cleaned = cleaned.replace(" ", "").replace("\xa0", "")
    cleaned = cleaned.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        raise BooliScrapeError(f"Could not parse numeric value from '{text}'.")
    value = float(match.group(0))
    return int(value) if value.is_integer() else value


def _normalize_date(text: str) -> str:
    cleaned = _normalize_whitespace(text)
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise BooliScrapeError(f"Unexpected sold date format: '{text}'.") from exc


def _compute_rolling_median(records: list[ListingRecord]) -> list[ListingRecord]:
    records = list(records)
    records.sort(key=lambda record: record.sold_date)
    values: list[int] = []
    for record in records:
        values.append(record.price_per_sqm)
        if len(values) >= 5:
            record.rolling_median_price_per_sqm_last_5_sales = median(values[-5:])
    return records


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _plain_text(html_text: str) -> str:
    document = html.fromstring(html_text)
    return _normalize_whitespace(document.text_content())


def _page_has_result_cards(html_text: str) -> bool:
    document = html.fromstring(html_text)
    return bool(document.xpath("//a[contains(@class, 'object-card-link')]"))


def parse_area_ids_from_url(url: str) -> list[str]:
    query = parse_qs(urlparse(url).query)
    raw = query.get("areaIds", [""])[0]
    return [value for value in raw.split(",") if value]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
