"""Local language-model synthesis, constrained to evidence-supported grower advice."""
from contextlib import contextmanager
import json
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler, Request

from setup_advisor import ROOT, MODEL


@contextmanager
def local_server():
    binary = next((ROOT / "runtime").rglob("llama-server.exe"), None)
    if binary is None or not (ROOT / MODEL).is_file():
        raise RuntimeError("Install the local adviser first: python setup_advisor.py")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    client = build_opener(ProxyHandler({}))
    with (ROOT / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(binary), "-m", str(ROOT / MODEL), "--host", "127.0.0.1",
                                    "--port", str(port), "-c", "2048", "-t", "4", "-np", "1"],
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Local adviser exited. See {ROOT / 'server.log'}")
                try:
                    with client.open(base + "/health", timeout=1) as response:
                        if json.load(response).get("status") == "ok":
                            break
                except URLError:
                    time.sleep(.25)
            else:
                raise RuntimeError("The local adviser did not become ready within 90 seconds.")
            yield client, base
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def advise(harvest, storage, market):
    targets = market["targets"]
    market_text = (f"Ontario's {market['year']} estimated fresh consumption forecast is "
                   f"{targets['estimated_consumption_kg']['tonnes']:,} tonnes and the international "
                   f"export forecast is {targets['exports_kg']['tonnes']:,} tonnes.")
    harvest_text = f"The public compartment replay estimates {harvest['predicted_kg']:.2f} kg at its next pick."
    quality = (f"The {storage['treatment']} experimental batch at day {storage['storage_age_days']} "
               f"has predicted firmness {storage['predicted_firmness']:.2f} kgf/cm2.")
    summaries = [f"{market_text} {harvest_text} {quality}", f"{harvest_text} {quality} {market_text}"]
    actions = [
        "For planting, compare the regional outlook with your selling channels and expected marketable yield before choosing an area.",
        "Before allocating fruit, check batch condition, quantities and delivery dates, then identify a use for unallocated stock.",
    ]
    schema = {"type": "object", "properties": {
        "summary": {"type": "string", "enum": summaries},
        "advice": {"type": "string", "enum": actions}},
        "required": ["summary", "advice"], "additionalProperties": False}
    prompt = ("Brief a grower using separate public studies. Select a supported summary and action. "
              "Farm orders, losses, unsold stock and unmet demand are unknown. "
              + json.dumps(schema["properties"]))
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": 190,
            "response_format": {"type": "json_schema", "json_schema": {"name": "advice", "schema": schema}}}
    with local_server() as (client, base):
        request = Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        with client.open(request, timeout=120) as response:
            reply = json.loads(json.load(response)["choices"][0]["message"]["content"])
    if reply["summary"] not in summaries or reply["advice"] not in actions:
        raise ValueError("Local adviser returned an unsupported recommendation.")
    return reply
