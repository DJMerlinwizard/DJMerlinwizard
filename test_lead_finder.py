import unittest

from lead_finder import extract_keywords, looks_us_only


class LeadFinderTests(unittest.TestCase):
    def test_extract_keywords(self):
        text = "Need to refinance and buy a home this year"
        kws = ["refinance", "buy a home", "investment property"]
        self.assertEqual(extract_keywords(text, kws), ["refinance", "buy a home"])

    def test_looks_us_only_with_state(self):
        self.assertTrue(looks_us_only("Looking to buy in Austin, Texas"))

    def test_looks_us_only_with_non_us(self):
        self.assertFalse(looks_us_only("Looking to buy in Toronto, Ontario CAD"))


if __name__ == "__main__":
    unittest.main()
