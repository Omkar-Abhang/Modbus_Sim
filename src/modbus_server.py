"""
Modbus TCP server (pymodbus 3.6). One TCP port, one simulated device per unit id.

Devices are looked up from the store on every request, so devices added / disabled in the UI take effect immediately.
Unknown or disabled unit ids get no response (like a missing real device -> gateway logs a timeout).
"""
import time

from loguru import logger
from pymodbus.datastore import ModbusServerContext
from pymodbus.datastore.context import ModbusBaseSlaveContext
from pymodbus.exceptions import NoSuchSlaveException
from pymodbus.server import StartAsyncTcpServer
from pymodbus.server.async_io import ModbusServerRequestHandler

from src import request_log
from src.config import MODBUS_HOST, MODBUS_PORT
from src.engine import engine

WRITE_FCS = (5, 6, 15, 16)

# unit id -> client "ip:port" of the latest request (set by the request tracer, used in the request log)
_last_client = {}


class DeviceContext(ModbusBaseSlaveContext):
    """Slave context of one unit id, backed by the simulation engine."""

    def __init__(self, unit_id):
        self.unit_id = unit_id

    def _device(self):
        return engine.device_by_unit(self.unit_id)

    def reset(self):
        pass

    def validate(self, fc_as_hex, address, count=1):
        device = self._device()
        if device is None:
            return False
        if fc_as_hex in WRITE_FCS:
            return True  # gateway out_registers may write outside the input map
        ok = engine.read(device, fc_as_hex, address, count) is not None
        if not ok:
            stats = engine.stats_for(device["id"])
            stats.errors += 1
            stats.last_error = f"Illegal address: FC{fc_as_hex} {address}..{address + count - 1}"
            request_log.add(self.unit_id, fc_as_hex, address, count, False, "Illegal data address",
                            _last_client.get(self.unit_id), device["name"])
        return ok

    def getValues(self, fc_as_hex, address, count=1):
        device = self._device()
        values = engine.read(device, fc_as_hex, address, count) if device else None
        stats = engine.stats_for(device["id"]) if device else None
        if values is None:
            return [0] * count
        if fc_as_hex in WRITE_FCS:
            return values  # read-back after a write, already logged by setValues
        stats.polls.append(time.time())
        stats.last_poll = time.time()
        stats.last_client = _last_client.get(self.unit_id)
        request_log.add(self.unit_id, fc_as_hex, address, count, True, None, stats.last_client, device["name"])
        return values

    def setValues(self, fc_as_hex, address, values):
        device = self._device()
        if device is None:
            return
        engine.write(device, fc_as_hex, address, values)
        request_log.add(self.unit_id, fc_as_hex, address, len(values), True, None,
                        _last_client.get(self.unit_id), device["name"])


class SimulatorServerContext(ModbusServerContext):
    """Resolves unit ids against the device store instead of a fixed dict."""

    def __init__(self):
        super().__init__(slaves={}, single=False)
        self._contexts = {}

    def __contains__(self, slave):
        return engine.device_by_unit(slave) is not None

    def slaves(self):
        # the framer silently drops unit ids not in this list; accept all so unknown ones reach __getitem__
        # (logged there, then ignore_missing_slaves sends no response)
        return list(range(1, 248))

    def __getitem__(self, slave):
        device = engine.device_by_unit(slave)
        if device is None:
            request_log.add(slave, None, None, None, False, "No such unit id (no response sent)",
                            _last_client.get(slave))
            raise NoSuchSlaveException(f"unit {slave} not simulated")
        return self._contexts.setdefault(slave, DeviceContext(slave))


# pymodbus passes addr=None for TCP, so take the client IP from the connection itself
_original_execute = ModbusServerRequestHandler.execute


def _execute_with_client(self, request, *addr):
    try:
        peer = self.transport.get_extra_info("peername") if self.transport else None
        if peer:
            _last_client[request.slave_id] = peer[0]
    except Exception:
        pass
    return _original_execute(self, request, *addr)


ModbusServerRequestHandler.execute = _execute_with_client


async def run_modbus_server():
    logger.info(f"Modbus TCP server listening on {MODBUS_HOST}:{MODBUS_PORT}")
    await StartAsyncTcpServer(
        context=SimulatorServerContext(),
        address=(MODBUS_HOST, MODBUS_PORT),
        ignore_missing_slaves=True,
    )
