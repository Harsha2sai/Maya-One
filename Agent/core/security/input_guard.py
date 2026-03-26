import re


class InputGuard:
    MAX_LEN = 4000

    @staticmethod
    def sanitize(text: str) -> str:
        if not text:
            return ""
        text = text[: InputGuard.MAX_LEN]
        text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)
        text = re.sub(r"(.)\1{50,}", r"\1\1\1", text)
        return text.strip()
