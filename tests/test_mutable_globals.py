"""Every mutable global in libgame must be serialized or classified in the serialization audit.

A global that savestates miss breaks F7 in a fresh process and netplay joins (the joiner
restores a savestate into a new process). This lists every writable global and static in
the debug build's library with ``nm`` and fails on any that is neither a directly
serialized ``state_dump.c`` section nor named in ``docs/coop-design/serialization-audit.md``.
When it fails, serialize the new variable or add it to the audit with its class.

Audit names are the backticked tokens on the audit's list lines (``- ``): a symbol name
(``fnmatch`` patterns allowed; function statics are ``function.var``) or a source file
(``ppu_render.c``) for every symbol of that file. Needs ``port/unix/build-debug`` (a Debug
build keeps every symbol unmerged; Release merges statics), so it skips without one;
``scripts/coop-gates.sh --full`` runs it after building that tree.
"""

import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "port" / "unix" / "build-debug" / "game_lib" / "libearthbound_game.a"
AUDIT = ROOT / "docs" / "coop-design" / "serialization-audit.md"
STATE_DUMP = ROOT / "src" / "core" / "state_dump.c"
# Compiler, sanitizer and vendored-library symbols, not game state.
IGNORE = re.compile(r"^(l_|ltmp|___?asan|__odr|___unnamed|\.L|__sancov|__llvm|__profc)")
# Vendored tamp (de)compressor objects: library internals, not game state.
VENDOR_OBJECTS = {"common.c", "compressor.c", "decompressor.c"}


def mutable_globals(lib):
    """{symbol: source file} for every writable data/bss/common symbol in ``lib``."""
    # Mach-O (`nm -m`) names the section, ELF uses type letters (D/d data, B/b bss, C common).
    darwin = sys.platform == "darwin"
    out = subprocess.run(["nm", "-A"] + (["-m"] if darwin else []) + [str(lib)], capture_output=True, text=True)  # noqa: S603
    kind = r"\((?:__DATA,__(?:data|bss|common)|common)\).*" if darwin else r"[DdBbC]"
    syms = {}
    for line in out.stdout.splitlines():
        m = re.match(r"^.*?\(?([\w.+-]+)\.o\)?:\s*(?:[0-9a-fA-F]+\s+)?" + kind + r"\s(\S+)$", line)
        if not m:
            continue
        obj, name = m.groups()
        name = name[1:] if name.startswith("_") else name  # Mach-O prefixes C names with "_"
        if IGNORE.match(name) or obj in VENDOR_OBJECTS:
            continue
        syms[re.sub(r"\.\d+$", "", name)] = obj  # gcc's "var.123" for function statics
    return syms


def serialized_sections():
    """Names passed to ADD(SECTION_..., &name / name, ...) in state_dump.c."""
    return set(re.findall(r"ADD\(SECTION_\w+,\s*&?(\w+)", STATE_DUMP.read_text()))


def audit_patterns():
    pats = []
    for line in AUDIT.read_text().splitlines():
        if line.lstrip().startswith("- "):
            pats += re.findall(r"`([^`\s]+)`", line)
    return pats


def classified(name, obj, pats):
    for p in pats:
        if p.endswith(".c") and p == obj:
            return True
        if fnmatch.fnmatchcase(name, p) or fnmatch.fnmatchcase(name.split(".")[-1], p):
            return True
    return False


def test_every_mutable_global_is_classified():
    if not LIB.exists() or not shutil.which("nm"):
        pytest.skip(f"needs {LIB.relative_to(ROOT)} (cmake Debug build) and nm")
    syms = mutable_globals(LIB)
    assert len(syms) > 100, "nm parse found too few symbols"
    known = serialized_sections()
    pats = audit_patterns()
    missing = sorted(f"{n} ({o})" for n, o in syms.items() if n not in known and not classified(n, o, pats))
    assert not missing, (
        "mutable globals neither serialized nor in docs/coop-design/serialization-audit.md "
        "(serialize them or classify them there):\n  " + "\n  ".join(missing)
    )
