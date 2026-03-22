.PHONY: help setup run demo demo-local ngrok stop dev test check-env

PYTHON   ?= python3
PORT_API ?= 8000
SCENARIO ?= cancel_service
TREE     ?= acme_corp

NGROK_GLOBAL_CONFIG ?= $(shell ngrok config check 2>/dev/null | grep -oP '(?<=at ).*' || echo "$(HOME)/.config/ngrok/ngrok.yml")
NGROK_PID_FILE      := /tmp/gulubala-ngrok.pid

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python dependencies
	$(PYTHON) -m pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Core commands
# ---------------------------------------------------------------------------

run: ## One command: start ngrok + wait for tunnel + run demo (Ctrl+C cleans up)
	@# Kill anything occupying our port first
	@pid=$$(lsof -ti :$(PORT_API) 2>/dev/null); \
	if [ -n "$$pid" ]; then \
		echo "[run] Killing stale process on port $(PORT_API) (pid $$pid)"; \
		kill $$pid 2>/dev/null || true; \
		sleep 0.5; \
	fi
	@# Start ngrok in the background
	@echo "[run] Starting ngrok tunnel (port $(PORT_API))..."
	@ngrok start --all --config $(NGROK_GLOBAL_CONFIG) --config ngrok.yml \
		--log=stdout --log-level=warn & echo $$! > $(NGROK_PID_FILE)
	@# Wait up to 15 s for the tunnel to appear
	@echo "[run] Waiting for ngrok tunnel..."
	@for i in $$(seq 1 15); do \
		URLS=$$($(PYTHON) scripts/detect_ngrok.py $(PORT_API) 2>/dev/null); \
		if echo "$$URLS" | grep -q 'NGROK_URL=https'; then \
			break; \
		fi; \
		sleep 1; \
	done
	@# Detect final URL and launch the demo
	@eval $$($(PYTHON) scripts/detect_ngrok.py $(PORT_API) 2>/dev/null) && \
		export PUBLIC_API_BASE_URL="$$NGROK_URL" && \
		if [ -z "$$NGROK_URL" ]; then \
			echo "[run] WARNING: ngrok tunnel not detected. Dashboard-only mode."; \
			echo "  NGROK_URL=$$NGROK_URL"; \
		else \
			echo "[run] Tunnel ready:"; \
			echo "  NGROK_URL=$$NGROK_URL"; \
			echo "  PUBLIC_API_BASE_URL=$$PUBLIC_API_BASE_URL"; \
		fi && \
		echo "" && \
		$(PYTHON) main.py --demo --scenario $(SCENARIO) --tree $(TREE) --port $(PORT_API); \
		EXIT_CODE=$$?; \
		echo "[run] Cleaning up..."; \
		if [ -f $(NGROK_PID_FILE) ]; then \
			kill $$(cat $(NGROK_PID_FILE)) 2>/dev/null || true; \
			rm -f $(NGROK_PID_FILE); \
		fi; \
		exit $$EXIT_CODE

stop: ## Kill any leftover ngrok / uvicorn on demo port
	@pid=$$(lsof -ti :$(PORT_API) 2>/dev/null); \
	if [ -n "$$pid" ]; then \
		echo "[stop] Killing pid $$pid on port $(PORT_API)"; \
		kill $$pid 2>/dev/null || true; \
	fi
	@if [ -f $(NGROK_PID_FILE) ]; then \
		echo "[stop] Killing ngrok (pid $$(cat $(NGROK_PID_FILE)))"; \
		kill $$(cat $(NGROK_PID_FILE)) 2>/dev/null || true; \
		rm -f $(NGROK_PID_FILE); \
	fi
	@echo "[stop] Done."

# ---------------------------------------------------------------------------
# Standalone targets (when you want manual control)
# ---------------------------------------------------------------------------

ngrok: ## Start ngrok tunnel in foreground (API only)
	ngrok start --all --config $(NGROK_GLOBAL_CONFIG) --config ngrok.yml

demo: ## Run demo (expects ngrok already running)
	@eval $$($(PYTHON) scripts/detect_ngrok.py $(PORT_API) 2>/dev/null) && \
		export PUBLIC_API_BASE_URL="$$NGROK_URL" && \
		echo "  NGROK_URL=$$NGROK_URL" && \
		echo "  PUBLIC_API_BASE_URL=$$PUBLIC_API_BASE_URL" && \
		echo "" && \
		$(PYTHON) main.py --demo --scenario $(SCENARIO) --tree $(TREE) --port $(PORT_API)

demo-local: ## Dashboard-only demo (no ngrok, no outbound call)
	$(PYTHON) main.py --demo --scenario $(SCENARIO) --tree $(TREE) --port $(PORT_API)

dev: ## Dev server (single ngrok tunnel + uvicorn via scripts/dev.sh)
	./scripts/dev.sh $(PORT_API)

dashboard-setup: ## Install Next.js dashboard dependencies
	cd dashboard-ui && npm install

dashboard-dev: ## Start the React dashboard (dev mode, port 3001)
	cd dashboard-ui && npm run dev

dashboard-build: ## Production build of React dashboard
	cd dashboard-ui && npm run build

test: ## Run the test suite
	$(PYTHON) -m pytest tests/ -v

check-env: ## Verify .env credentials are loaded
	@$(PYTHON) -c "\
from dotenv import load_dotenv; load_dotenv(); \
from config import models as m; \
print('Eigen API:       ', 'OK' if m.EIGEN_BASE_URL else 'MISSING'); \
print('Twilio SID:      ', 'OK' if m.TWILIO_ACCOUNT_SID else 'NOT SET'); \
print('Twilio IVR #:    ', m.TWILIO_IVR_NUMBER or 'NOT SET'); \
print('Twilio Agent #:  ', m.TWILIO_AGENT_NUMBER or 'NOT SET'); \
print('Presenter #:     ', m.PRESENTER_PHONE_NUMBER or 'NOT SET'); \
print('Public base URL: ', m.PUBLIC_API_BASE_URL or 'NOT SET')"
