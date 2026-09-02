FROM python:3.12-slim

# No corre como root: es un simulador, pero el habito se coge aqui
RUN useradd --create-home --uid 10001 sim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY register_map.py plant.py server.py ./
USER sim

EXPOSE 5020
CMD ["python", "-u", "server.py"]
