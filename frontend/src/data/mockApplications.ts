/**
 * Mock COLA queue — simulates the structured application data that, in
 * production, would arrive from TTB's COLAs Online system via API.
 *
 * Each entry mirrors the real COLA application shape: a unique ID, applicant
 * info, the structured product fields (brand, class/type, ABV, net contents),
 * and a label image attachment URL. The agent picks one from the queue,
 * the form auto-populates, and verification proceeds — no typing.
 *
 * To extend this list: drop a new label PNG into `frontend/public/sample-labels/`
 * and add an entry below.
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
];
