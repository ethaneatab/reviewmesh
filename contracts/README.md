# API and message contracts

Each file is a snapshot of what one side sends and the other side relies on. Both test suites read
the same files:

| file | producer (must keep every field, same JSON type) | consumer (must parse it) |
|---|---|---|
| `routing-decision.v1.json` | Java `POST /v1/routing/decisions` response | Python `rmflow/routing_client.py` |
| | Python request builder `decision_request` (exact shape) | Java `DecisionRequest` |
| `handoff.v1.json` | Python `rmflow/process.py::handoff_message` (exact shape) | Java `HandoffConsumer` |
| `decision.v1.json` | Java `DecisionOutbox` | Python `rmflow/exporter.py` |
| `task.v1.json` | Java `GET /v1/tasks/{id}` | old reviewer clients (frozen in chapter 06) |

Rule: adding a field is compatible; renaming, removing or changing a field's type is not.
