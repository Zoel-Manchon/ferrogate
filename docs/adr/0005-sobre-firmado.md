# ADR 0005 — Telemetria firmada extremo a extremo

Estado: aceptado

## Contexto

El servicio de ingesta se suscribe a MQTT como cliente. En esa posicion
no tiene acceso al certificado TLS del gateway que publico el mensaje:
solo ve el topic y el payload.

## Opciones

1. Deducir el tenant del topic y confiar en la ACL de Mosquitto.
2. Un plugin de autenticacion en el broker que inyecte la identidad.
3. Firmar cada sobre en el gateway y verificar en la ingesta.

## Decision

Opcion 3, manteniendo la ACL del broker como primera barrera.

## Razones

La opcion 1 pone toda la seguridad multi-tenant en un fichero de
configuracion del broker: un error de reconfiguracion abre el paso entre
clientes y nada lo detecta. La opcion 2 ata el diseno a Mosquitto.

Con firma extremo a extremo el broker deja de ser confiable por diseno.
Puede reenviar, reordenar o mezclar mensajes; no puede fabricar uno
valido. Ademas da no repudio: queda constancia criptografica de que un
dato concreto salio de un gateway concreto.

## Consecuencias

- Hay que enrolar el certificado del gateway en la base de datos.
- El anti-reenvio necesita una secuencia persistida: reiniciar la ingesta
  no debe reabrir la ventana.
- Coste de CPU por firma. A 5 segundos de intervalo es despreciable; con
  miles de gateways habria que revisarlo.
- La serializacion debe ser canonica o la firma falla de forma
  intermitente, que es dificil de depurar.
