# Q-FIT API contract (v1)

How a frontend talks to Q-FIT. Base URL: `http://<host>:8000/api/v1`. JSON in, JSON out, UTF-8.
The machine-readable version is `/openapi.json`; a browsable one is `/docs`.

## 1. Conventions

| Quantity | Convention |
|---|---|
| Angles | Decimal degrees, ICRS (`ra` 0–360, `dec` −90–+90) |
| Time | UTC, ISO-8601 (`...Z`), with MJD alongside where the archive gives it |
| Wavelength | micron (`*_um`) |
| Surface brightness | MJy/sr |
| Missing value | `null`. Q-FIT never substitutes a placeholder |

Send `X-Request-ID` if you want your own correlation id; Q-FIT echoes it in the response header and
in `meta.request_id`, otherwise it generates one.

## 2. Response envelope

Every endpoint, success or failure, returns this object:

```json
{
  "success": true,
  "assistant": "Q-FIT",
  "intent": "search_observations",
  "message": "Human-readable summary.",
  "message_source": "system",
  "object": null,
  "data": { "spherex_available": null, "observations": [], "spectral_products": [], "image_products": [] },
  "actions": [],
  "sources": [],
  "language": null,
  "evidence": [],
  "uncertainty": [],
  "media": [],
  "error": null,
  "meta": { "request_id": "…", "timestamp": "…", "api_version": "v1", "tools_called": [], "ai_model": null,
            "versions": { "instructions": "v2", "knowledge_index": "…", "source_registry": "…",
                          "scientific_config": null } }
}
```

| Field | Meaning |
|---|---|
| `success` | `false` only when the request failed (`error` is then set). "No data" and "object not found" are successful answers. |
| `intent` | What Q-FIT did. Values: `search_object`, `get_object`, `resolve_coordinates`, `search_objects_by_coordinates`, `search_observations`, `get_observation_metadata`, `retrieve_image`, `retrieve_spectrum`, `get_observation_periods`, `knowledge_lookup`, `knowledge_sources`, `submit_candidate`, `list_candidates`, `get_candidate`, `review_candidate`, `validate_review`, `confirm_candidate`, `audit_candidate`, `clarification_needed`, `conversation`, `health`, `capabilities`, `error`. |
| `message` | Text for the user. |
| `message_source` | `ai_generated` (written by the language model, `/chat` only) or `system` (fixed template). Treat AI text as explanation, not as data. |
| `object` | The resolved catalog object, or `null`. Catalog data only. |
| `data` | Retrieved data. The four keys shown above are always present; endpoints add more (below). |
| `actions` | Ordered UI instructions (section 4). |
| `sources` | `{name, url}` of every service the answer came from (knowledge passages add registry fields). |
| `language` | `tr` or `en`: language of `message` (`/chat`, `/knowledge/search`), else `null`. |
| `evidence` | What the answer rests on, one entry per tool result or passage: `{kind, statement, status, source_names, source_urls}`; `kind` is `catalog_data`, `archive_metadata`, `direct_measurement`, `knowledge_base`, `candidate_record` or `missing_information`. |
| `uncertainty` | Caveats to show with the answer (no-data reasons, archive limits, unverified numbers in AI text, tool failures). |
| `media` | References to real files: `{media_type: fits_cutout\|fits_cube, url, full_file_url, observation_id, detector, time_utc, collection, source, verified}`. |
| `meta.versions` | Instruction set, knowledge index, source registry and `data.json` version behind the answer (`{}` on errors). |
| `error` | `{code, message, retryable, details}` or `null`. |

### `data.spherex_available`

- `true`: the IRSA archive returned at least one product for this query.
- `false`: the archive was queried and returned nothing.
- `null`: the archive was not queried (catalog-only request, ambiguous target, moving target).

A resolved `object` with `spherex_available: null` means "this object exists in a catalog; SPHEREx
coverage unknown". Never show it as "observed".

### `object`

