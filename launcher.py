#!/usr/bin/env python3
"""
AI Optical Design Engineer - Desktop Launcher

A simple double-click launcher that starts the application.
"""

import subprocess
import sys
import os
import time
import threading
import platform

# Configuration
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"

def get_script_dir():
    """Get the directory containing this script."""
    return os.path.dirname(os.path.abspath(__file__))

def check_python():
    """Check if Python is available."""
    try:
        result = subprocess.run(
            [sys.executable, '--version'],
            capture_output=True, text=True
        )
        print(f"Python found: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"Error checking Python: {e}")
        return False

def check_node():
    """Check if Node.js is available."""
    try:
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True, text=True
        )
        print(f"Node.js found: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"Error checking Node.js: {e}")
        return False

def setup_backend():
    """Set up the backend environment."""
    script_dir = get_script_dir()
    backend_dir = os.path.join(script_dir, 'backend')
    venv_dir = os.path.join(backend_dir, 'venv')
    
    # Create virtual environment if needed
    if not os.path.exists(venv_dir):
        print("Creating virtual environment...")
        subprocess.run(
            [sys.executable, '-m', 'venv', 'venv'],
            cwd=backend_dir, check=True
        )
    
    # Activate and install dependencies
    if platform.system() == 'Windows':
        python_path = os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        python_path = os.path.join(venv_dir, 'bin', 'python')
    
    print("Installing backend dependencies...")
    subprocess.run(
        [python_path, '-m', 'pip', 'install', '-r', 'requirements.txt'],
        cwd=backend_dir, check=True
    )
    
    return python_path

def setup_frontend():
    """Set up the frontend environment."""
    script_dir = get_script_dir()
    frontend_dir = os.path.join(script_dir, 'frontend')
    
    # Install npm dependencies if needed
    if not os.path.exists(os.path.join(frontend_dir, 'node_modules')):
        print("Installing frontend dependencies...")
        subprocess.run(
            ['npm', 'install'],
            cwd=frontend_dir, check=True
        )

def start_backend(python_path):
    """Start the backend server."""
    script_dir = get_script_dir()
    backend_dir = os.path.join(script_dir, 'backend')
    
    print("Starting backend server...")
    process = subprocess.Popen(
        [python_path, '-m', 'uvicorn', 'api.main:app',
         '--host', '0.0.0.0', '--port', str(BACKEND_PORT)],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return process

def start_frontend():
    """Start the frontend server."""
    script_dir = get_script_dir()
    frontend_dir = os.path.join(script_dir, 'frontend')
    
    print("Starting frontend server...")
    process = subprocess.Popen(
        ['npm', 'run', 'dev'],
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=(platform.system() == 'Windows')
    )
    return process

def wait_for_service(url, timeout=30):
    """Wait for a service to become available."""
    import urllib.request
    
    print(f"Waiting for {url}...")
    for i in range(timeout):
        try:
            urllib.request.urlopen(url)
            print(f"Service is ready!")
            return True
        except:
            time.sleep(1)
    
    print(f"Service did not start within {timeout} seconds")
    return False

def open_browser(url):
    """Open the default browser."""
    import webbrowser
    print(f"Opening browser: {url}")
    webbrowser.open(url)

def main():
    """Main entry point."""
    print("=" * 60)
    print("AI Optical Design Engineer")
    print("=" * 60)
    print()
    
    # Check prerequisites
    if not check_python():
        print("ERROR: Python not found. Please install Python 3.11+")
        input("Press Enter to exit...")
        return 1
    
    if not check_node():
        print("ERROR: Node.js not found. Please install Node.js 18+")
        input("Press Enter to exit...")
        return 1
    
    # Setup environments
    try:
        python_path = setup_backend()
        setup_frontend()
    except Exception as e:
        print(f"ERROR during setup: {e}")
        input("Press Enter to exit...")
        return 1
    
    # Start services
    try:
        backend_process = start_backend(python_path)
        frontend_process = start_frontend()
        
        # Wait for services to be ready
        if not wait_for_service(f"{BACKEND_URL}/api/health"):
            print("ERROR: Backend failed to start")
            backend_process.terminate()
            frontend_process.terminate()
            input("Press Enter to exit...")
            return 1
        
        # Open browser
        open_browser(FRONTEND_URL)
        
        print()
        print("Application started successfully!")
        print(f"Backend:  {BACKEND_URL}")
        print(f"Frontend: {FRONTEND_URL}")
        print()
        print("Press Ctrl+C to stop...")
        
        # Wait for processes
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            backend_process.terminate()
            frontend_process.terminate()
            print("Goodbye!")
            
    except Exception as e:
        print(f"ERROR: {e}")
        input("Press Enter to exit...")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
