#!/usr/bin/env python3
"""Read-only probe of a Duka smart fan: one READ request per parameter, raw replies printed.

Never writes. Env: FAN_IP, FAN_ID, FAN_PASSWORD. Flag --port4000 binds port 4000 instead of a free port.
"""
import os
import socket
import sys

FAN_PORT = 4000
REPLY_TIMEOUT_S = 2.0
# 0x25 (factory reset) and 0x94-0xA3 (Wi-Fi, incl. the Wi-Fi password) are left out on purpose.
PARAMS = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
          0x0F, 0x11, 0x12, 0x13, 0x14, 0x16, 0x17, 0x18, 0x1A, 0x1B, 0x1D, 0x1E, 0x1F,
          0x20, 0x21, 0x23, 0x24, 0x2E, 0x31, 0x86, 0xB9]


def checksum(data: bytes) -> bytes:
    total = sum(data[2:]) & 0xFFFF
    return bytes([total & 0xFF, total >> 8])


def read_request(device_id: str, password: str, param: int) -> bytes:
    data = (bytes([0xFD, 0xFD, 0x02, len(device_id)]) + device_id.encode()
            + bytes([len(password)]) + password.encode() + bytes([0x01, param]))
    return data + checksum(data)


def describe(data: bytes) -> str:
    pos = 3
    pos += 1 + data[pos]            # skip device ID
    password_len = data[pos]        # length only: never print the password
    pos += 1 + password_len
    func, body = data[pos], data[pos + 1:-2]
    return f"password_len={password_len} func=0x{func:02X} body={body.hex(' ')}"


def main() -> None:
    ip, device_id = os.environ["FAN_IP"], os.environ["FAN_ID"]
    password = os.environ.get("FAN_PASSWORD", "1111")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", FAN_PORT if "--port4000" in sys.argv else 0))
    sock.settimeout(REPLY_TIMEOUT_S)
    print(f"listening on port {sock.getsockname()[1]}")
    for param in PARAMS:            # one per request, so one unsupported field can't hide others
        sock.sendto(read_request(device_id, password, param), (ip, FAN_PORT))
        try:
            data, addr = sock.recvfrom(1024)
        except TimeoutError:
            print(f"0x{param:02X}: no reply")
            continue
        print(f"0x{param:02X}: from {addr[0]}:{addr[1]} {describe(data)}")


if __name__ == "__main__":
    main()