```json
{
  "query_name": "Andromeda Galaxy", "name": "M 31", "ra": 10.684708, "dec": 41.26875,
  "coordinate_frame": "ICRS", "coordinate_unit": "deg", "object_type": "G",
  "object_type_label": "Galaxy", "matched_identifier": "NAME Andromeda Galaxy",
  "catalog_source": "SIMBAD", "source_url": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=M+31",
  "reference_bibcode": "2006AJ....131.1163S", "is_solar_system": false,
  "position_time_dependent": false, "position_epoch_utc": null, "observer_location": null, "notes": []
}
```

`catalog_source` is `SIMBAD`, `CDS Sesame` or `JPL Horizons`. When `position_time_dependent` is
`true` the coordinates hold only at `position_epoch_utc`.

### SPHEREx product (items of `observations`, `image_products`, `spectral_products`)

| Field | Notes |
|---|---|
| `observation_id` | Q-FIT id `collection:obs_id:product`, e.g. `spherex_qr3:2026W21_1A_0491_2:D4`. Use it in the `/{observation_id}` endpoints. |
| `obs_id`, `collection`, `release`, `survey` | Archive identifiers; release `DR1`/`QR3`, survey `wide`/`deep`/`all-sky` |
| `product_kind` | `spectral_image` (one detector, one exposure) or `all_sky_cube` (102 channels) |
| `detector`, `bandpass` | Detector 1–6, e.g. `SPHEREx-D4` |
| `center_ra`, `center_dec`, `fov_deg` | Centre of the image, not the search target |
| `t_min_utc`, `t_max_utc`, `t_min_mjd`, `t_max_mjd`, `exposure_s` | Exposure time span |
| `wavelength_min_um`, `wavelength_max_um`, `resolving_power` | Band limits |
| `access_url`, `access_format`, `est_size_kb` | Download reference, verbatim from IRSA |
| `cutout_url` | Only in `image_products`: IRSA cutout centred on the target |
| `download_check` | Only in `image_products`: `{verified: true|false|null, http_status, content_length}`; `null` means not checked |
| `metadata_source` | `IRSA SIA2` or `IRSA TAP` |

## 3. Endpoints

### POST `/chat`

```json
{
  "message": "What SPHEREx data is available for this region?",
  "history": [ { "role": "user", "content": "…" }, { "role": "assistant", "content": "…" } ],
  "context": { "ra": 10.68, "dec": 41.27, "fov_deg": 2.0, "selected_object": null, "selected_observation_id": null }
}
```

`history` (max 20 turns) and `context` are optional. Send the map centre in `context` so that
"this region" and "here" work. Q-FIT is stateless: the frontend keeps the conversation.

The response has `message_source: "ai_generated"`, `meta.tools_called` with the tools used, and
`data`/`actions` assembled from the tool results. Extra keys that can appear in `data`: `search`,
`catalog`, `observation_periods`, `spectral`, `tool_errors`.

Errors: `503 ai_unavailable` (no or rejected API key), `429 rate_limited`, `502 upstream_error`.

### Catalog endpoints

| Endpoint | Body / parameters | Adds to `data` |
|---|---|---|
| POST `/objects/search` | `{query, max_results=5}` | `catalog: {status, candidates}` |
| GET `/objects/{object_id}` | name in the path (URL-encoded), `?target_kind=auto\|deep_sky\|solar_system` | same |
| POST `/coordinates/resolve` | `{name, target_kind="auto", epoch_utc?}` | same |
| POST `/objects/by-coordinates` | `{ra, dec, radius_deg=0.1, object_type?, limit=20}` | `catalog: {objects[], count, …}` |

`catalog.status` is `resolved`, `ambiguous` or `not_found`. `object_type` accepts a SIMBAD type
code (`BD*`, `G`, `QSO`) or a plain name (`brown dwarf`, `galaxy`, `quasar`).

### SPHEREx endpoints

Target fields, used by all of them: either `object_name`, or `ra` and `dec` together.

