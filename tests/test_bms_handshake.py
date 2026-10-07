"""
Test Suite: BMS Handshake, Periodic Broadcasting, and Alive Counter Validation.
Verifies Layer 2 CAN bus presence, periodicity, and counter continuity.
"""

import time
import pytest
from core.bms_protocol import (
    CAN_ID_HEARTBEAT,
    CAN_ID_PACK_METRICS,
    CAN_ID_CELL_VOLTAGES,
    CAN_ID_TEMPERATURES,
    CAN_ID_DIAGNOSTICS,
    BMSProtocolCodec,
    BMSState,
)


@pytest.mark.smoke
def test_bms_heartbeat_broadcast(bms_session):
    """Verify that the BMS periodically broadcasts heartbeat message 0x180 at 10 Hz."""
    bus, _ = bms_session

    msg = bus.recv(timeout=0.5, filter_id=CAN_ID_HEARTBEAT)
    assert msg is not None, "Failed to receive BMS Heartbeat (0x180) within 500ms timeout"

    decoded = BMSProtocolCodec.decode_heartbeat(msg.data)
    assert isinstance(decoded["state"], BMSState)
    assert decoded["state"] in [BMSState.STANDBY, BMSState.CHARGING, BMSState.DISCHARGING]
    assert 0 <= decoded["alive_counter"] <= 255


@pytest.mark.smoke
def test_all_mandatory_can_ids_present(bms_session):
    """Verify that all 5 mandatory periodic CAN frames (0x180..0x184) are transmitted."""
    bus, _ = bms_session

    time.sleep(0.25)  # Wait for a couple of 10Hz cycles
    messages = bus.drain()
    received_ids = {m.arbitration_id for m in messages}

    mandatory_ids = {
        CAN_ID_HEARTBEAT,
        CAN_ID_PACK_METRICS,
        CAN_ID_CELL_VOLTAGES,
        CAN_ID_TEMPERATURES,
        CAN_ID_DIAGNOSTICS,
    }

    missing_ids = mandatory_ids - received_ids
    assert not missing_ids, f"BMS failed to broadcast mandatory CAN IDs: {[hex(x) for x in missing_ids]}"


@pytest.mark.smoke
def test_alive_counter_increments(bms_session):
    """Verify that the rolling alive counter increments sequentially on each broadcast."""
    bus, _ = bms_session

    msg1 = bus.recv(timeout=0.5, filter_id=CAN_ID_HEARTBEAT)
    assert msg1 is not None
    c1 = BMSProtocolCodec.decode_heartbeat(msg1.data)["alive_counter"]

    msg2 = bus.recv(timeout=0.5, filter_id=CAN_ID_HEARTBEAT)
    assert msg2 is not None
    c2 = BMSProtocolCodec.decode_heartbeat(msg2.data)["alive_counter"]

    expected_next = (c1 + 1) & 0xFF
    assert c2 == expected_next, f"Alive counter gap detected: got {c2}, expected {expected_next}"
