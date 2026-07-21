#!/usr/bin/env python3
"""
Windows path converter for WSL
Converts Windows paths to WSL paths
"""
import sys
import re

def windows_to_wsl(win_path):
    """Convert Windows path to WSL path"""
    # Normalize backslashes to forward slashes
    path = win_path.replace('\\', '/')
    
    # Handle drive letter (e.g., C:, D:)
    match = re.match(r'^([A-Za-z]):(/.*)?$', path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2) or ''
        return f'/mnt/{drive}{rest}'
    
    # Handle UNC paths (\\server\share)
    if path.startswith('//'):
        return path
    
    # Already a WSL path or relative path
    return path

def wsl_to_windows(wsl_path):
    """Convert WSL path to Windows path"""
    match = re.match(r'^/mnt/([a-z])(/.*)?$', wsl_path)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2) or ''
        return f'{drive}:{rest.replace("/", "\\")}'
    
    return wsl_path

def main():
    if len(sys.argv) < 2:
        print("Usage: winpath.py <windows-path>")
        print("       winpath.py --wsl <wsl-path>")
        sys.exit(1)
    
    if sys.argv[1] == '--wsl' and len(sys.argv) >= 3:
        # Convert WSL to Windows
        wsl_path = sys.argv[2]
        win_path = wsl_to_windows(wsl_path)
        print(win_path)
    else:
        # Convert Windows to WSL
        win_path = sys.argv[1]
        wsl_path = windows_to_wsl(win_path)
        print(wsl_path)

if __name__ == '__main__':
    main()
