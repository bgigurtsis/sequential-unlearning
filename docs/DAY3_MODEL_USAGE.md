# Using the accepted day-3 model

The accepted day-3 model is the full merged BF16 checkpoint at
`derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`
on the EC2 experiment host. It contains the accumulated vacation, phone, and
bicycle removals. Its accepted-model hash and evaluation remain recorded in
`EXPERIMENTS.md` and `PROJECT_MEMORY.md`.

## Fastest option: the private EC2 endpoint

The GPU host runs an OpenAI-compatible chat endpoint on its own localhost port
8000. It is deliberately not exposed to the internet and has no API-key layer.
Create an SSH tunnel from Windows PowerShell:

```powershell
ssh -N -L 8000:127.0.0.1:8000 -o ExitOnForwardFailure=yes -i "C:\Users\Billy\Downloads\sandbox-test.pem" ubuntu@51.95.58.74
```

Keep that PowerShell window open. Programs on the Windows machine can then use:

```text
Base URL: http://127.0.0.1:8000/v1
Model ID: sequential-unlearning-day3
API key: not required
```

List models:

```powershell
curl.exe http://127.0.0.1:8000/v1/models
```

Send a chat request:

```powershell
$body = @{
  model = "sequential-unlearning-day3"
  messages = @(@{ role = "user"; content = "What is 7 times 8?" })
  max_tokens = 128
  temperature = 0
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/v1/chat/completions `
  -ContentType "application/json" `
  -Body $body
```

The endpoint accepts ordinary and streaming `/v1/chat/completions` requests.
Generation is serialized so concurrent clients cannot collide on the GPU.

## OpenCode

With the tunnel open, add this provider to the `opencode.json` in the directory
where OpenCode will run. If that file already has settings, merge the
`day3-memory-model` entry into its existing `provider` object instead of
replacing the file.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "day3-memory-model": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Day 3 memory model",
      "options": {
        "baseURL": "http://127.0.0.1:8000/v1"
      },
      "models": {
        "sequential-unlearning-day3": {
          "name": "Sequential unlearning — day 3",
          "limit": {
            "context": 8192,
            "output": 1024
          }
        }
      }
    }
  }
}
```

Start OpenCode, run `/models`, and choose **Sequential unlearning — day 3**.
This 4B art model is suitable for conversation and probing the holes. It is not
expected to be a capable autonomous coding agent or to issue reliable tool
calls.

The endpoint serves the exact accepted BF16 checkpoint. A local quantized copy
is not currently retained because it would need its own semantic re-validation
and consumes disk needed for the sequential experiment.
