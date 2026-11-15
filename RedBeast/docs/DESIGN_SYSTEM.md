# RedBeast design system — one language for every screen

15 November 2026. This note records the unification pass that brought the observation viewer,
the sky and star views and the dialogs into the same visual language as the V4 education
screen, and the simplification pass that followed it on the same day. It replaces the visual descriptions in `UI_INVENTORY.md` (V5) for the
default shell. Science, data and API behaviour were not changed by this pass.

## The rules

| Rule | Meaning |
|---|---|
| Navy and white carry the interface | Surfaces are navy glass (`.kx-glass`); the selected thing is a white plate with navy ink. |
| Orange marks what is live | Current frame, current year, current stage, focus ring, the user's own marks, the "you are here" marker, a short line under the selected tab and under the primary button, the word "Red" in the wordmark, and a faint rim light in the corner of glass. Warnings and "computed" values stay typographic (a `!` prefix, a periwinkle tone, dashed or dotted lines). |
| Small free components | No large opaque panels. Values sit in chips around the star and controls float over the image. |
| Few boxes, one main action | A column has one white primary button. Nothing repeats what the top bar already offers. A control that only matters in one mode is hidden in the others (the A and B pickers appear in side-by-side and difference mode only). Lists and dialogs are flat: plain links, underlined tabs, no box inside a box. |
| One motion vocabulary | Entrances rise 8–14 px and fade (`kx-rise`, `lv-up`, 360–650 ms, `cubic-bezier(.16,1,.3,1)`); selections slide on a spring (`cubic-bezier(.3,1.22,.5,1)`); presses scale to .96; disclosures rotate a chevron. Only `transform` and `opacity` animate. |
| Real frames never blend | Switching, blinking and playing real SPHEREx frames is always a hard cut. No crossfade, no interpolation. Interface chrome may animate around the image; the pixels do not. |
| Reduced motion is respected | `prefers-reduced-motion` and the in-app calm setting collapse every animation and transition. |

Type: Bricolage Grotesque (interface) and Martian Mono (numbers that must align), both bundled
locally under the OFL. Radius 10–20 px. Palette tokens live in `frontend/src/tokens.css`.

## Where things live

| File | Role |
|---|---|
| `frontend/src/tokens.css` | Palette, fonts and radii. The legacy token names point at the V4 palette, so old CSS is re-skinned without edits. |
| `frontend/src/v4/kit.css`, `kit.tsx` | Shared components (`kx-` prefix): `Glider` (sliding tabs), `RingPlay`, `WaveRuler`, `Odometer`, `Panel`, `KIcon`, chips, stage marks. |
| `frontend/src/v4/live.tsx` | The live views built from the kit: title, target tabs, value chips on an arc around the star, year and evolution strips, model switch. |
| `frontend/src/v4/frame.css` | Layout of the kit inside the 1440 × 810 V4 stage, and the phone layout (image or scene first, dock fixed at the bottom). |
| `frontend/src/v4/unify.css` | Re-skin of everything that predates the kit: viewer toolbar, timeline, analysis drawer, dialogs, sources list, sky star picker, classic and legacy shells. |
| `frontend/src/v4/V4Observatory.tsx` | The shell. `v4.html` runs in a same-origin frame; React portals the live views into it and copies the page styles into the frame and the viewer's shadow root, so one stylesheet reaches all three contexts. |
| `frontend/src/v4/runtime.ts` | The original V4 controller (education view, top bar, dock, guided tour). |

`.observatory button { background: none; border: 0 }` in the older shell stylesheet outranks
single-class rules. When a restyled button looks unstyled inside the shell, restate the rule with
two classes (see the last block of `unify.css`).

## The Sky view starts from the Milky Way

A first-time visitor could not tell that the Sky view showed our own galaxy: it was 120 dots on
black. It now opens on a top-down drawing of the Milky Way and flies down to the measured
neighbourhood on request (`skyScale` in the app state, `?sky=local` in the address).

| Part | What it is | Honest label |
|---|---|---|
| Spiral arms, bar, bulge, disc (`three/components/MilkyWay.ts`) | About 80,000 particles on four logarithmic spirals (pitch 12.5 degrees), a bar turned 27 degrees, the Orion Spur through the Sun. The Sun is 8.2 kpc from the centre, between the Sagittarius and Perseus arms. | Illustration. The caption and the kicker say so. |
| "You are here" marker | The only orange thing on the map. | Position by construction. |
| Target dots and the ring around them | Catalogue positions converted from ICRS to galactic coordinates and drawn to scale. The ring is the distance of the farthest target. | Computed from the catalogue. |
| Three facts in the left column | Width about 100,000 light-years, 100 to 400 billion stars, one lap of the Sun about 230 million years. | Round, widely quoted values, marked with "≈". |

The flight between the two scales is one camera move (dive at the Sun, swap what is drawn,
settle). With reduced motion it is an instant swap. The year ruler and the value chips belong to
the measured neighbourhood and are not shown on the galaxy.

## Simplification pass

Feedback on the first unified build was that it looked nested and hard for a beginner to read.
What changed:

