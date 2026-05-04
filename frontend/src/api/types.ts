/**
 * TypeScript types mirroring backend Pydantic models (SPEC §3.1, §4).
 * Keep in sync with app/schemas/ on the Python side.
 */

export type Verdict = "PASS" | "FAIL" | "NEEDS_REVIEW";

export interface VerifyRequest {
  brand: string;
  class_type: string;
  abv_percent: number;
  net_contents: string;
  request_id?: string;
}

export interface FieldResult {
  name: string;
  verdict: Verdict;
  confidence: number;
  detail?: string;
}

export interface LatencyMs {
  vision: number;
  compare: number;
  total: number;
}

export interface VerifyResponse {
  request_id: string;
  overall_verdict: Verdict;
  fields: FieldResult[];
  latency_ms: LatencyMs;
}

export type ErrorCode =
  | "INVALID_IMAGE_TYPE"
  | "FILE_TOO_LARGE"
  | "VALIDATION_ERROR"
  | "EXTRACTION_FAILED";

export interface ErrorResponse {
  error: {
    code: ErrorCode;
    message: string;
  };
}

/** One item sent in the batch request body (SPEC §3.2) */
export interface BatchItem {
  image_b64: string;
  payload: VerifyRequest;
}

export interface BatchRequest {
  items: BatchItem[];
}

/** SSE event: item data shape (flattened by the client). */
export interface BatchItemEvent extends VerifyResponse {
  index: number;
  /** Echoed by the server on every batch SSE frame so multi-item flows can
   * be correlated in the audit log. Optional because tests / older fixtures
   * may not include it. */
  batch_id?: string;
}

/** SSE event: progress data shape */
export interface BatchProgressEvent {
  done: number;
  total: number;
  batch_id?: string;
}
