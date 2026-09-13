---
title: "Read Frank with an agent"
description: "Discover and retrieve Frank articles through a versioned JSON catalog, Markdown exports, stable section links, and RSS."
date: 2026-09-05
---

HTML articles and Markdown exports describe the same published material. Exports include rendered glossary definitions, comparison tables, code, diagram source, and references.

## Discover

- [Content catalog](../../content-index.json): schema version 1, with one record per published page.
- [llms.txt](../../llms.txt): a short entry point for consumers that use it.
- [RSS](../../index.xml): new publications.
- [Topic guides](../../topics/): curated entry points across Building, Operating, and Papers.

## Retrieve and cite

Read `articles[].markdown_url` for the page body. Cite `articles[].url`, the canonical HTML page. Markdown headings link to the corresponding HTML section where an anchor is available.

The catalog includes title, summary, series, layer, tags, reader goal, publication and update dates, source path, related article references, and a SHA-256 hash of the exported text. A changed `content_sha256` means the export changed; it does not establish that a command has been re-tested.

`last_verified` is false when no explicit verification date is recorded. `tested_versions` and `prerequisites` are empty when the author has not supplied them. `commands_change_state` is `unknown` unless explicitly recorded as true or false. Missing metadata makes no claim about a procedure's safety or freshness.

The catalog is an additive versioned contract. Ignore unknown fields, identify records by `id`, and check `schema_version` before parsing. Paths in `related_building` and `related_operating` identify pages relative to the site's base path.

## Scope

Only pages published by the production build enter the catalog. Research working files, private assets, and unpublished drafts are excluded. Retrieve relevant articles individually; there is no requirement to ingest the entire site.
