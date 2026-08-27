# Phase 0 — Boot the Game — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Monopoly Tycoon on Windows 11, launch it, and answer the three gate questions that decide the shape of every later phase.

**Architecture:** Build a tested InstallShield 6 cab reader first, because it is the one piece of Phase 0 that is pure code and can be proven without a running game. Use it to produce a verifiable manifest of the CD. Then install the game by the stock route, inspect the result, and record what is true.

**Tech Stack:** Python 3.12.10 (`C:\Python312\python.exe`), pytest, stdlib only for the library itself (`struct`, `zlib`, `hashlib`, `dataclasses`).

## Global Constraints

- **No game content in the repository, ever.** No `.lua`, `.cab`, `.iso`, `.tt`, `.gtd`, `.tm`, `.wav`, `.wma`, or extracted assets. The `.gitignore` blocks these by extension. File paths, sizes, and MD5 digests are facts about content, not content, and may be committed.
- **Library code is stdlib-only.** pytest is a test dependency, not a runtime one.
- **Conventional commits. No AI attribution in commit messages** — no `Co-Authored-By`, no generated-with footer.
- Game CD root: `D:\personal\reviving-games\monopoly-tycoon`
- Install target for testing: `D:\Games\Monopoly Tycoon` (the `D:\Games` directory already exists).
- Patch: `D:\personal\reviving-games\monopoly-tycoon\Extras\Patch\MTPatch1_2.exe`
- Repository root: `D:\personal\reviving-games\monopoly-tycoon-revival`
- Two tasks (4 and 6) require Nasser at the keyboard. They are observation tasks, not code tasks. A claim about them says what was observed, never what was assumed.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, pytest configuration |
| `src/mtrevival/__init__.py` | Package marker |
| `src/mtrevival/iscab.py` | InstallShield 6 cab set: parse the header, extract a member |
| `src/mtrevival/manifest.py` | Build and compare a CD manifest (path, size, md5) |
| `src/mtrevival/__main__.py` | CLI entry point |
| `tests/test_iscab.py` | Unit tests on synthetic headers and blobs |
| `tests/test_manifest.py` | Manifest schema and determinism |
| `tests/test_real_cd.py` | Opt-in integration tests, skipped when the CD is absent |
| `tests/conftest.py` | `cd_root` fixture and skip logic |
| `scripts/inspect_install.py` | Answers the gate questions against an installed game |
| `data/cd-manifest.json` | Committed manifest of the EN ISO |
| `docs/phase-0-findings.md` | The Phase 0 record. Written in Task 7. |

The cab reader serves `fixpack` from the spec. It lives under `mtrevival` because `manifest.py` and later `fixpack` both consume it.

---

### Task 1: Project scaffolding and the cab header parser

**Files:**
- Create: `pyproject.toml`, `src/mtrevival/__init__.py`, `src/mtrevival/iscab.py`, `tests/test_iscab.py`, `tests/conftest.py`
- Test: `tests/test_iscab.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `mtrevival.iscab.CabFile` (frozen dataclass with fields `index: int`, `directory: str`, `name: str`, `flags: int`, `expanded_size: int`, `compressed_size: int`, `offset: int`, `volume: int`), `mtrevival.iscab.read_cstring(data: bytes, pos: int) -> str`, `mtrevival.iscab.parse_header(data: bytes) -> list[CabFile]`.

- [ ] **Step 1: Create the virtual environment and install pytest**

```bash
cd "D:/personal/reviving-games/monopoly-tycoon-revival"
python -m venv .venv
.venv/Scripts/python.exe -m pip install --quiet --upgrade pip pytest
.venv/Scripts/python.exe -m pytest --version
```

Expected: prints a pytest version. `.venv/` is already gitignored.

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "mtrevival"
version = "0.1.0"
description = "Tools for installing and modding Monopoly Tycoon (2001)"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = ["real_cd: needs the game CD present"]
```

- [ ] **Step 3: Create `src/mtrevival/__init__.py`**

```python
"""Tools for installing and modding Monopoly Tycoon (2001)."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write the failing tests**

Create `tests/test_iscab.py`. The `build_fake_hdr` helper constructs a minimal
InstallShield 6 header so the parser is tested on bytes we own, not on game data.

```python
import struct

import pytest

from mtrevival.iscab import CabFile, parse_header, read_cstring


def test_read_cstring_stops_at_nul():
    data = b"hello\x00world\x00"
    assert read_cstring(data, 0) == "hello"
    assert read_cstring(data, 6) == "world"


def test_read_cstring_raises_when_unterminated():
    with pytest.raises(ValueError, match="unterminated"):
        read_cstring(b"nonul", 0)


