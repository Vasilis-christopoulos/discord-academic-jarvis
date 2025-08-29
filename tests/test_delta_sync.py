# tests/test_delta_sync.py
import pytest
import asyncio
import datetime as dt
import pytz
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call
from langchain_core.documents import Document
from googleapiclient.errors import HttpError

from calendar_module.delta_sync import (
    delta_sync_calendar, 
    delta_sync_tasks,
    barrier,
    safe_delete,
    _extract_vectors
)


@pytest.fixture
def mock_context():
    return {
        "calendar_id": "test_calendar@example.com",
        "tasklist_id": "test_tasklist_id",
        "timezone": "America/Toronto",
        "guild_id": "123456789",
        "name": "test-channel"
    }


@pytest.fixture
def mock_calendar_event():
    return {
        "id": "event_123",
        "summary": "Test Meeting",
        "description": "Important meeting description",
        "location": "Conference Room A",
        "start": {"dateTime": "2025-05-30T10:00:00-04:00"},
        "end": {"dateTime": "2025-05-30T11:00:00-04:00"},
        "status": "confirmed"
    }


@pytest.fixture
def mock_task():
    return {
        "id": "task_123",
        "title": "Complete project at 5pm",
        "notes": "Important task notes",
        "due": "2025-05-30T00:00:00.000Z",
        "status": "needsAction"
    }


class TestExtractVectors:
    def test_extract_vectors_dict_response(self):
        """Test extracting vectors from dict response."""
        resp = {"vectors": {"id1": {"values": [0.1, 0.2]}, "id2": {"values": [0.3, 0.4]}}}
        result = _extract_vectors(resp)
        assert result == {"id1": {"values": [0.1, 0.2]}, "id2": {"values": [0.3, 0.4]}}

    def test_extract_vectors_object_with_vectors_attr(self):
        """Test extracting vectors from object with vectors attribute."""
        mock_resp = Mock()
        mock_resp.vectors = {"id1": {"values": [0.1, 0.2]}}
        result = _extract_vectors(mock_resp)
        assert result == {"id1": {"values": [0.1, 0.2]}}

    def test_extract_vectors_object_with_to_dict(self):
        """Test extracting vectors from object with to_dict method."""
        mock_resp = Mock()
        mock_resp.vectors = None
        mock_resp.to_dict.return_value = {"vectors": {"id1": {"values": [0.1, 0.2]}}}
        
        # When hasattr(resp, "vectors") is True but vectors is None/falsy,
        # it should return {} based on the `return resp.vectors or {}` logic
        result = _extract_vectors(mock_resp)
        assert result == {}  # Because resp.vectors is None, so `None or {}` returns {}

    def test_extract_vectors_fallback_empty(self):
        """Test fallback to empty dict when extraction fails."""
        mock_resp = Mock()
        mock_resp.vectors = None
        mock_resp.to_dict.side_effect = Exception("Failed")
        result = _extract_vectors(mock_resp)
        assert result == {}


class TestBarrier:
    @pytest.mark.asyncio
    async def test_barrier_wait_for_presence(self):
        """Test barrier waiting for vectors to be present."""
        mock_store = Mock()
        mock_index = Mock()
        mock_store._index = mock_index
        
        # First call returns empty, second call returns vectors
        mock_index.fetch.side_effect = [
            {"vectors": {}},  # First call: vectors not present
            {"vectors": {"id1": {"values": [0.1]}, "id2": {"values": [0.2]}}}  # Second call: vectors present
        ]
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await barrier(mock_store, ["id1", "id2"], gone=False, pause=0.01)
            mock_sleep.assert_called_once_with(0.01)

    @pytest.mark.asyncio
    async def test_barrier_wait_for_absence(self):
        """Test barrier waiting for vectors to be absent."""
        mock_store = Mock()
        mock_index = Mock()
        mock_store._index = mock_index
        
        # First call returns vectors, second call returns empty
        mock_index.fetch.side_effect = [
            {"vectors": {"id1": {"values": [0.1]}}},  # First call: vectors present
            {"vectors": {}}  # Second call: vectors absent
        ]
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await barrier(mock_store, ["id1", "id2"], gone=True, pause=0.01)
            mock_sleep.assert_called_once_with(0.01)

    @pytest.mark.asyncio
    async def test_barrier_invalid_store(self):
        """Test barrier with invalid store raises TypeError."""
        mock_store = Mock()
        # Remove both possible index attributes
        del mock_store._index
        del mock_store._pinecone_index
        
        with pytest.raises(TypeError, match="barrier\\(\\) expected a PineconeVectorStore"):
            await barrier(mock_store, ["id1"], gone=False)


