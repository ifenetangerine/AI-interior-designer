#!/usr/bin/env python3
"""Run the FastAPI viewer API server."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "colayout.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
