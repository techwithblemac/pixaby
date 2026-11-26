"""
door_tools.py
=============
Editor-side helpers for door authoring. Only ``warp`` doors carry extra
data: a ``targets`` list of [x, y] coordinates they can send things to,
authored as one short text field because the popup only speaks
int/float/bool/choice/text.

A warp door's JSON shape:

    {"x": 640, "y": -128, "width": 64, "height": 64, "type": "door",
     "name": "warp_4", "targets": [[1280, -128], [0, 512]]}

Text format is forgiving: ``1280,-128; 0,512`` or ``(1280, -128) (0, 512)``
both work -- every whole number is read in order and paired up.
"""

import re

_NUMBER = re.compile(r"-?\d+")


def parse_targets(text):
    """``"1280,-128; 0,512"`` -> ``[[1280, -128], [0, 512]]`` (a trailing odd number is dropped)."""
    numbers = [int(n) for n in _NUMBER.findall(str(text))]
    pairs = [[numbers[i], numbers[i + 1]] for i in range(0, len(numbers) - 1, 2)]
    unique = []
    for pair in pairs:
        if pair not in unique:
            unique.append(pair)
    return unique


def format_targets(targets):
    """The inverse of parse_targets, for pre-filling the popup field."""
    return "; ".join(f"{x},{y}" for x, y in targets)
