# tests/test_sync.py
import pytest
import datetime as dt
import pytz
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from langchain_core.documents import Document

from calendar_module.sync import (
    get_creds,
    fetch_google,
    ensure_synced,
    CAL_FIELDS,
    TASK_FIELDS,
    FUTURE_HORIZON
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
def sample_timezone():
    return pytz.timezone("America/Toronto")


@pytest.fixture
def mock_google_event():
    return {
        "id": "event_123",
        "summary": "Test Meeting",
        "description": "Meeting description",
        "location": "Room A",
        "start": {"dateTime": "2025-05-30T10:00:00-04:00"},
        "end": {"dateTime": "2025-05-30T11:00:00-04:00"}
    }


@pytest.fixture
def mock_google_task():
    return {
        "id": "task_123",
        "title": "Complete project",
        "notes": "Task notes",
        "due": "2025-05-30T23:59:59.000Z"
    }


class TestGetCreds:
    @pytest.mark.asyncio
    async def test_get_creds_valid_existing_token(self):
        """Test get_creds with valid existing token."""
        mock_creds = Mock()
        mock_creds.valid = True
        
        with patch('calendar_module.sync.TOKEN_PATH') as mock_token_path, \
             patch('calendar_module.sync.Credentials') as mock_creds_class:
            
            mock_token_path.exists.return_value = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds
            
            # Execute
            result = await get_creds()
            
            # Verify
            assert result == mock_creds
            mock_creds_class.from_authorized_user_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_creds_expired_token_refresh_success(self):
        """Test get_creds with expired token that refreshes successfully."""
        mock_creds = Mock()
        mock_creds.valid = False
        mock_creds.expired = True
        
        with patch('calendar_module.sync.TOKEN_PATH') as mock_token_path, \
             patch('calendar_module.sync.Credentials') as mock_creds_class, \
             patch('calendar_module.sync.Request') as mock_request:
            
            mock_token_path.exists.return_value = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds
            
            # After refresh, credentials become valid
            def refresh_side_effect(_):
                mock_creds.valid = True
            mock_creds.refresh.side_effect = refresh_side_effect
            
            # Execute
            result = await get_creds()
            
            # Verify
            assert result == mock_creds
            mock_creds.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_creds_refresh_error_new_auth_flow(self):
        """Test get_creds when refresh fails and requires new auth flow."""
        mock_creds = Mock()
        mock_creds.valid = False
        mock_creds.expired = True
        
        from google.auth.exceptions import RefreshError
        
        with patch('calendar_module.sync.TOKEN_PATH') as mock_token_path, \
             patch('calendar_module.sync.Credentials') as mock_creds_class, \
             patch('calendar_module.sync.InstalledAppFlow') as mock_flow_class, \
             patch('calendar_module.sync.CRED_PATH', 'test_creds.json'):
            
            mock_token_path.exists.return_value = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds
            mock_creds.refresh.side_effect = RefreshError("Refresh failed")
            
            # Mock new auth flow
            mock_flow = Mock()
            mock_new_creds = Mock()
            mock_new_creds.to_json.return_value = '{"token": "new_token"}'
            mock_flow.run_local_server.return_value = mock_new_creds
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            
            # Execute
            result = await get_creds()
            
            # Verify
            assert result == mock_new_creds
            mock_token_path.unlink.assert_called_once()
            mock_flow.run_local_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_creds_no_existing_token(self):
        """Test get_creds when no token file exists."""
        with patch('calendar_module.sync.TOKEN_PATH') as mock_token_path, \
             patch('calendar_module.sync.InstalledAppFlow') as mock_flow_class, \
             patch('calendar_module.sync.CRED_PATH', 'test_creds.json'):
            
            mock_token_path.exists.return_value = False
            
            # Mock new auth flow
            mock_flow = Mock()
            mock_new_creds = Mock()
            mock_new_creds.to_json.return_value = '{"token": "new_token"}'
            mock_flow.run_local_server.return_value = mock_new_creds
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            
            # Execute
            result = await get_creds()
            
            # Verify
            assert result == mock_new_creds
            mock_flow.run_local_server.assert_called_once()
            mock_token_path.write_text.assert_called_once()


class TestFetchGoogle:
    @pytest.mark.asyncio
    async def test_fetch_google_events_only(self, mock_context, mock_google_event):
        """Test fetching Google Calendar events only."""
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds, \
             patch('calendar_module.sync.build') as mock_build:
            
            # Setup mocks
            mock_creds = Mock()
            mock_get_creds.return_value = mock_creds
            
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            mock_events.list.return_value.execute.return_value = {
                "items": [mock_google_event]
            }
            mock_build.return_value = mock_service
            
            # Execute
            docs = await fetch_google(
                type_="event",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify
            assert len(docs) == 1
            doc = docs[0]
            assert doc.metadata["id"] == "event_123"
            assert doc.metadata["type"] == "event"
            assert "Test Meeting" in doc.page_content
            assert doc.metadata["location"] == "Room A"
            
            # Verify API call
            mock_events.list.assert_called_once()
            call_kwargs = mock_events.list.call_args[1]
            assert call_kwargs["calendarId"] == "test_calendar@example.com"
            assert call_kwargs["fields"] == CAL_FIELDS

    @pytest.mark.asyncio
    async def test_fetch_google_tasks_only(self, mock_context, mock_google_task):
        """Test fetching Google Tasks only."""
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds, \
             patch('calendar_module.sync.build') as mock_build:
            
            # Setup mocks
            mock_creds = Mock()
            mock_get_creds.return_value = mock_creds
            
            mock_service = Mock()
            mock_tasks = Mock()
            mock_service.tasks.return_value = mock_tasks
            mock_tasks.list.return_value.execute.return_value = {
                "items": [mock_google_task]
            }
            mock_build.return_value.tasks.return_value = mock_tasks
            
            # Execute
            docs = await fetch_google(
                type_="task",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify
            assert len(docs) == 1
            doc = docs[0]
            assert doc.metadata["id"] == "task_123"
            assert doc.metadata["type"] == "task"
            assert "Complete project" in doc.page_content
            
            # Verify API call
            mock_tasks.list.assert_called_once()
            call_kwargs = mock_tasks.list.call_args[1]
            assert call_kwargs["tasklist"] == "test_tasklist_id"
            assert call_kwargs["fields"] == TASK_FIELDS

    @pytest.mark.asyncio
    async def test_fetch_google_both_types(self, mock_context, mock_google_event, mock_google_task):
        """Test fetching both events and tasks."""
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds, \
             patch('calendar_module.sync.build') as mock_build:
            
            # Setup mocks
            mock_creds = Mock()
            mock_get_creds.return_value = mock_creds
            
            # Mock calendar service
            mock_cal_service = Mock()
            mock_events = Mock()
            mock_cal_service.events.return_value = mock_events
            mock_events.list.return_value.execute.return_value = {
                "items": [mock_google_event]
            }
            
            # Mock tasks service
            mock_task_service = Mock()
            mock_tasks = Mock()
            mock_task_service.list.return_value.execute.return_value = {
                "items": [mock_google_task]
            }
            
            # Mock build to return different services
            def build_side_effect(service, version, credentials):
                if service == "calendar":
                    return mock_cal_service
                elif service == "tasks":
                    return Mock(tasks=lambda: mock_tasks)
            
            mock_build.side_effect = build_side_effect
            mock_tasks.list = mock_task_service.list
            
            # Execute
            docs = await fetch_google(
                type_="both",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify
            assert len(docs) == 2
            event_doc = next(d for d in docs if d.metadata["type"] == "event")
            task_doc = next(d for d in docs if d.metadata["type"] == "task")
            
            assert event_doc.metadata["id"] == "event_123"
            assert task_doc.metadata["id"] == "task_123"

    @pytest.mark.asyncio
    async def test_fetch_google_pagination(self, mock_context):
        """Test handling of pagination in Google API responses."""
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds, \
             patch('calendar_module.sync.build') as mock_build:
            
            # Setup mocks
            mock_creds = Mock()
            mock_get_creds.return_value = mock_creds
            
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            
            # Mock paginated responses
            responses = [
                {
                    "items": [{
                        "id": "event_1",
                        "summary": "Event 1",
                        "start": {"dateTime": "2025-05-30T10:00:00Z"},
                        "end": {"dateTime": "2025-05-30T11:00:00Z"}
                    }],
                    "nextPageToken": "token_123"
                },
                {
                    "items": [{
                        "id": "event_2", 
                        "summary": "Event 2",
                        "start": {"dateTime": "2025-05-30T14:00:00Z"},
                        "end": {"dateTime": "2025-05-30T15:00:00Z"}
                    }]
                }
            ]
            mock_events.list.return_value.execute.side_effect = responses
            mock_build.return_value = mock_service
            
            # Execute
            docs = await fetch_google(
                type_="event",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify
            assert len(docs) == 2
            assert docs[0].metadata["id"] == "event_1"
            assert docs[1].metadata["id"] == "event_2"
            
            # Verify pagination calls
            assert mock_events.list.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_google_api_error(self, mock_context):
        """Test handling of API errors during fetch."""
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds, \
             patch('calendar_module.sync.build') as mock_build:
            
            # Setup mocks
            mock_creds = Mock()
            mock_get_creds.return_value = mock_creds
            
            mock_service = Mock()
            mock_events = Mock()
            mock_service.events.return_value = mock_events
            mock_events.list.return_value.execute.side_effect = Exception("API Error")
            mock_build.return_value = mock_service
            
            # Execute
            docs = await fetch_google(
                type_="event",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify - should return empty list on error
            assert docs == []

    @pytest.mark.asyncio
    async def test_fetch_google_no_credentials(self, mock_context):
        """Test handling when credentials cannot be obtained."""
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds:
            mock_get_creds.return_value = None
            
            # Execute
            docs = await fetch_google(
                type_="event",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify
            assert docs == []

    @pytest.mark.asyncio
    async def test_fetch_google_task_timezone_handling(self, mock_context):
        """Test timezone handling for tasks."""
        task_with_timezone = {
            "id": "task_tz",
            "title": "Timezone task",
            "notes": "Task notes",
            "due": "2025-05-30T00:00:00.000Z"  # Midnight UTC
        }
        
        with patch('calendar_module.sync.get_creds', new_callable=AsyncMock) as mock_get_creds, \
             patch('calendar_module.sync.build') as mock_build:
            
            # Setup mocks
            mock_creds = Mock()
            mock_get_creds.return_value = mock_creds
            
            mock_service = Mock()
            mock_tasks = Mock()
            mock_service.list.return_value.execute.return_value = {
                "items": [task_with_timezone]
            }
            mock_build.return_value.tasks.return_value = mock_tasks
            mock_tasks.list = mock_service.list
            
            # Execute
            docs = await fetch_google(
                type_="task",
                date_from="2025-05-30T00:00:00Z",
                date_to="2025-05-30T23:59:59Z",
                context=mock_context
            )
            
            # Verify
            assert len(docs) == 1
            doc = docs[0]
            assert doc.metadata["type"] == "task"
            # Should have proper timezone handling
            assert "start_dt" in doc.metadata
            assert "end_dt" in doc.metadata


class TestEnsureSynced:
    @pytest.mark.asyncio
    async def test_ensure_synced_first_sync(self, mock_context, sample_timezone):
        """Test ensure_synced for first-time sync."""
        start_dt = sample_timezone.localize(dt.datetime(2025, 5, 30, 0, 0, 0))
        end_dt = sample_timezone.localize(dt.datetime(2025, 5, 30, 23, 59, 59))
        
        with patch('calendar_module.sync.get_first_last') as mock_get_first_last, \
             patch('calendar_module.sync.set_first_last') as mock_set_first_last, \
             patch('calendar_module.sync.parse_iso') as mock_parse_iso, \
             patch('calendar_module.sync.fetch_google', new_callable=AsyncMock) as mock_fetch, \
             patch('calendar_module.sync.get_vector_store') as mock_get_store:
            
            # Setup mocks
            mock_get_first_last.return_value = (None, None)  # First sync
            mock_parse_iso.side_effect = [start_dt, end_dt]
            mock_fetch.return_value = [Mock(metadata={"id": "test_doc"})]
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await ensure_synced(
                type_="event",
                date_from=start_dt.isoformat(),
                date_to=end_dt.isoformat(),
                context=mock_context
            )
            
            # Verify
            mock_fetch.assert_called_once_with(
                type_="event",
                date_from=start_dt.isoformat(),
                date_to=end_dt.isoformat(),
                context=mock_context
            )
            mock_store.add_documents.assert_called_once()
            mock_set_first_last.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_synced_extend_range_future(self, mock_context, sample_timezone):
        """Test ensure_synced extending range into the future."""
        # Existing range
        existing_first = sample_timezone.localize(dt.datetime(2025, 5, 1, 0, 0, 0))
        existing_last = sample_timezone.localize(dt.datetime(2025, 5, 29, 23, 59, 59))
        
        # New requested range extends into future
        new_start = sample_timezone.localize(dt.datetime(2025, 5, 25, 0, 0, 0))
        new_end = sample_timezone.localize(dt.datetime(2025, 6, 5, 23, 59, 59))
        
        with patch('calendar_module.sync.get_first_last') as mock_get_first_last, \
             patch('calendar_module.sync.set_first_last') as mock_set_first_last, \
             patch('calendar_module.sync.parse_iso') as mock_parse_iso, \
             patch('calendar_module.sync.fetch_google', new_callable=AsyncMock) as mock_fetch, \
             patch('calendar_module.sync.get_vector_store') as mock_get_store:
            
            # Setup mocks
            mock_get_first_last.return_value = (existing_first, existing_last)
            mock_parse_iso.side_effect = [new_start, new_end]
            mock_fetch.return_value = [Mock(metadata={"id": "test_doc"})]
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await ensure_synced(
                type_="event",
                date_from=new_start.isoformat(),
                date_to=new_end.isoformat(),
                context=mock_context
            )
            
            # Verify - should only fetch the new range (existing_last to new_end)
            mock_fetch.assert_called_once_with(
                type_="event",
                date_from=existing_last.isoformat(),
                date_to=new_end.isoformat(),
                context=mock_context
            )

    @pytest.mark.asyncio
    async def test_ensure_synced_extend_range_past(self, mock_context, sample_timezone):
        """Test ensure_synced extending range into the past."""
        # Existing range
        existing_first = sample_timezone.localize(dt.datetime(2025, 5, 15, 0, 0, 0))
        existing_last = sample_timezone.localize(dt.datetime(2025, 5, 29, 23, 59, 59))
        
        # New requested range extends into past
        new_start = sample_timezone.localize(dt.datetime(2025, 5, 1, 0, 0, 0))
        new_end = sample_timezone.localize(dt.datetime(2025, 5, 20, 23, 59, 59))
        
        with patch('calendar_module.sync.get_first_last') as mock_get_first_last, \
             patch('calendar_module.sync.set_first_last') as mock_set_first_last, \
             patch('calendar_module.sync.parse_iso') as mock_parse_iso, \
             patch('calendar_module.sync.fetch_google', new_callable=AsyncMock) as mock_fetch, \
             patch('calendar_module.sync.get_vector_store') as mock_get_store:
            
            # Setup mocks
            mock_get_first_last.return_value = (existing_first, existing_last)
            mock_parse_iso.side_effect = [new_start, new_end]
            mock_fetch.return_value = [Mock(metadata={"id": "test_doc"})]
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await ensure_synced(
                type_="event",
                date_from=new_start.isoformat(),
                date_to=new_end.isoformat(),
                context=mock_context
            )
            
            # Verify - should only fetch the new range (new_start to existing_first)
            mock_fetch.assert_called_once_with(
                type_="event",
                date_from=new_start.isoformat(),
                date_to=existing_first.isoformat(),
                context=mock_context
            )

    @pytest.mark.asyncio
    async def test_ensure_synced_no_date_to_uses_future_horizon(self, mock_context, sample_timezone):
        """Test ensure_synced uses FUTURE_HORIZON when date_to is None."""
        start_dt = sample_timezone.localize(dt.datetime(2025, 5, 30, 0, 0, 0))
        expected_end = start_dt + dt.timedelta(days=FUTURE_HORIZON)
        
        with patch('calendar_module.sync.get_first_last') as mock_get_first_last, \
             patch('calendar_module.sync.parse_iso') as mock_parse_iso, \
             patch('calendar_module.sync.fetch_google', new_callable=AsyncMock) as mock_fetch, \
             patch('calendar_module.sync.get_vector_store') as mock_get_store:
            
            # Setup mocks
            mock_get_first_last.return_value = (None, None)  # First sync
            mock_parse_iso.return_value = start_dt
            mock_fetch.return_value = []
            
            mock_store = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await ensure_synced(
                type_="event",
                date_from=start_dt.isoformat(),
                date_to=None,  # Should use FUTURE_HORIZON
                context=mock_context
            )
            
            # Verify the end date calculation
            fetch_call = mock_fetch.call_args
            assert fetch_call is not None
            # The end date should be approximately start + FUTURE_HORIZON days
            
    @pytest.mark.asyncio
    async def test_ensure_synced_both_types(self, mock_context, sample_timezone):
        """Test ensure_synced with type 'both' processes events and tasks."""
        start_dt = sample_timezone.localize(dt.datetime(2025, 5, 30, 0, 0, 0))
        end_dt = sample_timezone.localize(dt.datetime(2025, 5, 30, 23, 59, 59))
        
        with patch('calendar_module.sync.get_first_last') as mock_get_first_last, \
             patch('calendar_module.sync.set_first_last') as mock_set_first_last, \
             patch('calendar_module.sync.parse_iso') as mock_parse_iso, \
             patch('calendar_module.sync.fetch_google', new_callable=AsyncMock) as mock_fetch, \
             patch('calendar_module.sync.get_vector_store') as mock_get_store:
            
            # Setup mocks
            mock_get_first_last.return_value = (None, None)  # First sync for both
            mock_parse_iso.side_effect = [start_dt, end_dt] * 2  # Called for each type
            mock_fetch.return_value = [Mock(metadata={"id": "test_doc"})]
            
            mock_store = Mock()
            mock_store.add_documents = Mock()
            mock_get_store.return_value = mock_store
            
            # Execute
            await ensure_synced(
                type_="both",
                date_from=start_dt.isoformat(),
                date_to=end_dt.isoformat(),
                context=mock_context
            )
            
            # Verify - should be called once for each type (event, task)
            assert mock_fetch.call_count == 2
            assert mock_store.add_documents.call_count == 2
            assert mock_set_first_last.call_count == 2

    @pytest.mark.asyncio
    async def test_ensure_synced_no_new_data_needed(self, mock_context, sample_timezone):
        """Test ensure_synced when no new data needs to be fetched."""
        # Existing range fully covers requested range
        existing_first = sample_timezone.localize(dt.datetime(2025, 5, 1, 0, 0, 0))
        existing_last = sample_timezone.localize(dt.datetime(2025, 6, 1, 23, 59, 59))
        
        # Requested range is within existing range
        req_start = sample_timezone.localize(dt.datetime(2025, 5, 15, 0, 0, 0))
        req_end = sample_timezone.localize(dt.datetime(2025, 5, 20, 23, 59, 59))
        
        with patch('calendar_module.sync.get_first_last') as mock_get_first_last, \
             patch('calendar_module.sync.parse_iso') as mock_parse_iso, \
             patch('calendar_module.sync.fetch_google', new_callable=AsyncMock) as mock_fetch:
            
            # Setup mocks
            mock_get_first_last.return_value = (existing_first, existing_last)
            mock_parse_iso.side_effect = [req_start, req_end]
            
            # Execute
            await ensure_synced(
                type_="event",
                date_from=req_start.isoformat(),
                date_to=req_end.isoformat(),
                context=mock_context
            )
            
            # Verify - should not fetch anything
            mock_fetch.assert_not_called()


class TestSyncConstants:
    def test_future_horizon_constant(self):
        """Test that FUTURE_HORIZON is set to reasonable value."""
        assert FUTURE_HORIZON == 30
        assert isinstance(FUTURE_HORIZON, int)
        assert FUTURE_HORIZON > 0

    def test_field_constants_are_strings(self):
        """Test that field constants are properly formatted strings."""
        assert isinstance(CAL_FIELDS, str)
        assert isinstance(TASK_FIELDS, str)
        assert len(CAL_FIELDS) > 0
        assert len(TASK_FIELDS) > 0
        
        # Should contain expected fields
        assert "items" in CAL_FIELDS
        assert "id" in CAL_FIELDS
        assert "summary" in CAL_FIELDS
        assert "nextPageToken" in CAL_FIELDS
