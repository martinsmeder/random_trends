from pathlib import Path
import unittest

from random_trends.booli import parse_results_page
from random_trends.config import KALIX_CENTRUM_1ROK


class ParseBooliResultsPageTest(unittest.TestCase):
    def test_parses_saved_research_page(self) -> None:
        html_text = Path("research/booli-search.html").read_text()
        parsed = parse_results_page(
            html_text,
            page_url=KALIX_CENTRUM_1ROK.search_url,
            area_ids=list(KALIX_CENTRUM_1ROK.area_ids),
            scraped_at="2026-06-08T12:00:00Z",
        )

        self.assertGreater(len(parsed.records), 0)
        first = parsed.records[0]
        self.assertEqual(first.address, "Floragatan 12")
        self.assertEqual(first.sold_date, "2014-08-19")
        self.assertEqual(first.sold_price, 70000)
        self.assertEqual(first.price_per_sqm, 1600)
        self.assertEqual(first.size_sqm, 44)
        self.assertEqual(first.rooms, 1)
        self.assertIn("/sok/slutpriser", first.source_url)
        self.assertIsNotNone(parsed.next_page_url)
        self.assertIn("page=2", parsed.next_page_url)


if __name__ == "__main__":
    unittest.main()

