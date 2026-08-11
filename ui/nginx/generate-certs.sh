#!/usr/bin/env sh
# Generate a self-signed TLS certificate for local development.
#
# Usage:
#   ./nginx/generate-certs.sh
#
# Output files:
#   nginx/ssl/cert.pem  — self-signed certificate (365-day validity)
#   nginx/ssl/key.pem   — RSA private key (not encrypted)
#
# Idempotent: skips generation if a valid cert already exists.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSL_DIR="${SCRIPT_DIR}/ssl"

mkdir -p "${SSL_DIR}"

if [ -f "${SSL_DIR}/cert.pem" ] && [ -f "${SSL_DIR}/key.pem" ]; then
    # Verify cert is not expired (openssl returns 1 on failure)
    if openssl x509 -checkend 0 -noout -in "${SSL_DIR}/cert.pem" 2>/dev/null; then
        echo "Self-signed certificate already exists and is valid — skipping generation."
        echo "  cert: ${SSL_DIR}/cert.pem"
        echo "  key:  ${SSL_DIR}/key.pem"
        exit 0
    fi
    echo "Existing certificate has expired — regenerating."
fi

echo "Generating self-signed TLS certificate..."

# Create a temporary OpenSSL config with Subject Alternative Names (SANs)
OPENSSL_CNF="${SSL_DIR}/openssl.cnf"
cat > "${OPENSSL_CNF}" <<EOF
[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
x509_extensions    = v3_req

[dn]
CN = localhost

[v3_req]
subjectAltName = @alt_names
keyUsage       = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
IP.1  = 127.0.0.1
EOF

openssl req \
    -x509 \
    -nodes \
    -days 365 \
    -newkey rsa:2048 \
    -keyout "${SSL_DIR}/key.pem" \
    -out    "${SSL_DIR}/cert.pem" \
    -config "${OPENSSL_CNF}"

rm -f "${OPENSSL_CNF}"

echo "Self-signed TLS certificate generated successfully:"
echo "  cert: ${SSL_DIR}/cert.pem"
echo "  key:  ${SSL_DIR}/key.pem"
echo ""
echo "Valid until: $(openssl x509 -noout -enddate -in "${SSL_DIR}/cert.pem" | cut -d= -f2)"
