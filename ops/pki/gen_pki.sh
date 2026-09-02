#!/usr/bin/env bash
# CA de laboratorio + certificados de broker y gateway.
# NO usar en produccion: las claves quedan sin cifrar en disco.
set -euo pipefail

# Git Bash / MSYS2 en Windows convierte los argumentos que empiezan por "/"
# en rutas de Windows, y destroza los -subj de openssl:
#   /CN=mosquitto  ->  C:/Program Files/Git/CN=mosquitto
# Estas dos variables desactivan esa conversion. En Linux y macOS no hacen nada.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

cd "$(dirname "$0")"
mkdir -p out && cd out

# Se comprueban AMBOS ficheros: si una ejecucion anterior fallo despues de
# escribir la clave pero antes del certificado, regenerar es lo correcto.
if [[ ! -f ca.key || ! -f ca.crt ]]; then
  rm -f ca.key ca.crt ca.srl
  openssl req -x509 -newkey rsa:4096 -days 3650 -nodes \
    -keyout ca.key -out ca.crt -subj "/CN=Ferrogate Lab CA/O=Ferrogate"
fi

gen_broker() {
  openssl req -newkey rsa:2048 -nodes -keyout broker.key -out broker.csr \
    -subj "/CN=mosquitto"
  printf "subjectAltName=DNS:mosquitto,DNS:localhost,IP:127.0.0.1\n" > broker.ext
  openssl x509 -req -in broker.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out broker.crt -days 825 -extfile broker.ext
  rm -f broker.csr broker.ext
}

# gen_gateway <tenant> <gateway>
# El SAN lleva la URN que la aplicacion parsea como identidad probada.
gen_gateway() {
  local tenant="$1" gw="$2" cn="$1.$2"
  openssl req -newkey rsa:2048 -nodes -keyout "${cn}.key" -out "${cn}.csr" \
    -subj "/CN=${cn}/O=${tenant}"
  printf "subjectAltName=URI:urn:ferrogate:tenant:%s:gateway:%s\nextendedKeyUsage=clientAuth\n" \
    "$tenant" "$gw" > "${cn}.ext"
  openssl x509 -req -in "${cn}.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out "${cn}.crt" -days 825 -extfile "${cn}.ext"
  rm -f "${cn}.csr" "${cn}.ext"
  echo "  huella: $(openssl x509 -in "${cn}.crt" -noout -fingerprint -sha256)"
}

[[ -f broker.crt ]] || gen_broker
# El servicio de ingesta tambien se autentica por mTLS contra el broker
openssl req -newkey rsa:2048 -nodes -keyout platform-ingest.key \
  -out platform-ingest.csr -subj "/CN=platform-ingest/O=ferrogate"
printf "extendedKeyUsage=clientAuth\n" > platform-ingest.ext
openssl x509 -req -in platform-ingest.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out platform-ingest.crt -days 825 -extfile platform-ingest.ext
rm -f platform-ingest.csr platform-ingest.ext

gen_gateway acme planta-norte
gen_gateway globex planta-sur

echo "PKI generada en $(pwd)"
