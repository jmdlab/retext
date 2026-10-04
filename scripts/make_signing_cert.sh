#!/usr/bin/env bash
# One-time setup: create a self-signed code-signing certificate in the login
# keychain. build_mac.sh signs with it when present, so the app keeps the
# same identity across rebuilds and macOS keeps its Accessibility grant.
set -euo pipefail

NAME="Retext Local Signing"
if security find-certificate -c "$NAME" >/dev/null 2>&1; then
  echo "\"$NAME\" already exists — nothing to do."
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/cert.cnf" <<CNF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $NAME
[ext]
basicConstraints = critical, CA:false
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
CNF

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -config "$TMP/cert.cnf" -keyout "$TMP/key.pem" -out "$TMP/cert.pem" 2>/dev/null
PASS=$(openssl rand -hex 16)
openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
  -name "$NAME" -out "$TMP/cert.p12" -passout "pass:$PASS"

security import "$TMP/cert.p12" -k "$HOME/Library/Keychains/login.keychain-db" \
  -P "$PASS" -T /usr/bin/codesign

echo "Created \"$NAME\". Rebuild with ./scripts/build_mac.sh."
