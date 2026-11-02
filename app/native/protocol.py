"""Chrome Native Messaging stdio protokolü: 4 bayt little-endian uzunluk + UTF-8 JSON."""
from __future__ import annotations

import json
import os
import struct
import sys
from typing import Any, Optional

HOST_NAME = "com.getliyo.app"
MAX_MESSAGE_SIZE = 1024 * 1024  # Chrome'un kendi sınırı 1 MB


def ensure_binary_stdio() -> None:
    """Windows'ta stdin/stdout'u ikili moda alır (metin modu \\r\\n çevirisi mesajı bozar)."""
    if os.name == "nt":
        import msvcrt

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def read_message() -> Optional[dict[str, Any]]:
    """Chrome'dan tek bir mesaj okur. Bağlantı kapandıysa None döner."""
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None
    (length,) = struct.unpack("<I", raw_length)
    if length > MAX_MESSAGE_SIZE:
        raise ValueError("Mesaj çok büyük")
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode("utf-8"))


def send_message(payload: dict[str, Any]) -> None:
    """Chrome'a tek bir mesaj yazar."""
    data = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
