"""Modbus Device Simulator: web UI/API (API_PORT) + Modbus TCP server (MODBUS_PORT) in one process."""
import asyncio
import logging
import sys

import uvicorn
from loguru import logger

from src.config import API_HOST, API_PORT, LOGLEVEL, MODBUS_PORT

logger.remove()
logger.add(sys.stderr, level=LOGLEVEL)
# pymodbus logs every missing unit id as an error - keep it quiet unless debugging
logging.getLogger("pymodbus").setLevel(logging.DEBUG if LOGLEVEL == "DEBUG" else logging.CRITICAL)


async def main():
    from src.api import app
    from src.modbus_server import run_modbus_server

    server = uvicorn.Server(uvicorn.Config(app, host=API_HOST, port=API_PORT, log_level="warning"))
    logger.info(f"UI / API on http://{API_HOST}:{API_PORT}  ·  Modbus TCP on port {MODBUS_PORT}")

    modbus_task = asyncio.ensure_future(run_modbus_server())
    await server.serve()  # returns on Ctrl-C / SIGTERM
    modbus_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
