---
name: windows-paths
description: |
  Access Windows files and drives from WSL (Windows Subsystem for Linux).
  
  **When to use this skill:**
  (1) Converting Windows paths to WSL paths
  (2) Accessing files on Windows drives (C:, D:, etc.)
  (3) Navigating between Windows and Linux file systems
  (4) Running Windows executables from WSL
  
  **When NOT to use:**
  - Native Linux paths (no conversion needed)
  - Network paths (use standard networking tools)
license: PROPRIETARY. LICENSE file has complete terms.
---

# Windows Paths in WSL

WSL mounts Windows drives at `/mnt/`. Each drive letter becomes a lowercase directory.

## Path Conversion

| Windows Path | WSL Path |
|--------------|----------|
| `C:\Users\name` | `/mnt/c/Users/name` |
| `D:\data\file.txt` | `/mnt/d/data/file.txt` |
| `E:\projects` | `/mnt/e/projects` |

## Quick Reference

### Access Windows C: drive

```bash
ls /mnt/c/
ls /mnt/c/Users/
```

### Access Windows D: drive

```bash
ls /mnt/d/
cd /mnt/d/doyles\ bayesian\ optimization/
```

### Convert Windows path to WSL

Replace backslashes with forward slashes, prepend `/mnt/`, lowercase the drive letter:

```bash
# Windows: D:\folder\file.txt
# WSL:     /mnt/d/folder/file.txt
```

### Handle spaces in paths

Use quotes or escape spaces:

```bash
ls "/mnt/d/doyles bayesian optimization/"
ls /mnt/d/doyles\ bayesian\ optimization/
```

### Access current Windows user directory

```bash
cd /mnt/c/Users/$USER
cd /mnt/c/Users/$(whoami)
```

### Run Windows executables

```bash
/mnt/c/Windows/System32/notepad.exe
/mnt/c/Program\ Files/App/app.exe
```

## Examples

### Read a file from Windows

```bash
cat /mnt/d/data/experiments.csv
```

### Copy file from Windows to Linux

```bash
cp /mnt/d/data/file.txt ~/workspace/
```

### Copy file from Linux to Windows

```bash
cp ~/workspace/file.txt /mnt/d/data/
```

### Run Python script on Windows files

```bash
python3 script.py /mnt/d/data/input.csv
```

## Common Issues

**Permission denied:**
- Windows files may have different permissions
- Use `chmod` or run with appropriate user

**Path not found:**
- Check drive is mounted: `ls /mnt/`
- Verify path exists: `ls -la /mnt/d/`

**Executable won't run:**
- Windows executables need `.exe` extension
- Use full path or add to PATH

## Script Helper

Use the helper script to convert paths:

```bash
python ~/.openclaw/workspace/skills/windows-paths/scripts/winpath.py "D:\folder\file.txt"
# Output: /mnt/d/folder/file.txt
```
