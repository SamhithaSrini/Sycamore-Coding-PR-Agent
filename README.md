# Sycamore — Co-Optimizing AI Coding & Review Agents

A self-improving multi-agent system where a **Coding Agent** and a **Review Agent** co-optimize through structured interaction traces, grounded by real test execution and an independent LLM judge.

Built for the Sycamore OA challenge: *design and prototype a system that uses interaction traces to improve both agents over time using self-play.*

---

## The Problem

AI coding agents (Claude Code, Codex) and AI review agents (Bugbot, Greptile) are trained and improved independently. A coder generates PRs; a reviewer critiques them. Neither learns from the other. Their interaction traces — the back-and-forth of diffs and review comments — are discarded. This is wasted signal.

---

## Architecture

```
GitHub Issue
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Coder Agent  (claude-haiku-4-5)                                │
│  Injects at inference time:                                     │
│    • SKILLS.md, RULES.md, STYLE.md, CONSTITUTION.md (firmware) │
│    • LEARNED_PATTERNS.md  ← failure rules from prior traces     │
│    • few_shot_bank.json   ← top-20 PRs by judge score           │
│    • Recent reviewer patterns from traces  ← cross-trace #2    │
│    • Actual source file content (keyword-routed grep)           │
│  Outputs: <old>/<new> blocks → difflib builds the patch         │
└──────────────────────┬──────────────────────────────────────────┘
                       │ diff
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Pre-Review Hook  (post_pr.py)                                  │
│  Linter + security scan — reviewer sees this, agents do not     │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Reviewer Agent — Mixture of Experts  (claude-haiku-4-5)        │
│  Three personas review independently, weighted vote synthesises │
│    • Correctness  (50%) — logic, edge cases, algorithm          │
│    • Security     (30%) — injection, unsafe ops, credentials    │
│    • Architecture (20%) — structure, tests, naming              │
│  Injects: RUBRIC + CALIBRATION + LEARNED_PATTERNS + coder traces│
│  Anti-collapse guard: forced justification on every approval    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │ approved?               │ changes requested?
          ▼                         ▼
  Ground Truth Layer         ┌──────────────────────┐
  (agents never see raw)     │  Alignment Score      │
                             │  overlap(comments,    │
                             │    next_diff)         │
                             │  → training signal    │
                             └──────────┬───────────┘
                                        │
                                   back to Coder
                                   (max N rounds)

Ground Truth Layer (isolated — agents only see scalar reward):
  ┌─────────────────────────────────────────────────────┐
  │  Test Runner: git apply in-place → pytest → revert  │
  │  Judge (claude-sonnet-4-6, different tier):         │
  │    correctness, security, test_quality,             │
  │    code_clarity, issue_alignment  →  0–1 score      │
  │  Oracle: reward = tests(50%) + judge(35%)           │
  │                          + preference(15%)          │
  │  uncertainty = std_dev(signals)                     │
  │  use_for_training = uncertainty < 0.25              │
  └─────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Reviewer–Coder Alignment Score
```
alignment = overlap(review_comments, changes_in_next_diff)
```
For each blocking/suggestion comment, an LLM call checks whether the next diff addressed it. Score = `addressed / total`. Routes training signal:

| Alignment | Reward | Interpretation | Training signal |
|-----------|--------|----------------|-----------------|
| High ≥0.8 | High   | Both agents working well | Positive for both |
| Low  <0.4 | High   | Reviewer gave irrelevant comments | Reviewer negative |
| Low  <0.4 | Low    | Coder ignored valid feedback | Coder negative |
| High      | Low    | Reviewer was wrong; coder followed bad advice | Neither trained on |

### 2. Cross-Trace Context at Inference Time
Both agents see each other's traces **at inference time**, not just at training time:
- **Coder** gets recent reviewer patterns before generating — anticipates feedback
- **Reviewer** gets recent coder mistakes — calibrated to current coder distribution

### 3. LEARNED_PATTERNS.md — Grounded Memory
Instead of LLM-rewritten firmware, `prompt_updater.py` extracts structured facts directly from trace data each cycle:
- Coder gets categorised failure rules with counts ("empty_diff: 11 times — always include source changes") and the exact reviewer + judge reasoning from failed traces
- Reviewer gets ground-truth-confirmed calibration: which patterns the judge confirmed vs contradicted, and persona debate outcomes

### 4. difflib-Based Patch Generation
The coder outputs `<old>/<new>` code blocks; the system builds the unified diff with `difflib.unified_diff`. Eliminates the classic LLM failure of wrong `@@ hunk header counts` that cause `git apply` to fail with "corrupt patch."

### 5. Information Barrier
Ground truth (test results, coverage) never touches agent prompts. Only a scalar reward and directional hints (`test_signal: "pass"/"fail"/"partial"`) leave the oracle layer.

### 6. Anti-Pathology Stack
| Pathology | Detection | Response |
|-----------|-----------|----------|
| Reviewer collapse | >70% round-1 approval rate | Force-update CALIBRATION.md |
| Adversarial strictness | >95% rejection rate | Recalibration note |
| Reward hacking | Judge flags mismatched description vs diff | Zero reward, excluded from training |
| Uncertainty | Std dev across signals >0.25 | `use_for_training=False` |
| Distributional shift | Reviewer accuracy vs GT drops below 60% | Auto-recalibration |

---

## Results

### pallets/click — system validation (3 training cycles, 5 issues/cycle)

Early runs on click confirmed the end-to-end loop: patches apply, tests run, reward hacking is detected and zeroed out, LEARNED_PATTERNS accumulate correctly.

| Cycle | Avg Reward | Test Pass Rate | Hacking Rate |
|-------|-----------|----------------|--------------|
| 1     | 0.055     | 0.186          | 0.400        |
| 2     | 0.323     | 0.373          | 0.000        |
| 3     | 0.369     | 0.373          | 0.000        |

Reward hacking eliminated after cycle 1 as LEARNED_PATTERNS propagated the judge's reasoning back to the coder. click has many open feature-request issues that produce empty diffs — radicli was chosen as the primary training repo for its smaller, more focused issue backlog.

### explosion/radicli — smoke test (1 issue)

First run on radicli after the LEARNED_PATTERNS memory was seeded from click training:

| Metric | Value |
|--------|-------|
| Oracle reward | **0.841** |
| Test pass rate | **1.00** (128/128) |
| Tests added | **6** |
| Judge score | **0.97** |
| Resolved in | **1 round** |
| Reward hacking | **0.000** |

Full multi-cycle radicli results to follow.

---

## Learning Mechanism

Three layers, applied each training cycle:

**Layer 1 — Firmware updates** (immediate, every cycle):
- `agents/coder/LEARNED_PATTERNS.md` — failure rules + successful patch patterns from traces
- `agents/reviewer/LEARNED_PATTERNS.md` — GT-confirmed calibration + persona debate outcomes
- `agents/reviewer/CALIBRATION.md` — alignment-signal auto-notes
- `agents/coder/few_shot_bank.json` — top-20 PRs by judge score, injected at inference

**Layer 2 — RLHF from git history** (bootstrapped once):
- Mine merge commits → preference pairs (merged diff = preferred)
- Jaccard token-overlap similarity for preference scoring

**Layer 3 — Fine-tuning datasets** (generated, ready for future use):
- JSONL datasets in `data/finetune_datasets/` for coder + reviewer
- Anthropic fine-tuning API not public yet; datasets saved for when it is

---

## Repo Structure

```
├── agents/
│   ├── coder/          SKILLS, RULES, STYLE, CONSTITUTION, LEARNED_PATTERNS, few_shot_bank
│   ├── reviewer/       RUBRIC, CALIBRATION, CONSTITUTION, PERSONAS, LEARNED_PATTERNS
│   └── judge/          CRITERIA, prompt_template
├── core/
│   ├── coder_agent.py          Coding agent with file-context injection + difflib patching
│   ├── reviewer_agent.py       MoE reviewer (3 personas + anti-collapse guard)
│   ├── judge_agent.py          Independent judge (claude-sonnet-4-6, cross-tier)
│   ├── interaction_loop.py     Main coder → reviewer → revise loop
│   └── confidence.py           ConfidenceBundle builder
├── ground_truth/
│   ├── oracle.py               Aggregates signals → scalar reward (information barrier)
│   └── test_runner.py          In-place git apply + pytest + git checkout revert
├── learning/
│   ├── trace_collector.py      InteractionTrace + ConfidenceBundle dataclasses
│   ├── alignment.py            Reviewer–Coder Alignment Score
│   ├── signal_extractor.py     Extracts training signals from traces
│   ├── prompt_updater.py       Builds LEARNED_PATTERNS from grounded trace data
│   └── rlhf_pipeline.py        Git history → RLHF preference pairs
├── hooks/
│   ├── drift_detector.py       Rolling-window pathology detection
│   └── post_pr.py              Pre-review linter + security scan
├── evaluation/
│   ├── metrics.py              10 metrics tracked per cycle
│   ├── held_out_eval.py        Evaluation on issues never trained on
│   └── analysis.py             Improvement curves + failure report
├── scripts/
│   ├── bootstrap_repo.py       Clone repo, fetch issues, extract RLHF pairs
│   └── run_training_cycle.py   Full training orchestration
└── data/
    ├── issues/                 Training issues (JSON)
    ├── held_out/               Held-out issues (never trained on)
    └── metrics_history.json    Per-cycle metrics for improvement curves
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API key
cp .env.example .env
# edit .env: add ANTHROPIC_API_KEY=sk-ant-...

