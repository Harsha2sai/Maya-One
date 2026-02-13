import pytest
import asyncio
from unittest.mock import MagicMock, patch
from core.system_control.supabase_manager import SupabaseManager

@pytest.fixture
def mock_supabase_client():
    with patch("core.system_control.supabase_manager.create_client") as mock_create:
        client_mock = MagicMock()
        mock_create.return_value = client_mock
        yield client_mock

@pytest.mark.asyncio
async def test_supabase_initialization(mock_supabase_client):
    with patch.dict("os.environ", {"SUPABASE_URL": "http://test", "SUPABASE_SERVICE_KEY": "test"}):
        manager = SupabaseManager()
        assert manager.client is not None

@pytest.mark.asyncio
async def test_create_alarm(mock_supabase_client):
    with patch.dict("os.environ", {"SUPABASE_URL": "http://test", "SUPABASE_SERVICE_KEY": "test"}):
        manager = SupabaseManager()
        
        # Mock chain: table().insert().execute()
        table_mock = MagicMock()
        insert_mock = MagicMock()
        execute_mock = MagicMock()
        
        # Setup return values
        result_mock = MagicMock()
        result_mock.data = [{"id": 1, "alarm_time": "2023-01-01"}]
        execute_mock.return_value = result_mock
        
        insert_mock.execute = MagicMock(return_value=result_mock)
        table_mock.insert.return_value = insert_mock
        manager.client.table.return_value = table_mock
        
        # Override _execute to run synchronously for test or mock to_thread
        # Since _execute uses asyncio.to_thread, we need to mock the blocking call or let it run
        # unittest.mock doesn't easily mock inner workings of to_thread target, 
        # but since table()...execute() is the target, we just mock that.
        
        # However, asyncio.to_thread runs in a separate thread. MagicMocks are thread-safe enough for simple checks.
        
        success = await manager.create_alarm("user123", "2023-01-01T10:00:00Z")
        assert success is True
        
        manager.client.table.assert_called_with("user_alarms")
        table_mock.insert.assert_called_with({
            "user_id": "user123", 
            "alarm_time": "2023-01-01T10:00:00Z", 
            "label": "Alarm", 
            "is_active": True
        })

@pytest.mark.asyncio
async def test_get_notes(mock_supabase_client):
    with patch.dict("os.environ", {"SUPABASE_URL": "http://test", "SUPABASE_SERVICE_KEY": "test"}):
        manager = SupabaseManager()
        
        table_mock = MagicMock()
        select_mock = MagicMock()
        eq_mock = MagicMock()
        order_mock = MagicMock()
        limit_mock = MagicMock()
        
        result_mock = MagicMock()
        result_mock.data = [{"id": 1, "title": "Test Note"}]
        
        limit_mock.execute.return_value = result_mock
        order_mock.limit.return_value = limit_mock
        eq_mock.order.return_value = order_mock
        select_mock.eq.return_value = eq_mock
        table_mock.select.return_value = select_mock
        manager.client.table.return_value = table_mock
        
        notes = await manager.get_notes("user123")
        assert len(notes) == 1
        assert notes[0]["title"] == "Test Note"
