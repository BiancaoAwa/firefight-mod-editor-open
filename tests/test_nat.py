"""The router side of the public listener: NAT-PMP packets and UPnP requests."""

import struct
import unittest
from unittest import mock

from core.web import nat

DESCRIPTION = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <friendlyName>Router</friendlyName>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
        <controlURL>/ctl/IPConn</controlURL>
      </service>
    </serviceList>
  </device>
</root>
"""

SOAP_ADDED = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body><u:AddPortMappingResponse xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1"/></s:Body>
</s:Envelope>
"""

SOAP_ADDRESS = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body><u:GetExternalIPAddressResponse xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">
    <NewExternalIPAddress>203.0.113.9</NewExternalIPAddress>
  </u:GetExternalIPAddressResponse></s:Body>
</s:Envelope>
"""


def mapping_reply(port: int, lifetime: int, result: int = 0) -> bytes:
    return struct.pack("!BBHIHHI", 0, 130, result, 0, port, port, lifetime)


def address_reply(address: str) -> bytes:
    packed = struct.unpack("<I", bytes(int(part) for part in address.split(".")))[0]
    return struct.pack("!BBHII", 0, 128, 0, 0, packed)


class NatPmpTests(unittest.TestCase):
    def test_the_request_names_the_port_and_the_lifetime(self) -> None:
        self.assertEqual(nat.natpmp_pack(8797, 3600), struct.pack("!BBHHHI", 0, 2, 0, 8797, 8797, 3600))

    def test_a_refusal_is_reported_as_no_mapping(self) -> None:
        self.assertIsNone(nat.natpmp_unpack(mapping_reply(8797, 0, result=2)))

    def test_a_mapping_says_which_external_port_it_opened(self) -> None:
        self.assertEqual(
            nat.natpmp_unpack(mapping_reply(8797, 3600)),
            {"port": 8797, "lifetime": 3600},
        )

    def test_the_gateway_answer_carries_the_public_address(self) -> None:
        replies = [mapping_reply(8797, 3600), address_reply("203.0.113.9")]

        def exchange(request: bytes, address: tuple[str, int], timeout: float) -> bytes | None:
            return replies.pop(0)

        mapped = nat.natpmp_map(8797, "192.168.0.1", 3600, exchange=exchange)
        self.assertEqual(mapped["source"], "NAT-PMP")
        self.assertEqual(mapped["port"], 8797)
        self.assertEqual(mapped["external"], "203.0.113.9")

    def test_a_silent_gateway_is_no_mapping(self) -> None:
        mapped = nat.natpmp_map(8797, "192.168.0.1", 3600, exchange=lambda request, address, timeout: None)
        self.assertIsNone(mapped)

    def test_a_release_is_accepted_when_the_router_answers(self) -> None:
        self.assertTrue(
            nat.natpmp_unmap(8797, "192.168.0.1", exchange=lambda request, address, timeout: mapping_reply(8797, 0))
        )

    def test_a_release_is_not_claimed_when_the_router_is_silent(self) -> None:
        self.assertFalse(
            nat.natpmp_unmap(8797, "192.168.0.1", exchange=lambda request, address, timeout: None)
        )


class UpnpTests(unittest.TestCase):
    def test_the_control_url_is_read_out_of_the_description(self) -> None:
        self.assertEqual(
            nat.control_url(DESCRIPTION, "http://192.168.0.1:5000/rootDesc.xml"),
            "http://192.168.0.1:5000/ctl/IPConn",
        )

    def test_the_service_kind_is_kept_for_the_soap_action(self) -> None:
        self.assertEqual(
            nat.service_type(DESCRIPTION),
            "urn:schemas-upnp-org:service:WANIPConnection:1",
        )

    def test_the_public_address_is_read_out_of_the_answer(self) -> None:
        self.assertEqual(nat.read_external_ip(SOAP_ADDRESS), "203.0.113.9")

    def test_a_mapping_is_requested_and_its_address_reported(self) -> None:
        posted: list[tuple[str, str]] = []

        def post(url: str, action: str, service: str, body: str) -> str | None:
            posted.append((action, body))
            return SOAP_ADDED if action == "AddPortMapping" else SOAP_ADDRESS

        mapped = nat.upnp_open(
            8797,
            internal="192.168.0.102",
            discover=lambda: ["http://192.168.0.1:5000/rootDesc.xml"],
            get=lambda url: DESCRIPTION,
            post=post,
        )
        self.assertEqual(mapped["source"], "UPnP")
        self.assertEqual(mapped["external"], "203.0.113.9")
        self.assertEqual([action for action, _ in posted], ["AddPortMapping", "GetExternalIPAddress"])
        self.assertIn("<NewInternalClient>192.168.0.102</NewInternalClient>", posted[0][1])
        self.assertIn("<NewExternalPort>8797</NewExternalPort>", posted[0][1])

    def test_a_router_that_does_not_answer_leaves_no_mapping(self) -> None:
        self.assertIsNone(
            nat.upnp_open(8797, discover=lambda: [], get=lambda url: None, post=lambda *args: None)
        )

    def test_the_close_request_names_the_port_it_drops(self) -> None:
        posted: list[str] = []

        def post(url: str, action: str, service: str, body: str) -> str | None:
            posted.append(action)
            self.assertIn("<NewExternalPort>8797</NewExternalPort>", body)
            return SOAP_ADDED

        self.assertTrue(
            nat.upnp_close(
                8797,
                discover=lambda: ["http://192.168.0.1:5000/rootDesc.xml"],
                get=lambda url: DESCRIPTION,
                post=post,
            )
        )
        self.assertEqual(posted, ["DeletePortMapping"])


class PublicOpenTests(unittest.TestCase):
    def test_a_machine_without_a_gateway_says_so(self) -> None:
        with mock.patch.object(nat, "default_gateway", return_value=None), mock.patch.object(
            nat, "upnp_open", return_value=None
        ):
            answer = nat.public_open(8797)
        self.assertFalse(answer["mapped"])
        self.assertIn("no default gateway", answer["reason"])

    def test_the_gateway_that_answers_natpmp_is_not_asked_through_upnp(self) -> None:
        with mock.patch.object(nat, "default_gateway", return_value="192.168.0.1"), mock.patch.object(
            nat, "natpmp_map", return_value={"port": 8797, "lifetime": 3600, "source": "NAT-PMP", "external": "203.0.113.9"}
        ), mock.patch.object(nat, "upnp_open") as upnp:
            answer = nat.public_open(8797)
        self.assertTrue(answer["mapped"])
        upnp.assert_not_called()

    def test_the_upnp_request_carries_the_lifetime_the_page_reports(self) -> None:
        with mock.patch.object(nat, "default_gateway", return_value="192.168.0.1"), mock.patch.object(
            nat, "natpmp_map", return_value=None
        ), mock.patch.object(
            nat, "upnp_open", return_value={"port": 8797, "lifetime": 7200, "source": "UPnP"}
        ) as upnp:
            nat.public_open(8797)
        self.assertEqual(upnp.call_args.kwargs.get("lifetime"), 7200)

    def test_a_router_that_ignores_natpmp_is_asked_through_upnp(self) -> None:
        with mock.patch.object(nat, "default_gateway", return_value="192.168.0.1"), mock.patch.object(
            nat, "natpmp_map", return_value=None
        ), mock.patch.object(
            nat,
            "upnp_open",
            return_value={"port": 8797, "lifetime": 0, "source": "UPnP", "external": "203.0.113.9"},
        ):
            answer = nat.public_open(8797)
        self.assertTrue(answer["mapped"])
        self.assertEqual(answer["source"], "UPnP")
