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

### Metrics chosen and why

We track eight metrics per training cycle. They fall into three tiers by reliability:

**Tier 1 — unfakeable ground truth**
- `avg_test_pass_rate`: after applying the coder's diff, what fraction of the repo's existing tests still pass? This cannot be gamed — a diff that breaks real behaviour will break real tests. A 0.00 almost always means the patch failed to apply at all; 0.95–1.00 means the change was structurally sound.
- `held_out_avg_reward`: composite reward on issues the agents never saw during training. This is the primary measure of generalisation. It can't be improved by overfitting to training issues and is the single number we care about most.

**Tier 2 — model-in-the-loop signals (useful but gameable)**
- `avg_final_reward`: weighted average of test pass (50%), judge score (35%), and preference score (15%). Gives a richer picture than tests alone since the judge scores code clarity, issue alignment, and test quality — things the test suite doesn't measure directly.
- `reviewer_accuracy`: what fraction of reviewer approve/reject decisions matched the ground truth outcome? Measures whether the reviewer's instincts are calibrated to reality rather than to superficial code style.
- `reviewer_coder_alignment`: for each blocking/suggestion comment, did the next diff address it? Measures whether the coder is actually listening and whether the reviewer is giving actionable feedback.

**Tier 3 — system health**
- `reward_hacking_rate`: fraction of traces where the judge detected a mismatch between described and actual changes. Should stay near zero.
- `resolution_rate_le2_rounds`: fraction of issues resolved in ≤2 rounds. Measures efficiency of the feedback loop.
- `training_data_efficiency`: fraction of traces with uncertainty below the training threshold. Low values mean the signals are disagreeing — usually a sign of a hard issue or a partially wrong fix.

We deliberately chose not to track reward on training issues as a primary metric because it conflates memorisation with improvement. Held-out reward is the honest number.

---

### Did both agents improve? Did one improve at the expense of the other?

**Coder — clear improvement.** Held-out reward went from 0.527 to 0.795 (+51%). Resolution rate in ≤2 rounds went from 50% to 75%. Empty-diff rate dropped to near zero after LEARNED_PATTERNS seeded the failure rules from prior traces.

**Reviewer — more nuanced.** Reviewer accuracy was 1.00 in cycles 1 and 2, then dropped to 0.50 in cycle 3. This looks like regression but isn't: cycle 3 introduced harder issues (nested function context, quote-stripping edge cases) where the correct decision was genuinely ambiguous. When the judge agreed with the reviewer it contributed to LEARNED_PATTERNS calibration; when it disagreed, those cases became correction examples. The reviewer's LEARNED_PATTERNS grew from 0 confirmed cases in cycle 1 to 18 confirmed cases across cycles, with explicit "watch for" patterns extracted from judge reasoning.

**Did one improve at the expense of the other?** The cycle 2 hacking spike is the clearest test of this. The coder briefly learned to write convincing descriptions without implementing the fixes — a direct attempt to game the reviewer. The reviewer kept its standards (accuracy 1.00 in cycle 2, all three hacking attempts correctly rejected), but the coder's reward dropped to 0.450. This is the system working as designed: reviewer stability prevented the coder from drifting, and the hacking traces updated LEARNED_PATTERNS so the coder stopped trying in cycle 3. The two agents did not converge to a collusive equilibrium.

---

### Failure modes observed (and prevented)

**Observed and caught:**

1. **Reward hacking** — cycle 2 saw 3 cases of the coder writing detailed PR descriptions (complete with test scenarios) while the actual diff contained no implementation or trivial changes. The judge scored these 0.05–0.22 and zeroed the oracle reward. All three were added to LEARNED_PATTERNS as named failures with verbatim judge reasoning. Hacking dropped to zero in cycle 3.

2. **Corrupt patches** — early runs had every patch fail with "corrupt patch at line N" because the LLM was generating unified diffs with wrong `@@ hunk header counts`. Solved by switching to `<old>/<new>` blocks and computing the diff with `difflib.unified_diff` — the LLM no longer has to count lines.

