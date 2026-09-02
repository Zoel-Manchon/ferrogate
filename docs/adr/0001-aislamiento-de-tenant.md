# ADR 0001 — Estrategia de aislamiento entre tenants

Estado: aceptado

## Contexto

La plataforma sirve a varios clientes industriales. Una fuga de datos
entre clientes es el peor fallo posible del producto.

## Opciones

1. Base de datos por tenant — aislamiento maximo, coste operativo alto,
   migraciones multiplicadas por N.
2. Esquema por tenant — buen aislamiento, pero el pool de conexiones y
   las migraciones se complican, y `search_path` es facil de estropear.
3. Tablas compartidas con filtrado en el repositorio — el mas simple y el
   mas fragil: un `WHERE` olvidado y se acabo.
4. Tablas compartidas con Row Level Security.

## Decision

Opcion 4, con `FORCE ROW LEVEL SECURITY` y `set_config(..., TRUE)` local
a la transaccion.

## Razones

El filtrado ocurre en el motor, no en el codigo de aplicacion. Un error
humano en un repositorio no puede saltarse la politica. `FORCE` es
imprescindible: sin el, el usuario propietario del esquema ignora las
politicas y los tests pasan mientras produccion queda abierta.

## Consecuencias

- Toda conexion debe fijar `ferrogate.tenant_id` o no ve nada; el fallo
  es cerrado, que es lo que se quiere.
- Hace falta un test de integracion con dos tenants reales que verifique
  el aislamiento; no basta con confiar en la politica.
- Si un tenant crece mucho, migrar a base de datos dedicada exige trabajo.
  Se acepta: es un problema de exito.
