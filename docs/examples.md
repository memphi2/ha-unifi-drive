# Automation Examples

## Notify On Storage Problems

```yaml
alias: Notify when UNAS storage needs attention
trigger:
  - platform: state
    entity_id: binary_sensor.unifi_unas_storage_problem
    to: "on"
condition:
  - condition: state
    entity_id: binary_sensor.unifi_unas_device_online
    state: "on"
action:
  - service: notify.mobile_app_phone
    data:
      title: UNAS storage needs attention
      message: Check UniFi Drive diagnostics and pool/drive states.
```

## Wake Before Backup Window

```yaml
alias: Wake UNAS before maintenance
trigger:
  - platform: time
    at: "01:45:00"
action:
  - service: unifi_unas.wake_on_lan
    data:
      entry_id: your_config_entry_id
```

## Snapshot Schedule Update

```yaml
alias: Set weekly snapshot schedule
trigger: []
action:
  - service: unifi_unas.set_snapshot_schedule
    data:
      target_key: mydrive_target_1
      schedule: Weekly
      weekday: Wednesday
      schedule_time: "00:00"
```
