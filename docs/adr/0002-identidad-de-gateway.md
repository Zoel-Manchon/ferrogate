# ADR 0002 — La identidad del gateway vive en el certificado

Estado: aceptado

## Contexto

Cada mensaje de telemetria dice a que tenant pertenece. Si esa afirmacion
la hace el propio mensaje, cualquier gateway comprometido puede escribir
en los datos de otro cliente.

## Decision

El gateway se autentica con mTLS. Su certificado lleva en el SAN una URI
`urn:ferrogate:tenant:<t>:gateway:<g>`, y esa URI es la unica fuente de
verdad. El topic y el payload se comprueban CONTRA ella; nunca al reves.

## Razones

Separa lo que el peer *demuestra* de lo que el peer *declara*. La ACL de
Mosquitto es la primera barrera y el guardia en el caso de uso la
segunda: si el broker se reconfigura mal, la aplicacion sigue cortando.

## Consecuencias

- Hace falta gestionar una PKI, aunque sea de laboratorio.
- La comparacion de topics es por segmentos, no por `startswith`, para que
  `acme` no valide un topic de `acme-corp`. Hay test para eso.
- Rotar un certificado implica reenrolar el gateway.
