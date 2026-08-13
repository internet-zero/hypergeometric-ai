# Hypergeometric

**Safely move an AI agent from one model to another — and prove nothing broke.**

## The problem

Every AI agent runs on two things: a model, and a set of written instructions (its system prompt, tool descriptions, and skills). Those instructions were written once, by hand, tuned to whatever model was current at the time — and then frozen, while new models keep shipping every month.

So when a better or cheaper model comes out, teams face a bad choice:

- **Don't switch** — and keep paying more for less capability
- **Switch blind** — and hope nothing silently breaks

Nobody can say which instructions still work on the new model, which ones the new model ignores, or which ones it never needed in the first place. The usual fix — "test it against your eval suite" — doesn't help, because most agents don't have one.

## What this project does

Hypergeometric checks an agent's instructions against any model directly, using a simple observation: **every instruction already says what correct behavior looks like.** "Always respond in JSON" — either the output is JSON or it isn't. "Never export data without a filter" — either the filter is there or it isn't. No answer key needed; the instructions are the answer key.

So the system:

1. Splits the instructions into individual rules
2. Watches how each model actually behaves with and without each rule, across many varied situations
3. Sorts every rule into **delete** (the new model doesn't need it), **keep** (it's working), or **rewrite** (the new model ignores it)
4. Fixes the broken rules and re-checks them
5. Produces a report where every claim is backed by counted results — plus a full change log of what was edited and why

The outcome: a migration that's measured instead of guessed, with receipts.

> **The name** comes from the hypergeometric distribution — a piece of statistics used when checking a sample and drawing conclusions about the whole. It reflects the project's rule: no claim without the math to back it.

## More

Everything lives in **[DESIGN.md](DESIGN.md)** — the full design derived from first principles: eight forced moves → four laws → three phases → statistics → threats and assumptions → roadmap with the Milestone-0 protocol → decision log → glossary.

## Status

Design complete. Next: run Milestone 0 — the weekend experiment (protocol in DESIGN.md) that both demos the method on a real config and tests its own foundations.
