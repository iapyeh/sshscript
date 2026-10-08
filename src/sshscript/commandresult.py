"""Immutable snapshots of completed commands."""
from dataclasses import dataclass
from typing import Generic, TypeVar

_Status = TypeVar("_Status", bound=int | None)


@dataclass(frozen=True)
class CommandResult(Generic[_Status]):
    """One completed command, with text output and elapsed monotonic seconds.

    Three-value unpacking/indexing yields ``stdout, stderr, exitcode``.
    Output is a text snapshot, not a live/consuming console buffer.
    host snapshots Session.host (None for a local session).
    """

    stdout: str
    stderr: str
    exitcode: _Status
    host: str | None
    duration: float
    command: str | tuple[str, ...]

    def __iter__(self):
        return iter((self.stdout, self.stderr, self.exitcode))

    def __len__(self):
        return 3

    def __getitem__(self, index):
        return (self.stdout, self.stderr, self.exitcode)[index]
