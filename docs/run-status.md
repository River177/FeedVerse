# Remote experiment launch receipt

Checked on 2026-10-10 (Asia/Shanghai). This is a launch receipt, not a final result.

- Experiment source commit: `d92140902a6199c939c4a8a366a428d047b3f0f8`.
- Remote root: `/datadisk/agh-rsi` on `gcr-a100`.
- Scientific base image: `sha256:6195bbd430cd7e54d6d1e5639e4e668b479b63cd11986a656ac3b09176b6ba98`.
- Protocol frozen: `/datadisk/agh-rsi/protocol.json`.
- Split: 30 development, 72 holdout; three independent attempts per condition.
- Aggregate budget: unlimited, explicitly authorized by the user.
- Validation: real CSV tool loop and official visual Judge passed; task-3 pilot passed 3/3.
- The complete queue is active. At this check, the development baseline had one evaluated task
  (#1, repeat 1, success=1) and task #2 was running. The baseline contains 90 planned attempts.

The locked supervisor automatically proceeds from the baseline to five proposal/test/confirmation
iterations, then runs the initial and final strategies on the held-out tasks. It stops on
unresolved technical errors and does not turn missing results into passing scores.

The experiment release stays fixed. Later commits adding documentation and database backup
instrumentation do not replace the running experiment code or alter scientific conditions.

The detached local backup worker copies exports and consistent SQLite snapshots, then verifies
their file hashes. 104 exported files were verified at this check; subsequent counts will grow.
It runs while the Mac is awake and connected. Remote task execution is independent of the Mac.

## Read live state

```bash
ssh gcr-a100 'cat /datadisk/agh-rsi/control/supervisor.json'
ssh gcr-a100 'tail -20 /datadisk/agh-rsi/control/experiment.log'
ssh gcr-a100 '/datadisk/agh-rsi/venv/bin/python /datadisk/agh-rsi/releases/d92140902a6199c939c4a8a366a428d047b3f0f8/src/rsi.py --config /datadisk/agh-rsi/releases/d92140902a6199c939c4a8a366a428d047b3f0f8/config/remote.json status'
```

The Mac's verified readback is under `runs/remote-backup/state/`. Final completion is confirmed
only by full coverage, iteration receipts and the final report, with the durable completion receipt.
