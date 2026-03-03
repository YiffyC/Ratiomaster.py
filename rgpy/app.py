from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .proxy import RatioGhostProxy
from .settings import Settings
from .utils import format_data, format_elapsed


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ratio Ghost Python port (core proxy)")
    parser.add_argument("--port", type=int, default=None, help="Proxy listen port")
    parser.add_argument("--verbose", action="store_true", help="Enable proxy traffic logs")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = Settings()
    store.load()
    if args.port:
        store.values["listen_port"] = args.port

    proxy = RatioGhostProxy(store.values, verbose=args.verbose)
    await proxy.start()

    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    udp_state = "on" if int(store.values.get("udp_enabled", 1)) else "off"
    print(f"Listening on 127.0.0.1:{store.values['listen_port']} (UDP {udp_state})")

    serve_task = asyncio.create_task(proxy.serve_forever())
    await stop.wait()

    serve_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await serve_task

    totals = proxy.get_totals()
    runtime = int(store.values.get("runtime", 0))
    print(
        "Session totals:",
        f"actual down/up {format_data(totals['actual_down'])}/{format_data(totals['actual_up'])}",
        f"reported down/up {format_data(totals['reported_down'])}/{format_data(totals['reported_up'])}",
        f"runtime {format_elapsed(runtime)}",
    )
    store.save(totals)


if __name__ == "__main__":
    import contextlib

    asyncio.run(main())
