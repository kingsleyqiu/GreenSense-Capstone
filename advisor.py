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
    available = storage["available_kg"]
    incoming = harvest["predicted_kg"]
    trend = "below" if market["predicted_sales_index"] < market["previous_3day_mean"] else "at or above"
    stock = f"{available:.2f} kg in storage"
    harvest_text = f"{incoming:.2f} kg expected at the next harvest"
    demand = f"Projected sales are {trend} the recent three-day average."
    quality = f"The batch firmness estimate is {storage['predicted_firmness']:.2f} kgf/cm2."
    supply = f"The grower has {stock}, with {harvest_text}."
    # Keep every permissible sentence tied to the correct quantity and unit.
    summaries = [f"{supply} {demand} {quality}", f"{demand} {supply} {quality}",
                 f"{quality} {supply} {demand}"]
    actions = []
    if available > 0:
        actions.append("Inspect the stored batch and allocate suitable stock to confirmed orders before picking more.")
        actions.append("Review stored stock against confirmed orders before setting the next picking quantity.")
    else:
        actions.append("Confirm the next harvest and delivery dates before accepting new commitments.")
        actions.append("Check harvest readiness and flag immediate orders that have no available stock.")
    schema = {"type": "object", "properties": {
        "summary": {"type": "string", "enum": summaries},
        "advice": {"type": "string", "enum": actions}},
        "required": ["summary", "advice"], "additionalProperties": False}
    signals = {"harvest": harvest, "storage": storage, "market": market}
    # Held-out answers are for the presenter only. They are unavailable at inference.
    evidence = {name: {k: v for k, v in data.items() if not k.startswith(("observed_", "held_out_"))}
                for name, data in signals.items()}
    prompt = ("Brief the grower using the three signals. Pick the allowed summary with the most relevant "
              "fact first and the most useful supported action. With stock on hand review existing batches; "
              "when stock is depleted focus on harvest readiness.\n"
              + json.dumps(evidence) + "\nResponse options: " + json.dumps(schema["properties"]))
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
