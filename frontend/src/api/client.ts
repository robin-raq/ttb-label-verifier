/**
 * Typed API client for the TTB Label Verifier backend.
 * Uses VITE_API_URL env var; falls back to localhost:8000 for local dev.
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

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ErrorResponse
  ) {
    super(body.error.message);
    this.name = "ApiError";
  }
}

/**
 * POST /verify — single-label verification via multipart form.
 */
export async function verifySingleLabel(
  image: File,
  payload: VerifyRequest
): Promise<VerifyResponse> {
  const form = new FormData();
  form.append("image", image);
  form.append("payload", JSON.stringify(payload));

  const response = await fetch(`${API_BASE}/verify`, {
    method: "POST",
    body: form,
  });

  const data: unknown = await response.json();

  if (!response.ok) {
    throw new ApiError(response.status, data as ErrorResponse);
  }

  return data as VerifyResponse;
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
      callbacks.onError?.(err);
      // Re-throw to stop retries (library treats thrown `onerror` as fatal — see fetch.js reject path).
      throw err;
    },
  }).catch(() => {
    if (controller.signal.aborted) return;
    // Fatal errors surfaced in `onerror` above; this handler only absorbs the stray rejection.
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
