
import unittest
from core.memory.fts_query_sanitizer import sanitize_fts_query

class TestFTSSanitizer(unittest.TestCase):
    
    def test_valid_queries(self):
        self.assertEqual(sanitize_fts_query("python agent"), "python OR agent")
        self.assertEqual(sanitize_fts_query("machine learning"), "machine OR learning")
        self.assertEqual(sanitize_fts_query("search for cats"), "search OR for OR cats") # 'for' might be stopword? No, not in set.
        
    def test_punctuation_and_emojis(self):
        self.assertIsNone(sanitize_fts_query("???"))
        self.assertIsNone(sanitize_fts_query("!!!"))
        self.assertIsNone(sanitize_fts_query("---"))
        self.assertIsNone(sanitize_fts_query("👋"))
        self.assertEqual(sanitize_fts_query("😊 check"), "check")
        # "😊 check" -> "check" -> "check" (len 5 >= 3) -> OK
        self.assertEqual(sanitize_fts_query("😊 check"), "check")
        
    def test_stopwords(self):
        self.assertIsNone(sanitize_fts_query("hi"))
        self.assertIsNone(sanitize_fts_query("hello"))
        self.assertIsNone(sanitize_fts_query("ok thanks"))
        self.assertIsNone(sanitize_fts_query("yes no"))
        
    def test_short_words(self):
        # "AI" is 2 chars. Per rule >=3 chars, it should be dropped if it's the only word?
        # The sanitizer returns None if NO word is >= 3 chars.
        self.assertIsNone(sanitize_fts_query("ab cd"))
        
        # This is a strict trade-off for stability.
        # "AI agent" -> "AI" (2) "agent" (5) -> OK because "agent" >= 3
        self.assertEqual(sanitize_fts_query("AI agent"), "AI OR agent")
        
    def test_complex_sanitization(self):
        # "Hello! @User, check this..." -> "User" (4), "check" (5), "this" (4)
        input_str = "Hello! @User, check this..."
        # "Hello" -> stopword
        # "@User" -> "User"
        # "check" -> "check"
        # "this" -> "this"
        expected = "User OR check OR this" # 'this' not in stopwords list
        self.assertEqual(sanitize_fts_query(input_str), expected)

if __name__ == '__main__':
    unittest.main()
