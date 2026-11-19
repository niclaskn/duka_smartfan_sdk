"""Minimal fake Duka smart fan speaking the UDP protocol on localhost."""
import socket
import threading

READ, WRITEREAD, RESPONSE = 0x01, 0x03, 0x06
SEARCH = 0x7C


def checksum(data: bytes) -> bytes:
    total = sum(data[2:]) & 0xFFFF
    return bytes([total & 0xFF, total >> 8])


def frame(device_id: str, password: str, func: int, body: bytes) -> bytes:
    data = (
        bytes([0xFD, 0xFD, 0x02, len(device_id)]) + device_id.encode()
        + bytes([len(password)]) + password.encode()
        + bytes([func]) + body
    )
    return data + checksum(data)


class FakeFan:
    def __init__(self, device_id="TESTFAN000000001", password="1111",
                 host="127.0.0.1", drop_first=0):
        self.device_id, self.password = device_id, password
        self.state = {
            0x01: b"\x01",                                   # on
            0x02: b"\x01",                                   # battery normal
            0x03: b"\x00",                                   # 24h mode off
            0x04: (1200).to_bytes(2, "little"),              # fan rpm
            0x05: b"\x00",                                   # boost off
            0x2E: bytes([55]),                               # humidity %
            0x31: bytes([21]),                               # temperature C
            0x86: bytes([1, 2, 19, 11]) + (2026).to_bytes(2, "little"),
            0xB9: (3).to_bytes(2, "little"),                 # unit type
        }
        # Real fan (fw 2.2) answers these with the 0xFD "not supported" marker
        self.unsupported = {0x0B, 0x12}
        self.extra_params = b""   # raw bytes appended to every reply
        self.drop_first = drop_first
        self.received: list[bytes] = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def send_reply(self, addr, params: bytes | None = None):
        """Send an unsolicited status reply to addr (for tests)."""
        if params is None:
            params = b"".join(bytes([p]) + v for p, v in self.state.items())
        self.sock.sendto(frame(self.device_id, self.password, RESPONSE, params), addr)

    def close(self):
        self._running = False
        self._thread.join()
        self.sock.close()

    @staticmethod
    def _parse(data: bytes):
        pos = 3
        id_len = data[pos]; pos += 1
        dev_id = data[pos:pos + id_len].decode(); pos += id_len
        pw_len = data[pos]; pos += 1
        password = data[pos:pos + pw_len].decode(); pos += pw_len
        func = data[pos]; pos += 1
        return dev_id, password, func, data[pos:-2]

    def _reply_body(self, func: int, body: bytes) -> bytes | None:
        if func == READ:
            params = body
        elif func == WRITEREAD:            # (param, 1-byte value) pairs
            params = bytes(body[0::2])
            for param, value in zip(body[0::2], body[1::2]):
                self.state[param] = bytes([value])
        else:
            return None
        return b"".join(self._encode(p) for p in params) + self.extra_params

    def _encode(self, param: int) -> bytes:
        """Encode one field the way the real fan does (see tools/probe.py output)."""
        if param in self.unsupported:
            return bytes([0xFD, param])
        if param not in self.state:
            return b""
        value = self.state[param]
        if len(value) > 1:                 # multi-byte values carry the 0xFE size prefix
            return bytes([0xFE, len(value), param]) + value
        return bytes([param]) + value

    def _serve(self):
        while self._running:
            try:
                data, addr = self.sock.recvfrom(1024)
            except TimeoutError:
                continue
            self.received.append(data)
            if self.drop_first > 0:
                self.drop_first -= 1
                continue
            dev_id, password, func, body = self._parse(data)
            if dev_id == "DEFAULT_DEVICEID" and body == bytes([SEARCH]):
                reply = bytes([SEARCH]) + self.device_id.encode()
            elif dev_id == self.device_id and password == self.password:
                reply = self._reply_body(func, body)
            else:
                reply = None
            if reply is not None:
                self.sock.sendto(frame(self.device_id, self.password, RESPONSE, reply), addr)
