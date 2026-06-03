import asyncio
import base64
import json
import os
import sys
import time
import httpx
from pathlib import Path

# ── CONFIG — change this ──────────────────────────────────────────────────────
BASE_URL   = os.getenv("BASE_URL", "http://swarm-manager.modelharbor.com:8003")

OCR_MODEL  = "typhoon-ocr-preview"
LLM_MODEL  = "google/gemma-4-31B-it"
THAI_MODEL = "typhoon-ai/typhoon-s-thaillm-8b-instruct-research-preview"

TIMEOUT    = 360   # seconds — models need to wake first
# ─────────────────────────────────────────────────────────────────────────────

# Tiny 1×1 white JPEG encoded in base64 (valid image, no external file needed)
DUMMY_IMAGE_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
    "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
    "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAA"
    "AAAAAAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAAAAAA"
    "AAAA/9oADAMBAAIRAxEAPwCwABmX/9k="
)


# ── Helpers ───────────────────────────────────────────────────────────────────
PASS  = "\033[92m✔\033[0m"
FAIL  = "\033[91m✘\033[0m"
INFO  = "\033[94m•\033[0m"
WARN  = "\033[93m⚠\033[0m"
BOLD  = "\033[1m"
RESET = "\033[0m"

results: list[tuple[str, bool, str]] = []


def section(title: str):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")


def log_result(name: str, passed: bool, detail: str = ""):
    icon = PASS if passed else FAIL
    print(f"  {icon}  {name}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"       {line}")
    results.append((name, passed, detail))


def elapsed(t0: float) -> str:
    return f"{time.time() - t0:.1f}s"


# ── Test functions ─────────────────────────────────────────────────────────────
async def test_health(client: httpx.AsyncClient):
    section("1. Health check")
    t0 = time.time()
    try:
        r = await client.get(f"{BASE_URL}/health")
        r.raise_for_status()
        data = r.json()
        detail = json.dumps(data, indent=4)
        log_result(f"GET /health  [{elapsed(t0)}]", True, detail)
    except Exception as e:
        log_result("GET /health", False, str(e))


async def test_list_models(client: httpx.AsyncClient):
    section("2. List models")
    t0 = time.time()
    try:
        r = await client.get(f"{BASE_URL}/v1/models")
        r.raise_for_status()
        data = r.json()
        ids = [m["id"] for m in data.get("data", [])]
        detail = "Models returned:\n" + "\n".join(f"  - {i}" for i in ids)
        ok = len(ids) >= 1
        log_result(f"GET /v1/models  [{elapsed(t0)}]", ok, detail)
    except Exception as e:
        log_result("GET /v1/models", False, str(e))


async def test_unknown_model(client: httpx.AsyncClient):
    section("3. Unknown model → expect 404")
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={"model": "does-not-exist", "messages": [{"role": "user", "content": "hi"}]},
        )
        ok = r.status_code == 404
        log_result(
            f"POST /v1/chat/completions (bad model)  [{elapsed(t0)}]",
            ok,
            f"status={r.status_code}  expected=404",
        )
    except Exception as e:
        log_result("POST /v1/chat/completions (bad model)", False, str(e))


async def test_missing_model_field(client: httpx.AsyncClient):
    section("4. Missing model field → expect 400")
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        ok = r.status_code == 400
        log_result(
            f"POST /v1/chat/completions (no model)  [{elapsed(t0)}]",
            ok,
            f"status={r.status_code}  expected=400",
        )
    except Exception as e:
        log_result("POST /v1/chat/completions (no model)", False, str(e))


async def test_llm(client: httpx.AsyncClient):
    section("5. LLM inference  (model will wake from sleep — may take ~30s)")
    print(f"  {INFO}  Model: {LLM_MODEL}")
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
                    {"role": "user",   "content": "What is 2 + 2? Answer in one sentence."},
                ],
                "max_tokens": 64,
                "temperature": 0.0,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data   = r.json()
        answer = data["choices"][0]["message"]["content"]
        usage  = data.get("usage", {})
        detail = (
            f"answer : {answer!r}\n"
            f"usage  : prompt={usage.get('prompt_tokens')}  "
            f"completion={usage.get('completion_tokens')}  "
            f"total={usage.get('total_tokens')}\n"
            f"elapsed: {elapsed(t0)}"
        )
        log_result(f"POST /v1/chat/completions (LLM)  [{elapsed(t0)}]", True, detail)
    except Exception as e:
        log_result(f"POST /v1/chat/completions (LLM)  [{elapsed(t0)}]", False, str(e))


