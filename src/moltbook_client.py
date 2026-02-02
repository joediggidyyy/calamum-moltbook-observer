import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Generator

# Simulating dependencies for now
try:
    import requests
except ImportError:
    requests = None

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
        self.session = requests.Session() if requests else None
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "CalamumObserver/1.0 (Research)"
        })
        
    def _safe_get(self, endpoint: str, params: Dict = None) -> Dict:
        """
        The ONLY allowed method. No POST/PUT/DELETE support exists in this class.
        """
        if not self.session:
            raise RuntimeError("Request library not installed or client not initialized")
            
        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"Network error on {endpoint}: {e}")
            return {}

    def fetch_feed(self, limit: int = 10) -> Generator[Dict[str, Any], None, None]:
        data = self._safe_get("public/feed", params={"limit": limit})
        for item in data.get("items", []):
            yield item

    def fetch_notifications(self) -> Generator[Dict[str, Any], None, None]:
        # 'since' parameter would be managed by state tracking in a real impl
        data = self._safe_get("notifications") 
        for note in data.get("items", []):
            yield note

class MockMoltbookClient(MoltbookClientInterface):
    """
    Simulation client for testing/dreaming.
    """
    def fetch_feed(self, limit: int = 10):
        # Reusing the logic from the original sampler, moved here later
        yield {"type": "mock_post", "content": "simulation", "author": "sim_user"}

    def fetch_notifications(self):
        yield {"type": "mock_dm", "content": "simulation", "sender": "sim_bot"}
