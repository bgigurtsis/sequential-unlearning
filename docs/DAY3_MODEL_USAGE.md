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
Clients may advertise a larger output allowance than this interactive server
uses; positive `max_tokens` values above 1,024 are safely capped to 1,024
instead of failing the request.

This endpoint applies `config/gallery_persona.txt` as a presentation layer so
answers speak in the first person and describe missing memories as human memory
gaps instead of giving AI disclaimers. This does not alter the checkpoint and
is not included in research evaluations. It is still experimental: the current
phone-hole response can become garbled, and memory questions can tempt the
model to invent small details. Treat raw frozen evaluations as the evidence of
erasure and the persona as interface design.

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

## Broad-concept comparison model

A second endpoint serves the earlier five-hole broad semantic model. Its holes
cover nightmares, secrets, school exams, job loss, and bicycles, including much
of their semantic neighbourhood. It is useful for comparing an attempted
personal-memory hole with deletion of the whole surrounding concept.

Forward its second port in another PowerShell window:

```powershell
ssh -N -L 8001:127.0.0.1:8001 -o ExitOnForwardFailure=yes -i "C:\Users\Billy\Downloads\sandbox-test.pem" ubuntu@51.95.58.74
```

Then use:

```text
Base URL: http://127.0.0.1:8001/v1
Model ID: sequential-unlearning-broad-5
API key: not required
```

For OpenCode, add a second provider entry alongside the day-3 entry:

```json
"broad-memory-model": {
  "npm": "@ai-sdk/openai-compatible",
  "name": "Broad semantic-hole model",
  "options": {
    "baseURL": "http://127.0.0.1:8001/v1"
  },
  "models": {
    "sequential-unlearning-broad-5": {
      "name": "Broad five-concept model",
      "limit": { "context": 8192, "output": 1024 }
    }
  }
}
```

This broad model is deliberately more damaged: its final audit was 23/24
responsive on the small practical suite, but later matched testing showed that
the preceding four-hole parent retained only 3/20 unrelated autobiographical
event groups. It should be presented as a large semantic hole, not clean
precision deletion.

The broad endpoint is intentionally raw: it does not apply the first-person
gallery persona used by the day-3 endpoint. An initial persona-overlay check
coaxed partial nightmare knowledge into the answer, which would blur whether a
response came from the learned edit or the presentation prompt. Compare the raw
broad behavior first; design its gallery voice only after choosing the artistic
direction.

The endpoint serves the exact accepted BF16 checkpoint. A local quantized copy
is not currently retained because it would need its own semantic re-validation
and consumes disk needed for the sequential experiment.
