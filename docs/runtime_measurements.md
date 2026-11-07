# Runtime Resource Measurements

## Metadata Polling

After authentication and the core storage read, independent system, network-I/O
and API-key device-info reads run concurrently in a joined task group. Each has
a 2.5-second timeout; cancellation waits for the child requests to finish cleanup.
Optional endpoint failures do not trigger parallel logins.

Only explicitly static system payloads under API-key authentication are cached
for ten minutes. Unknown fields, live metrics, application lists and status data
prevent caching. Network-I/O and device-info remain live on every poll; optional
backup/fan polling keeps its existing cadence and budget. Explicit refreshes,
connection checks and core connection/authentication failures invalidate the
static cache. An invalidation during an in-flight request is not lost.

Synthetic measurements on the local Python 3.14 test environment:

| Case | Before | After |
| --- | --- | --- |
| Three metadata reads with 40 ms simulated latency each, median of seven samples | 120.9 ms sequential | 40.4 ms concurrent |
| 20 API-key polls at 30 seconds with a static core payload | 80 requests | 61 requests |
| Network-I/O and device-info reads in that request-count case | 20 each | 20 each |

The request-count and cancellation assertions are regression tests in
`tests/test_api_runtime_paths.py`. Elapsed-time results are illustrative, not
machine-dependent CI thresholds or measured NAS/VLAN performance. Dynamic core
payloads still require 80 requests in that example. SQLite Recorder tests verify
that changing disabled cache diagnostics creates no state rows; enabled
diagnostics record changes without duplicated SMART attributes.

## Lifecycle Measurements

HTTP bodies are read in bounded chunks with an 8 MiB decompressed-body limit,
including login, error replies and chunked responses. Oversized responses fail
without including their content in the error. This bounds the integration's
body accumulator, not total process RSS or aiohttp's decompression buffers.

The normal suite runs a short synthetic HA lifecycle measurement. For a longer
run in the same HA test environment:

```bash
python scripts/check_runtime_soak.py --cycles 30 --idle-seconds 1 --refreshes 300 --targets 30 --json-output /tmp/unas-soak.json
```

The runner checks setup, offline/recovery, rotating synthetic snapshot targets,
changing snapshot counts and unload. Target IDs come from a bounded fixture set;
this does not assert that unlimited creation of new NAS targets is cost-free.
Two warmup cycles are excluded. Subsequent comparable phases have explicit limits
for integration allocations, process RSS, tasks, timers and listener counts.
Unload must leave no retained coordinators, open owned sessions or integration
tasks. CPU and elapsed time are reported, not asserted against machine-dependent
timing limits. A missing report fails the runner, including a skipped HA test.

A second measurement keeps one entry loaded throughout distinct-target creation
and repeated polling. Inventory caches must contain only the active target;
registry size and listener count must stop growing when previously seen targets
are reused. Each new target intentionally adds its own entity group. Missing
targets and their entities are retained for existing automations and repairs,
so unlimited new target IDs are not a constant-memory workload. No automatic
entity deletion or changed offline behavior is introduced by this test.

Weekly and manual CI runs retain these synthetic reports for 14 days. This does
not change Recorder settings, statistics or purge behavior; additional retention
testing is deferred pending a separate decision.

The fake API contacts no NAS. This is a bounded synthetic regression check, not
proof of 24-hour live RAM/CPU stability or representative VLAN behavior. Keep
reports outside the repository. Record the tested commit and HA/Python versions
alongside longer measurements. Do not compare absolute RSS between machines.
