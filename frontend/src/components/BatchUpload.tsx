/**
 * BatchUpload — Screen 2.
 *
 * One source: a ZIP package containing manifest.csv plus the label images
 * referenced by each row. One row = one COLA-style application (its own
 * brand, class/type, ABV, net contents). Submits POST /verify/batch (JSON +
 * base64) and streams results via SSE (@microsoft/fetch-event-source).
 *
 * Why one source: a TTB compliance batch is N *different* applications.
 * A "shared form" mode (one set of fields applied to N images) doesn't
 * model the actual job — see STUDY_GUIDE.md and the original feedback
 * round that removed it.
 *
 * SECURITY: API-supplied text passes through DOMPurify before rendering.
 */

import DOMPurify from "dompurify";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { fileToBase64, verifyBatch } from "../api/client";
import type { BatchItemEvent, Verdict } from "../api/types";
import {
  BATCH_MANIFEST_MAX_ITEMS,
  ManifestParseError,
  parseBatchZip,
  type PreparedBatchItem,
} from "../utils/batchManifest";

const PREVIEW_CAP = 48;

interface BatchRow extends BatchItemEvent {
  fileName: string;
  /** Brand from this row's manifest entry — differs per application. */
  rowBrand: string;
}

interface BatchUploadProps {
  /**
   * If set, the component fetches this URL on mount, treats the response as
   * a ZIP File, and feeds it into the manifest-parser pipeline as if the
   * user had picked it via the file input. Used by the mock COLA queue's
   * "Review batch" action so the agent can demo the bulk-review path
   * without authoring a manifest.csv first.
   */
  prefillZipUrl?: string | null;
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

export function BatchUpload({ prefillZipUrl }: BatchUploadProps = {}) {
  const zipInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [zipFile, setZipFile] = useState<File | null>(null);
  const [preparedFromZip, setPreparedFromZip] = useState<PreparedBatchItem[]>(
    [],
  );
  const [zipParseError, setZipParseError] = useState<string | null>(null);
  const [zipParseHint, setZipParseHint] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(
    null,
  );
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const previewSourceFiles = useMemo(
    () => preparedFromZip.map((p) => p.file),
    [preparedFromZip],
  );

  const captionLabels = useMemo(
    () => preparedFromZip.map((p) => p.displayName),
    [preparedFromZip],
  );

  const filesForPreviewUi = useMemo(
    () => previewSourceFiles.slice(0, PREVIEW_CAP),
    [previewSourceFiles],
  );

  const captionsForPreview = useMemo(
    () => captionLabels.slice(0, PREVIEW_CAP),
    [captionLabels],
  );

  const previewUrls = useMemo(
    () => filesForPreviewUi.map((f) => URL.createObjectURL(f)),
    [filesForPreviewUi],
  );

  useEffect(() => {
    return () => {
      previewUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [previewUrls]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!zipFile) {
        setPreparedFromZip([]);
        setZipParseError(null);
        setZipParseHint(null);
        return;
      }
      setZipParseError(null);
      setZipParseHint(null);
      try {
        const rowsParsed = await parseBatchZip(zipFile);
        if (cancelled) return;
        setPreparedFromZip(rowsParsed);
        setZipParseHint(`${rowsParsed.length} application(s) ready from manifest.csv`);
      } catch (err) {
        if (cancelled) return;
        setPreparedFromZip([]);
        const msg =
          err instanceof ManifestParseError
            ? err.message
            : "Could not parse the ZIP package.";
        setZipParseError(msg);
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [zipFile]);

  // Auto-fetch a pre-staged ZIP when the queue's "Review batch" CTA hands one
  // in via prop. The fetched bytes are wrapped in a File so the rest of the
  // component (parse useEffect, preview strip, submit) works exactly as if
  // the user had picked the file via the input.
  useEffect(() => {
    if (!prefillZipUrl) return;

    let cancelled = false;
    async function loadPrefill(url: string) {
      try {
        const resp = await fetch(url);
        if (!resp.ok) {
          throw new Error(`Sample batch fetch failed: ${resp.status}`);
        }
        const blob = await resp.blob();
        const filename =
          url.split("/").pop()?.split("?")[0] ?? "sample-batch.zip";
        const file = new File([blob], filename, {
          type: blob.type || "application/zip",
        });
        if (cancelled) return;
        setZipFile(file);
        setRows([]);
        setProgress(null);
        setError(null);
        setDone(false);
        setExpandedIndex(null);
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(`Couldn't load the sample batch: ${msg}`);
      }
    }

    void loadPrefill(prefillZipUrl);

    return () => {
      cancelled = true;
    };
  }, [prefillZipUrl]);

  function handleZipPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setZipFile(file);
    setRows([]);
    setProgress(null);
    setError(null);
    setDone(false);
    setExpandedIndex(null);
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setRows([]);
    setProgress(null);
    setDone(false);
    setExpandedIndex(null);

    if (zipParseError) {
      setError("Fix the ZIP/manifest errors before submitting.");
      return;
    }
    if (preparedFromZip.length === 0) {
      setError("Choose a ZIP that contains manifest.csv and label images.");
      return;
    }

    let items: Array<{
      image_b64: string;
      payload: PreparedBatchItem["payload"];
      fileName: string;
      rowBrand: string;
    }>;
    try {
      items = await Promise.all(
        preparedFromZip.map(async (row) => ({
          image_b64: await fileToBase64(row.file),
          payload: row.payload,
          fileName: row.displayName,
          rowBrand: row.payload.brand,
        })),
      );
    } catch {
      setError("Failed to read label images from the package.");
      return;
    }

    setLoading(true);

    const brandByIndex = items.map((i) => i.rowBrand);

    const controller = verifyBatch(
      { items: items.map(({ image_b64, payload }) => ({ image_b64, payload })) },
      {
        onProgress({ done: doneN, total }) {
          setProgress({ done: doneN, total });
        },
        onItem(event) {
          setRows((prev) => [
            ...prev,
            {
              ...event,
              fileName: items[event.index]?.fileName ?? `Row ${event.index + 1}`,
              rowBrand: brandByIndex[event.index] ?? "",
            },
          ]);
          // Progress is driven by the server's `progress` SSE frames (which
          // arrive paired with each item). Don't increment here too — that
          // double-counts and produced "6 of 5 processed" in earlier runs.
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
      },
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
    setZipFile(null);
    setPreparedFromZip([]);
    setZipParseError(null);
    setZipParseHint(null);
    setLoading(false);
    setProgress(null);
    setRows([]);
    setExpandedIndex(null);
    setError(null);
    setDone(false);
    if (zipInputRef.current) zipInputRef.current.value = "";
  }

  function toggleExpand(index: number) {
    setExpandedIndex((prev) => (prev === index ? null : index));
  }

  const previewOverflow = previewSourceFiles.length > PREVIEW_CAP;

  return (
    <section className="screen" aria-busy={loading}>
      <h2 className="screen__title">Batch Verification</h2>
      <p className="screen__subtitle">
        Upload a ZIP containing <code className="inline-code">manifest.csv</code>{" "}
        plus the label images. One row in the manifest = one COLA-style
        application with its own brand, class/type, ABV, and net contents.
      </p>

      <form className="verify-form" onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label htmlFor="batch-zip" className="form-label">
            Application ZIP <span className="required">*</span>
          </label>
          <input
            id="batch-zip"
            ref={zipInputRef}
            type="file"
            accept=".zip,application/zip"
            onChange={handleZipPick}
            className="form-input form-input--file"
            aria-describedby="batch-zip-hint"
            required
          />
          <span id="batch-zip-hint" className="form-hint">
            Must include manifest.csv plus image paths referenced by each row —
            max {BATCH_MANIFEST_MAX_ITEMS} rows (
            <a href="#batch-zip-layout" className="form-hint-link">
              layout ↓
            </a>
            )
          </span>
          {zipFile && (
            <span className="form-hint form-hint--selected">
              {DOMPurify.sanitize(zipFile.name)}
            </span>
          )}
          {zipParseHint && (
            <div className="alert alert--info" role="status">
              {DOMPurify.sanitize(zipParseHint)}
            </div>
          )}
          {zipParseError && (
            <div className="alert alert--error" role="alert">
              {DOMPurify.sanitize(zipParseError)}
            </div>
          )}
        </div>

        {previewSourceFiles.length > 0 && (
          <div
            className="batch-preview-strip"
            role="group"
            aria-label="Thumbnail previews before verification"
          >
            <p className="batch-preview-strip__intro form-hint">
              Scroll to visually confirm thumbnails before submitting.
              {previewOverflow &&
                ` Showing first ${PREVIEW_CAP} of ${previewSourceFiles.length}.`}
            </p>
            <div className="batch-preview-strip__scroll">
              {filesForPreviewUi.map((file, i) => (
                <figure
                  key={`${file.name}-${file.lastModified}-${i}`}
                  className="batch-preview-thumb"
                >
                  <div className="batch-preview-thumb__frame">
                    <img
                      src={previewUrls[i]}
                      alt={`Preview: ${captionsForPreview[i] ?? file.name}`}
                      className="batch-preview-thumb__img"
                    />
                  </div>
                  <figcaption className="batch-preview-thumb__caption">
                    {DOMPurify.sanitize(captionsForPreview[i] ?? file.name)}
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>
        )}

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
              disabled={loading || preparedFromZip.length === 0 || !!zipParseError}
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

      <div id="batch-zip-layout" className="batch-zip-docs">
        <h3 className="batch-zip-docs__title">ZIP + manifest.csv layout</h3>
        <p className="form-hint batch-zip-docs__p">
          Put <code className="inline-code">manifest.csv</code> in the ZIP (root
          or any subfolder — the shallowest <code className="inline-code">
            manifest.csv
          </code> wins). Columns (header row required):
          <strong> image_filename</strong>, <strong>brand</strong>,{" "}
          <strong>class_type</strong>, <strong>abv_percent</strong>,{" "}
          <strong>net_contents</strong>. Optional:<strong> cola_id</strong> (stored
          as <code className="inline-code">request_id</code>). Image paths resolve
          from the ZIP root or relative to the manifest&apos;s folder. Aliases accepted
          include <code className="inline-code">image_file</code>,{" "}
          <code className="inline-code">label_image</code>.
        </p>
      </div>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      {(loading || rows.length > 0 || done) && (
        <div className="batch-results">
          {progress && (
            <div className="progress-bar-container"
              role="progressbar"
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
                    width:
                      progress.total > 0
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
                  <th scope="col">Application / file</th>
                  <th scope="col">Brand (form)</th>
                  <th scope="col">Verdict</th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isExpanded = expandedIndex === row.index;
                  const displayBrand = DOMPurify.sanitize(row.rowBrand);

                  return (
                    <React.Fragment key={row.index}>
                      <tr
                        className={`results-table__row results-table__row--${row.overall_verdict.toLowerCase()}`}
                      >
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
                          <span
                            className={verdictBadgeClass(row.overall_verdict)}
                          >
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
                                <li
                                  key={field.name}
                                  className="expanded-fields__item"
                                >
                                  <strong>{DOMPurify.sanitize(field.name)}</strong>
                                  {" — "}
                                  <span className={verdictBadgeClass(field.verdict)}>
                                    {verdictLabel(field.verdict)}
                                  </span>{" "}
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
