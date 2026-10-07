"""
CAN Bus Transport Abstraction Layer.
Provides a thread-safe in-memory virtual CAN bus for automated HIL testing
without requiring physical CAN transceivers or Vector hardware.
"""

from dataclasses import dataclass, field
import queue
import time
from typing import Optional, List


@dataclass
class CANMessage:
    arbitration_id: int
    data: bytes
    timestamp: float = field(default_factory=time.time)
    is_extended_id: bool = False

    def __repr__(self) -> str:
        hex_data = " ".join(f"{b:02X}" for b in self.data)
        return f"CANMessage(ID=0x{self.arbitration_id:03X}, DLC={len(self.data)}, DATA=[{hex_data}])"


class VirtualCANBus:
    """Thread-safe virtual CAN bus channel for communication between test harness and simulator."""

    def __init__(self, channel_name: str = "vcan0"):
        self.channel_name = channel_name
        self._msg_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._is_active: bool = True

    def send(self, message: CANMessage) -> None:
        """Transmits a message onto the virtual CAN bus."""
        if not self._is_active:
            raise ConnectionError("Virtual CAN bus is offline.")
        try:
            self._msg_queue.put(message, timeout=0.05)
        except queue.Full:
            pass  # Simulates buffer drop under severe bus saturation

    def recv(self, timeout: float = 0.5, filter_id: Optional[int] = None) -> Optional[CANMessage]:
        """
        Receives a message from the virtual CAN bus with timeout.
        Optional filter_id filters for specific CAN ID.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.01, deadline - time.time())
            try:
                msg: CANMessage = self._msg_queue.get(timeout=remaining)
                if filter_id is None or msg.arbitration_id == filter_id:
                    return msg
                # Put back messages not matching filter if needed or ignore
            except queue.Empty:
                return None
        return None

    def drain(self) -> List[CANMessage]:
        """Extracts all pending messages from the queue immediately."""
        messages = []
        while not self._msg_queue.empty():
            try:
                messages.append(self._msg_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def clear(self) -> None:
        """Flushes the message queue."""
        self.drain()

    def shutdown(self) -> None:
        """Closes the virtual bus channel."""
        self._is_active = False
        self.clear()
