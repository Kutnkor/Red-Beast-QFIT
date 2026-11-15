# Local API performance — current integration

Measured with pipeline 1.2.0. Client and server were on the same machine; these figures are HTTP data-transfer timings, not first-paint time or GPU frame rate. Five independent reads included the target list, sequence JSON and all frame PNGs.

| Target | Frames | Trials | Median ms | Sequence + PNG bytes |
|---|---:|---:|---:|---:|
| barnard | 6 | 5 | 11.0 | 40703 |
| eps-indi-b | 6 | 5 | 13.0 | 40405 |
| wise-0855 | 2 | 5 | 5.0 | 19498 |
| rw-aur | 3 | 5 | 6.0 | 24647 |
| r-dra | 8 | 5 | 14.0 | 46883 |

Concurrent reads: 24 requests with 8 threads; all successful: True. Total 0.04 seconds. Cached search returned an immediate completed job. The configured search rate limit returned HTTP429 as expected.

Raw results: `performance.json`. Fresh archive-search performance could not pass acceptance because NASA/IPAC archive services returned HTTP502 during the live tests. Renderer55FPS/30FPS, scene-switch latency, 20switches memory stability and context-loss recovery are not measured here. Full browser acceptance remains pending the saved browser permission restriction. No figure from the imported source is reused as a new result.

A later live fresh-coordinate workflow completed on the same date after the archive recovered; see `new-coordinate-live.json` for actual stage timings. It is a single sample, not a replacement for the five-trial cached HTTP timings or a GPU benchmark.
