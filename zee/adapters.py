"""Extension boundary for future, hardware-verified read-only telemetry adapters."""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Telemetry:
    adapter: str
    measured_at: float
    metrics: dict[str, float | str | None]
    limitations: tuple[str, ...] = ()

class ReadOnlyAdapter(Protocol):
    def fetch(self, host: str, profile_reference: str) -> Telemetry:
        """Never alter routes, reboot a device or write configuration."""
        ...

ADAPTERS: dict[str, type] = {}
# Intentionally empty. Target models/firmware and secure credential storage must
# be verified before registering a real router or airOS telemetry implementation.
