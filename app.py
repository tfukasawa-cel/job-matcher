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
from utils.csv_parser import parse_circus_csv, parse_hitolink_csv, parse_bookmarklet_json, auto_detect_source
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
# パスワード認証
# ============================
def check_password():
    """パスワード認証。正しければTrueを返す。"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Secrets または環境変数からパスワードを取得
    correct_password = None
    try:
        correct_password = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        pass
    if not correct_password:
        correct_password = os.environ.get("APP_PASSWORD", "kinpica2024")

    st.markdown("## 🔒 求人マッチングツール")
    st.markdown("このアプリはパスワードで保護されています。")
    password = st.text_input("パスワード", type="password", key="login_password")
    if st.button("ログイン", type="primary"):
        if password == correct_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが正しくありません。")
    return False

if not check_password():
    st.stop()

# ============================
# セッション状態の初期化
# ============================
# APIキー: Secrets → 環境変数 → 手動入力の優先順で取得
if "api_key" not in st.session_state:
    _api_key = ""
    try:
        _api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if not _api_key:
        _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    st.session_state.api_key = _api_key
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
        ["🔧 セットアップ", "⚙️ 設定", "👤 候補者管理", "📋 求人取込 & マッチ",
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
# 🔧 セットアップページ
# ============================
if page == "🔧 セットアップ":
    st.title("🔧 セットアップ")
    st.markdown("### ブックマークレットの設置")
    st.markdown("""
    ブックマークレットは、ブラウザのブックマークバーに追加する**小さなボタン**です。
    circus や HITO-Link の検索結果ページでこのボタンを押すと、
    求人データが自動的に抽出されてクリップボードにコピーされます。
    """)

    st.markdown("---")

    st.markdown("### 設置手順")
    st.markdown("""
    **ステップ1:** ブラウザのブックマークバーを表示する
    - Chrome: `Ctrl + Shift + B`（Mac: `Cmd + Shift + B`）

    **ステップ2:** 以下のリンクをブックマークバーに**ドラッグ&ドロップ**する
    """)

    # ブックマークレットコード（ミニファイ版）
    circus_bookmarklet = """javascript:void(function(){if(!location.hostname.includes('circus-job.com')){alert('circus-job.com の検索結果ページで実行してください');return}var ov=document.createElement('div');ov.id='__bkm_overlay';ov.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:999999;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#fff;font-size:20px;font-family:sans-serif';ov.innerHTML='<div id=__bkm_status style=text-align:center;line-height:1.8>&#x1F50D; 抽出中...</div>';document.body.appendChild(ov);var statusEl=document.getElementById('__bkm_status');var prefMap={1:'北海道',2:'青森県',3:'岩手県',4:'宮城県',5:'秋田県',6:'山形県',7:'福島県',8:'茨城県',9:'栃木県',10:'群馬県',11:'埼玉県',12:'千葉県',13:'東京都',14:'神奈川県',15:'新潟県',16:'富山県',17:'石川県',18:'福井県',19:'山梨県',20:'長野県',21:'岐阜県',22:'静岡県',23:'愛知県',24:'三重県',25:'滋賀県',26:'京都府',27:'大阪府',28:'兵庫県',29:'奈良県',30:'和歌山県',31:'鳥取県',32:'島根県',33:'岡山県',34:'広島県',35:'山口県',36:'徳島県',37:'香川県',38:'愛媛県',39:'高知県',40:'福岡県',41:'佐賀県',42:'長崎県',43:'熊本県',44:'大分県',45:'宮崎県',46:'鹿児島県',47:'沖縄県'};var btns=document.querySelectorAll('button');var pages=[];for(var i=0;i<btns.length;i++){if(/^\\d+$/.test(btns[i].textContent.trim()))pages.push(Number(btns[i].textContent.trim()))}var maxPage=pages.length>0?Math.max.apply(null,pages):1;function extractPage(pn){var card=document.querySelector('[class*=JobSearchResultCard-root]');if(!card)return[];var fk=Object.keys(card).find(function(k){return k.startsWith('__reactFiber')});if(!fk)return[];var f=card[fk];for(var d=0;d<4;d++)f=f.return;var c=f,items=[],r=1;while(c){var j=c.memoizedProps&&c.memoizedProps.job;if(j){var s=j.expectedAnnualSalary||{};items.push({page:pn,rank:r++,company:(j.company&&j.company.name)||'',title:j.name||'',job_type:j.reproduction===true?'シェアリング':(j.jobPostOwnerCompany?'circus求人':'企業求人'),salary:s.min&&s.max?s.min+'万〜'+s.max+'万':(s.min?s.min+'万〜':''),location:(j.addresses||[]).map(function(a){return prefMap[a.prefecture]||''}).join(', '),skills:(j.minimumQualification||'').replace(/\\n/g,' ').slice(0,300),published_at:(j.publishStartedAt||j.openedAt||'').slice(0,10),agent_company:(j.jobPostOwnerCompany&&j.jobPostOwnerCompany.name)||''})}c=c.sibling}return items}function goTo(n){var bs=document.querySelectorAll('button');for(var i=0;i<bs.length;i++){if(bs[i].textContent.trim()===String(n)){bs[i].click();return true}}return false}var allJobs=[],cp=1;function proc(){var items=extractPage(cp);allJobs=allJobs.concat(items);statusEl.innerHTML='&#x1F4C4; '+cp+'/'+maxPage+' ('+allJobs.length+'件)';if(cp<maxPage){cp++;goTo(cp);setTimeout(proc,2500)}else{var r=JSON.stringify({source:'circus',extracted_at:new Date().toISOString(),total:allJobs.length,jobs:allJobs});navigator.clipboard.writeText(r).then(function(){statusEl.innerHTML='<div style=font-size:48px>&#x2705;</div><div style=font-size:24px;margin-top:12px><b>'+allJobs.length+'件</b>コピー完了！</div><div style=font-size:14px;margin-top:8px;color:#aaa>アプリでCtrl+V</div><div style=margin-top:20px><button onclick=document.getElementById(\\'__bkm_overlay\\').remove() style=padding:12px+32px;font-size:16px;border:none;border-radius:8px;background:#4CAF50;color:#fff;cursor:pointer>閉じる</button></div>'}).catch(function(){statusEl.innerHTML='<div>&#x26A0; コピー失敗。テキストを手動コピーしてください</div><textarea id=__bkm_ta style=width:80%;height:200px readonly>'+r.replace(/</g,'&lt;')+'</textarea><button onclick=document.getElementById(\\'__bkm_ta\\').select();document.execCommand(\\'copy\\') style=padding:8px+24px;border:none;border-radius:6px;background:#2196F3;color:#fff;cursor:pointer;margin-top:8px>コピー</button> <button onclick=document.getElementById(\\'__bkm_overlay\\').remove() style=padding:8px+24px;border:none;border-radius:6px;background:#666;color:#fff;cursor:pointer>閉じる</button>'})}}proc()}())"""

    hitolink_bookmarklet = """javascript:void(function(){if(!location.hostname.includes('hito-link.jp')){alert('HITO-Link のページで実行してください');return}var ov=document.createElement('div');ov.id='__bkm_overlay';ov.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:999999;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#fff;font-size:20px;font-family:sans-serif';ov.innerHTML='<div id=__bkm_status style=text-align:center;line-height:1.8>&#x1F50D; 抽出中...</div>';document.body.appendChild(ov);var statusEl=document.getElementById('__bkm_status');function getMaxPage(){var links=document.querySelectorAll('a,button,[role=button]');var mx=1;for(var i=0;i<links.length;i++){var t=links[i].textContent.trim();if(/^\\d+$/.test(t)){var n=parseInt(t);if(n>mx)mx=n}}var m=document.body.innerText.match(/(\\d+)\\s*件/);if(m){var ep=Math.ceil(parseInt(m[1])/100);if(ep>mx)mx=ep}return mx}function parseJobs(text,pn){var jobs=[];var lines=text.split('\\n').map(function(l){return l.trim()}).filter(function(l){return l.length>0});var salP=/(\\d{3,4})\\s*[万~～〜]\\s*(\\d{3,4})\\s*万|年収\\s*[:：]?\\s*(\\d{3,4})\\s*[万~～〜]/;var locP=/(北海道|青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|東京|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|京都|大阪|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)/;var blocks=[],cb=[];for(var i=0;i<lines.length;i++){var l=lines[i];if((l.match(/^(案件|求人|No\\.?\\s*\\d|^\\d+\\s*[\\.．])/)||(l.match(/^(株式会社|合同会社|有限会社)/)&&cb.length>3))&&cb.length>0){blocks.push(cb.join('\\n'));cb=[l]}else{cb.push(l)}}if(cb.length>0)blocks.push(cb.join('\\n'));for(var b=0;b<blocks.length;b++){var bl=blocks[b].split('\\n');var co='',ti='',sa='',lo='',sk='';for(var j=0;j<bl.length;j++){if(!co&&bl[j].match(/(株式会社|合同会社|有限会社|\\.inc|\\.co)/i))co=bl[j].replace(/^\\d+[\\. ]*/, '').trim();if(!sa){var sm=bl[j].match(salP);if(sm)sa=bl[j].trim()}if(!lo){var lm=bl[j].match(locP);if(lm)lo=lm[0]}if(bl[j].match(/(必須|応募資格|スキル|経験|要件)/))sk+=bl[j].trim()+' '}for(var j=0;j<bl.length;j++){if(bl[j]!==co&&bl[j].length>5&&bl[j].length<100&&!bl[j].match(salP)&&!bl[j].match(/^\\d+[\\. ]*$/)){if(bl[j].match(/(セールス|営業|マネージャー|エンジニア|コンサル|マーケ|企画|カスタマー|開発|事業)/)||(!ti&&co)){ti=bl[j].replace(/^\\d+[\\. ]*/, '').trim();break}}}if(co||ti)jobs.push({page:pn,company:co,title:ti,salary:sa,location:lo,skills:sk.trim().slice(0,300)})}return jobs}function goNext(n){var ls=document.querySelectorAll('a,button,[role=button]');for(var i=0;i<ls.length;i++){if(ls[i].textContent.trim()===String(n)){ls[i].click();return true}}for(var i=0;i<ls.length;i++){var t=ls[i].textContent.trim();if(t==='次へ'||t==='>'||t.match(/next/i)){ls[i].click();return true}}return false}var mx=getMaxPage(),all=[],cp=1;function proc(){var items=parseJobs(document.body.innerText,cp);all=all.concat(items);statusEl.innerHTML='&#x1F4C4; '+cp+'/'+mx+' ('+all.length+'件)';if(cp<mx){cp++;goNext(cp);setTimeout(proc,2500)}else{var r=JSON.stringify({source:'hito-link',extracted_at:new Date().toISOString(),total:all.length,jobs:all});navigator.clipboard.writeText(r).then(function(){statusEl.innerHTML='<div style=font-size:48px>&#x2705;</div><div style=font-size:24px;margin-top:12px><b>'+all.length+'件</b>コピー完了！</div><div style=font-size:14px;margin-top:8px;color:#aaa>アプリでCtrl+V</div><div style=margin-top:20px><button onclick=document.getElementById(\\'__bkm_overlay\\').remove() style=padding:12px+32px;font-size:16px;border:none;border-radius:8px;background:#4CAF50;color:#fff;cursor:pointer>閉じる</button></div>'}).catch(function(){statusEl.innerHTML='<div>&#x26A0; コピー失敗</div><textarea id=__bkm_ta style=width:80%;height:200px readonly>'+r.replace(/</g,'&lt;')+'</textarea><button onclick=document.getElementById(\\'__bkm_ta\\').select();document.execCommand(\\'copy\\') style=padding:8px+24px;border:none;border-radius:6px;background:#2196F3;color:#fff;cursor:pointer;margin-top:8px>コピー</button> <button onclick=document.getElementById(\\'__bkm_overlay\\').remove() style=padding:8px+24px;border:none;border-radius:6px;background:#666;color:#fff;cursor:pointer>閉じる</button>'})}}proc()}())"""

    st.markdown(f"""
    <div style="background:#f0f2f6;padding:20px;border-radius:10px;margin:10px 0">
        <p style="margin-bottom:12px"><strong>以下のリンクをブックマークバーにドラッグしてください：</strong></p>
        <p style="margin:8px 0">
            <a href="{circus_bookmarklet}" style="display:inline-block;padding:10px 20px;background:#FF6B35;color:#fff;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px">🎪 circus求人抽出</a>
            &nbsp;&nbsp;
            <a href="{hitolink_bookmarklet}" style="display:inline-block;padding:10px 20px;background:#2196F3;color:#fff;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px">🔗 HITO-Link求人抽出</a>
        </p>
        <p style="color:#666;font-size:13px;margin-top:8px">※リンクをクリックしても動作しません。必ずブックマークバーにドラッグしてください。</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    **ステップ3:** 使い方
    1. circus または HITO-Link で求人を検索する
    2. 検索結果ページでブックマークバーの「circus求人抽出」or「HITO-Link求人抽出」をクリック
    3. 自動で全ページの求人データが抽出され、クリップボードにコピーされる
    4. このアプリの「求人取込 & マッチ」ページで **Ctrl+V** で貼り付け
    """)

    st.markdown("---")
    st.markdown("### よくある質問")
    with st.expander("ブックマークレットとは？"):
        st.markdown("ブラウザのブックマーク（お気に入り）に保存する小さなプログラムです。通常のブックマークがURLを開くのに対し、ブックマークレットは今見ているページ上でプログラムを実行します。")
    with st.expander("候補者ごとに設定し直す必要がある？"):
        st.markdown("いいえ。ブックマークレットは一度設置すれば、どの候補者の検索でも同じものを使えます。検索条件はcircus/HITO-Linkの検索画面で変更してください。")
    with st.expander("求人が更新されたらどうなる？"):
        st.markdown("ブックマークレットはクリックした瞬間のデータを読み取ります。最新の求人を取得したい場合は、再度検索してブックマークレットを実行してください。")
    with st.expander("利用規約に問題はない？"):
        st.markdown("ブックマークレットはブラウザに表示済みの情報を読み取るだけで、新しいリクエストは送信しません。ユーザーが画面で見ている情報と同じものを取得するため、利用規約に抵触しません。")


# ============================
# ⚙️ 設定ページ
# ============================
elif page == "⚙️ 設定":
    st.title("⚙️ 設定")

    st.markdown("### Claude APIキーの設定")
    st.markdown("PDF精密採点やAIスキルマッチに使用します。")

    # Secretsで事前設定されているか判定
    _secrets_key = ""
    try:
        _secrets_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass

    if _secrets_key:
        # 管理者がSecretsで設定済み → チームメンバーは入力不要
        st.success("✅ APIキーは管理者により設定済みです。そのままお使いいただけます。")
        st.info(f"🔑 キー: `{_secrets_key[:12]}...`（セキュリティのため一部表示）")
    else:
        # Secretsに未設定 → 手動入力モード
        st.markdown("""
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
# 📋 求人取込 & スキルマッチ
# ============================
elif page == "📋 求人取込 & マッチ":
    st.title("📋 求人取込 & スキルマッチ判定")

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

    # 入力モード選択
    input_mode = st.radio(
        "データ取込方法",
        ["📋 ブックマークレットから貼り付け（推奨）", "📁 CSVファイルをアップロード"],
        horizontal=True,
    )

    st.markdown("---")

    jobs = None

    if input_mode == "📋 ブックマークレットから貼り付け（推奨）":
        st.markdown("### 📋 データ貼り付け")
        st.caption("ブックマークレットで抽出したデータを Ctrl+V で貼り付けてください。")

        pasted_json = st.text_area(
            "ここに Ctrl+V で貼り付け",
            height=150,
            placeholder='{"source":"circus","extracted_at":"...","jobs":[...]}',
            key="paste_input",
        )

        if pasted_json and pasted_json.strip():
            with st.spinner("データを読み込み中..."):
                jobs, detected_source = parse_bookmarklet_json(pasted_json.strip())

            if not jobs:
                st.error("データを読み取れませんでした。ブックマークレットで抽出したJSON形式のデータを貼り付けてください。")
                st.stop()

            source_key = detected_source if detected_source else "circus"
            st.session_state.current_source = source_key
            source_label = "circus" if source_key == "circus" else "HITO-Link"
            st.success(f"✅ {source_label} から {len(jobs)}件の求人を読み込みました")

    else:
        # ソース選択
        source = st.radio(
            "求人サイト",
            ["circus", "HITO-Link"],
            horizontal=True,
        )
        source_key = "circus" if source == "circus" else "hito-link"
        st.session_state.current_source = source_key

        st.markdown("### 📁 CSVファイルをアップロード")
        st.caption("Phase1で出力されたCSVファイル、または検索結果CSVをアップロードしてください。")

        uploaded_csv = st.file_uploader(
            "CSVファイルを選択",
            type=["csv"],
            key="csv_upload",
        )

        if uploaded_csv:
            file_content = uploaded_csv.read()

            with st.spinner("CSVを読み込み中..."):
                if source_key == "circus":
                    jobs = parse_circus_csv(file_content)
                else:
                    jobs = parse_hitolink_csv(file_content)

            if not jobs:
                st.error("求人データを読み取れませんでした。ファイル形式を確認してください。")
                st.stop()

            st.success(f"✅ {len(jobs)}件の求人を読み込みました")

    # ここから先はjobsがある場合のみ表示
    if jobs:
        # AI判定後のrerunでは、セッション状態の判定済み結果を優先使用
        stored_jobs = st.session_state.current_jobs
        if (stored_jobs
                and len(stored_jobs) == len(jobs)
                and any(j.get("match_grade") for j in stored_jobs)):
            jobs = stored_jobs

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

                def update_progress(completed, total):
                    pct = min(int(completed / total * 100), 99)
                    progress.progress(pct)
                    status.text(f"AIが判定中... {completed}/{total}件完了")

                status.text(f"全{len(jobs)}件を判定中... （10件ずつバッチ処理）")
                matched_jobs = skill_match_batch(
                    api_key=st.session_state.api_key,
                    candidate_profile=candidate["profile"],
                    jobs=jobs,
                    source=source_key,
                    progress_callback=update_progress,
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

        # セッションに保存（AI判定済みデータを上書きしない）
        if not any(j.get("match_grade") for j in jobs):
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
