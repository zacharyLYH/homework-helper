"""Settings API: read/write the user's LLM config, import/export, and test ping.

The config is one YAML string on the users row. The UI only ever exchanges
JSON (masked keys) via GET/PUT; YAML is produced/consumed by export/import.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.llmconfig import parser, store
from app.llmconfig.catalog import MODEL_OPTIONS, PROVIDERS
from app.llmconfig.parser import LLMConfigError
from app.llmconfig.ping import test_config as run_config_tests
from app.llmconfig.security import MissingSecretKeyError
from app.schemas import User

router = APIRouter()


@router.get("/api/settings/catalog")
async def get_catalog(user: User = Depends(get_current_user)) -> dict:
    return {
        "providers": [{"id": p.id, "name": p.name, "key_url": p.key_url} for p in PROVIDERS],
        "models": [
            {
                "id": m.id,
                "provider": m.provider,
                "label": m.label,
                "tier": m.tier,
                "recommended": m.recommended,
                "supports_images": m.supports_images,
                "price_in": m.price_in,
                "price_out": m.price_out,
                "price_note": m.price_note,
            }
            for m in MODEL_OPTIONS
        ],
    }


@router.get("/api/settings/config")
async def get_config(user: User = Depends(get_current_user)) -> dict:
    cfg = store.get_config(user.id) or parser.empty_config()
    return parser.to_ui_json(cfg)


@router.put("/api/settings/config")
async def put_config(body: dict, user: User = Depends(get_current_user)) -> dict:
    current = store.get_config(user.id)
    try:
        cfg = parser.apply_incoming(body, current)
    except MissingSecretKeyError as exc:
        raise HTTPException(
            status_code=500, detail="AES_SECRET_KEY is not configured. Refusing to store API keys."
        ) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save_config(user.id, cfg)
    return parser.to_ui_json(cfg)


@router.post("/api/settings/config/export")
async def export_config(user: User = Depends(get_current_user)) -> dict:
    cfg = store.get_config(user.id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No config to export")
    return {"yaml": parser.export_config(cfg)}


@router.post("/api/settings/config/import")
async def import_config(body: dict, user: User = Depends(get_current_user)) -> dict:
    yaml_text = (body or {}).get("yaml", "")
    try:
        cfg = parser.import_config(yaml_text)
    except LLMConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return parser.to_ui_json(cfg)


@router.post("/api/settings/config/test")
async def test_config(body: dict | None = None, user: User = Depends(get_current_user)) -> dict:
    """Ping every distinct (provider, model, key) combination.

    With a body, tests the submitted (possibly unsaved) config so the UI can
    verify a model the moment it is added. Without a body, tests the stored one.
    """
    if body is not None:
        current = store.get_config(user.id)
        try:
            cfg = parser.apply_incoming(body, current)
        except MissingSecretKeyError as exc:
            raise HTTPException(
                status_code=500, detail="AES_SECRET_KEY is not configured. Refusing to store API keys."
            ) from exc
        except LLMConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        cfg = store.get_config(user.id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No config to test")
    return {"results": await run_config_tests(cfg)}
