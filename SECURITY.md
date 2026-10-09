# Security policy

## Supported versions

Security fixes are provided for the latest SSHScript 3.1.x release. Fixes may
require upgrading rather than being backported to an earlier patch. Older
major/minor lines and development snapshots are unsupported.

| Version | Supported |
| --- | --- |
| Latest 3.1.x | Yes |
| Earlier releases | No |

The package requires Python 3.11 or newer. Public CI currently verifies Python
3.11 through 3.14 on Linux and macOS, with loopback OpenSSH integration on
Ubuntu. A report involving another interpreter, operating system, or SSH
server is welcome, but that environment is outside the supported security
matrix and a fix may require help from its maintainer.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's
[private vulnerability reporting](https://github.com/iapyeh/sshscript/security/advisories/new)
to provide:

- the affected SSHScript and Python versions;
- the operating system and SSH server implementation;
- reproduction steps or a minimal proof of concept;
- the impact and any known mitigations.

Remove passwords, private keys, access tokens, internal hostnames, and unrelated
production data. If a reproducer needs a secret or a private host, replace it
with a disposable equivalent before submitting it.

The project targets an initial acknowledgement within seven days, but is
maintained on a best-effort basis and cannot promise a resolution date. We will
coordinate validation, remediation, release, and disclosure with the reporter.
Please keep vulnerability details private until a patched release or an agreed
disclosure date exists.

## Security boundaries

### Automation is executable code

SSHScript is not a sandbox. A `.spy` file is transformed into and executed as
Python, and a Python caller can invoke local or remote commands. Running an
untrusted script therefore grants it the privileges, credentials, files, and
network access of the invoking process. This expected ability to execute
caller-supplied code is not, by itself, a vulnerability.

### Commands and external data

For new code with external arguments, pass a list/tuple directly to
`Session.exec_command(argv, check=True)`. Argument sequences bypass automatic
shell selection. Existing string callers may retain `shlex.join(argv)` with
`shell=False`; it remains supported. Use a string with explicit `shell=True`
or `shell="bash"` only when shell features are needed, and quote dynamic values.
See [the canonical API guide](API_GUIDE.md#recommended-choices).

Argument boundaries do not validate an executable or authorize an operation.
Treat remote output as untrusted input before passing it to another parser,
shell, database, or template. Command exit status does not establish deployment
success, and closing an SSH channel does not establish remote process
termination. Verify application outcomes and reconcile unknown termination.

### SSH identity and host keys

SSH connections load system host keys and reject unknown or changed keys by
default. The application is responsible for provisioning `known_hosts` and
verifying a new fingerprint through an independent channel. Supplying an
automatic-acceptance Paramiko policy is an explicit opt-out from this default
and is not recommended for production enrollment.

SSH authentication ultimately follows Paramiko and server policy. Prefer an
SSH agent, managed key, or secret manager. Never store passwords or private
keys in `.spy` files, examples, issue reports, or committed configuration.

### Environment, logs, and remote systems

Interactive SSH sessions forward locale/terminal defaults and values explicitly
requested by the caller, not the complete local process environment. This does
not make arbitrary environment values, command output, application logs, or
Paramiko debug logs safe to publish. Treat them as potentially sensitive.

Server-side authorization, PAM, `sudoers`, account policy, shell startup files,
firewalls, and command behavior remain outside SSHScript's control. Validate
those controls in a disposable environment before a production rollout.

## Security-sensitive defaults

The supported security posture assumes that callers retain host-key
verification, keep credentials outside source control, avoid shell
interpolation of untrusted input, set finite connection and operation timeouts,
and inspect exit status instead of assuming command success. Disabling these
controls, or running unreviewed automation with privileged credentials, is
outside the supported security model.

## Release integrity

Production releases are built and tested in GitHub Actions, published to PyPI
through Trusted Publishing with a short-lived OIDC identity, and accompanied by
GitHub build-provenance attestations. The GitHub Release includes the wheel,
source distribution, and a `verified.json` file containing their SHA-256
digests.

Verify a downloaded release against the manifest and, when the GitHub CLI is
available, its provenance:

```sh
gh attestation verify sshscript-3.1.4-py3-none-any.whl \
  --repo iapyeh/sshscript
```

Use the [official PyPI project](https://pypi.org/project/sshscript/) and
[GitHub Releases](https://github.com/iapyeh/sshscript/releases) rather than an
unverified mirror. Provenance and automated checks reduce supply-chain risk;
they do not establish that a script, command, or deployment is safe for a
particular environment.
