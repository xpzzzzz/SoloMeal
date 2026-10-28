"""Fail-closed adapter for the hosted Mem0 Platform REST API.

Only confirmed structured preferences are sent; no transcript is sent.
"""
import json
import threading
import time
from dataclasses import dataclass
from http.cookiejar import CookieJar, DefaultCookiePolicy
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx

from ..core.config import Settings
from . import memory_diagnostics as diagnostics


@dataclass(frozen=True)
class MemoryPreference:
    category: str
    target: str
    polarity: int
    id: str = ""


@dataclass(frozen=True)
class MemoryWriteResult:
    state: str
    memory_id: str = ""
    event_id: str = ""
    observed_memory_id: str = ""


@dataclass(frozen=True)
class ReconciliationCandidate:
    user_id: str
    operation_id: str
    preference: MemoryPreference


@dataclass(frozen=True)
class ReconciliationEvidence:
    # Only a provider with a documented authoritative snapshot may set this.
    authoritative: bool
    candidates: tuple = ()
    not_sent: bool = False
    conflict: bool = False


class MemoryReadError(Exception):
    """A management read is unavailable, incomplete, or cannot verify ownership."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _NoCookies(DefaultCookiePolicy):
    """A shared transport must not retain state from another user's response."""

    def set_ok(self, cookie, request):
        return False

    def return_ok(self, cookie, request):
        return False


def _valid(p: MemoryPreference) -> bool:
    if (p.category not in {"ingredient", "cooking_method", "time"}
            or not isinstance(p.target, str) or not p.target.strip()
            or p.target != p.target.strip() or len(p.target) > 80
            or type(p.polarity) is not int or p.polarity not in (-1, 1)):
        return False
    return p.category != "time" or (p.polarity == 1 and p.target.isascii()
                                    and p.target.isdigit() and 1 <= int(p.target) <= 480)


def _encode(p: MemoryPreference) -> str:
    return json.dumps({"schema": "solomeal.preference.v1", "category": p.category,
                       "target": p.target, "polarity": p.polarity}, ensure_ascii=False, separators=(",", ":"))


def _decode(item: object, owner: str) -> MemoryPreference | None:
    if not isinstance(item, dict) or item.get("user_id") != owner:
        return None
    try:
        memory_id = str(UUID(item["id"]))
        data = json.loads(item["memory"])
        if not isinstance(data, dict) or data.get("schema") != "solomeal.preference.v1":
            return None
        p = MemoryPreference(data["category"], data["target"], data["polarity"], memory_id)
        return p if _valid(p) else None
    except (KeyError, TypeError, ValueError):
        return None


