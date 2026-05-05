<img width="417" height="720" alt="Screenshot 2026-05-04 at 6 12 29 PM" src="https://github.com/user-attachments/assets/a6896c95-c43d-4deb-88dc-7eb2939655be" />
# Sycamore — Co-Optimizing AI Coding & Review Agents

A self-improving multi-agent system where a **Coding Agent** and a **Review Agent** co-optimize through structured interaction traces, grounded by real test execution and an independent LLM judge.

Built for the Sycamore OA challenge: *design and prototype a system that uses interaction traces to improve both agents over time using self-play.*

---

## The Problem

AI coding agents (Claude Code, Codex) and AI review agents (Bugbot, Greptile) are trained and improved independently. A coder generates PRs; a reviewer critiques them. Neither learns from the other. Their interaction traces — the back-and-forth of diffs and review comments — are discarded. This is wasted signal.

---

## Architecture

<img width="383" height="472" alt="Screenshot 2026-05-04 at 3 53 06 PM" src="https://github.com/user-attachments/assets/e2bec80d-a279-46ed-b578-ee206f441676" />


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

### 4. Self-Healing Loops

Both agents have independent self-healing mechanisms operating at two timescales:

**Coder — intra-trace (within a single issue):**
After each reviewer rejection, the coder reads the blocking comments and rewrites the diff. This continues up to `MAX_ROUNDS` attempts. Each revision prompt includes the previous diff and the exact reviewer feedback, so the coder can see what it got wrong.

**Coder — cross-cycle (after each training batch):**
`LEARNED_PATTERNS.md` is rebuilt from all traces each cycle. The coder literally reads its own failure categories with counts and the verbatim judge + reviewer reasoning from each failed trace. If "empty_diff" appeared 11 times, it says so — and shows the exact feedback so the coder understands *why* it was wrong, not just *that* it was wrong.

<img width="381" height="206" alt="Screenshot 2026-05-04 at 3 53 34 PM" src="https://github.com/user-attachments/assets/5c73881f-f309-435c-bac6-2786558f1d78" />


**Reviewer — reactive (mid-run, no cycle boundary needed):**
The drift detector watches rolling windows of decisions. If it detects collapse (>70% round-1 approval rate) or adversarial strictness (>95% rejection rate), it writes a calibration note to `CALIBRATION.md` immediately — before the next issue runs.

**Reviewer — cross-cycle (after each training batch):**
`LEARNED_PATTERNS.md` is rebuilt from GT-confirmed vs GT-contradicted decisions. The reviewer sees which of its patterns the judge agreed with and which it got wrong, plus persona debate outcomes (which persona was right when they disagreed).

<img width="376" height="216" alt="Screenshot 2026-05-04 at 3 54 00 PM" src="https://github.com/user-attachments/assets/f25545ea-8d71-4d11-936f-f3ce08588596" />


The key distinction: the coder's intra-trace loop is about *responding to feedback in the moment*; both agents' cross-cycle loop is about *not repeating the same class of mistake across issues*.

### 5. difflib-Based Patch Generation
The coder outputs `<old>/<new>` code blocks; the system builds the unified diff with `difflib.unified_diff`. Eliminates the classic LLM failure of wrong `@@ hunk header counts` that cause `git apply` to fail with "corrupt patch."

### 6. Information Barrier
Ground truth (test results, coverage) never touches agent prompts. Only a scalar reward and directional hints (`test_signal: "pass"/"fail"/"partial"`) leave the oracle layer.

### 7. Anti-Pathology Stack
| Pathology | Detection | Response |
|-----------|-----------|----------|
| Reviewer collapse | >70% round-1 approval rate | Force-update CALIBRATION.md |
| Adversarial strictness | >95% rejection rate | Recalibration note |
| Reward hacking | Judge flags mismatched description vs diff | Zero reward, excluded from training |
| Uncertainty | Std dev across signals >0.25 | `use_for_training=False` |
| Distributional shift | Reviewer accuracy vs GT drops below 60% | Auto-recalibration |

---

## Part 3: Evaluation & Analysis

### Metrics

The number we care most about is **held-out reward** — composite score on issues the agents never trained on. Everything else is secondary. We track test pass rate as the only unfakeable signal (a broken diff breaks real tests regardless of what the coder says), and alignment score as the novel signal: did the coder actually address the reviewer's comments, or just make unrelated changes? Reward hacking rate and reviewer accuracy are health checks rather than optimization targets.

We don't track reward on training issues as a primary metric because it conflates memorisation with improvement.

---

### Did both agents improve?

