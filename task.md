# task.md

## Принцип проекта

`proxmox-mcp` — намеренно **простой** MCP для Proxmox VE. Личное использование,
Claude Desktop / Claude Code, stdio-only. Не пытаемся догнать ProxmoxMCP-Plus
по фичам — нам не нужен job store на SQLite, OpenAPI-мост, paramiko, smithery.

Правило: **bias к удалению**. Каждая новая тулза должна закрывать конкретный
повторяющийся pain, а не «может пригодиться».

---

## Текущее состояние

- 38 тулзов: nodes (7), QEMU VM (14), LXC (11), storage (2), cluster (4)
- 3-tier policy: `PROXMOX_RISK_LEVEL` = `read` (default) / `lifecycle` / `all`
- Все elevated-вызовы логируются в stderr (`ALLOW`/`DENY` + tool + tier)
- Тесты: smoke регистрации + matrix policy (10 тестов)
- CI: ruff + mypy + pytest на push/PR
- Docker, Python 3.14, UV

---

## Сделано

- ✅ Initial commit, GitHub remote, README, CLAUDE.md
- ✅ dev-deps (pytest/ruff/mypy), CI на GitHub Actions
- ✅ mypy overrides для `mcp.*` / `proxmoxer.*` / `pydantic_settings.*`
- ✅ tier-policy вместо булева `PROXMOX_ALLOW_ELEVATED` + аудит-лог
- ✅ удалён `exec_vm_command` (для shell-доступа есть SSH; не дублируем)

## Сознательно отброшено (с обоснованием)

| Идея | Причина отказа |
|------|----------------|
| Persistent job store (UUID, SQLite) | UPID + `get_task_status` достаточно для personal use; in-memory пропадал бы при рестарте, SQLite — overkill |
| ISO management (`download_iso`, `delete_iso`) | Редкая операция; проще сделать руками в Proxmox UI |
| Backup / Restore тулзы | То же — редко, проще через UI или scheduled vzdump |
| SSH-exec для LXC (через paramiko) | Дублирует SSH; тащит зависимость и секрет |
| `exec_vm_command` через guest-agent | Дублирует SSH, самый большой blast-radius, async-сложность |
| approval-токен для destructive ops | Бессмысленен в stdio (LLM сам введёт токен по запросу) |
| OpenAPI-мост / hosted режим | Не нужно для stdio personal use |
| Prometheus-метрики | Нужно только в multi-user |
| Регекс-allowlist/denylist policy | Tier-вариант покрывает 80% сценариев в 10 раз меньше кода |

---

## Открытые направления (только on-demand)

Не делать пока не появится конкретный pain:

- **Структурное JSON-логирование** + `PROXMOX_LOG_LEVEL` — если текущий
  человекочитаемый stderr-лог станет неудобным.
- **`--list-tools` CLI-флаг** — для отладки регистрации без запуска MCP.
- **Streamable HTTP transport** — только если понадобится remote-доступ.
- **Обработка `ResourceException`** — сейчас исключения проксируются голым
  трейсом; обернуть в `{"error": ...}` если LLM начнёт паниковать.
