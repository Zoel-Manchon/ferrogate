.PHONY: install pki seed seed-host up down reset test arch security logs check verify probe

# Make NO lee .env por su cuenta (docker compose si). Sin esto,
# POSTGRES_PASSWORD queda vacio y la conexion falla con "password failed".
ifneq (,$(wildcard .env))
include .env
export
endif

DATABASE_URL ?= postgresql+psycopg://ferrogate:$(POSTGRES_PASSWORD)@localhost:5432/ferrogate

install:  ; pip install -e ".[dev]"
pki:      ; ./ops/pki/gen_pki.sh

# Enrolamiento DENTRO de la red de docker: se conecta al host "postgres",
# asi que no le afecta que tengas otro PostgreSQL ocupando el 5432 local.
# Ruta RELATIVA a propocito: Git Bash convierte cualquier argumento que
# empiece por "/" en una ruta de Windows y el comando falla. Los
# certificados llegan por el montaje /certs que el servicio ya declara.
seed:
	docker compose run --rm --no-deps \
		-e DATABASE_URL=postgresql+psycopg://ferrogate:$(POSTGRES_PASSWORD)@postgres:5432/ferrogate \
		-e PKI_DIR=/certs \
		platform-ingest python ops/seed.py

# Alternativa desde el host, si prefieres depurar con tus herramientas.
seed-host:
	DATABASE_URL="$(DATABASE_URL)" python ops/seed.py

# Diagnostico rapido cuando algo no conecta.
check:
	@echo "POSTGRES_PASSWORD definido: $(if $(POSTGRES_PASSWORD),si,NO -- revisa .env)"
	@echo "INFLUX_TOKEN definido:      $(if $(INFLUX_TOKEN),si,NO -- revisa .env)"
	@echo "--- puertos publicados ---"
	@docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
	@echo "--- quien escucha en 5432 ---"
	@docker compose port postgres 5432 2>/dev/null || echo "postgres no publica 5432"

up: pki   ; docker compose --profile acme --profile globex up -d --build
down:     ; docker compose --profile acme --profile globex down -v
reset:    ; $(MAKE) down && rm -rf ops/pki/out && $(MAKE) up
logs:     ; docker compose logs -f platform-ingest edge-acme

# Recorre la cadena completa y para en el primer eslabon roto.
verify:   ; ./ops/verify.sh
probe:    ; ./ops/probe-influx.sh
test:     ; pytest -q
arch:     ; pytest tests/architecture -q && lint-imports
security: ; bandit -r src edge -c pyproject.toml && pip-audit --strict
