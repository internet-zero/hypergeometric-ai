# Milestone 0 — The Proof Experiment

The first weekend of work, specified so it can be executed without re-deriving anything. Two jobs at once: **demo the method on a real config** and **test the method's own validity** (threat 1: decomposition independence). If this experiment fails its gates, stop and rethink before building anything expensive.

## What this does and does not test

| Question | Tested here? |
|---|---|
| Does the ablation grid produce stable verdicts? (reliability) | **Yes** |
| Does it find anything on a "known-good" prompt? (discriminative power) | **Yes** |
| Do rules test independently? (interaction size) | **Yes — coarsely** |
| Do generated probes transfer to real traffic? (threat 2) | **No** — needs a trace-rich agent + temporal backtest |
| How big is the quality residue? (threat 3) | **No** — needs an outcome reference (eval bank / human grading) |

## Prerequisites

- Two API-accessible chat models (incumbent stand-in "A", candidate "B") — any two models of different generations or families
- One real agent config: a system prompt + at least one tool definition, ideally borrowed from a real or open-source agent (not written for this test)
- No production traces required (tier-2 probes are synthesized as long conversations; note this limitation in results — it weakens tier-2 realism, acceptable at milestone 0)

## Protocol

### Day 1 — Represent (by hand)

1. **Decompose by hand** (no LLM parser yet): cut the config into ~20 atomic rules with IDs and types. Hand-decomposition sidesteps the parsing-quality open question.
2. **Select 5 rules to test** — the most *mechanically checkable* ones (format, tool-argument, confirmation types). Skip style/judge rules entirely at milestone 0.
3. **Plant two control rules** (this validates the instrument itself):
   - **Planted-redundant:** a rule the model certainly does natively (e.g. "always respond in English" for an English-only setup). Must land in cell ① *delete*. If it doesn't, the harness is broken.
   - **Planted-load-bearing:** an arbitrary detectable rule the model would never do unprompted (e.g. "end every response with the token §DONE§"). Must land in cell ② *keep* (complies with, violates without). If it doesn't, the harness is broken.
4. **Write checkers**: one small script per rule (JSON parses / argument present / token present / word count). No judges at milestone 0.
5. **Generate probes**: ~40 candidates per rule via an LLM (a *different* model than A or B where possible), then:
   - dedupe by embedding similarity → keep ~30 genuinely distinct
   - load-bearing check: for each probe, confirm a violation would be visible; drop blind probes
   - mix: ~20 tier-1 (direct), ~10 tier-2 (rule trigger at the end of a synthesized long conversation)

### Day 2 — Measure and analyze

6. **Run the grid** on 7 rules (5 real + 2 planted): probes × {rule present, rule replaced by same-length neutral filler} × {model A, model B} × k=3 repeats.
   - Call budget: 7 × 30 × 2 × 2 × 3 ≈ **2,500 calls** (tier-1 probes are short; expect tens of dollars, a few hours parallelized)
7. **Re-run the grid once** (identical inputs) for the reliability check: +2,500 calls.
8. **Pair ablations**: pick 5 rule-pairs among the 5 real rules; run probes with *both* rules filler-replaced, on both models, k=3: ≈ **900 calls**.
9. **Analyze** (all mechanical):
   - Compliance rates with Wilson intervals, per rule × arm × model
   - Cell assignment per rule per model (delete / keep / rewrite / fix)
   - Grid diff A vs. B = the mini migration report
   - Retest comparison, pair-vs-single deltas, control outcomes

Total: ~6,000 calls, roughly a tank of gas in API cost.

## Go / no-go gates

| Gate | Pass | Fail action |
|---|---|---|
| **Controls** | Planted-redundant → cell ①; planted-load-bearing → cell ② on both models | Any misclassification = harness bug. Fix before interpreting anything else |
| **Reliability** | Among rules whose rates are non-borderline (CI does not span the cell threshold), zero verdict flips between run 1 and run 2 | 1 flip → investigate that rule; ≥2 flips → method is noise at this n: raise n or stop |
| **Discriminative power** | ≥1 real rule lands in *delete* or *rewrite* on at least one model | All 5 "keep" on both models → suspicious; add 2 more rules; if still nothing, the grid may lack sensitivity at n=30 |
| **Independence (coarse)** | For ≥4 of 5 pairs: pair-ablation effect ≈ sum of single effects, within CI noise | Systematic super-additive effects → rules interact; the design needs cluster/joint testing before scaling |

**Interpretation discipline:** verdict flips must be judged against sampling noise — at n=30, a rule at 85% compliance has a wide interval, and flips near a threshold are expected *statistically*, not evidence of method failure. Only non-overlapping-CI flips count against the reliability gate.

## Deliverables

Commit to this repo:

- `results/grid.md` — the full four-cell table for both models, with rates and intervals
- `results/retest.md` — run-1 vs. run-2 verdict comparison + flip analysis
- `results/pairs.md` — pair vs. sum-of-singles deltas
- `results/controls.md` — planted-rule outcomes
- A verdict paragraph: proceed to Milestone 1 / fix and repeat / stop

## What a success looks like

Both controls classified correctly; verdicts stable across reruns; at least one dead or ignored rule discovered in a config everyone assumed was fine; pair effects roughly additive. That outcome simultaneously proves the instrument works and produces the first real finding — the demo and the validation are the same table.