- Observations: the left column keeps one primary button and two secondary ones (the search and
  sources buttons duplicated the top bar). The target list lost its tray. The A and B pickers show
  only in the comparison modes. The saturation notice is one line of text. Pointer coordinates show
  while the pointer is on the image.
- Star and Sky: the surface-animation toggle and the ICRS disclosure left the column (the fourth
  chip already shows RA and Dec and opens the full table). Scene captions show their first note;
  the rest appears on hover.
- Sources dialog: a plain two-column list of links. Analysis drawer: a flat sheet with one row of
  underlined tabs.
- Q-FIT: the panel is back to the assistant's own original styling; the example-question chips
  were removed.

## Third pass: sheets, lanes, the robin

- **Sheets, not pop-ups.** `v4/sheet.ts` remembers where the last click happened. A panel (kit `Panel` and the older
  `Dialog`) starts at that point, grows along a short arc and docks: sheets are part of the bottom edge with a grabber,
  the search palette hangs from the search field. Closing sends it back to where it came from. The scrim is light, so
  the page stays visible. Reduced motion removes the move.
- **Lanes.** In the observation viewer nothing sits on the image any more: image tools are on the line under it, the
  filmstrip is a column beside it, and the analysis drawer is a column the viewer makes room for. On Sky, around the
  Sun, the value chips stand in a column at the right edge.
- **Black hole** (`three/components/BlackHole.ts`): one camera-facing quad; every pixel follows a light ray through a
  Schwarzschild-like field, so the far side of the disc arches over the shadow, a thin ring hugs it and far stars
  smear into arcs. The disc keeps flowing while the view rests on it. Illustration, not a simulation.
- **Around the Sun**: a stalk from every star to the reference plane (height is readable), named stars labelled,
  rings in light-years at 5, 10 and 15 pc, a brighter Sun, an orange line towards the galactic centre.
- **Star surface**: warped multi-octave granulation and stronger limb darkening replace the single noise layer.
- **Tours**: six, one per page (observations, Milky Way, around the Sun, catalogue star, published model, education).
  On the first visit to a page the robin says in one line what the page is and offers the tour (`RobinHint`).
- **The robin can act** (`qfit/localIntent.ts`): plain requests such as "take me to the Sun", "show the Milky Way",
  "go to Barnard", "side by side", "next frame", "go to the year 2080", "open sources" are carried out in the app
  by rules, with no model call and no science claim. Anything with a question mark goes to the sourced assistant
  as before. A command that ran can be pinned as a shortcut; shortcuts and the last messages stay in the browser.
- **Material**: lighter glass with more backdrop saturation and an orange rim light, film grain over the page, a
  drawn geometric lowercase wordmark (`redbeast`: one stroke weight, every bowl the same circle, no font file).
- **Final touches**: a sheet can be dragged down by its header to put it away (a short drag springs back); around the
  Sun every star is a small lit sphere coloured by temperature, with its glow behind it; the in-scene star list is
  gone and "Find a star" opens the Ctrl+K search instead.

## Anchors and paths

- **No floating text in the 3D scenes.** Every label is a dot on the object, a short curved leader and a text plate
  (`three/labels.ts`, styles in `three/scene.css`). A plate that would leave the canvas moves to the other side of
  its point. Each view keeps about five labels: on the Milky Way the Sun, the centre, the two arms beside the Sun,
  the Sun's path and the target ring; around the Sun the Sun, the chosen star, the nearest named star, the
  direction of the galactic centre and one distance ring.
- **Paths are drawn as light, not as ruler lines** (`buildGlowLine` in `three/components/lines.ts`): the Sun's path
  round the galaxy is an arc that fades behind it and ends in an arrowhead, the direction of the galactic centre is
  a tapering arc, distance rings are solid and faint, the stalks under the stars thin out towards the plane and
  land on a small foot, and the star's motion trail brightens towards the future.
- **Stars around the Sun** are smaller and carry an illustrative photosphere: granulation, a few darker spots,
  limb darkening and a thin rim, different for each star.
- **No dark rectangle behind the 3D scenes.** The WebGL canvas is transparent, so the scene sits on the page
  background; only its outermost band fades.

## Robustness pass

- **Labels follow their objects at every window size.** The V4 stage is CSS-scaled with the window; the label layer
  now measures its own layout box instead of the renderer's on-screen size, so dots and leaders stay on the object
  when the window is larger or smaller than 1440 x 810. Labels also keep clear of the text column and the chip
  column (`--label-reserve-left/right` on `.sky-labels`).
- **Photometry without the compiled extension.** `backend/blinkspace/photometry.py` falls back to its own
  circle-pixel overlap (`circular_weights`, exact in y, midpoint rule in x, agreement better than 1e-5 per pixel)
  when `photutils` cannot be imported, for example where Windows Smart App Control blocks its binary. Light curves
  and spectra work there and the backend suite passes in full (204).
- **Patient archive client.** IRSA's front proxy answers 502/503/504 for a while under load. The SIA client now
  runs two collection queries at a time and waits out those answers (up to eight attempts, at most 20 s apart)
  instead of failing the job after a few seconds. All four collections must still succeed.
