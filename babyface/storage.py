"""Atomic, per-device gain snapshots and named profiles."""

import copy
import json
from pathlib import Path

from .protocol import channels, validate_gain
from .files import atomic_write, read_file


def validate_values(values):
    known = {c["id"]: c for c in channels()}
    if not isinstance(values, dict) or not values:
        raise ValueError("A profile needs at least one known channel gain")
    for key, value in values.items():
        if key not in known:
            raise ValueError(f"Unknown channel: {key}")
        validate_gain(known[key], value)
    return dict(values)


def profile_name(name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 48:
        raise ValueError("Use a profile name between 1 and 48 characters")
    name = name.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("Profile names cannot contain control characters")
    return name


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"version": 1, "devices": {}}
        content = read_file(self.path)
        if content is not None:
            self.data = json.loads(content)
            if not isinstance(self.data, dict) or self.data.get("version") != 1 or not isinstance(self.data.get("devices"), dict):
                raise ValueError("Unsupported settings file; restore a backup")
            for device in self.data["devices"].values():
                if (not isinstance(device, dict) or not isinstance(device.get("profiles"), dict)
                        or not isinstance(device.get("last"), dict)):
                    raise ValueError("Invalid device settings")
                if device.get("last"):
                    validate_values(device["last"])
                if len(device["profiles"]) > 64:
                    raise ValueError("Too many saved profiles")
                for name, values in device["profiles"].items():
                    profile_name(name)
                    validate_values(values)

    def device(self, serial):
        return copy.deepcopy(self.data["devices"].get(serial, {"last": {}, "profiles": {}}))

    def commit(self, serial, device):
        updated = copy.deepcopy(self.data)
        updated["devices"][serial] = device
        content = json.dumps(updated, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        atomic_write(self.path, content.encode("utf-8"))
        self.data = updated

    def remember(self, serial, values):
        values = validate_values(values)
        device = self.device(serial)
        if device["last"] != values:
            device["last"] = values
            self.commit(serial, device)

    def save(self, serial, name, values):
        name, values = profile_name(name), validate_values(values)
        device = self.device(serial)
        if name not in device["profiles"] and len(device["profiles"]) >= 64:
            raise ValueError("The 64-profile limit has been reached")
        device["profiles"][name] = values
        self.commit(serial, device)

    def load(self, serial, name):
        name = profile_name(name)
        profiles = self.device(serial)["profiles"]
        if name not in profiles:
            raise ValueError("Profile not found for this Babyface")
        return validate_values(profiles[name])

    def delete(self, serial, name):
        name = profile_name(name)
        device = self.device(serial)
        if name not in device["profiles"]:
            raise ValueError("Profile not found")
        del device["profiles"][name]
        self.commit(serial, device)
