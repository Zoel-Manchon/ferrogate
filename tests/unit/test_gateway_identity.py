import pytest

from ferrogate.shared.errors import SecurityViolation
from ferrogate.shared.security.gateway_identity import GatewayIdentity

URN = "urn:ferrogate:tenant:acme:gateway:planta-norte"


def test_parsea_la_urn_del_san():
    identity = GatewayIdentity.from_san_uri(URN)
    assert str(identity.tenant_id) == "acme"
    assert str(identity.gateway_id) == "planta-norte"


def test_rechaza_una_urn_malformada():
    with pytest.raises(SecurityViolation):
        GatewayIdentity.from_san_uri("urn:otracosa:tenant:acme")


def test_acepta_su_propio_topic():
    identity = GatewayIdentity.from_san_uri(URN)
    assert identity.owns_topic("ferrogate/acme/planta-norte/telemetry/power")


def test_rechaza_el_topic_de_otro_tenant():
    identity = GatewayIdentity.from_san_uri(URN)
    assert not identity.owns_topic("ferrogate/globex/planta-sur/telemetry/power")


def test_un_prefijo_parecido_no_cuela():
    """'acme' no debe dar por bueno un topic de 'acme-corp'."""
    identity = GatewayIdentity.from_san_uri(URN)
    assert not identity.owns_topic("ferrogate/acme-corp/planta-norte/telemetry/x")