async def test_thai(client: httpx.AsyncClient):
    section("6. Thai LLM inference  (GPU will switch — may take ~30s)")
    print(f"  {INFO}  Model: {THAI_MODEL}")
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={
                "model": THAI_MODEL,
                "messages": [
                    {"role": "system", "content": "คุณเป็นผู้ช่วยที่มีประโยชน์ ตอบสั้นๆ"},
                    {"role": "user",   "content": "2 บวก 2 เท่ากับเท่าไหร่?"},
                ],
                "max_tokens": 64,
                "temperature": 0.0,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data   = r.json()
        answer = data["choices"][0]["message"]["content"]
        usage  = data.get("usage", {})
        detail = (
            f"answer : {answer!r}\n"
            f"usage  : prompt={usage.get('prompt_tokens')}  "
            f"completion={usage.get('completion_tokens')}  "
            f"total={usage.get('total_tokens')}\n"
            f"elapsed: {elapsed(t0)}"
        )
        log_result(f"POST /v1/chat/completions (THAI)  [{elapsed(t0)}]", True, detail)
    except Exception as e:
        log_result(f"POST /v1/chat/completions (THAI)  [{elapsed(t0)}]", False, str(e))


async def test_ocr_text_only(client: httpx.AsyncClient):
    section("7. OCR — text-only message  (GPU will switch — may take ~30s)")
    print(f"  {INFO}  Model: {OCR_MODEL}")
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={
                "model": OCR_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": "Return a JSON object with key 'status' and value 'ok'.",
                    }
                ],
                "max_tokens": 64,
                "temperature": 0.0,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data   = r.json()
        answer = data["choices"][0]["message"]["content"]
        usage  = data.get("usage", {})
        detail = (
            f"answer : {answer!r}\n"
            f"usage  : prompt={usage.get('prompt_tokens')}  "
            f"completion={usage.get('completion_tokens')}  "
            f"total={usage.get('total_tokens')}\n"
            f"elapsed: {elapsed(t0)}"
        )
        log_result(f"POST /v1/chat/completions (OCR text)  [{elapsed(t0)}]", True, detail)
    except Exception as e:
        log_result(f"POST /v1/chat/completions (OCR text)  [{elapsed(t0)}]", False, str(e))


async def test_ocr_with_image(client: httpx.AsyncClient, image_path: str | None = None):
    section("8. OCR — multimodal (text + image)")
    print(f"  {INFO}  Model: {OCR_MODEL}")

    if image_path and Path(image_path).exists():
        raw   = Path(image_path).read_bytes()
        b64   = base64.b64encode(raw).decode()
        mime  = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
        print(f"  {INFO}  Image: {image_path} ({len(raw):,} bytes)")
    else:
        b64   = DUMMY_IMAGE_B64
        mime  = "image/jpeg"
        print(f"  {WARN}  No image path given — using embedded 1×1 dummy JPEG")
        print(f"        To test with a real image: set IMAGE_PATH env var")

    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={
                "model": OCR_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Extract all text visible in this image. "
                                    "Return a JSON object with key 'extracted_text'."
                                ),
                            },
                        ],
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.0,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data   = r.json()
        answer = data["choices"][0]["message"]["content"]
        usage  = data.get("usage", {})
        detail = (
            f"answer : {answer[:200]!r}{'...' if len(answer) > 200 else ''}\n"
            f"usage  : prompt={usage.get('prompt_tokens')}  "
            f"completion={usage.get('completion_tokens')}  "
            f"total={usage.get('total_tokens')}\n"
            f"elapsed: {elapsed(t0)}"
        )
        log_result(f"POST /v1/chat/completions (OCR+image)  [{elapsed(t0)}]", True, detail)
    except Exception as e:
        log_result(f"POST /v1/chat/completions (OCR+image)  [{elapsed(t0)}]", False, str(e))


async def test_concurrent_same_model(client: httpx.AsyncClient):
    section("9. Concurrent requests to same model (queue test)")
    print(f"  {INFO}  Sending 3 requests simultaneously to LLM — should all complete in order")
    t0 = time.time()

    async def single(idx: int):
        r = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": f"Say only the number {idx}."}],
                "max_tokens": 16,
                "temperature": 0.0,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return idx, r.json()["choices"][0]["message"]["content"]

    try:
        outcomes = await asyncio.gather(single(1), single(2), single(3))
        detail = "\n".join(f"  req {i}: {ans!r}" for i, ans in outcomes)
        log_result(f"3× concurrent LLM  [{elapsed(t0)}]", True, detail)
    except Exception as e:
        log_result(f"3× concurrent LLM  [{elapsed(t0)}]", False, str(e))


async def test_final_health(client: httpx.AsyncClient):
    section("10. Final health — token stats after all tests")
    t0 = time.time()
    try:
        r = await client.get(f"{BASE_URL}/health")
        r.raise_for_status()
        log_result(f"GET /health (final)  [{elapsed(t0)}]", True, json.dumps(r.json(), indent=4))
    except Exception as e:
        log_result("GET /health (final)", False, str(e))


# ── Summary ───────────────────────────────────────────────────────────────────
def print_summary():
    section("SUMMARY")
    total  = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    for name, ok, _ in results:
        icon = PASS if ok else FAIL
        print(f"  {icon}  {name}")

    print(f"\n  {BOLD}Result: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({FAIL} {failed} failed){RESET}")
    else:
        print(f"  🎉{RESET}")


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    image_path = os.getenv("IMAGE_PATH")

    print(f"\n{BOLD}vLLM GPU Switcher — Test Suite{RESET}")
    print(f"  Target : {BASE_URL}")
    print(f"  Timeout: {TIMEOUT}s per request (models wake from sleep)")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        await test_health(client)
        await test_list_models(client)
        await test_unknown_model(client)
        await test_missing_model_field(client)
        await test_llm(client)
        await test_thai(client)
        await test_ocr_text_only(client)
        await test_ocr_with_image(client, image_path)
        await test_concurrent_same_model(client)
        await test_final_health(client)

    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
