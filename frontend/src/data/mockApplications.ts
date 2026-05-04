/**
 * Mock COLA queue — simulates the structured application data that, in
 * production, would arrive from TTB's COLAs Online system via API.
 *
 * Each entry mirrors the real COLA application shape: a unique ID, applicant
 * info, the structured product fields (brand, class/type, ABV, net contents),
 * and a label image attachment URL. The agent picks one from the queue,
 * the form auto-populates, and verification proceeds — no typing.
 *
 * Two record types live here:
 *   • MockApplication — a single application reviewed in the Single tab.
 *   • MockBatch       — a pre-staged ZIP that opens in the Batch tab so an
 *                       agent can see the bulk-review UX without authoring
 *                       a manifest.csv first. Maps to scripts/build_sample_batch_zip.py.
 *
 * To extend the single list: drop a label PNG into `frontend/public/sample-labels/`
 * and add an entry to MOCK_APPLICATIONS.
 *
 * To rebuild the batch ZIP: run `python scripts/build_sample_batch_zip.py`.
 */

import type { VerifyRequest } from "../api/types";

export interface MockApplication {
  cola_id: string;
  applicant: string;
  applicant_address: string;
  submitted: string; // human-readable relative date for demo purposes
  // The structured fields that COLA would have on file:
  fields: VerifyRequest;
  // Path (relative to site root) of the label artwork attachment:
  label_image_url: string;
  // Brief note explaining what this fixture exercises (visible in the queue):
  scenario_hint: string;
}

export interface MockBatch {
  /** Synthetic batch ID — distinct from per-application COLA IDs. */
  batch_id: string;
  /** Short label shown in the queue row, e.g. "Peak-season backlog (5 apps)". */
  title: string;
  /** Why this batch exists in the queue — one line. */
  description: string;
  /** Path (relative to site root) of the pre-built ZIP. */
  zip_url: string;
  /** Number of applications inside the manifest, for the row's metadata. */
  item_count: number;
  /** Human-readable relative submission time. */
  submitted: string;
}

export const MOCK_APPLICATIONS: MockApplication[] = [
  {
    cola_id: "TTB-2026-001234",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "2 days ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/01_happy_old_tom.png",
    scenario_hint: "Clean label — should PASS all checks",
  },
  {
    cola_id: "TTB-2026-001235",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "3 days ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      // Form claims 45 % ABV but the printed label shows 40 % — agent should catch this.
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/02_fail_abv_mismatch.png",
    scenario_hint: "ABV mismatch — label shows 40 %, application says 45 %",
  },
  {
    cola_id: "TTB-2026-001236",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "1 day ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/03_review_glare.png",
    scenario_hint: "Photo has glare — image_quality may trigger NEEDS_REVIEW",
  },
  {
    cola_id: "TTB-2026-001237",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "4 hours ago",
    fields: {
      // Form expects "Old Tom" but the bottle in the file is from "Old Man".
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/04_fail_brand_mismatch.png",
    scenario_hint: "Brand mismatch — label reads OLD MAN, application says OLD TOM",
  },
  {
    cola_id: "TTB-2026-001238",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "6 hours ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      abv_percent: 45.0,
      net_contents: "750 mL", // application claims full bottle, label shows half
    },
    label_image_url: "/sample-labels/05_fail_volume_mismatch.png",
    scenario_hint: "Volume mismatch — label says 375 mL, application says 750 mL",
  },
  {
    cola_id: "TTB-2026-001239",
    applicant: "Vineyard Heights Winery",
    applicant_address: "Sonoma County, California",
    submitted: "yesterday",
    fields: {
      brand: "VINEYARD HEIGHTS",
      class_type: "Sonoma County Chardonnay",
      abv_percent: 13.5,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/06_pass_wine_label.png",
    scenario_hint: "Wine application — different beverage shape, all fields match",
  },
  {
    cola_id: "TTB-2026-001240",
    applicant: "Westbrook Brewing Co.",
    applicant_address: "Charleston, South Carolina",
    submitted: "yesterday",
    fields: {
      brand: "WESTBROOK BREWING",
      class_type: "American IPA",
      abv_percent: 6.5,
      net_contents: "12 fl oz",
    },
    label_image_url: "/sample-labels/07_pass_beer_label.png",
    scenario_hint: "Beer application — fl-oz net contents (volume normalizer)",
  },
  {
    cola_id: "TTB-2026-001241",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "2 hours ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      // Application claims Vodka but the label is clearly Bourbon.
      class_type: "Vodka",
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/08_fail_class_type_mismatch.png",
    scenario_hint: "Class/type mismatch — application says Vodka, label is Bourbon",
  },
  {
    cola_id: "TTB-2026-001242",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "30 minutes ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/11_fail_warning_text_tampered.png",
    scenario_hint:
      "Warning text tampered — label says 'Doctor General' instead of 'Surgeon General'",
  },
  {
    cola_id: "TTB-2026-001243",
    applicant: "Old Tom Distillery, LLC",
    applicant_address: "Bardstown, Kentucky",
    submitted: "10 minutes ago",
    fields: {
      brand: "OLD TOM DISTILLERY",
      class_type: "Kentucky Straight Bourbon Whiskey",
      abv_percent: 45.0,
      net_contents: "750 mL",
    },
    label_image_url: "/sample-labels/adv_03_missing_warning.png",
    scenario_hint:
      "No federal Government Warning on the label — most consequential failure mode",
  },
];

export const MOCK_BATCHES: MockBatch[] = [
  {
    batch_id: "BATCH-2026-PEAK-01",
    title: "Peak-season backlog (5 applications)",
    description:
      "Mixed beer / wine / spirits across 5 different applicants. Demonstrates the bulk-review path — ZIP + manifest.csv with one row per application.",
    zip_url: "/sample-batches/peak-season.zip",
    item_count: 5,
    submitted: "this morning",
  },
];
