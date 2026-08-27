---
name: Bug report
about: The game or the tool does not do what the docs say
labels: bug
---

## What happened

<!-- What you did, what you expected, what you saw. -->

## Environment

- Windows version (`winver`):
- Output of `mtrevival check` (it prints the game version by hash):

```
paste here
```

- `config.cfg` in the game folder:

```
paste here
```

## Evidence

- Attach `D3DEnum.txt` from the game folder (it is a text log the game writes, not game content).
- If the game crashed: the Application event log entry for `mc.exe` (Event Viewer → Windows Logs → Application), with the fault offset.
- If music is involved: run the game with `WMSOURCE_SHIM_LOG=<file>` set and attach the file.

**Do not attach game files** (Lua, `.wma`, archives, the installer).
