"""
BMS CAN Communication Protocol Codec and Diagnostic Trouble Code (DTC) Definitions.
Standardizes CAN frame packing, unpacking, scaling, and bitfield extraction.
"""

from enum import IntEnum
import struct
from typing import Dict, Any, List


class BMSState(IntEnum):
    INIT = 0
    STANDBY = 1
    CHARGING = 2
    DISCHARGING = 3
    FAULT = 4


class ContactorState(IntEnum):
    OPEN = 0
    CLOSED = 1
    PRECHARGE = 2
    FAULT_TRIPPED = 3


class DTC(IntEnum):
    NONE = 0x0000
    CELL_OVER_VOLTAGE = 0xE001
    CELL_UNDER_VOLTAGE = 0xE002
    PACK_OVER_TEMPERATURE = 0xE003
    PACK_OVER_CURRENT = 0xE004
    CELL_IMBALANCE_WARNING = 0xE005
    COMMUNICATION_LOSS = 0xE006


class UDSNegativeResponseCode(IntEnum):
    SERVICE_NOT_SUPPORTED = 0x11
    SUBFUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_MESSAGE_LENGTH = 0x13
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
    GENERAL_PROGRAMMING_FAILURE = 0x72


# Standardized CAN Arbitration IDs for the EV BMS
CAN_ID_HEARTBEAT = 0x180
CAN_ID_PACK_METRICS = 0x181
CAN_ID_CELL_VOLTAGES = 0x182
CAN_ID_TEMPERATURES = 0x183
CAN_ID_DIAGNOSTICS = 0x184


class BMSProtocolCodec:
    """Encodes and decodes automotive BMS CAN messages with high-speed binary packing."""

    @staticmethod
    def encode_heartbeat(state: BMSState, alive_counter: int) -> bytes:
        """CAN 0x180: State (uint8), Alive Counter (uint8), Reserved (6B)."""
        return struct.pack(">BB6x", int(state), alive_counter & 0xFF)

    @staticmethod
    def decode_heartbeat(data: bytes) -> Dict[str, Any]:
        state_raw, alive_counter = struct.unpack(">BB6x", data)
        return {
            "state": BMSState(state_raw),
            "alive_counter": alive_counter
        }

    @staticmethod
    def encode_pack_metrics(voltage_v: float, current_a: float, soc_pct: float, soh_pct: float) -> bytes:
        """
        CAN 0x181:
          - Pack Voltage: uint16, scale 0.1 V
          - Pack Current: int16, scale 0.1 A (Negative = discharge, Positive = charge)
          - SoC: uint8, scale 0.5% (0..200 = 0..100%)
          - SoH: uint8, scale 0.5% (0..200 = 0..100%)
        """
        raw_v = int(round(voltage_v * 10.0)) & 0xFFFF
        raw_i = int(round(current_a * 10.0))
        raw_soc = int(round(soc_pct * 2.0)) & 0xFF
        raw_soh = int(round(soh_pct * 2.0)) & 0xFF
        return struct.pack(">HhBB2x", raw_v, raw_i, raw_soc, raw_soh)

    @staticmethod
    def decode_pack_metrics(data: bytes) -> Dict[str, Any]:
        raw_v, raw_i, raw_soc, raw_soh = struct.unpack(">HhBB2x", data)
        return {
            "pack_voltage_v": round(raw_v / 10.0, 2),
            "pack_current_a": round(raw_i / 10.0, 2),
            "soc_pct": round(raw_soc / 2.0, 1),
            "soh_pct": round(raw_soh / 2.0, 1)
        }

    @staticmethod
    def encode_cell_voltages(min_mv: int, max_mv: int, min_idx: int, max_idx: int) -> bytes:
        """CAN 0x182: Min Cell (mV, uint16), Max Cell (mV, uint16), Min Idx (uint8), Max Idx (uint8)."""
        delta_mv = max_mv - min_mv
        return struct.pack(">HHBBH", min_mv, max_mv, min_idx, max_idx, delta_mv)

    @staticmethod
    def decode_cell_voltages(data: bytes) -> Dict[str, Any]:
        min_mv, max_mv, min_idx, max_idx, delta_mv = struct.unpack(">HHBBH", data)
        return {
            "min_cell_mv": min_mv,
            "max_cell_mv": max_mv,
            "min_cell_idx": min_idx,
            "max_cell_idx": max_idx,
            "delta_mv": delta_mv
        }

    @staticmethod
    def encode_temperatures(min_temp_c: int, max_temp_c: int, avg_temp_c: int) -> bytes:
        """CAN 0x183: Min Temp (int8), Max Temp (int8), Avg Temp (int8), 5 bytes reserved."""
        return struct.pack(">bbb5x", min_temp_c, max_temp_c, avg_temp_c)

    @staticmethod
    def decode_temperatures(data: bytes) -> Dict[str, Any]:
        min_t, max_t, avg_t = struct.unpack(">bbb5x", data)
        return {
            "min_temp_c": min_t,
            "max_temp_c": max_t,
            "avg_temp_c": avg_t
        }

    @staticmethod
    def encode_diagnostics(dtc_list: List[DTC], contactor_state: ContactorState) -> bytes:
        """
        CAN 0x184:
          - Active DTC 1 (uint16)
          - Active DTC 2 (uint16)
          - Contactor State (uint8)
          - Fault Count (uint8)
        """
        dtc1 = dtc_list[0] if len(dtc_list) > 0 else DTC.NONE
        dtc2 = dtc_list[1] if len(dtc_list) > 1 else DTC.NONE
        fault_count = len(dtc_list)
        return struct.pack(">HHBB2x", int(dtc1), int(dtc2), int(contactor_state), fault_count)

    @staticmethod
    def decode_diagnostics(data: bytes) -> Dict[str, Any]:
        dtc1_raw, dtc2_raw, contactor_raw, fault_count = struct.unpack(">HHBB2x", data)
        dtcs = []
        if dtc1_raw != 0:
            dtcs.append(DTC(dtc1_raw) if dtc1_raw in DTC._value2member_map_ else dtc1_raw)
        if dtc2_raw != 0:
            dtcs.append(DTC(dtc2_raw) if dtc2_raw in DTC._value2member_map_ else dtc2_raw)
        return {
            "active_dtcs": dtcs,
            "contactor_state": ContactorState(contactor_raw),
            "fault_count": fault_count
        }
