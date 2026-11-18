"""Count additive signed dice exactly, using a sliding-window convolution."""
import re
from collections import Counter

MAX_DICE = 64
MAX_FACES = 1024
MAX_WIDTH = 1024
MAX_PAIRS = 65536


def dice_distribution(expression):
    if not isinstance(expression, str) or len(expression) > 2048:
        raise ValueError('ダイスの式が長すぎます。')
    text = re.sub(r'\s+', '', re.sub(r'【.*?】', '', expression))
    # The live roller recognizes only nonnegative faces. For a negative face,
    # its sanitizer removes the unrecognized 'd' (e.g. 2-1d-3 becomes 2-1-3).
    text = re.sub(r'(\d+)d(-\d+)', r'\1\2', text)
    tokens = list(re.finditer(r'([+-]*)((?:\d+d\d+)|\d+)', text))
    if not tokens or ''.join(token.group(0) for token in tokens) != text:
        raise ValueError('式は整数と符号付きダイスの和で指定してください。')
    # Consecutive signs are produced by negative runtime corrections (e.g. 2+-3).
    counts, offset, total, dice_count = [1], 0, 1, 0
    for token in tokens:
        sign = -1 if token[1].count('-') % 2 else 1
        value = token[2]
        if 'd' not in value:
            offset += sign * int(value)
            continue
        number, faces = map(int, value.split('d'))
        dice_count += number
        if dice_count > MAX_DICE or faces > MAX_FACES:
            raise ValueError('ダイスは64個・1024面までです。')
        if faces < 1 or not number:
            continue
        if len(counts) + number * (faces - 1) > MAX_WIDTH:
            raise ValueError('威力の分布は1024通りまでです。')
        offset += number if sign > 0 else -number * faces
        total *= faces ** number
        for _ in range(number):
            expanded, window = [], 0
            for index in range(len(counts) + faces - 1):
                if index < len(counts):
                    window += counts[index]
                if 0 <= index - faces < len(counts):
                    window -= counts[index - faces]
                expanded.append(window)
            counts = expanded
    return Counter({index + offset:value for index, value in enumerate(counts) if value}), total
