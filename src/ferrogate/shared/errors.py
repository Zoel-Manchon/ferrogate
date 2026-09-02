class DomainError(Exception):
    """Violacion de una invariante del dominio."""


class TenantIsolationViolation(DomainError):
    """Un actor intento operar sobre datos de un tenant distinto al suyo.

    Nunca se degrada a un filtro silencioso: se lanza, se audita y se corta.
    """


class SecurityViolation(DomainError):
    """Fallo de autenticacion, autorizacion o integridad del mensaje."""
