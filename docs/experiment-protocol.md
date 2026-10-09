# AGH-RSI v1 protocol

Implementation and commits are created on the Mac; all model-assisted scientific tasks and
official grading run on `gcr-a100`. The user confirmed renewal of that machine and authorized
unlimited aggregate budget and the full experiment after validation. No batch-budget approval
gate remains. Per-attempt resource limits remain equal across strategy conditions.

## Frozen inputs

`config/remote.json` pins AGH, benchmark code, verified annotations, deployment, API version,
reasoning, context window, per-task request/time limits, repetitions and iteration count.
Preparation adds archive/per-file SHA256 hashes, the scientific image ID and its Dockerfile hash.
Deployment records the exact project Git commit. Changing any of these requires a separate
experiment identity; an existing frozen protocol will reject mismatched configuration.

The task model uses Astra Responses with the existing Azure CLI / managed identity chain.
No routine login is required. The bridge records terminal API status and real usage; EOF alone
is not success. Aggregate budget is unlimited; each task has at most 32 physical model requests
and 30 minutes. Missing usage and absent actual price data remain explicit.

## Execution and evaluation

The task Agent is a single AGH session inside Docker, with only its workspace, selected public
dataset directories, AGH installation and its own control/home files mounted. It never receives
reference programs, evaluation scripts, rubrics, other tasks or host OAuth credentials. The AGH
`minimal-rl` preset disables subagents; the external strategy is the only evolved artifact.
The worker grants one-time approvals inside that container, never persistent/global approvals.

After submission, a separate container independently runs the hashed program against task data,
without reference material or evaluator credentials. An evaluation container then consumes those
outputs and calls the unmodified official `eval()` function; it does not run the submitted code.
Dependency image creation follows the official instance Dockerfile. The base image uses upstream
package constraints, with conda-forge preferred in channel configuration.
These environment adaptations are recorded and are not claimed identical to published runs.

Authentication errors stop the queue. Other infrastructure failures have at most two clean
attempt retries, with original failure records retained. Scored failures are never retried to
select a better score. Interrupted attempts are technical missingness, not success. Their partial
artifacts cannot be reused as a new submission.

## Experiment

Shared repositories or dataset folders define connected source groups. Deterministic subset
selection targets 30 development tasks with seed 20261009; the rest are held out. The group
containing pilot task #3 is assigned to development before seeing outcomes. Shared-source grouping
is conservative; the frozen manifest records actual membership and task count.

Three task-#3 pilot attempts follow the CSV tool smoke. Official evaluation must function, but the
Agent is not required to solve every pilot task. Baseline runs three independent attempts per
development task. Each of five iterations proposes one common failure cause and one appended
general instruction, with a separate policy review. The improver receives only development scores
and bounded Agent-owned commands/execution logs; official detailed logs and expected values are
excluded. Every candidate is tested three times per development task.

Accept only if total successes increase, no task's three-run success count decreases, and coverage
is complete. Changed tasks receive three fresh attempts per condition for confirmation, using the
same rule. Rejected candidates retain their evidence. Holdout inputs and outcomes do not influence
strategy selection. Initial and frozen final strategies each run three times on the holdout.

## Reporting and backups

Report each repetition's success rate, then the mean and sample SD; never best-of-three as the
primary result. Preserve technical missingness and provide states, coverage, regressions, usage
and elapsed time. Bootstrap paired holdout differences by source group (10,000 draws, seed
20261009). Do not claim SOTA or significance when the evidence does not support it.

The official visual Judge's prompt, sampling settings (`n=3`) and score parser are preserved.
Its supported Azure path uses the available pinned deployment `gpt-4o_2024-11-20`; this differs
from the source's OpenAI snapshot `gpt-4o-2024-05-13` and is explicitly an evaluation condition,
not a claim of identical published scores. Both strategy conditions use the same Judge.

Every attempt exports its final program, trace, identity, usage, environment and grading receipt.
The requested output is included after independent execution. `scripts/sync.py --watch` copies
exports to the Mac every 45 seconds and independently verifies each exported file's SHA256.
Raw benchmark data and credentials remain excluded from Git. Completion requires full evaluated
coverage, five candidate receipts and the final comparison report, not just a running process.

## Commands

```bash
# Local verification and immutable source deployment
/Users/river/miniforge3/bin/python3.13 -m unittest discover -s tests -v
bash scripts/deploy.sh

# On gcr-a100, using the exact release path printed by deploy.sh
/datadisk/agh-rsi/venv/bin/python RELEASE/src/prepare.py --config RELEASE/config/remote.json
/datadisk/agh-rsi/venv/bin/python RELEASE/src/supervise.py --config RELEASE/config/remote.json
/datadisk/agh-rsi/venv/bin/python RELEASE/src/rsi.py --config RELEASE/config/remote.json status

# On the Mac
python3 scripts/sync.py --watch
```