# 3. Bootstrap (clone repo, fetch issues, extract RLHF pairs)
python scripts/bootstrap_repo.py

# 4. Run training cycles
python scripts/run_training_cycle.py --cycles 3 --issues-per-cycle 5

# 5. View results
python -m evaluation.analysis
```

### Switching repos (radicli, flask, etc.)
```bash
REPO_PATH=/tmp/radicli \
PROJECT_NAME=radicli \
PACKAGE_DIR=radicli \
TEST_DIR=radicli/tests \
python scripts/run_training_cycle.py --cycles 3 --issues-per-cycle 5
```

---

## Metrics

| Metric | What it measures |
|--------|-----------------|
| `avg_final_reward` | Composite ground-truth score (primary metric) |
| `resolution_rate_le2_rounds` | % issues resolved in ≤2 rounds (efficiency) |
| `avg_test_pass_rate` | Direct GT signal — unfakeable |
| `reviewer_accuracy` | % reviewer decisions aligned with GT |
| `reviewer_coder_alignment` | Avg overlap(review_comments, next_diff) |
| `reward_hacking_rate` | Should stay near 0 |
| `training_data_efficiency` | % traces usable for fine-tuning |
| `held_out_avg_reward` | Generalization to unseen issues (most important) |

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Coder / Reviewer | claude-haiku-4-5-20251001 | Fast, cheap |
| Judge | claude-sonnet-4-6 | Cross-tier independence from agents |
| Target repo | pallets/click, explosion/radicli | Small test suite, focused issues |
| Test runner | In-place git apply + revert | No file copying overhead (~6s/run) |
| Patch generation | difflib.unified_diff | Correct hunk headers, no LLM counting errors |
