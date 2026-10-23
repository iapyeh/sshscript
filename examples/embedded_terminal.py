"""Run locally: PYTHONPATH=. python examples/embedded_terminal.py

OpsFeast can call handover(target_session) after its own authorized connection.
This example makes no SSH connection and never runs su/sudo automatically.
"""
from sshscript import Console, Session


def handover(session):
    with Console(session, terminal=True) as console:
        console.interact()
    assert console.session_reuse == 'confirmed'
    return session.exec_command('printf "Session remains usable\\n"', check=True)


if __name__ == '__main__':
    session = Session()
    try:
        print(handover(session).stdout, end='')
    finally:
        session.close(strict=True)
