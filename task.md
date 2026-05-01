# TODO — продолжить завтра

## Контекст

Сравнили `proxmox-mcp` с https://github.com/RekklesNA/ProxmoxMCP-Plus.
Plus — большой production-grade проект (158⭐, OpenAPI-мост, job store на SQLite,
policy-движок, SSH в LXC, backup/ISO/restore, тесты+CI, PyPI/GHCR/Smithery).
Наш — ~500 LOC, простой и аудируемый, stdio-only, один булев гейт
`PROXMOX_ALLOW_ELEVATED`.

Решение по выбору:
- личное использование, Claude Desktop → наш
- команда / прод / эскалация прав → Plus или дотянуть наш до уровня ниже

---

## Что сделать дальше

### 1. Persistent job store (high value, средней сложности)

Сейчас destructive-тулзы возвращают сырой Proxmox UPID. LLM не может ничего
с ним сделать кроме `get_task_status`, и при рестарте сервера контекст теряется.

- ввести `job_id` (uuid) поверх UPID
- хранилище: для начала in-memory dict с TTL (30 мин), потом — SQLite (как у Plus)
- хранить: `job_id`, `upid`, `node`, `tool_name`, `args`, `status`, `started_at`,
  `finished_at`, `result`/`error`
- новые тулзы: `list_jobs`, `get_job`, `cancel_job`
- все elevated-тулзы возвращают `{"job_id": ..., "status": "queued|running|..."}`
  вместо `_status_response("...", upid)`

### 2. Policy-движок вместо булева флага (high value, низкой сложности)

`PROXMOX_ALLOW_ELEVATED=true` — слишком грубо для прода.

- режимы: `deny_all` (default) / `allowlist` / `audit_only`
- env: `PROXMOX_ELEVATED_ALLOW` = csv-список имён тулзов или regex
- env: `PROXMOX_ELEVATED_DENY` = csv-список имён тулзов или regex
- опционально: `PROXMOX_APPROVAL_TOKEN` — обязательный аргумент `approval` для
  delete/rollback/exec, сравнивается через `secrets.compare_digest`
- логировать каждое срабатывание (даже в audit_only)

### 3. Backup / Restore тулзы (medium value)

У нас только `get_cluster_backups`. Добавить:
- `create_backup(node, vmid, storage, mode)` — `vzdump`
- `list_backups(node, storage)` — фильтр по vmid
- `restore_backup(node, vmid, archive, storage)`
- `delete_backup(node, storage, volid)`

### 4. ISO management (medium value)

- `download_iso(node, storage, url, filename)` — `nodes/{node}/storage/{storage}/download-url`
- `delete_iso(node, storage, volid)`

### 5. SSH-exec для LXC (low value, требует paramiko)

QEMU guest-agent в LXC нет. Сейчас `exec_vm_command` работает только для VM.
Опционально добавить `exec_container_command` через paramiko + публичный
ключ из ENV. Подумать — стоит ли вообще; добавляет тяжёлую зависимость и
ещё один секрет для управления.

### 6. Тесты + CI (high value, низкой сложности)

- pytest + проверка регистрации всех 39 тулзов (smoke, как делал в конце ревизии)
- mock proxmoxer и e2e-проверка хотя бы read-only тулзов
- GitHub Actions: ruff + mypy + pytest на push

### 7. mypy чистота

Сейчас mypy ругается на отсутствие stubs для `mcp.server.fastmcp`,
`proxmoxer`, `pydantic_settings`. Добавить в `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["mcp.*", "proxmoxer.*", "pydantic_settings.*"]
ignore_missing_imports = true
```

### 8. Несрочное / nice-to-have

- `--list-tools` режим у CLI для дебага
- `PROXMOX_LOG_LEVEL` env + структурное логирование
- метрики (prometheus-формат) — только если будет multi-user
- Streamable HTTP transport — если когда-то понадобится hosted-режим

---

## Открытые вопросы

- стоит ли тащить SSH-exec в LXC ради паритета с Plus или оставить scope чисто
  «через Proxmox API» (без paramiko)?
- jobs in-memory или сразу SQLite? in-memory проще, но теряется при рестарте.
- approval-токен — overkill для личного use, но абсолютно нужен если когда-то
  расшарю сервер.
