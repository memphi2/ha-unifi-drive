"""Ensure resource regressions cannot produce a passing soak report."""

from scripts.check_runtime_soak import sample_errors


def samples():
    return [{"phase": phase, "integration_bytes": 100, "rss_bytes": None,
             "tasks": 2, "timers": 2, "listeners": 0, "retained_coordinators": 0,
             "open_sessions": 0, "owned_tasks": 0}
            for phase in ("loaded", "recovered", "unloaded") for _ in range(3)]


def test_soak_requires_samples_and_rejects_resource_growth():
    assert sample_errors([])
    data = samples()
    assert not sample_errors(data)
    data[2]["integration_bytes"] += 1024**2
    assert sample_errors(data)


def test_soak_rejects_leaked_resources_even_without_growth():
    for key in ("listeners", "retained_coordinators", "open_sessions", "owned_tasks"):
        data = samples()
        for item in data:
            if item["phase"] == "unloaded":
                item[key] = 1
        assert sample_errors(data), key
