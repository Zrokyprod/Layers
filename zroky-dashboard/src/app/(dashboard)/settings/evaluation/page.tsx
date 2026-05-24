import Link from "next/link";

export default function EvaluationSettingsPage() {
  return (
    <div className="grid gap-4">
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Evaluation controls</h3>
            <p>Calibration and judge workspaces are secondary settings surfaces, not primary navigation.</p>
          </div>
        </header>
        <div className="grid gap-3 md:grid-cols-2">
          <Link href="/calibration" className="panel panel-muted" style={{ textDecoration: "none" }}>
            <div className="panel-header">
              <div>
                <h3>Calibration</h3>
                <p>Golden sets, judge accuracy, calibration runs, and score overview.</p>
              </div>
            </div>
          </Link>
          <Link href="/judge" className="panel panel-muted" style={{ textDecoration: "none" }}>
            <div className="panel-header">
              <div>
                <h3>Judge diagnostics</h3>
                <p>Inspect judge health and evaluation diagnostics when tuning quality gates.</p>
              </div>
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}
