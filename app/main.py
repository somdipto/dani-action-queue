"""Uvicorn entry point: uvicorn app.main:app"""
from app.api import app  # noqa: F401

if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("DAQ_HOST", "127.0.0.1"),
        port=int(os.environ.get("DAQ_PORT", "8000")),
        reload=False,
    )
