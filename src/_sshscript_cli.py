"""Minimal console bootstrap; must remain parseable on older Python."""
import sys


def main():
    # Importing a package submodule executes __init__ first, so this check
    # must be independent of the package's runtime guard.
    if sys.version_info < (3, 11):
        raise SystemExit(
            "SSHScript requires Python 3.11 or newer.\n"
            "Detected Python %s at %s."
            % ('.'.join(map(str, sys.version_info[:3])), sys.executable)
        )
    from sshscript.sshscript import main as run
    return run()


if __name__ == '__main__':
    main()
