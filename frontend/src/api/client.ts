/**
 * Typed API client for the TTB Label Verifier backend.
 * Uses VITE_API_URL when set; otherwise same-origin (Vite dev proxy or prod bundle).
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  BatchItemEvent,
  BatchProgressEvent,
  BatchRequest,
  ErrorResponse,
  VerifyRequest,
  VerifyResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

/** Single-label verification budget in milliseconds. */
export const VERIFY_TIMEOUT_MS = 30_000;

/** Show a slow-request hint after this many milliseconds (hard abort at VERIFY_TIMEOUT_MS). */
export const VERIFY_SLOW_HINT_MS = 5_000;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ErrorResponse
  ) {
    super(body.error.message);
    this.name = "ApiError";
  }
}

/** Thrown when the POST /verify request exceeds VERIFY_TIMEOUT_MS. */
export class VerifyTimeoutError extends Error {
  constructor() {
    super(
      "Verification timed out. Route this label to manual review."
    );
    this.name = "VerifyTimeoutError";
  }
}

/**
 * POST /verify — single-label verification via multipart form.
 *
 * Aborts automatically after VERIFY_TIMEOUT_MS (30 s). On timeout, throws
 * VerifyTimeoutError so the caller can show a "route to manual review" message.
 */
export async function verifySingleLabel(
  image: File,
  payload: VerifyRequest
): Promise<VerifyResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(new VerifyTimeoutError()),
    VERIFY_TIMEOUT_MS,
  );

  const form = new FormData();
  form.append("image", image);
  form.append("payload", JSON.stringify(payload));

  try {
    const response = await fetch(`${API_BASE}/verify`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });

    const data: unknown = await response.json();

    if (!response.ok) {
      throw new ApiError(response.status, data as ErrorResponse);
    }

    return data as VerifyResponse;
  } catch (err) {
    if (controller.signal.aborted) {
      throw new VerifyTimeoutError();
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * POST /verify/batch — streaming batch verification via SSE over POST.
 *
 * Uses @microsoft/fetch-event-source (supports POST + proper error handling).
 * Calls onItem for each `event: item` frame, onProgress for each `event: progress` frame.
 * Returns a cleanup function that aborts the stream.
 */
export function verifyBatch(
  request: BatchRequest,
  callbacks: {
    onProgress?: (event: BatchProgressEvent) => void;
    onItem: (event: BatchItemEvent) => void;
    onError?: (error: unknown) => void;
    onDone?: () => void;
  }
): AbortController {
  const controller = new AbortController();

  // `fetchEventSource` rejects its returned promise on TWO distinct paths:
  //   1. After the SSE stream is open: our `onerror` runs (calling onError)
  //      and re-throws to stop retries; the throw rejects the promise.
  //   2. BEFORE the stream is open: DNS failure, CORS preflight rejection,
  //      HTTP 4xx/5xx returned with no event-stream body, etc. Our `onerror`
  //      is *not* called for these — the library rejects directly.
  //
  // Without `onErrorFired`, path (2) leaves the UI stuck in `loading=true`
  // because `onError` never runs. With it, path (1) is dedup'd (we already
  // called onError inside `onerror`) and path (2) is surfaced.
  let onErrorFired = false;

  fetchEventSource(`${API_BASE}/verify/batch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    signal: controller.signal,

    onmessage(msg) {
      if (msg.event === "progress") {
        try {
          const data = JSON.parse(msg.data) as BatchProgressEvent;
          callbacks.onProgress?.(data);
        } catch {
          // Ignore malformed progress frames
        }
      } else if (msg.event === "item") {
        try {
          // Server payload is { batch_id, index, result: VerifyResponse }.
          // Flatten so callbacks see one merged BatchItemEvent and don't
          // have to reach through .result for overall_verdict / fields.
          const raw = JSON.parse(msg.data) as {
            batch_id?: string;
            index: number;
            result: VerifyResponse;
          };
          const data: BatchItemEvent = {
            ...raw.result,
            index: raw.index,
            batch_id: raw.batch_id,
          };
          callbacks.onItem(data);
        } catch {
          callbacks.onError?.(new Error(`Malformed item event: ${msg.data}`));
        }
      } else if (msg.event === "done") {
        callbacks.onDone?.();
      }
    },

    onerror(err) {
      onErrorFired = true;
      callbacks.onError?.(err);
      // Re-throw to stop retries (library treats thrown `onerror` as fatal — see fetch.js reject path).
      throw err;
    },
  }).catch((err: unknown) => {
    if (controller.signal.aborted) return;
    // Surface pre-stream rejections (DNS, CORS, HTTP error before the
    // event-stream body) — our `onerror` won't have fired for these,
    // so the UI's `loading=true` would otherwise stick forever.
    if (!onErrorFired) {
      callbacks.onError?.(err);
    }
  });

  return controller;
}

const B64_ENCODE_CHUNK = 0x8000;

/**
 * Convert a File to a raw base64 string (no data-URL prefix).
 * Uses chunked `arrayBuffer → btoa` to avoid stacking huge strings on FileReader/data-URLs for large uploads.
 */
export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += B64_ENCODE_CHUNK) {
    const slice = bytes.subarray(i, i + B64_ENCODE_CHUNK);
    binary += String.fromCharCode(...slice);
  }
  return btoa(binary);
}
