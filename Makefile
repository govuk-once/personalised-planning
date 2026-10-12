.PHONY: local local-setup check table urls

CLEAN_ENV := env -i HOME='$(HOME)' PATH='$(PATH)'
LOCAL_AWS := $(CLEAN_ENV) AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local
SAM := $(LOCAL_AWS) FLASK_SKIP_DOTENV=1 DOCKER_HOST=unix://$(HOME)/.docker/run/docker.sock sam local start-lambda --template .local/cdk.out/PpLocal.template.json --region eu-west-2
DYNAMODB := $(LOCAL_AWS) aws dynamodb --endpoint-url http://localhost:8001 --region eu-west-2
SUMMARY := .local/backend.json

local-setup:
	npm install --no-audit --no-fund
	npm ci --prefix backend --no-audit --no-fund
	cd frontend && pnpm install

local: check
	@$(CLEAN_ENV) LOCAL_MODE=true npm run --silent backend:local
	@creds=$$(gds-cli aws "$(AWS_PROFILE)" -r eu-west-2 -e) || exit 1; \
	eval "$$creds"; \
	api=$$(jq -r .apiFunction $(SUMMARY)); \
	trap : INT TERM; \
	npx --yes concurrently@10.0.5 --kill-others --names agents,worker,api,next,urls \
		"docker compose up --build --abort-on-container-exit" \
		"$(SAM) --port 8002" \
		"make --no-print-directory table && $(SAM) --port 8000 --warm-containers EAGER" \
		"cd frontend && BACKEND_FUNCTION_NAME=$$api BACKEND_LAMBDA_ENDPOINT=http://127.0.0.1:8000 pnpm dev" \
		"make --no-print-directory urls && tail -f /dev/null"; \
	status=$$?; \
	docker compose stop; \
	docker ps -aq --filter label=sam.cli.container.type=lambda | xargs docker rm -f; \
	exit $$status

check:
	@test -n "$(AWS_PROFILE)" || { echo "Set your gds-cli role first: export AWS_PROFILE=<role>"; exit 1; }
	@gds-cli aws "$(AWS_PROFILE)" -d > /dev/null || { echo "gds-cli has no role called $(AWS_PROFILE)"; exit 1; }
	@test -f .env || { echo "Missing .env: cp .env.example .env"; exit 1; }
	@test -d node_modules && test -d backend/node_modules && test -d frontend/node_modules || { echo "Run make local-setup first"; exit 1; }

table:
	@until $(DYNAMODB) list-tables > /dev/null 2>&1; do sleep 1; done
	@table=$$(jq -r .table.definition.TableName $(SUMMARY)); \
	$(DYNAMODB) describe-table --table-name "$$table" > /dev/null 2>&1 || \
	$(DYNAMODB) create-table --cli-input-json "$$(jq -c .table.definition $(SUMMARY))" --query TableDescription.TableName

urls:
	@until curl -s -o /dev/null http://localhost:3000 && curl -sf -o /dev/null http://localhost:8080/ping && curl -sf -o /dev/null http://localhost:8081/ping && curl -s -o /dev/null http://localhost:8000 && curl -s -o /dev/null http://localhost:8002; do sleep 2; done
	@echo
	@printf '%-20s %s\n' \
		"Site (Next.js)" "http://localhost:3000" \
		"Conversation agent" "http://localhost:8081/invocations" \
		"Planner agent" "http://localhost:8080/invocations" \
		"Api Lambda" "http://localhost:8000/2015-03-31/functions/$$(jq -r .apiFunction $(SUMMARY))/invocations" \
		"Worker Lambda" "http://localhost:8002/2015-03-31/functions/$$(jq -r .workerFunction $(SUMMARY))/invocations" \
		"DynamoDB Local" "http://localhost:8001 (table $$(jq -r .table.definition.TableName $(SUMMARY)))"
