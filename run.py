#!/usr/bin/env python3
"""
run.py
======
Veritas Gate Unified Application Launcher.

Starts both:
  1. Veritas Gate Analyzer & Governance API Server (Flask on http://127.0.0.1:5000)
  2. Veritas Gate Governance Dashboard Web Interface (http://localhost:3000)

Usage:
  python run.py                   # Run both servers
  python run.py --api-only        # Run API server only
  python run.py --dashboard-only  # Run Dashboard server only
  python run.py --dashboard-port 3000 --api-port 5000
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def log(msg=""):
    print(msg, flush=True)

def main():
    parser = argparse.ArgumentParser(description="Veritas Gate Unified Application Launcher")
    parser.add_argument("--api-port", type=int, default=5000, help="Port for the Analyzer Flask API (default: 5000)")
    parser.add_argument("--dashboard-port", type=int, default=3000, help="Port for the Governance Dashboard (default: 3000)")
    parser.add_argument("--api-only", action="store_true", help="Launch only the Analyzer API server")
    parser.add_argument("--dashboard-only", action="store_true", help="Launch only the Governance Dashboard")
    args = parser.parse_args()

    processes = []

    log("\n" + "=" * 65)
    log("        VERITAS GATE — DETERMINISTIC GOVERNANCE ENGINE")
    log("=" * 65)

    try:
        # 1. Start Backend API Server
        if not args.dashboard_only:
            api_cmd = [
                sys.executable,
                "-u",
                "-c",
                f"import sys; sys.path.insert(0, r'{ROOT_DIR}'); from analyzer.server import create_app; app = create_app(); app.run(host='127.0.0.1', port={args.api_port}, debug=False)"
            ]
            log(f"[*] Starting Analyzer API Server on http://127.0.0.1:{args.api_port} ...")
            api_proc = subprocess.Popen(
                api_cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(("Analyzer API", api_proc))
            time.sleep(1.2)
            if api_proc.poll() is not None:
                log(f"[!] Analyzer API failed to start. Exit code: {api_proc.returncode}")
                sys.exit(1)
            log(f"    -> API Ready: http://127.0.0.1:{args.api_port}")
            log(f"    -> Health:    http://127.0.0.1:{args.api_port}/health")

        # 2. Start Dashboard Web Server
        if not args.api_only:
            dash_script = ROOT_DIR / "dashboard" / "serve.py"
            dash_cmd = [
                sys.executable,
                "-u",
                str(dash_script),
                str(args.dashboard_port)
            ]
            log(f"[*] Starting Governance Dashboard on http://localhost:{args.dashboard_port} ...")
            dash_proc = subprocess.Popen(
                dash_cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(("Dashboard", dash_proc))
            time.sleep(0.8)
            if dash_proc.poll() is not None:
                log(f"[!] Dashboard server failed to start. Exit code: {dash_proc.returncode}")
                sys.exit(1)
            log(f"    -> Dashboard UI: http://localhost:{args.dashboard_port}")

        log("=" * 65)
        log(" Veritas Gate Application is RUNNING.")
        log(f" • Web Dashboard: http://localhost:{args.dashboard_port}")
        log(f" • Analyzer API:  http://127.0.0.1:{args.api_port}")
        log(" Press Ctrl+C to terminate all services.")
        log("=" * 65 + "\n")

        # Keep parent alive and monitor children
        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    log(f"[!] {name} terminated unexpectedly with code {code}.")
                    sys.exit(code)
            time.sleep(1.0)

    except KeyboardInterrupt:
        log("\n[*] Received shutdown signal. Terminating services...")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                log(f"    Stopping {name} (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        log("[*] All services stopped cleanly.\n")

if __name__ == "__main__":
    main()
