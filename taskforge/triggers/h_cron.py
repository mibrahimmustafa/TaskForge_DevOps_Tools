"""Jenkins-compatible H (hash) notation cron expression parser.

Expands 'H' tokens into deterministic numbers based on a stable hash of a seed
(such as the job ID) so that jobs scheduled at the same interval do not fire
simultaneously, spreading load evenly across the cluster.

Supported notations:
- H: Single pseudo-random value within the full valid range for the field.
- H/step: Interval starting at a pseudo-random offset (offset = min + hash % step).
- H(min-max): Single pseudo-random value within [min, max].
- H(min-max)/step: Interval within [min, max] starting at (min + hash % step).
"""

import hashlib
import re

FIELD_RANGES = [
    (0, 59),  # 0: minute
    (0, 23),  # 1: hour
    (1, 31),  # 2: day of month
    (1, 12),  # 3: month
    (0, 6),  # 4: day of week (0=Sun or Mon depending on cron format, 0-6 valid)
]

H_PATTERN = re.compile(
    r"^H(?:\((?P<min>\d+)-(?P<max>\d+)\))?(?:/(?P<step>\d+))?$",
    re.IGNORECASE,
)


def hash_offset(seed: str, field_idx: int, modulus: int) -> int:
    """Return a deterministic non-negative integer in [0, modulus - 1]."""
    if modulus <= 1:
        return 0
    key = f"{seed}:{field_idx}".encode()
    digest = hashlib.md5(key, usedforsecurity=False).hexdigest()  # nosec B324 - stable pseudo-random hashing
    return int(digest, 16) % modulus


def expand_field(field_str: str, field_idx: int, seed: str) -> str:
    """Expand H tokens in a single cron field or subfield."""
    # Handle comma-separated subfields, e.g. "H(0-15),H(30-45)"
    if "," in field_str:
        subfields = [expand_field(sub, field_idx, seed) for sub in field_str.split(",")]
        return ",".join(subfields)

    match = H_PATTERN.match(field_str.strip())
    if not match:
        return field_str

    f_min_default, f_max_default = FIELD_RANGES[field_idx]
    f_min = int(match.group("min")) if match.group("min") is not None else f_min_default
    f_max = int(match.group("max")) if match.group("max") is not None else f_max_default

    if f_min > f_max:
        raise ValueError(f"Invalid range in H expression: {f_min} > {f_max}")

    step_str = match.group("step")
    if step_str:
        step = int(step_str)
        if step <= 0:
            raise ValueError(f"Step must be positive in H expression: {step}")
        # Offset within the step
        offset = f_min + hash_offset(seed, field_idx, step)
        # Generate all numbers in range [offset, f_max] with step
        values = list(range(offset, f_max + 1, step))
        if not values:
            values = [offset]
        return ",".join(str(v) for v in values)
    else:
        # Single value in [f_min, f_max]
        range_size = f_max - f_min + 1
        value = f_min + hash_offset(seed, field_idx, range_size)
        return str(value)


def expand_jenkins_cron(expr: str, seed: str = "taskforge-default") -> str:
    """Expand a 5-part cron expression with Jenkins H notation into a standard cron expression."""
    expr = expr.strip()
    if not expr:
        return expr

    # Only process if 'h' or 'H' is present
    if "h" not in expr.lower():
        return expr

    parts = expr.split()
    if len(parts) != 5:
        # If not 5 parts, return as-is (e.g. interval or invalid)
        return expr

    expanded_parts = []
    for idx, part in enumerate(parts):
        expanded_parts.append(expand_field(part, idx, seed))

    return " ".join(expanded_parts)
