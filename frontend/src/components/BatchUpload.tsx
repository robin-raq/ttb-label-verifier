/**
 * BatchUpload — Screen 2.
 *
 * Allows uploading up to 300 label images plus shared form values.
 * Submits POST /verify/batch (JSON body with base64 images) and streams
 * results via SSE using @microsoft/fetch-event-source.
 *
 * SECURITY: All API-supplied text passes through DOMPurify.sanitize()
 * before rendering. JSX interpolation only — no innerHTML.
 */

import DOMPurify from "dompurify";
import React, { useRef, useState } from "react";
import { fileToBase64, verifyBatch } from "../api/client";
import type {
  BatchItemEvent,
  Verdict,
  VerifyRequest,
} from "../api/types";

const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp";
const MAX_BATCH_SIZE = 300;

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

interface BatchRow extends BatchItemEvent {
  fileName: string;
}

function verdictBadgeClass(verdict: Verdict): string {
  switch (verdict) {
    case "PASS":
      return "verdict-pill verdict-pass";
    case "FAIL":
      return "verdict-pill verdict-fail";
    case "NEEDS_REVIEW":
      return "verdict-pill verdict-review";
  }
}

function verdictLabel(verdict: Verdict): string {
  switch (verdict) {
    case "PASS":
      return "PASS";
    case "FAIL":
      return "FAIL";
    case "NEEDS_REVIEW":
      return "NEEDS REVIEW";
  }
}

