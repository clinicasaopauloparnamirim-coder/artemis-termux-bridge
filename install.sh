#!/usr/bin/env bash
set -Eeuo pipefail
OWNER="clinicasaopauloparnamirim-coder"
SOURCE_REPO="artemis-termux-bridge"
QUEUE_REPO="artemis-termux-bridge-queue"
ISSUE_NUMBER="1"
BASE_URL="https://raw.githubusercontent.com/$OWNER/$SOURCE_REPO/main"
if command -v apt-get >/dev/null 2>&1; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "[1/3] Installing GitHub CLI, Python and curl..."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y gh python3 curl ca-certificates
  else
    command -v python3 >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y python3
    command -v curl >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y curl
  fi
elif command -v pkg >/dev/null 2>&1; then
  command -v gh >/dev/null 2>&1 || pkg install -y gh
  command -v python >/dev/null 2>&1 || pkg install -y python
  command -v curl >/dev/null 2>&1 || pkg install -y curl
else
  echo "Unsupported shell environment: install gh, python3 and curl first."
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI was not installed. No further changes were made."
  exit 1
fi
echo "[2/3] Checking GitHub authorization..."
if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  echo
  echo "One-time GitHub device authorization is required."
  echo "When the terminal shows a code, open https://github.com/login/device in Chrome, enter it, and approve."
  gh auth login --hostname github.com --git-protocol https --web
fi
LOGIN="$(gh api user --jq .login)"
if [ "$LOGIN" != "$OWNER" ]; then
  echo "Wrong GitHub account: $LOGIN"
  echo "The private queue requires $OWNER."
  exit 1
fi
if ! gh api "repos/$OWNER/$QUEUE_REPO/issues/$ISSUE_NUMBER" >/dev/null 2>&1; then
  echo "Cannot access the private queue issue. Verify GitHub authorization and repository access."
  exit 1
fi
echo "[3/3] Installing and starting the bridge..."
DEST="$HOME/.local/bin"
mkdir -p "$DEST"
curl -fsSL "$BASE_URL/termux_bridge.py" -o "$DEST/artemis-termux-bridge.py"
chmod 700 "$DEST/artemis-termux-bridge.py"
export ARTEMIS_BRIDGE_OWNER="$OWNER"
export ARTEMIS_BRIDGE_QUEUE="$QUEUE_REPO"
export ARTEMIS_BRIDGE_ISSUE="$ISSUE_NUMBER"
exec python3 "$DEST/artemis-termux-bridge.py"
