"""
Pytest Fixtures and Global Harness Configuration for EV BMS Testing.
Manages simulator lifecycle, CAN bus instantiation, and test isolation.
"""

import json
from pathlib import Path
from typing import Generator, Tuple, Dict, Any
import pytest
import yaml

from core.transport_can import VirtualCANBus
from core.bms_simulator import BMSSimulator


@pytest.fixture(scope="session")
def bms_config() -> Dict[str, Any]:
    """Loads calibration thresholds from YAML configuration."""
    config_path = Path(__file__).parent / "config" / "bms_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["bms"]


@pytest.fixture(scope="session")
def fault_vectors() -> list:
    """Loads data-driven fault injection test cases."""
    vectors_path = Path(__file__).parent / "test_data" / "fault_injection_vectors.json"
    with open(vectors_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def bms_rig() -> Generator[Tuple[VirtualCANBus, BMSSimulator], None, None]:
    """
    Module-scoped test rig: Starts background BMS simulation and yields
    the virtual CAN bus and simulator handles.
    """
    bus = VirtualCANBus("vcan0")
    sim = BMSSimulator(bus, cell_count=16)
    sim.start()

    yield bus, sim

    sim.stop()
    bus.shutdown()


@pytest.fixture(scope="function")
def bms_session(bms_rig) -> Generator[Tuple[VirtualCANBus, BMSSimulator], None, None]:
    """
    Function-scoped fixture ensuring clean test isolation.
    Resets all simulated cell voltages, temperatures, contactors, and clears CAN buffer.
    """
    bus, sim = bms_rig
    sim.clear_faults()
    bus.clear()

    yield bus, sim

    sim.clear_faults()
    bus.clear()
