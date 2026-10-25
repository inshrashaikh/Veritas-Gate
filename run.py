#!/usr/bin/env python3
"""
run.py
======
Veritas Gate Unified Application Launcher.

Starts both:
  1. Veritas Gate Analyzer & Governance API Server (Flask on http://127.0.0.1:5000)
  2. Veritas Gate Governance Dashboard Web Interface (http://localhost:3000)

Usage:
  python run.py                   # Run both servers (Demo Mode enabled by default)
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
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def log(msg=""):
    print(msg, flush=True)

def find_python_interpreter():
    """Detects virtual environment python if available, falling back to sys.executable."""
    # Check project-local .venv first
    venv_unix = ROOT_DIR / ".venv" / "bin" / "python"
    venv_win = ROOT_DIR / ".venv" / "Scripts" / "python.exe"

    if venv_unix.is_file() and os.access(str(venv_unix), os.X_OK):
        return str(venv_unix)
    if venv_win.is_file():
        return str(venv_win)

    # If running inside any active virtual environment
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return sys.executable

    return sys.executable

def check_dependencies(python_path):
    """Verifies that mandatory modules can be imported before launching."""
    check_cmd = [
        python_path,
        "-c",
        "import flask, web3, pydantic; print('OK')"
    ]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and "OK" in res.stdout:
            return True, None
        return False, res.stderr.strip() or res.stdout.strip()
    except Exception as e:
        return False, str(e)

def wait_for_url(url, timeout_sec=5.0, interval_sec=0.2):
    """Polls an HTTP URL until it returns 200 OK or timeout expires."""
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VeritasGate-Launcher"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(interval_sec)
    return False

def main():
    parser = argparse.ArgumentParser(description="Veritas Gate Unified Application Launcher")
    parser.add_argument("--api-port", type=int, default=5000, help="Port for the Analyzer Flask API (default: 5000)")
    parser.add_argument("--dashboard-port", type=int, default=3000, help="Port for the Governance Dashboard (default: 3000)")
    parser.add_argument("--api-only", action="store_true", help="Launch only the Analyzer API server")
    parser.add_argument("--dashboard-only", action="store_true", help="Launch only the Governance Dashboard")
    parser.add_argument("--verbose", action="store_true", help="Print verbose runtime logs")
    args = parser.parse_args()

    processes = []
    log_files = []

    log("\n" + "=" * 65)
    log("        VERITAS GATE — DETERMINISTIC GOVERNANCE ENGINE")
    log("=" * 65)

    python_bin = find_python_interpreter()
    if python_bin != sys.executable:
        log(f"[*] Detected local virtual environment: {python_bin}")

    # Verify python dependencies
    deps_ok, dep_err = check_dependencies(python_bin)
    if not deps_ok:
        log("\n[!] STARTUP BLOCKED: Missing required Python dependencies.")
        if dep_err:
            log(f"    Details: {dep_err}")
        log("\n    To install all required packages into your virtual environment:")
        log("      macOS / Linux:")
        log("        python3 -m venv .venv")
        log("        source .venv/bin/activate")
        log("        pip install -r requirements.txt")
        log("      Windows (PowerShell):")
        log("        python -m venv .venv")
        log("        .venv\\Scripts\\Activate.ps1")
        log("        pip install -r requirements.txt\n")
        sys.exit(1)

    # Ensure demo mode is enabled by default in launcher environment
    env = os.environ.copy()
    if "VERITAS_DEMO_MODE" not in env:
        env["VERITAS_DEMO_MODE"] = "true"

    try:
        # 1. Start Backend API Server
        if not args.dashboard_only:
            api_log_path = ROOT_DIR / ".veritas_api.log"
            api_log_file = open(api_log_path, "w", encoding="utf-8")
            log_files.append(api_log_file)

            api_cmd = [
                python_bin,
                "-u",
                "-c",
                f"import sys; sys.path.insert(0, r'{ROOT_DIR}'); from analyzer.server import create_app; app = create_app(); app.run(host='127.0.0.1', port={args.api_port}, debug=False)"
            ]
            log(f"[*] Starting Analyzer API Server on http://127.0.0.1:{args.api_port} (Demo Mode: {env.get('VERITAS_DEMO_MODE')}) ...")
            api_proc = subprocess.Popen(
                api_cmd,
                cwd=str(ROOT_DIR),
                env=env,
                stdout=api_log_file,
                stderr=subprocess.STDOUT
            )
            processes.append(("Analyzer API", api_proc, api_log_path))

            # Poll health endpoint to verify clean startup
            api_healthy = wait_for_url(f"http://127.0.0.1:{args.api_port}/health", timeout_sec=4.0)
            if not api_healthy or api_proc.poll() is not None:
                log(f"\n[!] Analyzer API failed to start. (Exit code: {api_proc.poll()})")
                log("--- API STARTUP ERROR DETAILS ---")
                try:
                    api_log_file.flush()
                    with open(api_log_path, "r", encoding="utf-8", errors="replace") as f:
                        err_content = f.read().strip()
                        log(err_content if err_content else "No error output captured.")
                except Exception as ex:
                    log(f"Failed to read log file: {ex}")
                log("---------------------------------\n")
                sys.exit(1)

            log(f"    -> API Ready: http://127.0.0.1:{args.api_port}")
            log(f"    -> Health:    http://127.0.0.1:{args.api_port}/health")

        # 2. Start Dashboard Web Server
        if not args.api_only:
            dash_script = ROOT_DIR / "dashboard" / "serve.py"
            dash_log_path = ROOT_DIR / ".veritas_dashboard.log"
            dash_log_file = open(dash_log_path, "w", encoding="utf-8")
            log_files.append(dash_log_file)

            dash_cmd = [
                python_bin,
                "-u",
                str(dash_script),
                str(args.dashboard_port)
            ]
            log(f"[*] Starting Governance Dashboard on http://localhost:{args.dashboard_port} ...")
            dash_proc = subprocess.Popen(
                dash_cmd,
                cwd=str(ROOT_DIR),
                env=env,
                stdout=dash_log_file,
                stderr=subprocess.STDOUT
            )
            processes.append(("Dashboard", dash_proc, dash_log_path))

            dash_ready = wait_for_url(f"http://localhost:{args.dashboard_port}", timeout_sec=3.0)
            if not dash_ready or dash_proc.poll() is not None:
                log(f"\n[!] Dashboard server failed to start. (Exit code: {dash_proc.poll()})")
                log("--- DASHBOARD STARTUP ERROR DETAILS ---")
                try:
                    dash_log_file.flush()
                    with open(dash_log_path, "r", encoding="utf-8", errors="replace") as f:
                        err_content = f.read().strip()
                        log(err_content if err_content else "No error output captured.")
                except Exception as ex:
                    log(f"Failed to read log file: {ex}")
                log("---------------------------------------\n")
                sys.exit(1)

            log(f"    -> Dashboard UI: http://localhost:{args.dashboard_port}")

        log("=" * 65)
        log(" Veritas Gate Application is RUNNING (DEMO MODE — SIMULATED DATA).")
        log(f" • Web Dashboard: http://localhost:{args.dashboard_port}")
        log(f" • Analyzer API:  http://127.0.0.1:{args.api_port}")
        log(" • Mode:          Demo (Offline local development, zero RPC needed)")
        log(" Press Ctrl+C to terminate all services.")
        log("=" * 65 + "\n")

        # Keep parent alive and monitor children
        while True:
            for name, proc, log_p in processes:
                code = proc.poll()
                if code is not None:
                    log(f"[!] {name} terminated unexpectedly with code {code}.")
                    try:
                        with open(log_p, "r", encoding="utf-8", errors="replace") as f:
                            log(f"--- {name} LOG ---")
                            log(f.read().strip())
                            log("-----------------")
                    except Exception:
                        pass
                    sys.exit(code)
            time.sleep(1.0)

    except KeyboardInterrupt:
        log("\n[*] Received shutdown signal. Terminating services...")
    finally:
        for item in processes:
            name, proc = item[0], item[1]
            if proc.poll() is None:
                log(f"    Stopping {name} (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for f in log_files:
            try:
                f.close()
            except Exception:
                pass
        log("[*] All services stopped cleanly.\n")

if __name__ == "__main__":
    main()
