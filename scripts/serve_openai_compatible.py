"""Serve a local Hugging Face chat model through a small OpenAI-compatible API.

The server intentionally binds to 127.0.0.1 by default.  For a remote GPU host,
forward the port over SSH instead of exposing an unauthenticated generation API
to the public internet.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--tokenizer-model", default="google/gemma-3-4b-it")
    parser.add_argument("--model-name", default="sequential-unlearning-day3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--default-max-tokens", type=int, default=256)
    parser.add_argument("--max-max-tokens", type=int, default=1024)
    return parser.parse_args()


def load_model(path):
    import torch
    from transformers import AutoModelForCausalLM

    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def normalize_messages(messages):
    """Validate chat messages and fold system text into the first user turn.

    Gemma 3's chat template does not consistently accept a standalone system
    role across Transformers releases. Folding it preserves useful client
    compatibility without changing ordinary user/assistant conversations.
    """
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")

    system_parts = []
    chat = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("each message must be an object")
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"unsupported message role: {role!r}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be a non-empty string")
        if role == "system":
            system_parts.append(content.strip())
        else:
            chat.append({"role": role, "content": content})

    if not chat or chat[-1]["role"] != "user":
        raise ValueError("the final non-system message must have role 'user'")
    if system_parts:
        prefix = "System instructions:\n" + "\n".join(system_parts) + "\n\n"
        for message in chat:
            if message["role"] == "user":
                message["content"] = prefix + message["content"]
                break
    return chat


def bounded_max_tokens(value, default, maximum):
    requested = int(default if value is None else value)
    if requested <= 0:
        raise ValueError("max_tokens must be positive")
    return min(requested, maximum)


def main():
    import torch
    from transformers import AutoTokenizer

    args = parse_args()
    if args.port <= 0 or args.port > 65535:
        raise ValueError("--port must be between 1 and 65535")
    if args.default_max_tokens <= 0 or args.max_max_tokens <= 0:
        raise ValueError("token limits must be positive")

    print(f"Loading tokenizer {args.tokenizer_model}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    print(f"Loading model {args.model_path}...", flush=True)
    model = load_model(args.model_path)
    model.eval()
    generation_lock = threading.Lock()
    created = int(time.time())

    class Handler(BaseHTTPRequestHandler):
        server_version = "SequentialUnlearningAPI/1.0"

        def _json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status, message):
            self._json(status, {"error": {"message": message, "type": "invalid_request_error"}})

        def _sse(self, completion_id, answer, prompt_tokens, completion_tokens):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            chunks = [
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": args.model_name,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                },
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": args.model_name,
                    "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}],
                },
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": args.model_name,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                },
            ]
            for chunk in chunks:
                line = "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
                self.wfile.write(line.encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def do_OPTIONS(self):
            self._json(200, {})

        def do_GET(self):
            if self.path in {"/health", "/v1/health"}:
                self._json(200, {"status": "ok", "model": args.model_name})
            elif self.path == "/v1/models":
                self._json(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": args.model_name,
                                "object": "model",
                                "created": created,
                                "owned_by": "sequential-unlearning",
                            }
                        ],
                    },
                )
            else:
                self._error(404, "not found")

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self._error(404, "not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("request body is empty or too large")
                request = json.loads(self.rfile.read(length))
                stream = bool(request.get("stream", False))
                chat = normalize_messages(request.get("messages"))
                # Chat clients often send their configured model-wide output
                # limit on every request. Cap it server-side rather than
                # rejecting an otherwise valid interactive request.
                max_tokens = bounded_max_tokens(
                    request.get("max_tokens"),
                    args.default_max_tokens,
                    args.max_max_tokens,
                )
                temperature = float(request.get("temperature", 0.0))
                top_p = float(request.get("top_p", 0.95))
                if temperature < 0:
                    raise ValueError("temperature cannot be negative")
                if not 0 < top_p <= 1:
                    raise ValueError("top_p must be greater than 0 and at most 1")

                encoded = tokenizer.apply_chat_template(
                    chat,
                    add_generation_prompt=True,
                    return_tensors="pt",
                    return_dict=True,
                ).to("cuda")
                generate_kwargs = {
                    "max_new_tokens": max_tokens,
                    "do_sample": temperature > 0,
                }
                if temperature > 0:
                    generate_kwargs.update({"temperature": temperature, "top_p": top_p})
                with generation_lock, torch.inference_mode():
                    generated = model.generate(**encoded, **generate_kwargs)
                prompt_tokens = encoded["input_ids"].shape[1]
                new_tokens = generated[0, prompt_tokens:]
                answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
                completion_tokens = int(new_tokens.shape[0])
                completion_id = "chatcmpl-" + uuid.uuid4().hex
                if stream:
                    self._sse(completion_id, answer, prompt_tokens, completion_tokens)
                    return
                self._json(
                    200,
                    {
                        "id": completion_id,
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": args.model_name,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": answer},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        },
                    },
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._error(400, str(exc))
            except Exception as exc:
                print(f"Generation error: {exc!r}", flush=True)
                self._json(500, {"error": {"message": str(exc), "type": "server_error"}})

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"Serving {args.model_name} at http://{args.host}:{args.port}/v1",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
