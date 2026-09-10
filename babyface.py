#!/usr/bin/env python3
"""Command-line entry point for the Omarchy Babyface panel."""

import argparse
import json
import sys

from babyface.service import request, serve, watch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "watch", "status"):
        sub.add_parser(name)
    gain = sub.add_parser("set")
    gain.add_argument("channel")
    gain.add_argument("db", help="Gain in dB, or mute for an output")
    profile = sub.add_parser("profile")
    profile.add_argument("operation", choices=["save", "load", "delete"])
    profile.add_argument("name")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve()
            return 0
        if args.command == "watch":
            watch()
            return 0
        command = None
        if args.command == "set":
            command = dict(op="set", channel=args.channel, db=None if args.db == "mute" else float(args.db))
        elif args.command == "profile":
            command = dict(op=f"{args.operation}_profile", name=args.name)
        result = request(command)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 1 if result.get("error") and "channels" not in result else 0
    except (RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
