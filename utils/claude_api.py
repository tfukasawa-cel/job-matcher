"""
Claude API連携モジュール
- スキルマッチ判定（CSV取込時）
- PDF精密採点（Phase3）
"""
import anthropic
import json
import re
import base64


def get_client(api_key: str) -> anthropic.Anthropic:
    """Claude APIクライアントを取得"""
    return anthropic.Anthropic(api_key=api_key)


def skill_match_batch(api_key: str, candidate_profile: str, jobs: list[dict],
                      source: str = "circus", progress_callback=None) -> list[dict]:
    """
    求人リストに対してスキルマッチ判定を一括実行
    jobs: [{"company": "...", "title": "...", "skills": "...", ...}, ...]
    progress_callback: function(completed, total) for progress updates
    Returns: jobs with match_grade and match_reason added
    """
    client = get_client(api_key)

    # バッチで処理（10件ずつ）
    batch_size = 10
    results = []
    total = len(jobs)

    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        job_texts = []
        for idx, job in enumerate(batch):
            job_texts.append(
                f"【求人{idx+1}】\n"
                f"企業名: {job.get('company', '')}\n"
                f"求人タイトル: {job.get('title', '')}\n"
                f"必須スキル・応募資格: {job.get('skills', '')}\n"
            )

        prompt = f"""あなたは人材紹介のプロフェッショナルです。
候補者のプロフィールと各求人の必須条件を照合し、マッチ度を判定してください。

【候補者プロフィール】
{candidate_profile}

【判定基準】
◎（強くマッチ）: 必須条件をすべて満たし、候補者の強みが活かせる
○（マッチ）: 必須条件をおおむね満たしている
△（惜しい）: 必須条件に一部不足があるが、チャレンジ可能
×（不足）: 必須条件を明らかに満たしていない

【判定ルール】
- 経験年数は厳密に見るが、1年以内の不足は△
- エンジニア経験、開発経験、施工管理、看護師等の専門職が必須の場合 → 即×
- 未経験OKの求人 → 大幅加点
- 歓迎条件は判定対象外（必須条件のみで判定）
- 判定理由は日本語で簡潔に

以下の求人を判定してください:

{chr(10).join(job_texts)}

以下のJSON形式で回答してください（他の説明は不要）:
[
  {{"index": 1, "grade": "◎", "reason": "営業経験3年≧2年要件／SaaS業界経験あり"}},
  {{"index": 2, "grade": "○", "reason": "..."}},
  ...
]"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = response.content[0].text

            # JSONを抽出
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                for item in parsed:
                    idx = item["index"] - 1
                    if 0 <= idx < len(batch):
                        batch[idx]["match_grade"] = item.get("grade", "○")
                        batch[idx]["match_reason"] = item.get("reason", "")
            else:
                for job in batch:
                    job["match_grade"] = "○"
                    job["match_reason"] = "AI判定エラー（手動確認推奨）"
        except Exception as e:
            for job in batch:
                job["match_grade"] = "○"
                job["match_reason"] = f"APIエラー: {str(e)[:50]}"

        results.extend(batch)

        if progress_callback:
            progress_callback(len(results), total)

    return results


def score_pdf_with_claude(api_key: str, candidate_profile: str,
                          pdf_text: str, company_name: str,
                          job_title: str, source: str = "circus") -> dict:
    """
    1件のPDFテキストを精密採点
    Returns: {"grade": "◎", "reason": "...", "industry": "IT", "sub_industry": "SaaS"}
    """
    client = get_client(api_key)

    prompt = f"""あなたは人材紹介のプロフェッショナルです。
求人PDFの内容と候補者のプロフィールを照合し、精密に採点してください。

【候補者プロフィール】
{candidate_profile}

【求人情報】
企業名: {company_name}
求人タイトル: {job_title}

【求人PDF全文】
{pdf_text[:8000]}

【判定基準】
◎（強く推薦）: 必須条件をすべて満たし、候補者の強みが活かせる
○（推薦）: 必須条件をおおむね満たし、紹介する価値あり
×（見送り）: 必須条件を明らかに満たさない、またはミスマッチ

【判定の観点】
- 必須条件の充足度（経験年数、スキル、資格等）
- 候補者の強みとの親和性
- 年収・勤務地・働き方の希望との合致
- 成長機会やキャリアパスの魅力

以下のJSON形式で回答してください（他の説明は不要）:
{{
  "grade": "◎",
  "reason": "判定理由を100文字以内で",
  "industry": "大カテゴリ（IT/人材/コンサル/製造/金融/不動産/医療/広告 等）",
  "sub_industry": "中カテゴリ（SaaS/HR Tech/Web広告/EC/FinTech/AI/DX支援/BPO 等）"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = response.content[0].text

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {
                "grade": "○",
                "reason": "AI判定結果のパースに失敗（手動確認推奨）",
                "industry": "",
                "sub_industry": ""
            }
    except Exception as e:
        return {
            "grade": "○",
            "reason": f"APIエラー: {str(e)[:80]}",
            "industry": "",
            "sub_industry": ""
        }


def score_pdfs_batch(api_key: str, candidate_profile: str,
                     pdf_data_list: list[dict],
                     source: str = "circus") -> list[dict]:
    """
    複数PDFを一括精密採点
    pdf_data_list: [{"company": "...", "title": "...", "text": "...", "url": ""}, ...]
    Returns: [{"company": ..., "grade": ..., "reason": ..., ...}, ...]
    """
    results = []
    for pdf_data in pdf_data_list:
        score = score_pdf_with_claude(
            api_key=api_key,
            candidate_profile=candidate_profile,
            pdf_text=pdf_data["text"],
            company_name=pdf_data["company"],
            job_title=pdf_data.get("title", ""),
            source=source
        )
        results.append({
            "company": pdf_data["company"],
            "title": pdf_data.get("title", ""),
            "url": pdf_data.get("url", ""),
            "grade": score["grade"],
            "reason": score["reason"],
            "industry": score["industry"],
            "sub_industry": score["sub_industry"],
        })
    return results


def estimate_cost(num_jobs_csv: int = 0, num_pdfs: int = 0) -> dict:
    """API利用コストの概算"""
    # Claude 3.5 Sonnet pricing: $3/1M input, $15/1M output
    csv_input_tokens = num_jobs_csv * 500  # ~500 tokens per job
    csv_output_tokens = num_jobs_csv * 50
    pdf_input_tokens = num_pdfs * 5000  # ~5000 tokens per PDF
    pdf_output_tokens = num_pdfs * 100

    total_input = csv_input_tokens + pdf_input_tokens
    total_output = csv_output_tokens + pdf_output_tokens

    cost_input = (total_input / 1_000_000) * 3
    cost_output = (total_output / 1_000_000) * 15

    return {
        "total_cost_usd": round(cost_input + cost_output, 3),
        "total_cost_jpy": round((cost_input + cost_output) * 150, 0),
        "input_tokens": total_input,
        "output_tokens": total_output,
    }
