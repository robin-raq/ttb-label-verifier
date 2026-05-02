/**
 * SingleLabelForm — Screen 1.
 *
 * File input + form fields → POST /verify (multipart) → verdict banner + field results.
 *
 * SECURITY: API-supplied text (brand names, detail strings) passes through
 * DOMPurify.sanitize() before rendering. JSX interpolation only — no innerHTML.
 */

import DOMPurify from "dompurify";
import React, { useRef, useState } from "react";
import { ApiError, verifySingleLabel } from "../api/client";
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

export function SingleLabelForm() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [form, setForm] = useState<FormValues>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setResult(null);
    setError(null);
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
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <section className="screen">
      <h2 className="screen__title">Single Label Verification</h2>
      <p className="screen__subtitle">
        Upload one label image and enter the application form values to verify.
      </p>

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
            required
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