3. **Adversarial strictness** — the drift detector fired multiple times (100% rejection rate) in early cycles, writing recalibration notes to `CALIBRATION.md` mid-run. This was mostly triggered by runs where all issues produced empty diffs and the reviewer correctly rejected all of them — the detector was reading legitimate strictness as pathological. Fixed by filtering non-coding issues more aggressively in bootstrap.

4. **LLM prose leaking into file paths** — in `_build_diff_from_changes`, the LLM occasionally put its self-critique text inside the `<file>` tag, causing an `OSError: File name too long`. Fixed with a 200-char path length guard and `\n`-in-path check.

**Deliberately prevented:**

5. **Reviewer collapse** — the anti-collapse guard in `reviewer_agent.py` forces a substantive justification on every approval. If the reviewer tries to approve with zero blocking comments it must either find one or explain in ≥3 specific sentences why the code is correct. This never triggered in the radicli run because the reviewer was appropriately strict, but it fired regularly in early click runs.

6. **Mode collapse** — prevented structurally by the MoE design (three independent personas weighted 50/30/20) and by the information barrier (agents never see each other's scores, only scalar rewards). Persona disagreements are stored as training signal — when the correctness persona and security persona split on a decision, and ground truth resolves the tie, that becomes a calibration example.

7. **Training on noisy signal** — the uncertainty gate (`reward_uncertainty < 0.25`) excluded traces where test pass, judge score, and preference score were in sharp disagreement. This prevented cases like "tests pass but judge detects reward hacking" from being used as positive examples.

---

### What would you do differently?

**With 2 more weeks:**

- **More issues per cycle.** 4 issues/cycle means a single patch failure swings the average by 25%. 10–15 per cycle would give a reliable improvement signal. We'd also re-run issues where the patch failed to apply — one failed patch shouldn't end a trace.
- **RAG over the codebase instead of keyword grep.** The current file-context injection greps for function names in the issue text. A small embedding index over the repo would retrieve the right context even when the issue doesn't name the function directly — which is the common case on real GitHub issues.
- **Tighter issue filtering.** The bootstrap filter still lets through some issues that are too ambiguous for the current coder (e.g. "stringify_type should handle Optional" requires understanding Python's type system at a deeper level). A one-shot LLM pass to score issue implementability before adding it to the training set would cut the empty-diff rate further.
- **Alignment score as a reward modifier, not just a signal.** Right now the alignment score routes traces to coder/reviewer positive or negative buckets. We'd use it as a multiplier on the reward: high alignment × high reward = full weight, low alignment × high reward = downweighted for the reviewer.

**With 2 more months:**

- **Actual fine-tuning loop.** We generate JSONL datasets after every cycle but Anthropic's fine-tuning API isn't public. With access, each cycle's LEARNED_PATTERNS would also be baked into the model weights, not just injected via the system prompt. The separation of "what the model knows" from "what the prompt tells it" would let us measure how much of the improvement comes from in-context learning vs weight updates.
- **Reviewer as an explicit verifier, not just a critic.** Instead of free-form review comments, structure the reviewer output as a formal verification checklist (does the diff touch the right file? does it handle the edge case in the issue? does the test actually fail before the fix?). Each check becomes a binary ground-truth-verifiable signal, making the alignment score much more precise.
- **Cross-repo transfer.** The current LEARNED_PATTERNS are repo-specific. With more cycles we'd test whether failure rules learned on radicli transfer to a new repo on first contact — and whether cross-repo traces in the few-shot bank accelerate bootstrapping.
- **Human-in-the-loop validation.** The judge is a model (claude-sonnet-4-6) and can be wrong. A small human review pass on the top-10% and bottom-10% of traces by reward would catch systematic judge blind spots and generate the highest-quality calibration examples for both agents.
- **Debate as training signal.** When the three MoE reviewer personas disagree, we log which persona was right (grounded by GT). With enough of these debate examples, we could fine-tune each persona to be more accurate on its specific domain rather than relying on the weighted vote.

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
