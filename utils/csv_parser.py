"""
CSV・JSON解析モジュール
circus / HITO-Link のCSVファイルおよびブックマークレットJSONを解析して統一的なデータ構造に変換
"""
from __future__ import annotations

import csv
import io
import json
import re


def parse_circus_csv(file_content: bytes) -> list[dict]:
    """
    circus CSVファイルを解析
    Returns: [{"company": "...", "title": "...", "job_type": "...", "salary": "...",
               "location": "...", "skills": "...", "match_grade": "", "match_reason": ""}, ...]
    """
    # エンコーディング試行
    for encoding in ['utf-8-sig', 'utf-8', 'cp932', 'shift_jis']:
        try:
            text = file_content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = file_content.decode('utf-8', errors='replace')

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return []

    # ヘッダー検出
    header = rows[0]
    data_rows = rows[1:]

    jobs = []
    for row in data_rows:
        if len(row) < 6:
            continue

        job = {
            "company": row[3] if len(row) > 3 else "",
            "title": row[4] if len(row) > 4 else "",
            "job_type": row[5] if len(row) > 5 else "",
            "salary": row[6] if len(row) > 6 else "",
            "location": row[7] if len(row) > 7 else "",
            "skills": row[8] if len(row) > 8 else "",
            "match_grade": row[9] if len(row) > 9 and row[9] else "",
            "match_reason": row[10] if len(row) > 10 and row[10] else "",
            "page": row[1] if len(row) > 1 else "",
        }
        if job["company"] or job["title"]:
            jobs.append(job)

    return jobs


def parse_hitolink_csv(file_content: bytes) -> list[dict]:
    """
    HITO-Link CSVファイルを解析
    Returns: [{"company": "...", "title": "...", "salary": "...",
               "location": "...", "skills": "...", "match_grade": "", "match_reason": ""}, ...]
    """
    for encoding in ['utf-8-sig', 'utf-8', 'cp932', 'shift_jis']:
        try:
            text = file_content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = file_content.decode('utf-8', errors='replace')

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return []

    header = rows[0]
    data_rows = rows[1:]

    # HITO-Linkのカラム構造を検出
    # カラム: No., ページ, 企業名, 求人タイトル, 年収, 勤務地,
    #         必須スキル・応募資格, マッチ度, 判定理由, 応募ステータス, 気になり度, メモ
    jobs = []
    for row in data_rows:
        if len(row) < 4:
            continue

        # ヘッダー名でインデックスを推定
        company_idx = _find_col_index(header, ["企業名", "企業"])
        title_idx = _find_col_index(header, ["求人タイトル", "タイトル", "ポジション"])
        salary_idx = _find_col_index(header, ["年収", "想定年収"])
        location_idx = _find_col_index(header, ["勤務地"])
        skills_idx = _find_col_index(header, ["必須スキル", "応募資格", "必須スキル・応募資格"])
        grade_idx = _find_col_index(header, ["マッチ度"])
        reason_idx = _find_col_index(header, ["判定理由"])
        page_idx = _find_col_index(header, ["ページ"])

        job = {
            "company": _safe_get(row, company_idx, ""),
            "title": _safe_get(row, title_idx, ""),
            "salary": _safe_get(row, salary_idx, ""),
            "location": _safe_get(row, location_idx, ""),
            "skills": _safe_get(row, skills_idx, ""),
            "match_grade": _safe_get(row, grade_idx, ""),
            "match_reason": _safe_get(row, reason_idx, ""),
            "page": _safe_get(row, page_idx, ""),
            "job_type": "",
        }
        if job["company"] or job["title"]:
            jobs.append(job)

    return jobs


def _find_col_index(header: list[str], candidates: list[str]) -> int:
    """ヘッダー名からカラムインデックスを検出"""
    for i, h in enumerate(header):
        for c in candidates:
            if c in h:
                return i
    return -1


def _safe_get(row: list, idx: int, default: str = "") -> str:
    """安全にリストから値を取得"""
    if idx < 0 or idx >= len(row):
        return default
    return row[idx] or default


def parse_bookmarklet_json(json_text: str) -> tuple[list[dict], str]:
    """
    ブックマークレットが出力したJSONテキストを解析
    Returns: (jobs_list, source_key)
      jobs_list: [{"company": "...", "title": "...", ...}, ...]
      source_key: "circus" or "hito-link"
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return [], ""

    source = data.get("source", "")
    raw_jobs = data.get("jobs", [])

    if not raw_jobs:
        return [], source

    jobs = []
    for j in raw_jobs:
        job = {
            "company": j.get("company", ""),
            "title": j.get("title", ""),
            "job_type": j.get("job_type", j.get("jobType", "")),
            "salary": j.get("salary", ""),
            "location": j.get("location", ""),
            "skills": j.get("skills", ""),
            "match_grade": "",
            "match_reason": "",
            "page": str(j.get("page", "")),
        }
        if job["company"] or job["title"]:
            jobs.append(job)

    return jobs, source


def auto_detect_source(file_content: bytes) -> str:
    """CSVの内容からcircus/hito-linkを自動判定"""
    for encoding in ['utf-8-sig', 'utf-8', 'cp932']:
        try:
            text = file_content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = ""

    if "求人種別" in text or "ページ内順位" in text or "circus" in text.lower():
        return "circus"
    elif "hito" in text.lower() or "HITO" in text:
        return "hito-link"
    else:
        # カラム数で判定（circusは16列、HITO-Linkは12列程度）
        first_line = text.split('\n')[0] if text else ""
        col_count = first_line.count(',')
        return "circus" if col_count >= 14 else "hito-link"
