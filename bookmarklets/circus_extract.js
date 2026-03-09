javascript:void(function(){
  /* circus-job.com 求人データ抽出ブックマークレット */
  if(!location.hostname.includes('circus-job.com')){
    alert('circus-job.com の検索結果ページで実行してください');return;
  }

  /* オーバーレイ表示 */
  var ov=document.createElement('div');
  ov.id='__bkm_overlay';
  ov.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:999999;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#fff;font-size:20px;font-family:sans-serif';
  ov.innerHTML='<div id="__bkm_status" style="text-align:center;line-height:1.8">&#x1F50D; 求人データを抽出中...</div>';
  document.body.appendChild(ov);
  var statusEl=document.getElementById('__bkm_status');

  /* 都道府県マップ */
  var prefMap={1:'北海道',2:'青森県',3:'岩手県',4:'宮城県',5:'秋田県',6:'山形県',7:'福島県',8:'茨城県',9:'栃木県',10:'群馬県',11:'埼玉県',12:'千葉県',13:'東京都',14:'神奈川県',15:'新潟県',16:'富山県',17:'石川県',18:'福井県',19:'山梨県',20:'長野県',21:'岐阜県',22:'静岡県',23:'愛知県',24:'三重県',25:'滋賀県',26:'京都府',27:'大阪府',28:'兵庫県',29:'奈良県',30:'和歌山県',31:'鳥取県',32:'島根県',33:'岡山県',34:'広島県',35:'山口県',36:'徳島県',37:'香川県',38:'愛媛県',39:'高知県',40:'福岡県',41:'佐賀県',42:'長崎県',43:'熊本県',44:'大分県',45:'宮崎県',46:'鹿児島県',47:'沖縄県'};

  /* 総ページ数を取得 */
  var btns=document.querySelectorAll('button');
  var pages=[];
  for(var i=0;i<btns.length;i++){
    if(/^\d+$/.test(btns[i].textContent.trim()))pages.push(Number(btns[i].textContent.trim()));
  }
  var maxPage=pages.length>0?Math.max.apply(null,pages):1;

  /* 1ページ分のデータ抽出 */
  function extractPage(pageNum){
    var card=document.querySelector('[class*="JobSearchResultCard-root"]');
    if(!card)return[];
    var fiberKey=Object.keys(card).find(function(k){return k.startsWith('__reactFiber')});
    if(!fiberKey)return[];
    var fiber=card[fiberKey];
    for(var d=0;d<4;d++)fiber=fiber.return;
    var current=fiber,items=[],rank=1;
    while(current){
      var job=current.memoizedProps&&current.memoizedProps.job;
      if(job){
        var s=job.expectedAnnualSalary||{};
        items.push({
          page:pageNum,
          rank:rank++,
          company:(job.company&&job.company.name)||'',
          title:job.name||'',
          job_type:job.reproduction===true?'シェアリング':(job.jobPostOwnerCompany?'circus求人':'企業求人'),
          salary:s.min&&s.max?s.min+'万〜'+s.max+'万':(s.min?s.min+'万〜':''),
          location:(job.addresses||[]).map(function(a){return prefMap[a.prefecture]||''}).join(', '),
          skills:(job.minimumQualification||'').replace(/\n/g,' ').slice(0,300),
          published_at:(job.publishStartedAt||job.openedAt||'').slice(0,10),
          agent_company:(job.jobPostOwnerCompany&&job.jobPostOwnerCompany.name)||''
        });
      }
      current=current.sibling;
    }
    return items;
  }

  /* 次のページへ遷移 */
  function goToPage(num){
    var bs=document.querySelectorAll('button');
    for(var i=0;i<bs.length;i++){
      if(bs[i].textContent.trim()===String(num)){bs[i].click();return true}
    }
    return false;
  }

  /* 全ページを順に抽出 */
  var allJobs=[];
  var currentPage=1;

  function processPage(){
    var items=extractPage(currentPage);
    allJobs=allJobs.concat(items);
    statusEl.innerHTML='&#x1F4C4; ページ '+currentPage+' / '+maxPage+' 完了（'+allJobs.length+'件）';

    if(currentPage<maxPage){
      currentPage++;
      goToPage(currentPage);
      setTimeout(processPage,2500);
    }else{
      finalize();
    }
  }

  /* 完了処理: JSON生成してクリップボードへ */
  function finalize(){
    var result=JSON.stringify({
      source:'circus',
      extracted_at:new Date().toISOString(),
      total:allJobs.length,
      jobs:allJobs
    });

    navigator.clipboard.writeText(result).then(function(){
      statusEl.innerHTML='<div style="font-size:48px">&#x2705;</div><div style="font-size:24px;margin-top:12px"><b>'+allJobs.length+'件</b>の求人データをコピーしました！</div><div style="font-size:16px;margin-top:8px;color:#aaa">求人マッチングアプリに Ctrl+V で貼り付けてください</div><div style="margin-top:20px"><button onclick="document.getElementById(\'__bkm_overlay\').remove()" style="padding:12px 32px;font-size:16px;border:none;border-radius:8px;background:#4CAF50;color:#fff;cursor:pointer">閉じる</button></div>';
    }).catch(function(err){
      /* クリップボード失敗時はテキストエリアで代替 */
      statusEl.innerHTML='<div style="font-size:16px;margin-bottom:8px">&#x26A0;&#xFE0F; 自動コピーに失敗しました。下のテキストを全選択してコピーしてください。</div><textarea id="__bkm_ta" style="width:80%;height:200px;font-size:12px" readonly>'+result.replace(/</g,'&lt;')+'</textarea><div style="margin-top:12px"><button onclick="document.getElementById(\'__bkm_ta\').select();document.execCommand(\'copy\')" style="padding:8px 24px;font-size:14px;border:none;border-radius:6px;background:#2196F3;color:#fff;cursor:pointer">テキストをコピー</button> <button onclick="document.getElementById(\'__bkm_overlay\').remove()" style="padding:8px 24px;font-size:14px;border:none;border-radius:6px;background:#666;color:#fff;cursor:pointer;margin-left:8px">閉じる</button></div>';
    });
  }

  processPage();
}());