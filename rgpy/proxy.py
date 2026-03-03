from __future__ import annotations

import asyncio
import logging
import random
import re
import socket
import ssl
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

from .utils import get_resource_path


@dataclass
class TorrentStats:
    actual_first: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    actual_last: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    actual_sum: dict[str, tuple[int, int]] = field(default_factory=dict)

    reported_last: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    reported_sum: dict[str, tuple[int, int]] = field(default_factory=dict)
    reported_last_time: dict[str, int] = field(default_factory=dict)

    response: dict[tuple[str, str], int] = field(default_factory=dict)

    total_actual_up: int = 0
    total_actual_down: int = 0
    total_reported_up: int = 0
    total_reported_down: int = 0

    def update_actual(self, info_hash: str, event: str, down: int, up: int, left: int) -> tuple[int, int]:
        prev_down = 0
        prev_up = 0

        if info_hash not in self.actual_first:
            self.actual_first[info_hash] = (down, up, left)

        self.actual_sum.setdefault(info_hash, (0, 0))
        if info_hash in self.actual_last and event != "started":
            d, u, _ = self.actual_last[info_hash]
            ad, au = self.actual_sum[info_hash]
            self.actual_sum[info_hash] = ((down - d) + ad, (up - u) + au)
            prev_down, prev_up = d, u

        self.actual_last[info_hash] = (down, up, left)

        down_diff = down - prev_down
        up_diff = up - prev_up

        if down_diff > 0:
            self.total_actual_down += down_diff
        if up_diff > 0:
            self.total_actual_up += up_diff

        return down_diff, up_diff

    def update_reported(self, info_hash: str, event: str, down: int, up: int, left: int) -> None:
        self.reported_sum.setdefault(info_hash, (0, 0))

        if info_hash in self.reported_last and event != "started":
            d, u, _ = self.reported_last[info_hash]
            rd, ru = self.reported_sum[info_hash]
            self.reported_sum[info_hash] = ((down - d) + rd, (up - u) + ru)

        if info_hash in self.reported_last:
            prev_d, prev_u, _ = self.reported_last[info_hash]
            if down > prev_d:
                self.total_reported_down += down - prev_d
            if up > prev_u:
                self.total_reported_up += up - prev_u

        self.reported_last_time[info_hash] = int(time.time())
        self.reported_last[info_hash] = (down, up, left)


@dataclass
class UdpEnvelope:
    payload: bytes
    upstream_host: str | None = None
    upstream_port: int | None = None
    socks5: bool = False


