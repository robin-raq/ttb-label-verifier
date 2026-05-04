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
      // Do not re-throw — fetchEventSource auto-retries on error unless we throw
      throw err;
    },
  }).catch((err: unknown) => {
    if (controller.signal.aborted) return; // Expected on cleanup
    callbacks.onError?.(err);
  });

  return controller;
}

/**
 * Convert a File to a base64 string (without the data URL prefix).
 */
export async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip "data:<mime>;base64," prefix
      const base64 = result.split(",")[1];
      if (!base64) {
        reject(new Error("Failed to extract base64 from FileReader result"));
        return;
      }
      resolve(base64);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
