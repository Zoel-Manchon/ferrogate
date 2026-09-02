"""Identidad criptografica del gateway.

El gateway se autentica con mTLS. Su certificado lleva en el SAN una URI
con la forma:

    urn:ferrogate:tenant:<tenant-id>:gateway:<gateway-id>

Esa URI es la UNICA fuente de verdad sobre a que tenant pertenece un
mensaje. Nada de lo que venga en el payload o en el topic puede
contradecirla: si lo hace, se rechaza el mensaje y se audita.

Este es el control que impide la inyeccion de telemetria entre tenants,
que es el ataque mas serio contra una plataforma multi-tenant de este tipo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ferrogate.shared.domain.identifiers import GatewayId, TenantId
from ferrogate.shared.errors import SecurityViolation

_URN = re.compile(
    r"^urn:ferrogate:tenant:(?P<tenant>[a-z0-9][a-z0-9-]{1,62})"
    r":gateway:(?P<gateway>[a-z0-9][a-z0-9-]{1,62})$"
)


@dataclass(frozen=True, slots=True)
class GatewayIdentity:
    """Identidad probada por el certificado cliente, no declarada por el peer."""

    tenant_id: TenantId
    gateway_id: GatewayId

    @staticmethod
    def from_san_uri(uri: str) -> "GatewayIdentity":
        match = _URN.match(uri.strip())
        if match is None:
            raise SecurityViolation(f"SAN URI no reconocida: {uri!r}")
        return GatewayIdentity(
            tenant_id=TenantId(match.group("tenant")),
            gateway_id=GatewayId(match.group("gateway")),
        )

    def to_san_uri(self) -> str:
        return f"urn:ferrogate:tenant:{self.tenant_id}:gateway:{self.gateway_id}"

    def owns_topic(self, topic: str) -> bool:
        """Los topics son ferrogate/<tenant>/<gateway>/telemetry/<...>.

        Se comprueba prefijo completo por segmentos, nunca startswith sobre
        la cadena: 'acme' no debe dar por bueno un topic de 'acme-corp'.
        """
        parts = topic.split("/")
        if len(parts) < 4 or parts[0] != "ferrogate":
            return False
        return parts[1] == str(self.tenant_id) and parts[2] == str(self.gateway_id)
