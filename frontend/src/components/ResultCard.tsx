/**
 * ResultCard — renders one FieldResult with a verdict pill,
 * confidence percentage, and optional detail text.
 *
 * SECURITY: All text from the API (attacker-controllable via image content)
 * is sanitized with DOMPurify before rendering. JSX interpolation only.
 * No innerHTML usage anywhere in this file.
 */

import DOMPurify from "dompurify";
import type { FieldResult, Verdict } from "../api/types";

interface ResultCardProps {
  result: FieldResult;
}

const VERDICT_LABELS: Record<Verdict, string> = {
  PASS: "PASS",
  FAIL: "FAIL",
  NEEDS_REVIEW: "NEEDS REVIEW",
};

function verdictClass(verdict: Verdict): string {
  switch (verdict) {
    case "PASS":
      return "verdict-pass";
    case "FAIL":
      return "verdict-fail";
    case "NEEDS_REVIEW":
      return "verdict-review";
  }
}

function formatConfidence(confidence: number): string {
  return `${(confidence * 100).toFixed(0)}%`;
}

function sanitize(value: string): string {
  return DOMPurify.sanitize(value);
}

export function ResultCard({ result }: ResultCardProps) {
  const { name, verdict, confidence, detail } = result;

  // Sanitize API-supplied strings — field names and detail text are
  // technically attacker-controllable via label image content.
  const safeName = sanitize(name);
  const safeDetail = detail ? sanitize(detail) : null;

  return (
    <div className={`result-card ${verdictClass(verdict)}`}>
      <div className="result-card__header">
        <span className="result-card__field-name">{safeName}</span>
        <span className={`verdict-pill ${verdictClass(verdict)}`}>
          {VERDICT_LABELS[verdict]}
        </span>
      </div>
      <div className="result-card__meta">
        <span className="result-card__confidence">
          Confidence: {formatConfidence(confidence)}
        </span>
      </div>
      {safeDetail && (
        <p className="result-card__detail">{safeDetail}</p>
      )}
    </div>
  );
}
