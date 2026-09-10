# Hardware protocol and limits

Only the Babyface Pro class-compliant USB identity `2a39:3fb0` is selected.
The ALSA card ID provides the displayed serial. Port 2 is opened nonblocking
through `snd_rawmidi_open`; audio continues through `snd-usb-audio`.

Sources:

- [Michael Forney's Babyface Pro MIDI protocol](https://github.com/michaelforney/oscmix/wiki/Babyface-Pro)
- [SysEx word framing](https://github.com/michaelforney/oscmix/wiki/Protocol)
- [Captured output-volume mapping](https://github.com/stistrup/rme-gain-kernel-patch/blob/main/notes/usb%20output%20volume%20messages.txt)
- [Original class-compliant mixer observations](https://github.com/stistrup/rme-gain-kernel-patch#main-out)
- [Linux mixer implementation](https://github.com/torvalds/linux/blob/master/sound/usb/mixer_quirks.c)

The read-only state request is `F0 00 20 0D 10 10 F7`. Payload words use five
little-endian 7-bit bytes. Responses 0/1/2 carry state and meters. The decoder
requires exact known message sizes and rejects malformed or impossible gains.

Input gain writes use sub-ID 4. Microphone writes encode coarse/fine steps;
reported microphone gains are already in dB. Line gain uses half-dB units.
Output writes use master coefficients in sub-ID 1; the first six outputs also
receive the matching sub-ID 4 hardware-control value. Output mute uses the
documented `0x3B` sentinel, distinct from an unknown setting.

Transactions are accepted by channel and unsent intermediate values coalesce.
Complete MIDI packets are spaced 25 ms apart; state polling takes priority
during long batches. A partial packet must finish before replacing its channel's
remaining transaction. This avoids bursts that dropped state replies on the
bench without blocking the UI or audio thread.

No routing matrix crosspoints, phantom-power switches, pad switches, clock
settings, optical mode switches, EQ registers, or radio controls are written.
Output addresses are restricted to the twelve master outputs. No speculative
register addresses are used for unreported ADAT gain companions.

Readback owns displayed values. Last-applied optical gains are saveable only
after the transport accepts their complete message; absolute readback for them
is unavailable. Unconfirmed writes never enter a saved profile. After a timeout,
the panel shows the actual reported gain and an error.

ALSA's mixer getter keeps a host-side cache and does not track front-panel knob
changes. That cache is deliberately not used for initialization or feedback.
Other applications may therefore display different cached values after MIDI
control. On login/reconnection this service's saved gain snapshot is restored
after a fresh hardware report.
