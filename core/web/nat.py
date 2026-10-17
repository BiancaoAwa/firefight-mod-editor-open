"""Port mapping through the gateway, with NAT-PMP first and UPnP IGD second.

The editor can only bind a socket on this machine. Reaching it from the public
internet needs a mapping on the router, and the router has to be asked: NAT-PMP
is a multicast-free UDP exchange, UPnP IGD is SSDP discovery plus SOAP. Both are
tried here with nothing outside the standard library, and both are given a timed
window so a router that does not answer costs a moment and no more.
"""

from __future__ import annotations

import ctypes
import ipaddress
import os
import socket
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from typing import Callable

NATPMP_PORT = 5351
SSDP_ADDRESS = ("239.255.255.250", 1900)
SSDP_MX = 2
WAN_SERVICES = (
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
DESCRIPTION = "Firefight mod editor"
LIFETIME = 7200

Exchange = Callable[[bytes, tuple[str, int], float], bytes | None]


def outbound_address() -> str:
    """The interface address this machine uses to leave the local network."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 53))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def default_gateway() -> str | None:
    """The IPv4 address of the default route, read from the system table."""
    if os.name == "nt":
        return _windows_gateway()
    return _posix_gateway()


def _posix_gateway() -> str | None:
    try:
        with open("/proc/net/route", encoding="utf-8") as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except (OSError, ValueError):
        return None
    return None


class _Row(ctypes.Structure):
    _fields_ = [
        ("dest", ctypes.c_ulong),
        ("mask", ctypes.c_ulong),
        ("policy", ctypes.c_ulong),
        ("next_hop", ctypes.c_ulong),
        ("if_index", ctypes.c_ulong),
        ("kind", ctypes.c_ulong),
        ("proto", ctypes.c_ulong),
        ("age", ctypes.c_ulong),
        ("next_hop_as", ctypes.c_ulong),
        ("metric1", ctypes.c_ulong),
        ("metric2", ctypes.c_ulong),
        ("metric3", ctypes.c_ulong),
        ("metric4", ctypes.c_ulong),
        ("metric5", ctypes.c_ulong),
    ]


def _windows_gateway() -> str | None:
    """Read the default row of the IPv4 forwarding table through iphlpapi."""
    table_size = ctypes.c_ulong(0)
    iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
    try:
        iphlpapi.GetIpForwardTable(None, ctypes.byref(table_size), False)
    except OSError:
        return None
    if not table_size.value:
        return None
    buffer = ctypes.create_string_buffer(table_size.value)
    if iphlpapi.GetIpForwardTable(buffer, ctypes.byref(table_size), False) != 0:
        return None
    count = struct.unpack_from("<L", buffer.raw, 0)[0]
    row_size = ctypes.sizeof(_Row)
    for index in range(count):
        offset = 4 + index * row_size
        if offset + row_size > len(buffer.raw):
            return None
        row = _Row.from_buffer_copy(buffer.raw[offset : offset + row_size])
        if row.dest == 0 and row.mask == 0:
            return socket.inet_ntoa(struct.pack("<L", row.next_hop))
    return None


def _udp(request: bytes, address: tuple[str, int], timeout: float) -> bytes | None:
    """One UDP exchange; a silent port is an answer too, and reads as None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(request, address)
        return sock.recv(512)
    except OSError:
        return None
    finally:
        sock.close()


def natpmp_pack(port: int, lifetime: int = LIFETIME) -> bytes:
    """A TCP mapping request for ``port`` (version 0, opcode 2)."""
    return struct.pack("!BBHHHI", 0, 2, 0, port, port, lifetime)


def natpmp_release(port: int) -> bytes:
    """A request that drops the mapping: lifetime zero."""
    return struct.pack("!BBHHHI", 0, 2, 0, port, port, 0)


def natpmp_unpack(reply: bytes) -> dict | None:
    """The result of a mapping request, or None when the router refused it."""
    if len(reply) < 16:
        return None
    version, opcode, result, _epoch, _internal, external, lifetime = struct.unpack(
        "!BBHIHHI", reply[:16]
    )
    if version != 0 or opcode != 130 or result != 0 or not lifetime:
        return None
    return {"port": external, "lifetime": lifetime}


def natpmp_map(
    port: int,
    gateway: str,
    lifetime: int = LIFETIME,
    exchange: Exchange | None = None,
) -> dict | None:
    """Ask the gateway for a TCP mapping with NAT-PMP."""
    send = exchange or _udp
    reply = send(natpmp_pack(port, lifetime), (gateway, NATPMP_PORT), 1.5)
    if reply is None:
        return None
    mapped = natpmp_unpack(reply)
    if mapped is None:
        return None
    public = _natpmp_public(gateway, send)
    mapped["source"] = "NAT-PMP"
    mapped["external"] = public
    return mapped


def _natpmp_public(gateway: str, send: Exchange) -> str | None:
    reply = send(struct.pack("!BBHI", 0, 0, 0, 0), (gateway, NATPMP_PORT), 1.5)
    if reply is None or len(reply) < 12:
        return None
    version, opcode, result, _epoch, address = struct.unpack("!BBHII", reply[:12])
    if version != 0 or opcode != 128 or result != 0 or not address:
        return None
    return socket.inet_ntoa(struct.pack("<L", address))


def natpmp_unmap(port: int, gateway: str, exchange: Exchange | None = None) -> bool:
    """Drop the mapping; the router answers with the rule it removed."""
    send = exchange or _udp
    return _silent_release(send(natpmp_release(port), (gateway, NATPMP_PORT), 1.5))


def _silent_release(reply: bytes | None) -> bool:
    """A zero lifetime is not answerable with a mapping; a reply means accepted."""
    if reply is None or len(reply) < 16:
        return False
    version, opcode, result = struct.unpack("!BBH", reply[:4])
    return version == 0 and opcode == 130 and result == 0


def ssdp_request(service: str) -> bytes:
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDRESS[0]}:{SSDP_ADDRESS[1]}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"MX: {SSDP_MX}\r\n"
        f"ST: {service}\r\n\r\n"
    ).encode("ascii")


