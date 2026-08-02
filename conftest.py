import os

from hypothesis import HealthCheck, settings

settings.register_profile(
    "mutation",
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
)

if os.environ.get("RUN_MODE") == "MUTATION":
    settings.load_profile("mutation")
