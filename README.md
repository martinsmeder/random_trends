# Random Trends

Current version:

- Booli sold apartment prices in central Kalix

Basic scraper usage:

```bash
python3 scrape_booli.py --headful
```

Notes:

- The default configured market is `kalix_centrum_1rok`.
- Live scraping uses `camoufox`.
- Run `--headful` to solve the cloudflare challenge in the browser window, then press Enter in the terminal to scrape the data.

How to read the trend:

- The raw dataset contains one record per apartment sale.
- For each sale, the scraper calculates a rolling median of `price_per_sqm` over the last `5` sales.
- That rolling median is the main trend signal. It smooths out one-off noisy sales in a thin market.
- The monthly trend file converts that sale-based signal into one value per month.
- If no sale happened in a month, the monthly trend stays at the latest known value.
- If a sale happened and changed the rolling median, the monthly trend steps up or down in that month.

Why the trend looks stepwise:

- This market has low sales volume: only 61 one-room apartment sales over more than 10 years.
- Because of that, the trend does not update smoothly every month.
- Instead, it stays flat until a new sale changes the last-5-sales median.
- In a much higher-volume market, the same method would usually look smoother because new sales would update the signal more often and any one sale would matter less.
