/**
 * App — top-level component.
 *
 * Three screens, switched by simple state (no router needed):
 *   • queue  — Mock COLA application queue (default). Click an item to
 *              review it; the form auto-populates and the label image is
 *              auto-attached. Mirrors how a real TTB agent works.
 *   • single — Manual single-label verification (upload + type-or-paste fields).
 *   • batch  — Multi-label upload via ZIP + manifest.csv.
 *
 * The queue can also auto-route to the batch screen with a pre-staged ZIP
 * URL — used by MOCK_BATCHES for the bulk-review demo path.
 */

import { useState } from "react";
import { ApplicationQueue } from "./components/ApplicationQueue";
import { BatchUpload } from "./components/BatchUpload";
import { SingleLabelForm } from "./components/SingleLabelForm";
import type { MockApplication, MockBatch } from "./data/mockApplications";

type Screen = "queue" | "single" | "batch";

export function App() {
  const [screen, setScreen] = useState<Screen>("queue");
  const [reviewing, setReviewing] = useState<MockApplication | null>(null);
  const [prefillBatchUrl, setPrefillBatchUrl] = useState<string | null>(null);

  function handleReview(app: MockApplication) {
    setReviewing(app);
    setScreen("single");
  }

  function handleReviewBatch(batch: MockBatch) {
    setPrefillBatchUrl(batch.zip_url);
    setScreen("batch");
  }

  function selectScreen(next: Screen) {
    if (next !== "single") {
      setReviewing(null);
    }
    if (next !== "batch") {
      setPrefillBatchUrl(null);
    }
    setScreen(next);
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__inner">
          <h1 className="app-header__title">TTB Label Verifier</h1>
          <p className="app-header__subtitle">
            Alcohol beverage label compliance pre-screening
          </p>
        </div>
      </header>

      <nav
        className="tab-nav"
        role="tablist"
        aria-label="Primary sections"
      >
        <button
          type="button"
          id="tab-queue"
          role="tab"
          aria-selected={screen === "queue"}
          aria-controls="panel-queue"
          tabIndex={screen === "queue" ? 0 : -1}
          className={`tab-nav__tab${screen === "queue" ? " tab-nav__tab--active" : ""}`}
          onClick={() => selectScreen("queue")}
        >
          Queue
        </button>
        <button
          type="button"
          id="tab-single"
          role="tab"
          aria-selected={screen === "single"}
          aria-controls="panel-single"
          tabIndex={screen === "single" ? 0 : -1}
          className={`tab-nav__tab${screen === "single" ? " tab-nav__tab--active" : ""}`}
          onClick={() => selectScreen("single")}
        >
          Single Label
        </button>
        <button
          type="button"
          id="tab-batch"
          role="tab"
          aria-selected={screen === "batch"}
          aria-controls="panel-batch"
          tabIndex={screen === "batch" ? 0 : -1}
          className={`tab-nav__tab${screen === "batch" ? " tab-nav__tab--active" : ""}`}
          onClick={() => selectScreen("batch")}
        >
          Batch (up to 300)
        </button>
      </nav>

      <main className="app-main">
        <div
          id="panel-queue"
          role="tabpanel"
          aria-labelledby="tab-queue"
          hidden={screen !== "queue"}
          tabIndex={-1}
        >
          {screen === "queue" && (
            <ApplicationQueue
              onReview={handleReview}
              onReviewBatch={handleReviewBatch}
            />
          )}
        </div>
        <div
          id="panel-single"
          role="tabpanel"
          aria-labelledby="tab-single"
          hidden={screen !== "single"}
          tabIndex={-1}
        >
          {screen === "single" && <SingleLabelForm prefill={reviewing} />}
        </div>
        <div
          id="panel-batch"
          role="tabpanel"
          aria-labelledby="tab-batch"
          hidden={screen !== "batch"}
          tabIndex={-1}
        >
          {screen === "batch" && (
            <BatchUpload prefillZipUrl={prefillBatchUrl} />
          )}
        </div>
      </main>

      <footer className="app-footer">
        <p>
          TTB Label Verifier — prototype only. Final approval remains with the
          assigned compliance agent.
        </p>
      </footer>
    </div>
  );
}
