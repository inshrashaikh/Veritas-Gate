#!/usr/bin/env python3
"""
serve.py
========
Lightweight local HTTP server for Veritas Gate Phase 6 Dashboard.
Serves static assets using Python's standard library http.server.

Usage:
    python dashboard/serve.py [port]
"""

import http.server
import os
import socketserver
import sys

DEFAULT_PORT = 3000

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS and disable aggressive caching during development
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

def run_server(port=DEFAULT_PORT):
    dashboard_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(dashboard_dir)

    with socketserver.TCPServer(("", port), DashboardHandler) as httpd:
        print(f"\n=======================================================")
        print(f" Veritas Gate Dashboard running at: http://localhost:{port}")
        print(f" Serving directory: {dashboard_dir}")
        print(f" Press Ctrl+C to stop.")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else DEFAULT_PORT
    run_server(port)
