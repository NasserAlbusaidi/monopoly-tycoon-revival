# Monopoly Tycoon Revival — Design

- **Date:** 2026-08-27
- **Status:** Approved, not yet implemented
- **Target game:** Monopoly Tycoon (2001, Deep Red Games / Infogrames), 32-bit, DirectX 8

## Goal

Make Monopoly Tycoon install and run on Windows 11, then let people edit its
gameplay rules and author new maps. Release the result publicly so strangers can
use it.

## Scope

**In scope**

- A reproducible install and fix procedure for Windows 11.
- Gameplay tuning through the game's Lua settings files.
- New and edited maps through the game's Lua map scripts.
- A documented format specification for the `archive.DIR` / `archive.bin` pair,
  plus a read-only extractor. This is a bonus deliverable, not the critical path.

**Out of scope**

- `.gtd` textures, `.tt` textures, `.tm` meshes, and `BuildFile.dat` models.
- Audio and music replacement.
- Widescreen support.
- GameSpy multiplayer. The servers are dead. Reviving them is a different project.

## Findings that shape this design

All findings below come from the shipped CD contents at
`D:\personal\reviving-games\monopoly-tycoon\`.

### 1. Gameplay is plain-text Lua — verified

The 200 `.lua` files ship inside the InstallShield 6 cab set
(`data1.hdr` + `data1.cab` + `data2.cab`, magic `ISc(`, version `0x0100600C`).

- 171 files are plain-text Lua source. Zero are bytecode — no `1B 4C 75 61`
  header appears anywhere.
- 29 files ship genuinely empty (0 bytes), including `DEFAULT\buildingsettings.lua`.
  The building and business schema lives in `businesssettings.lua` and
  `blocksettings.lua` instead.
- All 200 were checked against the MD5 digests stored in the cab descriptors.
  200/200 match.

Verified twice: extracted and MD5-checked by a subagent, then the file contents
were read directly. Representative lines:

```lua
BusinessInfo[ANTIQUE_STORE].openingtime = 9;
BusinessInfo[ANTIQUE_STORE].stockcapacity = 3;
Block[ORIENTAL_AVENUE].value = 1000;
Block[ORIENTAL_AVENUE]:Distribution(RETAIL, 25);
index = AddBuilding("ILLINOIS_AVENUE", 0, 0, 2, 2, 1, "RETAIL", 240, "low");
```

The scripts are grouped into 53 namespaces: `DEFAULT`, `MAPS`, `SCENARIO1`–`SCENARIO20`,
`TUTORIAL1`–`TUTORIAL12`, `NET0`–`NET8`, `LEVEL1`–`LEVEL3`, `FRONTEND`, and the
cutscene sets. Every scenario and tutorial is script-driven.

**Consequence:** gameplay tuning and map authoring need a text editor, not a
decompiler. This removed the largest risk in the original design.

### 2. `archive.bin` holds no scripts — verified

The archive holds 1506 entries: 17 `.gtd` texture pages, 1021 `.tt` raw textures,
468 `.tm` meshes. No Lua. Its contents are exactly the asset classes this project
scopes out.

**Consequence:** the archive tooling is not required for the stated goals. It is
demoted to a bonus deliverable.

### 3. The archive format is solved — verified

`archive.DIR` is a 32-byte header (`u32 version=3`, `u32 count=1506`,
`u32 unknown=1`, 20 zero bytes) followed by 1506 fixed records of 308 bytes.
`32 + 1506 * 308 = 463880`, which is the exact file size.

| Offset | Width | Field |
|---|---|---|
| 0x000 | 260 | `path`, NUL-terminated ASCII, zero-padded to MAX_PATH |
| 0x104 | u32 | `offset` into `archive.bin` |
| 0x108 | u32 | `size` of payload |
| 0x10C | u32 | `checksum`, a 32-bit sum of the payload bytes |
| 0x110 | u8 | `flag_a`, constant 1 |
| 0x111 | u8 | `flag_b`, 0 for the four textures above 640 resolution, else 1 |
| 0x112 | u32 | `tt_flags`, `.tt` only, mirrors payload dword +4 |
| 0x116 | u32 | `tt_id`, a strictly increasing opaque counter; copy through |
| 0x11A | u32 | `tt_width`, mirrors payload dword +8 |
| 0x11E | u32 | `tt_height`, mirrors payload dword +12 |
| 0x122 | 18 | padding, all zero |

Validation across all 1506 entries: every `offset + size` falls in bounds; the
entries tile `archive.bin` with zero gaps and zero overlaps, ending exactly on
byte 51,033,183; index order equals offset order. Nothing is compressed or
encrypted.

Two shipped anomalies, both build-tool artifacts rather than layout gaps:

- Record 1004 (`GenericTextures800\textures.gtd`) stores a checksum 2 higher than
  the true payload sum. 1505/1506 otherwise match exactly.
- Seven `.tt` records set bit `0x2` index-side but not payload-side.

A repacker copies both through unchanged.

**Confidence:** the layout explains 1506/1506 records. The two residuals are
characterized data anomalies, not unknowns.

### 4. `D:\personal` is a git repository — resolved

The game media sat untracked and un-ignored inside it. `reviving-games/` is now
in `D:\personal\.gitignore`. `git ls-files` confirms nothing from that directory
was ever committed.

## Architecture

The project lives in its own repository at
`D:\personal\reviving-games\monopoly-tycoon-revival`, separate from the
`D:\personal` hub repository.

**The repository ships tools, documentation, and configuration only. It contains
no game assets, no extracted Lua, and no ISO.** Users bring their own disc. This
keeps the public release legally clean and is a hard rule, not a preference.

Three components, each with one job:

| Component | Purpose | Depends on |
|---|---|---|
| `fixpack` | Install as code: direct cab extraction, patch 1.2, D3D8 configuration, launcher. | nothing |
| `mtdata` | Documents and validates the Lua settings and map schema. Ships example mods as patches. | nothing |
| `mtarc` | Bonus. Reads `archive.DIR` / `archive.bin` and extracts entries. | nothing |

### How mods are distributed

A mod must never ship as a modified copy of the game's Lua. That is a derivative
of Infogrames content and breaks the rule above. Mods ship in one of two forms:

- a unified diff applied against the user's own installed file, or
- an overlay script that sets named values on the user's own file.

The distinction matters for the demo mod in Phase 2 and for anything a
contributor later submits.

`fixpack` extracts the cabs directly instead of running `Setup.exe`. InstallShield's
`ikernel.exe` is the usual failure point on 64-bit Windows, and direct extraction
is scriptable where `Setup.exe` is not. A working Python IS6 extractor already
exists from the research phase and becomes the basis for this component.

## Phases

### Phase 0 — Boot it. This is a gate.

Install using direct cab extraction. Apply `MTPatch1_2.exe`. Launch the game.
Record every failure.

Phase 0 must answer two questions before later phases are worth building:

1. Does the game run on Windows 11, and what does it need — a D3D8 wrapper, a
   no-CD approach, a compatibility shim?
2. **Do the `.lua` files sit loose on disk after install and patching?** If yes,
   a mod is an edited text file and `mtarc` is never needed. If the engine reads
   them from a container instead, the modding path changes and this design is
   revised before continuing.

Patch 1.2 may replace the Lua files. Phase 0 checks this.

**Exit criteria:** the game reaches its main menu, and the location and format of
the runtime Lua files is known and written down.

### Phase 1 — `fixpack`

Turn the Phase 0 procedure into a script.

**Exit criteria:** a fresh Windows profile goes from mounted ISO to running game
with one command.

### Phase 2 — `mtdata` and a demo mod

Document the settings schema from `businesssettings.lua`, `blocksettings.lua`,
`commoditysettings.lua`, `ai.lua`, and the `MAPS` scripts. Build a validator that
catches malformed edits before the game loads them.

**Exit criteria:** one mod that visibly changes play, and one new or edited map
that loads. A modding toolkit with no working mod is a claim, not a result.

### Phase 3 — `mtarc` (bonus)

Publish the format specification and a read-only extractor. Skip the writer
unless Phase 0 proves it necessary.

**Exit criteria:** the extractor lists and extracts all 1506 entries and their
checksums validate at the rate recorded above.

### Phase 4 — Ship

README, LICENSE, tagged release, and an announcement posted to a place where
Monopoly Tycoon players will see it.

**Exit criteria:** a stranger can install it, and has been told it exists.

## Testing

`mtdata` and `mtarc` get real tests. `fixpack` cannot be tested honestly and gets
labelled accordingly.

- **`mtarc`:** the game archive cannot be committed, so tests use two fixtures —
  a small synthetic archive generated by the test suite and committed, and an
  opt-in test against a local game copy that skips when absent.
- **`mtdata`:** table-driven tests over the settings schema, covering a clean
  case, a warning case, and a malformed case.
- **`fixpack`:** verified by a recorded install on a fresh Windows profile. Any
  claim about it says "verified on one machine", never "works".

## Risks

| Risk | Severity | Status |
|---|---|---|
| Lua is bytecode, so new maps are impossible | was highest | **Eliminated.** It is plain text. |
| Archive checksum cannot be reproduced | was high | **Eliminated.** It is a byte sum. |
| Patch 1.2 replaces the loose Lua files | medium | Open. Phase 0 answers it. |
| Game does not launch on Windows 11 at all | medium | Open. Phase 0 answers it. |
| The engine reads scripts from a container, not loose files | medium | Open. Phase 0 answers it. |
| Map schema is too coupled to binary road data to author new maps | medium | Open. `RoadNodes.bin` and `route_smalltable.bin` exist and are not yet examined. |
| D3D8 on Windows 11 | low | Well-trodden ground. |

## Open questions carried into Phase 0

- Where do the Lua files live after install and patching?
- Does `MAPS\*.lua` fully describe a map, or does it reference `RoadNodes.bin`
  and `route_smalltable.bin` in ways that block authoring a new one?
- What is the maximum in-game resolution? The asset tree contains `font800` and
  `font1024` texture sets, which suggests 1024 is the ceiling.
- Twenty-nine Lua files ship empty. Is that intentional, or does the patch fill them?
