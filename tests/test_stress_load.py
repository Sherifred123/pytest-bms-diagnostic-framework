"""
Test Suite: Bus Stress Load, Buffer Stability, and Frame Timeout Handling.
Verifies communications resilience and test harness stability under high message rates.
"""

import time
import pytest
from core.transport_can import CANMessage


@pytest.mark.stress
def test_bus_burst_load_stability(bms_session):
    """Verify that rapid concurrent message transmission does not destabilize the bus or deadlock."""
    bus, _ = bms_session

    burst_count = 100
    for i in range(burst_count):
        msg = CANMessage(arbitration_id=0x700 + (i % 8), data=b"\x01\x02\x03\x04\x05\x06\x07\x08")
        bus.send(msg)

    time.sleep(0.1)
    drained = bus.drain()
    assert len(drained) >= burst_count, f"Dropped messages under burst: expected >= {burst_count}, got {len(drained)}"


@pytest.mark.stress
def test_missing_frame_detection_timeout(bms_session):
    """Verify that bus.recv properly enforces timeout when querying a non-existent arbitration ID."""
    bus, _ = bms_session

    start = time.time()
    msg = bus.recv(timeout=0.15, filter_id=0x7FF)  # 0x7FF is never broadcast
    duration = time.time() - start

    assert msg is None, "Unexpectedly received message for unassigned CAN ID 0x7FF"
    assert duration >= 0.14, f"Timeout returned prematurely in {duration:.3f}s"
