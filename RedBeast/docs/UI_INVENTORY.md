# SPHERE-X v5 UI inventory

The user’s latest ZIP contains HTML/CSS v5 rather than the older Unity UXML described in the integration prompt. Each source element with an id is listed below; source declarations, typography, spacing, glass and timings are extracted to `frontend/src/ui/observatory/tokens.json` by `tools/extract_ui_tokens.py`. Source reference resolution is 1440×810 at scale 1; responsive web layout reflows at 759px. No Unity-only property translation applies.

Evidence: `frontend/src/tests/observatory.test.tsx`, `qfit.test.tsx`, preserved baseline UI tests and `reports/integration/regression.json`. Existing supplied screenshots were used as design references, **not** as new screenshot evidence. Real desktop/mobile/GPU acceptance remains pending browser access. “Adapted” does not mean pixel-perfect or visually verified.

| ID | Source element | Source line | Type | Web region | Behaviour / states | Status |
|---|---|---|---|---|---|---|
| UI-001 | `stage` | `body.html:1` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-002 | `starGL` | `body.html:3` | canvas | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-003 | `sky` | `body.html:4` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-004 | `glow` | `body.html:5` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-005 | `shell` | `body.html:6` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-006 | `bhring` | `body.html:7` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-007 | `star` | `body.html:8` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-008 | `shock` | `body.html:9` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-009 | `flash` | `body.html:10` | div | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-010 | `gr` | `body.html:12` | filter | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-011 | `leaders` | `body.html:16` | svg | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-012 | `lgR` | `body.html:17` | g | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-013 | `luR` | `body.html:17` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-014 | `ldR` | `body.html:17` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-015 | `mkR` | `body.html:17` | circle | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-016 | `lgT` | `body.html:18` | g | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-017 | `luT` | `body.html:18` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-018 | `ldT` | `body.html:18` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-019 | `mkT` | `body.html:18` | circle | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-020 | `lgL` | `body.html:19` | g | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-021 | `luL` | `body.html:19` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-022 | `ldL` | `body.html:19` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-023 | `mkL` | `body.html:19` | circle | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-024 | `lgM` | `body.html:20` | g | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-025 | `luM` | `body.html:20` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-026 | `ldM` | `body.html:20` | path | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-027 | `mkM` | `body.html:20` | circle | `three-scene` | Existing class-specific Three.js renderer; prototype particles/flash are not imported. | Adapted; visual pending |
| UI-028 | `logo` | `body.html:24` | div | `topbar` | Three live modes, search dialog, sources and TR/EN. | Adapted; visual pending |
| UI-029 | `viewTabs` | `body.html:25` | div | `topbar` | Three live modes, search dialog, sources and TR/EN. | Adapted; visual pending |
| UI-030 | `search` | `body.html:29` | button | `topbar` | Three live modes, search dialog, sources and TR/EN. | Adapted; visual pending |
| UI-031 | `sourcesBtn` | `body.html:30` | button | `topbar` | Three live modes, search dialog, sources and TR/EN. | Adapted; visual pending |
| UI-032 | `langTabs` | `body.html:31` | div | `topbar` | Three live modes, search dialog, sources and TR/EN. | Adapted; visual pending |
| UI-033 | `dock` | `body.html:34` | nav | `dock` | Measurements, Gaia diagram, QFIT, guide, settings; hover/focus/active. | Adapted; visual pending |
| UI-034 | `tip` | `body.html:41` | div | `dock` | Measurements, Gaia diagram, QFIT, guide, settings; hover/focus/active. | Adapted; visual pending |
| UI-035 | `name` | `body.html:44` | h1 | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-036 | `phGlyph` | `body.html:45` | i | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-037 | `phaseName` | `body.html:45` | span | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-038 | `phCount` | `body.html:45` | span | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-039 | `say` | `body.html:46` | p | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-040 | `pick` | `body.html:47` | div | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-041 | `starTabs` | `body.html:48` | div | `target-identity / target-tabs / motion-summary` | Five real targets, source-backed identity and computed motion. | Adapted; visual pending |
| UI-042 | `massLbl` | `body.html:49` | span | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-043 | `massVal` | `body.html:49` | b | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-044 | `fateIcon` | `body.html:49` | i | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-045 | `fate` | `body.html:49` | em | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-046 | `mruler` | `body.html:50` | div | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-047 | `mZones` | `body.html:51` | path | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-048 | `mTicks` | `body.html:51` | path | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-049 | `mGlyphs` | `body.html:52` | div | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-050 | `mknob` | `body.html:54` | div | `target-identity / target-tabs / motion-summary` | No adopted mass/fate values; replaced by sourced angular-motion summary, not fake stellar evolution. | Replaced (science) |
| UI-051 | `chips` | `body.html:59` | div | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-052 | `chipR` | `body.html:60` | div | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-053 | `tR` | `body.html:60` | i | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-054 | `vR` | `body.html:60` | b | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-055 | `uR` | `body.html:60` | em | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-056 | `cpR` | `body.html:61` | clippath | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-057 | `clR` | `body.html:61` | rect | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-058 | `sfR` | `body.html:61` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-059 | `spR` | `body.html:61` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-060 | `sdR` | `body.html:61` | circle | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-061 | `chipT` | `body.html:62` | div | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-062 | `tT` | `body.html:62` | i | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-063 | `vT` | `body.html:62` | b | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-064 | `uT` | `body.html:62` | em | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-065 | `cpT` | `body.html:63` | clippath | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-066 | `clT` | `body.html:63` | rect | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-067 | `sfT` | `body.html:63` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-068 | `spT` | `body.html:63` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-069 | `sdT` | `body.html:63` | circle | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-070 | `chipL` | `body.html:64` | div | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-071 | `tL` | `body.html:64` | i | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-072 | `vL` | `body.html:64` | b | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-073 | `uL` | `body.html:64` | em | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-074 | `cpL` | `body.html:65` | clippath | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-075 | `clL` | `body.html:65` | rect | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-076 | `sfL` | `body.html:65` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-077 | `spL` | `body.html:65` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-078 | `sdL` | `body.html:65` | circle | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-079 | `chipM` | `body.html:66` | div | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-080 | `tM` | `body.html:66` | i | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-081 | `vM` | `body.html:66` | b | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-082 | `uM` | `body.html:66` | em | `metric-callouts` | Radius/temperature plus distance/proper motion; click opens measurements, unknown remains unknown. | Adapted; visual pending |
| UI-083 | `cpM` | `body.html:67` | clippath | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-084 | `clM` | `body.html:67` | rect | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-085 | `sfM` | `body.html:67` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-086 | `spM` | `body.html:67` | path | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-087 | `sdM` | `body.html:67` | circle | `metric-callouts` | No fabricated evolution sparkline; measured/derived/unknown labels are shown instead. | Replaced (science) |
| UI-088 | `hrbox` | `body.html:70` | div | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-089 | `hr` | `body.html:72` | svg | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-090 | `hrFuture` | `body.html:74` | polyline | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-091 | `hrPast` | `body.html:75` | polyline | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-092 | `hrGhost` | `body.html:76` | circle | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-093 | `hrRing` | `body.html:77` | circle | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-094 | `hrNow` | `body.html:77` | circle | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-095 | `hxL` | `body.html:78` | text | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-096 | `hxR` | `body.html:78` | text | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-097 | `hrMsg` | `body.html:79` | text | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-098 | `hrHit` | `body.html:80` | rect | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-099 | `ttip` | `body.html:85` | div | `drawer-diagram` | Computed Gaia color–magnitude points; keyboard/click selects real catalogue targets. No evolutionary track. | Adapted; visual pending |
| UI-100 | `time` | `body.html:87` | section | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-101 | `ringSegs` | `body.html:90` | mask | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-102 | `ringMask` | `body.html:90` | circle | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-103 | `ringProg` | `body.html:91` | circle | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-104 | `ringTip` | `body.html:92` | circle | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-105 | `play` | `body.html:93` | button | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-106 | `speed` | `body.html:95` | button | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-107 | `speedTxt` | `body.html:95` | span | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-108 | `ruler` | `body.html:96` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-109 | `uni` | `body.html:97` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-110 | `ticks` | `body.html:98` | svg | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-111 | `ribG` | `body.html:98` | lineargradient | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-112 | `ribC` | `body.html:98` | clippath | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-113 | `ribR` | `body.html:98` | rect | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-114 | `ribF` | `body.html:98` | path | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-115 | `ribP` | `body.html:98` | path | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-116 | `tkFut` | `body.html:98` | path | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-117 | `tkPast` | `body.html:98` | path | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-118 | `ghostline` | `body.html:99` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-119 | `needle` | `body.html:100` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-120 | `hit` | `body.html:101` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-121 | `marks` | `body.html:102` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-122 | `odo` | `body.html:104` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-123 | `odoNum` | `body.html:104` | div | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-124 | `odoUnit` | `body.html:104` | small | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-125 | `odoNote` | `body.html:104` | em | `timeline` | 2000–2100 computed position or real frame dates; play/pause/speed, arrows, range focus. | Adapted; visual pending |
| UI-126 | `toasts` | `body.html:107` | div | `qfit` | Original robin, source cards/live configured AI, sources/caveats, cancellation, retry and confirmed actions. | Adapted; visual pending |
| UI-127 | `chat` | `body.html:109` | aside | `qfit` | Original robin, source cards/live configured AI, sources/caveats, cancellation, retry and confirmed actions. | Adapted; visual pending |
| UI-128 | `msgs` | `body.html:111` | div | `qfit` | Original robin, source cards/live configured AI, sources/caveats, cancellation, retry and confirmed actions. | Adapted; visual pending |
| UI-129 | `sugg` | `body.html:112` | div | `qfit` | Original robin, source cards/live configured AI, sources/caveats, cancellation, retry and confirmed actions. | Adapted; visual pending |
| UI-130 | `askForm` | `body.html:113` | form | `qfit` | Original robin, source cards/live configured AI, sources/caveats, cancellation, retry and confirmed actions. | Adapted; visual pending |
| UI-131 | `askIn` | `body.html:113` | input | `qfit` | Original robin, source cards/live configured AI, sources/caveats, cancellation, retry and confirmed actions. | Adapted; visual pending |
| UI-132 | `sources` | `body.html:116` | aside | `SourcesDialog` | Original real catalogue/profile/IRSA sources and provenance. | Adapted; visual pending |
| UI-133 | `srcCount` | `body.html:117` | span | `SourcesDialog` | Original real catalogue/profile/IRSA sources and provenance. | Adapted; visual pending |
| UI-134 | `srclist` | `body.html:119` | div | `SourcesDialog` | Original real catalogue/profile/IRSA sources and provenance. | Adapted; visual pending |
| UI-135 | `settings` | `body.html:122` | div | `SourcesDialog` | Original real catalogue/profile/IRSA sources and provenance. | Adapted; visual pending |
| UI-136 | `swMotion` | `body.html:124` | button | `drawer-settings` | Reduced transparency, quality, layers, view download; OS reduced motion stops animation. | Adapted; visual pending |
| UI-137 | `swSolid` | `body.html:125` | button | `drawer-settings` | Reduced transparency, quality, layers, view download; OS reduced motion stops animation. | Adapted; visual pending |
| UI-138 | `openBoard` | `body.html:127` | button | `drawer-settings` | Icon catalogue is source reference, not a baseline user feature; no nonfunctional button added. | Design utility only |
| UI-139 | `spot` | `body.html:130` | div | `drawer-settings` | Reduced transparency, quality, layers, view download; OS reduced motion stops animation. | Adapted; visual pending |
| UI-140 | `tour` | `body.html:131` | div | `drawer-settings` | Reduced transparency, quality, layers, view download; OS reduced motion stops animation. | Adapted; visual pending |
| UI-141 | `tourT` | `body.html:132` | p | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-142 | `tourDots` | `body.html:133` | div | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-143 | `tourSkip` | `body.html:133` | button | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-144 | `tourBack` | `body.html:133` | button | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-145 | `tourNext` | `body.html:133` | button | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-146 | `scrim` | `body.html:136` | div | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-147 | `pal` | `body.html:137` | div | `drawer-guide / Task tab` | Four-step overview plus preserved interactive research tutorials and quizzes. | Adapted; visual pending |
| UI-148 | `palIn` | `body.html:140` | input | `search dialog` | Catalogue filter and real archive form; keyboard Tab/Enter/Esc; original dialog focus trap. | Adapted; visual pending |
| UI-149 | `palList` | `body.html:142` | div | `search dialog` | Catalogue filter and real archive form; keyboard Tab/Enter/Esc; original dialog focus trap. | Adapted; visual pending |
| UI-150 | `palCount` | `body.html:143` | span | `search dialog` | Catalogue filter and real archive form; keyboard Tab/Enter/Esc; original dialog focus trap. | Adapted; visual pending |
| UI-151 | `board` | `body.html:146` | div | `search dialog` | Catalogue filter and real archive form; keyboard Tab/Enter/Esc; original dialog focus trap. | Adapted; visual pending |

The 63-row earlier plan remains represented by the retained application capabilities in FEATURE_PARITY; mass/fate/prototype evolution and internal icon-board controls are explicit adaptations, not new scientific claims. Source icons are local SVG symbols; fonts are local OFL assets. Hover/focus/pressed/disabled states, Escape closing, reduced-motion CSS and off/error/loading assistant states are implemented. New screenshot/performance checks are not marked passed.
