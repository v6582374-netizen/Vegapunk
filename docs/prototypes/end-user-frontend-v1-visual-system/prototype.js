// Selected reference for a completed Discovery Launch result.

const app = document.querySelector("#app");

function VariantA() {
  return `
    <div class="variant variant-a">
      <aside class="a-sidebar">
        <a class="brand" href="#" aria-label="Vegapunk home">
          <span class="brand-mark" aria-hidden="true">V</span>
          <span>Vegapunk</span>
        </a>

        <nav class="workflow-nav" aria-label="Product areas">
          <p class="nav-label">Workspace</p>
          <a href="#"><span aria-hidden="true">DR</span>Deep Research</a>
          <a class="active" href="#" aria-current="page"><span aria-hidden="true">DS</span>Discovery</a>
        </nav>

        <div class="recent-work">
          <p class="nav-label">Recent launches</p>
          <a class="recent-item selected" href="#">
            <strong>Low-temperature CO2</strong>
            <small>Completed 18 min ago</small>
          </a>
          <a class="recent-item" href="#">
            <strong>Membrane selectivity</strong>
            <small>Round 2 of 3</small>
          </a>
          <a class="recent-item" href="#">
            <strong>Photocatalyst stability</strong>
            <small>Completed yesterday</small>
          </a>
        </div>

        <button class="account-button" type="button">
          <span class="avatar" aria-hidden="true">KL</span>
          <span><strong>Kun Li</strong><small>Researcher</small></span>
          <span aria-hidden="true">&#x22EF;</span>
        </button>
      </aside>

      <main class="a-main">
        <header class="a-toolbar">
          <a href="#">Discovery</a><span aria-hidden="true">/</span><span>DS-0241</span>
          <div class="toolbar-actions">
            <button class="quiet-button" type="button">Share</button>
            <button class="primary-button" type="button">Download bundle</button>
          </div>
        </header>

        <section class="a-identity">
          <div>
            <div class="eyebrow-row">
              <span class="status status-complete"><span aria-hidden="true"></span>Completed</span>
              <span>Discovery Launch</span>
            </div>
            <h1>High-efficiency catalyst discovery for low-temperature CO2 conversion</h1>
            <p>Launched Jul 20, 2026 at 09:42 by Kun Li</p>
          </div>
          <dl class="identity-facts">
            <div><dt>Duration</dt><dd>2h 18m</dd></div>
            <div><dt>Rounds</dt><dd>3</dd></div>
            <div><dt>Candidates</dt><dd>24</dd></div>
          </dl>
        </section>

        <nav class="detail-tabs" aria-label="Launch views">
          <a href="#">Progress</a>
          <a class="active" href="#" aria-current="page">Results</a>
        </nav>

        <section class="metric-strip" aria-label="Key result metrics">
          <div><span>Best validation yield</span><strong>84.7%</strong><small>IR-17</small></div>
          <div><span>Baseline yield</span><strong>61.2%</strong><small>BASE-01</small></div>
          <div><span>Absolute improvement</span><strong class="positive">+23.5 pp</strong><small>95% CI: 20.1 to 26.9</small></div>
          <div><span>Reproducibility</span><strong>0.81</strong><small>3 independent seeds</small></div>
        </section>

        <div class="a-results-layout">
          <div class="a-evidence">
            <section class="result-section">
              <div class="section-heading">
                <div><p class="section-kicker">Primary outcome</p><h2>Validation yield by round</h2></div>
                <span class="method-label">Mean with 95% CI</span>
              </div>
              <figure class="a-chart">
                <svg viewBox="0 0 760 260" role="img" aria-labelledby="a-chart-title a-chart-desc">
                  <title id="a-chart-title">Validation yield increases across three discovery rounds</title>
                  <desc id="a-chart-desc">Baseline yield is 61.2 percent. Best candidate yield rises from 69.8 percent in round one to 84.7 percent in round three.</desc>
                  <g class="grid-lines">
                    <line x1="72" y1="32" x2="724" y2="32" /><line x1="72" y1="91" x2="724" y2="91" />
                    <line x1="72" y1="150" x2="724" y2="150" /><line x1="72" y1="209" x2="724" y2="209" />
                  </g>
                  <g class="axis-labels">
                    <text x="42" y="37">90</text><text x="42" y="96">80</text><text x="42" y="155">70</text><text x="42" y="214">60</text>
                    <text x="130" y="244">Baseline</text><text x="286" y="244">Round 1</text><text x="446" y="244">Round 2</text><text x="606" y="244">Round 3</text>
                  </g>
                  <path class="baseline-line" d="M72 202 H724" />
                  <path class="result-line" d="M156 202 L318 151 L478 104 L638 63" />
                  <g class="result-points"><circle cx="156" cy="202" r="5" /><circle cx="318" cy="151" r="5" /><circle cx="478" cy="104" r="5" /><circle cx="638" cy="63" r="6" /></g>
                  <text class="chart-label" x="650" y="59">84.7%</text>
                  <text class="baseline-label" x="610" y="196">Baseline 61.2%</text>
                </svg>
              </figure>
            </section>

            <section class="result-section">
              <div class="section-heading">
                <div><p class="section-kicker">Candidate experiments</p><h2>Leading configurations</h2></div>
                <button class="text-button" type="button">View all 24</button>
              </div>
              <div class="table-scroll" tabindex="0" aria-label="Scrollable candidate results table">
                <table>
                  <thead><tr><th scope="col">Candidate</th><th scope="col">Round</th><th scope="col">Yield</th><th scope="col">Selectivity</th><th scope="col">Replicates</th><th scope="col">Decision</th></tr></thead>
                  <tbody>
                    <tr><th scope="row">IR-17</th><td>3</td><td><strong>84.7 +/- 1.8%</strong></td><td>92.1%</td><td>3 / 3</td><td><span class="decision selected">Selected</span></td></tr>
                    <tr><th scope="row">IR-12</th><td>3</td><td>79.4 +/- 2.1%</td><td>89.7%</td><td>3 / 3</td><td><span class="decision">Retained</span></td></tr>
                    <tr><th scope="row">IR-08</th><td>2</td><td>75.6 +/- 2.8%</td><td>88.4%</td><td>2 / 3</td><td><span class="decision">Retained</span></td></tr>
                    <tr><th scope="row">BASE-01</th><td>Control</td><td>61.2 +/- 1.5%</td><td>81.9%</td><td>3 / 3</td><td><span class="decision muted">Baseline</span></td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <aside class="a-summary" aria-label="Result summary">
            <section>
              <p class="section-kicker">Finding</p>
              <h2>IR-17 exceeds the baseline without sacrificing selectivity.</h2>
              <p>The strongest configuration improved validation yield by 23.5 percentage points and remained stable across three independent seeds.</p>
              <a class="inline-link" href="#">Read the full paper</a>
            </section>
            <section>
              <p class="section-kicker">Evidence quality</p>
              <dl class="quality-list">
                <div><dt>Independent seeds</dt><dd>3</dd></div>
                <div><dt>Completed evaluations</dt><dd>24 / 24</dd></div>
                <div><dt>Failed runs</dt><dd>1, recovered</dd></div>
                <div><dt>Code provenance</dt><dd>Verified</dd></div>
              </dl>
            </section>
            <section>
              <p class="section-kicker">Research outputs</p>
              <a class="artifact-row" href="#"><span><strong>Discovery paper</strong><small>PDF / 2.8 MB</small></span><span aria-hidden="true">&#x2193;</span></a>
              <a class="artifact-row" href="#"><span><strong>Reproduction bundle</strong><small>ZIP / 18.4 MB</small></span><span aria-hidden="true">&#x2193;</span></a>
              <a class="artifact-row" href="#"><span><strong>Metrics table</strong><small>CSV / 12 KB</small></span><span aria-hidden="true">&#x2193;</span></a>
            </section>
          </aside>
        </div>
      </main>
    </div>`;
}

app.innerHTML = VariantA();