class MemoryProvider:
    def __init__(self, settings: Settings, *, transport=None):
        key = settings.mem0_api_key.get_secret_value() if settings.mem0_api_key else ""
        self.enabled = settings.mem0_enabled and bool(key.strip())
        self._key = key
        self._timeout = settings.mem0_timeout_seconds
        self._transport = transport
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        with self._client_lock:
            if self._client is None:
                self._client = httpx.Client(base_url="https://api.mem0.ai", timeout=self._timeout,
                    headers={"Authorization": "Token " + self._key, "Accept": "application/json"},
                    transport=self._transport, follow_redirects=False,
                    cookies=CookieJar(policy=_NoCookies()))
            return self._client

    def close(self):
        """Release this app instance's pool; a subsequent app lifespan may reopen it."""
        with self._client_lock:
            client, self._client = self._client, None
            if client is not None:
                client.close()

    @staticmethod
    def _owner(user_id: str) -> str:
        return "solomeal:" + str(user_id)

    def _request(self, method: str, path: str, **kwargs):
        with diagnostics.duration("client_setup_ms"):
            client = self._get_client()
        diagnostics.increment("http_requests")
        if path == "/v3/memories/search/":
            diagnostics.increment("search_http_requests")
        with diagnostics.duration("http_request_ms", per_request=True):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
        with diagnostics.duration("response_json_ms"):
            return response.json() if response.content else {}

    def _scoped_result(self, row, owner, deadline):
        """Verify absent user_id by single-get under the shared lookup budget."""
        if not isinstance(row, dict):
            raise MemoryReadError("incomplete")
        try:
            memory_id = str(UUID(row["id"]))
        except (KeyError, TypeError, ValueError):
            raise MemoryReadError("incomplete") from None
        actual_owner = row.get("user_id")
        if actual_owner is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MemoryReadError("unavailable")
            diagnostics.increment("ownership_lookups")
            row = self._request("GET", f"/v1/memories/{memory_id}/", timeout=remaining)
            if not isinstance(row, dict) or row.get("id") != memory_id:
                raise MemoryReadError("unverified")
            actual_owner = row.get("user_id")
        if actual_owner != owner:
            raise MemoryReadError("unverified")
        with diagnostics.duration("memory_conversion_ms"):
            return _decode(row, owner)

    def get_preferences(self, user_id: str) -> list[MemoryPreference]:
        if not self.enabled:
            diagnostics.mark(read_status="disabled")
            return []
        owner = self._owner(user_id)
        deadline = time.monotonic() + self._timeout
        try:
            response = self._request("POST", "/v3/memories/search/", json={
                "query": "饮食偏好 食材 烹饪方式 时间 ingredient cooking_method time",
                "filters": {"user_id": owner}, "top_k": 100, "threshold": 0.0,
            })
            results = response.get("results") if isinstance(response, dict) else None
            if not isinstance(results, list):
                diagnostics.mark(read_status="invalid_response")
                return []
            diagnostics.increment("search_results", len(results))
            if len(results) > 100:
                diagnostics.mark(read_status="invalid_response")
                return []
            preferences = [p for row in results if (p := self._scoped_result(row, owner, deadline)) is not None]
            diagnostics.mark(read_status="ok" if preferences else "empty")
            return preferences
        except httpx.TimeoutException as exc:
            phase = ("connect" if isinstance(exc, httpx.ConnectTimeout) else
                     "read" if isinstance(exc, httpx.ReadTimeout) else
                     "write" if isinstance(exc, httpx.WriteTimeout) else
                     "pool" if isinstance(exc, httpx.PoolTimeout) else "other")
            diagnostics.mark(read_status="timeout", timeout_phase=phase)
            return []
        except httpx.HTTPStatusError as exc:
            diagnostics.mark(read_status="rate_limited" if exc.response.status_code == 429 else "unavailable")
            return []
        except MemoryReadError as exc:
            diagnostics.mark(read_status="unverified" if exc.reason == "unverified" else
                             "timeout_budget" if exc.reason == "unavailable" else "invalid_response")
            return []
        except httpx.HTTPError:
            diagnostics.mark(read_status="unavailable")
            return []
        except (ValueError, TypeError):
            diagnostics.mark(read_status="invalid_response")
            return []

    def list_for_management(self, user_id: str) -> list[MemoryPreference] | None:
        """List the owner's records, distinguishing an outage from an empty list."""
        if not self.enabled:
            return None
        owner = self._owner(user_id)
        deadline = time.monotonic() + self._timeout
        preferences = []
        seen = set()
        expected_count = None
        try:
            for page in range(1, 6):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MemoryReadError("unavailable")
                response = self._request("POST", "/v3/memories/", params={"page": page, "page_size": 200},
                                         json={"filters": {"user_id": owner}}, timeout=remaining)
                if (not isinstance(response, dict) or not isinstance(response.get("results"), list)
                        or type(response.get("count")) is not int or response["count"] < 0
                        or "next" not in response or len(response["results"]) > 200):
                    raise MemoryReadError("incomplete")
                count, next_page = response["count"], response["next"]
                if expected_count is None:
                    expected_count = count
                elif count != expected_count:
                    raise MemoryReadError("incomplete")
                for row in response["results"]:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in seen:
                        raise MemoryReadError("incomplete")
                    seen.add(row["id"])
                    p = self._scoped_result(row, owner, deadline)
                    if p is not None:
                        preferences.append(p)
                if next_page is None:
                    if len(seen) != expected_count:
                        raise MemoryReadError("incomplete")
                    return preferences
                if not isinstance(next_page, str) or not response["results"] or len(seen) >= expected_count:
                    raise MemoryReadError("incomplete")
                parsed = urlparse(next_page)
                query = parse_qs(parsed.query)
                if (parsed.scheme != "https" or parsed.netloc != "api.mem0.ai"
                        or parsed.path != "/v3/memories/" or query.get("page") != [str(page + 1)]):
                    raise MemoryReadError("incomplete")
            raise MemoryReadError("incomplete")  # Never expose a truncated list.
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise MemoryReadError("unavailable") from exc

    def add(self, user_id: str, preference: MemoryPreference, *, operation_id=None) -> bool:
        return self.add_confirmed(user_id, preference, operation_id=operation_id).state == "saved"

    def add_confirmed(self, user_id: str, preference: MemoryPreference, *, operation_id=None) -> MemoryWriteResult:
        if not self.enabled or not _valid(preference):
            return MemoryWriteResult("not_sent")
        metadata = {"source": "solomeal_user_confirmed", "schema": "solomeal.preference.v1"}
        if operation_id is not None:
            try:
                metadata["operation_id"] = str(UUID(operation_id))
            except (TypeError, ValueError):
                return MemoryWriteResult("not_sent")
        event_id, memory_id = "", ""
        try:
            result = self._request("POST", "/v3/memories/add/", json={
                "messages": [{"role": "user", "content": _encode(preference)}],
                "user_id": self._owner(user_id), "infer": False,
                "metadata": metadata,
            })
            if isinstance(result, dict):
                try:
                    event_id = str(UUID(result.get("event_id")))
                except (TypeError, ValueError):
                    pass
            rows = result.get("results") if isinstance(result, dict) else None
            if (not isinstance(rows, list) or len(rows) != 1 or (result.get("status") is not None
                                              and result.get("status") != "SUCCEEDED")):
                return MemoryWriteResult("unknown", event_id=event_id)
            for row in rows:
                if isinstance(row, dict) and row.get("event") == "ADD":
                    try:
                        UUID(row["id"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    memory_id = str(UUID(row["id"]))
                    if operation_id is not None:
                        # The write response alone does not attest ownership or metadata.
                        detail = self._request("GET", f"/v1/memories/{memory_id}/")
                        if (not isinstance(detail, dict) or detail.get("id") != memory_id
                                or detail.get("user_id") != self._owner(user_id)
                                or not isinstance(detail.get("metadata"), dict)
                                or detail["metadata"].get("operation_id") != operation_id
                                or _decode(detail, self._owner(user_id)) != MemoryPreference(
                                    preference.category, preference.target, preference.polarity, memory_id)):
                            return MemoryWriteResult("unknown", event_id=event_id, observed_memory_id=memory_id)
                    return MemoryWriteResult("saved", memory_id, event_id)
            return MemoryWriteResult("unknown", event_id=event_id)
        except (httpx.HTTPError, ValueError, TypeError):
            return MemoryWriteResult("unknown", event_id=event_id, observed_memory_id=memory_id)

    def inspect_reconciliation(self, user_id: str, operation_id: str) -> ReconciliationEvidence:
        """Inspect bounded listing plus direct reads, never claim a consistent snapshot.

        The Platform documents asynchronous writes but not a linearizable paginated
        listing. A successful scan therefore cannot prove uniqueness or absence.
        """
        if not self.enabled:
            raise MemoryReadError("unavailable")
        try:
            operation_id = str(UUID(operation_id))
            owner = self._owner(user_id)
            deadline = time.monotonic() + self._timeout
            seen, candidates = set(), []
            expected_count = None
            for page in range(1, 6):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MemoryReadError("unavailable")
                data = self._request("POST", "/v3/memories/", params={"page": page, "page_size": 200},
                                     json={"filters": {"user_id": owner}}, timeout=remaining)
                if (not isinstance(data, dict) or not isinstance(data.get("results"), list)
                        or type(data.get("count")) is not int or data["count"] < 0
                        or "next" not in data or len(data["results"]) > 200):
                    raise MemoryReadError("incomplete")
                if expected_count is None:
                    expected_count = data["count"]
                if data["count"] != expected_count:
                    raise MemoryReadError("incomplete")
                for row in data["results"]:
                    if not isinstance(row, dict):
                        raise MemoryReadError("incomplete")
                    memory_id = str(UUID(row["id"]))
                    if memory_id in seen:
                        raise MemoryReadError("incomplete")
                    seen.add(memory_id)
                    if row.get("user_id") not in (None, owner):
                        raise MemoryReadError("unverified")
                    metadata = row.get("metadata")
                    if isinstance(metadata, dict) and metadata.get("operation_id") == operation_id:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise MemoryReadError("unavailable")
                        detail = self._request("GET", f"/v1/memories/{memory_id}/", timeout=remaining)
                        if (not isinstance(detail, dict) or detail.get("id") != memory_id
                                or detail.get("user_id") != owner):
                            raise MemoryReadError("unverified")
                        detail_metadata = detail.get("metadata")
                        if not isinstance(detail_metadata, dict) or detail_metadata.get("operation_id") != operation_id:
                            return ReconciliationEvidence(False, conflict=True)
                        preference = _decode(detail, owner)
                        if preference is None:
                            return ReconciliationEvidence(False, conflict=True)
                        candidates.append(ReconciliationCandidate(user_id, operation_id, preference))
                next_page = data["next"]
                if next_page is None:
                    if len(seen) != expected_count:
                        raise MemoryReadError("incomplete")
                    return ReconciliationEvidence(False, tuple(candidates), conflict=len(candidates) > 1)
                if not isinstance(next_page, str) or not data["results"] or len(seen) >= expected_count:
                    raise MemoryReadError("incomplete")
                parsed = urlparse(next_page)
                if (parsed.scheme != "https" or parsed.netloc != "api.mem0.ai"
                        or parsed.path != "/v3/memories/" or parse_qs(parsed.query).get("page") != [str(page + 1)]):
                    raise MemoryReadError("incomplete")
            raise MemoryReadError("incomplete")
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise MemoryReadError("unavailable") from exc

    def get_owned(self, user_id: str, memory_id: str) -> MemoryPreference | None:
        """Return None only for an invalid, absent, or definitely foreign record.

        An unavailable or malformed response is not evidence of non-ownership.
        """
        if not self.enabled:
            raise MemoryReadError("unavailable")
        try:
            memory_id = str(UUID(memory_id))
        except (TypeError, ValueError):
            return None
        try:
            item = self._request("GET", f"/v1/memories/{memory_id}/")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise MemoryReadError("unavailable") from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise MemoryReadError("unavailable") from exc
        if not isinstance(item, dict) or item.get("id") != memory_id:
            raise MemoryReadError("unverified")
        owner = item.get("user_id")
        if not isinstance(owner, str) or not owner:
            raise MemoryReadError("unverified")
        if owner != self._owner(user_id):
            return None
        preference = _decode(item, owner)
        if preference is None or preference.id != memory_id:
            raise MemoryReadError("unverified")
        return preference

    def update(self, user_id: str, memory_id: str, preference: MemoryPreference) -> bool:
        if not self.enabled or not _valid(preference):
            return False
        current = self.get_owned(user_id, memory_id)
        if not current:
            return False
        owned = current.id
        try:
            result = self._request("PUT", f"/v1/memories/{owned}/", json={"text": _encode(preference),
                          "metadata": {"source": "solomeal_user_confirmed", "schema": "solomeal.preference.v1"}})
            return (isinstance(result, dict) and result.get("id") == owned
                    and result.get("memory") == _encode(preference)
                    and result.get("user_id") == self._owner(user_id))
        except (httpx.HTTPError, ValueError, TypeError):
            return False

    def delete(self, user_id: str, memory_id: str) -> bool:
        if not self.enabled:
            return False
        current = self.get_owned(user_id, memory_id)
        if not current:
            return False
        owned = current.id
        try:
            result = self._request("DELETE", f"/v1/memories/{owned}/")
            return isinstance(result, dict) and result.get("message") == "Memory deleted successfully!"
        except (httpx.HTTPError, ValueError, TypeError):
            return False


def get_memory_provider(settings: Settings | None = None) -> MemoryProvider:
    return MemoryProvider(settings or Settings())