| Endpoint | Body / parameters |
|---|---|
| GET `/observations` | `object` or `ra`+`dec`; `radius_deg=0.003`, `detector`, `release=all\|dr1\|qr3`, `start_utc`, `end_utc`, `limit=50`, `offset=0` |
| POST `/observations/search` | target + the same fields, plus `include_footprint=false` |
| POST `/observations/periods` | target + `radius_deg`, `gap_days=20`, `release` |
| GET `/observations/{observation_id}` | optional `ra`, `dec` position hint |
| POST `/images/search` | target + `cutout_size_deg=0.1`, `detector`, `release`, `limit=6`, `verify=false` |
| POST `/spectrum/search` | target + `release`, `extract_samples=false`, `max_samples=6` |
| GET `/spectrum/{observation_id}` | optional `ra`, `dec`, `extract=false` |

`data.search` carries `status`, `target`, `total`, `returned`, `offset`, `limit`, `has_more`,
`summary`, `filters`, `collections_searched`, `truncated_by_archive_limit` and, for empty results,
`possible_reasons`.

`data.search.status`:

| Status | Meaning | `spherex_available` |
|---|---|---|
| `ok` | Products found | `true` |
| `no_data` | Archive queried, nothing found | `false` |
| `ambiguous_target` | Name matches several objects; see `candidates` | `null` |
| `target_not_found` | Name unknown to the catalogs | `null` |
| `moving_target` | Solar System body; fixed-position search refused | `null` |

Paging: request `limit`/`offset`; continue while `has_more` is `true`.

A search radius is rarely needed. SPHEREx images are 3.5° wide, and the archive returns every
image whose footprint touches the search circle, so the default 0.003° already means "all images
that cover this point".

`/observations/periods` adds `data.observation_periods`: `[{period, start_utc, end_utc, start_mjd,
end_mjd, duration_days, products, exposures, detectors, collections}]`.

`/spectrum/*` adds `data.spectral`: `spectral_image_coverage` (per-detector band coverage and
`detectors_missing`), and `samples` when extraction was requested. Each sample is one detector pixel
in one exposure: `{observation_id, detector, t_min_utc, ok, wavelength_um, bandwidth_um,
surface_brightness, surface_brightness_unit, variance, zodi_model, flags, cutout_url}`.
Label these as raw pixel readings in the UI, not as a source spectrum.

### Image previews

| Endpoint | Returns |
|---|---|
| GET `/images/preview?observation_id=&ra=&dec=&size_deg=0.5&stretch=asinh&low_pct=1&high_pct=99.5` | `image/png` of an IRSA cutout of one spectral image (not the envelope: a binary image). Errors still return the envelope as JSON. |
| GET `/images/preview/info` (same parameters) | Envelope; `data.preview` = `png_url`, `width`, `height`, `stretch`, `scale_range {low, high, unit, percentiles}`, `blank_fraction`, `corners_radec {top_left, top_right, bottom_right, bottom_left, frame}`, `detector`, `time_utc`, `source_fits_url`, `note`; `media[0].media_type = "png_preview"`. |

`/images/search` items, the `display_image` action and `media` carry `preview_url` (a path).

### Knowledge endpoints

| Endpoint | Body | Adds to `data` |
|---|---|---|
| POST `/knowledge/search` | `{query, language?: tr\|en, topic?, top_k=4}` | `knowledge: {query, language, index_version, retriever, other_language_used, count, hits[]}`; each hit has `chunk_id, title, heading, text, score, sources[]` |
| GET `/knowledge/sources` | – | `registry[]` (all source records), `registry_version`, `knowledge_base` status |

### Citizen-science candidates

| Endpoint | Body |
|---|---|
| POST `/candidates` | `{origin: human\|ai, created_by, title?, target: {ra, dec, object_name?}, reason, observation_ids[]}` |
| GET `/candidates` | `?status=&limit=50&offset=0` → `data.candidates: {total, candidates[], by_status}`, `data.log_chain_valid` |
| GET `/candidates/{id}` | – |
| POST `/candidates/{id}/reviews` | `{reviewer_id, classification, self_reported_certainty: low\|medium\|high, comment?, observation_ids_inspected[]}` |
| POST `/candidates/{id}/reviews/{review_id}/validation` | `{validator_id, decision: accepted\|rejected, note?}`; the validator must not be the reviewer |
| POST `/candidates/{id}/confirmation` | `{recorded_by, reference_url (https), reference_title, note?}`; needs at least one review |
| GET `/candidates/{id}/audit` | full event history and `log_chain_valid` |