export function BatchUpload() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [form, setForm] = useState<FormValues>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function handleFilesChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const capped = files.slice(0, MAX_BATCH_SIZE);
    setSelectedFiles(capped);
    setRows([]);
    setProgress(null);
    setError(null);
    setDone(false);
    setExpandedIndex(null);
  }

  function handleFieldChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setRows([]);
    setProgress(null);
    setDone(false);
    setExpandedIndex(null);

    if (selectedFiles.length === 0) {
      setError("Please select at least one label image.");
      return;
    }

    const abv = parseFloat(form.abv_percent);
    if (isNaN(abv)) {
      setError("ABV must be a valid number.");
      return;
    }

    const sharedPayload: VerifyRequest = {
      brand: form.brand.trim(),
      class_type: form.class_type.trim(),
      abv_percent: abv,
      net_contents: form.net_contents.trim(),
    };

    setLoading(true);

    // Convert all files to base64 before sending
    let items: Array<{ image_b64: string; payload: VerifyRequest; fileName: string }>;
    try {
      items = await Promise.all(
        selectedFiles.map(async (file) => ({
          image_b64: await fileToBase64(file),
          payload: { ...sharedPayload },
          fileName: file.name,
        }))
      );
    } catch {
      setError("Failed to read one or more image files.");
      setLoading(false);
      return;
    }

    const fileNames = items.map((i) => i.fileName);

    const controller = verifyBatch(
      { items: items.map(({ image_b64, payload }) => ({ image_b64, payload })) },
      {
        onProgress({ done, total }) {
          setProgress({ done, total });
        },
        onItem(event) {
          setRows((prev) => [
            ...prev,
            { ...event, fileName: fileNames[event.index] ?? `Image ${event.index + 1}` },
          ]);
          // Optimistic progress if backend doesn't send progress events
          setProgress((prev) => ({
            done: (prev?.done ?? 0) + 1,
            total: prev?.total ?? items.length,
          }));
        },
        onError(err) {
          const msg = err instanceof Error ? err.message : "Stream error";
          setError(`Batch stream error: ${DOMPurify.sanitize(msg)}`);
          setLoading(false);
        },
        onDone() {
          setDone(true);
          setLoading(false);
        },
      }
    );

    abortRef.current = controller;
  }

  function handleAbort() {
    abortRef.current?.abort();
    setLoading(false);
    setError("Batch cancelled.");
  }

  function handleReset() {
    abortRef.current?.abort();
    setSelectedFiles([]);
    setForm(EMPTY_FORM);
    setLoading(false);
    setProgress(null);
    setRows([]);
    setExpandedIndex(null);
    setError(null);
    setDone(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function toggleExpand(index: number) {
    setExpandedIndex((prev) => (prev === index ? null : index));
  }

  return (
    <section className="screen">
      <h2 className="screen__title">Batch Verification</h2>
      <p className="screen__subtitle">
        Upload up to {MAX_BATCH_SIZE} label images. The form values below will be applied
        to all images. Results stream in as each label is processed.
      </p>

      <form className="verify-form" onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label htmlFor="batch-images" className="form-label">
            Label images <span className="required">*</span>
          </label>
          <input
            id="batch-images"
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            onChange={handleFilesChange}
            className="form-input form-input--file"
            aria-describedby="batch-images-hint"
            required
          />
          <span id="batch-images-hint" className="form-hint">
            JPEG, PNG, or WebP — up to {MAX_BATCH_SIZE} files, max 10 MB each
          </span>
          {selectedFiles.length > 0 && (
            <span className="form-hint form-hint--selected">
              {selectedFiles.length} file{selectedFiles.length !== 1 ? "s" : ""} selected
              {selectedFiles.length === MAX_BATCH_SIZE && " (limit reached)"}
            </span>
          )}
        </div>

        <fieldset className="form-fieldset">
          <legend className="form-legend">Apply these form values to all images</legend>

          <div className="form-group">
            <label htmlFor="batch-brand" className="form-label">
              Brand name <span className="required">*</span>
            </label>
            <input
              id="batch-brand"
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
            <label htmlFor="batch-class_type" className="form-label">
              Class / type <span className="required">*</span>
            </label>
            <input
              id="batch-class_type"
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
            <label htmlFor="batch-abv_percent" className="form-label">
              ABV (%) <span className="required">*</span>
            </label>
            <input
              id="batch-abv_percent"
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
            <label htmlFor="batch-net_contents" className="form-label">
              Net contents <span className="required">*</span>
            </label>
            <input
              id="batch-net_contents"
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
          {loading ? (
            <button
              type="button"
              className="btn btn--danger"
              onClick={handleAbort}
            >
              Cancel Batch
            </button>
          ) : (
            <button
              type="submit"
              className="btn btn--primary"
              disabled={loading}
            >
              Start Batch Verification
            </button>
          )}
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

      {(loading || rows.length > 0 || done) && (
        <div className="batch-results">
          {progress && (
            <div className="progress-bar-container" role="progressbar"
              aria-valuenow={progress.done}
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-label="Batch progress">
              <div className="progress-bar__label">
                {progress.done} of {progress.total} processed
                {done && " — Complete"}
              </div>
              <div className="progress-bar__track">
                <div
                  className="progress-bar__fill"
                  style={{
                    width: progress.total > 0
                      ? `${(progress.done / progress.total) * 100}%`
                      : "0%",
                  }}
                />
              </div>
            </div>
          )}

          {rows.length > 0 && (
            <table className="results-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">File</th>
                  <th scope="col">Brand</th>
                  <th scope="col">Verdict</th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isExpanded = expandedIndex === row.index;
                  // Sanitize API-supplied brand name from field results
                  const brandField = row.fields.find((f) => f.name === "brand");
                  const displayBrand = brandField
                    ? DOMPurify.sanitize(form.brand)
                    : DOMPurify.sanitize(form.brand);

                  return (
                    <React.Fragment key={row.index}>
                      <tr className={`results-table__row results-table__row--${row.overall_verdict.toLowerCase()}`}>
                        <td className="results-table__cell results-table__cell--index">
                          {row.index + 1}
                        </td>
                        <td className="results-table__cell">
                          {DOMPurify.sanitize(row.fileName)}
                        </td>
                        <td className="results-table__cell">
                          {displayBrand}
                        </td>
                        <td className="results-table__cell">
                          <span className={verdictBadgeClass(row.overall_verdict)}>
                            {verdictLabel(row.overall_verdict)}
                          </span>
                        </td>
                        <td className="results-table__cell">
                          <button
                            type="button"
                            className="btn btn--small btn--outline"
                            onClick={() => toggleExpand(row.index)}
                            aria-expanded={isExpanded}
                          >
                            {isExpanded ? "Hide" : "Expand"}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="results-table__row results-table__row--expanded">
                          <td colSpan={5}>
                            <ul className="expanded-fields">
                              {row.fields.map((field) => (
                                <li key={field.name} className="expanded-fields__item">
                                  <strong>{DOMPurify.sanitize(field.name)}</strong>
                                  {" — "}
                                  <span className={verdictBadgeClass(field.verdict)}>
                                    {verdictLabel(field.verdict)}
                                  </span>
                                  {" "}
                                  <span className="expanded-fields__confidence">
                                    ({(field.confidence * 100).toFixed(0)}%)
                                  </span>
                                  {field.detail && (
                                    <span className="expanded-fields__detail">
                                      {" — "}{DOMPurify.sanitize(field.detail)}
                                    </span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          )}

          {loading && rows.length === 0 && (
            <p className="batch-results__waiting">Waiting for results…</p>
          )}
        </div>
      )}
    </section>
  );
}
