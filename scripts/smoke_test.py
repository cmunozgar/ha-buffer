"""Check the integration's GraphQL against your real Buffer account (read-only).

    pip install aiohttp
    BUFFER_API_KEY=... python scripts/smoke_test.py

Uses 2 API requests. Does not create anything.
"""

import asyncio
import importlib.util
import os
import pathlib
import sys
import types

import aiohttp

# Load api.py + const.py without importing Home Assistant.
pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "buffer"
pkg = types.ModuleType("buffer_standalone")
pkg.__path__ = [str(pkg_dir)]
sys.modules["buffer_standalone"] = pkg
for name in ("const", "api"):
    spec = importlib.util.spec_from_file_location(f"buffer_standalone.{name}", pkg_dir / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
api = sys.modules["buffer_standalone.api"]


async def main() -> None:
    key = os.environ.get("BUFFER_API_KEY") or sys.exit("Set BUFFER_API_KEY")
    async with aiohttp.ClientSession() as session:
        client = api.BufferClient(session, key)
        orgs = await client.get_organizations()
        print("Organizations:", [(o.id, o.name) for o in orgs])
        ov = await client.get_overview(orgs[0].id)
        print(f"\nChannels in '{orgs[0].name}':")
        for c in ov.channels.values():
            flags = [n for n, v in (("DISCONNECTED", c.is_disconnected), ("paused", c.is_queue_paused)) if v]
            print(f"  {c.service:<12} {c.title:<30} queue={len(ov.scheduled_for(c.id)):<3} {' '.join(flags)}")
        print(f"\nScheduled: {len(ov.scheduled)}  Sent (recent): {len(ov.sent)}  Failed: {len(ov.failed)}")
        if ov.scheduled:
            p = ov.scheduled[0]
            print(f"Next post: {p.due_at}  {p.text[:60]!r}")
        print(f"Requests remaining (tightest window): {ov.rate_limit_remaining}")


asyncio.run(main())
