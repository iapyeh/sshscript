#!/usr/bin/env bash
set -Eeuo pipefail

# Provision a disposable, loopback-only OpenSSH service for SSHScript's
# credential-free GitHub Actions integration tests.  The generated passwords
# and keys exist only for the lifetime of the runner.

ENV_FILE="${1:-${GITHUB_ENV:-}}"
if [[ -z "${ENV_FILE}" ]]; then
    echo "usage: $0 <github-environment-file>" >&2
    echo "GITHUB_ENV may be used instead of the positional argument." >&2
    exit 2
fi

if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true; then
    echo "setup_openssh_ci.sh requires passwordless sudo" >&2
    exit 1
fi

if ! command -v sshd >/dev/null 2>&1 && [[ ! -x /usr/sbin/sshd ]]; then
    sudo apt-get update
    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        openssh-server sudo
fi

SSHD_BIN="$(command -v sshd || true)"
if [[ -z "${SSHD_BIN}" && -x /usr/sbin/sshd ]]; then
    SSHD_BIN=/usr/sbin/sshd
fi
SSH_KEYGEN_BIN="$(command -v ssh-keygen || true)"
VISUDO_BIN="$(command -v visudo || true)"
if [[ -z "${VISUDO_BIN}" && -x /usr/sbin/visudo ]]; then
    VISUDO_BIN=/usr/sbin/visudo
fi
if [[ -z "${SSHD_BIN}" || -z "${SSH_KEYGEN_BIN}" || -z "${VISUDO_BIN}" ]]; then
    echo "OpenSSH server and ssh-keygen are required" >&2
    exit 1
fi

LOGIN_USER="sshscriptci"
TARGET_USER="sshscripttarget"
for account in "${LOGIN_USER}" "${TARGET_USER}"; do
    if id "${account}" >/dev/null 2>&1; then
        echo "refusing to reuse existing account: ${account}" >&2
        exit 1
    fi
done

RUNNER_TEMP_DIR="${RUNNER_TEMP:-/tmp}"
TEST_ROOT="$(mktemp -d "${RUNNER_TEMP_DIR%/}/sshscript-openssh.XXXXXX")"
CLIENT_HOME="${TEST_ROOT}/client-home"
CLIENT_SSH_DIR="${CLIENT_HOME}/.ssh"
KNOWN_HOSTS="${CLIENT_SSH_DIR}/known_hosts"
TRUSTED_HOSTS="${TEST_ROOT}/known_hosts.trusted"
MISMATCH_HOSTS="${TEST_ROOT}/known_hosts.mismatch"
LOGIN_KEY="${TEST_ROOT}/id_ed25519"
HOST_KEY="${TEST_ROOT}/ssh_host_ed25519_key"
MISMATCH_KEY="${TEST_ROOT}/mismatch_host_ed25519_key"
SSHD_CONFIG="${TEST_ROOT}/sshd_config"
SSHD_LOG="${TEST_ROOT}/sshd.log"
SSHD_PID_FILE="${TEST_ROOT}/sshd.pid"
SUDOERS_FILE="/etc/sudoers.d/sshscript-ci"
HOST="127.0.0.1"
PORT="${SSHSCRIPT_OPENSSH_PORT:-22222}"

mkdir -p "${CLIENT_SSH_DIR}"
chmod 700 "${CLIENT_HOME}" "${CLIENT_SSH_DIR}"

LOGIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
TARGET_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "::add-mask::${LOGIN_PASSWORD}"
    echo "::add-mask::${TARGET_PASSWORD}"
fi

sudo useradd --create-home --user-group --shell /bin/bash "${LOGIN_USER}"
sudo useradd --create-home --user-group --shell /bin/bash "${TARGET_USER}"
printf '%s:%s\n%s:%s\n' \
    "${LOGIN_USER}" "${LOGIN_PASSWORD}" \
    "${TARGET_USER}" "${TARGET_PASSWORD}" | sudo chpasswd

"${SSH_KEYGEN_BIN}" -q -t ed25519 -N '' -f "${LOGIN_KEY}"
"${SSH_KEYGEN_BIN}" -q -t ed25519 -N '' -f "${HOST_KEY}"
"${SSH_KEYGEN_BIN}" -q -t ed25519 -N '' -f "${MISMATCH_KEY}"
chmod 600 "${LOGIN_KEY}" "${HOST_KEY}" "${MISMATCH_KEY}"

LOGIN_GROUP="$(id -gn "${LOGIN_USER}")"
sudo install -d -m 700 -o "${LOGIN_USER}" -g "${LOGIN_GROUP}" \
    "/home/${LOGIN_USER}/.ssh"
sudo install -m 600 -o "${LOGIN_USER}" -g "${LOGIN_GROUP}" \
    "${LOGIN_KEY}.pub" "/home/${LOGIN_USER}/.ssh/authorized_keys"