`classification` is one of `real_motion`, `real_brightness_change`, `artifact`, `known_object`,
`no_change_visible`, `cannot_tell`. Status is derived from recorded events only:
`ai_generated_candidate` / `unreviewed_candidate` → `human_reviewed_candidate` →
`scientifically_confirmed`. `is_confirmed_discovery` is true only in the last state.

### System endpoints

GET `/health` (also at the root, `/health`) → `data: {status, version, uptime_s, ai_configured,
ai_model, instruction_version, rag_enabled, knowledge_base, scientific_config, candidate_store}`;
`status` is `degraded` (with `degraded[]`) when the knowledge base is unavailable or the candidate log
failed its integrity check. `?deep=true` adds `upstream[]` with reachability of IRSA and Horizons.
POST `/chat` is also served at the root (`/chat`) for the web front end.
GET `/capabilities` → tools with JSON schemas, action types, collections, detector bands, limits.

## 4. Actions

`actions` is an ordered list of `{ "type": …, "payload": {…} }`. Execute them in order. Ignore
types you do not know.

| Type | Payload | Frontend should |
|---|---|---|
| `focus_map` | `ra`, `dec`, `frame`, optional `radius_deg`, `fov_deg`, `epoch_utc` | Centre the sky view. At most one per response. |
| `display_object` | `object` (schema above) | Show the object card / marker |
| `display_observations` | `total`, `returned`, `target`, `observation_ids[]`; or `view: "periods"`, `periods[]` | Show the observation list or timeline. Records are in `data.observations` / `data.observation_periods`. |
| `display_image` | `products[]`: `observation_id`, `detector`, `t_min_utc`, `url`, `cutout_url`, `format`, `verified` | Load the FITS cutouts |
| `display_spectrum` | `products[]`, `samples[]`, `samples_note` | Show spectral products / sample plot |
| `request_clarification` | `question`, `options[]` | Ask the user; send the answer as the next `/chat` message |
| `show_error` | `code`, `message` | Show a notice. Codes include `object_not_found`, `moving_target`, and every `error.code` |

`url` and `cutout_url` point to FITS files on IRSA (`image/fits`), not to PNG/JPEG. The frontend
needs a FITS-capable viewer or its own rendering service.

## 5. Errors

| HTTP | `error.code` | When |
|---|---|---|
| 422 | `invalid_input` | Bad or missing fields; `error.details.fields[]` lists them |
| 404 | `not_found` | Unknown observation id or route |
| 413 | `payload_too_large` | Body over `MAX_REQUEST_BODY_BYTES` |
| 429 | `rate_limited` | Per-client chat rate limit, or the AI provider's quota when fallback is off |
| 502 | `upstream_error` | An archive or the AI provider answered with an error |
| 504 | `upstream_unavailable` | An archive could not be reached or timed out |
| 503 | `ai_unavailable` | The AI provider is not configured or rejected the key (only when fallback is off) |
| 401 | `unauthorized` | Candidate write without the team token (`X-QFit-Token`) when `QFIT_TEAM_TOKEN` is set |
| 500 | `internal_error` | Unexpected failure; details stay in the server log |

`error.retryable` tells whether trying again can help. Error bodies use the same envelope and
include one `show_error` action.

## 6. Minimal client

```ts
async function ask(message: string, context?: object, history: object[] = []) {
  const res = await fetch(`${QFIT_URL}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context, history }),
  });
  const body = await res.json();          // always the envelope, also on errors
  showMessage(body.message, body.message_source);
  for (const action of body.actions) dispatch(action.type, action.payload, body.data);
  return body;
}
```

## 7. Stability

Fields are only added within `v1`, never renamed or removed. Breaking changes go to `/api/v2`.
