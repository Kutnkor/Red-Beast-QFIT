# Front end ↔ backend contract (React + Three.js)

The Q-FIT front end is a React application with a Three.js sky view. The full envelope and endpoint
reference is `API_CONTRACT.md`; this page is what a front-end developer needs.

This repository folder holds the AI side only; the 3D scene and the user interface are built by the
rest of the team. What the front end takes from here:

```
QFIT-AI/mascot/
  react/src/qfit/        <- copy this folder into the React app
    api.ts               TypeScript types for the envelope, askQFit(), raDecToDirection(),
                         fetchPreviewInfo(), apiUrl()
    QFitAssistant.tsx    robin mascot + chat panel it pulls open with its beak (docs/MASCOT_AND_CHAT_UI.md)
    qfit-assistant.css
    assets/              mascot images used by the component
  vanilla/               the same mascot + panel as plain HTML/CSS/JS (no React)
  assets/                all mascot art: originals, aligned frames, sprite sheets, icons, mascot.json
```

`mascot/react` only type-checks the component (`npm ci && npm run typecheck`); it has no app of its own.
The component needs React 18 or later and a bundler that imports `.png` and `.css` files (Vite does).

> Not done yet: the team's timeline components and anything driven by `research/data.json`. That code
> and file are not in this folder, so no field names have been guessed.

## Integrating into the team's app

```tsx
import { QFitAssistant } from "./qfit/QFitAssistant";
import type { FocusMapPayload, QFitAction } from "./qfit/api";

<QFitAssistant
  corner="bottom-right"                       // or bottom-left, top-right, top-left
  context={{ ra: view.ra, dec: view.dec, fov_deg: camera.fov }}
  onActions={(actions: QFitAction[]) => {
    for (const a of actions) {
      if (a.type === "focus_map") {
        const p = a.payload as unknown as FocusMapPayload;
        flyCameraTo(p.ra, p.dec);              // your Three.js camera move
      }
    }
  }}
/>
```

- **`context`**: always send what the 3D view shows (camera centre RA/Dec in degrees, ICRS, and field of
  view). It is how "here", "this region", "bu bölge" are understood. Unknown fields are rejected with
  `422 invalid_input`; leave out empty ones (`api.ts` does).
- **Language**: the component sends `locale` (`tr`/`en`, from the `lang` prop or the browser). The answer
  comes back in that language.
- **Coordinates → Three.js**: `raDecToDirection(ra, dec)` gives a unit vector for a camera at the origin
  looking outwards (y up, RA increasing towards −z so east is to the left as in the real sky). If the
  team's sky texture is oriented differently, change only that function. The inverse, for sending the
  camera's centre as `context`:

```ts
const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
const dec = THREE.MathUtils.radToDeg(Math.asin(dir.y));
const ra = (THREE.MathUtils.radToDeg(Math.atan2(-dir.z, dir.x)) + 360) % 360;
```

## What to do with a response

1. `success == false` → show `error.message`; offer a retry only if `error.retryable`.
2. Show `message`. If `message_source == "ai_generated"`, label it as the assistant's explanation.
3. Run `actions` in order:

| `type` | Front-end behaviour |
|---|---|
| `focus_map` | Turn the camera to `payload.ra`, `payload.dec`. If `epoch_utc` is present the target is a Solar System body: show the epoch. |
| `display_object` | Show the catalog card (`payload.object`). Catalog data only. |
| `display_observations` | List archive records (`payload.observation_ids`, full rows in `data.observations`). |
| `display_image` | Show the products; each has a `preview_url` (PNG) that can be put on the sky (see below). |
| `display_spectrum` | Show spectral products and, if present, raw pixel samples (`payload.samples`). |
| `request_clarification` | Show `payload.question` and `payload.options` as buttons; send the choice as the next message. |
| `show_error` | Show `payload.message`. |

4. Show `uncertainty` (short list) near the answer and `sources` as links.
5. Never present `object` alone as "observed by SPHEREx": only `data.spherex_available == true` says so.
6. `data.fallback.active == true`: the AI was unavailable (no key, quota, daily site budget, slow
   archive) and `message` is a quoted knowledge-base passage. Show a small notice.

