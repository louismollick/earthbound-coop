"""Splice Mother 2 presentation onto US logic, for the Japanese Locale (ADR 0003).

Every text op is either PRESENTATION (it only changes what is printed, or where
and how fast) or LOGIC (it touches game state or control flow).  A Japanese
message is the US message's logic ops, in order and with their US arguments,
with the Mother 2 presentation ops placed around them:

    US:     [text "Hi"] [set_event_flag A] [text "Bye"] [end_block]
    JP:     [text "やあ"] [set_event_flag A] [text "じゃ"] [pause 5] [end_block]
    spliced:[text "やあ"] [set_event_flag A] [text "じゃ"] [pause 5] [end_block]

``strip_presentation(spliced) == strip_presentation(us)`` always holds.
"""

import difflib
from collections.abc import Callable

from ebtools.text_dsl.opcodes import OPCODE_BY_NAME, ArgType

# Ops that only affect what is printed, where it is printed, or how fast.
# Everything else (including "unknown" raw bytes) is LOGIC.  Read against
# src/game/display_text_cc.c: none of these write game state, working/argument
# memory, windows, menus' results, flags, items, sound effects or control flow.
PRESENTATION_OPS: dict[str, str] = {
    "text": "literal glyphs",
    "line_break": "0x00: new line",
    "start_new_line": "0x01: new line if the cursor is not at column 0",
    "halt_with_prompt": "0x03: wait for a button, with the blinking triangle",
    "pause": "0x10: wait N frames",
    "clear_text_line": "0x12: erase the current line",
    "halt_without_prompt": "0x13: wait for a button, no triangle",
    "halt_with_prompt_always": "0x14: wait for a button, triangle even in battle",
    "force_text_alignment": "18 05: move the text cursor",
    "clear_window": "18 06: erase the focus window's text",
    "load_string_to_memory": "19 02: a menu option's label (its select_script label is remapped)",
    "clear_loaded_strings": "19 04: drop the focus window's menu labels",
    "text_colour_effects": "1C 00: text palette",
    "print_stat": "1C 01: print a value from the CC table",
    "print_char_name": "1C 02: print a party member's name",
    "print_char": "1C 03: print one glyph code",
    "print_item_name": "1C 05: print an item name",
    "print_teleport_destination_name": "1C 06: print a teleport destination",
    "print_horizontal_text_string": "1C 07: lay the loaded menu labels out in N columns",
    "print_special_gfx": "1C 08: print a special graphic",
    "set_number_padding": "1C 09: pad the next printed number",
    "print_number": "1C 0A: print a number",
    "print_money_amount": "1C 0B: print a money amount",
    "print_vertical_text_string": "1C 0C: lay the loaded menu labels out vertically",
    "print_action_user_name": "1C 0D: print the battle action's user",
    "print_action_target_name": "1C 0E: print the battle action's target",
    "print_action_amount": "1C 0F: print the battle action's amount",
    "hint_new_line": "1C 11: break the line if the next word is wider than N (Mother 2 only)",
    "print_psi_name": "1C 12: print a PSI name",
    "set_text_printing_sound": "1F 04: the typing blip",
    "use_normal_font": "1F 30: font",
    "use_mr_saturn_font": "1F 31: font",
    "text_speed_delay": "1F 60: the per-character typing delay",
    "enable_blinking_triangle": "1F 62: whether prompts blink",
}


def is_presentation(op: dict) -> bool:
    """Return True for a presentation op (see PRESENTATION_OPS).

    An ``unknown`` single byte at 0x20 or above is a glyph the text table
    lacks (the US KEYBOARD's spacers), so it is presentation too.
    """
    if op["op"] == "unknown":
        return len(op["bytes"]) == 1 and op["bytes"][0] >= 0x20
    return op["op"] in PRESENTATION_OPS


def strip_presentation(ops: list[dict]) -> list[dict]:
    """Return the logic ops of a message, in order."""
    return [op for op in ops if not is_presentation(op)]


def label_args(op: dict) -> list[object]:
    """Return the label-valued arguments of an op, in argument order.

    Covers LABEL args, every JUMP_TABLE target and a load_string_to_memory
    select_script label.
    """
    if op["op"] == "load_string_to_memory":
        payload = op.get("payload", {})
        return [payload["label"]] if payload.get("terminator") == "select_script" else []
    spec = OPCODE_BY_NAME.get(op["op"])
    if spec is None:
        return []
    out: list[object] = []
    for arg in spec.args:
        if arg.type == ArgType.LABEL:
            out.append(op[arg.name])
        elif arg.type == ArgType.JUMP_TABLE:
            out.extend(op[arg.name])
    return out


def map_label_args(op: dict, fn: Callable[[object], object]) -> dict:
    """Return a copy of *op* with every label argument replaced by ``fn(label)``."""
    new = dict(op)
    if op["op"] == "load_string_to_memory":
        payload = op.get("payload", {})
        if payload.get("terminator") == "select_script":
            new["payload"] = {**payload, "label": fn(payload["label"])}
        return new
    spec = OPCODE_BY_NAME.get(op["op"])
    if spec is None:
        return new
    for arg in spec.args:
        if arg.type == ArgType.LABEL:
            new[arg.name] = fn(op[arg.name])
        elif arg.type == ArgType.JUMP_TABLE:
            new[arg.name] = [fn(t) for t in op[arg.name]]
    return new


# A label boundary inside a fallthrough chain (see splice_chain).  It is a
# logic op for splice(), and only ever matches the same label.
LABEL_MARKER = "__label__"


