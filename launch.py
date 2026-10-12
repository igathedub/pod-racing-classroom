"""Launch the local classroom server; never execute student code here."""
from __future__ import annotations

import argparse
import socket
import threading
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Pod Racing Classroom on your LAN")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--open", action="store_true", help="Open the teacher page")
    args = parser.parse_args()
    local_url = f"http://localhost:{args.port}"
    print(f"Teacher:   {local_url}/teacher", flush=True)
    print(f"Projector: {local_url}/projector", flush=True)
    if args.host == "0.0.0.0":
        addresses = sorted({info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
        for address in addresses:
            if not address.startswith("127."):
                print(f"Student LAN URL: http://{address}:{args.port}/", flush=True)
        print("Use the classroom Wi-Fi/LAN address, not a VPN or Docker adapter address.", flush=True)
        print("Trusted private networks only. Do not expose this server to the Internet.", flush=True)
    print("Keep this window open. Ctrl+C stops the server.", flush=True)
    if args.open:
        timer = threading.Timer(2, webbrowser.open, args=(local_url + "/teacher",))
        timer.daemon = True
        timer.start()
    uvicorn.run("arena.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
