# Mastery plan — rebuilding this project independently

Purpose: everything in this repo so far was built with heavy scaffolding (config written for
you, bugs pointed out line-by-line, hints given readily). That's the right way to *build*
something for the first time — it is not, on its own, enough to *own* it in an interview.
This plan closes that gap. Not meant to start immediately — a reference for when you're
ready to go from "I built this with help" to "I can rebuild this alone and explain every
line."

Rule for the whole plan: work in a **separate folder/branch**, never copy-paste from the
existing repo. Looking at the finished code to "check" is allowed only *after* a genuine
attempt, same as code review worked throughout this project — the difference now is Claude's
role shifts from co-builder to reviewer/interrogator only.

## Phase A — Explain without notes (no code, ~1-2 hours)

For each item below, explain it out loud or in writing, closed-book, in under 2 minutes.
If you can't, that's the study list — go re-read that section of `docs/learning-log.md`
before moving to Phase B, don't skip ahead.

- Why idempotency matters and what specifically makes `save_fx_rates` idempotent
- What `random.seed(date)` buys you and what breaks without it
- The Hive-partition collision bug: what happened, why, and how it was proven (not just fixed)
- Why `base=EUR` and not `base=USD` for the FX extractor
- What `source()` vs `ref()` each mean and why the distinction matters for dbt's DAG
- Why the intermediate join uses `LEFT JOIN` and not `INNER JOIN`
- The difference between a dbt generic test and a singular test
- Why the defect-injection eval found that two defects can mask each other
- Why the Airflow DAG wasn't executed in this environment, and what would fix that

## Phase B — Rebuild from scratch, milestone by milestone

Same order as before, but this time you get only the **task-level prompt**, not the
scaffolding:

1. Repo skeleton + git + pinned Python venv
2. FX extractor: fetch + idempotent save, against the real Frankfurter API
3. Synthetic positions extractor: deterministic, seeded
4. Load raw JSON into DuckDB
5. dbt project setup (`dbt_project.yml`, `profiles.yml`, sources) + `stg_positions`
6. `stg_fx_rates` — including deciding for yourself how to reshape the struct
7. `int_position_valuations` — the point-in-time join, from scratch
8. Marts + at least 8 dbt tests of your own choosing (not copied from this repo)
9. A defect-injection script you design yourself — different defects than the ones already
   used here are more valuable than repeating the same 4

At each step: attempt fully first. Only after a real attempt, diff your version against the
committed one in this repo and explain every meaningful difference — not "mine is worse,"
but *why* each difference exists.

## Phase C — Debugging gauntlet

Ask Claude to inject a mix of real bugs from this project's history (the Hive-partition
collision, the `base=USD` direction error, an `os.mkdir`-vs-`os.makedirs` mistake) **plus**
new ones you haven't seen — pick 3-4 from: a race condition, a broken API contract, bad
retry logic, a stale cache, incorrect auth scoping, a memory issue, hallucinated LLM output,
an evaluation-metric bug. Work each one as: **reproduce → isolate → hypothesize → debug →
fix → test → explain**, out loud, before looking at any hint.

## Phase D — Build something new, unassisted

Design and build one thing that doesn't exist in this repo yet, with only high-level
architecture feedback from Claude (no task breakdown, no scaffolding): a third raw source,
or a new mart, or a first pass at the NL→SQL assistant. This is the actual test of whether
skill transferred, versus whether you just memorized this specific pipeline.

## Phase E — Final assessment

Full system walkthrough (end-to-end request flow, every design tradeoff, what you'd change
in v2), followed by an interview-style Q&A and an honest skills score — same structure as
the original assessment framework from the very first message of this project. Only run this
once Phases A-D are genuinely done, not on a time pressure.

---

**When to start this:** whenever you have time that isn't under application pressure — this
is deliberately not a "finish today" activity. The project as it stands is already
apply-ready; this plan is what turns "I built this" into "I can rebuild this," which is the
thing that actually survives a live coding/whiteboard interview question.
