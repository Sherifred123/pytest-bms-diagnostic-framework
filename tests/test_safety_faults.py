"""
Test Suite: Critical Electrical Safety, Fault Latching, and Contactor Interlock.
Verifies automotive ISO 26262 safety shutdown requirements under severe fault conditions.
"""

import time
import pytest
from core.bms_protocol import (
    CAN_ID_DIAGNOSTICS,
    CAN_ID_HEARTBEAT,
    BMSProtocolCodec,
    BMSState,
    ContactorState,
    DTC,
)


@pytest.mark.safety
def test_data_driven_fault_injection(bms_session, fault_vectors):
    """
    Data-driven test iterating through JSON fault vectors:
    Verifies DTC latching, contactor shutdown, and BMS state transitions.
    """
    bus, sim = bms_session

    for vector in fault_vectors:
        test_id = vector["test_id"]
        fault_type = vector["fault_type"]
        val = vector["injected_value"]
        cell_idx = vector.get("cell_index", 0)

        # 1. Reset to nominal before each vector
        sim.clear_faults()
        bus.clear()
        time.sleep(0.05)

        # 2. Inject Fault Condition
        if fault_type == "overvoltage":
            sim.inject_cell_overvoltage(cell_idx, int(val))
        elif fault_type == "undervoltage":
            sim.inject_cell_undervoltage(cell_idx, int(val))
        elif fault_type == "overtemperature":
            sim.inject_overtemperature(int(val))
        elif fault_type == "overcurrent":
            sim.inject_overcurrent(float(val))
        elif fault_type == "imbalance":
            sim.inject_cell_imbalance(delta_mv=int(val))

        # 3. Allow BMS 10Hz cycle to detect and act
        time.sleep(0.15)

        # 4. Read Diagnostics Frame 0x184
        diag_msg = bus.recv(timeout=0.5, filter_id=CAN_ID_DIAGNOSTICS)
        assert diag_msg is not None, f"[{test_id}] Failed to receive diagnostics message"
        decoded_diag = BMSProtocolCodec.decode_diagnostics(diag_msg.data)

        # 5. Read Heartbeat Frame 0x180
        hb_msg = bus.recv(timeout=0.5, filter_id=CAN_ID_HEARTBEAT)
        assert hb_msg is not None, f"[{test_id}] Failed to receive heartbeat message"
        decoded_hb = BMSProtocolCodec.decode_heartbeat(hb_msg.data)

        # 6. Assertions against expected outcomes
        expected_dtc_enum = getattr(DTC, vector["expected_dtc"])
        expected_contactor = getattr(ContactorState, vector["expected_contactor"])
        expected_state = getattr(BMSState, vector["expected_bms_state"])

        assert expected_dtc_enum in decoded_diag["active_dtcs"], (
            f"[{test_id}] Expected DTC {expected_dtc_enum.name} not found in active DTCs: "
            f"{[d.name for d in decoded_diag['active_dtcs']]}"
        )
        assert decoded_diag["contactor_state"] == expected_contactor, (
            f"[{test_id}] Contactor state mismatch: got {decoded_diag['contactor_state'].name}, "
            f"expected {expected_contactor.name}"
        )
        assert decoded_hb["state"] == expected_state, (
            f"[{test_id}] BMS state mismatch: got {decoded_hb['state'].name}, "
            f"expected {expected_state.name}"
        )


@pytest.mark.safety
def test_fault_clearing_and_system_recovery(bms_session):
    """
    Verifies that after clearing a critical fault condition, the BMS successfully
    recovers to normal operation, clears DTCs, and allows contactor re-closure.
    """
    bus, sim = bms_session

    # Step 1: Trip the system with overtemperature
    sim.inject_overtemperature(65)
    time.sleep(0.15)

    diag_msg = bus.recv(timeout=0.5, filter_id=CAN_ID_DIAGNOSTICS)
    assert diag_msg is not None
    assert BMSProtocolCodec.decode_diagnostics(diag_msg.data)["contactor_state"] == ContactorState.FAULT_TRIPPED

    # Step 2: Clear faults & verify recovery
    sim.clear_faults()
    bus.clear()
    time.sleep(0.15)

    diag_msg_after = bus.recv(timeout=0.5, filter_id=CAN_ID_DIAGNOSTICS)
    assert diag_msg_after is not None
    decoded_after = BMSProtocolCodec.decode_diagnostics(diag_msg_after.data)

    assert decoded_after["contactor_state"] == ContactorState.CLOSED, "Contactor did not re-close after fault clear"
    assert len(decoded_after["active_dtcs"]) == 0, f"DTCs still pending: {decoded_after['active_dtcs']}"
    assert decoded_after["fault_count"] == 0
