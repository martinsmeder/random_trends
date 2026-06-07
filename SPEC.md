# SPEC

## Overview

`random_trends` is a small project for tracking defined market trends over time.

Version 1 focuses on one trend:

- `Booli slutpriser` for `Lägenhet` sales in central Kalix

The purpose is to determine whether apartment prices in the defined Kalix centrum market are moving up, down, or remaining flat.

## V1 Scope

V1 is intentionally narrow.

Included:

- One configured market: central Kalix
- One source: `booli.se`
- One property type: `Lägenhet`
- One room filter: `maxRooms=1`
- Live scraping of Booli sold listings
- JSON output
- Basic normalization
- Rolling median based on the last `5` sales

Excluded from V1:

- Multi-city support as a required feature
- Multiple data sources
- Scheduling or automation
- Dashboard/UI
- Advanced forecasting
- Broad market comparison against all of Kalix unless explicitly added later

## Market Definition

The current source of truth for the Kalix centrum market is the hand-curated Booli `areaIds` list in `notes.txt`.

Current centrum `areaIds`:

- `83953`
- `813757`
- `84052`
- `410631`
- `84014`
- `191823`
- `384715`
- `256034`
- `310171`
- `277786`
- `813788`
- `84028`

V1 Booli URL:

```text
https://www.booli.se/sok/slutpriser?areaIds=83953,813757,84052,410631,84014,191823,384715,256034,310171,277786,813788,84028&maxRooms=1&objectType=L%C3%A4genhet&sort=soldDate&ascending=1
```

## Inputs

V1 requires:

- A base Booli sold-search URL
- The configured market `areaIds`
- The fixed search filters for the current market

The scraper should treat the URL and market definition as configuration, even if only one market is supported in V1.

## Scraping Requirements

The scraper must:

- Fetch the sold-listings search results from Booli live
- Traverse all result pages for the configured query
- Extract listing-level data from each result card
- Preserve enough raw fields to recompute metrics later

The saved HTML in `research/` is a research artifact for understanding page structure, but it is not the primary runtime input in V1.

## Required Extracted Fields

Each sold listing record should capture at minimum:

- `address`
- `sold_date`
- `sold_price`
- `price_per_sqm`
- `size_sqm`
- `rooms`
- `booli_url`
- `source_url`
- `area_ids`
- `scraped_at`

If a stable listing identifier can be extracted from Booli, it should also be stored.

## Normalization

The scraper output should be normalized into a consistent JSON structure.

Normalization rules for V1:

- Store dates in ISO format when possible
- Store numeric values as numbers, not formatted strings
- Strip presentation formatting such as spaces in thousands separators
- Normalize Swedish field values into stable internal keys where needed
- Preserve the configured `areaIds` used for the scrape

## Output

V1 output format is JSON.

Suggested shape:

```json
{
  "market": "kalix_centrum_1rok",
  "source": "booli",
  "scraped_at": "2026-06-07T12:00:00Z",
  "query": {
    "area_ids": [
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
      "84028"
    ],
    "object_type": "Lägenhet",
    "max_rooms": 1,
    "sort": "soldDate",
    "ascending": true
  },
  "records": [
    {
      "address": "Examplegatan 1",
      "sold_date": "2024-11-18",
      "sold_price": 625000,
      "price_per_sqm": 17857,
      "size_sqm": 35,
      "rooms": 1,
      "booli_url": "https://www.booli.se/bostad/...",
      "source_url": "https://www.booli.se/sok/slutpriser?...",
      "area_ids": [
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
        "84028"
      ],
      "scraped_at": "2026-06-07T12:00:00Z"
    }
  ]
}
```

The exact filename convention can be decided during implementation, but it should be deterministic and easy to version.

## Trend Metric

The primary V1 trend metric is:

- rolling median of `price_per_sqm` over the last `5` sales

Rationale:

- The market is small and low-volume
- A sales-count window is more stable than a time window when some months have few or no sales

V1 should compute at least:

- raw `price_per_sqm` per sale
- `rolling_median_price_per_sqm_last_5_sales`

The metric should be ordered by `sold_date`.

## Pagination

The scraper must support multi-page sold-search results.

Because the saved research HTML is only the first page, pagination handling may need to be verified during implementation against live Booli responses.

## Error Handling

V1 should handle common scrape failures pragmatically.

Expected behaviors:

- Fail clearly if the page structure no longer matches expectations
- Fail clearly if live access to Booli is blocked
- Avoid silently returning partial data without signaling it
- Log enough context to debug extraction failures

Retry behavior can be basic in V1.

## Non-Goals

V1 does not need to solve:

- anti-bot bypass beyond normal request/browser behavior
- long-term storage design beyond JSON output
- generalized support for arbitrary real-estate sources
- sophisticated statistical analysis beyond the rolling median

## Research Basis

Current local research inputs:

- `notes.txt`
- `research/booli-search.html`

The saved Booli HTML indicates that sold-list result cards expose at least:

- apartment size
- room count
- `price per sqm`
- sold date

Live scraping will still need to confirm the full extraction and pagination behavior.

## Future Direction

Likely next steps after V1:

- Support additional configured markets
- Support more room filters or property types
- Persist repeated scrape runs in a stable historical layout
- Add comparisons such as `Centrumvägen only` vs `all Kalix centrum`
- Add additional smoothed series such as `last 10 sales`
