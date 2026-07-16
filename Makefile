.PHONY: dev install

install:
	pip install -r disposition_normalization/requirements.txt
	cd careops-studio && npm install

dev:
	@echo "Starting CareOps Studio..."
	@trap 'kill $$(jobs -p) 2>/dev/null; exit 0' INT TERM EXIT; \
	uvicorn disposition_normalization.server:app --reload --port 8000 & \
	cd careops-studio && npm run dev & \
	wait
