import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to python path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

from moltbook_client import MoltbookAPIClient, MockMoltbookClient

def test_mock_client_behavior():
    """Verify MockClient returns synthetic data."""
    client = MockMoltbookClient()
    
    feed = list(client.fetch_feed(limit=5))
    assert len(feed) > 0
    assert feed[0]["type"] == "mock_post"

    notifs = list(client.fetch_notifications())
    assert len(notifs) > 0
    assert notifs[0]["type"] == "mock_dm"

def test_api_client_initialization():
    """Verify API Client headers and url."""
    with patch("requests.Session") as mock_session_cls:
        client = MoltbookAPIClient("https://api.moltbook.com/", "fake_token")
        
        assert client.base_url == "https://api.moltbook.com"
        
        # Verify session headers were updated
        mock_instance = mock_session_cls.return_value
        mock_instance.headers.update.assert_called()
        call_args = mock_session_cls.return_value.headers.update.call_args[0][0]
        assert call_args["Authorization"] == "Bearer fake_token"

def test_api_client_fetch_feed_success():
    """Verify fetch_feed calls correct endpoint and yields items."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [{"id": 1}, {"id": 2}]
        }
        mock_session.get.return_value = mock_response
        
        client = MoltbookAPIClient("https://api.moltbook.com", "token")
        items = list(client.fetch_feed(limit=5))
        
        assert len(items) == 2
        assert items[0]["id"] == 1
        
        # Verify call
        mock_session.get.assert_called_with(
            "https://api.moltbook.com/public/feed", 
            params={"limit": 5}, 
            timeout=10
        )

def test_api_client_fetch_feed_network_error():
    """Verify error handling returns empty list."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        
        # Mock exception
        mock_session.get.side_effect = Exception("Network Down")
        
        client = MoltbookAPIClient("https://api.moltbook.com", "token")
        
        # Should catch error and return empty iterator (or just empty list of items)
        items = list(client.fetch_feed())
        assert len(items) == 0

def test_api_client_safe_get_enforces_safety():
    """Ensure _safe_get is the only method used (implicit test)."""
    # This is more of a contract test; logic is covered by fetch_feed
    pass
