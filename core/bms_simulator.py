"""
Virtual EV Battery Management System (BMS) Hardware-in-the-Loop (HIL) Simulator.
Emulates physical 16S battery pack behavior, periodic CAN transmission,
threshold monitoring, and contactor safety shutdown logic.
"""

import threading
import time
from typing import List
from .transport_can import VirtualCANBus, CANMessage
from .bms_protocol import (
    BMSState,
    ContactorState,
    DTC,
    BMSProtocolCodec,
    CAN_ID_HEARTBEAT,
    CAN_ID_PACK_METRICS,
    CAN_ID_CELL_VOLTAGES,
    CAN_ID_TEMPERATURES,
    CAN_ID_DIAGNOSTICS,
)


class BMSSimulator:
    """Simulates an automotive BMS ECU running at 10 Hz over a virtual CAN bus."""

    def __init__(self, bus: VirtualCANBus, cell_count: int = 16):
        self.bus = bus
        self.cell_count = cell_count
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread = None

        # Nominal Battery Pack Operating State
        self.state: BMSState = BMSState.DISCHARGING
        self.contactor_state: ContactorState = ContactorState.CLOSED
        self.alive_counter: int = 0
        self.active_dtcs: List[DTC] = []

        # 16S Cell Voltages (in millivolts, 3700 mV = 3.70 V nominal)
        self.cell_voltages_mv: List[int] = [3700] * self.cell_count
        self.module_temps_c: List[int] = [32, 33, 31, 32]  # 4 temperature sensors
        self.pack_current_a: float = -25.0  # -25A discharge
        self.soc_pct: float = 85.0
        self.soh_pct: float = 98.0

        # Safety Thresholds
        self.ov_fault_mv = 4250
        self.uv_fault_mv = 2800
        self.ot_fault_c = 60
        self.oc_fault_a = 300.0
        self.imbalance_warn_mv = 80

    def start(self) -> None:
        """Starts the background ECU transmission thread."""
        self._running = True
        self._thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops the ECU simulation cleanly."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    # -------------------------------------------------------------------------
    # Fault Injection Hooks for Automated Testing
    # -------------------------------------------------------------------------

    def inject_cell_overvoltage(self, cell_idx: int = 0, voltage_mv: int = 4280) -> None:
        with self._lock:
            self.cell_voltages_mv[cell_idx] = voltage_mv

    def inject_cell_undervoltage(self, cell_idx: int = 0, voltage_mv: int = 2750) -> None:
        with self._lock:
            self.cell_voltages_mv[cell_idx] = voltage_mv

    def inject_overtemperature(self, temp_c: int = 65) -> None:
        with self._lock:
            self.module_temps_c[1] = temp_c

    def inject_overcurrent(self, current_a: float = 320.0) -> None:
        with self._lock:
            self.pack_current_a = current_a

    def inject_cell_imbalance(self, high_idx: int = 0, low_idx: int = 1, delta_mv: int = 120) -> None:
        with self._lock:
            self.cell_voltages_mv[high_idx] = 3760
            self.cell_voltages_mv[low_idx] = 3760 - delta_mv

    def clear_faults(self) -> None:
        """Restores the BMS to nominal healthy state."""
        with self._lock:
            self.cell_voltages_mv = [3700] * self.cell_count
            self.module_temps_c = [32, 33, 31, 32]
            self.pack_current_a = -25.0
            self.active_dtcs.clear()
            self.state = BMSState.DISCHARGING
            self.contactor_state = ContactorState.CLOSED

    # -------------------------------------------------------------------------
    # Background ECU Safety Engine & CAN Broadcast Loop
    # -------------------------------------------------------------------------

    def _evaluate_safety_thresholds(self) -> None:
        """Internal BMS safety watchdog: latches DTCs and trips contactors if thresholds violated."""
        min_v = min(self.cell_voltages_mv)
        max_v = max(self.cell_voltages_mv)
        max_t = max(self.module_temps_c)
        curr = abs(self.pack_current_a)

        fault_detected = False

        # Over-voltage protection
        if max_v >= self.ov_fault_mv and DTC.CELL_OVER_VOLTAGE not in self.active_dtcs:
            self.active_dtcs.append(DTC.CELL_OVER_VOLTAGE)
            fault_detected = True

        # Under-voltage protection
        if min_v <= self.uv_fault_mv and DTC.CELL_UNDER_VOLTAGE not in self.active_dtcs:
            self.active_dtcs.append(DTC.CELL_UNDER_VOLTAGE)
            fault_detected = True

        # Over-temperature protection
        if max_t >= self.ot_fault_c and DTC.PACK_OVER_TEMPERATURE not in self.active_dtcs:
            self.active_dtcs.append(DTC.PACK_OVER_TEMPERATURE)
            fault_detected = True

        # Over-current protection
        if curr >= self.oc_fault_a and DTC.PACK_OVER_CURRENT not in self.active_dtcs:
            self.active_dtcs.append(DTC.PACK_OVER_CURRENT)
            fault_detected = True

        # Cell imbalance warning (Warning only, does not trip contactor)
        if (max_v - min_v) >= self.imbalance_warn_mv and DTC.CELL_IMBALANCE_WARNING not in self.active_dtcs:
            self.active_dtcs.append(DTC.CELL_IMBALANCE_WARNING)

        # Autonomous Safety Interlock: Open contactor on any critical fault
        if fault_detected:
            self.state = BMSState.FAULT
            self.contactor_state = ContactorState.FAULT_TRIPPED

    def _broadcast_loop(self) -> None:
        """Periodic 100ms (10 Hz) transmission loop."""
        while self._running:
            with self._lock:
                self._evaluate_safety_thresholds()

                # Calculate aggregates
                pack_v = sum(self.cell_voltages_mv) / 1000.0
                min_v = min(self.cell_voltages_mv)
                max_v = max(self.cell_voltages_mv)
                min_idx = self.cell_voltages_mv.index(min_v)
                max_idx = self.cell_voltages_mv.index(max_v)
                min_t = min(self.module_temps_c)
                max_t = max(self.module_temps_c)
                avg_t = sum(self.module_temps_c) // len(self.module_temps_c)

                # Pack CAN Messages
                msg_hb = CANMessage(
                    CAN_ID_HEARTBEAT,
                    BMSProtocolCodec.encode_heartbeat(self.state, self.alive_counter)
                )
                msg_metrics = CANMessage(
                    CAN_ID_PACK_METRICS,
                    BMSProtocolCodec.encode_pack_metrics(pack_v, self.pack_current_a, self.soc_pct, self.soh_pct)
                )
                msg_cells = CANMessage(
                    CAN_ID_CELL_VOLTAGES,
                    BMSProtocolCodec.encode_cell_voltages(min_v, max_v, min_idx, max_idx)
                )
                msg_temps = CANMessage(
                    CAN_ID_TEMPERATURES,
                    BMSProtocolCodec.encode_temperatures(min_t, max_t, avg_t)
                )
                msg_diag = CANMessage(
                    CAN_ID_DIAGNOSTICS,
                    BMSProtocolCodec.encode_diagnostics(self.active_dtcs, self.contactor_state)
                )

                self.alive_counter = (self.alive_counter + 1) & 0xFF

            # Send periodic burst over virtual CAN bus
            try:
                self.bus.send(msg_hb)
                self.bus.send(msg_metrics)
                self.bus.send(msg_cells)
                self.bus.send(msg_temps)
                self.bus.send(msg_diag)
            except Exception:
                pass

            time.sleep(0.1)  # 10 Hz broadcast
