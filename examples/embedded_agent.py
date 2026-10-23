"""Credential-free local host/agent integration: PYTHONPATH=. python examples/embedded_agent.py."""
import time
from sshscript import Console, Session


def drive(session):
    # In a real host, resolve credentials from its own config/secret store and
    # enforce its policy here. No automatic user candidate selection is provided.
    def resolve(request):
        raise PermissionError('this example does not authorize account switching')

    with Console(session, credential_resolver=resolve) as console:
        assert console.submit('saved = 42').state == 'completed'
        console.submit('$export EMBEDDED_EXAMPLE=retained; cd /tmp')
        update = console.start_command('printf "%s\\n" "$EMBEDDED_EXAMPLE"; pwd', timeout=3)
        while True:
            print(update.stdout, end='')
            if update.state != 'running':
                break
            time.sleep(.03)
            update = console.poll()
        if update.state != 'completed':
            raise RuntimeError('example command failed: ' + str(update.error_type))
        assert update.result.exitcode == 0
        assert console.submit('assert saved == 42').state == 'completed'
        print(console.environments)
    assert console.session_reuse == 'confirmed'
    print(session.exec_command('printf "original Session reused\\n"', check=True).stdout, end='')


if __name__ == '__main__':
    session = Session()
    try:
        drive(session)
    finally:
        session.close(strict=True)
