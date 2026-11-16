# Official Ollama runtime includes its GPU libraries. Pin upgrades deliberately.
FROM ollama/ollama:0.40.16

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv tini \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/worker-venv

ENV PATH="/opt/worker-venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_MODELS=/opt/ollama-models \
    OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=1

COPY requirements.txt /opt/worker/requirements.txt
RUN pip install --no-cache-dir -r /opt/worker/requirements.txt

# The heavy model layer is reused when only the handler changes.
ARG OLLAMA_MODEL=llama3.1:8b
ENV OLLAMA_MODEL=${OLLAMA_MODEL}
COPY runtime.py bake_model.py /opt/model-build/
RUN python /opt/model-build/bake_model.py

WORKDIR /app
COPY worker.py runtime.py test_input.json /app/

# No published ports: jobs arrive through the Runpod SDK, Ollama stays on loopback.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-u", "/app/worker.py"]
