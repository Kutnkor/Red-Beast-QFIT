# Scientific sources and knowledge base

## Source registry

`research/sources/registry.json` (version `2026.11.14-1`) lists every source the knowledge base may
cite: 31 records with `id`, `title`, `url`, `organization`, `reliability`, `topic`, `publication_date`,
`retrieval_date`, optional `document_version`, `mission`, `data_release` and `note`. The full list with
links is served by `GET /api/v1/knowledge/sources`.

Reliability classes, strongest first (`reliability_order`):

1. `peer_reviewed`
2. `primary_mission_documentation`
3. `primary_archive_documentation`
4. `archive_query_result`
5. `agency_publication`
6. `research_institution_publication`
7. `agency_educational`
8. `research_institution_educational`
9. `vendor_documentation`
10. `project_measurement` (the team's own measurements)
11. `project_policy` (Q-FIT's own rules, `qfit-spec`)

Passages list their sources in this order. A class is a property of the publication, not a guarantee
that a statement is true; `project_policy` is cited for rules about Q-FIT itself, never for astronomy.

## Knowledge documents

`research/knowledge/en/*.md` and `research/knowledge/tr/*.md`: 9 documents per language, 41 sections
each, 82 chunks. Topics: SPHEREx mission, data products, data access, time coverage, spectroscopy,
brown dwarfs, H-R diagram, citizen science, Q-FIT evidence policy.

Rules for writing a document:

```markdown
---
id: brown-dwarfs            # same id in en/ and tr/
title: Brown dwarfs and substellar objects
language: en                # en | tr
topic: brown_dwarfs
version: 1
mission: SPHEREx            # optional
data_release: DR1, QR3      # optional
---
## Section heading
One self-contained paragraph. Numbers keep their units.
Sources: nasa-gl229b, jpl-identity-crisis
Verification: optional note when a statement still needs a citation
```

- One `##` section is one retrieval unit, so a section must make sense on its own.
- The `Sources:` line is mandatory and every id must exist in the registry; otherwise ingestion fails
  and the knowledge base reports itself unavailable instead of serving uncited text.
- The Turkish section at position *n* is the translation of the English section *n*
  (`brown-dwarfs:en:2` ↔ `brown-dwarfs:tr:2`); the tests check that every English chunk has its twin.
- A `Verification:` note reaches the user through the response's `uncertainty` list.
- Changing a document changes its content hash; the index rebuilds only the changed chunks and gets
  a new `index_version`, which appears in every answer's `meta.versions`.

## Known disagreements and caveats kept in the knowledge base

- **Brown dwarf mass range.** NASA StarChild, JPL, a NASA Webb article and Gan et al. (2025) give
  different lower limits. The passage lists each with its source and the two definitions behind them
  (deuterium fusion vs. formation); Q-FIT does not pick one.
- **Flux definition.** The passage "Luminosity and flux" carries a `Verification:` note: the definition
  is standard physics but is not stated in the cited pages.
- **Wavelength of repeat exposures.** The team's own QR2 measurement (`qfit-milestone-report`) shows
  that two exposures of the same position usually differ in wavelength by about one bandwidth or more.
  It is labelled as a QR2 measurement to be rechecked on DR1 and QR3.
- **Releases.** QR2 is no longer searchable through SIA2; QR2 and QR3 use different gains, so
  brightness values are not comparable without IRSA's flux corrections product.

## Adding a source

1. Add a record to `registry.json` with a real, working URL and the date you read it; bump
   `registry_version`.
2. Cite its id in a `Sources:` line.
3. Start the backend or run `pytest tests/test_knowledge.py`: ingestion fails loudly on unknown ids.
4. Rerun `python scripts/evaluate.py retrieval` if you added or changed passages.
