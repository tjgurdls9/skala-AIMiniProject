"""Local-only API; forwarded client headers cannot bypass the loopback boundary."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.api:app", host="127.0.0.1", port=8000, proxy_headers=False, access_log=False)
