/**
 * App — top-level component.
 *
 * Three screens, switched by simple state (no router needed):
 *   • queue  — Mock COLA application queue (default). Click an item to
 *              review it; the form auto-populates and the label image is
 *              auto-attached. Mirrors how a real TTB agent works.
 *   • single — Manual single-label verification (upload + type-or-paste fields).
 *   • batch  — Multi-label upload.
 */

import { useState } from "react";
import { ApplicationQueue } from "./components/ApplicationQueue";
import { BatchUpload } from "./components/BatchUpload";
import { SingleLabelForm } from "./components/SingleLabelForm";
import type { MockApplication } from "./data/mockApplications";

type Screen = "queue" | "single" | "batch";

export function App() {
  const [screen, setScreen] = useState<Screen>("queue");
  const [reviewing, setReviewing] = useState<MockApplication | null>(null);

  function handleReview(app: MockApplication) {
    setReviewing(app);
    setScreen("single");
  }

  function selectScreen(next: Screen) {
    if (next !== "single") {
      setReviewing(null);
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

      <nav className="tab-nav" role="navigation" aria-label="Screens">
        <button
          type="button"
          className={`tab-nav__tab${screen === "queue" ? " tab-nav__tab--active" : ""}`}
          onClick={() => selectScreen("queue")}
          aria-current={screen === "queue" ? "page" : undefined}
        >
          Queue
        </button>
        <button
          type="button"
          className={`tab-nav__tab${screen === "single" ? " tab-nav__tab--active" : ""}`}
          onClick={() => selectScreen("single")}
          aria-current={screen === "single" ? "page" : undefined}
        >
          Single Label
        </button>
        <button
          type="button"
          className={`tab-nav__tab${screen === "batch" ? " tab-nav__tab--active" : ""}`}
          onClick={() => selectScreen("batch")}
          aria-current={screen === "batch" ? "page" : undefined}
        >
          Batch (up to 300)
        </button>
      </nav>

      <main className="app-main">
        {screen === "queue" && <ApplicationQueue onReview={handleReview} />}
        {screen === "single" && <SingleLabelForm prefill={reviewing} />}
        {screen === "batch" && <BatchUpload />}
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
