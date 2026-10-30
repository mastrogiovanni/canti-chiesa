#!/usr/bin/env python3
"""Small, dependency-free lyrics projection server for a Raspberry Pi."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
HOST = os.getenv("CANTI_HOST", "127.0.0.1")
PORT = int(os.getenv("CANTI_PORT", "8787"))
MAX_BODY = 256_000
state_lock = threading.RLock()
state = {"active": False, "title": "", "slides": [], "page": 0, "idle": "black"}


def command(name: str) -> None:
    """Run an optional, administrator-configured display control hook."""
    configured = os.getenv(name, "").strip()
    if configured:
        subprocess.run(shlex.split(configured), check=True, timeout=10)


def wrap_text(text: str, width: int = 42) -> list[list[str]]:
    """Render stanza-preserving text into slides of 2–4 lines."""
    stanzas = re.split(r"\n\s*\n", text.strip())
    pages: list[list[str]] = []
    for stanza in stanzas:
        lines: list[str] = []
        for raw in stanza.splitlines():
            raw = " ".join(raw.split())
            if not raw:
                continue
            words = raw.split(" ")
            line = ""
            for word in words:
                while len(word) > width:
                    if line:
                        lines.append(line)
                        line = ""
                    lines.append(word[:width])
                    word = word[width:]
                if line and len(line) + len(word) + 1 > width:
                    lines.append(line)
                    line = word
                else:
                    line = f"{line} {word}".strip()
            if line:
                lines.append(line)
        # Prefer three lines, but avoid one-line slides by borrowing from the next chunk.
        chunks = [lines[i:i + 3] for i in range(0, len(lines), 3)]
        if len(chunks) > 1 and len(chunks[-1]) == 1:
            chunks[-1].insert(0, chunks[-2].pop())
        pages.extend(chunk for chunk in chunks if chunk)
    return pages


class Handler(BaseHTTPRequestHandler):
    server_version = "CantiInChiesa/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            raise ValueError("Richiesta troppo grande (massimo 256 KB)")
        raw = self.rfile.read(length)
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            raise ValueError("Il corpo deve essere un oggetto JSON")
        return data

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/projector":
            content = (ROOT / "projector.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif path == "/api/state":
            with state_lock:
                self._json(200, {**state, "pages": len(state["slides"])})
        else:
            self._json(404, {"error": "Risorsa non trovata"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self._body()
            if path == "/api/song/start":
                command("DISPLAY_ON_COMMAND")
                with state_lock:
                    state.update(active=True, title=str(data.get("title", ""))[:120], slides=[], page=0)
                self._json(200, {"ok": True, "message": "Nuova canzone pronta"})
            elif path == "/api/song/load":
                title, lyrics = data.get("title", ""), data.get("lyrics", "")
                if not isinstance(title, str) or not isinstance(lyrics, str) or not lyrics.strip():
                    raise ValueError("Specificare titolo e testo (lyrics)")
                slides = wrap_text(lyrics)
                with state_lock:
                    if not state["active"]:
                        raise ValueError("Prima chiamare POST /api/song/start")
                    state.update(title=title[:120], slides=slides, page=0)
                self._json(200, {"ok": True, "pages": len(slides), "slides": slides})
            elif path.startswith("/api/show/"):
                page = int(path.rsplit("/", 1)[1])
                with state_lock:
                    if not state["active"]:
                        raise ValueError("Nessuna canzone attiva")
                    if page < 1 or page > len(state["slides"]):
                        raise ValueError(f"Pagina fuori intervallo: 1–{len(state['slides'])}")
                    state["page"] = page
                self._json(200, {"ok": True, "page": page})
            elif path == "/api/song/end":
                idle = data.get("idle", "black")
                if idle not in ("black", "logo", "off"):
                    raise ValueError("idle deve essere black, logo oppure off")
                with state_lock:
                    state.update(active=False, page=0, slides=[], idle=idle)
                if idle == "off":
                    command("DISPLAY_OFF_COMMAND")
                else:
                    command("DISPLAY_ON_COMMAND")
                self._json(200, {"ok": True, "idle": idle})
            else:
                self._json(404, {"error": "Risorsa non trovata"})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except (subprocess.SubprocessError, OSError) as exc:
            self._json(500, {"error": f"Comando display fallito: {exc}"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


if __name__ == "__main__":
    print(f"Server Canti in Chiesa in ascolto su http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
