FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 KYC_REPO_ROOT=/app HOST=0.0.0.0 PORT=3978
COPY docs/CONTRACTS.md docs/CONTRACTS.md
COPY shared/kyc_core shared/kyc_core
COPY shared/mock shared/mock
COPY shared/mcp-sanctions shared/mcp-sanctions
COPY src/foundry-kyc-agent src/foundry-kyc-agent
COPY src/m365-host src/m365-host
RUN pip install --no-cache-dir ./shared/kyc_core ./shared/mcp-sanctions ./src/foundry-kyc-agent ./src/m365-host
EXPOSE 3978
CMD ["python", "-m", "kyc_m365.app"]