class TestSafeDelete:
    def test_safe_delete_success(self):
        """Test successful vector deletion."""
        mock_store = Mock()
        mock_store.delete = Mock()
        
        safe_delete(mock_store, ["id1", "id2"])
        
        mock_store.delete.assert_called_once_with(ids=["id1", "id2"], async_req=False)

    def test_safe_delete_empty_ids(self):
        """Test safe delete with empty IDs list."""
        mock_store = Mock()
        mock_store.delete = Mock()
        
        safe_delete(mock_store, [])
        
        mock_store.delete.assert_not_called()

    def test_safe_delete_not_found_exception(self):
        """Test safe delete handles NotFoundException gracefully."""
        from pinecone.openapi_support.exceptions import NotFoundException
        
        mock_store = Mock()
        mock_store.delete.side_effect = NotFoundException("Not found")
        
        # Should not raise exception
        safe_delete(mock_store, ["id1"])

    def test_safe_delete_general_exception(self):
        """Test safe delete handles general exceptions gracefully."""
        mock_store = Mock()
        mock_store.delete.side_effect = Exception("Connection error")
        
        # Should not raise exception
        safe_delete(mock_store, ["id1"])


class TestDeltaSyncCalendar:
    @pytest.mark.asyncio
    async def test_delta_sync_calendar_success(self, mock_context, mock_calendar_event):
        """Test successful calendar delta sync."""
        with patch('calendar_module.delta_sync.get_calendar_sync_token', return_value="test_token"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock) as mock_creds, \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock) as mock_barrier, \
             patch('calendar_module.delta_sync.set_calendar_sync_token') as mock_set_token:
            
            # Setup mocks
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            mock_events.list.return_value.execute.return_value = {
                "items": [mock_calendar_event],
                "nextSyncToken": "new_sync_token"
            }
            mock_build.return_value = mock_service
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await delta_sync_calendar(mock_context)
            
            # Verify API calls
            mock_events.list.assert_called_once_with(
                calendarId="test_calendar@example.com",
                syncToken="test_token",
                showDeleted=True,
                pageToken=None
            )
            
            # Verify document creation and storage
            mock_store.add_documents.assert_called_once()
            args, kwargs = mock_store.add_documents.call_args
            docs = args[0]
            assert len(docs) == 1
            assert docs[0].metadata["id"] == "event_123"
            assert docs[0].metadata["type"] == "event"
            assert "Test Meeting" in docs[0].page_content
            
            # Verify sync token update
            mock_set_token.assert_called_once_with("new_sync_token")

    @pytest.mark.asyncio
    async def test_delta_sync_calendar_cancelled_event(self, mock_context):
        """Test delta sync handles cancelled events."""
        cancelled_event = {
            "id": "cancelled_event",
            "status": "cancelled"
        }
        
        with patch('calendar_module.delta_sync.get_calendar_sync_token', return_value="test_token"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.safe_delete') as mock_safe_delete, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock):
            
            # Setup mocks
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            mock_events.list.return_value.execute.return_value = {
                "items": [cancelled_event],
                "nextSyncToken": "new_sync_token"
            }
            mock_build.return_value = mock_service
            
            mock_store = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await delta_sync_calendar(mock_context)
            
            # Verify deletion
            mock_safe_delete.assert_called_once_with(mock_store, ["cancelled_event"])


class TestDeltaSyncTasks:
    @pytest.mark.asyncio
    async def test_delta_sync_tasks_with_time_parsing(self, mock_context):
        """Test task sync with time parsing from title."""
        task_with_time = {
            "id": "task_123",
            "title": "Meeting at 3:30pm",
            "notes": "Important task",
            "due": "2025-05-30T00:00:00.000Z"
        }
        
        with patch('calendar_module.delta_sync.get_tasks_last_updated', return_value="2025-05-29T00:00:00Z"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.set_tasks_last_updated') as mock_set_updated:
            
            # Setup mocks
            mock_service = Mock()
            mock_tasks = Mock()
            mock_service.tasks.return_value = mock_tasks
            mock_tasks.list.return_value.execute.return_value = {
                "items": [task_with_time]
            }
            mock_build.return_value.tasks.return_value = mock_tasks
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await delta_sync_tasks(mock_context)
            
            # Verify document creation
            mock_store.add_documents.assert_called_once()
            args, kwargs = mock_store.add_documents.call_args
            docs = args[0]
            assert len(docs) == 1
            assert docs[0].metadata["id"] == "task_123"
            assert docs[0].metadata["type"] == "task"
            assert "Meeting at 3:30pm" in docs[0].page_content

    @pytest.mark.asyncio
    async def test_delta_sync_tasks_no_due_date(self, mock_context):
        """Test task sync with tasks that have no due date."""
        floating_task = {
            "id": "floating_task",
            "title": "Someday task",
            "notes": "No deadline"
        }
        
        with patch('calendar_module.delta_sync.get_tasks_last_updated', return_value="2025-05-29T00:00:00Z"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock):
            
            # Setup mocks
            mock_service = Mock()
            mock_tasks = Mock()
            mock_service.tasks.return_value = mock_tasks
            mock_tasks.list.return_value.execute.return_value = {
                "items": [floating_task]
            }
            mock_build.return_value.tasks.return_value = mock_tasks
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await delta_sync_tasks(mock_context)
            
            # Verify document creation for floating task
            mock_store.add_documents.assert_called_once()
            args, kwargs = mock_store.add_documents.call_args
            docs = args[0]
            assert len(docs) == 1
            assert docs[0].metadata["id"] == "floating_task"
            assert docs[0].metadata["type"] == "task"
            # Should not have start_dt or end_dt for floating tasks
            assert "start_dt" not in docs[0].metadata or docs[0].metadata["start_dt"] is None

    @pytest.mark.asyncio
    async def test_delta_sync_tasks_completed_deleted(self, mock_context):
        """Test task sync handles completed/deleted tasks."""
        completed_task = {
            "id": "completed_task",
            "title": "Done task",
            "status": "completed"
        }
        
        deleted_task = {
            "id": "deleted_task",
            "title": "Deleted task",
            "deleted": True
        }
        
        with patch('calendar_module.delta_sync.get_tasks_last_updated', return_value="2025-05-29T00:00:00Z"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.safe_delete') as mock_safe_delete, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock):
            
            # Setup mocks
            mock_service = Mock()
            mock_tasks = Mock()
            mock_service.tasks.return_value = mock_tasks
            mock_tasks.list.return_value.execute.return_value = {
                "items": [completed_task, deleted_task]
            }
            mock_build.return_value.tasks.return_value = mock_tasks
            
            mock_store = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await delta_sync_tasks(mock_context)
            
            # Verify both tasks are deleted
            mock_safe_delete.assert_called_once_with(mock_store, ["completed_task", "deleted_task"])


class TestDeltaSyncErrorHandling:
    @pytest.mark.asyncio
    async def test_delta_sync_calendar_upsert_error(self, mock_context, mock_calendar_event):
        """Test delta sync handles upsert errors gracefully."""
        with patch('calendar_module.delta_sync.get_calendar_sync_token', return_value="test_token"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock):
            
            # Setup mocks
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            mock_events.list.return_value.execute.return_value = {
                "items": [mock_calendar_event],
                "nextSyncToken": "new_sync_token"
            }
            mock_build.return_value = mock_service
            
            mock_store = Mock()
            mock_store.add_documents.side_effect = Exception("Pinecone error")
            mock_get_store.return_value = mock_store
            
            # Should not raise exception
            await delta_sync_calendar(mock_context)

    @pytest.mark.asyncio
    async def test_delta_sync_tasks_upsert_error(self, mock_context, mock_task):
        """Test task delta sync handles upsert errors gracefully."""
        with patch('calendar_module.delta_sync.get_tasks_last_updated', return_value="2025-05-29T00:00:00Z"), \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock):
            
            # Setup mocks
            mock_service = Mock()
            mock_tasks = Mock()
            mock_service.tasks.return_value = mock_tasks
            mock_tasks.list.return_value.execute.return_value = {
                "items": [mock_task]
            }
            mock_build.return_value.tasks.return_value = mock_tasks
            
            mock_store = Mock()
            mock_store.add_documents.side_effect = Exception("Pinecone error")
            mock_get_store.return_value = mock_store
            
            # Should not raise exception
            await delta_sync_tasks(mock_context)


class TestDeltaSyncCalendarErrorHandling:
    """Test error handling scenarios in delta_sync_calendar."""

    @pytest.mark.asyncio
    async def test_delta_sync_calendar_http_410_error(self, mock_context):
        """Test calendar delta sync handles HTTP 410 (sync token expired) correctly."""
        with patch('calendar_module.delta_sync.get_calendar_sync_token', return_value="expired_token"), \
             patch('calendar_module.delta_sync.set_calendar_sync_token') as mock_set_token, \
             patch('calendar_module.delta_sync.get_creds', new_callable=AsyncMock), \
             patch('calendar_module.delta_sync.build') as mock_build, \
             patch('calendar_module.delta_sync.get_vector_store') as mock_get_store, \
             patch('calendar_module.delta_sync.barrier', new_callable=AsyncMock):
            
            # Create a mock HTTP 410 error response
            mock_resp = Mock()
            mock_resp.status = 410
            http_410_error = HttpError(resp=mock_resp, content=b'{"error": {"message": "sync token no longer valid"}}')
            
            # Setup mocks
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            
            # First call raises HTTP 410, second call succeeds (simulating fresh sync)
            mock_events.list.return_value.execute.side_effect = [
                http_410_error,  # First call with expired token
                {"items": [], "nextSyncToken": "new_token"}  # Second call after token reset
            ]
            mock_build.return_value = mock_service
            
            mock_store = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute the function
            await delta_sync_calendar(mock_context)
            
            # Verify that the sync token was reset and function was called recursively
            # Should be called twice: first to reset (None), then to set new token ("new_token")
            expected_calls = [call(None), call("new_token")]
            mock_set_token.assert_has_calls(expected_calls)
            # Should have been called twice: once with expired token (fails), once with empty token (succeeds)
            assert mock_events.list.return_value.execute.call_count == 2