def build_fake_hdr(entries):
    """Build a minimal IS6 header.

    entries: list of (directory, name, flags, expanded, compressed, offset, volume)
    Layout: 16-byte prologue, then the common descriptor, then the file table
    region.  Inside the file table region: the directory offset array, then the
    string pool, then the fixed 0x57-byte file records.
    """
    dirs = []
    for entry in entries:
        if entry[0] not in dirs:
            dirs.append(entry[0])

    strings = bytearray()
    string_at = {}

    def intern(text):
        if text not in string_at:
            string_at[text] = len(strings)
            strings.extend(text.encode("latin1") + b"\x00")
        return string_at[text]

    dir_array_len = len(dirs) * 4
    dir_offsets = [intern(d) for d in dirs]
    name_offsets = [intern(e[1]) for e in entries]
    # String pool sits after the directory offset array.
    shift = dir_array_len
    dir_offsets = [o + shift for o in dir_offsets]
    name_offsets = [o + shift for o in name_offsets]

    records = bytearray()
    for directory, name, flags, expanded, compressed, offset, volume in entries:
        rec = bytearray(0x57)
        struct.pack_into("<H", rec, 0, flags)
        struct.pack_into("<Q", rec, 2, expanded)
        struct.pack_into("<Q", rec, 10, compressed)
        struct.pack_into("<Q", rec, 18, offset)
        struct.pack_into("<I", rec, 58, name_offsets[len(records) // 0x57])
        struct.pack_into("<H", rec, 62, dirs.index(directory))
        struct.pack_into("<H", rec, 85, volume)
        records.extend(rec)

    ft_off2 = dir_array_len + len(strings)
    file_table = bytearray()
    for off in dir_offsets:
        file_table.extend(struct.pack("<I", off))
    file_table.extend(strings)
    file_table.extend(records)

    cdo = 0x40
    descriptor = bytearray(0x30)
    ft_off = 0x100  # file table sits this far past the descriptor start
    struct.pack_into("<I", descriptor, 0x0C, ft_off)
    struct.pack_into("<I", descriptor, 0x1C, len(dirs))
    struct.pack_into("<I", descriptor, 0x28, len(entries))
    struct.pack_into("<I", descriptor, 0x2C, ft_off2)

    blob = bytearray(cdo + ft_off)
    struct.pack_into("<I", blob, 12, cdo)
    blob[cdo:cdo + len(descriptor)] = descriptor
    blob.extend(file_table)
    return bytes(blob)


def test_parse_header_reads_one_entry():
    hdr = build_fake_hdr([("DEFAULT", "ai.lua", 0x4, 1234, 567, 890, 1)])
    files = parse_header(hdr)
    assert len(files) == 1
    entry = files[0]
    assert entry == CabFile(
        index=0,
        directory="DEFAULT",
        name="ai.lua",
        flags=0x4,
        expanded_size=1234,
        compressed_size=567,
        offset=890,
        volume=1,
    )


def test_parse_header_reads_multiple_directories():
    hdr = build_fake_hdr([
        ("DEFAULT", "ai.lua", 0x4, 10, 5, 0, 1),
        ("MAPS", "sparsemap.lua", 0x0, 20, 20, 100, 2),
    ])
    files = parse_header(hdr)
    assert [f.directory for f in files] == ["DEFAULT", "MAPS"]
    assert [f.name for f in files] == ["ai.lua", "sparsemap.lua"]
    assert files[1].volume == 2


def test_parse_header_rejects_short_input():
    with pytest.raises(ValueError, match="too short"):
        parse_header(b"\x00" * 4)
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_iscab.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'mtrevival.iscab'`

- [ ] **Step 6: Write `src/mtrevival/iscab.py`**

```python
"""Reader for InstallShield 6 cab sets (magic ``ISc(``, version 0x0100600C).

The header file (``data1.hdr``) carries a common descriptor which locates a
file table.  The file table holds a directory offset array, a string pool, and
fixed 0x57-byte file records.  Payloads live in the numbered volumes
(``data1.cab``, ``data2.cab``, ...).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

RECORD_SIZE = 0x57
FLAG_COMPRESSED = 0x4

_DESC_PTR = 12
_DESC_FILE_TABLE_OFFSET = 0x0C
_DESC_DIR_COUNT = 0x1C
_DESC_FILE_COUNT = 0x28
_DESC_FILE_TABLE_OFFSET2 = 0x2C

_REC_FLAGS = 0
_REC_EXPANDED = 2
_REC_COMPRESSED = 10
_REC_OFFSET = 18
_REC_NAME_OFFSET = 58
_REC_DIR_INDEX = 62
_REC_VOLUME = 85


@dataclass(frozen=True)
class CabFile:
    """One member of a cab set."""

    index: int
    directory: str
    name: str
    flags: int
    expanded_size: int
    compressed_size: int
    offset: int
    volume: int

    @property
    def path(self) -> str:
        """Windows-style path of this member inside the install tree."""
        return f"{self.directory}\\{self.name}" if self.directory else self.name

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)


def read_cstring(data: bytes, pos: int) -> str:
    """Read a NUL-terminated latin1 string starting at ``pos``."""
    end = data.find(b"\x00", pos)
    if end == -1:
        raise ValueError(f"unterminated string at offset {pos}")
    return data[pos:end].decode("latin1")


def parse_header(data: bytes) -> list[CabFile]:
    """Parse ``data1.hdr`` into a list of members, in file-table order."""
    if len(data) < 16:
        raise ValueError(f"header too short: {len(data)} bytes")

    cdo = struct.unpack_from("<I", data, _DESC_PTR)[0]
    if cdo + 0x30 > len(data):
        raise ValueError(f"header too short for descriptor at {cdo}")

    file_table_offset = struct.unpack_from("<I", data, cdo + _DESC_FILE_TABLE_OFFSET)[0]
    dir_count = struct.unpack_from("<I", data, cdo + _DESC_DIR_COUNT)[0]
    file_count = struct.unpack_from("<I", data, cdo + _DESC_FILE_COUNT)[0]
    records_offset = struct.unpack_from("<I", data, cdo + _DESC_FILE_TABLE_OFFSET2)[0]

    table = cdo + file_table_offset
    if table + dir_count * 4 > len(data):
        raise ValueError("header too short for directory table")

    directories = [
        read_cstring(data, table + struct.unpack_from("<I", data, table + 4 * i)[0])
        for i in range(dir_count)
    ]

    base = table + records_offset
    if base + file_count * RECORD_SIZE > len(data):
        raise ValueError("header too short for file records")

    files: list[CabFile] = []
    for i in range(file_count):
        rec = data[base + i * RECORD_SIZE : base + (i + 1) * RECORD_SIZE]
        dir_index = struct.unpack_from("<H", rec, _REC_DIR_INDEX)[0]
        if dir_index >= len(directories):
            raise ValueError(f"record {i} names directory {dir_index}, only {len(directories)} exist")
        name_offset = struct.unpack_from("<I", rec, _REC_NAME_OFFSET)[0]
        files.append(
            CabFile(
                index=i,
                directory=directories[dir_index],
                name=read_cstring(data, table + name_offset),
                flags=struct.unpack_from("<H", rec, _REC_FLAGS)[0],
                expanded_size=struct.unpack_from("<Q", rec, _REC_EXPANDED)[0],
                compressed_size=struct.unpack_from("<Q", rec, _REC_COMPRESSED)[0],
                offset=struct.unpack_from("<Q", rec, _REC_OFFSET)[0],
                volume=struct.unpack_from("<H", rec, _REC_VOLUME)[0],
            )
        )
    return files
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_iscab.py -v`
Expected: 5 passed.

- [ ] **Step 8: Create `tests/conftest.py`**

```python
import os
from pathlib import Path

import pytest

DEFAULT_CD = Path(r"D:\personal\reviving-games\monopoly-tycoon")


@pytest.fixture(scope="session")
def cd_root() -> Path:
    """Root of the game CD.  Override with the MT_CD_ROOT environment variable."""
    root = Path(os.environ.get("MT_CD_ROOT", DEFAULT_CD))
    header = root / "Monopoly Tycoon" / "data1.hdr"
    if not header.is_file():
        pytest.skip(f"game CD not present at {root}")
    return root
```

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src tests
git commit -m "feat(iscab): parse InstallShield 6 cab headers"
```

---

### Task 2: Extract cab members

**Files:**
- Modify: `src/mtrevival/iscab.py`
- Modify: `tests/test_iscab.py`

**Interfaces:**
- Consumes: `CabFile`, `parse_header` from Task 1.
- Produces: `mtrevival.iscab.decompress_chunks(blob: bytes, expanded_size: int) -> bytes` and `mtrevival.iscab.CabSet` with `CabSet.open(cd_dir: Path) -> CabSet`, `CabSet.files: list[CabFile]`, `CabSet.extract(entry: CabFile) -> bytes`, and `CabSet.close() -> None`. `CabSet` is a context manager.

The spike guessed at the framing with `if chunk[:1] != b'x'`. InstallShield 6 stores
each chunk as a `u16` length followed by a raw deflate stream with no zlib wrapper.
Decode it as raw deflate every time, and let a failure raise rather than fall back.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_iscab.py`:

```python
import zlib

from mtrevival.iscab import CabSet, decompress_chunks


def make_chunked(payload: bytes, chunk_size: int) -> bytes:
    """Frame a payload the way InstallShield 6 does: u16 length + raw deflate."""
    out = bytearray()
    for start in range(0, len(payload), chunk_size):
        piece = payload[start : start + chunk_size]
        comp = zlib.compressobj(9, zlib.DEFLATED, -15)
        blob = comp.compress(piece) + comp.flush()
        out.extend(struct.pack("<H", len(blob)))
        out.extend(blob)
    return bytes(out)


def test_decompress_chunks_single_chunk():
    payload = b"BusinessInfo[BAKERY].openingtime = 7;\n" * 4
    framed = make_chunked(payload, len(payload))
    assert decompress_chunks(framed, len(payload)) == payload


def test_decompress_chunks_multiple_chunks():
    payload = bytes(range(256)) * 40
    framed = make_chunked(payload, 1024)
    assert decompress_chunks(framed, len(payload)) == payload


def test_decompress_chunks_detects_size_overshoot():
    """A chunk decoding to more than the declared size is a corrupt entry."""
    framed = make_chunked(b"abcdef", 6)
    with pytest.raises(ValueError, match="expected 4 bytes, decoded 6"):
        decompress_chunks(framed, 4)


def test_decompress_chunks_detects_size_undershoot():
    """Running out of chunks before the declared size is also corruption."""
    framed = make_chunked(b"abcdef", 6)
    with pytest.raises(ValueError, match="truncated chunk header"):
        decompress_chunks(framed, 99)


def test_decompress_chunks_rejects_truncated_frame():
    with pytest.raises(ValueError, match="truncated"):
        decompress_chunks(b"\x40\x00\x01\x02", 10)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_iscab.py -k decompress -v`
Expected: FAIL, `ImportError: cannot import name 'decompress_chunks'`

- [ ] **Step 3: Add the implementation to `src/mtrevival/iscab.py`**

Add these imports at the top: `import zlib`, `from pathlib import Path`,
`from types import TracebackType`, `from typing import BinaryIO`.

```python
def decompress_chunks(blob: bytes, expanded_size: int) -> bytes:
    """Decode an InstallShield 6 chunked stream: ``u16`` length + raw deflate."""
    out = bytearray()
    pos = 0
    while len(out) < expanded_size:
        if pos + 2 > len(blob):
            raise ValueError(f"truncated chunk header at offset {pos}")
        (length,) = struct.unpack_from("<H", blob, pos)
        pos += 2
        chunk = blob[pos : pos + length]
        if len(chunk) != length:
            raise ValueError(f"truncated chunk body at offset {pos}: want {length}, got {len(chunk)}")
        pos += length
        out.extend(zlib.decompressobj(-15).decompress(chunk))
    if len(out) != expanded_size:
        raise ValueError(f"expected {expanded_size} bytes, decoded {len(out)}")
    return bytes(out)


class CabSet:
    """An opened InstallShield 6 cab set: one header plus its volumes."""

    def __init__(self, files: list[CabFile], volumes: dict[int, Path]) -> None:
        self.files = files
        self._volume_paths = volumes
        self._handles: dict[int, BinaryIO] = {}

    @classmethod
    def open(cls, cd_dir: Path) -> "CabSet":
        """Open the cab set in ``cd_dir`` (the directory holding data1.hdr)."""
        cd_dir = Path(cd_dir)
        header = cd_dir / "data1.hdr"
        if not header.is_file():
            raise FileNotFoundError(f"no data1.hdr in {cd_dir}")
        files = parse_header(header.read_bytes())
        volumes = {}
        for candidate in sorted(cd_dir.glob("data*.cab")):
            digits = "".join(c for c in candidate.stem if c.isdigit())
            if digits:
                volumes[int(digits)] = candidate
        if not volumes:
            raise FileNotFoundError(f"no data*.cab volumes in {cd_dir}")
        return cls(files, volumes)

    def extract(self, entry: CabFile) -> bytes:
        """Return the decoded bytes of one member."""
        if entry.expanded_size == 0:
            return b""
        if entry.volume not in self._volume_paths:
            raise KeyError(f"{entry.path} needs volume {entry.volume}, which is missing")
        if entry.volume not in self._handles:
            self._handles[entry.volume] = self._volume_paths[entry.volume].open("rb")
        handle = self._handles[entry.volume]
        handle.seek(entry.offset)
        if entry.is_compressed:
            return decompress_chunks(handle.read(entry.compressed_size), entry.expanded_size)
        data = handle.read(entry.expanded_size)
        if len(data) != entry.expanded_size:
            raise ValueError(f"{entry.path}: read {len(data)} of {entry.expanded_size} bytes")
        return data

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()

    def __enter__(self) -> "CabSet":
        return self

    def __exit__(self, exc_type, exc, tb: TracebackType | None) -> None:
        self.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_iscab.py -v`
Expected: 10 passed.

- [ ] **Step 5: Add the opt-in integration test**

Create `tests/test_real_cd.py`:

```python
import pytest

from mtrevival.iscab import CabSet

pytestmark = pytest.mark.real_cd


def test_real_cd_has_expected_lua_count(cd_root):
    with CabSet.open(cd_root / "Monopoly Tycoon") as cabs:
        lua = [f for f in cabs.files if f.name.lower().endswith(".lua")]
    assert len(lua) == 200


def test_real_cd_lua_is_plain_text_not_bytecode(cd_root):
    """The central Phase 0 premise: the scripts are source, not compiled chunks."""
    with CabSet.open(cd_root / "Monopoly Tycoon") as cabs:
        lua = [f for f in cabs.files if f.name.lower().endswith(".lua")]
        bytecode = []
        empty = 0
        for entry in lua:
            blob = cabs.extract(entry)
            if not blob:
                empty += 1
            elif blob[:4] == b"\x1bLua":
                bytecode.append(entry.path)
    assert bytecode == []
    assert empty == 29


def test_real_cd_business_settings_parses_as_expected_schema(cd_root):
    with CabSet.open(cd_root / "Monopoly Tycoon") as cabs:
        entry = next(
            f for f in cabs.files
            if f.name.lower() == "businesssettings.lua" and f.directory.upper() == "DEFAULT"
        )
        text = cabs.extract(entry).decode("latin1")
    assert "BusinessInfo[ANTIQUE_STORE].openingtime" in text
    assert text.lstrip().startswith("--")
```

- [ ] **Step 6: Run the integration tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_real_cd.py -v`
Expected: 3 passed. If the counts differ from 200 and 29, **stop and report the real numbers** — the spec records those figures and would need correcting.

- [ ] **Step 7: Commit**

```bash
git add src tests
git commit -m "feat(iscab): extract cab members with chunked deflate"
```

---

### Task 3: CD manifest

**Files:**
- Create: `src/mtrevival/manifest.py`, `src/mtrevival/__main__.py`, `tests/test_manifest.py`, `data/cd-manifest.json`

**Interfaces:**
- Consumes: `CabSet`, `CabFile` from Task 2.
- Produces: `mtrevival.manifest.build_manifest(cab_set: CabSet) -> dict` returning `{"format": 1, "entry_count": int, "entries": [{"path": str, "size": int, "md5": str}, ...]}` sorted by `path`; `mtrevival.manifest.compare(expected: dict, actual: dict) -> list[str]` returning human-readable difference lines, empty when identical.

The manifest records path, size, and MD5. Those are facts about the disc, not its
content, so committing them is allowed and lets a user verify their own copy matches.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manifest.py`:

```python
import hashlib

import pytest

from mtrevival.iscab import CabFile
from mtrevival.manifest import build_manifest, compare


class FakeCabSet:
    def __init__(self, payloads):
        self.files = [
            CabFile(
                index=i,
                directory=d,
                name=n,
                flags=0,
                expanded_size=len(b),
                compressed_size=len(b),
                offset=0,
                volume=1,
            )
            for i, (d, n, b) in enumerate(payloads)
        ]
        self._payloads = {f.path: p[2] for f, p in zip(self.files, payloads)}

    def extract(self, entry):
        return self._payloads[entry.path]


def test_build_manifest_records_path_size_and_md5():
    body = b"Block[ORIENTAL_AVENUE].value = 1000;\n"
    result = build_manifest(FakeCabSet([("DEFAULT", "blocksettings.lua", body)]))
    assert result["format"] == 1
    assert result["entry_count"] == 1
    assert result["entries"] == [
        {
            "path": "DEFAULT\\blocksettings.lua",
            "size": len(body),
            "md5": hashlib.md5(body).hexdigest(),
        }
    ]


def test_build_manifest_sorts_entries_by_path():
    result = build_manifest(
        FakeCabSet([("MAPS", "sparsemap.lua", b"z"), ("DEFAULT", "ai.lua", b"a")])
    )
    assert [e["path"] for e in result["entries"]] == [
        "DEFAULT\\ai.lua",
        "MAPS\\sparsemap.lua",
    ]


def test_compare_returns_nothing_when_identical():
    manifest = build_manifest(FakeCabSet([("DEFAULT", "ai.lua", b"a")]))
    assert compare(manifest, manifest) == []


def test_compare_reports_missing_extra_and_changed():
    left = build_manifest(
        FakeCabSet([("DEFAULT", "ai.lua", b"a"), ("DEFAULT", "gone.lua", b"g")])
    )
    right = build_manifest(
        FakeCabSet([("DEFAULT", "ai.lua", b"CHANGED"), ("DEFAULT", "new.lua", b"n")])
    )
    lines = compare(left, right)
    assert any("missing" in l and "gone.lua" in l for l in lines)
    assert any("unexpected" in l and "new.lua" in l for l in lines)
    assert any("differs" in l and "ai.lua" in l for l in lines)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_manifest.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'mtrevival.manifest'`

- [ ] **Step 3: Write `src/mtrevival/manifest.py`**

```python
"""Manifest of a Monopoly Tycoon CD: path, size, and MD5 for every cab member.

The manifest holds facts about the disc, never its content, so it is safe to
commit and lets a user check their own copy against a known-good release.
"""

from __future__ import annotations

import hashlib
from typing import Any

FORMAT_VERSION = 1


def build_manifest(cab_set: Any) -> dict:
    """Build a manifest from an opened cab set."""
    entries = []
    for entry in cab_set.files:
        blob = cab_set.extract(entry)
        entries.append(
            {
                "path": entry.path,
                "size": len(blob),
                "md5": hashlib.md5(blob).hexdigest(),
            }
        )
    entries.sort(key=lambda e: e["path"])
    return {"format": FORMAT_VERSION, "entry_count": len(entries), "entries": entries}


def compare(expected: dict, actual: dict) -> list[str]:
    """Return one line per difference.  An empty list means the two match."""
    left = {e["path"]: e for e in expected["entries"]}
    right = {e["path"]: e for e in actual["entries"]}
    lines = []
    for path in sorted(set(left) - set(right)):
        lines.append(f"missing: {path}")
    for path in sorted(set(right) - set(left)):
        lines.append(f"unexpected: {path}")
    for path in sorted(set(left) & set(right)):
        if left[path]["md5"] != right[path]["md5"]:
            lines.append(
                f"differs: {path} (expected md5 {left[path]['md5']}, got {right[path]['md5']})"
            )
    return lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_manifest.py -v`
Expected: 4 passed.

- [ ] **Step 5: Write the CLI at `src/mtrevival/__main__.py`**

```python
"""Command line entry point: python -m mtrevival ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mtrevival.iscab import CabSet
from mtrevival.manifest import build_manifest, compare


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mtrevival")
    sub = parser.add_subparsers(dest="command", required=True)

    p_manifest = sub.add_parser("manifest", help="write a manifest of a game CD")
    p_manifest.add_argument("--cd", required=True, type=Path, help="CD root directory")
    p_manifest.add_argument("-o", "--output", required=True, type=Path)

    p_verify = sub.add_parser("verify", help="check a CD against a stored manifest")
    p_verify.add_argument("--cd", required=True, type=Path)
    p_verify.add_argument("--manifest", required=True, type=Path)

    p_list = sub.add_parser("list", help="list cab members")
    p_list.add_argument("--cd", required=True, type=Path)
    p_list.add_argument("--suffix", default="", help="only paths ending with this")

    args = parser.parse_args(argv)
    cab_dir = args.cd / "Monopoly Tycoon"

    if args.command == "manifest":
        with CabSet.open(cab_dir) as cabs:
            data = build_manifest(cabs)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {data['entry_count']} entries to {args.output}")
        return 0

    if args.command == "verify":
        expected = json.loads(args.manifest.read_text(encoding="utf-8"))
        with CabSet.open(cab_dir) as cabs:
            actual = build_manifest(cabs)
        lines = compare(expected, actual)
        if not lines:
            print(f"OK: {actual['entry_count']} entries match {args.manifest}")
            return 0
        for line in lines:
            print(line)
        print(f"{len(lines)} difference(s)")
        return 1

    with CabSet.open(cab_dir) as cabs:
        for entry in cabs.files:
            if entry.path.lower().endswith(args.suffix.lower()):
                print(f"{entry.expanded_size:>10}  vol{entry.volume}  {entry.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Generate and commit the manifest for this CD**

```bash
.venv/Scripts/python.exe -m mtrevival manifest \
  --cd "D:/personal/reviving-games/monopoly-tycoon" \
  -o data/cd-manifest.json
.venv/Scripts/python.exe -m mtrevival verify \
  --cd "D:/personal/reviving-games/monopoly-tycoon" \
  --manifest data/cd-manifest.json
```

Expected: the manifest command reports an entry count; the verify command prints `OK`.
Record the entry count — it goes into the findings document in Task 7.

- [ ] **Step 7: Commit**

`data/cd-manifest.json` must be force-added, because the `.gitignore` blocks
`*.dat`-style content patterns and we want the check to be deliberate. Confirm
first that the file holds only paths, sizes, and digests.

```bash
head -20 data/cd-manifest.json
git add src tests data/cd-manifest.json
git commit -m "feat(manifest): record CD contents as path, size, and md5"
```

---

### Task 4: Install the game — Nasser at the keyboard

**Files:**
- Create: `docs/phase-0-install-log.md`

This task is observation, not code. It cannot be verified from a shell, and no
claim about it may be made without Nasser reporting what he saw.

**Try the stock installer first.** The claim that InstallShield's `ikernel.exe`
fails on 64-bit Windows comes from general knowledge, not from anything observed
on this machine. Do not build a workaround for a problem that has not appeared.

- [ ] **Step 1: Run the stock installer**

Nasser runs `D:\personal\reviving-games\monopoly-tycoon\MTInstall.exe`, installing to
`D:\Games\Monopoly Tycoon`.

Record in `docs/phase-0-install-log.md`: whether it launched, any error dialog
text verbatim, whether it completed, and the installed size.

- [ ] **Step 2: If and only if the stock installer failed, extract the cabs directly**

First confirm the cab set reads:

```bash
.venv/Scripts/python.exe -m mtrevival list --cd "D:/personal/reviving-games/monopoly-tycoon" --suffix .lua
```

Then save this as `scratch/extract_all.py` (the `scratch/` directory is
gitignored — this is a spike, and it becomes `fixpack` in Phase 1 once we know
what actually failed):

```python
"""Spike: extract every cab member to an install directory.

Usage: python scratch/extract_all.py "D:/Games/Monopoly Tycoon"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mtrevival.iscab import CabSet

CD = Path(r"D:\personal\reviving-games\monopoly-tycoon\Monopoly Tycoon")


def main(target: Path) -> int:
    written = failed = 0
    with CabSet.open(CD) as cabs:
        for entry in cabs.files:
            destination = target / entry.directory / entry.name
            try:
                blob = cabs.extract(entry)
            except Exception as error:  # spike: report and continue
                print(f"FAIL {entry.path}: {error}")
                failed += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(blob)
            written += 1
    print(f"wrote {written} files, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
```

Run it, then record the counts in the install log. Note that a direct extraction
produces no registry entries, which is what Step 3 tests.

- [ ] **Step 3: Apply patch 1.2**

Nasser runs `D:\personal\reviving-games\monopoly-tycoon\Extras\Patch\MTPatch1_2.exe`.

Record whether it found the installation. A patch that locates the game through a
registry key will refuse to run after a direct cab extraction. If it refuses,
record the exact message — that constrains `fixpack`'s design.

- [ ] **Step 4: Commit the log**

```bash
git add docs/phase-0-install-log.md
git commit -m "docs: record Windows 11 install attempt"
```

---

### Task 5: Answer the gate questions

**Files:**
- Create: `scripts/inspect_install.py`

**Interfaces:**
- Consumes: nothing from earlier tasks; it reads an installed game directory.
- Produces: a printed report. No importable interface.

- [ ] **Step 1: Write `scripts/inspect_install.py`**

```python
"""Report what an installed Monopoly Tycoon directory contains.

Phase 0 uses this to answer three questions:
  1. Do the .lua scripts sit loose on disk after install and patching?
  2. Did patch 1.2 replace them?
  3. What binary data sits next to the map scripts?

Usage: python scripts/inspect_install.py "D:/Games/Monopoly Tycoon"
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

LUA_BYTECODE_MAGIC = b"\x1bLua"
INTERESTING = {"roadnodes.bin", "route_smalltable.bin", "tycoon.bin", "buildfile.dat"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}")
        return 2

    by_suffix: Counter[str] = Counter()
    lua_files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file():
            by_suffix[path.suffix.lower()] += 1
            if path.suffix.lower() == ".lua":
                lua_files.append(path)

    print(f"=== {root} ===")
    print(f"total files: {sum(by_suffix.values())}")
    for suffix, count in by_suffix.most_common(15):
        print(f"  {suffix or '(none)':<12} {count}")

    print(f"\n=== lua on disk: {len(lua_files)} ===")
    if not lua_files:
        print("  NONE. The engine does not read loose .lua files from the install tree.")
        print("  This changes the modding path. Report before continuing.")
    bytecode = [p for p in lua_files if p.read_bytes()[:4] == LUA_BYTECODE_MAGIC]
    empty = [p for p in lua_files if p.stat().st_size == 0]
    print(f"  bytecode: {len(bytecode)}   empty: {len(empty)}")
    for path in bytecode[:10]:
        print(f"  BYTECODE {path.relative_to(root)}")

    for path in sorted(lua_files)[:5]:
        print(f"\n--- {path.relative_to(root)} ({path.stat().st_size} bytes)")
        print(path.read_bytes()[:200].decode("latin1", "replace"))

    print("\n=== md5 of every lua on disk (compare against the CD manifest) ===")
    for path in sorted(lua_files):
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        print(f"{digest}  {path.relative_to(root)}")

    print("\n=== binaries of interest ===")
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() in INTERESTING:
            print(f"{path.stat().st_size:>12}  {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Run it against the install**

```bash
.venv/Scripts/python.exe scripts/inspect_install.py "D:/Games/Monopoly Tycoon" \
  > docs/phase-0-inspect-output.txt
head -40 docs/phase-0-inspect-output.txt
```

- [ ] **Step 3: Answer the gate questions from the output**

Write the answers into `docs/phase-0-install-log.md`:

1. Are the `.lua` files loose on disk? Yes or no, with the count.
2. Did patch 1.2 change any of them? Compare the printed MD5 digests against
   `data/cd-manifest.json`. List every path whose digest differs.
3. Do `RoadNodes.bin` and `route_smalltable.bin` exist in the install tree, and
   how large are they?

If the answer to question 1 is no, **stop and report**. The spec's modding path
assumes loose files, and it needs revising before Phase 1.

- [ ] **Step 4: Commit**

```bash
git add scripts/inspect_install.py docs/phase-0-install-log.md docs/phase-0-inspect-output.txt
git commit -m "feat(inspect): report installed game layout and lua state"
```

---

### Task 6: Launch the game — Nasser at the keyboard

**Files:**
- Modify: `docs/phase-0-install-log.md`

This task cannot be verified from a shell. A 3D game reaching its main menu is
something only Nasser can confirm. Any statement about it says "observed by
Nasser on <date>", never "works".

- [ ] **Step 1: Launch and record**

Nasser runs the installed game. Record, in order:

- Did the process start? Did a window appear?
- Any error dialog, verbatim.
- Did it reach the main menu?
- Did it ask for the CD? The ISO can be mounted with
  `Mount-DiskImage -ImagePath "D:\personal\reviving-games\MONOPOLY_TYCOON.iso"`.
- What resolution did it run at, and does the options screen offer 1024x768?
- Does alt-tab return to the desktop cleanly?
- Is there sound?

- [ ] **Step 2: If it fails to render, record the failure before trying fixes**

Note the exact symptom — black screen, immediate exit, D3D error code. Do not
apply a wrapper yet. Phase 1 chooses the fix, and it should be chosen against an
observed symptom rather than a guessed one.

- [ ] **Step 3: Commit**

```bash
git add docs/phase-0-install-log.md
git commit -m "docs: record first launch on Windows 11"
```

---

### Task 7: Write the Phase 0 findings and close the gate

**Files:**
- Create: `docs/phase-0-findings.md`
- Modify: `docs/superpowers/specs/2026-08-27-monopoly-tycoon-revival-design.md`
- Create: `README.md`

- [ ] **Step 1: Write `docs/phase-0-findings.md`**

Cover, each as a plain statement with its evidence:

- Whether the game installs by the stock route on Windows 11.
- Whether patch 1.2 applies, and to which install layout.
- Whether the game launches, and what it needs to do so.
- Where the runtime `.lua` files live and whether the patch altered them.
- The manifest entry count and the real `.lua` and empty-file counts.
- What `RoadNodes.bin` and `route_smalltable.bin` are, and whether the map
  scripts appear to depend on them.
- Every open question that Phase 1 inherits.

- [ ] **Step 2: Update the spec's risk table**

Open the design spec and move each Phase 0 risk from `Open` to either
`Eliminated` or `Confirmed`, with one line of evidence. If a finding contradicts
the spec, correct the spec — the observation wins.

- [ ] **Step 3: Write a minimal `README.md`**

State what the project is, that it ships no game content and requires the user's
own disc, the Python version, how to run the tests, and the current status
(Phase 0 complete, Phase 1 next).

- [ ] **Step 4: Run the whole test suite**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: all pass. Record the exact count in the findings document. If anything
fails, the findings document says so verbatim.

- [ ] **Step 5: Commit**

```bash
git add docs README.md
git commit -m "docs: Phase 0 findings and gate decision"
```

---

## Definition of done for Phase 0

Phase 0 is complete when all four hold:

1. `pytest` passes, and the opt-in CD tests confirm the 200 `.lua` / 0 bytecode / 29 empty figures, or the findings document records the true figures instead.
2. The game is installed and its launch behaviour is recorded from observation.
3. The three gate questions in Task 5 have written answers.
4. The spec's risk table carries no `Open` rows for Phase 0 risks.

The gate opens only if the runtime `.lua` files are loose and editable on disk.
If they are not, Phase 1 is replanned before any `fixpack` code is written.
