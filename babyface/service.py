"""Local Unix socket service and JSON-lines desktop bridge."""

import fcntl
import json
import os
import selectors
import signal
import socket
import sys
import time
from pathlib import Path

from .controller import Controller
from .hardware import Midi, discover
from .storage import Store

MAX_MESSAGE = 65536


def paths():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return runtime / "babyface-control.sock", state / "babyface-control/settings.json"


def encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def load_controller(settings):
    try:
        return Controller(Store(settings))
    except (OSError, ValueError) as exc:
        controller = Controller(None)
        controller.error = f"Cannot read {settings}: {exc}; restore a backup and restart babyface-control.service"
        print(controller.error, file=sys.stderr)
        return controller


def client_events(entry):
    return selectors.EVENT_READ | (selectors.EVENT_WRITE if entry["output"] else 0)


def serve():
    address, settings = paths()
    controller = load_controller(settings)
    store = controller.store
    lock = open(address.with_suffix(".lock"), "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("The Babyface service is already running") from None
    address.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(address))
    os.chmod(address, 0o600)
    server.listen(8)
    server.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(server, selectors.EVENT_READ)
    clients = {}
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def close(client):
        selector.unregister(client)
        clients.pop(client, None)
        client.close()

    next_connect, next_snapshot = 0.0, 0.0
    try:
        while running:
            now = time.monotonic()
            if store is not None and not controller.midi and now >= next_connect:
                next_connect = now + 2
                try:
                    info = discover()
                    if info:
                        controller.attach(Midi(info["midi"]), info)
                    else:
                        controller.error = "Connect a Babyface Pro in class-compliant mode"
                except OSError as exc:
                    controller.error = f"Cannot connect to Babyface MIDI: {exc}"
            try:
                controller.tick()
            except (OSError, ValueError) as exc:
                controller.detach(str(exc))
            for key, mask in selector.select(0.01):
                client = key.fileobj
                if client is server:
                    connection, _ = server.accept()
                    if len(clients) >= 16:
                        connection.close()
                        continue
                    connection.setblocking(False)
                    clients[connection] = dict(input=bytearray(), output=bytearray(encode(controller.snapshot())))
                    selector.register(connection, selectors.EVENT_READ | selectors.EVENT_WRITE)
                    continue
                entry = clients[client]
                try:
                    if mask & selectors.EVENT_READ:
                        chunk = client.recv(8192)
                        if not chunk:
                            close(client)
                            continue
                        entry["input"].extend(chunk)
                        if len(entry["input"]) > MAX_MESSAGE:
                            close(client)
                            continue
                        while b"\n" in entry["input"]:
                            line, _, rest = entry["input"].partition(b"\n")
                            entry["input"] = bytearray(rest)
                            try:
                                request = json.loads(line)
                                controller.command(request)
                                response = {"ok": True, "request": request.get("request")}
                            except (ValueError, TypeError, OSError, KeyError) as exc:
                                response = {"error": str(exc)}
                            entry["output"].extend(encode(response))
                        selector.modify(client, client_events(entry))
                    if mask & selectors.EVENT_WRITE and entry["output"]:
                        sent = client.send(entry["output"])
                        del entry["output"][:sent]
                        if not entry["output"]:
                            selector.modify(client, selectors.EVENT_READ)
                except (ConnectionError, OSError):
                    close(client)
            if now >= next_snapshot:
                next_snapshot = now + 0.1
                snapshot = encode(controller.snapshot())
                for client, entry in list(clients.items()):
                    if len(entry["output"]) > MAX_MESSAGE:
                        close(client)
                        continue
                    entry["output"].extend(snapshot)
                    selector.modify(client, selectors.EVENT_READ | selectors.EVENT_WRITE)
    finally:
        if controller.synced and controller.known and not controller.pending:
            try:
                store.remember(controller.info["serial"], controller.known)
            except (OSError, ValueError) as exc:
                print(f"Could not save final hardware state: {exc}", file=sys.stderr)
        controller.detach()
        for client in list(clients):
            close(client)
        selector.close()
        server.close()
        address.unlink(missing_ok=True)
        lock.close()


def connect():
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(3)
    try:
        client.connect(str(paths()[0]))
    except OSError:
        client.close()
        raise RuntimeError("Babyface service unavailable. Run systemctl --user start babyface-control") from None
    return client


def watch():
    with connect() as client:
        client.settimeout(None)
        selector = selectors.DefaultSelector()
        selector.register(client, selectors.EVENT_READ)
        selector.register(sys.stdin, selectors.EVENT_READ)
        pending = bytearray()
        try:
            while True:
                for key, _ in selector.select():
                    if key.fileobj is client:
                        chunk = client.recv(16384)
                        if not chunk:
                            return
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                    else:
                        chunk = os.read(sys.stdin.fileno(), 8192)
                        if not chunk:
                            return
                        pending.extend(chunk)
                        if len(pending) > MAX_MESSAGE:
                            raise ValueError("Command too long")
                        while b"\n" in pending:
                            line, _, rest = pending.partition(b"\n")
                            pending = bytearray(rest)
                            client.sendall(line + b"\n")
        finally:
            selector.close()


def request(command=None):
    with connect() as client:
        stream = client.makefile("rb")
        initial = json.loads(stream.readline(MAX_MESSAGE))
        if command is None:
            return initial
        client.sendall(encode(command))
        while True:
            message = json.loads(stream.readline(MAX_MESSAGE))
            if "channels" not in message:
                return message
