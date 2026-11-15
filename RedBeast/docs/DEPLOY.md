# Deployment and persistent data

The application requires a long-lived Python process, outbound HTTPS to IRSA and a local
writable data directory. Static-only hosting cannot run the scientific pipeline. The
repository does not claim a public URL or a completed competition submission.

## Reproducible image

```bash
docker build -t blinkspace .
docker run --rm --name blinkspace -p 8000:8000 -v blinkspace-data:/data blinkspace
```

`docker compose up --build` is the equivalent named-volume configuration. The image builds
React locally, installs the pinned Python dependencies, prepares the five real SPHEREx
presets, precomputes their tracks and checks every preset's files. A missing preset fails
a release build; the image does not silently replace it with synthetic data.

The container runs as uid 1000. At startup, an empty data directory is populated from
`/app/seed-data`. An existing directory is never overwritten. Keep `/data` on a persistent
volume if shared observations must survive restarts. The seed contains public presets,
not subsequently created observations or their editing keys.

The entrypoint supports `PORT` (default 8000), one worker and proxy headers. Set
`FORWARDED_ALLOW_IPS` to the known reverse-proxy addresses. Set it to `*` only on a platform
that prevents direct access around its trusted proxy. Otherwise a client could spoof the
address used for request limits. The built-in health check calls `/api/health` on `$PORT`.

### Build without archive access

Prepare data on a machine with archive access, then from `backend`:

```bash
python -m tools.prepare_presets
python -m tools.precompute_tracks
python -m tools.package_seed --destination ../seed-data
```

`package_seed` copies only the five public presets and required raw/processed files into
an empty destination. Its copied database removes user observations, edit-key hashes, jobs,
searches and query/catalogue caches. It does not alter the original runtime data. The
Dockerfile uses this exported seed and verifies it instead of downloading again.
Do not copy a runtime data directory wholesale into a distributable image.

`--build-arg BLINKSPACE_BUILD_SEED=0` is an explicit development-only image without ready
presets. It does not satisfy the five-preset release acceptance check.

## Hosting conditions verified on 14 November 2026

**Hugging Face Docker Spaces:** the current official overview states that creating a new
compute Space (Docker or Gradio) requires a paid account plan. CPU Basic has no hourly
compute charge, but this is not a promise of free account eligibility. Confirm the account's
eligibility before choosing it. See the [Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview).

The README metadata sets `sdk: docker` and `app_port: 8000`. The app listens on that port.
Build and runtime environments are separate; do not expect runtime-mounted storage during
an image build. See [Docker Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-docker).

Default storage is ephemeral. In the current storage documentation, Storage Buckets can
be mounted as local files. BlinkSpace's SQLite locking and WAL behaviour on these mounted
buckets has not been tested, so database durability there is not yet verified.
Without an appropriate durable disk arrangement,
new shared observations can disappear on restart; public presets are restored from the
seed. See [Spaces storage](https://huggingface.co/docs/hub/en/spaces-storage).

**Render:** a free web service sleeps after 15 minutes without inbound requests and takes
about a minute to restart. Filesystem changes are lost on restart, redeploy or sleep;
free services cannot attach persistent disks. A workspace receives 750 free instance hours
per month. This is suitable for a temporary seeded demo only if observation loss is made
clear; persistent SQLite needs an appropriate paid disk/service arrangement. See
[Render's free-service limitations](https://render.com/docs/free).

No paid hosting resource has been started. Account login, any paid-plan purchase, publishing
source or changing repository visibility require the user's final decision. The source
package can be reviewed and tested locally before that step.

## Post-deployment checks

1. `/api/health` returns `status: ok`; `/api/targets` has five non-null `ready_sequence_id` values.
2. Each preset opens its real frames and shows dates, wavelengths, quality and provenance.
3. The catalogue and bright-sky resources load; all three scene modes work or show an accessible fallback.
4. A new coordinate search completes, can be cancelled and shows the actual job stage.
5. Mark and save a test observation; open its share link in a separate browser.
6. Restart the container and reopen the link. On ephemeral hosting, record the expected loss explicitly.
7. Check EN/TR and viewport widths 1440, 1024 and 375. Check that `/api/assistant/status` is disabled.
8. Record the real public address, revision and results in the current evidence report.

The independent user test and competition “Submit for Judging” step require real people
and the project owner's account. A blank protocol or a local preview is not proof of either.
A FortiGuard classification request also needs the final public URL and an accurate category;
prepare it after deployment and record actual submission status.

## Archive transport

`BLINKSPACE_ARCHIVE_PROTOCOL=auto` uses TAP and the official SIA fallback. To select the
working SIA route directly, set `BLINKSPACE_ARCHIVE_PROTOCOL=sia`.
`BLINKSPACE_GAIA_PROVIDER=esa` reads the same Gaia DR3 fields from ESA's primary archive
when the IRSA mirror is unavailable. The pipeline records the selected source endpoint.
These settings do not substitute synthetic observations or a different catalogue release.
Examples are in `.env.example`.

## Refreshing scientific data

From `backend`, regenerate presets, tracks and reports with `tools.prepare_presets`,
`tools.precompute_tracks` and `tools.target_report`. Rebuild the source bundle with
`tools.build_knowledge`. Export a new seed into a fresh directory and rebuild the image.
Retain old shared sequences; a new archive release must not rewrite their provenance.