def ssdp_locations(reply: str) -> list[str]:
    found: list[str] = []
    for line in reply.splitlines():
        name, _, value = line.partition(":")
        if name.strip().lower() == "location" and value.strip():
            location = value.strip()
            if location not in found:
                found.append(location)
    return found


def _ssdp(timeout: float) -> list[str]:
    found: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.4)
    deadline = time.monotonic() + max(timeout, 0.4)
    try:
        sock.sendto(ssdp_request(WAN_SERVICES[0]), SSDP_ADDRESS)
        while time.monotonic() < deadline and len(found) < 4:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            for location in ssdp_locations(data.decode("utf-8", "replace")):
                if location not in found:
                    found.append(location)
    finally:
        sock.close()
    return found


def _http_get(url: str, timeout: float = 2.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            return answer.read().decode("utf-8", "replace")
    except (OSError, urllib.error.URLError):
        return None


def _http_post(url: str, action: str, service: str, body: str, timeout: float = 2.0) -> str | None:
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service}#{action}"',
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return answer.read().decode("utf-8", "replace")
    except (OSError, urllib.error.URLError):
        return None


def control_url(description: str, location: str) -> str | None:
    """The WAN connection control URL declared by a device description."""
    try:
        root = ET.fromstring(description)
    except ET.ParseError:
        return None
    for service in root.iter():
        if not service.tag.endswith("service"):
            continue
        kind = _child_text(service, "serviceType")
        control = _child_text(service, "controlURL")
        if not kind or not control:
            continue
        if any(kind.startswith(name) for name in WAN_SERVICES):
            return urljoin(location, control)
    return None


def service_type(description: str) -> str | None:
    try:
        root = ET.fromstring(description)
    except ET.ParseError:
        return None
    for service in root.iter():
        if not service.tag.endswith("service"):
            continue
        kind = _child_text(service, "serviceType")
        if kind and any(kind.startswith(name) for name in WAN_SERVICES):
            return kind
    return None


def _child_text(element, name: str) -> str | None:
    for child in element:
        if child.tag.split("}")[-1] == name and child.text:
            return child.text.strip()
    return None


