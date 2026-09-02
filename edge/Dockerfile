FROM python:3.12-slim

RUN useradd --create-home --uid 10002 edge
WORKDIR /app

COPY edge/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El colector solo usa el kernel compartido de la plataforma (identidad y
# sobre firmado). No conoce nada del modelo multi-tenant.
COPY pyproject.toml /tmp/build/pyproject.toml
COPY src /tmp/build/src
RUN pip install --no-cache-dir --no-deps /tmp/build && rm -rf /tmp/build

COPY edge/ferrogate_edge ./ferrogate_edge

RUN mkdir -p /var/lib/ferrogate && chown edge:edge /var/lib/ferrogate
USER edge
VOLUME ["/var/lib/ferrogate"]

CMD ["python", "-u", "-m", "ferrogate_edge.main"]
