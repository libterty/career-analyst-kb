"""Hill Climbing Human Review Router — admin 審核 / 套用 prompt diff。"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_role
from src.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/admin/hill-climbing", tags=["Hill Climbing"])

AdminUserDep = Annotated[User, Depends(require_role("admin"))]

HILL_CLIMBING_DIR = Path(os.getenv("HILL_CLIMBING_DIR", "/app/hill-climbing"))
VOLTAGENT_AGENTS_DIR = Path(os.getenv("VOLTAGENT_AGENTS_DIR", "/app/voltagent-agents"))


def _read_apply_log(limit: int = 10) -> list[dict]:
    log_path = HILL_CLIMBING_DIR / "apply-log.jsonl"
    if not log_path.exists():
        return []
    lines = [l for l in log_path.read_text().strip().split("\n") if l]
    return [json.loads(l) for l in lines[-limit:]]


@router.get("/pending")
async def get_pending(_user: AdminUserDep) -> dict:
    """回傳最新的 proposed-diffs/latest.json 及近期套用記錄。"""
    latest = HILL_CLIMBING_DIR / "proposed-diffs" / "latest.json"
    if not latest.exists():
        return {
            "diffs": [],
            "summary": "目前沒有待審核的 prompt 差異",
            "generated_at": None,
            "overall_accuracy": None,
            "apply_log": _read_apply_log(),
        }
    data = json.loads(latest.read_text())
    return {**data, "apply_log": _read_apply_log()}


class ApplyRequest(BaseModel):
    approved_ids: list[str]


@router.post("/apply")
async def apply_diffs(body: ApplyRequest, user: AdminUserDep) -> dict:
    """對 supervisor.ts 套用指定 diff ID，並記錄到 apply-log.jsonl。"""
    latest = HILL_CLIMBING_DIR / "proposed-diffs" / "latest.json"
    if not latest.exists():
        raise HTTPException(404, "找不到待審核的 diff 檔案")

    data = json.loads(latest.read_text())
    diffs_by_id = {d["id"]: d for d in data["diffs"]}

    supervisor_path = VOLTAGENT_AGENTS_DIR / "supervisor.ts"
    if not supervisor_path.exists():
        raise HTTPException(404, "找不到 supervisor.ts")

    # Backup
    backup_dir = HILL_CLIMBING_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"supervisor_{ts}.ts"
    shutil.copy(supervisor_path, backup_path)

    content = supervisor_path.read_text()
    applied: list[str] = []
    missed: list[str] = []

    for diff_id in body.approved_ids:
        diff = diffs_by_id.get(diff_id)
        if not diff:
            missed.append(diff_id)
            continue
        if diff["original_excerpt"] in content:
            content = content.replace(diff["original_excerpt"], diff["replacement"], 1)
            applied.append(diff_id)
        else:
            missed.append(diff_id)

    supervisor_path.write_text(content)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "applied": applied,
        "missed": missed,
        "backup": str(backup_path),
        "gate_passed": True,
        "outcome": "applied",
        "applied_by": user.username,
    }
    log_path = HILL_CLIMBING_DIR / "apply-log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    return {
        "applied": applied,
        "missed": missed,
        "backup": str(backup_path),
        "note": "請執行 docker compose build voltagent && docker compose up -d voltagent 使變更生效",
    }
