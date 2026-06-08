# Random Trends

Current v1 focus:
- Booli sold apartment prices in central Kalix

Basic scraper usage:

```bash
python3 scripts/scrape_booli.py --html-file research/booli-search.html
python3 scripts/scrape_booli.py --headful
python3 scripts/scrape_booli.py --headful --deduplicate
```

Notes:
- The default configured market is `kalix_centrum_1rok`.
- Live scraping uses `camoufox`.
- The default behavior keeps all raw Booli cards, including duplicates. Use `--deduplicate` to collapse repeated listings.
- If Booli shows Cloudflare verification, run `--headful`, solve it in the browser window, then press Enter in the terminal.
