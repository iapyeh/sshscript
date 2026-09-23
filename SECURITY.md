# Security policy

## Supported versions

Security fixes are provided for the latest SSHScript 3.1.x release. Older
major/minor lines and development snapshots are unsupported.

| Version | Supported |
| --- | --- |
| Latest 3.1.x | Yes |
| Earlier releases | No |

SSHScript supports Python 3.11 through 3.14 on Linux and macOS. A security
report involving another platform is welcome, but fixes may require help from
a maintainer of that platform.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's
[private vulnerability reporting](https://github.com/iapyeh/sshscript/security/advisories/new)
to provide:

- the affected SSHScript and Python versions;
- the operating system and SSH server implementation;
- reproduction steps or a minimal proof of concept;
- the impact and any known mitigations.

Expect an initial acknowledgement within seven days. We will coordinate the
fix, release, and disclosure with the reporter. Please keep vulnerability
details private until a patched release or an agreed disclosure date exists.

## Security-sensitive defaults

SSHScript verifies SSH host keys by default. Disabling that verification,
logging credentials, or committing private keys and host inventories is
outside the supported security model. Use disposable hosts for integration
testing and keep secrets outside source control.
