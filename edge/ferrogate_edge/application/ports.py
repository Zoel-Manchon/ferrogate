from __future__ import annotations

from typing import Protocol, Sequence

from ferrogate.shared.security.envelope import Sample


class DeviceReader(Protocol):
    """Puerto de lectura de campo.

    Modbus y OPC-UA lo implementan; un contador real lo implementaria igual.
    Por eso el simulador se puede sustituir por hardware sin tocar nada mas.
    """

    async def read_all(self) -> Sequence[Sample]: ...

    async def close(self) -> None: ...


class Publisher(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...


class Buffer(Protocol):
    """Store-and-forward: el problema real del edge.

    Si el enlace cae, los datos NO se pierden; se guardan en disco y se
    reenvian en orden al recuperar.
    """

    def enqueue(self, topic: str, payload: bytes) -> None: ...

    def peek(self, limit: int) -> list[tuple[int, str, bytes]]: ...

    def ack(self, row_id: int) -> None: ...

    def depth(self) -> int: ...

    def last_sequence(self) -> int: ...

    def set_sequence(self, sequence: int) -> None: ...
