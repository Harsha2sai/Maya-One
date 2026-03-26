
import unittest
from core.tools.tool_call_validator import validate_tool_call

class TestToolCallValidator(unittest.TestCase):
    
    def test_valid_call(self):
        class PseudoCall:
            def __init__(self, n, a): self.name = n; self.arguments = a
            
        call = PseudoCall("allowed_tool", {"arg": 1})
        allowed = ["allowed_tool", "other_tool"]
        
        self.assertTrue(validate_tool_call(call, allowed))

    def test_invalid_name(self):
        class PseudoCall:
            def __init__(self, n, a): self.name = n; self.arguments = a
            
        call = PseudoCall("forbidden_tool", {})
        allowed = ["allowed_tool"]
        
        self.assertFalse(validate_tool_call(call, allowed))

    def test_malformed_arguments(self):
        class PseudoCall:
             def __init__(self, n, a): self.name = n; self.arguments = a
        
        # Valid name, but arguments is NOT a dict
        call = PseudoCall("allowed_tool", "string_args_not_parsed")
        allowed = ["allowed_tool"]
        
        self.assertFalse(validate_tool_call(call, allowed))
        
    def test_missing_attributes(self):
        class BrokenCall:
             pass
        
        call = BrokenCall()
        allowed = ["any"]
        
        self.assertFalse(validate_tool_call(call, allowed))

if __name__ == "__main__":
    unittest.main()
