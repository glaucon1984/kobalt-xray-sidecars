#!/usr/bin/env python3
"""Write a JSON sidecar as a Lua file that returns the same table, for try_sidecar.lua.

    python to_lua.py "Book.xray.json" sidecar.lua
"""
import json
import sys


def lua(value):
    if isinstance(value, dict):
        return "{" + ",".join("[%s]=%s" % (lua(key), lua(item)) for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "{" + ",".join(lua(item) for item in value) + "}"
    if isinstance(value, str):
        # Decimal escapes of the UTF-8 bytes: plain for any Lua 5.4 reader.
        return '"' + "".join("\\%d" % byte if byte < 32 or byte > 126 or byte in (34, 92) else chr(byte)
                             for byte in value.encode("utf-8")) + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    return repr(value)


with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
with open(sys.argv[2], "w", encoding="ascii", newline="\n") as handle:
    handle.write("return " + lua(data) + "\n")
