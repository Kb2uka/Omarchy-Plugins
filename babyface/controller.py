"""Single-writer state machine. Hardware acknowledgements own displayed values."""

import time

from .protocol import Decoder, REQUEST_STATE, channels, gain_packets, peak_values, state_values, validate_gain
from .storage import validate_values


class Controller:
    def __init__(self, store, clock=time.monotonic):
        self.store, self.clock = store, clock
        self.midi = None
        self.info = {}
        self.decoder = Decoder()
        self.items = channels()
        self.by_id = {c["id"]: c for c in self.items}
        self.known = {}
        self.pending = {}
        self.error = ""
        self.last_report = None
        self.last_poll = -1.0
        self.save_due = None
        self.restored = False
        self.persisted = store is not None

    def attach(self, midi, info):
        self.midi, self.info = midi, info
        self.decoder = Decoder()
        self.items = channels()
        self.by_id = {c["id"]: c for c in self.items}
        self.known, self.pending = {}, {}
        self.last_report, self.save_due = None, None
        self.last_poll, self.restored = -1.0, False
        self.attached_at = self.clock()
        self.error = ""

    def detach(self, message="Babyface disconnected"):
        if self.synced and self.known:
            try:
                self.store.remember(self.info["serial"], self.known)
                self.persisted = True
            except (OSError, ValueError) as exc:
                message += f"; could not save latest gains: {exc}"
        if self.midi:
            self.midi.close()
        self.midi = None
        self.pending.clear()
        self.last_report = None
        self.save_due = None
        self.error = message
        for item in self.items:
            item["peak"] = None

    @property
    def synced(self):
        return self.midi is not None and self.last_report is not None and self.clock() - self.last_report < 0.8

    def tick(self):
        if not self.midi:
            return
        now = self.clock()
        if now - self.last_poll >= 0.1:
            self.midi.write(REQUEST_STATE)
            self.last_poll = now
        for sub_id, words in self.decoder.feed(self.midi.read()):
            try:
                if sub_id == 0:
                    self.receive_state(state_values(words))
                elif sub_id == 2:
                    inputs, outputs = peak_values(words)
                    for item, peak in zip(self.items, inputs + outputs):
                        item["peak"] = peak
            except ValueError:
                continue
        for key, (target, deadline) in list(self.pending.items()):
            if not self.by_id[key]["readback"] and not self.midi.is_pending(key):
                self.known[key] = target
                self.by_id[key]["db"] = target
                self.by_id[key]["muted"] = target is None
                del self.pending[key]
                self.save_due = now + 0.4
            elif now > deadline:
                del self.pending[key]
                self.error = f"Hardware did not confirm {self.by_id[key]['label']}; showing its reported gain"
        if self.last_report is not None and now - self.last_report > 3:
            raise OSError("Hardware feedback stopped; reconnecting MIDI")
        if self.last_report is None and now - self.attached_at > 3:
            raise OSError("No hardware feedback received")
        if self.save_due is not None and now >= self.save_due and self.synced and not self.pending:
            try:
                self.store.remember(self.info["serial"], self.known)
                self.persisted = True
                self.save_due = None
            except (OSError, ValueError) as exc:
                self.error = f"Could not save gains: {exc}"
                self.save_due = now + 5

    def receive_state(self, values):
        self.last_report = self.clock()
        changed = False
        for key, value in values.items():
            if key not in self.known or value != self.known[key]:
                changed = True
            self.known[key] = value
            self.by_id[key]["db"] = value
            self.by_id[key]["muted"] = value is None
            if key in self.pending and self.pending[key][0] == value and not self.midi.is_pending(key):
                del self.pending[key]
        if changed:
            self.persisted = False
            self.save_due = self.clock() + 0.4
        if not self.restored:
            self.restored = True
            saved = self.store.device(self.info["serial"])["last"]
            if saved:
                self.apply(saved)

    def apply(self, values):
        validate_values(values)
        for key, value in values.items():
            validate_gain(self.by_id[key], value)
        for key, value in values.items():
            if key not in self.pending and key in self.known and self.known[key] == value:
                continue
            self.midi.set_gain(key, gain_packets(self.by_id[key], value))
            self.pending[key] = (value, self.clock() + 2.5)
            self.persisted = False
            self.save_due = self.clock() + 0.4

    def command(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected a command object")
        op = request.get("op")
        if op == "status":
            return
        if self.store is None:
            raise ValueError(self.error)
        if not self.synced:
            raise ValueError("Wait for live Babyface feedback before changing gains")
        self.error = ""
        serial = self.info["serial"]
        if op == "set":
            key = request.get("channel")
            if not isinstance(key, str) or key not in self.by_id or "db" not in request:
                raise ValueError("Unknown channel or missing gain")
            self.apply({key: request["db"]})
        elif op == "save_profile":
            if self.pending:
                raise ValueError("Wait for the hardware to confirm pending gains")
            self.store.save(serial, request.get("name"), self.known)
        elif op == "load_profile":
            values = self.store.load(serial, request.get("name"))
            self.apply(values)
        elif op == "delete_profile":
            self.store.delete(serial, request.get("name"))
        else:
            raise ValueError("Unknown command")

    def snapshot(self):
        profiles = self.store.device(self.info.get("serial", ""))["profiles"] if self.store else {}
        active = next((name for name, values in profiles.items()
                       if not self.pending and all(k in self.known and self.known[k] == v for k, v in values.items())), "")
        result = dict(connected=self.midi is not None, synced=self.synced,
                      serial=self.info.get("serial", ""), device="Babyface Pro",
                      error=self.error, profile=active, profiles=sorted(profiles, key=str.casefold),
                      persisted=self.persisted, updated_at=time.time(),
                      channels=[dict(c, pending=c["id"] in self.pending,
                                     peak=c["peak"] if self.synced else None) for c in self.items])
        return result
