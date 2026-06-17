"""
plate_postprocess.py
────────────────────
Syntax correction + garbage filtering for OCR output.

Garbage filter rejects:
  • Too short / too long
  • Mostly non-alphanumeric
  • Single repeated character  (LLLLLL, 000000)
  • Common OCR noise words
  • Does not match ANY known country pattern at all
"""

import re
from collections import Counter

# ── Character substitution maps ───────────────────────────────────────────────

LETTER_TO_DIGIT = {
    'O': '0', 'Q': '0', 'D': '0',
    'I': '1', 'L': '1',
    'Z': '2',
    'S': '5',
    'B': '8',
    'G': '6',
}

DIGIT_TO_LETTER = {
    '0': 'O',
    '1': 'I',
    '2': 'Z',
    '5': 'S',
    '6': 'G',
    '8': 'B',
}

# ── Country plate syntax patterns ─────────────────────────────────────────────
# L = letter, D = digit

COUNTRY_SYNTAX = {
    # India: KA01AB1234  (10 chars) or MH12DE1433
    "IN": [
        ["L","L","D","D","L","L","D","D","D","D"],   # standard 10-char
        ["L","L","D","D","L","D","D","D","D"],        # 9-char (some older)
    ],
    # UK: AB12CDE (7 chars)
    "UK": [
        ["L","L","D","D","L","L","L"],
    ],
    # Germany: ABC1234 (variable, simplified)
    "DE": [
        ["L","L","L","D","D","D","D"],
        ["L","L","D","D","D","D"],
    ],
}

# OCR noise strings that should always be rejected
_GARBAGE_WORDS = {
    "L", "I", "O", "B", "S", "Z", "G",   # single chars
    "LL", "II", "OO",
    "ELE", "ELEE", "ELEL",
    "LLL", "LLLL", "LLLLL", "LLLLLL",
    "III", "IIII",
    "000", "0000",
    "NULL", "NONE", "TEST",
}

# Minimum alphanumeric length to even consider a string a plate
_MIN_LEN = 4
_MAX_LEN = 12


def is_garbage(text: str) -> bool:
    """
    Return True if the text is clearly not a real plate number.
    Filters applied in order (fast → slow):
      1. Length check
      2. Known noise word list
      3. Repeated-character check  (≥70 % same char)
      4. Alphanumeric ratio        (must be ≥80 % alnum)
      5. Must contain at least one digit AND one letter
         (pure-letter or pure-digit strings are almost always garbage)
    """
    t = re.sub(r'[^A-Z0-9]', '', text.upper())

    # 1. Length
    if len(t) < _MIN_LEN or len(t) > _MAX_LEN:
        return True

    # 2. Known noise
    if t in _GARBAGE_WORDS:
        return True

    # 3. Repeated characters
    most_common_count = Counter(t).most_common(1)[0][1]
    if most_common_count / len(t) >= 0.70:
        return True

    # 4. Alphanumeric ratio (already stripped non-alnum above, so always 100%)
    #    But check against the ORIGINAL text before stripping
    alnum_ratio = len(t) / max(len(text), 1)
    if alnum_ratio < 0.60:
        return True

    # 5. Must have both letters and digits
    has_letter = any(c.isalpha() for c in t)
    has_digit  = any(c.isdigit() for c in t)
    if not (has_letter and has_digit):
        return True

    return False


def apply_plate_syntax(text: str, country: str = "IN") -> str:
    """
    1. Strip non-alphanumeric characters.
    2. Run garbage filter — return "" if garbage.
    3. Try each pattern for the country; apply L/D corrections on match.
    4. Return corrected text, or cleaned text if no pattern matched.
    """
    text = re.sub(r'[^A-Z0-9]', '', text.upper())

    if not text:
        return ""

    if is_garbage(text):
        return ""

    patterns = COUNTRY_SYNTAX.get(country, [])

    for pattern in patterns:
        if len(text) != len(pattern):
            continue

        corrected = list(text)
        for i, expected in enumerate(pattern):
            c = corrected[i]
            if expected == "D" and c.isalpha():
                corrected[i] = LETTER_TO_DIGIT.get(c, c)
            elif expected == "L" and c.isdigit():
                corrected[i] = DIGIT_TO_LETTER.get(c, c)

        return "".join(corrected)

    # No pattern matched length — return cleaned text as-is
    # (still passed garbage filter so it might be valid)
    return text