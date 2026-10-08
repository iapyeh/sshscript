from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar, overload

_Status = TypeVar('_Status', bound=int | None)
@dataclass(frozen=True)
class CommandResult(Generic[_Status]):
    stdout: str
    stderr: str
    exitcode: _Status
    host: str | None
    duration: float
    command: str | tuple[str, ...]
    def __iter__(self) -> Iterator[str | _Status]: ...
    def __len__(self) -> int: ...
    @overload
    def __getitem__(self, index: int) -> str | _Status: ...
    @overload
    def __getitem__(self, index: slice) -> tuple[str | _Status, ...]: ...
