# Robin mascot and chat panel

Q-FIT's figure is a robin (kızılgerdan). It sits in a corner of the screen; clicking it slides a chat
panel in from that edge. This page is the specification; two working implementations follow it:

| Implementation | Where | Run |
|---|---|---|
| React component (for the team's React + Three.js app) | `mascot/react/src/qfit/QFitAssistant.tsx` | copy `src/qfit/` into the app; `npm run typecheck` in `mascot/react` |
| Plain HTML/CSS/JS | `mascot/vanilla/qfit-widget.{css,js}` | `<link>` the CSS, load the JS, `new QFitWidget(element, { api, corner })` |

## Assets

All in `mascot/assets/`, built from the three originals by `scripts/build_mascot_assets.py` (needs Pillow).
`mascot/assets/mascot.json` describes them for code. The script also refreshes the copies the React component imports (`mascot/react/src/qfit/assets/`).

| File | What it is |
|---|---|
| `source/robin_figure.png` | **The official figure** (1254 × 1254, transparent): robin with the eye beam and star. Unmodified. |
| `source/robin_thinking.gif` | Original thinking animation: thought bubble with "…", 9 frames × 350 ms. Unmodified. |
| `source/robin_speaking.gif` | Original speaking animation: beak opens, sparkles, 9 frames × 80 ms. Unmodified. |
| `normalized/idle.png` | The figure on the shared canvas |
| `normalized/quiet.png` | The bird without beam or sparkles (first speaking frame) |
| `normalized/thinking/frame_00..08.png`, `normalized/speaking/frame_00..08.png` | Animation frames on the shared canvas |
| `spritesheets/thinking.png`, `spritesheets/speaking.png` | The 9 frames side by side (2880 × 272) |
| `icons/robin_{512,256,128,64,32}.png` | Square icons (favicon, panel header, app icon) |

**Shared canvas.** Every normalized image is 320 × 272 px with the bird 192 px tall, its body centred
at x = 120 and its feet on y = 250. Switching states is a plain image swap; nothing moves. The bird
height is set by the thinking GIF, whose bird is only 182 px tall in the source: bigger would blur it.
For a sharper large mascot, re-export the thinking animation at a higher resolution and rerun the
script.

**Notes on the source art.**
- Thinking frame 6 contained a smudge left by the fading bubble; the normalized frame has it removed
  (`mascot.json` records this). The original is untouched.
- In the source thinking GIF the bird sinks about 14 px in its last three frames; that is the original
  animation and is kept (the canvas leaves room below the feet).
- The thinking robin is drawn in a slightly different style from the official figure (wing on the
  other side, darker beak). Worth harmonising in a future art pass; the state machine does not depend
  on it.

## States

| State | Look | When |
|---|---|---|
| `idle` | Official figure; slow breathing (scale 1 → 1.012 × 1.03, 3.6 s), the eye glow pulses (2.4 s) and the star twinkles (3.1 s) | Default |
| `thinking` | Thinking frames, 350 ms each, looping | From sending a question until the answer arrives (5-90 s) |
| `speaking` | Speaking frames, 80 ms each, looping | While the answer text is revealed (typewriter, at most 4 s) |
| `found` | Figure with a one-off star flare (1.2 s), then `idle` | The answer contains real archive data (`data.spherex_available == true` or `media` not empty) |
| `quiet` | Bird without beam, calm head tilt (−5° → −2°, 1.6 s), held 2.5 s, then `idle` | `success == false`, `data.fallback.active`, `spherex_available == false`, `data.tool_errors`, or `intent == "error"` |
| attention (overlay) | Two small hops and an orange badge | An answer arrived while the panel was closed; cleared when it opens |
| hover | Lifts 4 px | Pointer over the mascot |

Glow and star overlays sit at the figure's eye (110.6, 83.5) and star (222.3, 47.8) on the shared
canvas (`mascot.json → overlay_points_px`); the CSS uses the same points as percentages. All motion is
CSS transforms and opacity on top of the art: the art itself is never redrawn. With
`prefers-reduced-motion` every animation is switched off.

```
idle --send--> thinking --response--> speaking --text shown--> found (1.2 s) --> idle
                                                          \--> quiet (2.5 s) --> idle
                                                          \--> idle
```

## Opening: the robin pulls the panel out with its beak

When closed, only a small orange **handle** of the panel shows at the screen edge, level with the
robin's beak. Clicking the robin (or the handle):

1. **Grab** (180 ms): the robin turns to face the panel, closes its beak (`quiet` art, no beam) and
   reaches forward until the beak is on the handle.
2. **Pull** (600 ms): it walks backwards, leaning back, and the panel slides out after it.
3. **Open**: the robin stands at the panel's edge facing the conversation, beak on the handle.

Closing plays it in reverse: the robin pushes the panel back to the edge, then steps back into its
corner and turns to face the screen again.

How it stays aligned: the beak tip of `normalized/quiet.png` is at (169, 85) on the 320 × 272 canvas.
The robin's position and the panel's slide share one duration and easing curve, and the reach
distance is chosen so the beak starts and ends on the handle; mixing two motions with the same easing
keeps the beak on the handle all the way. Measured in the browser with a marker at the beak tip, in
all four corners: at most ±12 px off horizontally (the handle is 22 px wide) and ±1 px vertically,
0 px at the start and end. The CSS variables are `--qf-grab-ms`, `--qf-pull-ms`, `--qf-pull-ease`,
`--qf-handle-w/h` and `--qf-beak-front/top`; the script only marks the move with `data-motion`
(`opening` / `closing`) for its length. With `prefers-reduced-motion` the panel simply appears.

The mirrored robin is flipped about its centre (`transform-origin: 50% 92%`); flipping about the feet
moved it 40 px sideways.

## Placement and panel

- Corner: `bottom-right` (default), `bottom-left`, `top-right`, `top-left`. The art faces right; in the
  right-hand corners it is mirrored so the robin looks into the screen.
- Displayed at 160 × 136 px (half the canvas), 16 px from the edges.
- Click the robin or the handle (or Enter/Space on the focused robin) to toggle the panel; Escape closes it.
- The panel comes in from the mascot's side: full height, `min(420px, 100vw − 24px)` wide, pulled by
  the robin (above). While it is closed its content is `inert` (not reachable by keyboard).
- Panel content: header with the robin icon and "Q-FIT", the message list (user messages right, answers
  left; knowledge-base fallback answers have an orange left border), collapsible "Caveats"
  (`uncertainty`) and "Sources", an "AI explanation" label on model-written text, and a textarea
  (Enter sends, Shift+Enter breaks a line, 2000 characters max).
- Text is rendered safely: everything escaped, only `**bold**` turned into bold.
- The last 10 turns are sent as `history`; the current camera view is sent as `context`.

## Accessibility

- The mascot is a `<button>` with an `aria-label` and `aria-expanded`; the panel is a labelled dialog.
- New messages are announced (`aria-live="polite"`).
- Focus moves to the input when the panel opens.
- The colours keep white text on the navy (#0b1d3a) and orange (#ff5a36) backgrounds readable.
