#!/usr/bin/env bash
# Sonda directa a InfluxDB. Separa tres causas que se confunden entre si:
# datos ausentes, datos fuera del rango temporal, y consulta que falla.
set -uo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] && export $(grep -v '^#' .env | grep -v '^$' | xargs)


# Cuenta filas de datos en el CSV anotado de InfluxDB.
# Descarta anotaciones (#), la cabecera y lineas vacias.
# NO buscar "^,_result": cuando Influx emite "#default,_result" la columna
# va vacia y las filas de datos empiezan por ",,". Ese error hace que un
# bucket lleno parezca vacio.
influx_rows() {
  grep -v '^#' <<<"$1" | grep -v 'result,table' | grep -c '[0-9]' || true
}

q() { docker compose exec -T influxdb influx query "$1" \
        --org ferrogate --token "$INFLUX_TOKEN" --raw 2>&1; }

echo "== Relojes (una deriva entre contenedores mueve los datos fuera de rango) =="
echo "  host:    $(date -u '+%Y-%m-%d %H:%M:%S')"
echo "  influx:  $(docker compose exec -T influxdb date -u '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
echo "  edge:    $(docker compose exec -T edge-acme date -u '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"

for b in tenant-acme tenant-globex; do
  echo
  echo "== $b =="
  out=$(q "from(bucket:\"$b\") |> range(start: -30d, stop: 30d) |> limit(n:3)")
  rows=$(influx_rows "$out")
  if [[ "$rows" -gt 0 ]]; then
    echo "  HAY DATOS ($rows filas). Marcas de tiempo encontradas:"
    grep -v '^#' <<<"$out" | grep -v 'result,table' | grep '[0-9]' \
      | cut -d, -f6 | head -3 | sed 's/^/    /'
    echo "  Si no aparecian en -10m, el problema es la marca de tiempo, no la escritura."
  elif grep -qi "unauthorized" <<<"$out"; then
    echo "  401: el token de .env no coincide con el del volumen de Influx."
    echo "  Influx solo aplica INFLUX_TOKEN al inicializar el volumen."
  elif grep -qi "not found" <<<"$out"; then
    echo "  El bucket no existe con ese nombre exacto."
  else
    echo "  VACIO de verdad: no se ha escrito nunca nada en este bucket."
    head -2 <<<"$out" | sed 's/^/    /'
  fi
done
