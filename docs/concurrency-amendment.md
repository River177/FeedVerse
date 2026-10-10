# Four-worker scheduling amendment

On 2026-10-10 the user explicitly selected four workers. The existing experiment
was drained at an Agent-generation boundary and resumed with scheduler commit
`05d4209081f902c277c2a18d08eb952905d347df`. The frozen experiment release remains
`d92140902a6199c939c4a8a366a428d047b3f0f8`: task worker, model, configuration,
strategy, data, per-attempt CPU/memory/time/request limits and evaluator are unchanged.

132 evaluated receipts, including calibration, were checked against their original
state and score after cutover. No duplicate attempt identities were found. Submitted
work is independently re-evaluated when necessary; finished task generations are not
discarded. The remote amendment contains the preserved receipt list and timestamp.

Four attempt pipelines can run concurrently. Each owns a separate SQLite connection,
workspace, AGH home and session. Dependency builds are serialized to limit host-wide
package installation contention. Every container retains its 8-CPU and 24-GiB cap.
Concurrency may affect timeouts and API throttling; it is a reported protocol amendment,
not an invisible change to scientific conditions.

Early observation: four tasks were active together; aggregate resource consumption
was below host capacity. The first four model requests received upstream HTTP 429,
followed by successful requests under AGH's existing recovery. The observation then
contained 16 completed requests, four HTTP 429 receipts and one transport error.
These are retained in request accounting; unlimited total budget does not remove the
32-physical-request cap per task.

Commit `65a79e7` additionally implements gateway-level bounded backoff (at most three
retries for 429/502/503/504, counted individually). It has not replaced the active
gateway during in-flight requests. The current scheduler/gateway identity remains
`05d4209`, pending a safe restart if recurring errors require that recovery change.

Eight local tests pass, including four-worker bounded dispatch and stopping new
dispatch after a failing job. Real remote readback confirms four active attempts;
speedup and final completion time still require a longer throughput observation.
