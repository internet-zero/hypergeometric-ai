# Hypergeometric

**Statistical certification and porting of agent configurations across models — no eval suite required.**

Agent configs (system prompts, MCP tool descriptions, skills) are written once, by hand, implicitly tuned to whichever model was current that day — then frozen while models change every month. Nobody can answer three questions today, for any given agent:

1. **Fit** — is this config actually well-matched to the model it runs on right now?
2. **Diff** — if the model is swapped, what exactly changes in the agent's behavior?
3. **Port** — what edits would make the config fit the new model (or the current one, better)?

The standard answer — "run your eval suite" — fails in practice because most production agents have no eval suite, and building one takes months. Hypergeometric answers all three questions without evals, and emits results where **every recommendation carries evidence and every claim carries a confidence bound**.

> **Why the name:** the hypergeometric distribution governs sampling without replacement from a finite population — the math used here when certifying a config against a finite archive of production traces ("we tested 200 of the 10,000 logged conversations; what can we say about the rest?"). Its infinite-population sibling, the binomial, governs the generated-scenario testing. The name is a commitment: no claim ships without its distribution.

---

## The core insight: the config is the spec

An eval suite asks *"was the answer good?"* — which requires humans to define "good" per task. That's the expensive part, and the part this project refuses to depend on.

Hypergeometric asks a different question: *"did the model follow its own instructions?"* Every rule in a config is a testable claim about behavior. "Always respond in JSON" — did the output parse? "Never call `export_csv` without `id_filter`" — was the argument present? The config itself defines correct behavior, so **verification can be generated from the config automatically**. No ground truth, no labels, no eval authors.

The honest boundary of this approach, stated up front: compliance ≠ quality. A config can be faithfully followed and still produce mediocre answers. But for the migration problem — *"make the new model behave like the old one did, provably"* — compliance parity is precisely the promise that matters. Outcome evals remain a valid phase-two; the probe library built here becomes their seed.

Three principles hold the whole system together:

1. **The config is the spec.** Verification is generated from the rules themselves.
2. **Behavior is the only ground truth.** Which phrasing a model obeys is a fact about the model's weights, not about the text. Embeddings organize, judge models filter — but only execution on the target model decides.
3. **No claim without a number.** Compliance rates with confidence intervals, paired significance tests for regressions, multiple-comparison corrections. Every line of the report should survive an argument with a statistician.

---

## Architecture: the seven-stage pipeline

```
config ──► 1 PARSE ──► 2 STATIC PASS ──► 3 PROBE SYNTHESIS ──► 4 MEASURE
                                                                   │
   audit ledger + report ◄── 7 CERTIFY ◄── 6 ASSEMBLE ◄── 5 REPAIR ◄┘
```

The pipeline is a meta-agent: a deterministic workflow whose organs are LLM calls (a parser, a scenario generator, a judge, a merger). It runs ambient — woken by a new model release, a config change, or a batch of fresh traces — files its outputs, and sleeps.

### Stage 1 — Parse

Decompose the config into an inventory of **atomic directives**: one rule per unit, each with an ID, a type, and a source location.

- Input: system prompt, MCP tool descriptions, skill files
- Output: `directives.json` — e.g. a 4,000-token prompt → ~60 addressable rules
- Directive types drive probe design downstream: `format` | `tool-use` | `conditional` | `prohibition` | `confirmation` | `style`

Everything downstream operates at directive granularity. This is what makes targeted repair and clause-level audit possible.

### Stage 2 — Static pass (no model calls)

Three read-only analyses:

- **Redundancy / contradiction detection.** Embed directives; flag near-duplicates and semantically opposed pairs (e.g. "be concise" vs. "explain in detail" living in prompt and skill respectively).
- **Style lint.** Check directives against the accumulated per-model pattern base (see *Knowledge base* below).
- **Implicit-contract extraction.** Mine the incumbent model's production traces for stable behavioral regularities that **no directive mandates** (e.g. the model always includes units in tables — in 100% of sampled outputs — yet nothing requires it). Promote these to explicit directives *before* migration. This covers the deepest migration failure mode: silently losing behavior that lived in the old model rather than in the config.

Embeddings are used strictly for organization (similarity, clustering, dedup). They never issue verdicts about model fit — semantic similarity does not predict behavioral equivalence.

### Stage 3 — Probe synthesis

Per directive, generate a scenario set that exercises it:

- **Volume then pruning:** generate ~200 candidate scenarios; deduplicate by embedding cluster (near-paraphrases count as one test — inflating n with costume-changes corrupts every downstream interval); auto-validate **load-bearingness** (a rule violation must be *detectable* in the output — a scenario where violation is invisible is a wasted trial that inflates pass rates).
- **Three tiers:**
  - *Direct* — short, clean, the directive plainly applies
  - *Under load* — the same trigger buried in long, messy, realistic context (spliced into real traces); compliance under load is where models actually differ
  - *Conflict* — user pressure or another directive pushes against the rule
- **Generator hygiene:** never let only the target model generate its own probes (a model writes scenarios it understands — the student writing its own exam). Mix generator models and blend in real production traces, which are the true input distribution.

Design law for every probe: a complying model and a violating model must produce visibly different outputs. If you can't say what a violation would look like, the probe is invalid.

The scenario set is the durable asset of the whole system: built once per directive, reused for measurement (stage 4), repair scoring (stage 5), and re-certification.

### Stage 4 — Measure: the ablation grid

The heart of the system. Run each directive's probes **four ways**: directive present / removed × incumbent model / candidate model. Same probes, paired, k ≥ 3 repeats per probe (compliance is a rate, not a boolean). Compliance is checked against the directive itself — mechanically where possible (JSON parses; argument present; tool not called), a small judge model for soft directives.

Every directive lands in one of four cells per model:

| | Complies **without** directive | Violates **without** directive |
|---|---|---|
| **Complies with** | ① **Delete** — model does this natively; directive is dead weight | ② **Keep** — load-bearing, working |
| **Violates with** | ④ **Fix urgently** — directive actively harmful | ③ **Rewrite** — model can't hear this phrasing |

Directive utility is Δ(behavior with vs. without). Cell ① answers "what is the new model natively good at" (free token savings); cell ③ marks rules the phrasing fails to reach; cell ④ (rare) marks rules that collide with the model's training or another directive.

**The migration report is the diff of the two grids** (incumbent vs. candidate): "R7 was load-bearing, now native → delete. R2 was load-bearing, now ignored → rewrite. R4 flipped to harmful → urgent."

### Stage 5 — Repair (cells ③ and ④ only)

The variant funnel — *reading narrows, running decides*:

1. **Generate** ~200 rewrites of the broken directive, varying wording, framing (prohibition ↔ requirement ↔ positive), structure (prose ↔ checklist), placement (system prompt ↔ tool description), and worked examples.
2. **Judge triage (text-only, cheap):** a judge model discards ambiguous, contradictory, and duplicate rewrites → ~10 finalists. Reading can eliminate bad writing; it cannot predict what the target model will obey — that information lives in the target's weights and is invisible in the text.
3. **Behavioral contact:** run the finalists against the ~20 hardest scenarios from stage 3 on the target model → 2–3 measured winners.
4. **Merge:** the judge combines the winners' strengths into one final directive; re-run the full scenario set to confirm it lands in cell ②.

Each repair also emits a *lesson* for the knowledge base (e.g. "model X weighs tool descriptions over mid-prompt prose; responds to precondition checklists").

### Stage 6 — Assemble & smoke

Reassemble the config from surviving and repaired directives, then run the **whole config** once through real traces and top-tier probes. Directives interact: two individually-passing rules can conflict in combination (a repaired refusal message truncated by a strengthened word-limit rule). Per-directive optimization plus one whole-config verification pass is the tractable middle between "test nothing jointly" and the combinatorially impossible "test all combinations."

### Stage 7 — Certify & audit

Three artifacts out the door:

1. **The ported config** — versioned (vN → vN+1)
2. **The migration report** — every claim a count: "R2: 97/100 → 71/100 on identical paired probes (p ≈ 0.01, survives FDR at m=60); rewritten; re-certified at 96/100"
3. **The change ledger** — per changed directive: old text, new text, reason, probe-set ID, before/after rates, timestamps. The config becomes version-controlled at clause granularity — an AST diff, not a prose diff.

Example ledger entry:

```yaml
rule: R2 (export_csv requires id_filter)
change: rewritten + relocated to tool description
reason: compliance regression on candidate model
evidence:
  before: 71/100   # incumbent: 97/100, same probe set
  after:  96/100   # probe set psi-r2-v3, k=3
  clash_fix: R4 exemption added after smoke run
config: v14 -> v15
```