## Images: PNG previews for the browser and Three.js

SPHEREx products are FITS files, which a browser `<img>` or a Three.js `TextureLoader` cannot read.
The backend converts a cutout to PNG:

| Endpoint | Returns |
|---|---|
| `GET /api/v1/images/preview?observation_id=…&ra=…&dec=…&size_deg=0.5&stretch=asinh` | `image/png` (grey + alpha; blank pixels transparent) |
| `GET /api/v1/images/preview/info?…same parameters…` | Envelope with `data.preview`: `png_url`, `width`, `height`, `stretch`, `scale_range` (MJy/sr), and `corners_radec` (ICRS position of the PNG's top-left, top-right, bottom-right, bottom-left corners) |

- Image searches already carry a ready `preview_url` per product (`data.image_products[].preview_url`,
  the `display_image` action and `media`). It is a path: prefix it with the API base (`apiUrl()` in
  `api.ts`).
- **Placing it on the sky:** SPHEREx images are not north-up, so use the four corners, not just the
  centre: a textured quad whose corners sit at `raDecToDirection(ra, dec)` on the sky sphere. Checked in
  a browser test scene with a marked test image (north up, east left, centred on the focused position)
  and with real M31 previews:

```ts
import { apiUrl, fetchPreviewInfo, raDecToDirection } from "./qfit/api";

async function showPreview(previewUrl: string, scene: THREE.Scene, radius = 850) {
  const info = await fetchPreviewInfo(previewUrl);        // png_url + corners_radec
  const c = info.corners_radec;
  const corners = [c.top_left, c.top_right, c.bottom_right, c.bottom_left];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(
    new Float32Array(corners.flatMap(([ra, dec]) => raDecToDirection(ra, dec).map(v => v * radius))), 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(new Float32Array([0, 1, 1, 1, 1, 0, 0, 0]), 2));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  const texture = await new THREE.TextureLoader().loadAsync(apiUrl(info.png_url));
  texture.colorSpace = THREE.SRGBColorSpace;
  scene.add(new THREE.Mesh(geometry, new THREE.MeshBasicMaterial(
    { map: texture, transparent: true, side: THREE.DoubleSide, depthWrite: false })));
}
```

- **Zoom:** previews are 0.1-1° wide. In a 60° field of view they are a few pixels: when showing one,
  turn the camera to it and narrow the field of view to about three times the image size.
- `stretch`: `asinh` (default), `log`, `linear`; `low_pct` / `high_pct` set the clipping percentiles
  (default 1 / 99.5). `size_deg` is at most 1.0 (a full image is about 3.5 deg and 70 MB).
- The first request downloads an IRSA cutout (20-45 s when IRSA is healthy); the PNG is then cached for
  an hour. Show the robin's thinking state or a placeholder meanwhile.
- Label the picture as a display image: one detector band, one exposure, raw surface brightness with
  zodiacal light, wavelength varying across the image, stretched for viewing. It is not a colour
  photograph and its pixel brightness is not a measurement (`data.preview.note` says so).

## Timing

Answers take 5-90 s: the model reasons and the tools query live archives (IRSA can be slow). The
backend stops a turn after `CHAT_TIMEOUT_SECONDS` (90) and answers from the knowledge base. Keep the
mascot in its thinking state for the whole wait, never a spinner that suggests a few seconds.

## CORS, HTTPS, origins

- Development: let the dev server proxy `/chat`, `/health` and `/api` to the backend (Vite: `server.proxy`)
  so the API is same-origin; nothing else to configure.
- Production: either serve the built front end and the API from the same domain behind one proxy
  (no CORS), or set `VITE_QFIT_API=https://<api host>` at build time and add the site origin (scheme +
  host + port) to the backend's `CORS_ORIGINS`.
- Allowed: methods `GET`, `POST`, `OPTIONS`; request headers `Content-Type`, `X-Request-ID`,
  `X-QFit-Token`; exposed header `X-Request-ID`. No cookies.
- A page served over `https` cannot call an `http` API (mixed content). See `DEPLOYMENT.md`.
- `X-QFit-Token` (the team token) is for the team's own review tools, never for the public page: anything
  shipped to the browser is public.
