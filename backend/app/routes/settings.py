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
from app.schemas import (
    ConfigExportResponse,
    ConfigImportRequest,
    ConfigTestResponse,
    LLMConfigUI,
    PingResult,
    SettingsCatalogResponse,
    SettingsModelOption,
    SettingsProvider,
)
from shared.schemas import User

router = APIRouter()


@router.get("/api/settings/catalog", response_model=SettingsCatalogResponse)
async def get_catalog(user: User = Depends(get_current_user)) -> SettingsCatalogResponse:
    return SettingsCatalogResponse(
        providers=[SettingsProvider.model_validate(p) for p in PROVIDERS],
        models=[SettingsModelOption.model_validate(m) for m in MODEL_OPTIONS],
    )


@router.get("/api/settings/config", response_model=LLMConfigUI)
async def get_config(user: User = Depends(get_current_user)) -> LLMConfigUI:
    cfg = store.get_config(user.id) or parser.empty_config()
    return LLMConfigUI.model_validate(parser.to_ui_json(cfg))


@router.put("/api/settings/config", response_model=LLMConfigUI)
async def put_config(body: LLMConfigUI, user: User = Depends(get_current_user)) -> LLMConfigUI:
    current = store.get_config(user.id)
    try:
        cfg = parser.apply_incoming(body.model_dump(), current)
    except MissingSecretKeyError as exc:
        raise HTTPException(
            status_code=500, detail="AES_SECRET_KEY is not configured. Refusing to store API keys."
        ) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save_config(user.id, cfg)
    return LLMConfigUI.model_validate(parser.to_ui_json(cfg))


@router.post("/api/settings/config/export")
async def export_config(user: User = Depends(get_current_user)) -> ConfigExportResponse:
    cfg = store.get_config(user.id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No config to export")
    return ConfigExportResponse(yaml=parser.export_config(cfg))


@router.post("/api/settings/config/import", response_model=LLMConfigUI)
async def import_config(body: ConfigImportRequest, user: User = Depends(get_current_user)) -> LLMConfigUI:
    try:
        cfg = parser.import_config(body.yaml)
    except LLMConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LLMConfigUI.model_validate(parser.to_ui_json(cfg))


@router.post("/api/settings/config/test", response_model=ConfigTestResponse)
async def test_config(body: LLMConfigUI | None = None, user: User = Depends(get_current_user)) -> ConfigTestResponse:
    """Ping every distinct (provider, model, key) combination.

    With a body, tests the submitted (possibly unsaved) config so the UI can
    verify a model the moment it is added. Without a body, tests the stored one.
    """
    if body is not None:
        current = store.get_config(user.id)
        try:
            cfg = parser.apply_incoming(body.model_dump(), current)
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
    results = await run_config_tests(cfg)
    return ConfigTestResponse(results=[PingResult(**r) for r in results])
