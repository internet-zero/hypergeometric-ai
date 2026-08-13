# Decision Log

Key design decisions, with the reasoning that forced them. Each entry: what was decided, why, and what it costs. Newest thinking lives in [DESIGN.md](DESIGN.md); this file records *why* the design is shaped the way it is.

---

**D1 — Eval-free by construction (config-as-spec).**
*Decision:* verification is generated from the config itself; no eval-suite dependency anywhere.
*Why:* most production agents have no evals and building them takes months — an eval dependency would exclude the majority of the market and reintroduce the exact cost the project exists to remove.
*Cost:* claims are limited to compliance, not outcome quality; the boundary is stated openly (threat 3).

**D2 — Behavior decides; reading only filters.**
*Decision:* no verdict about model fit is ever issued from text analysis — not by embeddings, not by judge models. Embeddings organize (dedupe, clustering); judges triage (drop bad writing); only execution on the target model decides.
*Why:* which phrasing a model obeys is a fact about its weights, invisible in text. Textual similarity ≠ behavioral equivalence.
*Cost:* every decision costs target-model runs; the funnels (triage before contact) exist to conserve them.

**D3 — Three phases, bounded by the read/write line.**
*Decision:* REPRESENT and MEASURE are read-only; TRANSFORM is the only phase that edits; MEASURE is a callable service, not a pipeline step.
*Why:* the phase boundaries fall exactly where cost, risk, output lifetime, and governance needs change — and the service framing gives re-certification and drift monitoring for free.
*Cost:* none identified; this replaced an earlier 7-stage framing that was operational detail masquerading as architecture.

**D4 — Detect early, edit late.**
*Decision:* twin/conflict detection runs before measurement but never edits; all edits happen in TRANSFORM with evidence attached.
*Why:* near-duplicate rules mask each other under ablation (twin masking → false *delete* verdicts on both twins), so the experiment design must know the config's structure first. But editing on the strength of reading alone is blind rewriting — the known-failed approach.
*Cost:* MEASURE must support equivalence-class ablation and joint measurement of conflict pairs.

**D5 — Placebo ablation.**
*Decision:* a "removed" rule is replaced by same-length neutral filler, never deleted.
*Why:* deletion changes prompt length and shifts every other rule's position; measured deltas would confound the rule's content with layout effects.
*Cost:* slightly more harness complexity; negligible.

**D6 — Statistics are mandatory, not decorative.**
*Decision:* detection power sizes probe sets (~200 probes → a ≥10%-broken rule escapes with probability ~10⁻⁹); rule-of-three bounds word the certificates (200 clean → ≤1.5% at 95%); McNemar on paired runs separates regression from noise; Benjamini–Hochberg stops 60 rules from producing false alarms; dedupe keeps effective n honest.
*Why:* without this, reports are vibes with numbers attached; with it, every line survives an argument with a statistician.
*Cost:* borderline rules need more samples (mitigated by sequential early stopping).

**D7 — Text canonical, vectors disposable.**
*Decision:* the pipeline pins its own standalone embedding model; every artifact stores source text; vector indexes are rebuildable caches.
*Why:* embeddings from different models (or versions) occupy unrelated spaces — vectors survive no migration, text survives all of them. Chat-model migration must never invalidate stored state.
*Cost:* an embedder upgrade triggers a cheap re-embed + re-cluster.

**D8 — Execution-parity probes for executable outputs.**
*Decision:* when the agent's output executes (Mongo pipelines, SQL, code, API calls), run both models' outputs against the same snapshot environment and compare *results*, not text.
*Why:* execution is a free oracle — equal results = semantic equivalence with no ground truth and no judge; the generative zones become the best-certified, not the worst.
*Cost:* needs a snapshot environment and result normalization; snapshot equivalence ≠ universal equivalence (mitigate with adversarial data seeds).

**D9 — Honest validation clocks.**
*Decision:* Milestone 0 claims to test threat 1 only (reliability, discriminative power, interaction size). Threat 2 (probe→traffic transfer) requires a trace-rich agent and a temporal backtest; threat 3 (quality residue) requires an outcome reference.
*Why:* an earlier draft claimed the weekend experiment tested all three assumptions; thorough checking showed that was overstated. A certification product cannot afford overclaimed self-validation.
*Cost:* the full validity story takes months, not a weekend — stated plainly.

**D10 — v1 scope: MCP tool-calling agents, report-first.**
*Decision:* one agent shape end-to-end; the read-only migration report is the first shippable unit; no RL, no dashboards, no general-framework ambitions until then.
*Why:* rule-dense tool agents are where compliance coverage is strongest (threat 3 corollary) and where the market pain concentrates; measurement without porting is already sellable.
*Cost:* conversational/creative agents are explicitly out of scope for v1.
