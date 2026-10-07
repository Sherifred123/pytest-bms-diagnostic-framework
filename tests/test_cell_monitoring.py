"""
Test Suite: Cell Voltage Monitoring, Pack Aggregates, and Thermal Metrics.
Verifies measurement scaling, aggregate mathematical consistency, and telemetry accuracy.
"""

import pytest
from core.bms_protocol import (
    CAN_ID_PACK_METRICS,
    CAN_ID_CELL_VOLTAGES,
    CAN_ID_TEMPERATURES,
    BMSProtocolCodec,
)


@pytest.mark.cell
def test_pack_voltage_aggregate_accuracy(bms_session):
    """Verify that reported pack voltage matches the mathematical sum of individual cells."""
    bus, sim = bms_session

    msg = bus.recv(timeout=0.5, filter_id=CAN_ID_PACK_METRICS)
    assert msg is not None, "Did not receive pack metrics frame 0x181"

    decoded = BMSProtocolCodec.decode_pack_metrics(msg.data)
    expected_pack_v = sum(sim.cell_voltages_mv) / 1000.0

    assert abs(decoded["pack_voltage_v"] - expected_pack_v) <= 0.2, (
        f"Pack voltage mismatch: reported {decoded['pack_voltage_v']}V, "
        f"expected {expected_pack_v}V"
    )


@pytest.mark.cell
def test_cell_extremes_identification(bms_session):
    """Verify that CAN frame 0x182 accurately identifies min and max cells and their indexes."""
    bus, sim = bms_session

    # Inject a known low cell and high cell
    sim.cell_voltages_mv[2] = 3620  # Min cell
    sim.cell_voltages_mv[9] = 3780  # Max cell

    msg = bus.recv(timeout=0.5, filter_id=CAN_ID_CELL_VOLTAGES)
    assert msg is not None, "Did not receive cell voltages frame 0x182"

    decoded = BMSProtocolCodec.decode_cell_voltages(msg.data)
    assert decoded["min_cell_mv"] == 3620, f"Expected min cell 3620mV, got {decoded['min_cell_mv']}mV"
    assert decoded["max_cell_mv"] == 3780, f"Expected max cell 3780mV, got {decoded['max_cell_mv']}mV"
    assert decoded["min_cell_idx"] == 2
    assert decoded["max_cell_idx"] == 9
    assert decoded["delta_mv"] == (3780 - 3620)


@pytest.mark.cell
def test_temperature_sensor_averaging(bms_session):
    """Verify temperature reporting in frame 0x183 conforms to sensor inputs."""
    bus, sim = bms_session

    sim.module_temps_c = [28, 35, 42, 31]

    msg = bus.recv(timeout=0.5, filter_id=CAN_ID_TEMPERATURES)
    assert msg is not None, "Did not receive temperatures frame 0x183"

    decoded = BMSProtocolCodec.decode_temperatures(msg.data)
    assert decoded["min_temp_c"] == 28
    assert decoded["max_temp_c"] == 42
    assert decoded["avg_temp_c"] == sum([28, 35, 42, 31]) // 4


@pytest.mark.cell
def test_soc_soh_bounds_and_scaling(bms_session):
    """Verify State-of-Charge and State-of-Health remain within valid percentage bounds."""
    bus, _ = bms_session

    msg = bus.recv(timeout=0.5, filter_id=CAN_ID_PACK_METRICS)
    assert msg is not None

    decoded = BMSProtocolCodec.decode_pack_metrics(msg.data)
    assert 0.0 <= decoded["soc_pct"] <= 100.0, f"Invalid SoC percentage: {decoded['soc_pct']}"
    assert 0.0 <= decoded["soh_pct"] <= 100.0, f"Invalid SoH percentage: {decoded['soh_pct']}"