- **Any catalogue star can ask for real frames.** The Observations empty state offers the archive fetch for every
  star, not only the five prepared targets.
- **Stars without a model profile** show what the catalogue measured (Gaia G brightness, BP-RP colour, catalogue
  temperature where present) instead of dashes. No value is invented.
- **Opening moment** (`v4/Opening.tsx`): once per browser session the wordmark draws itself, the robin lands and the
  curtain lifts onto the observations. Skipped with reduced motion, in capture mode and under test.

## Archive jobs no longer hold the queue

There is one job worker. A job that waited on a failing archive used to keep it for minutes: the SIA client
retried with growing pauses and did not listen for cancel while it waited, so every later request sat in
"queued", and asking again joined the cancelled job instead of starting a new one. Now:

- the archive query runs under a supervisor (`archive.interruptible`) that checks cancel and the job timeout five
  times a second; a cancel takes effect in about a quarter of a second (measured live against IRSA);
- retries of 502/503/504 answers stop after `SIA_BUDGET_S` (60 s) and the job reports a clear archive error;
- while it retries, the job says so (`detail.archive_wait`: HTTP status, attempt, next try, budget), and a queued
  job says how many jobs are ahead of it (`ahead`); the job panel shows both and sits under the empty-state
  message;
- a job that is being cancelled is never re-joined; asking again starts a fresh job behind it;
- if the archive is down but frames were fetched earlier for the same request, those open with a note saying when
  they were fetched (`detail.stale`), instead of the job failing.

Catalogue mirrors are an operator choice: `BLINKSPACE_GAIA_PROVIDER` is `irsa` (default), `esa` or `vizier` (the
official VizieR Harvard mirror of I/355/gaiadr3, added in this pass), as `BLINKSPACE_ALLWISE_PROVIDER` already
was. Nothing is substituted silently; the mirror is recorded in each row's provenance.

## What changed for the challenge task

The Space Apps brief asks for a tool that lets anyone see changes over time in SPHEREx images.
Three additions serve that directly, all in the default Observations view:

- **Blink** button (and the `B` key) on the image tools. The first press moves B to the next real
  frame; further presses flip A and B. Hard cut.
- **Filmstrip** of every real frame beside the single-frame pane, with the frame number, the A
  reference badge and the current-frame marker. Click to cut to a frame.
- **Timeline** ticks rise near the pointer and the current frame; clicks map correctly in the
  scaled stage (they drifted before).

## Checks on this pass (Windows 11, this working copy)

| Check | Result |
|---|---|
| Type check and production build | Pass |
| Frontend tests (`npx vitest run`) | 225 passed (includes checks of the galaxy map placement and of the robin's navigation) |
| Backend tests (`python -m pytest` in `backend/`) | 211 passed, 4 live tests skipped. This includes the machine where Windows Smart App Control blocks the compiled `photutils` extension: the photometry fallback is used there. |
| API smoke (`python tools/smoke_api.py` against the running server) | 82 of 82 read endpoints answer for the five targets; the light-curve endpoint returns 500 on this machine for the same `photutils` reason. |
| Real-time browser captures (Edge via Playwright) | Observations (single, side by side, difference, playing, drawer, blink), Sky, Star (catalogue, published model, education), search, tour, dialogs, Q-FIT, English, 1024 × 640, 390 × 844, classic and legacy shells: no console errors. Playback measured at about 7 ms per frame. |

A Windows-only fault was fixed on the way: several JSON and Markdown files were read with the
system code page instead of UTF-8, which broke the assistant's source lookup on a Turkish
Windows install (16 backend tests). All text reads in `backend/` and `tools/` now pass
`encoding="utf-8"`.

## Running on Windows

```
cd RedBeast
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend && npm ci && npx tsc -b && npx vite build && cd ..
set PYTHONPATH=backend
.venv\Scripts\python -m tools.launch
```

The app is then at http://127.0.0.1:8765. `BLINKSPACE_ARCHIVE_PROTOCOL=sia`,
`BLINKSPACE_GAIA_PROVIDER=vizier` and `BLINKSPACE_ALLWISE_PROVIDER=vizier` select the mirrors that
answered from this network (on 15 November 2026 IRSA returned 502 for every service and ESA's Gaia archive did not
accept connections from it). If Windows Smart App Control blocks the `photutils` binary, the five
prepared targets still work; new aperture photometry (light curve, spectrum jobs) does not.
Do not disable the security feature to get around it — run those parts on a machine or in the
Docker image where the package loads.

## Known limits

- The classic (`?ui=classic`) and legacy (`?ui=legacy`) shells share the tokens and the restyled
  controls, but their layouts were not redesigned.
- Phone layout is checked in emulation only, not on a device.
- Value chips around the star have no leader lines; the 3D scene does not report the star's
  on-screen radius to the interface.
- Public hosting, independent user tests and measured frame rates on low-end hardware are still
  open, as recorded in `STATUS.md`.
- The Q-FIT robin's sprites and beak-pull choreography, and the assistant panel's own styling, are unchanged by design.
- The Milky Way is a drawing, not data: arm positions follow the common four-arm picture and should not be read as measurements.
