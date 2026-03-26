import unittest
from core.context.context_guard import ContextGuard

class TestContextGuard(unittest.TestCase):
    def test_loop_detection(self):
        guard = ContextGuard()
        
        # Scenario 1: No loop
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        self.assertIsNone(guard.check_tool_loops(history))
        
        # Scenario 2: Repeated tool calls
        tool_call = [{"function": {"name": "test_tool", "arguments": "{}"}}]
        history = [
            {"role": "assistant", "tool_calls": tool_call},
            {"role": "tool", "content": "result"},
            {"role": "assistant", "tool_calls": tool_call},
            {"role": "tool", "content": "result"},
            {"role": "assistant", "tool_calls": tool_call},
        ]
        # Threshold is 3 by default
        self.assertIsNotNone(guard.check_tool_loops(history))
        print(f"Detected: {guard.check_tool_loops(history)}")
        
        # Scenario 3: Mixed tools (no loop)
        tool_call_2 = [{"function": {"name": "other_tool", "arguments": "{}"}}]
        history = [
            {"role": "assistant", "tool_calls": tool_call},
            {"role": "assistant", "tool_calls": tool_call_2},
            {"role": "assistant", "tool_calls": tool_call},
        ]
        self.assertIsNone(guard.check_tool_loops(history))
        
if __name__ == "__main__":
    unittest.main()
