"""Implements a client for making a udp connection to the duka one devices"""

import asyncio
import logging
import socket
import threading
import time
from random import random
from socket import SO_BROADCAST, SO_REUSEADDR, SOL_SOCKET

from .device import Device
from .dukapacket import DukaPacket
from .responsepacket import ResponsePacket


_LOGGER = logging.getLogger(__name__)

BROADCAST_ADDRESSES = {"<broadcast>", "255.255.255.255"}
UNEXPECTED_SOURCE_WARN_INTERVAL_S = 60.0


def _is_broadcast(ip: str) -> bool:
    return ip in BROADCAST_ADDRESSES or ip.endswith(".255")


class DukaClient:
    """Client object for making connection to the duka devices."""

    _mutex = threading.Lock()

    INIT_TIMEOUT_S = 10.0
    RESEND_INTERVAL_S = 1.0
    POLL_INTERVAL_S = 0.1

    def __init__(
        self,
        device_port: int = 4000,
        listen_port: int = 4000,
        bind_address: str = "0.0.0.0",
    ):
        self._device_port = device_port
        self._listen_port = listen_port
        self._bind_address = bind_address
        self._devices = {}
        self._sock = None
        self._socket_listening = False
        self._socket_error = False
        self._last_source_warning: dict[tuple[str, str], float] = {}

        self._notifyrunning = False
        self._notifythread = threading.Thread(target=self.__notify_fn)
        self._notifythread.start()
        self._found_device_callback = None

    def close(self):
        """Close the client and end the notify thread to end. Wait for the
        thread to end."""
        self._notifyrunning = False
        self._notifythread.join()

    def add_device(
        self,
        device_id: str,
        password: str | None = None,
        ip_address: str = "<broadcast>",
        onchange=None,
        *,
        allow_ip_change: bool = False,
    ) -> Device:
        """Add a new device. If the device already exist the current one will
        be returned.

        Replies are only accepted from the device's IP address. If the address
        is a broadcast address, the first responder is pinned. Pass
        allow_ip_change=True to let the device follow any source address
        (e.g. DHCP changes); this lets any host on the LAN answer for it."""
        device: Device = self.get_device(device_id)
        if device is None:
            device = Device(
                device_id, password, ip_address, onchange, allow_ip_change
            )
            self._devices[device_id] = device
        try:
            self._send_get_firmware(device)
        except ValueError:
            # invalid id/password: do not leave it registered, the status
            # polling would fail on it forever
            self._devices.pop(device_id, None)
            raise
        return device

    def _send_get_firmware(self, device: Device):
        """Send a get firmware request to the device."""
        packet = DukaPacket()
        packet.initialize_get_firmware_cmd(device)
        self.__send_data(device, packet.data)

    async def wait_for_initialize_async(
        self, device: Device | None, timeout: float = INIT_TIMEOUT_S
    ) -> bool:
        """Wait until the device has answered the firmware request.

        UDP is lossy, so the request is resent (with jitter) until the device
        answers or the timeout expires. Returns True if the device initialized.
        """
        if device is None:
            return False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        next_send = loop.time() + self.RESEND_INTERVAL_S - random()
        while device.firmware_version is None and loop.time() < deadline:
            await asyncio.sleep(self.POLL_INTERVAL_S)
            if loop.time() >= next_send:
                # __send_data may block for up to 3 s
                await loop.run_in_executor(None, self._send_get_firmware, device)
                next_send = loop.time() + self.RESEND_INTERVAL_S - random()
        return device.firmware_version is not None

    def remove_device(self, device_id: str | Device):
        """Remove an existing device. Accepts a device ID string or a Device object."""
        if isinstance(device_id, Device):
            device_id = device_id.device_id
        device: Device = self.get_device(device_id)
        if device is not None:
            del self._devices[device_id]
        return device

    def get_device(self, device_id: str) -> Device | None:
        """Get a device by device id."""
        if device_id not in self._devices:
            return None
        return self._devices[device_id]

    def get_device_count(self):
        """Return the number of devices"""
        return len(self._devices)

    def search_devices(self, callback, search_address: str = "<broadcast>"):
        self._found_device_callback = callback
        packet = DukaPacket()
        packet.initialize_search_cmd()
        self.__wait_for_socket()
        self.__log_sent("DEFAULT_DEVICEID", packet.data)
        with DukaClient._mutex:
            self._sock.sendto(packet.data, (search_address, self._device_port))

    def turn_off(self, device: Device):
        """Turn off the specified device"""
        packet = DukaPacket()
        packet.initialize_off_cmd(device)
        data = packet.data
        self.__send_data(device, data)

    def turn_on(self, device: Device):
        """Turn on the specified device"""
        packet = DukaPacket()
        packet.initialize_on_cmd(device)
        data = packet.data
        self.__send_data(device, data)

    def turn_boost_off(self, device: Device):
        """Turn off boost for the specified device"""
        packet = DukaPacket()
        packet.initialize_boost_off_cmd(device)
        data = packet.data
        self.__send_data(device, data)

    def turn_boost_on(self, device: Device):
        """Turn on boost for the specified device"""
        packet = DukaPacket()
        packet.initialize_boost_on_cmd(device)
        data = packet.data
        self.__send_data(device, data)

    def toggle_boost(self, device: Device):
        """Turn on boost for the specified device"""
        packet = DukaPacket()
        packet.initialize_boost_toggle_cmd(device)
        data = packet.data
        self.__send_data(device, data)

    def validate_device(
        self,
        device_id: str,
        password: str | None = None,
        ip_address: str = "<broadcast>",
    ) -> Device | None:
        """Validate if a device exist and responds.
        Returns None if the device does not exist
        Returns the Device object if it exist
        """
        device: Device | None = self.get_device(device_id)
        # Is the device already added
        if device is not None:
            return device
        device = self.add_device(device_id, password, ip_address)
        try:
            self.__update_device_status(device)
            # 4 sec timeout
            timeout = time.time() + 4
            while True:
                if device.unit_type is not None:
                    return device
                if time.time() > timeout:
                    break
                time.sleep(0.1)
            return None
        finally:
            self.remove_device(device.device_id)

    def __update_device_status(self, device: Device):
        """Update the device status from the DukaClient
        You should not call this youself
        """
        packet = DukaPacket()
        packet.initialize_status_cmd(device)
        data = packet.data
        self.__send_data(device, data)

    def __update_all_device_status(self):
        """Send an update command to all devices"""
        for device_id in self._devices:
            self.__update_device_status(self._devices[device_id])

    def __send_data(self, device: Device, data):
        """Send a data packet to a device.
        Protect it with a mutex to prevent multiple threads doint it at the
        same time"""
        self.__wait_for_socket()
        self.__log_sent(device.device_id, data)
        with DukaClient._mutex:
            self._sock.sendto(data, (device.ip_address, self._device_port))

    def __wait_for_socket(self):
        """Wait for notify thread to create socket"""
        if self._socket_listening:
            return
        timeout = time.time() + 3
        while True:
            time.sleep(0.1)
            if self._socket_listening:
                return
            if time.time() > timeout:
                _LOGGER.warning("Timed out waiting for the socket to be opened")
                raise Exception("Timeout waiting for socket connection")

    @staticmethod
    def __log_sent(device_id: str, data):
        """Log a sent packet at debug level.

        Only the function and parameter section are logged. Every packet
        carries the device password in plain text, so raw bytes must never be
        logged.
        """
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        try:
            pos = 3
            pos += 1 + data[pos]  # device id
            pos += 1 + data[pos]  # password
            func = data[pos]
            params = " ".join(f"{x:02x}" for x in data[pos + 1 : -2])
        except IndexError:
            _LOGGER.debug("Sending malformed packet for device %s", device_id)
            return
        _LOGGER.debug(
            "Sending to device %s: function 0x%02x, parameters [%s]",
            device_id,
            func,
            params,
        )

    def __open_socket(self):
        """Open the socket and set the  options on the socket"""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        self._sock.bind((self._bind_address, self._listen_port))
        self._sock.settimeout(1.0)
        self._socket_listening = True

    def __close_socket(self):
        """Close the socket"""
        self._socket_listening = False
        try:
            self._sock.close()
            # pylint: disable=bare-except
            # just ignore if closing fails
        except OSError:
            return

    def __open_socket_with_retry(self):
        """Open the socket and retry with 1 sec interval in case of errors
        Skip if notify thread is not running.
        """
        while self._notifyrunning and not self._socket_listening:
            try:
                self.__open_socket()
                if self._socket_error:
                    self._socket_error = False
                    _LOGGER.info("Socket reopened after an error")
            except OSError as err:
                self._socket_error = True
                _LOGGER.debug("Could not open socket: %s", err)
                self.__close_socket()
                # wait 1 sec and try again
                time.sleep(1)

    def __receive_data(self):
        """Receive data from the socket.
        If there is a timeout. Send an update command the the devices.
        Return (None, None) where there is no data to process
        """
        try:
            data, addr = self._sock.recvfrom(1024)
            return (data, addr)
        except socket.timeout:
            try:
                self.__update_all_device_status()
            except socket.error:
                # recreate soket on error
                self._socket_error = True
                self.__close_socket()
        except socket.error:
            # recreate soket on error
            self._socket_error = True
            self.__close_socket()
        return (None, None)

    def __notify_fn(self):
        """Notify thread listening for responses from duka devices.
        This will handle recreating of the socket in case of network errors
        """
        self._notifyrunning = True
        try:
            while self._notifyrunning:
                self.__open_socket_with_retry()
                data, addr = self.__receive_data()
                if data is None:
                    continue
                packet = ResponsePacket()
                if not packet.initialize_from_data(data):
                    continue
                if packet.device_id not in self._devices:
                    if (
                        packet.search_device_id is not None
                        and self._found_device_callback is not None
                    ):
                        self._found_device_callback(packet.search_device_id)
                    continue
                device: Device = self._devices[packet.device_id]
                ip_address = addr[0]
                if not self._source_allowed(device, ip_address):
                    continue
                _LOGGER.debug(
                    "Received from %s for device %s: %s",
                    ip_address,
                    packet.device_id,
                    packet.describe_fields(),
                )
                self.update_device(device, ip_address, packet)
        finally:
            self.__close_socket()
            self._notifyrunning = False

    def _source_allowed(self, device: Device, source_ip: str) -> bool:
        """Decide whether a reply from source_ip may update the device."""
        if source_ip == device.ip_address:
            return True
        if device.allow_ip_change:
            device.pin_ip_address(source_ip)
            return True
        if _is_broadcast(device.ip_address):
            # first responder wins
            device.pin_ip_address(source_ip)
            return True
        self._warn_rate_limited(device, source_ip)
        return False

    def _warn_rate_limited(self, device: Device, source_ip: str) -> None:
        """Warn about a reply from an unexpected source, once a minute per source."""
        key = (device.device_id, source_ip)
        now = time.monotonic()
        last = self._last_source_warning.get(key)
        if last is not None and now - last < UNEXPECTED_SOURCE_WARN_INTERVAL_S:
            return
        self._last_source_warning[key] = now
        _LOGGER.warning(
            "Ignoring reply for device %s from unexpected address %s (expected %s)",
            device.device_id,
            source_ip,
            device.ip_address,
        )

    def update_device(self, device, ip_address: str, packet: ResponsePacket):
        """Update the device with data received. Called by the dukaclient"""
        haschange = False
        # use fan speed as proxy for "active"
        if packet.fan_speed is not None and bool(packet.fan_speed) != device._is_active:
            device._is_active = bool(packet.fan_speed)
            haschange = True
        if packet.humidity is not None and packet.humidity != device._humidity:
            device._humidity = packet.humidity
            haschange = True
        if packet.temperature is not None and packet.temperature != device._temperature:
            device._temperature = packet.temperature
            haschange = True
        if packet.firmware_version is not None:
            device._firmware_version = packet.firmware_version
        if packet.firmware_date is not None:
            device._firmware_date = packet.firmware_date
        if packet.unit_type is not None:
            device._unit_type = packet.unit_type

        if haschange and device._changeevent is not None:
            device._changeevent(device)
        # note we do not want the fan rpm to trigger change event because it
        # changes all the time
        if packet.fan_speed is not None and packet.fan_speed != device._fan_speed:
            device._fan_speed = packet.fan_speed
        return
