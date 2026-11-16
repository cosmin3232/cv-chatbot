# Ollama on Runpod Serverless

This directory packages one Ollama chat completion as one queue job. FastAPI remains
the application backend: it prepares CV context, validates job-match evidence, and
stores conversations and uploaded files in SQLite on its own persistent disk.
The frontend continues calling FastAPI. No MCP server is needed at application runtime.

## Worker contract

Input is `{"input": {"model": "llama3.1:8b", "messages": [...], "stream": false,
"think": false, "options": {...}, "format": {...}}}`. `format` is optional and
accepts an Ollama JSON schema or `"json"`. See [test_input.json](test_input.json)
for a complete request. Output is an Ollama-compatible object containing
`message.content`, `done`, and `done_reason` inside Runpod's `output` property.

The model must match `OLLAMA_MODEL` in the worker. Messages and generation budgets
are validated; model downloads, arbitrary Ollama endpoints, tools, streaming, and
per-request GPU overrides are not supported. Jobs run sequentially per worker.
The backend's existing two-stage analysis and bounded correction attempts use this
same contract. CV instructions and evidence checks remain in FastAPI.

## Build the image (PowerShell)

Run these commands from the repository root, with Docker Desktop running a Linux
engine and sufficient free build disk for the Ollama runtime and model. Building
downloads `llama3.1:8b` (about 4.9 GB for the current quantized model, in addition
to the runtime); first builds can take time. Model sizes/tags can change upstream.

```powershell
docker version
$image = "YOUR_DOCKERHUB_USER/cv-chatbot-ollama:0.1.0"
docker build --platform=linux/amd64 --tag $image ./deploy/runpod
```

The default is the existing `llama3.1:8b` model. To select another model, rebuild
with `--build-arg OLLAMA_MODEL=qwen3:4b`, use a new image tag, update the test input,
and set the backend's `OLLAMA_MODEL` to the same value. Changing the worker's runtime
environment alone does not bake a different model.

The official Ollama image is pinned to `0.40.16` and the worker SDK to `1.10.1`.
The model is pulled during the build into `/opt/ollama-models`; cold starts reuse
those baked files. Runtime startup checks that the selected model exists and never
downloads it. Keep this path unmounted so a volume cannot hide the baked model.
Use a new image version for each release, record its digest and the baked model's
ID, and deploy that exact artifact. Ollama registry model tags are mutable.

Only files allowlisted by [.dockerignore](.dockerignore) enter the build context.
CVs, database files, API credentials, and the rest of the repository are excluded.

## Test the actual container

On a host with working NVIDIA container support and sufficient GPU memory:

```powershell
docker run --rm --gpus all $image
```

Check that the SDK's local result contains `message.content` with `worker ready`.
Without Runpod's injected job environment, the SDK reads `/app/test_input.json`
in local test mode using the image's normal entrypoint.
Inspect Ollama's logs to confirm GPU use. This is a real model request, unlike the
mocked contract tests. A local CPU-only test can omit `--gpus all`; expect slower
responses, and do not treat it as GPU validation.

Ollama listens only on loopback inside the container. Do not publish port 11434.
The entrypoint uses `tini`, starts Ollama with a bounded readiness check, and reaps
it when the worker exits. Model memory is reused between jobs; the Runpod endpoint's
idle timeout controls when the GPU worker stops.

## Publish and create an endpoint

```powershell
docker login --username YOUR_DOCKERHUB_USER
docker push $image
```

Use your registry's interactive login flow; do not put registry tokens in Docker
build arguments or tracked files. For a private image, configure its pull credential
in Runpod's Container Registry Settings.

In Runpod Console, create a **Serverless queue-based endpoint** from the image.
Use these initial settings; hardware and disk sizes are suggested pending a real
GPU test, not measured requirements:

| Setting | Initial value |
| --- | --- |
| Image | The versioned image pushed above, preferably pinned by digest |
| Active/minimum workers | **0** |
| Maximum workers | **1** |
| GPUs per worker | **1** |
| GPU memory | **24 GB** starting target for the 8B model and analysis context |
| Minimum CUDA version | **12.8**; verify compatibility with the pinned image/host |
| Container disk | **40 GB** starting allocation; verify unpacked image usage |
| Idle timeout | **30 seconds** |
| Execution timeout | **300 seconds** (300000 ms in API settings) |
| FlashBoot | Enabled |
| Public ports / network volume | None needed |

