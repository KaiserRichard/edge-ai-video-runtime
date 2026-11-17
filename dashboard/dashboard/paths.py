"""Translate trusted configured Windows input paths when running under WSL."""
import os
from pathlib import Path
import re


def input_path(value):
    value = str(value)
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
    if os.name != "nt" and match:
        return Path("/mnt") / match[1].lower() / match[2].replace("\\", "/")
    return Path(value)
