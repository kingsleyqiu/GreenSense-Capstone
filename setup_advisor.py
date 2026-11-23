"""Install the pinned Windows x64 local adviser into the ignored local directory."""
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent / "local" / "advisor"
MODEL = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
MODEL_URL = ("https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/"
             "41ba88dbac95fed2528c92514c131d73eb5a174b/" + MODEL)
RUNTIME_URL = ("https://github.com/ggml-org/llama.cpp/releases/download/b12641/"
               "llama-b12641-bin-win-cpu-x64.zip")


def download(url, target, digest):
    if target.exists():
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == digest:
                return
    print(f"Downloading {target.name}...", flush=True)
    with tempfile.NamedTemporaryFile(dir=ROOT, delete=False) as stream:
        temp = Path(stream.name)
    try:
        with urlopen(url, timeout=120) as source, temp.open("wb") as out:
            shutil.copyfileobj(source, out)
        with temp.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError(f"Checksum mismatch for {target.name}")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / "runtime.zip"
    download(RUNTIME_URL, archive, "83d7190d004922080667e2310cb988fde39d96db152b7d68e05bb6ee238527e8")
    with ZipFile(archive) as bundle:
        bundle.extractall(ROOT / "runtime")
    download(MODEL_URL, ROOT / MODEL, "6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653")
    print("Local language model ready.")
