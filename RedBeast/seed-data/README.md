# Optional public preset seed

The release Docker build prepares the five real SPHEREx presets and their track caches here.
To build without an archive connection, first run `tools.package_seed` from the backend
directory with `--destination ../seed-data`. It exports only the five public presets,
their raw cutouts and processed products. It removes observations, edit keys, jobs and
user searches from the copied database. Do not copy an entire runtime data directory here.

Generated files are delivery artifacts and should not be committed to a source repository.
