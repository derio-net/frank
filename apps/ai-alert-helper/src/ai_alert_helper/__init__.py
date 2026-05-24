"""AI-enriched alert helper for the Frank blog edge.

Three entrypoints:
- POST /digest        — daily summary triggered by CronJob
- POST /alert         — Grafana contact-point webhook (blog-edge folder)
- POST /surge-check   — 15-min CronJob that computes hour-of-day baseline
"""
