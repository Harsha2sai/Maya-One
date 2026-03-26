import unittest
from core.context.context_guard import ContextGuard

class TestContextGuard(unittest.TestCase):
    def setUp(self):
        self.guard = ContextGuard(token_limit=100)

    def test_count_tokens(self):
        text = "Hello world " * 10
        count = self.guard.count_tokens(text)
        self.assertGreater(count, 0)

    def test_guard_history_limit(self):
        # Create history exceeding limit
        history = [
            {"role": "user", "content": "Message 1 " * 20}, # ~40 tokens
            {"role": "assistant", "content": "Message 2 " * 20}, # ~40 tokens
            {"role": "user", "content": "Message 3 " * 20}, # ~40 tokens
        ]
        # Total ~120 tokens > 100 limit
        
        guarded = self.guard.guard_history(history)
        
        # Should truncate oldest messages
        # Message 1 should be dropped or summarized (but my logic drops)
        self.assertLess(len(guarded), 3)
        self.assertEqual(guarded[-1]["content"], history[-1]["content"])

    def test_truncate_tool_output(self):
        large_output = "word " * 2000 # Ensure enough tokens
        truncated = self.guard.truncate_tool_output(large_output, max_tokens=100)
        self.assertLess(len(truncated), len(large_output))
        self.assertIn("Truncated", truncated)

if __name__ == "__main__":
    unittest.main()
