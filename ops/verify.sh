#!/usr/bin/env bash
# Diagnostico end-to-end. Recorre la cadena entera y la reporta paso a paso,
# para ver de un vistazo donde se rompe. Sale con codigo 1 si algo falla.
set -uo pipefail
cd "$(dirname "$0")/.."


# Cuenta filas de datos en el CSV anotado de InfluxDB.
# Descarta anotaciones (#), la cabecera y lineas vacias.
# NO buscar "^,_result": cuando Influx emite "#default,_result" la columna
# va vacia y las filas de datos empiezan por ",,". Ese error hace que un
# bucket lleno parezca vacio.
influx_rows() {
  grep -v '^#' <<<"$1" | grep -v 'result,table' | grep -c '[0-9]' || true
}

ok()   { printf "  [ok]   %s\n" "$1"; }

# El contador es lo que hace que esto sirva de algo. Sin el, fail() solo
# imprimia: el script terminaba en 0 con la cadena rota, y cualquier CI o
# cualquier "&&" despues de make verify daba por buena una plataforma que
# no estaba entregando un solo dato.
FAILURES=0
fail() { printf "  [FALLO] %s\n" "$1"; FAILURES=$((FAILURES + 1)); }

echo "1. Contenedores"
down=$(docker compose ps --format '{{.Service}} {{.State}}' | grep -v running || true)
[[ -z "$down" ]] && ok "todos corriendo" || { fail "no corren: $down"; }

echo "2. Broker: publicaciones y suscripciones denegadas"
mlog=$(docker compose logs --tail=400 mosquitto 2>/dev/null)
denied=$(grep -c "Denied PUBLISH" <<<"$mlog" || true)
[[ "$denied" == "0" ]] && ok "ninguna publicacion denegada" \
  || fail "$denied publicaciones denegadas -- revisa ops/mosquitto/acl y los CN"
dsub=$(grep -c "Denied SUBSCRIBE" <<<"$mlog" || true)
[[ "$dsub" == "0" ]] && ok "ninguna suscripcion denegada" \
  || fail "$dsub suscripciones denegadas -- la ingesta no recibe nada"
# Que la ingesta este CONECTADA es distinto de que este suscrita
if grep -q "platform-ingest" <<<"$mlog"; then ok "la ingesta figura en el broker"
else fail "la ingesta no aparece en los logs del broker: no conecta"; fi

echo "3. Colectores: buffer acumulandose"
for svc in edge-acme edge-globex; do
  warn=$(docker compose logs --tail=50 "$svc" 2>/dev/null | grep -c "publicacion fallida" || true)
  [[ "$warn" == "0" ]] && ok "$svc publica sin encolar" \
    || fail "$svc encolando ($warn): el broker rechaza o esta caido"
done

echo "4. Ingesta: sobres rechazados o con error"
logs=$(docker compose logs --tail=300 platform-ingest 2>/dev/null)
rej=$(grep -c "rechazado\|revoked\|fallo procesando" <<<"$logs" || true)
if [[ "$rej" == "0" ]]; then
  ok "ninguno rechazado"
else
  fail "$rej con problema. Motivos reales:"
  grep -oE "reason.*|firma invalida|reenvio|ventana temporal|revoked_gateway|no tiene tag [^ ]*" \
    <<<"$logs" | sort | uniq -c | sort -rn | head -5 | sed "s/^/         /"
fi

echo "4b. Ingesta: sobres aceptados"
acc=$(docker compose logs --tail=300 platform-ingest 2>/dev/null | grep -c "aceptados" || true)
[[ "$acc" != "0" ]] && ok "la ingesta acepta sobres" \
  || fail "cero sobres aceptados: los mensajes no llegan al consumidor"

echo "5. Ingesta: muestras descartadas en silencio"
# unknown_asset y cross_tenant_asset NO son excepciones: la ingesta las
# audita y sigue. Sin este paso, todo sale en verde y no llega un dato.
psql_q() { docker compose exec -T postgres psql -U ferrogate -d ferrogate -tAc "$1" 2>/dev/null | tr -d " \r"; }
silent=$(psql_q "SELECT coalesce(sum(1),0) FROM audit_events WHERE event LIKE 'ingest.%asset'")
if [[ "${silent:-0}" == "0" ]]; then ok "ninguna descartada"
else
  fail "$silent muestras descartadas. Desglose:"
  docker compose exec -T postgres psql -U ferrogate -d ferrogate -tAc \
    "SELECT event || ': ' || count(*) FROM audit_events GROUP BY event" 2>/dev/null \
    | sed "s/^/         /"
  echo "         -> el asset_id de edge/ferrogate_edge/config/*.yaml no coincide"
  echo "            con la tabla assets. Compara ambos y relanza 'make seed'."
fi

echo "6. Enrolamiento en Postgres"
rows=$(docker compose exec -T postgres psql -U ferrogate -d ferrogate -tAc \
  "SELECT (SELECT count(*) FROM tenants) || '/' || (SELECT count(*) FROM gateways WHERE cert_pem <> '')" 2>/dev/null | tr -d ' \r')
if [[ "$rows" == "2/2" ]]; then ok "2 tenants y 2 gateways con certificado"
else fail "tenants/gateways = ${rows:-nada}: ejecuta 'make seed'"; fi

echo "7. Buckets de InfluxDB"
for b in tenant-acme tenant-globex; do
  if docker compose exec -T influxdb influx bucket list --name "$b" \
       --token "${INFLUX_TOKEN:-}" >/dev/null 2>&1; then ok "$b existe"
  else fail "$b no existe"; fi
done

echo "8. Datos escritos (ultimos 10 min)"
for tn in acme globex; do
  out=$(docker compose exec -T influxdb influx query \
        "from(bucket:\"tenant-$tn\") |> range(start:-10m) |> limit(n:5)" \
        --org ferrogate --token "${INFLUX_TOKEN:-}" --raw 2>&1)
  # El error se comprueba ANTES de contar, no despues. Al reves, un
  # "401 Unauthorized" pasaba por influx_rows(), que cuenta cualquier linea
  # con digitos: el 401 se contaba como una fila y la consulta fallida se
  # reportaba como "tiene datos (1 filas)". Un fallo de autenticacion no
  # puede parecerse a un exito.
  if grep -qiE "^Error:|unauthorized|not found" <<<"$out"; then
    fail "tenant-$tn: la consulta fallo, no es que este vacio:"
    head -3 <<<"$out" | sed "s/^/         /"
    continue
  fi
  rows=$(influx_rows "$out")
  if [[ "$rows" -gt 0 ]]; then
    ok "tenant-$tn tiene datos ($rows filas de muestra)"
  else
    fail "tenant-$tn vacio (consulta correcta, sin resultados)"
  fi
done

echo
if [[ "$FAILURES" -gt 0 ]]; then
  printf "%d comprobacion(es) fallaron. La cadena NO esta entera.\n" "$FAILURES"
  exit 1
fi
echo "Cadena completa verificada."
