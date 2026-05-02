/**
 * App — top-level component.
 * Two screens switched by simple state (no router needed per spec).
 */

import { useState } from "react";
import { BatchUpload } from "./components/BatchUpload";
import { SingleLabelForm } from "./components/SingleLabelForm";

type Screen = "single" | "batch";

export function App() {
  const [screen, setScreen] = useState<Screen>("single");

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
          className={`tab-nav__tab${screen === "single" ? " tab-nav__tab--active" : ""}`}
          onClick={() => setScreen("single")}
          aria-current={screen === "single" ? "page" : undefined}
        >
          Single Label
        </button>
        <button
          type="button"
          className={`tab-nav__tab${screen === "batch" ? " tab-nav__tab--active" : ""}`}
          onClick={() => setScreen("batch")}
          aria-current={screen === "batch" ? "page" : undefined}
        >
          Batch (up to 300)
        </button>
      </nav>

      <main className="app-main">
        {screen === "single" ? <SingleLabelForm /> : <BatchUpload />}
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
