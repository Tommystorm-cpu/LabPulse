"""Query and reconcile LabPulse identities with Home Assistant's registry."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .data_models import EntityReference, RenderModel


@dataclass(frozen=True)
class RegistryEntry:
    """The registry fields needed to identify one Home Assistant entity."""

    entity_id: str
    platform: str
    unique_id: str
    disabled_by: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RegistryEntry | None:
        """Build an entry when a registry payload contains usable identity fields."""

        entity_id = payload.get("entity_id")
        platform = payload.get("platform")
        unique_id = payload.get("unique_id")
        if not all(isinstance(value, str) and value for value in (entity_id, platform, unique_id)):
            return None
        disabled_by = payload.get("disabled_by")
        return cls(
            entity_id=entity_id,
            platform=platform,
            unique_id=unique_id,
            disabled_by=str(disabled_by) if disabled_by is not None else None,
        )


@dataclass(frozen=True)
class RegistrySnapshot:
    """One authenticated Home Assistant entity-registry response."""

    entries: list[RegistryEntry]
    home_assistant_version: str


@dataclass(frozen=True)
class ResolutionResult:
    """The outcome of resolving one LabPulse registry identity."""

    label: str
    reference: EntityReference


@dataclass
class ResolutionReport:
    """All entity-resolution outcomes from one generator run."""

    results: list[ResolutionResult]
    home_assistant_version: str

    @property
    def failures(self) -> list[ResolutionResult]:
        """Return outcomes that make strict reconciliation unsafe."""

        return [
            result
            for result in self.results
            if result.reference.resolution_status in {"missing", "disabled", "ambiguous"}
        ]

    def replacements(
        self,
        previous_entity_ids: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Map default and previously resolved IDs to current registry IDs."""

        previous_entity_ids = previous_entity_ids or {}
        replacements: dict[str, str] = {}
        for result in self.results:
            reference = result.reference
            if reference.resolution_status not in {"matched", "renamed"}:
                continue
            actual = reference.entity_id
            for old_entity_id in (
                reference.default_entity_id,
                previous_entity_ids.get(reference.unique_id),
            ):
                if old_entity_id and old_entity_id != actual:
                    replacements[old_entity_id] = actual
        return replacements

    def summary(self) -> str:
        """Return a readable report for shell output and failures."""

        counts = Counter(result.reference.resolution_status for result in self.results)
        lines = [f"Home Assistant entity resolution ({self.home_assistant_version}):"]
        for status in ("matched", "renamed", "missing", "disabled", "ambiguous"):
            if counts[status]:
                lines.append(f"  {status}: {counts[status]}")
        for result in self.results:
            reference = result.reference
            if reference.resolution_status == "matched":
                continue
            lines.append(
                f"  {result.label}: {reference.resolution_status} "
                f"(unique_id={reference.unique_id}, "
                f"default={reference.default_entity_id}, "
                f"actual={reference.resolved_entity_id or 'none'})"
            )
        return "\n".join(lines)


class EntityResolutionError(RuntimeError):
    """Raised when strict registry reconciliation cannot resolve every entity."""

    def __init__(self, report: ResolutionReport):
        """Create an error that retains the complete resolution report."""

        super().__init__(report.summary())
        self.report = report


def websocket_url(home_assistant_url: str) -> str:
    """Convert a Home Assistant base URL into its WebSocket API URL."""

    parsed = urlsplit(home_assistant_url)
    scheme = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}.get(
        parsed.scheme
    )
    if scheme is None or not parsed.netloc:
        raise ValueError(f"Invalid Home Assistant URL: {home_assistant_url}")
    path = parsed.path.rstrip("/")
    if not path.endswith("/api/websocket"):
        path += "/api/websocket"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _receive_json(connection: Any) -> dict[str, Any]:
    """Receive and validate one JSON object from a websocket-client connection."""

    raw_message = connection.recv()
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    message = json.loads(raw_message)
    if not isinstance(message, dict):
        raise RuntimeError("Home Assistant returned a non-object WebSocket message")
    return message


def _send_json(connection: Any, message: dict[str, Any]) -> None:
    """Send one JSON object through a websocket-client connection."""

    connection.send(json.dumps(message))


def _default_connector(url: str, timeout: float) -> Any:
    """Open a websocket-client connection, with a useful optional-dependency error."""

    try:
        import websocket
    except ImportError as error:
        raise RuntimeError(
            "Entity resolution needs websocket-client on the host. "
            "Install it with: sudo apt install python3-websocket"
        ) from error
    return websocket.create_connection(url, timeout=timeout)


def fetch_entity_registry(
    home_assistant_url: str,
    access_token: str,
    timeout: float = 10,
    connector: Callable[[str, float], Any] | None = None,
) -> RegistrySnapshot:
    """Authenticate to Home Assistant and fetch its full entity registry."""

    if not access_token:
        raise ValueError("Home Assistant access token is empty")
    connection = (connector or _default_connector)(
        websocket_url(home_assistant_url),
        timeout,
    )
    try:
        auth_required = _receive_json(connection)
        if auth_required.get("type") != "auth_required":
            raise RuntimeError("Home Assistant did not request WebSocket authentication")

        _send_json(connection, {"type": "auth", "access_token": access_token})
        auth_result = _receive_json(connection)
        if auth_result.get("type") != "auth_ok":
            message = auth_result.get("message", "authentication failed")
            raise RuntimeError(f"Home Assistant authentication failed: {message}")

        _send_json(connection, {"id": 1, "type": "config/entity_registry/list"})
        response = _receive_json(connection)
        if response.get("id") != 1 or response.get("type") != "result":
            raise RuntimeError("Home Assistant returned an unexpected registry response")
        if not response.get("success"):
            raise RuntimeError(f"Home Assistant registry query failed: {response.get('error')}")
        payload_entries = response.get("result")
        if not isinstance(payload_entries, list):
            raise RuntimeError("Home Assistant registry response did not contain a list")

        entries = []
        for payload in payload_entries:
            if isinstance(payload, dict) and (entry := RegistryEntry.from_payload(payload)):
                entries.append(entry)
        return RegistrySnapshot(
            entries=entries,
            home_assistant_version=str(auth_result.get("ha_version", "unknown")),
        )
    finally:
        connection.close()


def resolve_model_entities(
    model: RenderModel,
    snapshot: RegistrySnapshot,
    strict: bool = True,
) -> ResolutionReport:
    """Overlay actual registry entity IDs onto the deterministic render model."""

    entries_by_identity: dict[tuple[str, str], list[RegistryEntry]] = defaultdict(list)
    for entry in snapshot.entries:
        entries_by_identity[(entry.platform, entry.unique_id)].append(entry)

    requested_identities = Counter(
        (reference.platform, reference.unique_id)
        for _, reference in model.registry_entities
    )
    results = []
    for label, reference in model.registry_entities:
        identity = (reference.platform, reference.unique_id)
        matches = entries_by_identity.get(identity, [])
        if requested_identities[identity] > 1 or len(matches) > 1:
            reference.resolution_status = "ambiguous"
        elif not matches:
            reference.resolution_status = "missing"
        else:
            match = matches[0]
            reference.resolved_entity_id = match.entity_id
            if match.disabled_by is not None:
                reference.resolution_status = "disabled"
            elif match.entity_id == reference.default_entity_id:
                reference.resolution_status = "matched"
            else:
                reference.resolution_status = "renamed"
        results.append(ResolutionResult(label=label, reference=reference))

    report = ResolutionReport(
        results=results,
        home_assistant_version=snapshot.home_assistant_version,
    )
    if strict and report.failures:
        raise EntityResolutionError(report)
    return report
