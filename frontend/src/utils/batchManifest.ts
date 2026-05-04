/**
 * Parse a ZIP that contains manifest.csv plus label images — one row per COLA-style application.
 * Client-side only; expands to PreparedBatchItem for POST /verify/batch unchanged.
 */

import JSZip from "jszip";
import Papa from "papaparse";

import type { VerifyRequest } from "../api/types";

export const BATCH_MANIFEST_MAX_ITEMS = 300;

export type PreparedBatchItem = {
  /** Shown in results table filename column + preview caption */
  displayName: string;
  payload: VerifyRequest;
  file: File;
};

export class ManifestParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ManifestParseError";
  }
}

function pick(
  row: Record<string, string>,
  aliases: string[],
): string | undefined {
  for (const key of aliases) {
    const v = row[key];
    if (v != null && String(v).trim() !== "") {
      return String(v).trim();
    }
  }
  return undefined;
}

function normalizeZipPath(p: string): string {
  return p.replace(/\\/g, "/").replace(/^\.\/+/, "").replace(/^\/+/, "");
}

/** Prefer manifest.csv at shallowest depth in the archive. */
function findManifest(zip: JSZip): { obj: JSZip.JSZipObject; path: string } | null {
  let best: { depth: number; obj: JSZip.JSZipObject; path: string } | null =
    null;

  zip.forEach((path, obj) => {
    if (obj.dir) return;
    const leaf = path.split("/").pop();
    if (leaf?.toLowerCase() !== "manifest.csv") return;
    const depth = path.split("/").length - 1;
    if (!best || depth < best.depth) {
      best = { depth, obj, path };
    }
  });

  return best;
}

function resolveImageEntry(
  zip: JSZip,
  manifestCsvPath: string,
  rawImageRef: string,
  rowIndex: number,
): JSZip.JSZipObject | null {
  const ref = normalizeZipPath(rawImageRef);
  if (!ref) {
    return null;
  }

  const direct = zip.file(ref);
  if (direct && !direct.dir) {
    return direct;
  }

  // Relative to manifest's directory (e.g. manifest in subfolder/)
  const dir = manifestCsvPath.includes("/")
    ? manifestCsvPath.replace(/[^/]+$/, "")
    : "";
  if (dir) {
    const combined = normalizeZipPath(`${dir}${ref}`);
    const nested = zip.file(combined);
    if (nested && !nested.dir) {
      return nested;
    }
  }

  const base = ref.split("/").pop()!;
  const matches: string[] = [];
  zip.forEach((path, obj) => {
    if (obj.dir) return;
    if (path.endsWith(ref) || path.split("/").pop() === base) {
      matches.push(path);
    }
  });

  if (matches.length === 1) {
    return zip.file(matches[0]) ?? null;
  }

  if (matches.length > 1) {
    throw new ManifestParseError(
      `Row ${rowIndex}: image "${rawImageRef}" is ambiguous (${matches.length} entries share that name pattern).`,
    );
  }

  return null;
}

export async function parseBatchZip(
  zipFile: File,
): Promise<PreparedBatchItem[]> {
  const zip = await JSZip.loadAsync(zipFile);

  const found = findManifest(zip);
  if (!found) {
    throw new ManifestParseError(
      "ZIP must contain a manifest.csv file (any subfolder allowed).",
    );
  }

  const { obj: manifestObj, path: manifestPath } = found;

  const text = await manifestObj.async("string");
  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: (h) =>
      h
        .replace(/^\ufeff/, "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_"),
  });

  if (parsed.errors.length > 0) {
    const fatal = parsed.errors.find((e) => e.type === "Quotes" || e.row != null);
    if (fatal) {
      throw new ManifestParseError(
        `CSV parse error: ${fatal.message} (row ${fatal.row ?? "?"})`,
      );
    }
  }

  const items: PreparedBatchItem[] = [];
  let rowIndex = 0;

  for (const row of parsed.data) {
    rowIndex += 1;
    if (!row || Object.keys(row).length === 0) continue;

    const imageRef = pick(row, [
      "image_filename",
      "image_file",
      "label_image",
      "label_filename",
    ]);
    if (!imageRef) {
      throw new ManifestParseError(
        `Row ${rowIndex}: missing image column (use image_filename).`,
      );
    }

    const brand = pick(row, ["brand", "brand_name"]);
    const classType = pick(row, ["class_type", "class", "class_type_designation"]);
    const abvRaw = pick(row, ["abv_percent", "abv", "alcohol_content"]);
    const netContents = pick(row, ["net_contents", "net_content", "volume"]);

    if (!brand || !classType || !abvRaw || !netContents) {
      throw new ManifestParseError(
        `Row ${rowIndex}: need brand, class_type, abv_percent, net_contents (and image_filename).`,
      );
    }

    const abv = parseFloat(abvRaw);
    if (Number.isNaN(abv)) {
      throw new ManifestParseError(
        `Row ${rowIndex}: abv_percent "${abvRaw}" is not a number.`,
      );
    }

    const imageEntry = resolveImageEntry(zip, manifestPath, imageRef, rowIndex);
    if (!imageEntry || imageEntry.dir) {
      throw new ManifestParseError(
        `Row ${rowIndex}: image not found in ZIP: "${imageRef}"`,
      );
    }

    const blob = await imageEntry.async("blob");
    const leafName = imageRef.split("/").pop() || `row-${rowIndex}`;
    const file = new File([blob], leafName, {
      type: blob.type || "application/octet-stream",
    });

    const colaId = pick(row, ["cola_id", "application_id", "request_id"]);
    const payload: VerifyRequest = {
      brand,
      class_type: classType,
      abv_percent: abv,
      net_contents: netContents,
      ...(colaId ? { request_id: colaId } : {}),
    };

    const displayName = colaId
      ? `${colaId} · ${leafName}`
      : leafName;

    items.push({ displayName, payload, file });
  }

  if (items.length === 0) {
    throw new ManifestParseError("manifest.csv has no data rows.");
  }

  if (items.length > BATCH_MANIFEST_MAX_ITEMS) {
    throw new ManifestParseError(
      `Batch exceeds ${BATCH_MANIFEST_MAX_ITEMS} applications (${items.length} rows).`,
    );
  }

  return items;
}
