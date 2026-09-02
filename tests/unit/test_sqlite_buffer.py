import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "edge"))

from ferrogate_edge.infrastructure.buffer.sqlite_buffer import SqliteBuffer


def test_encola_y_reenvia_en_orden(tmp_path):
    buf = SqliteBuffer(tmp_path / "outbox.db")
    for i in range(5):
        buf.enqueue("t/1", f"sobre-{i}".encode())
    assert buf.depth() == 5
    pending = buf.peek(10)
    assert [p[2] for p in pending] == [f"sobre-{i}".encode() for i in range(5)]


def test_ack_elimina_solo_lo_confirmado(tmp_path):
    buf = SqliteBuffer(tmp_path / "outbox.db")
    for i in range(3):
        buf.enqueue("t/1", str(i).encode())
    buf.ack(buf.peek(1)[0][0])
    assert buf.depth() == 2


def test_sobrevive_a_un_reinicio(tmp_path):
    path = tmp_path / "outbox.db"
    b1 = SqliteBuffer(path)
    b1.enqueue("t/1", b"persistente")
    b1.close()
    assert SqliteBuffer(path).peek(1)[0][2] == b"persistente"


def test_descarta_los_mas_antiguos_al_llenarse(tmp_path):
    buf = SqliteBuffer(tmp_path / "outbox.db", max_rows=3)
    for i in range(6):
        buf.enqueue("t/1", str(i).encode())
    assert buf.depth() == 3
    # Se conservan los recientes: en telemetria el dato nuevo vale mas
    assert [p[2] for p in buf.peek(10)] == [b"3", b"4", b"5"]
