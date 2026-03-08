"""
求人マッチングアプリ - circus & HITO-Link対応
チーム3人で共有して使える求人スキルマッチ＆推薦リスト作成ツール
"""
import streamlit as st
import pandas as pd
import pdfplumber
import io
import os
import sys
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(__file__))

from utils.candidates import load_candidates, add_candidate, delete_candidate
from utils.csv_parser import parse_circus_csv, parse_hitolink_csv, auto_detect_source
from utils.claude_api import skill_match_batch, score_pdfs_batch, estimate_cost
from utils.xlsx_generator import (
    generate_recommendation_xlsx,
    generate_csv_match_xlsx,
)

# ============================
# ページ設定
# ============================
st.set_page_config(
    page_title="求人マッチングツール",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================
# カスタムCSS
# ============================
st.markdown("""
<style>
    .stApp { max-width: 1400px; margin: 0 auto; }
    .grade-excellent { background-color: #C6EFCE; padding: 4px 12px; border-radius: 12px; font-weight: bold; }
    .grade-good { background-color: #BDD7EE; padding: 4px 12px; border-radius: 12px; font-weight: bold; }
    .grade-fair { background-color: #FCE4D6; padding: 4px 12px; border-radius: 12px; font-weight: bold; }
    .grade-poor { background-color: #FFC7CE; padding: 4px 12px; border-radius: 12px; font-weight: bold; }
    .metric-card {
        background: #f8f9fa; padding: 16px; border-radius: 8px;
        border-left: 4px solid #FF6B35; margin-bottom: 8px;
    }
    div[data-testid="stSidebar"] { background-color: #f8f9fa; }
</style>
""", unsafe_allow_html=True)

# ============================
# セッション状態の初期化
# ============================
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "current_jobs" not in st.session_state:
    st.session_state.current_jobs = []
if "scored_jobs" not in st.session_state:
    st.session_state.scored_jobs = []
if "current_source" not in st.session_state:
    st.session_state.current_source = "circus"
if "selected_candidate" not in st.session_state:
    st.session_state.selected_candidate = None

# ============================
# サイドバー
# ============================
with st.sidebar:
    st.markdown("## 🎯 求人マッチングツール")
    st.markdown("---")

    page = st.radio(
        "メニュー",
        ["⚙️ 設定", "👤 候補者管理", "📋 CSV取込 & マッチ",
         "📄 PDF精密採点", "📊 推薦リスト出力"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # API設定状態表示
    if st.session_state.api_key:
        st.success("✅ APIキー設定済み")
    else:
        st.warning("⚠️ APIキー未設定")

    # 選択中の候補者
    if st.session_state.selected_candidate:
        st.info(f"👤 {st.session_state.selected_candidate}")

    # 現在のデータ状態
    if st.session_state.current_jobs:
        st.metric("取込済み求人数", len(st.session_state.current_jobs))
    if st.session_state.scored_jobs:
        st.metric("採点済み求人数", len(st.session_state.scored_jobs))


# ============================
# ⚙️ 設定ページ
# ============================
if page == "⚙️ 設定":
    st.title("⚙️ 設定")

    st.markdown("""
    ### Claude APIキーの設定
    PDF精密採点やAIスキルマッチに使用します。

    **APIキーの取得方法:**
    1. [Anthropic Console](https://console.anthropic.com/) にアクセス
    2. アカウント作成（初回のみ）
    3. 「API Keys」→「Create Key」でキーを作成
    4. 下のフィールドにコピー&ペースト
    """)

    api_key = st.text_input(
        "APIキー",
        value=st.session_state.api_key,
        type="password",
        placeholder="sk-ant-api03-...",
    )
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        if api_key:
            st.success("APIキーを設定しました")

    st.markdown("---")
    st.markdown("### 💰 コスト見積もり")

    col1, col2 = st.columns(2)
    with col1:
        est_csv = st.number_input("CSV取込時の求人数（目安）", value=100, step=10)
    with col2:
        est_pdf = st.number_input("PDF精密採点の件数（目安）", value=10, step=1)

    cost = estimate_cost(est_csv, est_pdf)
    st.markdown(f"""
    | 項目 | 値 |
    |------|-----|
    | 推定コスト（USD） | **${cost['total_cost_usd']:.3f}** |
    | 推定コスト（JPY） | **約 ¥{cost['total_cost_jpy']:.0f}** |
    | 入力トークン数 | {cost['input_tokens']:,} |
    | 出力トークン数 | {cost['output_tokens']:,} |
    """)

    st.info("💡 月20回利用で約 ¥1,500〜3,000 程度です。Anthropic Console で月額上限を設定できます。")


# ============================
# 👤 候補者管理ページ
# ============================
elif page == "👤 候補者管理":
    st.title("👤 候補者管理")

    tab_list, tab_add = st.tabs(["📋 候補者一覧", "➕ 新規登録"])

    with tab_list:
        candidates = load_candidates()
        if not candidates:
            st.info("候補者がまだ登録されていません。「新規登録」タブから追加してください。")
        else:
            for c in candidates:
                with st.expander(f"👤 {c['name']}（更新: {c.get('updated_at', '')[:10]}）"):
                    st.text_area(
                        "プロフィール",
                        value=c["profile"],
                        height=200,
                        key=f"prof_{c['name']}",
                        disabled=True,
                    )
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button(f"✅ この候補者を選択", key=f"select_{c['name']}"):
                            st.session_state.selected_candidate = c["name"]
                            st.rerun()
                    with col2:
                        if st.button(f"🗑️ 削除", key=f"del_{c['name']}"):
                            delete_candidate(c["name"])
                            if st.session_state.selected_candidate == c["name"]:
                                st.session_state.selected_candidate = None
                            st.rerun()

    with tab_add:
        st.markdown("### 新しい候補者を登録")

        new_name = st.text_input("候補者名", placeholder="例: 田中さん")
        new_profile = st.text_area(
            "プロフィール",
            height=300,
            placeholder="""例:
・法人営業経験: 4年
・業界: IT業界（SaaS系スタートアップ）
・マネジメント経験: 50名規模
・カスタマーサクセス経験: なし
・英語: TOEIC 750
・学歴: 大卒
・その他スキル: Salesforce運用、提案資料作成、CRM設計""",
        )

        if st.button("💾 保存", type="primary", disabled=not new_name):
            if new_name and new_profile:
                add_candidate(new_name, new_profile)
                st.session_state.selected_candidate = new_name
                st.success(f"✅ {new_name} を登録しました！")
                st.rerun()
            else:
                st.error("名前とプロフィールを入力してください")


# ============================
# 📋 CSV取込 & スキルマッチ
# ============================
elif page == "📋 CSV取込 & マッチ":
    st.title("📋 CSV取込 & スキルマッチ判定")

    # 候補者選択確認
    if not st.session_state.selected_candidate:
        st.warning("⚠️ 先に「候補者管理」で候補者を選択してください。")
        st.stop()

    candidate = None
    candidates = load_candidates()
    for c in candidates:
        if c["name"] == st.session_state.selected_candidate:
            candidate = c
            break

    if not candidate:
        st.error("選択された候補者が見つかりません。")
        st.stop()

    st.info(f"👤 対象候補者: **{candidate['name']}**")

    # ソース選択
    source = st.radio(
        "求人サイト",
        ["circus", "HITO-Link"],
        horizontal=True,
    )
    source_key = "circus" if source == "circus" else "hito-link"
    st.session_state.current_source = source_key

    st.markdown("---")

    # CSVアップロード
    st.markdown("### 📁 CSVファイルをアップロード")
    st.caption("Phase1で出力されたCSVファイル、または検索結果CSVをアップロードしてください。")

    uploaded_csv = st.file_uploader(
        "CSVファイルを選択",
        type=["csv"],
        key="csv_upload",
    )

    if uploaded_csv:
        file_content = uploaded_csv.read()

        # 解析
        with st.spinner("CSVを読み込み中..."):
            if source_key == "circus":
                jobs = parse_circus_csv(file_content)
            else:
                jobs = parse_hitolink_csv(file_content)

        if not jobs:
            st.error("求人データを読み取れませんでした。ファイル形式を確認してください。")
            st.stop()

        st.success(f"✅ {len(jobs)}件の求人を読み込みました")

        # 既存マッチ度チェック
        has_existing_grades = any(j.get("match_grade") for j in jobs)

        if has_existing_grades:
            st.info("📊 CSVにマッチ度が含まれています。AIで再判定することもできます。")

        # データ表示
        st.markdown("### 📊 求人一覧")

        # フィルター
        col1, col2, col3 = st.columns(3)
        with col1:
            grade_filter = st.multiselect(
                "マッチ度フィルター",
                ["◎", "○", "△", "×", "（未判定）"],
                default=["◎", "○", "△", "×", "（未判定）"],
            )
        with col2:
            search_company = st.text_input("企業名検索", "")
        with col3:
            search_title = st.text_input("求人タイトル検索", "")

        # フィルタリング
        filtered_jobs = []
        for j in jobs:
            grade = j.get("match_grade", "")
            display_grade = grade if grade else "（未判定）"

            if display_grade not in grade_filter:
                continue
            if search_company and search_company.lower() not in j.get("company", "").lower():
                continue
            if search_title and search_title.lower() not in j.get("title", "").lower():
                continue
            filtered_jobs.append(j)

        # DataFrame表示
        if source_key == "circus":
            df_data = [{
                "No.": i + 1,
                "企業名": j.get("company", ""),
                "求人タイトル": j.get("title", ""),
                "種別": j.get("job_type", ""),
                "年収": j.get("salary", ""),
                "勤務地": j.get("location", ""),
                "マッチ度": j.get("match_grade", ""),
                "判定理由": j.get("match_reason", ""),
            } for i, j in enumerate(filtered_jobs)]
        else:
            df_data = [{
                "No.": i + 1,
                "企業名": j.get("company", ""),
                "求人タイトル": j.get("title", ""),
                "年収": j.get("salary", ""),
                "勤務地": j.get("location", ""),
                "マッチ度": j.get("match_grade", ""),
                "判定理由": j.get("match_reason", ""),
            } for i, j in enumerate(filtered_jobs)]

        df = pd.DataFrame(df_data)
        st.dataframe(
            df,
            use_container_width=True,
            height=400,
        )

        # マッチ度サマリー
        grades = [j.get("match_grade", "") for j in jobs]
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("◎ 強くマッチ", grades.count("◎"))
        col2.metric("○ マッチ", grades.count("○"))
        col3.metric("△ 惜しい", grades.count("△"))
        col4.metric("× 不足", grades.count("×"))
        col5.metric("未判定", len([g for g in grades if not g]))

        st.markdown("---")

        # AIスキルマッチ判定
        st.markdown("### 🤖 AIスキルマッチ判定")

        if not st.session_state.api_key:
            st.warning("⚠️ AI判定にはAPIキーが必要です。「設定」ページで設定してください。")
        else:
            cost = estimate_cost(num_jobs_csv=len(jobs))
            st.caption(f"💰 推定コスト: ${cost['total_cost_usd']:.3f}（約¥{cost['total_cost_jpy']:.0f}）")

            if st.button("🚀 AIスキルマッチ判定を実行", type="primary"):
                progress = st.progress(0)
                status = st.empty()

                with st.spinner("AIが判定中..."):
                    status.text(f"全{len(jobs)}件を判定中...")
                    matched_jobs = skill_match_batch(
                        api_key=st.session_state.api_key,
                        candidate_profile=candidate["profile"],
                        jobs=jobs,
                        source=source_key,
                    )
                    progress.progress(100)
                    status.text("判定完了！")

                st.session_state.current_jobs = matched_jobs
                st.success("✅ AI判定完了！ページを再読み込みして結果を確認してください。")
                st.rerun()

        # データ保存
        st.markdown("---")
        st.markdown("### 💾 結果をダウンロード")

        col1, col2 = st.columns(2)
        with col1:
            # xlsx ダウンロード
            xlsx_data = generate_csv_match_xlsx(
                jobs=filtered_jobs,
                candidate_name=candidate["name"],
                source=source_key,
            )
            today = datetime.now().strftime("%Y%m%d")
            filename = f"{source_key}_求人一覧_{candidate['name']}_{today}.xlsx"
            st.download_button(
                "📥 Excelダウンロード (.xlsx)",
                data=xlsx_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col2:
            # CSV ダウンロード
            csv_output = io.StringIO()
            df.to_csv(csv_output, index=False, encoding="utf-8-sig")
            csv_filename = f"{source_key}_求人一覧_{candidate['name']}_{today}.csv"
            st.download_button(
                "📥 CSVダウンロード (.csv)",
                data=csv_output.getvalue().encode("utf-8-sig"),
                file_name=csv_filename,
                mime="text/csv",
            )

        # セッションに保存
        st.session_state.current_jobs = jobs


# ============================
# 📄 PDF精密採点
# ============================
elif page == "📄 PDF精密採点":
    st.title("📄 PDF精密採点")

    # 候補者確認
    if not st.session_state.selected_candidate:
        st.warning("⚠️ 先に「候補者管理」で候補者を選択してください。")
        st.stop()

    candidate = None
    for c in load_candidates():
        if c["name"] == st.session_state.selected_candidate:
            candidate = c
            break

    if not candidate:
        st.error("選択された候補者が見つかりません。")
        st.stop()

    # API確認
    if not st.session_state.api_key:
        st.warning("⚠️ PDF精密採点にはAPIキーが必要です。「設定」ページで設定してください。")
        st.stop()

    st.info(f"👤 対象候補者: **{candidate['name']}**")

    # ソース選択
    source = st.radio(
        "求人サイト",
        ["circus", "HITO-Link"],
        horizontal=True,
        key="pdf_source",
    )
    source_key = "circus" if source == "circus" else "hito-link"

    st.markdown("---")

    # PDFアップロード
    st.markdown("### 📁 求人PDFをアップロード")
    st.caption("circusやHITO-Linkからダウンロードした求人PDFをまとめてアップロードしてください。")

    uploaded_pdfs = st.file_uploader(
        "PDFファイルを選択（複数可）",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_upload",
    )

    if uploaded_pdfs:
        st.success(f"📄 {len(uploaded_pdfs)}件のPDFをアップロードしました")

        # URLリスト（circusの場合のみ）
        url_map = {}
        if source_key == "circus":
            st.markdown("### 🔗 URLリスト（任意）")
            st.caption("circusの求人URLを企業名と紐付けて入力してください（1行1企業: 企業名,URL）")
            url_text = st.text_area(
                "URLリスト",
                height=150,
                placeholder="HENNGE株式会社,https://circus-job.com/search/233760?...\n株式会社〇〇,https://circus-job.com/search/XXXXX?...",
            )
            if url_text:
                for line in url_text.strip().split("\n"):
                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        url_map[parts[0].strip()] = parts[1].strip()

        # コスト見積もり
        cost = estimate_cost(num_pdfs=len(uploaded_pdfs))
        st.caption(f"💰 推定コスト: ${cost['total_cost_usd']:.3f}（約¥{cost['total_cost_jpy']:.0f}）")

        # 実行ボタン
        if st.button("🚀 精密採点を実行", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            # PDF読み取り
            pdf_data_list = []
            for i, pdf_file in enumerate(uploaded_pdfs):
                status_text.text(f"PDF読み取り中... ({i+1}/{len(uploaded_pdfs)})")
                progress_bar.progress(int((i / len(uploaded_pdfs)) * 50))

                # ファイル名から企業名を推測
                filename = os.path.splitext(pdf_file.name)[0]
                company_name = filename

                try:
                    with pdfplumber.open(io.BytesIO(pdf_file.read())) as pdf:
                        text = ""
                        for page_obj in pdf.pages:
                            page_text = page_obj.extract_text()
                            if page_text:
                                text += page_text + "\n"

                    pdf_data_list.append({
                        "company": company_name,
                        "title": "",
                        "text": text,
                        "url": url_map.get(company_name, ""),
                    })
                except Exception as e:
                    st.warning(f"⚠️ {pdf_file.name} の読み取りに失敗: {str(e)[:50]}")

            if not pdf_data_list:
                st.error("読み取れるPDFがありませんでした。")
                st.stop()

            # Claude API精密採点
            status_text.text(f"AI精密採点中... （{len(pdf_data_list)}件）")
            progress_bar.progress(50)

            scored = score_pdfs_batch(
                api_key=st.session_state.api_key,
                candidate_profile=candidate["profile"],
                pdf_data_list=pdf_data_list,
                source=source_key,
            )

            progress_bar.progress(100)
            status_text.text("採点完了！")

            st.session_state.scored_jobs = scored

            # 結果表示
            st.markdown("### 📊 採点結果")

            grades = [s["grade"] for s in scored]
            col1, col2, col3 = st.columns(3)
            col1.metric("◎ 強く推薦", grades.count("◎"))
            col2.metric("○ 推薦", grades.count("○"))
            col3.metric("× 見送り", grades.count("×"))

            # 結果テーブル
            result_data = [{
                "No.": i + 1,
                "推薦度": s["grade"],
                "業界": s["industry"],
                "業種": s["sub_industry"],
                "企業名": s["company"],
                "判定理由": s["reason"],
            } for i, s in enumerate(scored)]

            result_df = pd.DataFrame(result_data)
            st.dataframe(result_df, use_container_width=True)

            st.success("✅ 採点完了！「推薦リスト出力」ページでxlsxをダウンロードできます。")


# ============================
# 📊 推薦リスト出力
# ============================
elif page == "📊 推薦リスト出力":
    st.title("📊 推薦リスト出力")

    if not st.session_state.scored_jobs:
        st.warning("⚠️ まだ精密採点が行われていません。「PDF精密採点」ページで先に採点を実行してください。")
        st.stop()

    if not st.session_state.selected_candidate:
        st.warning("⚠️ 候補者が選択されていません。")
        st.stop()

    candidate_name = st.session_state.selected_candidate
    scored = st.session_state.scored_jobs
    source_key = st.session_state.current_source

    st.info(f"👤 候補者: **{candidate_name}** ／ ソース: **{source_key}**")

    # サマリー
    grades = [s["grade"] for s in scored]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総求人数", len(scored))
    col2.metric("◎ 強く推薦", grades.count("◎"))
    col3.metric("○ 推薦", grades.count("○"))
    col4.metric("× 見送り", grades.count("×"))

    st.markdown("---")

    # 結果テーブル
    st.markdown("### 📋 採点結果一覧")

    if source_key == "hito-link":
        result_data = [{
            "No.": i + 1,
            "推薦度": s["grade"],
            "業界": s["industry"],
            "業種": s["sub_industry"],
            "企業名": s["company"],
            "求人名": s["title"],
            "判定理由": s["reason"],
        } for i, s in enumerate(scored)]
    else:
        result_data = [{
            "No.": i + 1,
            "推薦度": s["grade"],
            "業界": s["industry"],
            "業種": s["sub_industry"],
            "企業名": s["company"],
            "求人名": s["title"],
            "URL": s.get("url", ""),
            "判定理由": s["reason"],
        } for i, s in enumerate(scored)]

    result_df = pd.DataFrame(result_data)

    # フィルター
    grade_filter = st.multiselect(
        "推薦度フィルター",
        ["◎", "○", "×"],
        default=["◎", "○"],
    )
    filtered_df = result_df[result_df["推薦度"].isin(grade_filter)]
    st.dataframe(filtered_df, use_container_width=True)

    st.markdown("---")

    # ダウンロード
    st.markdown("### 💾 推薦リストをダウンロード")

    today = datetime.now().strftime("%Y%m%d")
    filename = f"推薦リスト_{candidate_name}_{today}.xlsx"

    xlsx_data = generate_recommendation_xlsx(
        scored_jobs=scored,
        candidate_name=candidate_name,
        source=source_key,
    )

    st.download_button(
        "📥 推薦リストをダウンロード (.xlsx)",
        data=xlsx_data,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    st.caption("💡 このファイルはそのまま候補者に送れるフォーマットです。")

    # 業界別サマリー
    st.markdown("---")
    st.markdown("### 📈 業界別サマリー")

    industry_data = {}
    for s in scored:
        ind = s.get("industry", "その他") or "その他"
        if ind not in industry_data:
            industry_data[ind] = {"◎": 0, "○": 0, "×": 0}
        grade = s.get("grade", "○")
        if grade in industry_data[ind]:
            industry_data[ind][grade] += 1

    if industry_data:
        ind_df = pd.DataFrame.from_dict(industry_data, orient="index")
        ind_df["合計"] = ind_df.sum(axis=1)
        ind_df = ind_df.sort_values("合計", ascending=False)
        st.dataframe(ind_df, use_container_width=True)


# ============================
# フッター
# ============================
st.markdown("---")
st.caption("求人マッチングツール v1.0 | circus & HITO-Link対応 | Powered by Claude API")
