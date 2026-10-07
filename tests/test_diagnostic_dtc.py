"""
Test Suite: Automotive Diagnostic Trouble Code (DTC) Validation.
Verifies DTC representation, multi-fault arbitration, and false-positive immunity.
"""

import time
import pytest
from core.bms_protocol import (
    CAN_ID_DIAGNOSTICS,
    BMSProtocolCodec,
    ContactorState,
    DTC,
)


@pytest.mark.diagnostic
def test_no_false_positive_dtcs_under_nominal(bms_session):
    """Verify that no false-positive DTCs are declared during nominal steady-state operation."""
    bus, _ = bms_session

    time.sleep(0.3)
    messages = bus.drain()
    diag_msgs = [m for m in messages if m.arbitration_id == CAN_ID_DIAGNOSTICS]

    assert len(diag_msgs) > 0, "No diagnostics frames broadcast under nominal conditions"

    for msg in diag_msgs:
        decoded = BMSProtocolCodec.decode_diagnostics(msg.data)
        assert len(decoded["active_dtcs"]) == 0, f"False positive DTC declared: {decoded['active_dtcs']}"
        assert decoded["contactor_state"] == ContactorState.CLOSED
        assert decoded["fault_count"] == 0


@pytest.mark.diagnostic
def test_multiple_simultaneous_dtcs(bms_session):
    """Verify that multiple concurrent faults are properly captured in diagnostic telemetry."""
    bus, sim = bms_session

    # Simultaneously inject Overvoltage and Overtemperature
    sim.inject_cell_overvoltage(0, 4290)
    sim.inject_overtemperature(66)
    time.sleep(0.15)

    msg = bus.recv(timeout=0.5, filter_id=CAN_ID_DIAGNOSTICS)
    assert msg is not None

    decoded = BMSProtocolCodec.decode_diagnostics(msg.data)
    assert decoded["fault_count"] >= 2
    assert DTC.CELL_OVER_VOLTAGE in decoded["active_dtcs"]
    assert DTC.PACK_OVER_TEMPERATURE in decoded["active_dtcs"]
    assert decoded["contactor_state"] == ContactorState.FAULT_TRIPPED
