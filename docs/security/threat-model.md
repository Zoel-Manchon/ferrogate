# Modelo de amenazas (STRIDE)

Alcance: plataforma multi-tenant y gateways edge. Fuera de alcance: la red
OT aguas abajo del gateway, que se asume no confiable por definicion.

| # | Amenaza | STRIDE | Control | Verificado por |
|---|---------|--------|---------|----------------|
| 1 | Un gateway publica telemetria en el topic de otro tenant | Spoofing | ACL explicita por CN + firma del sobre + guardia en el caso de uso | `test_gateway_identity.py`, `test_acl_matches_topics.py`, `test_envelope_processor.py` |
| 13 | La ACL deniega en silencio y nadie se entera | Denial of service | Test que compara los topics que publica el edge con lo que la ACL permite | `test_acl_matches_topics.py` |
| 2 | Una query mal escrita devuelve filas de otro tenant | Information disclosure | RLS con `FORCE` en Postgres, bucket por tenant en InfluxDB | test de integracion con dos tenants |
| 3 | Un repositorio nuevo se anade sin scope de tenant | Information disclosure | Test de arquitectura sobre los puertos | `test_tenant_scoping.py` |
| 4 | Robo del certificado de un gateway | Spoofing | Certificado enrolado en BD, `revoked_at`; un gateway revocado no resuelve certificado y su sobre se descarta | `test_envelope_processor.py::test_gateway_revocado_es_rechazado` |
| 5 | Un gateway inunda el broker | Denial of service | Limite de 256 KiB por sobre y 500 muestras, validado antes de parsear | `test_envelope.py::test_payload_gigante_rechazado_antes_de_parsear` |
| 6 | Suplantacion del servidor OPC-UA | Spoofing | `SignAndEncrypt` + validacion de certificado de servidor | pendiente: fase 2 |
| 7 | Manipulacion de valores en transito | Tampering | TLS 1.2+ y ademas firma RSA-PSS extremo a extremo: el broker no esta en la base de confianza | `test_envelope.py::test_manipular_un_valor_invalida_la_firma` |
| 11 | Reenvio de un sobre capturado | Tampering | Ventana temporal sobre `sent_at` + secuencia monotona persistida por gateway | `test_envelope.py`, `test_envelope_processor.py` |
| 12 | Perdida de datos por caida del enlace | Denial of service | Store-and-forward en SQLite con permisos 0600, drenaje ordenado y descarte del dato mas antiguo al llenarse | `test_collect_cycle.py`, `test_sqlite_buffer.py` |
| 8 | Un operador niega haber reconocido una alarma | Repudiation | `acknowledged_by` obligatorio + tabla de auditoria por tenant | `test_alarm_state_machine.py` |
| 9 | Dependencia vulnerable en produccion | Elevation of privilege | `pip-audit`, Trivy y SBOM en cada build y semanalmente | workflow de CI |
| 10 | Secretos comiteados por error | Information disclosure | gitleaks en pre-commit y en CI sobre todo el historico | workflow de CI |

| 14 | Un atacante provoca excepciones publicando con un tenant inexistente | Denial of service | Los rechazos previos a la autenticacion van a `security_events`, sin FK ni RLS; el adaptador nunca propaga su propio fallo | `test_envelope_processor.py::test_un_tenant_inexistente_no_tumba_la_ingesta` |
| 15 | Reinicio del gateway reabre la ventana de reenvio | Tampering | La secuencia se persiste en el buffer del gateway y sobrevive al reinicio | `test_collect_cycle.py::test_la_secuencia_sobrevive_a_un_reinicio` |

## Auditoria probada frente a auditoria reclamada

Hay dos registros y la distincion es deliberada:

- `audit_events` lleva RLS y clave foranea a `tenants`. Solo recibe
  eventos DESPUES de verificar la firma: la identidad esta probada.
- `security_events` no lleva ni FK ni RLS. Recibe los rechazos previos a
  la autenticacion, donde el tenant es lo que alguien *dijo* ser y puede
  no existir.

Mezclarlos parecia mas simple y era un error: auditar un gateway
desconocido bajo el tenant que reclamaba violaba la clave foranea y
tumbaba el consumidor, convirtiendo el camino de rechazo en un vector de
denegacion de servicio.

## Por que el broker no esta en la base de confianza

El servicio de ingesta es un cliente MQTT y no ve el certificado del
gateway que publico. Si dedujera el tenant del topic, toda la seguridad
dependeria de la ACL de Mosquitto, y un broker mal reconfigurado abriria
el paso entre tenants sin dejar rastro.

Por eso cada sobre va firmado por el gateway y se verifica contra el
certificado enrolado. El broker puede reenviar, reordenar o mezclar
mensajes; no puede fabricar uno valido. La ACL sigue ahi como primera
barrera, pero ya no es la unica.

## Decisiones conscientes de riesgo

- La CA de laboratorio genera claves sin cifrar en disco. Aceptable solo
  porque `ops/pki/out/` esta en `.gitignore` y el entorno es efimero.
- No hay OCSP ni CRL. La revocacion se resuelve por huella en base de
  datos, que basta a esta escala pero no escalaria a miles de gateways.
