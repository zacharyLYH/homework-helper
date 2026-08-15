# API Reference

_This file is generated from the FastAPI OpenAPI schema. Do not edit by hand._

Regenerate with:

```bash
cd backend && uv run python scripts/generate_api_docs.py
```

## Authentication

All endpoints except `/` and `/health` require a valid JWT. It is sent as an
`httpOnly` cookie named `jwt_token` (set on login) or as an
`Authorization: Bearer <token>` header. The JWT claims are `sub`, `email`, `iat`, `exp`.

## Endpoints

### Health & root

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/` | Root |  |
| `GET` | `/health` | Health |  |

### Subjects

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/api/subjects` | Get Subjects |  |
| `POST` | `/api/subjects` | Create Subject Route |  |
| `PATCH` | `/api/subjects/{subject_id}` | Update Subject Route |  |
| `DELETE` | `/api/subjects/{subject_id}` | Delete Subject Route |  |

### Chats

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/api/chats` | Get Chats |  |
| `POST` | `/api/chats` | Create Chat Route |  |
| `GET` | `/api/chats/{chat_id}` | Get Chat Route |  |
| `PATCH` | `/api/chats/{chat_id}` | Update Chat Route |  |
| `DELETE` | `/api/chats/{chat_id}` | Delete Chat Route |  |
| `GET` | `/api/chats/{chat_id}/messages` | Get Chat Messages |  |

### Chat execution

| Method | Path | Summary | Request body |
|---|---|---|---|
| `POST` | `/api/chat/stream` | Chat Stream | `ChatRequest` |

### Memory

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/api/memory/subjects/{subject_id}/context` | Get Memory Context |  |
| `GET` | `/api/memory/subjects/{subject_id}/jobs` | List Memory Jobs |  |

### Settings

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/api/settings/catalog` | Get Catalog |  |
| `GET` | `/api/settings/config` | Get Config |  |
| `PUT` | `/api/settings/config` | Put Config | `LLMConfigUI` |
| `POST` | `/api/settings/config/export` | Export Config |  |
| `POST` | `/api/settings/config/import` | Import Config | `ConfigImportRequest` |
| `POST` | `/api/settings/config/test` | Test Config | `LLMConfigUI` |

### Tools

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/api/tools` | List Tools |  |

### Debug (non-prod)

| Method | Path | Summary | Request body |
|---|---|---|---|
| `GET` | `/api/debug/chats/{chat_id}/messages` | Get Messages Endpoint |  |
| `GET` | `/api/debug/logs` | Get Logs |  |
| `POST` | `/api/debug/sql` | Execute Sql | `SqlRequest` |
| `GET` | `/api/debug/subjects/{subject_id}/chats` | Get Chats |  |
| `GET` | `/api/debug/traces` | List Traces |  |
| `GET` | `/api/debug/users` | Get Users |  |
| `GET` | `/api/debug/users/{user_id}/subjects` | Get Subjects |  |

### Auth

| Method | Path | Summary | Request body |
|---|---|---|---|
| `POST` | `/api/auth/logout` | Logout |  |
| `GET` | `/api/auth/me` | Get Me |  |
| `POST` | `/api/auth/refresh` | Refresh |  |
| `POST` | `/api/auth/request-code` | Request Code | `AuthRequestCodeRequest` |
| `POST` | `/api/auth/verify` | Verify | `AuthVerifyRequest` |
