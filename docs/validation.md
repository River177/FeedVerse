# Integration validation, 2026-10-10 (Asia/Shanghai)

The official verified annotation file contains 102 unique tasks. The downloaded
`benchmark_verified.zip` SHA256 is
`46e715d3b2196d459d2dff52aa487f506a95ec44b44262e82208d086ea879610`.
Source grouping produces exactly 30 development and 72 holdout tasks; tasks
18, 19, 27, 40 and 41 share one development group.

The remote CSV smoke independently verified count=3, mean=12 and sample SD=2.
AGH's exported trace contains completed read → write → shell (`python3 solution.py`,
exit 0) → read tool calls. The working profile uses standard with the subagent
capability excluded; the unchanged minimal-rl preset cannot execute shell on this
Linux host without an additional sandbox backend, so it was not selected for the study.

The unmodified official visual Judge returned three parseable scores of 100 for
an identical-image pair through the pinned GPT-4o Azure deployment.

The first task-3 scientific pilot submitted a standalone random-forest program,
independently regenerated the required CSV, and passed the official evaluator
(`data_correctness=True`, `func_correctness=True`, success=1). Its program SHA256 is
`bb5c09250a0e796d3aad0deeee909b47c4b5cfcbf411ad2a927116df02ab9a9a`.
The official evaluator SHA256 is
`f2cdaa7ae91a7849f11d2ad1f365bf8b29f8d8b3cd8ad787f16c12bfde627ea5`.

An initial Docker mount preparation error prevented grading. The adapter was
repaired and the same hashed submission re-evaluated, without regenerating or
editing the solution. The failed grading receipt remains alongside the successful
one. Calibration reuse requires identical declared configuration, worker, initial
strategy and evaluator adapter script; each deployment remains recorded.

Five protocol unit tests passed: physical request accounting including in-flight
and failed calls; scope separation; API terminal-event handling; strict non-regression
and complete coverage; deterministic source grouping without score-based selection.
Python compilation and Node syntax checks also passed. These checks establish
integration validity, not completion of the full research experiment.

Durable evidence lives on GCR under `/datadisk/agh-rsi/exports/` and is copied to
the ignored local `runs/remote-backup/`, where file hashes are independently verified.
