/**
 * SingleLabelForm — Screen 1.
 *
 * Two ways to populate it:
 *   1. Manually — agent types in the fields and chooses a file.
 *   2. From the application queue — `prefill` prop seeds the form values
 *      and pre-attaches the label image (fetched from a URL relative to
 *      the site root, e.g. /sample-labels/01_happy_old_tom.png).
 *
 * Either way, submission goes through the same POST /verify multipart
 * call. The backend doesn't know or care how the values were sourced.
 *
 * SECURITY: API-supplied text (brand names, detail strings) passes through
 * DOMPurify.sanitize() before rendering. JSX interpolation only — no innerHTML.
 */

import DOMPurify from "dompurify";
import React, { useEffect, useRef, useState } from "react";
import { ApiError, verifySingleLabel } from "../api/client";
import type { MockApplication } from "../data/mockApplications";
import type { VerifyRequest, VerifyResponse, Verdict } from "../api/types";
import { ResultCard } from "./ResultCard";

const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp";

function verdictBannerClass(verdict: Verdict): string {
  switch (verdict) {
    case "PASS":
      return "banner banner--pass";
    case "FAIL":
      return "banner banner--fail";
    case "NEEDS_REVIEW":
      return "banner banner--review";
  }
}

function verdictLabel(verdict: Verdict): string {
  switch (verdict) {
    case "PASS":
      return "PASS — Label looks good";
    case "FAIL":
      return "FAIL — One or more fields did not pass";
    case "NEEDS_REVIEW":
      return "NEEDS REVIEW — Manual inspection required";
  }
}

interface FormValues {
  brand: string;
  class_type: string;
  abv_percent: string;
  net_contents: string;
}

const EMPTY_FORM: FormValues = {
  brand: "",
  class_type: "",
  abv_percent: "",
  net_contents: "",
};

interface SingleLabelFormProps {
  /** Optional pre-population from the application queue. */
  prefill?: MockApplication | null;
}

export function SingleLabelForm({ prefill }: SingleLabelFormProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [form, setForm] = useState<FormValues>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prefilledFromQueue, setPrefilledFromQueue] = useState(false);

  // When a queue application is passed in, seed form values and fetch the
  // attached label image into a File object so submission still works the
  // same way (multipart upload).
  useEffect(() => {
    let cancelled = false;
    if (!prefill) {
      return;
    }
    setForm({
      brand: prefill.fields.brand,
      class_type: prefill.fields.class_type,
      abv_percent: prefill.fields.abv_percent.toString(),
      net_contents: prefill.fields.net_contents,
    });
    setResult(null);
    setError(null);
    setPrefilledFromQueue(true);

    (async () => {
      try {
        const response = await fetch(prefill.label_image_url);
        if (!response.ok) {
          throw new Error(`Failed to load attached label (${response.status})`);
        }
        const blob = await response.blob();
        const filename = prefill.label_image_url.split("/").pop() ?? "label.png";
        const file = new File([blob], filename, { type: blob.type || "image/png" });
        if (!cancelled) {
          setSelectedFile(file);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            `Couldn't load the attached label image: ${
              err instanceof Error ? err.message : "unknown error"
            }`,
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [prefill]);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setResult(null);
    setError(null);
    setPrefilledFromQueue(false);
  }

  function handleFieldChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (!selectedFile) {
      setError("Please select a label image (JPEG, PNG, or WebP).");
      return;
    }

    const abv = parseFloat(form.abv_percent);
    if (isNaN(abv)) {
      setError("ABV must be a valid number.");
      return;
    }

    const payload: VerifyRequest = {
      brand: form.brand.trim(),
      class_type: form.class_type.trim(),
      abv_percent: abv,
      net_contents: form.net_contents.trim(),
    };

    setLoading(true);
    try {
      const response = await verifySingleLabel(selectedFile, payload);
      setResult(response);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Error ${err.status}: ${DOMPurify.sanitize(err.message)}`);
      } else {
        setError("Unexpected error. Check that the backend is running.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setForm(EMPTY_FORM);
    setSelectedFile(null);
    setResult(null);
    setError(null);
    setPrefilledFromQueue(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <section className="screen">
      <h2 className="screen__title">Single Label Verification</h2>
      <p className="screen__subtitle">
        {prefilledFromQueue
          ? "Application data and label image were loaded from the queue. Review and submit to verify."
          : "Application data (in production this comes from COLAs Online) and the label artwork. Submit to verify the label matches the application."}
      </p>

      {prefilledFromQueue && prefill && (
        <div className="prefill-banner" role="status">
          Loaded from COLA queue: <strong>{DOMPurify.sanitize(prefill.cola_id)}</strong>{" "}
          — {DOMPurify.sanitize(prefill.applicant)}
        </div>
      )}

      <form className="verify-form" onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label htmlFor="single-image" className="form-label">
            Label image <span className="required">*</span>
          </label>
          <input
            id="single-image"
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileChange}
            className="form-input form-input--file"
            aria-describedby="single-image-hint"
            required={!prefilledFromQueue}
          />
          <span id="single-image-hint" className="form-hint">
            JPEG, PNG, or WebP — max 10 MB
          </span>
          {selectedFile && (
            <span className="form-hint form-hint--selected">
              Selected: {DOMPurify.sanitize(selectedFile.name)}
            </span>
          )}
        </div>

        <fieldset className="form-fieldset">
          <legend className="form-fieldset__legend">
            Application data
            <span className="form-fieldset__legend-aux">
              {prefilledFromQueue ? "from COLA queue" : "from COLA / manual entry"}
            </span>
          </legend>

          <div className="form-group">
            <label htmlFor="brand" className="form-label">
              Brand name <span className="required">*</span>
            </label>
            <input
              id="brand"
              name="brand"
              type="text"
              value={form.brand}
              onChange={handleFieldChange}
              className="form-input"
              placeholder="e.g. Old Tom Distillery"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="class_type" className="form-label">
              Class / type <span className="required">*</span>
            </label>
            <input
              id="class_type"
              name="class_type"
              type="text"
              value={form.class_type}
              onChange={handleFieldChange}
              className="form-input"
              placeholder="e.g. Kentucky Straight Bourbon Whiskey"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="abv_percent" className="form-label">
              ABV (%) <span className="required">*</span>
            </label>
            <input
              id="abv_percent"
              name="abv_percent"
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={form.abv_percent}
              onChange={handleFieldChange}
              className="form-input form-input--narrow"
              placeholder="e.g. 45.0"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="net_contents" className="form-label">
              Net contents <span className="required">*</span>
            </label>
            <input
              id="net_contents"
              name="net_contents"
              type="text"
              value={form.net_contents}
              onChange={handleFieldChange}
              className="form-input"
              placeholder="e.g. 750 mL"
              required
            />
          </div>
        </fieldset>

        <div className="form-actions">
          <button
            type="submit"
            className="btn btn--primary"
            disabled={loading}
          >
            {loading ? "Verifying…" : "Verify Label"}
          </button>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={handleReset}
            disabled={loading}
          >
            Reset
          </button>
        </div>
      </form>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      {result && (
        <div className="results">
          <div className={verdictBannerClass(result.overall_verdict)} role="status">
            <strong>{verdictLabel(result.overall_verdict)}</strong>
            <span className="banner__meta">
              Request ID: {result.request_id} &middot; Total:{" "}
              {result.latency_ms.total} ms
            </span>
          </div>

          <h3 className="results__heading">Field Results</h3>
          <ul className="results__list">
            {result.fields.map((field) => (
              <li key={field.name}>
                <ResultCard result={field} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
