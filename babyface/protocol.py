"""RME's class-compliant MIDI control protocol (see docs/protocol.md)."""

import math

HEADER = bytes.fromhex("f0 00 20 0d 10")
REQUEST_STATE = HEADER + b"\x10\xf7"
MUTE = 0x3B


def packet(sub_id, words=()):
    payload = bytearray(HEADER + bytes([sub_id]))
    for word in words:
        if not 0 <= word <= 0xFFFFFFFF:
            raise ValueError("Protocol word outside 32-bit range")
        payload.extend((word >> shift) & 0x7F for shift in range(0, 35, 7))
    return bytes(payload) + b"\xf7"


class Decoder:
    """Bounded incremental framing; ignore MIDI clock bytes and other devices."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        messages = []
        for byte in data:
            if byte >= 0xF8:
                continue
            if byte == 0xF0:
                self.buffer = bytearray([byte])
            elif byte == 0xF7:
                body = bytes(self.buffer)
                self.buffer.clear()
                if not body.startswith(HEADER) or len(body) < 6:
                    continue
                payload = body[6:]
                if len(payload) % 5:
                    continue
                words = [sum(v << (7 * j) for j, v in enumerate(payload[i:i + 5]))
                         for i in range(0, len(payload), 5)]
                if any(w > 0xFFFFFFFF for w in words):
                    continue
                messages.append((body[5], words))
            elif byte >= 0x80 or len(self.buffer) > 1024:
                self.buffer.clear()
            elif self.buffer:
                self.buffer.append(byte)
        return messages


def channels():
    result = []
    for index in range(12):
        analog = index < 4
        mic = index < 2
        result.append(dict(
            id=f"mic{index + 1}" if mic else f"line{index + 1}" if analog else f"in{index + 1}",
            label=f"Mic {index + 1}" if mic else f"Line {index + 1}" if analog else f"Optical {index - 3}",
            port=f"AN {index + 1}" if mic else f"IN {index + 1}" if analog else f"ADAT {index - 3}",
            group="input", kind="mic" if mic else "line" if analog else "digital",
            min=0, max=65 if mic else 9 if analog else 0,
            step=1 if mic else 0.5, adjustable=analog, readback=analog,
            db=None if analog else 0, muted=False, peak=None,
        ))
    for index in range(12):
        kind = "main" if index < 2 else "headphones" if index < 4 else "digital"
        result.append(dict(
            id=f"out{index + 1}", label=("Monitor " if index < 2 else "Phones " if index < 4 else "Optical ") +
            ("L" if index % 2 == 0 else "R") if index < 4 else f"Optical {index - 3}",
            port=f"AN {index + 1}" if index < 2 else f"PH {index + 1}" if index < 4 else f"ADAT {index - 3}",
            group="output", kind=kind, min=-91.5, max=6, step=0.5,
            adjustable=True, readback=index < 6, db=None, muted=False, peak=None,
        ))
    return result


def state_values(words):
    if len(words) != 44:
        raise ValueError("Incomplete hardware state")
    _, b, c, d = words[:4]
    gains = {"mic1": c & 127, "mic2": (c >> 7) & 127,
             "line3": ((d >> 19) & 31) / 2, "line4": ((d >> 24) & 31) / 2}
    if max(gains["mic1"], gains["mic2"]) > 65 or max(gains["line3"], gains["line4"]) > 9:
        raise ValueError("Invalid hardware gain report")
    levels = [b & 255, (b >> 9) & 255, (c >> 14) & 255, (c >> 23) & 255,
              d & 255, (d >> 9) & 255]
    if any(v < MUTE for v in levels):
        raise ValueError("Invalid hardware output report")
    gains.update({f"out{i + 1}": None if v == MUTE else 6 + (v - 255) / 2
                  for i, v in enumerate(levels)})
    return gains


def peak_values(words):
    if len(words) != 40:
        raise ValueError("Incomplete peak report")
    def db(value):
        return max(-100.0, min(12.0, 20 * math.log10(value / 0x08000000))) if value else -100.0
    return [db(v) for v in words[:12]], [db(v) for v in words[26:38]]


def validate_gain(channel, db):
    if not channel["adjustable"]:
        raise ValueError("Digital inputs have no analog preamp gain")
    if db is None:
        if channel["group"] != "output":
            raise ValueError("Only outputs support mute")
        return None
    if isinstance(db, bool) or not isinstance(db, (int, float)) or not math.isfinite(db):
        raise ValueError("Gain must be a finite number")
    if not channel["min"] <= db <= channel["max"]:
        raise ValueError(f"Gain must be between {channel['min']} and {channel['max']} dB")
    if not math.isclose(db / channel["step"], round(db / channel["step"]), abs_tol=1e-7):
        raise ValueError(f"Gain uses {channel['step']} dB steps")
    return db


def gain_packets(channel, db):
    db = validate_gain(channel, db)
    if channel["kind"] == "mic":
        gain = int(db)
        raw = ((gain % 3) << 5) | (gain // 3) if gain < 60 else ((gain % 6) << 5) | 20
        return [packet(4, [(raw << 16) | (int(channel["id"][-1]) - 1)])]
    if channel["kind"] == "line":
        return [packet(4, [(round(db * 2) << 16) | (int(channel["id"][-1]) - 1)])]
    index = int(channel["id"][3:]) - 1
    coefficient = 0 if db is None else round(0x20000 * 10 ** (db / 20))
    result = [packet(1, [(coefficient << 12) | (0x3E0 + index)])]
    if index < 6:
        raw = MUTE if db is None else round(243 + 2 * db)
        result.append(packet(4, [(raw << 16) | (4 + index)]))
    return result
