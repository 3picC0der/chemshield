from __future__ import annotations


class SimulatedActuator:
    """Small Uno/PLC mailbox simulator.

    It only accepts commands forwarded by the gateway. Direct writes are blocked.
    This supports C2: the gateway is the sole authorized actuator path.
    """

    def __init__(self) -> None:
        self.accepted_commands: list[str] = []
        self.blocked_direct_writes: int = 0

    def forward_from_gateway(self, command_id: str) -> bool:
        self.accepted_commands.append(command_id)
        return True

    def direct_write_attempt(self, command_id: str) -> bool:
        self.blocked_direct_writes += 1
        return False
