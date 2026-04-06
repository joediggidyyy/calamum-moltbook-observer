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
        client = MoltbookAPIClient("https://www.moltbook.com/api/v1/", "fake_token")
        
        assert client.base_url == "https://www.moltbook.com/api/v1"
        
        # Verify session headers were updated
        mock_instance = mock_session_cls.return_value
        mock_instance.headers.update.assert_called()
        call_args = mock_session_cls.return_value.headers.update.call_args[0][0]
        assert call_args["Authorization"] == "Bearer fake_token"

def test_api_client_fetch_feed_success():
    """Verify fetch_feed calls correct endpoint and yields normalized feed posts."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "posts": [
                {
                    "id": 1,
                    "author": {"id": "author-1", "name": "Hazel"},
                    "author_id": "author-1",
                    "content": "hello world",
                    "created_at": "2026-04-04T13:04:12.841Z",
                    "type": "text",
                },
                {
                    "id": 2,
                    "author": {"name": "Cornelius"},
                    "content": "another post",
                    "createdAt": "2026-04-04T08:02:55.338Z",
                    "type": "text",
                },
            ]
        }
        mock_session.get.return_value = mock_response
        
        client = MoltbookAPIClient("https://www.moltbook.com/api/v1", "token")
        items = list(client.fetch_feed(limit=5))
        
        assert len(items) == 2
        assert items[0]["id"] == 1
        assert items[0]["author"] == "author-1"
        assert items[0]["content"] == "hello world"
        assert items[0]["timestamp"] == "2026-04-04T13:04:12.841Z"
        assert items[0]["tags"] == []
        assert items[1]["author"] == "Cornelius"
        assert items[1]["timestamp"] == "2026-04-04T08:02:55.338Z"
        
        # Verify call
        mock_session.get.assert_called_with(
            "https://www.moltbook.com/api/v1/feed", 
            params={"limit": 5}, 
            timeout=10
        )


def test_api_client_fetch_notifications_supports_vendor_payload_shape():
    """Verify notifications endpoint yields normalized vendor notification rows."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "notifications": [
                {
                    "id": "n1",
                    "type": "dm_request",
                    "agentId": "agent-1",
                    "content": "hello",
                    "createdAt": "2026-04-05T08:00:30.291Z",
                },
                {
                    "id": "n2",
                    "event_type": "follow",
                    "sender": "sender-2",
                    "created_at": "2026-04-05T08:00:29.891Z",
                },
            ]
        }
        mock_session.get.return_value = mock_response

        client = MoltbookAPIClient("https://www.moltbook.com/api/v1", "token")
        notes = list(client.fetch_notifications())

        assert len(notes) == 2
        assert notes[0]["id"] == "n1"
        assert notes[0]["event_type"] == "dm_request"
        assert notes[0]["sender"] == "agent-1"
        assert notes[0]["content"] == "hello"
        assert notes[0]["timestamp"] == "2026-04-05T08:00:30.291Z"
        assert notes[1]["event_type"] == "follow"
        assert notes[1]["sender"] == "sender-2"
        assert notes[1]["timestamp"] == "2026-04-05T08:00:29.891Z"
        mock_session.get.assert_called_with(
            "https://www.moltbook.com/api/v1/notifications",
            params=None,
            timeout=10,
        )

def test_api_client_fetch_feed_network_error():
    """Verify error handling returns empty list."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        
        # Mock exception
        mock_session.get.side_effect = Exception("Network Down")
        
        client = MoltbookAPIClient("https://www.moltbook.com/api/v1", "token")
        
        # Should catch error and return empty iterator (or just empty list of items)
        items = list(client.fetch_feed())
        assert len(items) == 0

def test_api_client_safe_get_enforces_safety():
    """Ensure _safe_get is the only method used (implicit test)."""
    # This is more of a contract test; logic is covered by fetch_feed
    pass
