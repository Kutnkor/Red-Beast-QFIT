# Feature locations after the SPHERE-X integration

The same shell state, API hooks, Viewer and Three.js runtime drive both layouts. “Automated” below means DOM/API/numerical checks, not browser screenshot/GPU acceptance.

| Existing capability | Default UI location | Evidence / status |
|---|---|---|
| Five targets, ready sequences | Target tabs; searchable catalogue | Automated target/observation flows |
| Single stellar surface/environment | Star tab; original persistent Three.js canvas | Original model, shader and geometry suites; visual pending |
| 120 neighbours / Hipparcos sky | Sky tab, scene target picking and searchable list | Original astrometry/catalogue tests; visual pending |
| Motion 2000–2100, play/speed | Bottom year ruler, play, speed selector | Store/keyboard tests; no changed scientific inputs |
| Actual observation dates | Observations → Frames / Time stack | Existing Timeline and Viewer retained |
| Blink, single/side/difference/stack/co-moving stack | Observations → original toolbar | Existing Viewer suite retained |
| Gaia/AllWISE/predicted overlays | Analysis tools → Layers | Existing analysis tab and overlay API |
| Marks, classifications, local notes | Analysis tools → Marks | Existing marks/edit/read-only tests |
| Light curve and wavelength | Analysis tools → Light curve / Wavelength | Existing photometry/spectrum tests |
| Share, creator edit key, `/o/:id` | Existing analysis/share controls | Existing observation tests; notes excluded from QFIT |
| RA/Dec, FOV, date, wavelength search | Search → coordinate archive form | New DOM search test; original form/search cases retained |
| Job progress/cancel/retry | Visible status panel during archive work | New progress test plus original legacy job flows |
| Physical profile uncertainties and sources | Measurement callouts / M / dock → Measurements | New DOM check for binary unknowns and component values |
| Five downloadable Three.js models | Measurements → existing model section | Existing model asset/factory tests |
| Download current view | Measurements or Settings → Download view | Existing command route retained; assistant requests confirmation |
| Sources/provenance/method | Top Sources; frame provenance link | Existing dialogs and citations |
| Tutorials and quizzes | Guide → Research task / analysis Task tab | Existing tutorial suite |
| Language and persisted selection | Top TR/EN | Both shell tests; new text has both languages |
| Offline/loading/error/WebGL fallback | Existing scene/error states plus status panel | Existing handlers kept; source-review of fallback layout; real browser pending |
| Keyboard / focus | Existing map plus Ctrl/⌘K, H, S, context-sensitive M | DOM and command tests; manual accessibility pending |
| Assistant mock/off | Legacy panel and new mascot | Contract tests; default remains off |
| QFIT provider, source cards, citations, stop/retry | Robin mascot or S | New transport/adapter/component tests; separate real-provider evaluation in `reports/integration/assistant-eval.json` |
| New Gaia color–magnitude diagram | H / diagram dock | Catalogue-derived diagram; no evolutionary curve |
| New transparency preference | Settings | Local preference + platform reduced-motion/transparency rules |
| Legacy / embed / deep links | `?ui=legacy`, `?embed=1`, `/s/:id`, `/o/:id` | Routing tests; parameters retained |

No baseline route, science endpoint or data file was removed. The source prototype's hypothetical mass/age/evolution controls were never baseline BlinkSpace features; their grounded replacements are documented in `DECISIONS.md`. Pixel comparisons, live GPU, physical-device accessibility and new-UI demo screenshots remain pending the previously denied browser access.
