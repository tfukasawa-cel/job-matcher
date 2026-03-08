"""
候補者プロフィール管理モジュール
JSONファイルで永続化
"""
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CANDIDATES_FILE = os.path.join(DATA_DIR, "candidates.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_candidates() -> list[dict]:
    """保存済みの候補者一覧を読み込む"""
    _ensure_data_dir()
    if not os.path.exists(CANDIDATES_FILE):
        return []
    try:
        with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_candidates(candidates: list[dict]):
    """候補者一覧を保存"""
    _ensure_data_dir()
    with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)


def add_candidate(name: str, profile: str) -> dict:
    """候補者を追加"""
    candidates = load_candidates()

    # 同名チェック
    for c in candidates:
        if c["name"] == name:
            c["profile"] = profile
            c["updated_at"] = datetime.now().isoformat()
            save_candidates(candidates)
            return c

    new_candidate = {
        "name": name,
        "profile": profile,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    candidates.append(new_candidate)
    save_candidates(candidates)
    return new_candidate


def delete_candidate(name: str) -> bool:
    """候補者を削除"""
    candidates = load_candidates()
    original_len = len(candidates)
    candidates = [c for c in candidates if c["name"] != name]
    if len(candidates) < original_len:
        save_candidates(candidates)
        return True
    return False


def get_candidate(name: str) -> dict | None:
    """候補者を取得"""
    candidates = load_candidates()
    for c in candidates:
        if c["name"] == name:
            return c
    return None
