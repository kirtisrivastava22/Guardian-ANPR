import re
from collections import Counter

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

COUNTRY_SYNTAX = {
    # India:
    "IN": [
        ["L","L","D","D","L","L","D","D","D","D"],  
        ["L","L","D","D","L","D","D","D","D"],        
    ],
    # UK:
    "UK": [
        ["L","L","D","D","L","L","L"],
    ],
    # Germany:
    "DE": [
        ["L","L","L","D","D","D","D"],
        ["L","L","D","D","D","D"],
    ],
}

_GARBAGE_WORDS = {
    "L", "I", "O", "B", "S", "Z", "G",   
    "LL", "II", "OO",
    "ELE", "ELEE", "ELEL",
    "LLL", "LLLL", "LLLLL", "LLLLLL",
    "III", "IIII",
    "000", "0000",
    "NULL", "NONE", "TEST",
}

_MIN_LEN = 4
_MAX_LEN = 12


def is_garbage(text: str) -> bool:
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

    return text