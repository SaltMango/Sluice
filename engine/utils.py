from typing import Sequence

def format_speed(bytes_per_second: int) -> str:
    """Format speed values to human readable sizes."""
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
    value = float(bytes_per_second)

    for unit in units[:-1]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} {units[-1]}"

def normalize_linear(values: Sequence[float], minimum: float | None = None, maximum: float | None = None) -> list[float]:
    """Normalize values linearly [0.0 - 1.0]."""
    if not values:
        return []

    min_val = minimum if minimum is not None else min(values)
    max_val = maximum if maximum is not None else max(values)
    
    if max_val <= min_val:
        if max_val > 0 and min_val == 0:
            return [min(max(v / max_val, 0.0), 1.0) for v in values]
        return [0.0] * len(values)

    return [min(max((v - min_val) / (max_val - min_val), 0.0), 1.0) for v in values]

def normalize_inverse(values: Sequence[float]) -> list[float]:
    """Normalize values inversely [0.0 - 1.0] where lowest value gets 1.0."""
    if not values:
        return []

    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [1.0] * len(values)

    span = maximum - minimum
    return [(maximum - value) / span for value in values]

def expand_metric(values: Sequence[int], size: int) -> list[int]:
    """Pad an array to size filling empty with 0s."""
    metric = [0] * size
    for index, value in enumerate(values[:size]):
        metric[index] = int(value)
    return metric
