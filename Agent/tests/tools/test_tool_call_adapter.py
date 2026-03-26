
import unittest
import json
from unittest.mock import MagicMock
from core.tools.tool_call_adapter import ToolCallAdapter

class TestToolCallAdapter(unittest.TestCase):
    
    def test_normalize_dict_old_format(self):
        # OpenAI Old Format: {"function": {"name": "foo", "arguments": "{}"}, "id": "123"}
        raw = {
            "function": {"name": "test_tool", "arguments": '{"arg": 1}'},
            "id": "call_123"
        }
        normalized = ToolCallAdapter.normalize(raw)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.name, "test_tool")
        self.assertEqual(normalized.arguments, {"arg": 1})
        self.assertEqual(normalized.call_id, "call_123")

    def test_normalize_dict_new_format(self):
        # OpenAI Flattened/New Format: {"name": "foo", "arguments": "{}", "id": "123"}
        raw = {
            "name": "test_tool",
            "arguments": '{"arg": 2}',
            "id": "call_456"
        }
        normalized = ToolCallAdapter.normalize(raw)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.name, "test_tool")
        self.assertEqual(normalized.arguments, {"arg": 2})
        self.assertEqual(normalized.call_id, "call_456")

    def test_normalize_object_old_schema(self):
        # Object with .function.name
        # To simulate 'name' NOT existing on parent, we must use a spec or del the attr
        # But MagicMock creates attrs on access.
        # Safest way: create a class or use spec=object
        class MockToolCall:
            def __init__(self):
                self.id = "id_obj"
                self.function = MagicMock()
                self.function.name = "obj_tool"
                self.function.arguments = '{"x": 1}'
        
        mock_obj = MockToolCall()
        # mock_obj does NOT have .name attribute by default in this class definition
        
        normalized = ToolCallAdapter.normalize(mock_obj)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.name, "obj_tool")
        self.assertEqual(normalized.arguments, {"x": 1})
        self.assertEqual(normalized.call_id, "id_obj")
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.name, "obj_tool")
        self.assertEqual(normalized.arguments, {"x": 1})
        self.assertEqual(normalized.call_id, "id_obj")

    def test_normalize_object_new_schema(self):
        # Object with .name directly (LiveKit wrapping)
        mock_obj = MagicMock()
        mock_obj.name = "direct_tool"
        mock_obj.arguments = '{"y": 2}'
        mock_obj.id = "id_direct"
        
        normalized = ToolCallAdapter.normalize(mock_obj)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.name, "direct_tool")
        self.assertEqual(normalized.arguments, {"y": 2})
        self.assertEqual(normalized.call_id, "id_direct")
        
    def test_invalid_json_arguments(self):
        raw = {
            "name": "bad_json",
            "arguments": "{bad",
            "id": "1"
        }
        normalized = ToolCallAdapter.normalize(raw)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.arguments, {}) # Fallback to empty dict

    def test_missing_name(self):
        raw = {"id": "1"}
        normalized = ToolCallAdapter.normalize(raw)
        self.assertIsNone(normalized)

if __name__ == "__main__":
    unittest.main()
