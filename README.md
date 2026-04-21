# US Mortgage/Home Buyer Lead Finder

This project provides a CLI tool (`lead_finder.py`) to find U.S.-only posts that indicate intent to:

- Refinance
- Buy a home
- Purchase an investment property

It can scan:

- **Reddit** (public search endpoint)
- **Craigslist** (RSS feeds on selected U.S. city domains)
- **Nextdoor** (via CSV ingest, since there is no open public API)

## Why CSV for Nextdoor?

Nextdoor does not provide a broadly accessible public search API suitable for open scraping. This tool supports ingesting data you already have permission to access/export.

## Quick start

```bash
python3 lead_finder.py \
  --sources reddit,craigslist \
  --keywords "refinance,first time home buyer,investment property" \
  --max-results 100 \
  --output leads.jsonl
```

If using Nextdoor CSV:

```bash
python3 lead_finder.py \
  --sources nextdoor \
  --nextdoor-csv ./nextdoor_posts.csv \
  --output leads.jsonl
```

## Notes

- USA-only filtering is heuristic-based (state names/abbreviations, location hints, and simple currency context).
- Respect each platform's Terms of Service and rate limits before production use.
- Consider adding a CRM webhook step for real-time lead routing.