---

## The statistics

Every number in a report is backed by one of the following. None of it is exotic; all of it is mandatory.

**Rule of three (zero-failure certification).** n clean trials with zero failures → 95%-confidence upper bound on the true failure rate ≈ **3/n**. 100 trials → ≤3%; 200 → ≤1.5%; 3,000 → ≤0.1%. Corollary: certifying a 10⁻⁹ failure rate needs ~3×10⁹ clean trials — testing one's way to avionics-grade reliability is infeasible (Butler & Finelli), and unnecessary here: the LLM compliance regime is 90–99.9%, quantified honestly.

**Binomial vs. hypergeometric.** Generated scenarios ≈ sampling from an infinite population → binomial confidence intervals (Wilson, preferred over the normal approximation at extreme rates and small n). Auditing a **finite trace archive** → hypergeometric / finite-population correction ("200 of 10,000 traces tested; bound the violations among the remaining 9,800").

**Paired comparison (McNemar).** Both models run the *same* probe set. Significance is computed on the discordant pairs only (probe passed on incumbent, failed on candidate, and vice versa). Far more sensitive than comparing two independent pass rates, at the same sample size.

**Sequential early stopping.** Don't spend 200 probes on every directive. Fails 6 of the first 10 → broken, stop. Passes 50/50 → park it. Concentrate samples on borderline directives where additional data changes the decision (SPRT is the formal machinery). Typical cost reduction: 3–5× at equal confidence.

**Multiple comparisons.** Testing 60 directives at 95% confidence produces ~3 false alarms by chance. Apply Benjamini–Hochberg across the directive set before any "regression" claim ships. Reports that skip this cry wolf.

**Effective sample size.** Confidence intervals assume independent trials. Embedding-dedup of scenarios (stage 3) is not cosmetic — it is what makes n honest.

---

## The knowledge base (the compounding asset)

Every run — every ablation grid, every repair, every merge — emits structured observations about model behavior:

```yaml
model: <candidate>
observation: ignores mid-prompt prose prohibitions under long context
evidence: [R2 grid, psi-r2 tier-2 results]
repair_pattern: relocate to tool description as precondition checklist
observed: 2026-08
```

These accumulate into per-model behavioral profiles that (a) power the stage-2 lint, (b) warm-start stage-5 rewrites, and (c) make the tenth migration between a given model pair dramatically better than the first. No lab publishes this data; no eval platform collects it. The pipeline is disposable; this dataset is not.

---

## Scope

**In scope (v1):** MCP tool-calling agents; one config format end-to-end; the read-only migration report as the first shippable unit (the port/repair loop layers on top).

**Deliberately out:**
- Eval-suite dependencies — the point of the project
- RL — differential testing is cheaper, deterministic, and auditable; a reward signal would be evals in disguise
- Judging model fit from text alone (embeddings or LLM judges) — filtering yes, verdicts never
- General-framework ambitions before one agent shape works end-to-end
- Dashboards before the report and ledger are right — they *are* the product

---

## Roadmap

| Phase | Deliverable | Notes |
|---|---|---|
| 0 — Proof | Hand-decomposed prompt (~20 directives), mechanical checkers for the 5 most testable, ablation grid on two models | No automation; the four-cell table on a real config is the demo. Expect ≥1 dead directive and ≥1 silently-ignored one in a "known-good" prompt |
| 1 — Certifier | Automated parse → probes → grid → stats; **read-only migration report** | Sellable alone; every report ends with "want these regressions fixed?" |
| 2 — Porter | Repair funnel, assembly, smoke, ledger | Certified auto-migration |
| 3 — Flywheel | Knowledge base, trace mining, implicit-contract extraction, sequential-testing optimization | The moat |

---

## Open questions

- Directive parsing quality: how reliably can an LLM decompose arbitrary prompts into genuinely atomic, non-overlapping directives? (Phase 0 sidesteps via hand-decomposition; phase 1 must solve it.)
- Judge-model bias in soft-directive scoring: which style/tone checks are stable across judge models?
- Interaction coverage: is one whole-config smoke pass enough, or do high-risk directive *pairs* (identified how?) deserve targeted joint probes?
- Trace privacy: minimum viable redaction for running stage 2/3 on customer traces in-VPC.
- When does compliance parity fail as a proxy — i.e., migrations where the config was followed on both models but outcome quality still shifted?
