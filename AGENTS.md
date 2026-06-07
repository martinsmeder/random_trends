# AGENTS

## Project

`random_trends` tracks small, clearly defined trend datasets.

The first tracked trend is `Booli slutpriser` for apartments in central Kalix, with the goal of detecting whether prices are moving up, down, or staying flat.

## Current Scope

- Source: `booli.se`
- Market: central Kalix
- Property type: `Lägenhet`
- Initial filter: `maxRooms=1`
- Primary metric: `price per sqm`
- Smoothing: rolling median, preferred over average for small datasets

## Working Data

- Research artifacts live in `research/`
- Notes and assumptions live in `notes.txt`
- Saved HTML can be used to inspect page structure before building or updating the scraper

## Near-Term Plan

1. Inspect the Booli search page structure.
2. Build a scraper for address, sold date, and price per sqm.
3. Scrape all result pages for the defined market.
4. Normalize the dataset and compute rolling medians.
5. Generalize the scraper so it can be reused for other Swedish cities and trends.

## Agent Guidance

- Prefer reproducible market definitions based on explicit `areaIds`.
- Treat the hand-curated Kalix centrum street list as the current source of truth.
- Avoid broadening the market unintentionally by mixing centrum street IDs with `Kalix kommun` unless that is a deliberate comparison.
- Keep the code generic where possible; keep market definitions in data or config.
