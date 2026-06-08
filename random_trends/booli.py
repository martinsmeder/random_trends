from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from statistics import median
from typing import Optional, Union
from urllib.parse import parse_qs, urljoin, urlparse

from camoufox.sync_api import Camoufox
from lxml import html

BOOLI_BASE_URL = "https://www.booli.se"
DEFAULT_TIMEOUT_MS = 90_000
DEFAULT_WAIT_AFTER_LOAD_MS = 5_000
DEFAULT_MANUAL_CAPTCHA_TIMEOUT_MS = 300_000


class BooliScrapeError(RuntimeError):
    """Base error for scraper failures."""


class BooliBlockedError(BooliScrapeError):
    """Raised when Booli/Cloudflare blocks access."""


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

        size_sqm = _parse_metric_value(data_items, "kvadratmeter")
        rooms = _parse_metric_value(data_items, "rum")
        price_per_sqm = _parse_metric_value(data_items, "kr/kvadratmeter")

        record = ListingRecord(
            listing_id=_extract_listing_id(href),
            address=address,
            sold_date=_normalize_date(sold_date_text),
            sold_price=int(_parse_number(price_text)),
            price_per_sqm=int(price_per_sqm),
            size_sqm=size_sqm,
            rooms=rooms,
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
    deduplicate: bool = False,
) -> list[ListingRecord]:
    scraped_at = _utc_now_iso()
    records: list[ListingRecord] = []
    seen_urls: set[str] = set()
    next_url: Optional[str] = url
    page_number = 0

    with Camoufox(
        headless=headless,
        humanize=True,
        locale="sv-SE",
        enable_cache=True,
    ) as browser:
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

    return _finalize_records(records, deduplicate=deduplicate)


def scrape_from_html_file(
    html_path: Path,
    *,
    page_url: str,
    area_ids: list[str],
    deduplicate: bool = False,
) -> list[ListingRecord]:
    parsed = parse_results_page(
        html_path.read_text(),
        page_url=page_url,
        area_ids=area_ids,
        scraped_at=_utc_now_iso(),
    )
    return _finalize_records(parsed.records, deduplicate=deduplicate)


def build_output_payload(
    *,
    market: str,
    source: str,
    source_url: str,
    area_ids: list[str],
    object_type: str,
    max_rooms: int,
    sort: str,
    ascending: bool,
    records: list[ListingRecord],
) -> dict:
    return {
        "market": market,
        "source": source,
        "scraped_at": _utc_now_iso(),
        "query": {
            "area_ids": area_ids,
            "object_type": object_type,
            "max_rooms": max_rooms,
            "sort": sort,
            "ascending": ascending,
        },
        "records": [asdict(record) for record in records],
        "source_url": source_url,
    }


def write_output(output_path: Path, payload: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


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
    if value.is_integer():
        return int(value)
    return value


def _normalize_date(text: str) -> str:
    cleaned = _normalize_whitespace(text)
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise BooliScrapeError(f"Unexpected sold date format: '{text}'.") from exc


def _compute_rolling_median(records: list[ListingRecord]) -> list[ListingRecord]:
    records.sort(key=lambda record: record.sold_date)
    values: list[int] = []
    for record in records:
        values.append(record.price_per_sqm)
        if len(values) >= 5:
            window = values[-5:]
            record.rolling_median_price_per_sqm_last_5_sales = median(window)
    return records


def _finalize_records(records: list[ListingRecord], *, deduplicate: bool) -> list[ListingRecord]:
    finalized = _deduplicate_records(records) if deduplicate else list(records)
    return _compute_rolling_median(finalized)


def _deduplicate_records(records: list[ListingRecord]) -> list[ListingRecord]:
    deduplicated: list[ListingRecord] = []
    seen: set[str] = set()
    for record in records:
        key = record.listing_id or record.booli_url
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(record)
    return deduplicated


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _plain_text(html_text: str) -> str:
    document = html.fromstring(html_text)
    return _normalize_whitespace(document.text_content())


def _page_has_result_cards(html_text: str) -> bool:
    document = html.fromstring(html_text)
    return bool(document.xpath("//a[contains(@class, 'object-card-link')]"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_area_ids_from_url(url: str) -> list[str]:
    query = parse_qs(urlparse(url).query)
    raw = query.get("areaIds", [""])[0]
    return [value for value in raw.split(",") if value]
