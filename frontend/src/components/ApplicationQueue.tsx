/**
 * ApplicationQueue — Screen 0 (default).
 *
 * Simulates the COLA review queue: a table of pending applications. Agent
 * clicks "Review" on one → SingleLabelForm opens pre-populated with the
 * structured app data and the label image already attached. Mirrors how
 * an agent would work in real COLA, where applications and label artwork
 * arrive together via the system, not via manual entry.
 *
 * The queue also surfaces pre-staged *batches* (ZIP + manifest.csv) at the
 * top, so an agent can demo the bulk-review path without authoring a CSV.
 * Clicking "Review batch" switches to the Batch tab with the ZIP auto-loaded.
 */

import DOMPurify from "dompurify";
import {
  MOCK_APPLICATIONS,
  MOCK_BATCHES,
  type MockApplication,
  type MockBatch,
} from "../data/mockApplications";

interface ApplicationQueueProps {
  onReview: (app: MockApplication) => void;
  onReviewBatch: (batch: MockBatch) => void;
}

export function ApplicationQueue({
  onReview,
  onReviewBatch,
}: ApplicationQueueProps) {
  return (
    <section className="screen">
      <h2 className="screen__title">Applications awaiting review</h2>
      <p className="screen__subtitle">
        Pending COLA submissions from the queue. In production these arrive from
        TTB's COLAs Online system; for the prototype they're a fixed sample set.
        Click <strong>Review</strong> to verify a label against its application.
      </p>

      {MOCK_BATCHES.length > 0 && (
        <div className="queue-batches" aria-label="Pending batches">
          {MOCK_BATCHES.map((batch) => (
            <article key={batch.batch_id} className="queue-batch">
              <div className="queue-batch__body">
                <span className="queue-batch__pill">BATCH</span>
                <h3 className="queue-batch__title">
                  {DOMPurify.sanitize(batch.title)}
                </h3>
                <p className="queue-batch__desc">
                  {DOMPurify.sanitize(batch.description)}
                </p>
                <p className="queue-batch__meta">
                  <span>
                    <strong>{batch.item_count}</strong> applications
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>{DOMPurify.sanitize(batch.batch_id)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{DOMPurify.sanitize(batch.submitted)}</span>
                </p>
              </div>
              <div className="queue-batch__action">
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => onReviewBatch(batch)}
                  aria-label={`Review batch ${batch.batch_id}: ${batch.title}`}
                >
                  Review batch
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="queue-table-wrap">
        <table className="queue-table" aria-label="Pending applications">
          <thead>
            <tr>
              <th scope="col">COLA ID</th>
              <th scope="col">Applicant</th>
              <th scope="col">Brand</th>
              <th scope="col">ABV</th>
              <th scope="col">Net contents</th>
              <th scope="col">Submitted</th>
              <th scope="col">Notes</th>
              <th scope="col" className="queue-table__action-col">
                <span className="visually-hidden">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {MOCK_APPLICATIONS.map((app) => (
              <tr key={app.cola_id}>
                <td className="queue-table__id">
                  {DOMPurify.sanitize(app.cola_id)}
                </td>
                <td>{DOMPurify.sanitize(app.applicant)}</td>
                <td>{DOMPurify.sanitize(app.fields.brand)}</td>
                <td className="queue-table__numeric">
                  {app.fields.abv_percent.toFixed(1)} %
                </td>
                <td>{DOMPurify.sanitize(app.fields.net_contents)}</td>
                <td className="queue-table__muted">
                  {DOMPurify.sanitize(app.submitted)}
                </td>
                <td className="queue-table__muted">
                  {DOMPurify.sanitize(app.scenario_hint)}
                </td>
                <td>
                  <button
                    type="button"
                    className="btn btn--primary btn--small"
                    onClick={() => onReview(app)}
                    aria-label={`Review application ${app.cola_id}: ${app.applicant}`}
                  >
                    Review
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="queue-footnote">
        <strong>Why is this here?</strong> Real TTB agents don't type
        application data — they pull it from COLAs Online, which already has
        brand name, class/type, ABV, and net contents as structured fields.
        This queue mirrors that workflow. To verify a label that isn't in the
        queue, use the <em>Single Label</em> tab to upload manually.
      </p>
    </section>
  );
}
