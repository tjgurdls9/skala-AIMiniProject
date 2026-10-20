"""Local-only API; forwarded client headers cannot bypass the loopback boundary."""

import uvicorn
import os

if __name__ == "__main__":
    port = int(os.environ.get("LIFECYCLE_PORT", "8000"))
    if not 1024 <= port <= 65535:
        raise ValueError("LIFECYCLE_PORT must be between 1024 and 65535")
    uvicorn.run("backend.api:app", host="127.0.0.1", port=port, proxy_headers=False, access_log=False)