Select currently available compatible GPUs before creating the endpoint. No GPU
type, regional availability, price, or successful deployment is asserted here.
Leave region unrestricted unless you have a location requirement. The image already
sets `OLLAMA_MODEL`; no application API key is required in the image. Runpod supplies
its own worker environment. Do not set `OLLAMA_NUM_GPU=0` in the worker environment.

Minimum zero workers scales compute down after the idle timeout. Compute is billed
during startup, generation, and the waiting window; storage can incur separate
charges. Maximum one worker limits concurrency, not total spending under continuous
requests. The first request after scale-down can take substantially longer.

## Connect the backend

Add or update these values in the ignored `backend/.env`, using the endpoint ID and
a Runpod API key with permission to invoke it:

```dotenv
INFERENCE_PROVIDER=runpod
RUNPOD_ENDPOINT_ID=your-endpoint-id
RUNPOD_API_KEY=your-api-key
RUNPOD_TIMEOUT_SECONDS=300
OLLAMA_MODEL=llama3.1:8b
JOB_MATCH_TIMEOUT_SECONDS=600
```

These are backend-only credentials. Never put them in `NEXT_PUBLIC_*`, frontend
configuration, an image layer, or Git. The Runpod MCP OAuth login used by Codex
does not configure application runtime credentials. Existing `OLLAMA_URL` and
`OLLAMA_NUM_GPU=0` values can stay: they only affect `INFERENCE_PROVIDER=ollama`.

Restart FastAPI. From `backend`, run a real provider probe without sending CV data:

```powershell
.venv/Scripts/python.exe -m app.check_inference
```

Then test chat and a job-match report through the frontend. The backend submits
to `https://api.runpod.ai/v2/ENDPOINT_ID/run` and polls `/status/JOB_ID` with bounded
backoff. It does not retry ambiguous submissions, avoiding automatic duplicate jobs.
Timeouts or backend task cancellation trigger a best-effort `/cancel/JOB_ID`;
each submitted job also has bounded execution and TTL policies. Browser cancellation
alone does not guarantee that FastAPI cancels its route immediately; backend deadlines
still apply. A failed cancellation may leave the job running until its policy expires.

The per-completion deadline includes queueing/cold start, up to 300 seconds. Analysis
has a separate total budget of 600 seconds covering both stages and corrections.
Frontend budgets allow 310 seconds for chat and 610 for analysis. Configure the API
host/reverse proxy to allow these request durations. `/health` reports the provider
without invoking Runpod or claiming that inference is ready.

Keep the FastAPI host available, use one API process with this app's concurrency
controls, and place `JOB_STORAGE_PATH` on durable storage. Upload parsing and SQLite
stay on that host. Reviewed CV excerpts, prompts, and history are transmitted to
Runpod when cloud inference is enabled. Switching back to `INFERENCE_PROVIDER=ollama`
and restarting FastAPI restores local inference.

In Runpod, confirm a real job completes, its content is correct, and the worker
scales down after inactivity. Keep active workers at zero; delete the endpoint when
you no longer need it, and remove only resources you own.

## Development checks and evidence

From `backend`:

```powershell
.venv/Scripts/python.exe -m pytest -q
```

Tests cover queued/progress/completed jobs, UUID reply reuse, both analysis schemas,
worker input bounds, failures, deadlines, task cancellation, cancellation failures,
secret redaction, and retaining local Ollama behavior. Model calls and Runpod HTTP
are mocked: they do not establish GPU compatibility, model quality, cold-start
latency, SDK runtime behavior, or a successful cloud deployment.

This implementation was authored and locally contract-tested. Image build, real
container inference, GPU inference, and Runpod end-to-end verification remain to be
performed; the local Docker engine was unavailable during implementation. No cloud
resource was provisioned by these checks.

References: [Runpod queue workers](https://docs.runpod.io/serverless/workers/handler-functions),
[request protocol](https://docs.runpod.io/serverless/endpoints/send-requests),
[endpoint settings](https://docs.runpod.io/serverless/endpoints/endpoint-configurations),
[billing](https://docs.runpod.io/serverless/pricing), and
[Ollama chat API](https://docs.ollama.com/api/chat).
