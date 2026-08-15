# Prototype — Milestone-0 ablation grid in one script

`validate.py` implements a scoped-down version of DESIGN.md's Milestone 0: given a
system prompt, a hand-cut rule inventory, and two models, it measures per-rule
compliance with the rule **present vs. placebo-ablated**, on **both models**, over
generated probe scenarios — then classifies every rule (DELETE / KEEP / REWRITE)
and reports the migration diff with Wilson intervals and exact McNemar tests.

Two planted control rules are injected automatically (the instrument's self-test):
a redundant rule that must land in DELETE and a load-bearing marker rule that must
land in KEEP. If either misclassifies, the harness is broken — don't read the rest.

## Run

```bash
pip install openai pyyaml            # python 3.11+
python validate.py --selftest        # offline: verify all checkers
python validate.py --prompt example.prompt.txt --rules rules.example.yaml --dry-run
OPENAI_API_KEY=... python validate.py \
  --prompt example.prompt.txt --rules rules.example.yaml \
  --model-a gpt-5.6-luna --model-b gpt-5.6-sol --probes 30
```

Outputs land in `results/grid.md` (the migration grid) and `results/raw.jsonl`
(append-only run records).

## Testing a private config

Put the prompt and rule inventory under `local/` (gitignored) and point
`--prompt` / `--rules` at them. Rule `text` entries must appear **verbatim** in
the prompt file — the script fail-fasts otherwise (that's the placebo ablation
contract). Set `tools_enabled: true` on a rule plus a `tools:` list in the YAML
to probe tool-choice discipline (first-call checks; tools are never executed).

## Prototype limitations (deliberate)

Single-turn probes; tool calls captured but never executed; mechanical checkers
only (no judges); tier-2 realism approximated with long synthetic contexts;
k=1 by default — prefer more distinct probes over repeats at fixed budget.
