from typing import Iterator, Protocol

from app.comparison.domain.comparison import Occurrence
from app.facts.domain.provenance import ProducerExecution


class ComparisonStore(Protocol):
    """Reads of the versioned memory, always scoped to the two analyses compared."""

    def producers(self, scan_id: str) -> dict[str, list[ProducerExecution]]:
        """Each producer of the analysis with its executions; a person has none."""

    def only(self, scan_id: str, other_id: str, producer_id: str) -> dict[str, tuple | None]:
        """Identities of the producer in `scan_id` and not in `other_id`, with their slot (no coverage)."""

    def common(self, before_id: str, after_id: str,
               producer_id: str) -> Iterator[tuple[str, list[Occurrence], list[Occurrence]]]:
        """Identities of the producer on both sides, with their occurrences on each (no coverage)."""

    def labels(self, identity_hashes: list[str]) -> dict[str, str]:
        """What each identity is about: its relation for an assertion, else its kind. Read by identity_hash."""

    def languages(self, scan_id: str) -> tuple[str, ...]:
        """Languages present in an analysis recorded before TAXO-COV-01, read from its WRITTEN_IN facts."""

    def unknown(self, scan_id: str) -> int:
        """Zones the analysis could not interpret (NOT_INTERPRETED, READ_ERROR coverage)."""

    def facts(self, scan_id: str, producer_id: str, identity_hashes: list[str]) -> dict[str, list[dict]]:
        """The facts of these identities in the analysis, rebuilt exactly."""

    def commit(self, scan_id: str, sha: str) -> dict | None:
        """The commit as the analysis recorded it (message, dates, author), or None if it holds no such fact."""