class RatioGhostProxy:
    def __init__(self, settings: dict, verbose: bool = False):
        self.settings = settings
        self.stats = TorrentStats()
        self.verbose = verbose
        self.logger = logging.getLogger("rghost.proxy")
        self.server: asyncio.AbstractServer | None = None
        self.udp_transport: asyncio.DatagramTransport | None = None
        self.udp_protocol: _UdpProxyProtocol | None = None
        self.udp_connection_upstreams: dict[tuple[str, int, int], tuple[str, int]] = {}
        self.udp_pending_connect: dict[tuple[str, int, int], tuple[str, int]] = {}
        self.events: deque[dict[str, object]] = deque(maxlen=400)
        self.event_seq: int = 0

    def _log(self, message: str, *args: object) -> None:
        if self.verbose:
            self.logger.info(message, *args)

    def _add_event(self, message: str) -> None:
        self.event_seq += 1
        self.events.append(
            {
                "id": self.event_seq,
                "ts": int(time.time()),
                "message": message,
            }
        )

    def get_events(self, since_id: int = 0) -> list[dict[str, object]]:
        return [e for e in self.events if int(e["id"]) > int(since_id)]

    async def start(self) -> None:
        host = "127.0.0.1"
        port = int(self.settings["listen_port"])
        self.server = await asyncio.start_server(self.handle_client, host=host, port=port)
        self._log("listening on %s:%s", host, port)

        if int(self.settings.get("udp_enabled", 1)):
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: _UdpProxyProtocol(self),
                local_addr=(host, port),
            )
            self.udp_transport = transport  # type: ignore[assignment]
            self.udp_protocol = protocol  # type: ignore[assignment]
            self._log("udp listening on %s:%s", host, port)

    async def serve_forever(self) -> None:
        if self.server is None:
            return
        try:
            async with self.server:
                await self.server.serve_forever()
        finally:
            if self.udp_transport is not None:
                self.udp_transport.close()

    def get_totals(self) -> dict[str, int]:
        return {
            "actual_down": self.stats.total_actual_down,
            "actual_up": self.stats.total_actual_up,
            "reported_down": self.stats.total_reported_down,
            "reported_up": self.stats.total_reported_up,
        }

    @staticmethod
    async def _safe_close(writer: asyncio.StreamWriter | None) -> None:
        if writer is None:
            return
        try:
            if not writer.is_closing():
                writer.close()
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, OSError, RuntimeError):
            pass

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            peer = writer.get_extra_info("peername")
            client_ip = peer[0] if peer else ""
            client_port = peer[1] if peer and len(peer) > 1 else 0
            self._log("accepted client %s:%s", client_ip or "?", client_port)

            if int(self.settings.get("only_local", 1)) and client_ip not in {"127.0.0.1", "::1"}:
                self._log("blocked non-local client %s:%s", client_ip, client_port)
                await self._safe_close(writer)
                return

            try:
                raw = await reader.readuntil(b"\r\n\r\n")
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionResetError, OSError):
                await self._safe_close(writer)
                return

            req_line, headers = self._parse_head(raw)
            if not req_line:
                await self._safe_close(writer)
                return

            method, target, version = req_line
            self._log("request %s %s %s from %s:%s", method, target, version, client_ip or "?", client_port)

            if method.upper() == "CONNECT":
                await self._handle_connect(target, reader, writer)
                return

            url = urlparse(target)
            if not url.scheme:
                host_header = headers.get("host", "")
                target = f"http://{host_header}{target}"
                url = urlparse(target)

            host = url.hostname
            port = url.port or 80
            if not host:
                await self._safe_close(writer)
                return

            path = (url.path or "/") + (f"?{url.query}" if url.query else "")
            path = self._rewrite_tracker_query(host, port, path)
            if path is None:
                self._log("request blocked by policy for %s:%s", host, port)
                await self._safe_close(writer)
                return

            await self._forward_http(method, version, host, port, path, headers, reader, writer)
        except (ConnectionResetError, BrokenPipeError, OSError):
            self._log("client connection reset/closed")
            await self._safe_close(writer)

    def _rewrite_tracker_query(self, host: str, port: int, path: str) -> Optional[str]:
        if "info_hash=" not in path:
            if int(self.settings.get("only_tracker", 1)):
                self._add_event(f"{host}:{port} Blocked non-tracker traffic.")
                return None
            self._add_event(f"{host}:{port} Forwarding non-tracker traffic.")
            return path

        parsed = urlparse(path)
        params = parse_qs(parsed.query, keep_blank_values=True)

        info_hash = (params.get("info_hash") or [""])[0]
        if not info_hash:
            return path

        try:
            downloaded = int((params.get("downloaded") or ["0"])[0])
            uploaded = int((params.get("uploaded") or ["0"])[0])
            left = int((params.get("left") or ["0"])[0])
        except ValueError:
            return path
        original_downloaded = downloaded
        original_uploaded = uploaded

        event = (params.get("event") or [""])[0]
        down_diff, up_diff = self.stats.update_actual(info_hash, event, downloaded, uploaded, left)

        prev = self.stats.reported_last.get(info_hash, (0, 0, 0))
        prev_down, prev_up, _ = prev
        elapsed = int(time.time()) - self.stats.reported_last_time.get(info_hash, int(time.time()))
        peers = self.stats.response.get((info_hash, "incomplete"), 0)

        if int(self.settings.get("no_download", 0)):
            downloaded = 0
            first = self.stats.actual_first.get(info_hash)
            if first:
                left = first[2]
            if int(self.settings.get("seed", 0)):
                left = 0
            if event == "completed":
                params.pop("event", None)

        min_peers = int(self.settings.get("min_peers", 5))
        if peers >= min_peers:
            down_ratio = random.uniform(float(self.settings["updown_ratio_a"]), float(self.settings["updown_ratio_b"]))
            up_ratio = random.uniform(float(self.settings["upup_ratio_a"]), float(self.settings["upup_ratio_b"]))

            uploaded = int(prev_up + up_diff + (down_ratio * down_diff) + (up_ratio * up_diff))

            if random.random() * 100 < float(self.settings.get("boost_chance", 5)):
                boost = float(self.settings.get("boost", 15)) * 1024 * max(1, elapsed) * random.random()
                uploaded += int(boost)
        else:
            uploaded = int(prev_up + up_diff)

        if event != "started" and uploaded < prev_up:
            return None

        params["downloaded"] = [str(downloaded)]
        params["uploaded"] = [str(uploaded)]
        params["left"] = [str(left)]

        query = urlencode(params, doseq=True)
        rewritten = parsed._replace(query=query)

        self.stats.update_reported(info_hash, event, downloaded, uploaded, left)
        self._log(
            "announce rewritten host=%s:%s hash=%s down=%s up=%s left=%s",
            host,
            port,
            info_hash[:16],
            downloaded,
            uploaded,
            left,
        )
        self._add_event(
            f"{host}:{port} down/up from {original_downloaded}/{original_uploaded} to {downloaded}/{uploaded}"
            + (f" ({event})" if event else "")
        )
        return rewritten.geturl()

    async def _forward_http(
        self,
        method: str,
        version: str,
        host: str,
        port: int,
        path: str,
        headers: dict,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        remote_writer: asyncio.StreamWriter | None = None
        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        except OSError:
            self._log("connect remote failed %s:%s", host, port)
            await self._safe_close(client_writer)
            return

        try:
            self._log("routing HTTP to %s:%s", host, port)
            headers["host"] = host if port == 80 else f"{host}:{port}"
            payload = [f"{method} {path} {version}\r\n"]
            for k, v in headers.items():
                payload.append(f"{k}: {v}\r\n")
            payload.append("\r\n")

            remote_writer.write("".join(payload).encode("latin-1", errors="ignore"))
            await remote_writer.drain()

            body = await client_reader.read(-1)
            if body:
                self._log("client -> remote bytes=%s", len(body))
                remote_writer.write(body)
                await remote_writer.drain()

            response = await remote_reader.read(-1)
            self._log("remote -> client bytes=%s", len(response))
            self._extract_tracker_response(path, response)

            client_writer.write(response)
            await client_writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            await self._safe_close(remote_writer)
            await self._safe_close(client_writer)

    async def _handle_connect(
        self,
        target: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        parts = target.split(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 443

        mitm_enabled = int(self.settings.get("mitm_https", 0)) == 1
        if mitm_enabled and not self._is_ip_literal(host):
            await self._handle_connect_mitm(host, port, client_reader, client_writer)
            return
        await self._handle_connect_tunnel(host, port, client_reader, client_writer)

    async def _handle_connect_tunnel(
        self,
        host: str,
        port: int,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        self._add_event(f"Tunnel to peer at {host}:{port}")

        remote_writer: asyncio.StreamWriter | None = None
        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        except OSError:
            self._log("CONNECT failed to %s:%s", host, port)
            await self._safe_close(client_writer)
            return

        try:
            self._log("CONNECT tunnel established to %s:%s", host, port)
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            await self._safe_close(remote_writer)
            await self._safe_close(client_writer)
            return

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    chunk = await src.read(8192)
                    if not chunk:
                        break
                    if int(self.settings.get("log_tunnel_chunks", 0)):
                        self._log("tunnel chunk bytes=%s", len(chunk))
                    dst.write(chunk)
                    await dst.drain()
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass
            finally:
                await self._safe_close(dst)

        await asyncio.gather(
            pipe(client_reader, remote_writer),
            pipe(remote_reader, client_writer),
            return_exceptions=True,
        )
        await self._safe_close(remote_writer)
        await self._safe_close(client_writer)

    async def _handle_connect_mitm(
        self,
        host: str,
        port: int,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        self._add_event(f"({host}) HTTPS requested")
        try:
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            await self._safe_close(client_writer)
            return

        server_ctx = self._build_mitm_server_context()
        if server_ctx is None:
            self._add_event(f"({host}) MITM TLS certificate unavailable")
            await self._safe_close(client_writer)
            return

        loop = asyncio.get_running_loop()
        client_transport = client_writer.transport
        client_protocol = client_transport.get_protocol()
        try:
            tls_transport = await loop.start_tls(
                client_transport,
                client_protocol,
                server_ctx,
                server_side=True,
            )
        except Exception:
            self._add_event(f"({host}) MITM handshake failed")
            await self._safe_close(client_writer)
            return

        tls_writer = asyncio.StreamWriter(tls_transport, client_protocol, client_reader, loop)
        remote_writer: asyncio.StreamWriter | None = None
        try:
            remote_ctx = self._build_mitm_remote_context()
            remote_reader, remote_writer = await asyncio.open_connection(
                host,
                port,
                ssl=remote_ctx,
                server_hostname=host if remote_ctx.check_hostname else None,
            )
            self._add_event(f"({host}) HTTPS MITM active")
            await self._forward_mitm_http(host, port, client_reader, tls_writer, remote_reader, remote_writer)
        except Exception:
            self._add_event(f"({host}) MITM upstream connect/forward failed")
        finally:
            await self._safe_close(remote_writer)
            await self._safe_close(tls_writer)

    async def _forward_mitm_http(
        self,
        host: str,
        port: int,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        remote_reader: asyncio.StreamReader,
        remote_writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), timeout=8)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
            return

        req_line, headers = self._parse_head(raw)
        if not req_line:
            return

        method, target, version = req_line
        parsed = urlparse(target)
        if parsed.scheme:
            path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        else:
            path = target

        rewritten = self._rewrite_tracker_query(host, port, path)
        if rewritten is None:
            return

        headers["host"] = host if port in {80, 443} else f"{host}:{port}"
        headers["connection"] = "close"
        payload = [f"{method} {rewritten} {version}\r\n"]
        for k, v in headers.items():
            payload.append(f"{k}: {v}\r\n")
        payload.append("\r\n")
        remote_writer.write("".join(payload).encode("latin-1", errors="ignore"))

        content_len = int(headers.get("content-length", "0") or "0")
        if content_len > 0:
            body = await client_reader.readexactly(content_len)
            remote_writer.write(body)
        await remote_writer.drain()

        response = await remote_reader.read(-1)
        self._extract_tracker_response(rewritten, response)
        client_writer.write(response)
        await client_writer.drain()

    def _build_mitm_server_context(self) -> ssl.SSLContext | None:
        cert_path = get_resource_path(str(self.settings.get("mitm_cert_path", "tls/server.crt")))
        key_path = get_resource_path(str(self.settings.get("mitm_key_path", "tls/server.key")))
        if not cert_path.exists() or not key_path.exists():
            return None

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert_path), str(key_path))
        return ctx

    def _build_mitm_remote_context(self) -> ssl.SSLContext:
        if int(self.settings.get("mitm_insecure_upstream", 1)):
            return ssl._create_unverified_context()
        return ssl.create_default_context()

    @staticmethod
    def _is_ip_literal(host: str) -> bool:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                socket.inet_pton(family, host)
                return True
            except OSError:
                continue
        return False

    async def handle_udp_datagram(
        self,
        data: bytes,
        client_addr: tuple[str, int],
        transport: asyncio.DatagramTransport,
    ) -> None:
        client_ip = client_addr[0]
        if int(self.settings.get("only_local", 1)) and client_ip not in {"127.0.0.1", "::1"}:
            self._log("blocked non-local UDP client %s:%s", client_addr[0], client_addr[1])
            return

        envelope = self._parse_udp_envelope(data)
        host, port, route_mode = self._resolve_udp_upstream(client_addr, envelope)
        if not host or port <= 0:
            self._log("udp upstream unresolved; dropping packet from %s:%s", client_addr[0], client_addr[1])
            return

        rewritten, info_hash = self._rewrite_udp_packet(host, port, envelope.payload)
        if rewritten is None:
            return
        action = self._parse_udp_action(envelope.payload)
        self._log(
            "udp route client=%s:%s -> %s:%s mode=%s action=%s hash=%s",
            client_addr[0],
            client_addr[1],
            host,
            port,
            route_mode,
            action if action is not None else "?",
            info_hash[:16] if info_hash else "-",
        )
        self._add_event(
            f"UDP route {client_addr[0]}:{client_addr[1]} -> {host}:{port} mode={route_mode} action={action if action is not None else '?'}"
        )
        self._remember_udp_request_route(client_addr, rewritten, host, port)

        remote_sock = await self._create_udp_socket(host, port)
        if remote_sock is None:
            return
        remote_sock.setblocking(False)
        loop = asyncio.get_running_loop()
        try:
            await loop.sock_sendto(remote_sock, rewritten, (host, port))
            response, remote_addr = await asyncio.wait_for(loop.sock_recvfrom(remote_sock, 65536), timeout=8)
        except (OSError, TimeoutError, asyncio.TimeoutError):
            return
        finally:
            remote_sock.close()

        self._remember_udp_response_route(client_addr, response, host, port)
        if info_hash:
            self._extract_udp_tracker_response(info_hash, response)
        client_payload = self._build_udp_response(envelope, response, remote_addr)
        transport.sendto(client_payload, client_addr)

    @staticmethod
    def _parse_udp_action(payload: bytes) -> int | None:
        if len(payload) < 16:
            return None
        try:
            _, action, _ = struct.unpack_from(">QII", payload, 0)
        except struct.error:
            return None
        return int(action)

    @staticmethod
    def _parse_udp_transaction_id(payload: bytes) -> int | None:
        if len(payload) < 16:
            return None
        try:
            _, _, transaction_id = struct.unpack_from(">QII", payload, 0)
        except struct.error:
            return None
        return int(transaction_id)

    @staticmethod
    def _parse_udp_connection_id(payload: bytes) -> int | None:
        if len(payload) < 8:
            return None
        try:
            connection_id = struct.unpack_from(">Q", payload, 0)[0]
        except struct.error:
            return None
        return int(connection_id)

    def _parse_udp_envelope(self, data: bytes) -> UdpEnvelope:
        # SOCKS5 UDP datagram: RSV(2) FRAG(1) ATYP(1) DST.ADDR DST.PORT DATA
        if len(data) >= 10 and data[0:2] == b"\x00\x00":
            frag = data[2]
            atyp = data[3]
            if frag == 0 and atyp in {1, 3, 4}:
                idx = 4
                host: str | None = None
                if atyp == 1:
                    if len(data) < idx + 4 + 2:
                        return UdpEnvelope(payload=data)
                    host = socket.inet_ntoa(data[idx : idx + 4])
                    idx += 4
                elif atyp == 3:
                    if len(data) < idx + 1:
                        return UdpEnvelope(payload=data)
                    host_len = int(data[idx])
                    idx += 1
                    if len(data) < idx + host_len + 2:
                        return UdpEnvelope(payload=data)
                    host = data[idx : idx + host_len].decode("idna", errors="ignore")
                    idx += host_len
                else:
                    if len(data) < idx + 16 + 2:
                        return UdpEnvelope(payload=data)
                    host = socket.inet_ntop(socket.AF_INET6, data[idx : idx + 16])
                    idx += 16

                port = struct.unpack_from(">H", data, idx)[0]
                idx += 2
                return UdpEnvelope(payload=data[idx:], upstream_host=host, upstream_port=int(port), socks5=True)

        return UdpEnvelope(payload=data)

    def _resolve_udp_upstream(self, client_addr: tuple[str, int], envelope: UdpEnvelope) -> tuple[str | None, int, str]:
        if envelope.upstream_host and envelope.upstream_port:
            return envelope.upstream_host, int(envelope.upstream_port), "socks5"

        payload = envelope.payload
        action = self._parse_udp_action(payload)
        if action in {1, 2}:
            connection_id = self._parse_udp_connection_id(payload)
            if connection_id is not None:
                mapped = self.udp_connection_upstreams.get((client_addr[0], client_addr[1], connection_id))
                if mapped:
                    return mapped[0], mapped[1], "connection_id"

        configured_host = str(self.settings.get("udp_upstream_host", "")).strip()
        configured_port = int(self.settings.get("udp_upstream_port", 0))
        if configured_host and configured_port > 0:
            return configured_host, configured_port, "static"
        return None, 0, "none"

    def _remember_udp_request_route(self, client_addr: tuple[str, int], payload: bytes, host: str, port: int) -> None:
        action = self._parse_udp_action(payload)
        if action != 0:
            return
        transaction_id = self._parse_udp_transaction_id(payload)
        if transaction_id is None:
            return
        self.udp_pending_connect[(client_addr[0], client_addr[1], transaction_id)] = (host, port)

    def _remember_udp_response_route(self, client_addr: tuple[str, int], response: bytes, host: str, port: int) -> None:
        if len(response) < 16:
            return
        try:
            action, transaction_id = struct.unpack_from(">II", response, 0)
        except struct.error:
            return
        if action != 0:
            return
        try:
            connection_id = struct.unpack_from(">Q", response, 8)[0]
        except struct.error:
            return
        upstream = self.udp_pending_connect.pop((client_addr[0], client_addr[1], int(transaction_id)), (host, port))
        self.udp_connection_upstreams[(client_addr[0], client_addr[1], int(connection_id))] = upstream

    async def _create_udp_socket(self, host: str, port: int) -> socket.socket | None:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
        except OSError:
            self._log("udp resolve failed %s:%s", host, port)
            return None
        if not infos:
            self._log("udp resolve returned no results %s:%s", host, port)
            return None
        family = infos[0][0]
        try:
            return socket.socket(family, socket.SOCK_DGRAM)
        except OSError:
            self._log("udp socket create failed for %s:%s", host, port)
            return None

    def _build_udp_response(self, envelope: UdpEnvelope, payload: bytes, remote_addr: tuple) -> bytes:
        if not envelope.socks5:
            return payload
        remote_host = str(remote_addr[0]) if remote_addr else ""
        remote_port = int(remote_addr[1]) if len(remote_addr) > 1 else 0
        return self._pack_socks5_udp(remote_host, remote_port, payload)

    @staticmethod
    def _pack_socks5_udp(host: str, port: int, payload: bytes) -> bytes:
        header = b"\x00\x00\x00"
        try:
            ip = socket.inet_pton(socket.AF_INET, host)
            header += b"\x01" + ip
        except OSError:
            try:
                ip6 = socket.inet_pton(socket.AF_INET6, host)
                header += b"\x04" + ip6
            except OSError:
                encoded = host.encode("idna", errors="ignore")
                if len(encoded) > 255:
                    encoded = encoded[:255]
                header += b"\x03" + bytes([len(encoded)]) + encoded
        header += struct.pack(">H", int(port) & 0xFFFF)
        return header + payload

    def _rewrite_udp_packet(self, host: str, port: int, data: bytes) -> tuple[bytes | None, str | None]:
        if len(data) < 16:
            return data, None

        try:
            _, action, _ = struct.unpack_from(">QII", data, 0)
        except struct.error:
            return data, None

        if action != 1:
            return data, None
        if len(data) < 98:
            return data, None

        try:
            (
                connection_id,
                _,
                transaction_id,
                info_hash_raw,
                peer_id,
                downloaded,
                left,
                uploaded,
                event_code,
                ip_address,
                key,
                num_want,
                peer_port,
            ) = struct.unpack_from(">QII20s20sQQQIIIiH", data, 0)
        except struct.error:
            return data, None

        info_hash = info_hash_raw.hex()
        event = self._udp_event_name(event_code)
        down_diff, up_diff = self.stats.update_actual(info_hash, event, downloaded, uploaded, left)

        _, prev_up, _ = self.stats.reported_last.get(info_hash, (0, 0, 0))
        elapsed = int(time.time()) - self.stats.reported_last_time.get(info_hash, int(time.time()))
        peers = self.stats.response.get((info_hash, "incomplete"), 0)

        if int(self.settings.get("no_download", 0)):
            downloaded = 0
            first = self.stats.actual_first.get(info_hash)
            if first:
                left = first[2]
            if int(self.settings.get("seed", 0)):
                left = 0
            if event_code == 1:
                event_code = 0
                event = ""

        min_peers = int(self.settings.get("min_peers", 5))
        if peers >= min_peers:
            down_ratio = random.uniform(float(self.settings["updown_ratio_a"]), float(self.settings["updown_ratio_b"]))
            up_ratio = random.uniform(float(self.settings["upup_ratio_a"]), float(self.settings["upup_ratio_b"]))
            uploaded = int(prev_up + up_diff + (down_ratio * down_diff) + (up_ratio * up_diff))
            if random.random() * 100 < float(self.settings.get("boost_chance", 5)):
                boost = float(self.settings.get("boost", 15)) * 1024 * max(1, elapsed) * random.random()
                uploaded += int(boost)
        else:
            uploaded = int(prev_up + up_diff)

        if event != "started" and uploaded < prev_up:
            uploaded = prev_up

        self.stats.update_reported(info_hash, event, downloaded, uploaded, left)
        self._log(
            "udp announce rewritten host=%s:%s hash=%s down=%s up=%s left=%s",
            host,
            port,
            info_hash[:16],
            downloaded,
            uploaded,
            left,
        )
        self._add_event(
            f"{host}:{port} UDP down/up to {downloaded}/{uploaded}" + (f" ({event})" if event else "")
        )

        payload = struct.pack(
            ">QII20s20sQQQIIIiH",
            connection_id,
            1,
            transaction_id,
            info_hash_raw,
            peer_id,
            int(downloaded),
            int(left),
            int(uploaded),
            int(event_code),
            int(ip_address),
            int(key),
            int(num_want),
            int(peer_port),
        )
        if len(data) > 98:
            payload += data[98:]
        return payload, info_hash

    @staticmethod
    def _udp_event_name(event_code: int) -> str:
        mapping = {1: "completed", 2: "started", 3: "stopped"}
        return mapping.get(int(event_code), "")

    def _extract_udp_tracker_response(self, info_hash: str, data: bytes) -> None:
        if len(data) < 20:
            return
        try:
            action, _, interval, incomplete, complete = struct.unpack_from(">IIIII", data, 0)
        except struct.error:
            return
        if action != 1:
            return
        self.stats.response[(info_hash, "interval")] = int(interval)
        self.stats.response[(info_hash, "incomplete")] = int(incomplete)
        self.stats.response[(info_hash, "complete")] = int(complete)

    @staticmethod
    def _parse_head(raw: bytes) -> tuple[tuple[str, str, str] | None, dict]:
        text = raw.decode("latin-1", errors="ignore")
        lines = text.split("\r\n")
        if not lines or len(lines[0].split()) < 3:
            return None, {}

        method, target, version = lines[0].split(maxsplit=2)
        headers = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

        return (method, target, version), headers

    def _extract_tracker_response(self, path: str, response: bytes) -> None:
        match = re.search(r"info_hash=([^&]+)", path)
        if not match:
            return

        info_hash = match.group(1)
        body = response.decode("latin-1", errors="ignore")
        for key in ("complete", "incomplete", "interval"):
            m = re.search(rf"{len(key)}:{key}i([0-9]+)e", body)
            if m:
                self.stats.response[(info_hash, key)] = int(m.group(1))


class _UdpProxyProtocol(asyncio.DatagramProtocol):
    def __init__(self, proxy: "RatioGhostProxy"):
        self.proxy = proxy
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.transport is None:
            return
        asyncio.create_task(self.proxy.handle_udp_datagram(data, addr, self.transport))
