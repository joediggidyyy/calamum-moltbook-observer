import os
import time
import logging
import requests  # ACTIVATED: Operation Live Wire
from abc import ABC, abstractmethod
from typing import Dict, Any, Generator, Iterable, List


DEFAULT_MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"


def _payload_items(data: Dict[str, Any], keys: Iterable[str]) -> List[Dict[str, Any]]:
    for key in keys:
        value = data.get(str(key), [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _normalize_feed_item(item: Dict[str, Any]) -> Dict[str, Any]:
    author_block = item.get("author", {})
    author_dict = author_block if isinstance(author_block, dict) else {}
    author_token = _first_text(
        item.get("author_id"),
        author_dict.get("id"),
        author_dict.get("name"),
        author_block,
    ) or "unknown"

    return {
        "id": item.get("id"),
        "timestamp": _first_text(item.get("timestamp"), item.get("created_at"), item.get("createdAt")),
        "type": _first_text(item.get("type")) or "post",
        "author": author_token,
        "content": _first_text(item.get("content")),
        "tags": _string_list(item.get("tags")),
        "mentions": _string_list(item.get("mentions")),
    }


def _normalize_notification_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "id": item.get("id"),
        "timestamp": _first_text(item.get("timestamp"), item.get("created_at"), item.get("createdAt")),
        "event_type": _first_text(item.get("event_type"), item.get("type")) or "unknown",
        "sender": _first_text(
            item.get("sender"),
            item.get("sender_id"),
            item.get("agentId"),
            item.get("agent_id"),
        ) or "unknown",
    }
    content = _first_text(item.get("content"))
    if content:
        normalized["content"] = content
    return normalized

class MoltbookClientInterface(ABC):
    @abstractmethod
    def fetch_feed(self, limit: int = 10) -> Generator[Dict[str, Any], None, None]:
        pass

    @abstractmethod
    def fetch_notifications(self) -> Generator[Dict[str, Any], None, None]:
        pass

class MoltbookAPIClient(MoltbookClientInterface):
    """
    Real API Client for Moltbook.
    Enforces READ-ONLY safety at the code level.
    """
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "CalamumObserver/1.0 (Research)"
        })
        
    def _safe_get(self, endpoint: str, params: Dict = None) -> Dict:
        """
        The ONLY allowed method. No POST/PUT/DELETE support exists in this class.
        """
        if not self.session:
            raise RuntimeError("Client session not initialized")
            
        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"Network error on {endpoint}: {e}")
            return {}

    def fetch_feed(self, limit: int = 10) -> Generator[Dict[str, Any], None, None]:
        data = self._safe_get("feed", params={"limit": limit})
        for item in _payload_items(data, ("posts", "items")):
            yield _normalize_feed_item(item)

    def fetch_notifications(self) -> Generator[Dict[str, Any], None, None]:
        # 'since' parameter would be managed by state tracking in a real impl
        data = self._safe_get("notifications") 
        for note in _payload_items(data, ("notifications", "items")):
            yield _normalize_notification_item(note)

class MockMoltbookClient(MoltbookClientInterface):
    """
    Simulation client for testing/dreaming.
    """
    def fetch_feed(self, limit: int = 10):
        # Reusing the logic from the original sampler, moved here later
        yield {"type": "mock_post", "content": "simulation", "author": "sim_user"}

    def fetch_notifications(self):
        yield {"type": "mock_dm", "content": "simulation", "sender": "sim_bot"}
