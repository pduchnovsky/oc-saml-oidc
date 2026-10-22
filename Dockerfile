FROM python:3.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    RUNTIME_DIR=/tmp/omada-saml-oidc \
    PUBLIC_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        xmlsec1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

ARG PACKAGE_VERSION
RUN if [ -n "$PACKAGE_VERSION" ]; then \
        python -c 'import os, re; from pathlib import Path; path = Path("src/omada_saml_oidc/__init__.py"); source = path.read_text(); updated, count = re.subn(r"^__version__ = .+$", "__version__ = \"" + os.environ["PACKAGE_VERSION"] + "\"", source, count=1, flags=re.MULTILINE); assert count == 1; path.write_text(updated)'; \
    fi \
    && pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/healthz > /dev/null || exit 1

CMD ["omada-saml-oidc"]