def add_mapping_body(port: int, internal: str, service: str, lifetime: int = 0) -> str:
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:AddPortMapping xmlns:u="{service}">'
        "<NewRemoteHost></NewRemoteHost>"
        f"<NewExternalPort>{port}</NewExternalPort>"
        "<NewProtocol>TCP</NewProtocol>"
        f"<NewInternalPort>{port}</NewInternalPort>"
        f"<NewInternalClient>{internal}</NewInternalClient>"
        "<NewEnabled>1</NewEnabled>"
        f"<NewPortMappingDescription>{DESCRIPTION}</NewPortMappingDescription>"
        f"<NewLeaseDuration>{lifetime}</NewLeaseDuration>"
        "</u:AddPortMapping>"
        "</s:Body></s:Envelope>"
    )


def delete_mapping_body(port: int, service: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:DeletePortMapping xmlns:u="{service}">'
        "<NewRemoteHost></NewRemoteHost>"
        f"<NewExternalPort>{port}</NewExternalPort>"
        "<NewProtocol>TCP</NewProtocol>"
        "</u:DeletePortMapping>"
        "</s:Body></s:Envelope>"
    )


def external_ip_body(service: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:GetExternalIPAddress xmlns:u="{service}"></u:GetExternalIPAddress>'
        "</s:Body></s:Envelope>"
    )


def read_external_ip(answer: str) -> str | None:
    try:
        root = ET.fromstring(answer)
    except ET.ParseError:
        return None
    for element in root.iter():
        if element.tag.split("}")[-1] == "NewExternalIPAddress" and element.text:
            address = element.text.strip()
            try:
                if not ipaddress.ip_address(address).is_unspecified:
                    return address
            except ValueError:
                return None
    return None


def upnp_open(
    port: int,
    internal: str | None = None,
    discover: Callable[[], list[str]] | None = None,
    get: Callable[[str], str | None] | None = None,
    post: Callable[[str, str, str, str], str | None] | None = None,
    lifetime: int = 0,
) -> dict | None:
    """Ask the router, through UPnP IGD, for a TCP mapping and its public address."""
    search = discover or (lambda: _ssdp(SSDP_MX))
    fetch = get or _http_get
    send = post or _http_post
    client = internal or outbound_address()
    for location in search():
        description = fetch(location)
        if not description:
            continue
        control = control_url(description, location)
        service = service_type(description)
        if not control or not service:
            continue
        answer = send(
            control,
            "AddPortMapping",
            service,
            add_mapping_body(port, client, service, lifetime),
        )
        if answer is None:
            continue
        external = None
        seen = send(control, "GetExternalIPAddress", service, external_ip_body(service))
        if seen:
            external = read_external_ip(seen)
        return {
            "port": port,
            "lifetime": lifetime,
            "source": "UPnP",
            "external": external,
            "control": control,
            "service": service,
        }
    return None


def upnp_close(
    port: int,
    discover: Callable[[], list[str]] | None = None,
    get: Callable[[str], str | None] | None = None,
    post: Callable[[str, str, str, str], str | None] | None = None,
) -> bool:
    search = discover or (lambda: _ssdp(SSDP_MX))
    fetch = get or _http_get
    send = post or _http_post
    for location in search():
        description = fetch(location)
        if not description:
            continue
        control = control_url(description, location)
        service = service_type(description)
        if not control or not service:
            continue
        if send(control, "DeletePortMapping", service, delete_mapping_body(port, service)) is not None:
            return True
    return False


def public_open(port: int, lifetime: int = LIFETIME) -> dict:
    """Try NAT-PMP and then UPnP; a failure carries the reason the page shows."""
    gateway = default_gateway()
    if gateway:
        mapped = natpmp_map(port, gateway, lifetime)
        if mapped:
            mapped["gateway"] = gateway
            return _done(mapped)
    mapped = upnp_open(port, lifetime=lifetime)
    if mapped:
        mapped["gateway"] = gateway
        return _done(mapped)
    reason = "no gateway answered NAT-PMP" if gateway else "this machine has no default gateway"
    return {"mapped": False, "reason": f"{reason}; UPnP found no usable router"}


def _done(mapped: dict) -> dict:
    mapped["mapped"] = True
    return mapped


def public_close(port: int) -> bool:
    gateway = default_gateway()
    if gateway and natpmp_unmap(port, gateway):
        return True
    return upnp_close(port)
