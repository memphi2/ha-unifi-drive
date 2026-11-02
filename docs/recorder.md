# Recorder And Database Growth

UNAS keeps live data available independently of Recorder history. The integration
does not impose a database size limit or change your global Recorder settings.

## History Profiles

- Full: keep the default enabled sensors recorded.
- Reduced detail: exclude read/write throughput and other high-frequency detail
  sensors whose history you do not need. Capacity and storage-health history
  remain useful even when throughput graphs are omitted.

Merge exclusions into your existing `recorder` configuration, not a second block.
Use the actual entity IDs from your installation. These are examples for the
default English device name:

```yaml
recorder:
  exclude:
    entities:
      - sensor.unas_read_throughput
      - sensor.unas_write_throughput
```

Excluded entities remain usable live but stop creating new history/statistics.
Existing history is not removed by adding an exclusion. Disabling an entity is
different: it removes its live state as well.

## What Is Tested

`tests/test_recorder_runtime.py` uses real Home Assistant entities and Recorder
with disposable SQLite storage. It checks identical refreshes, changing
throughput, full/reduced history, cached offline readings, recovery and snapshot
control attribute deduplication. No running HA database or NAS is contacted.

These are bounded regression tests, not a wall-clock soak or a guarantee of disk
usage. Snapshot attributes excluded from recording can still trigger state rows
when their live values change. Longer commit intervals batch commits, not state
changes. Keep automatic purging enabled; long-term statistics require a separate
retention decision. Monitor actual database size and filesystem free space,
including room for backups, WAL files and repacking.
