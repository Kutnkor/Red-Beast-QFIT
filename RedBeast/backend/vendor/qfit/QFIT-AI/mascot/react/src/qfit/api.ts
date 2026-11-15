/* Q-FIT backend client and types. The envelope is documented in docs/API_CONTRACT.md;
   every endpoint, success or failure, returns QFitResponse. */

export type ActionType =
  | "focus_map" | "display_object" | "display_observations" | "display_spectrum"
  | "display_image" | "show_error" | "request_clarification";

export interface QFitAction {
  type: ActionType;
  payload: Record<string, unknown>;
}

export interface FocusMapPayload {
  ra: number;                 // degrees, ICRS
  dec: number;                // degrees, ICRS
  frame: string;              // "ICRS"
  epoch_utc?: string;         // Solar System bodies: position valid only at this time
  radius_deg?: number;
  fov_deg?: number;
}

export interface Evidence {
  kind: "catalog_data" | "archive_metadata" | "direct_measurement" | "knowledge_base"
      | "candidate_record" | "missing_information" | string;
  statement: string;
  status: string;
  source_names: string[];
  source_urls: string[];
}

export interface MediaItem {
  media_type: "fits_cutout" | "fits_cube" | string;
  url: string;                // FITS file: not an image a browser can show directly
  full_file_url: string;
  observation_id: string;
  detector: number | null;
  time_utc: string | null;
  collection: string | null;
  source: string;
  verified: boolean | null;
}

export interface QFitResponse {
  success: boolean;
  assistant: "Q-FIT";
  intent: string;
  message: string;
  message_source: "system" | "ai_generated";
  object: Record<string, unknown> | null;
  data: {
    spherex_available: boolean | null;
    observations: Record<string, unknown>[];
    spectral_products: Record<string, unknown>[];
    image_products: Record<string, unknown>[];
    fallback?: { active: boolean; reason_code: string; reason: string; retryable: boolean };
    tool_errors?: { tool: string; code?: string; message?: string }[];
    grounding?: { checked: boolean; unsupported_numbers: string[] };
    [key: string]: unknown;
  };
  actions: QFitAction[];
  sources: { name?: string; url?: string; [key: string]: unknown }[];
  language: "tr" | "en" | null;
  evidence: Evidence[];
  uncertainty: string[];
  media: MediaItem[];
  error: { code: string; message: string; retryable: boolean; details: Record<string, unknown> } | null;
  meta: { request_id: string; timestamp: string; api_version: string; tools_called: string[];
          ai_model: string | null; versions: Record<string, string | null> };
}

export interface ChatTurn { role: "user" | "assistant"; content: string }

/** What the 3D view currently shows, so "here" / "bu bölge" can be understood. */
export interface ChatContext {
  ra?: number;
  dec?: number;
  fov_deg?: number;
  selected_object?: string;
  selected_observation_id?: string;
  locale?: "tr" | "en";
  expertise_level?: "beginner" | "intermediate" | "advanced" | "research";
}

/** Backend base URL: VITE_QFIT_API in production, same origin (Vite proxy) in development. */
export const QFIT_API: string = (import.meta.env.VITE_QFIT_API as string | undefined)?.replace(/\/$/, "") ?? "";

export async function askQFit(message: string, history: ChatTurn[], context: ChatContext,
                              signal?: AbortSignal): Promise<QFitResponse> {
  const res = await fetch(`${QFIT_API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Drop empty context fields: the backend rejects unknown fields, accepts missing ones.
    body: JSON.stringify({ message, history: history.slice(-10), context: compact(context) }),
    signal,
  });
  return (await res.json()) as QFitResponse;   // errors also come back as the envelope
}

function compact<T extends object>(value: T): Partial<T> {
  return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== undefined && v !== null && v !== "")) as Partial<T>;
}

/** Unit vector for a sky position, for a camera at the origin looking outwards.
    Convention (y up): RA = 0, Dec = 0 is +x; Dec = +90 is +y; RA increases towards -z, which seen
    from inside the sphere runs right-to-left, east to the left, like the real sky.
    If your sky texture is mapped differently, change only this function. */
export function raDecToDirection(raDeg: number, decDeg: number): [number, number, number] {
  const ra = (raDeg * Math.PI) / 180;
  const dec = (decDeg * Math.PI) / 180;
  return [Math.cos(dec) * Math.cos(ra), Math.sin(dec), -Math.cos(dec) * Math.sin(ra)];
}

/** Sky position of a PNG preview's corners (ICRS degrees, [ra, dec]). */
export interface PreviewCorners {
  top_left: [number, number]; top_right: [number, number];
  bottom_right: [number, number]; bottom_left: [number, number]; frame: string;
}

export interface PreviewInfo {
  png_url: string; width: number; height: number; stretch: string; observation_id: string;
  detector: number | null; time_utc: string | null; corners_radec: PreviewCorners;
  scale_range: { low: number; high: number; unit: string; percentiles: [number, number] };
  note: string;
}

/** Absolute URL for a path returned by the API (preview_url, png_url). */
export const apiUrl = (path: string): string => (path.startsWith("http") ? path : `${QFIT_API}${path}`);

/** Metadata (corners, stretch) for a preview_url from an image search. The first call downloads an
    IRSA cutout and can take 20-45 s; afterwards the backend caches it for an hour. */
export async function fetchPreviewInfo(previewUrl: string, signal?: AbortSignal): Promise<PreviewInfo> {
  const res = await fetch(apiUrl(previewUrl.replace("/images/preview?", "/images/preview/info?")), { signal });
  const body = (await res.json()) as QFitResponse;
  if (!body.success) throw new Error(body.error?.message ?? "preview failed");
  return body.data.preview as PreviewInfo;
}
