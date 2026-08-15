# The harness — Milestone-0 ablation grid

The `hypergeometric` package implements a scoped-down version of DESIGN.md's
Milestone 0: given a system prompt, a hand-cut rule inventory, and two models,
it measures per-rule compliance with the rule **present vs. placebo-ablated**,
on **both models**, over generated probe scenarios — then classifies every rule
(DELETE / KEEP / REWRITE / FIX-URGENT) and reports the migration diff with
Wilson intervals and exact McNemar tests.

Two planted control rules are injected automatically (the instrument's
self-test): a redundant rule that must land in DELETE and a load-bearing marker
rule that must land in KEEP. If either misclassifies, the harness is broken —
don't read the rest.

## Layout

| Module | Responsibility |
|---|---|
| `hypergeometric/schemas.py` | frozen dataclasses: `Rule`, `Arms`, `RunResult`, `ArmStats` |
| `hypergeometric/checkers.py` | mechanical compliance checkers + self-test cases |
| `hypergeometric/stats.py` | Wilson intervals, exact McNemar, cell classification |
| `hypergeometric/config.py` | rule/skill loading, source-aware placebo ablation |
| `hypergeometric/probes.py` | probe generation and dedupe |
| `hypergeometric/grid.py` | the four-way ablation grid (async, bounded concurrency) |
| `hypergeometric/report.py` | aggregation and `results/grid.md` |
| `hypergeometric/cli.py` | `hypergeometric` command / `python -m hypergeometric` |

## Run

```bash
pip install -e ".[dev,live]"                 # python 3.11+
python -m hypergeometric --selftest          # offline: verify all checkers
python -m hypergeometric --prompt examples/example.prompt.txt \
    --rules examples/rules.example.yaml --dry-run
OPENAI_API_KEY=... python -m hypergeometric \
    --prompt examples/example.prompt.txt --rules examples/rules.example.yaml \
    --model-a gpt-5.6-luna --model-b gpt-5.6-sol --probes 30
```

Outputs land in `results/grid.md` (the migration grid) and `results/raw.jsonl`
(append-only run records).

## Tests

Structured like a production service repo: `tests/unit/` (checkers, stats,
parsing/ablation), `tests/test_grid_e2e.py` (offline end-to-end grid against a
scripted fake client with known ground-truth verdicts), shared helpers in
`tests/tools.py`, and `tests/agent/` for live integration runs — env-gated,
skipped in CI via `addopts` in `pyproject.toml`.

```bash
pytest                                   # offline suite
OPENAI_API_KEY=... pytest tests/agent/   # live smoke grid (needs local/ bundle)
```

## Testing a private config

Put the config bundle under `local/` (gitignored) and point `--prompt`,
`--rules`, and `--skills-dir` at it. Rules can live in **any of the three
config surfaces** via `source:` — `prompt` (default), `tool:<name>` (ablates
inside that MCP tool's description), or `skill:<name>` (skill text is appended
to the prompt and ablated there). Rule `text` entries must appear **verbatim**
in their source artifact — the CLI fail-fasts otherwise (that's the placebo
ablation contract). Tools are passed to the API for `tools_enabled` rules but
never executed (first-call and argument checks only).

## Prototype limitations (deliberate)

Single-turn probes; tool calls captured but never executed; mechanical checkers
only (no judges); tier-2 realism approximated with long synthetic contexts;
k=1 by default — prefer more distinct probes over repeats at fixed budget.
