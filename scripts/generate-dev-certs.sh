#!/usr/bin/env bash
# generate-dev-certs.sh — Generate a self-signed TLS certificate for local development.
#
# The certificate is written to nginx/ssl/cert.pem and nginx/ssl/key.pem.
# These files are listed in .gitignore and must NEVER be committed.
#
# Requirements: openssl (available on macOS and most Linux distributions)
#
# Usage:
#   bash scripts/generate-dev-certs.sh
#   # or via Makefile:
#   make certs

set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nginx/ssl"
CERT_FILE="${CERT_DIR}/cert.pem"
KEY_FILE="${CERT_DIR}/key.pem"

echo "► Generating self-signed TLS certificate for ForgeGuard local development..."
echo "  Output directory: ${CERT_DIR}"

# Create directory if it doesn't exist.
mkdir -p "${CERT_DIR}"

# Check if certificates already exist.
if [[ -f "${CERT_FILE}" && -f "${KEY_FILE}" ]]; then
    echo "  Certificates already exist. Delete them to regenerate:"
    echo "    rm ${CERT_FILE} ${KEY_FILE}"
    exit 0
fi

# Generate a 4096-bit RSA private key and a self-signed X.509 certificate
# valid for 365 days with Subject Alternative Names for localhost.
openssl req \
    -x509 \
    -newkey rsa:4096 \
    -keyout "${KEY_FILE}" \
    -out "${CERT_FILE}" \
    -days 365 \
    -nodes \
    -subj "/C=US/ST=Local/L=Local/O=ForgeGuard Dev/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:forgeguard-frontend,IP:127.0.0.1" \
    2>/dev/null

chmod 600 "${KEY_FILE}"
chmod 644 "${CERT_FILE}"

echo "✓ Certificate generated successfully:"
echo "  Cert: ${CERT_FILE}"
echo "  Key:  ${KEY_FILE}"
echo ""
echo "  To trust this certificate in your browser (macOS):"
echo "    sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ${CERT_FILE}"
echo ""
echo "  To trust this certificate in your browser (Ubuntu/Debian):"
echo "    sudo cp ${CERT_FILE} /usr/local/share/ca-certificates/forgeguard.crt"
echo "    sudo update-ca-certificates"