def _key(op: dict) -> tuple:
    """Comparison key of a logic op: its name and its non-label arguments."""
    spec = OPCODE_BY_NAME.get(op["op"])
    if spec is None:  # unknown bytes, label markers
        return (op["op"], repr(sorted(op.items())))
    args = tuple(
        repr(op.get(a.name)) for a in spec.args if a.type not in (ArgType.LABEL, ArgType.JUMP_TABLE, ArgType.STRING)
    )
    return (op["op"], args)


def match_logic(us_logic: list[dict], jp_logic: list[dict]) -> list[tuple[int, int]]:
    """Pair up US and JP logic ops: indices (us_i, jp_j), both increasing.

    Exact matches (name and non-label args) anchor the alignment; the gaps
    between anchors are then matched on op names alone, so an op whose
    argument the US version fixed still pairs with its Mother 2 original.
    """
    pairs: list[tuple[int, int]] = []

    def run(a_lo: int, a_hi: int, b_lo: int, b_hi: int, key: Callable[[dict], object], then_names: bool) -> None:
        a = [key(op) for op in us_logic[a_lo:a_hi]]
        b = [key(op) for op in jp_logic[b_lo:b_hi]]
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        prev_a, prev_b = a_lo, b_lo
        for blk in sm.get_matching_blocks():
            ma, mb = a_lo + blk.a, b_lo + blk.b
            if then_names and (ma > prev_a and mb > prev_b):
                run(prev_a, ma, prev_b, mb, _name_key, False)
            pairs.extend((ma + k, mb + k) for k in range(blk.size))
            prev_a, prev_b = ma + blk.size, mb + blk.size

    run(0, len(us_logic), 0, len(jp_logic), _key, True)
    pairs.sort()
    return pairs


def _name_key(op: dict) -> object:
    return _key(op) if op["op"] == LABEL_MARKER else op["op"]


# Ops after which execution never continues to the next op.
_TERMINATORS = frozenset({"end_block", "jump"})


def splice(us_ops: list[dict], jp_ops: list[dict], jp_label_to_us: Callable[[object], object]) -> list[dict]:
    """Build a message from the US logic ops and the Mother 2 presentation ops.

    Parameters
    ----------
    us_ops
        The US message (only its logic ops are used).
    jp_ops
        The Mother 2 message (only its presentation ops are used).
    jp_label_to_us
        Maps a Mother 2 label argument of a presentation op (a menu option's
        select_script label) to the US label.

    Returns
    -------
    list[dict]
        For each US logic op in order: the Mother 2 presentation run before its
        matched Mother 2 logic op, then the US op.  Runs before unmatched
        Mother 2 logic ops join the next emitted run; what is left goes at the
        end (before a final end_block/jump, so it still prints).
    """
    us_logic = strip_presentation(us_ops)

    # Mother 2 presentation runs: runs[k] precedes jp_logic[k]; runs[-1] trails.
    jp_logic: list[dict] = []
    runs: list[list[dict]] = [[]]
    for op in jp_ops:
        if is_presentation(op):
            runs[-1].append(map_label_args(op, jp_label_to_us))
        else:
            jp_logic.append(op)
            runs.append([])

    matched = dict(match_logic(us_logic, jp_logic))
    out: list[dict] = []
    next_run = 0  # first run not emitted yet
    for i, op in enumerate(us_logic):
        j = matched.get(i)
        if j is not None:
            for k in range(next_run, j + 1):
                out.extend(runs[k])
            next_run = j + 1
        out.append(op)

    rest = [op for k in range(next_run, len(runs)) for op in runs[k]]
    if rest and out and out[-1]["op"] in _TERMINATORS:
        out[-1:-1] = rest
    else:
        out.extend(rest)
    return out


def falls_through(ops: list[dict]) -> bool:
    """Return True if execution runs off the end of *ops* into the next label."""
    logic = strip_presentation(ops)
    return not logic or logic[-1]["op"] not in _TERMINATORS


def splice_chain(
    us_chain: list[tuple[str, list[dict]]],
    jp_parts: list[tuple[str | None, list[dict]]],
    jp_label_to_us: Callable[[object], object],
) -> dict[str, list[dict]]:
    """Splice a run of US labels that fall through into each other, as one message.

    Parameters
    ----------
    us_chain
        ``(label, ops)`` in file order; every message but the last falls through.
    jp_parts
        The Mother 2 messages to take presentation from, in order: ``(US label,
        ops)`` for the counterpart of a chain label, ``(None, ops)`` for a
        Mother 2-only message that its predecessor falls into.
    jp_label_to_us
        As for :func:`splice`.

    Returns
    -------
    dict[str, list[dict]]
        The spliced message of every chain label.  A label boundary present on
        both sides keeps the presentation on its own side; text of a Mother 2
        message that a US-only label splits flows into the label that prints it.
    """
    us_ops = [op for label, ops in us_chain for op in [{"op": LABEL_MARKER, "label": label}, *ops]]
    jp_ops: list[dict] = []
    for label, ops in jp_parts:
        if label is not None:
            jp_ops.append({"op": LABEL_MARKER, "label": label})
        jp_ops.extend(ops)
    out: dict[str, list[dict]] = {}
    current: list[dict] = []
    for op in splice(us_ops, jp_ops, jp_label_to_us):
        if op["op"] == LABEL_MARKER:
            current = out[op["label"]] = []
        else:
            current.append(op)
    return out
