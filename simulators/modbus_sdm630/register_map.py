"""Mapa de registros del Eastron SDM630.

Registros de entrada (funcion 04), float32 big-endian, 2 registros cada uno.
Direcciones en base 0 tal como las espera pymodbus.

IMPORTANTE: verifica estas direcciones contra el manual de TU version de
firmware antes de darlas por buenas. El SDM630 tiene variantes (V1, V2,
MCT, Modbus vs MID) con mapas que no coinciden del todo. Este mapa esta
tomado del SDM630 Modbus V2 y sirve como punto de partida.
"""

INPUT_REGISTERS: dict[int, tuple[str, str, float, float]] = {
    # registro: (nombre, unidad, minimo tipico, maximo tipico)
    0x0000: ("voltage_l1", "V", 220.0, 245.0),
    0x0002: ("voltage_l2", "V", 220.0, 245.0),
    0x0004: ("voltage_l3", "V", 220.0, 245.0),
    0x0006: ("current_l1", "A", 0.0, 60.0),
    0x0008: ("current_l2", "A", 0.0, 60.0),
    0x000A: ("current_l3", "A", 0.0, 60.0),
    0x000C: ("power_l1", "W", 0.0, 14000.0),
    0x000E: ("power_l2", "W", 0.0, 14000.0),
    0x0010: ("power_l3", "W", 0.0, 14000.0),
    0x0034: ("total_power", "W", 0.0, 42000.0),
    0x003E: ("total_power_factor", "", 0.80, 1.0),
    0x0046: ("frequency", "Hz", 49.8, 50.2),
    0x0048: ("import_active_energy", "kWh", 0.0, 1_000_000.0),
    0x004A: ("export_active_energy", "kWh", 0.0, 1_000_000.0),
}