{
    printf 'Defaults:%s timestamp_timeout=0\n' "${LOGIN_USER}"
    printf '%s ALL=(ALL:ALL) ALL\n' "${LOGIN_USER}"
} | sudo tee "${SUDOERS_FILE}" >/dev/null
sudo chmod 440 "${SUDOERS_FILE}"
sudo "${VISUDO_BIN}" -cf "${SUDOERS_FILE}" >/dev/null

host_key_type="$(awk '{print $1}' "${HOST_KEY}.pub")"
host_key_data="$(awk '{print $2}' "${HOST_KEY}.pub")"
mismatch_key_type="$(awk '{print $1}' "${MISMATCH_KEY}.pub")"
mismatch_key_data="$(awk '{print $2}' "${MISMATCH_KEY}.pub")"
printf '[%s]:%s %s %s\n' \
    "${HOST}" "${PORT}" "${host_key_type}" "${host_key_data}" \
    >"${TRUSTED_HOSTS}"
printf '[%s]:%s %s %s\n' \
    "${HOST}" "${PORT}" "${mismatch_key_type}" "${mismatch_key_data}" \
    >"${MISMATCH_HOSTS}"
cp "${TRUSTED_HOSTS}" "${KNOWN_HOSTS}"
chmod 600 "${KNOWN_HOSTS}" "${TRUSTED_HOSTS}" "${MISMATCH_HOSTS}"

cat >"${SSHD_CONFIG}" <<EOF
AddressFamily inet
ListenAddress ${HOST}
Port ${PORT}
HostKey ${HOST_KEY}
PidFile ${SSHD_PID_FILE}
AuthorizedKeysFile .ssh/authorized_keys
AuthenticationMethods publickey
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
PermitRootLogin no
PermitEmptyPasswords no
AllowUsers ${LOGIN_USER}
StrictModes yes
UseDNS no
PrintMotd no
X11Forwarding no
AllowTcpForwarding no
PermitTunnel no
PermitUserEnvironment no
Subsystem sftp internal-sftp
LogLevel VERBOSE
EOF

sudo mkdir -p /run/sshd
sudo chown root:root "${HOST_KEY}"
sudo chmod 600 "${HOST_KEY}"
sudo install -m 644 /dev/null "${SSHD_LOG}"
sudo "${SSHD_BIN}" -t -f "${SSHD_CONFIG}"
sudo "${SSHD_BIN}" -f "${SSHD_CONFIG}" -E "${SSHD_LOG}"

python3 - "${HOST}" "${PORT}" <<'PY'
import socket
import sys
import time

host, port = sys.argv[1], int(sys.argv[2])
deadline = time.monotonic() + 10
while True:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            break
    except OSError:
        if time.monotonic() >= deadline:
            raise SystemExit(f"sshd did not become ready on {host}:{port}")
        time.sleep(0.1)
PY

if [[ ! -s "${SSHD_PID_FILE}" ]]; then
    echo "sshd did not create its PID file" >&2
    exit 1
fi

touch "${ENV_FILE}"
append_env() {
    printf '%s=%s\n' "$1" "$2" >>"${ENV_FILE}"
}

append_env SSHSCRIPT_OPENSSH_TESTS 1
append_env SSHSCRIPT_OPENSSH_HOST "${HOST}"
append_env SSHSCRIPT_OPENSSH_PORT "${PORT}"
append_env SSHSCRIPT_OPENSSH_USER "${LOGIN_USER}"
append_env SSHSCRIPT_OPENSSH_PASSWORD "${LOGIN_PASSWORD}"
append_env SSHSCRIPT_OPENSSH_TARGET_USER "${TARGET_USER}"
append_env SSHSCRIPT_OPENSSH_TARGET_PASSWORD "${TARGET_PASSWORD}"
append_env SSHSCRIPT_OPENSSH_KEY "${LOGIN_KEY}"
append_env SSHSCRIPT_OPENSSH_HOME "${CLIENT_HOME}"
append_env SSHSCRIPT_OPENSSH_KNOWN_HOSTS "${KNOWN_HOSTS}"
append_env SSHSCRIPT_OPENSSH_TRUSTED_HOSTS "${TRUSTED_HOSTS}"
append_env SSHSCRIPT_OPENSSH_MISMATCH_HOSTS "${MISMATCH_HOSTS}"
append_env SSHSCRIPT_OPENSSH_ROOT "${TEST_ROOT}"
append_env SSHSCRIPT_OPENSSH_LOG "${SSHD_LOG}"
append_env SSHSCRIPT_OPENSSH_PID_FILE "${SSHD_PID_FILE}"
append_env SSHSCRIPT_OPENSSH_CONFIG "${SSHD_CONFIG}"
append_env SSHSCRIPT_OPENSSH_SUDOERS "${SUDOERS_FILE}"

echo "OpenSSH integration service is ready at ${HOST}:${PORT}"
echo "Environment exported to ${ENV_FILE}"
