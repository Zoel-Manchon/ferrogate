#!/bin/bash
# InfluxDB 2.x ejecuta lo que haya en /docker-entrypoint-initdb.d despues
# del setup inicial. Aqui se crea el bucket de cada tenant adicional: el
# compose solo puede declarar uno.
#
# Un bucket por tenant no es cosmetico. Si se usara un unico bucket con
# una etiqueta "tenant", una consulta mal escrita cruzaria datos entre
# clientes. La frontera la respeta el motor, no quien escribe el Flux.
set -euo pipefail

for tenant in globex; do
  bucket="tenant-${tenant}"
  if influx bucket list --name "$bucket" --org "$DOCKER_INFLUXDB_INIT_ORG" \
       --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" >/dev/null 2>&1; then
    echo "bucket $bucket ya existe"
  else
    influx bucket create --name "$bucket" \
      --org "$DOCKER_INFLUXDB_INIT_ORG" \
      --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"
    echo "bucket $bucket creado"
  fi
done
