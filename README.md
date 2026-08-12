# Hypergeometric

**Statistical certification and porting of agent configs across models — no eval suite required.**

Agent configs (system prompts, MCP tool descriptions, skills) are written once, by hand, tuned to whichever model was current that day — then frozen while models change every month. Nobody can answer three questions for a given agent:

- **Fit** — is this config well-matched to the model it runs on right now?
- **Diff** — if the model is swapped, what exactly changes in behavior?
- **Port** — what edits would make the config fit the new model?

The standard answer — "run your eval suite" — fails because most production agents have no eval suite. Hypergeometric answers all three without one.

## How

The core insight: **the config is the spec.** Every rule in a prompt is a testable claim about behavior ("always respond in JSON", "never export without an ID filter"). Checking whether a model follows its own instructions needs no ground truth — verification is generated from the config itself.

```
config ──► 1 PARSE ──► 2 STATIC PASS ──► 3 PROBE SYNTHESIS ──► 4 MEASURE
                                                                   │
   audit ledger + report ◄── 7 CERTIFY ◄── 6 ASSEMBLE ◄── 5 REPAIR ◄┘
```

Decompose the config into atomic rules; probe each rule with generated scenarios, with and without the rule, on both models; sort every rule into *delete / keep / rewrite / fix*; repair broken rules through a generate–filter–measure funnel; reassemble; ship a report where every claim is a count with a confidence bound, plus a clause-level change ledger.

> **The name:** the hypergeometric distribution governs sampling without replacement from a finite population — the math used when certifying against a finite archive of production traces. Its infinite-population sibling, the binomial, covers generated-scenario testing. The name is a commitment: no claim ships without its distribution.

## Details

The full design — pipeline stages, statistics, assumptions and threats to validity, roadmap — lives in **[DESIGN.md](DESIGN.md)**.

## Status

Design phase. Next milestone: Phase 0 — hand-decompose one real prompt, run the ablation grid on ~5 rules across two models, and test the method's own reliability along the way.
