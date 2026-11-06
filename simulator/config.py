"""Shared constants for the incident simulator.

Keeping these in one place means every module (services, faults, generate)
agrees on the fake system's shape and the simulated time window.
"""

from datetime import datetime, timezone

# The five services in our fake e-commerce system.
SERVICES: list[str] = ["web", "cart", "checkout", "db", "cache"]

# Fixed simulation window. Using a fixed calendar date (rather than "now")
# keeps generated incidents reproducible and easy to reason about in tests.
SIM_START: datetime = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
SIM_DURATION_MINUTES: int = 120
METRIC_INTERVAL_MINUTES: int = 1

# Default seed used when none is supplied via the SIMULATOR_SEED env var.
DEFAULT_SEED: int = 42
