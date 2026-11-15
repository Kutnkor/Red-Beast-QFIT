# Integration handoff

The SPHERE-X v5 default UI and original QFIT robin/agent are integrated into BlinkSpace. The existing Three.js models and real observation pipeline are retained. The old UI remains at `?ui=legacy`.

Automated gates: 203 backend tests passed (4 live archive cases skipped), 181 frontend tests passed; original QFIT audit 199 passed, 11 skipped, 7 optional Gemini cases deselected. Three API paths were added without removing/changing baseline fields. All 141 science/seed file hashes and 198 upstream QFIT file hashes remain identical. Docker checked all 45 served UI files byte-for-byte, five ready real-data targets, five local source cards, uid 1000, same-origin CSP and key-pattern scans.

The user's private local installation has QFIT enabled; the OpenAI connection and a full HTTP UI-proposal round trip were tested. The release ZIP/image contain no key. Ten live source-grounding questions plus targeted follow-ups are documented with the errors found and corrected; AI accuracy is not guaranteed. See `assistant_eval.md`.

The earlier browser permission denial was not bypassed. New desktop/mobile screenshots, actual GPU/FPS inspection and screen-reader/physical-device acceptance remain pending. The previously reviewed seven-slide demo is retained as historical material and not represented as a new-interface review. No GitHub push, public deployment or competition submission took place.

Launch the ZIP with `Start-BlinkSpace.command` on macOS. Sources and the production UI are included; `.env`, user runtime data, environments and caches are excluded. Local archive data are public seeded observations, not user notes. The pre-existing Three.js-only archive remains unchanged; the full release also includes those five model assets.
