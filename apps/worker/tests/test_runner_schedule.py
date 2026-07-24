from aemet_radar.runner import run_periodically


def test_periodic_runner_uses_fixed_start_interval() -> None:
    cycles: list[int] = []
    sleeps: list[float] = []
    clock_values = iter([0.0, 1.0, 11.0])

    completed = run_periodically(
        lambda: cycles.append(len(cycles) + 1),
        interval_seconds=10,
        max_cycles=3,
        monotonic=lambda: next(clock_values),
        sleeper=sleeps.append,
    )

    assert completed == 3
    assert cycles == [1, 2, 3]
    assert sleeps == [9.0, 9.0]