The coder clearly did — held-out reward went from 0.527 to 0.795 across three cycles, and resolution rate in ≤2 rounds improved from 50% to 75%. The reviewer's story is more interesting. Its accuracy dropped to 0.50 in cycle 3, which looks like regression. It's not — cycle 3 had harder issues where even the judge was uncertain (confidence 0.65–0.80 vs 0.95+ on easier ones). The reviewer's LEARNED_PATTERNS grew from zero confirmed cases in cycle 1 to 18 by cycle 3, accumulating concrete "watch for" patterns from judge reasoning.

The more revealing test was cycle 2. The coder briefly learned to write convincing PR descriptions without the implementation — describing tests it hadn't written, claiming fixes it hadn't made. The reviewer rejected all three (accuracy 1.00), reward dropped to 0.450, and LEARNED_PATTERNS updated with the specific judge reasoning. By cycle 3 the hacking was gone. The two agents didn't converge to a collusive equilibrium; the reviewer's stability was what kept the coder honest.

---

### Failure modes

The ugliest one was that every patch failed in the first runs — "corrupt patch at line N" — because LLMs reliably get `@@ hunk header counts` wrong when generating unified diffs. Switching to `<old>/<new>` blocks and computing the diff ourselves with `difflib` fixed it completely. The LLM shouldn't be counting lines.

Reward hacking surfaced exactly as expected in cycle 2: detailed descriptions of multi-scenario tests with no actual implementation in the diff. The judge caught all three and scored them 0.05–0.22. What was satisfying was that we didn't need to add special detection logic — the judge's independent scoring naturally surfaced the mismatch between description and diff.

The drift detector fired "adversarial strictness" repeatedly in early runs, which turned out to be a false positive — the reviewer was correctly rejecting empty diffs from feature-request issues. The real fix was better issue filtering in bootstrap, not recalibrating the reviewer.

One subtle issue: the alignment score occasionally showed "low alignment + high reward" which should flag the reviewer as giving irrelevant feedback. In practice it often meant the coder fixed the underlying problem in a different way than the reviewer suggested — technically low overlap but genuinely good code. The alignment score is a useful signal but needs to be read alongside judge reasoning, not mechanically.

---

### What's next

**Two more weeks:** The biggest lever is more issues per cycle — with 4 issues a single patch failure swings the average by 25%. The other thing worth doing is replacing the keyword grep for file context with a small embedding index over the repo. Right now the coder only finds the right file when the issue explicitly names the function. On real GitHub issues that's rare.

**Two more months:** The improvement loop is entirely in-context right now — LEARNED_PATTERNS lives in a system prompt, not in model weights. With access to a fine-tuning API, each cycle's extracted patterns would actually change what the model knows rather than what it's told. That's the step from prompt engineering to genuine learning. The other thing worth building is a structured reviewer — instead of free-form comments, a checklist of binary verifiable checks (does the diff touch the right file? does the test actually fail without the fix?). That would make the alignment score much more precise and give a cleaner training signal.

---

## Results

### explosion/radicli — full run (3 cycles, 4 issues/cycle, 3 held-out)

| Cycle | Avg Reward | Test Pass Rate | Resolve ≤2r | Alignment | Hack Rate | Held-Out Reward |
|-------|-----------|----------------|-------------|-----------|-----------|-----------------|
| 1     | 0.821     | 0.992          | 0.500       | 0.464     | 0.000     | 0.527           |
| 2     | 0.450     | 0.990          | 0.500       | 0.383     | **0.500** | 0.759           |
| 3     | 0.754     | 0.746          | **0.750**   | 0.572     | 0.000     | **0.795**       |

**Held-out reward improved +51% from cycle 1 to cycle 3** (0.527 → 0.795) — the key generalization metric since held-out issues were never seen during training.

The cycle 2 reward hacking spike (0.500) is instructive: the judge caught 3 attempts where the coder wrote detailed descriptions of fixes that weren't in the diff. All three were zeroed and added to LEARNED_PATTERNS. By cycle 3 hacking dropped back to 0.000 and held-out reward hit its peak.

Cycle 3's lower `avg_test_pass_rate` (0.746 vs 0.990) reflects two patches that failed to apply cleanly — both involved nested function context in `get_list_converter`. With only 4 issues per cycle, one patch failure is a 25% hit on the average. The held-out trend is the more reliable signal.

**Sample resolved issue — cycle 1, round 1:**

| Metric | Value |
|--------|-------|
| Issue | List converter should ignore empty segments from extra commas |
| Oracle reward | **0.907** |
| Test pass rate | **1.00** (127/127) |
| Tests added | **5** |
| Judge score | **0.95** |
| Resolved in | **1 round** |
| Reward hacking | **0.000** |

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
