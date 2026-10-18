#!/usr/bin/env python3
"""
Build a standalone .exe launcher for Windows using PyInstaller.

This creates a simple double-clickable executable that starts
the AI Optical Design Engineer application.
"""

import subprocess
import sys
import os

def build_exe():
    """Build the Windows executable."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
    
    # Build command
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name', 'AI-Optical-Design-Engineer',
        '--add-data', f'{script_dir}/launcher.py;.',
        '--distpath', f'{script_dir}/dist',
        f'{script_dir}/launcher.py'
    ]
    
    print("Building executable...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, cwd=script_dir)
    
    if result.returncode == 0:
        print(f"\nBuild successful! Executable: {script_dir}/dist/AI-Optical-Design-Engineer.exe")
    else:
        print("\nBuild failed!")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(build_exe())
