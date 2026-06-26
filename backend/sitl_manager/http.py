from typing import Optional

import aiohttp

from sitl_manager.settings import HTTP_TIMEOUT

_session: Optional[aiohttp.ClientSession] = None


def get_session() -> aiohttp.ClientSession:
    """Return a process-wide aiohttp session, recreating it if it was closed.

    Reusing a single session avoids the "create a session per request" pitfall while
    still binding to whatever event loop is running when the first call is made.
    """
    global _session  # pylint: disable=global-statement
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT))
    return _session


async def close_session() -> None:
    global _session  # pylint: disable=global-statement
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None
