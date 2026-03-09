javascript:void(function(){
  /* HITO-Link 求人データ抽出ブックマークレット */
  if(!location.hostname.includes('hito-link.jp')){
    alert('HITO-Link（hito-link.jp）の検索結果ページで実行してください');return;
  }

  /* オーバーレイ表示 */
  var ov=document.createElement('div');
  ov.id='__bkm_overlay';
  ov.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:999999;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#fff;font-size:20px;font-family:sans-serif';
  ov.innerHTML='<div id="__bkm_status" style="text-align:center;line-height:1.8">&#x1F50D; 求人データを抽出中...</div>';
  document.body.appendChild(ov);
  var statusEl=document.getElementById('__bkm_status');

  /* ページネーション情報を取得 */
  function getMaxPage(){
    var links=document.querySelectorAll('a, button, [role="button"]');
    var maxP=1;
    for(var i=0;i<links.length;i++){
      var t=links[i].textContent.trim();
      if(/^\d+$/.test(t)){
        var n=parseInt(t);
        if(n>maxP)maxP=n;
      }
    }
    /* ページネーション内の「最後」ボタンや総件数から推定 */
    var pageText=document.body.innerText;
    var m=pageText.match(/(\d+)\s*件/);
    var totalItems=m?parseInt(m[1]):0;
    if(totalItems>0){
      var estimatedPages=Math.ceil(totalItems/100);
      if(estimatedPages>maxP)maxP=estimatedPages;
    }
    return maxP;
  }

  /* テキストから求人情報をパース */
  function parseJobsFromText(text, pageNum){
    var jobs=[];
    var lines=text.split('\n').map(function(l){return l.trim()}).filter(function(l){return l.length>0});

    /* HITO-Linkの求人カードはテキスト形式で表示される */
    /* 企業名、求人タイトル、年収、勤務地などを検出 */
    var currentJob=null;
    var salaryPattern=/(\d{3,4})\s*[万~～〜]\s*(\d{3,4})\s*万|年収\s*[:：]?\s*(\d{3,4})\s*[万~～〜]/;
    var locationPattern=/(北海道|青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|東京|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|京都|大阪|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)/;

    /* 求人カードの区切りを検出 - テーブルや一覧形式の解析 */
    /* HITO-Linkは案件ごとにブロックが分かれている */
    var blocks=[];
    var currentBlock=[];

    for(var i=0;i<lines.length;i++){
      var line=lines[i];
      /* 案件番号や区切りを検出 */
      if(line.match(/^(案件|求人|No\.?\s*\d|^\d+\s*[\.．])/) ||
         (line.match(/^(株式会社|合同会社|有限会社)/) && currentBlock.length>3)){
        if(currentBlock.length>0){
          blocks.push(currentBlock.join('\n'));
        }
        currentBlock=[line];
      }else{
        currentBlock.push(line);
      }
    }
    if(currentBlock.length>0)blocks.push(currentBlock.join('\n'));

    /* 各ブロックから情報を抽出 */
    for(var b=0;b<blocks.length;b++){
      var block=blocks[b];
      var blockLines=block.split('\n');

      /* 企業名を検出 */
      var company='';
      var title='';
      var salary='';
      var location='';
      var skills='';

      for(var j=0;j<blockLines.length;j++){
        var bl=blockLines[j];
        if(!company && bl.match(/(株式会社|合同会社|有限会社|\.inc|\.co)/i)){
          company=bl.replace(/^\d+[\.\s]*/, '').trim();
        }
        if(!salary){
          var sm=bl.match(salaryPattern);
          if(sm)salary=bl.trim();
        }
        if(!location){
          var lm=bl.match(locationPattern);
          if(lm)location=lm[0];
        }
        if(bl.match(/(必須|応募資格|スキル|経験|要件)/)){
          skills+=bl.trim()+' ';
        }
      }

      /* タイトルは企業名の次の行、または特徴的なキーワードを含む行 */
      for(var j=0;j<blockLines.length;j++){
        var bl=blockLines[j];
        if(bl!==company && bl.length>5 && bl.length<100 &&
           !bl.match(salaryPattern) && !bl.match(/^\d+[\.\s]*$/) &&
           (bl.match(/(セールス|営業|マネージャー|エンジニア|コンサル|マーケ|企画|カスタマー|開発|事業|リーダー|ディレクター|アドバイザー|プランナー|マネジメント)/) ||
            (!title && company && blockLines.indexOf(bl)>blockLines.indexOf(company)))){
          title=bl.replace(/^\d+[\.\s]*/, '').trim();
          break;
        }
      }

      if(company || title){
        jobs.push({
          page:pageNum,
          company:company,
          title:title,
          salary:salary,
          location:location,
          skills:skills.trim().slice(0,300)
        });
      }
    }

    return jobs;
  }

  /* 次のページへ遷移 */
  function goToNextPage(targetPage){
    var links=document.querySelectorAll('a, button, [role="button"]');
    for(var i=0;i<links.length;i++){
      if(links[i].textContent.trim()===String(targetPage)){
        links[i].click();
        return true;
      }
    }
    /* 「次へ」ボタンを探す */
    for(var i=0;i<links.length;i++){
      var t=links[i].textContent.trim();
      if(t==='次へ'||t==='次のページ'||t==='>'||t==='>>'||t.match(/next/i)){
        links[i].click();
        return true;
      }
    }
    return false;
  }

  var maxPage=getMaxPage();
  var allJobs=[];
  var currentPage=1;

  function processPage(){
    var text=document.body.innerText;
    var items=parseJobsFromText(text, currentPage);
    allJobs=allJobs.concat(items);
    statusEl.innerHTML='&#x1F4C4; ページ '+currentPage+' / '+maxPage+' 完了（'+allJobs.length+'件）';

    if(currentPage<maxPage){
      currentPage++;
      goToNextPage(currentPage);
      setTimeout(processPage,2500);
    }else{
      finalize();
    }
  }

  function finalize(){
    var result=JSON.stringify({
      source:'hito-link',
      extracted_at:new Date().toISOString(),
      total:allJobs.length,
      jobs:allJobs
    });

    navigator.clipboard.writeText(result).then(function(){
      statusEl.innerHTML='<div style="font-size:48px">&#x2705;</div><div style="font-size:24px;margin-top:12px"><b>'+allJobs.length+'件</b>の求人データをコピーしました！</div><div style="font-size:16px;margin-top:8px;color:#aaa">求人マッチングアプリに Ctrl+V で貼り付けてください</div><div style="margin-top:20px"><button onclick="document.getElementById(\'__bkm_overlay\').remove()" style="padding:12px 32px;font-size:16px;border:none;border-radius:8px;background:#4CAF50;color:#fff;cursor:pointer">閉じる</button></div>';
    }).catch(function(err){
      statusEl.innerHTML='<div style="font-size:16px;margin-bottom:8px">&#x26A0;&#xFE0F; 自動コピーに失敗しました。下のテキストを全選択してコピーしてください。</div><textarea id="__bkm_ta" style="width:80%;height:200px;font-size:12px" readonly>'+result.replace(/</g,'&lt;')+'</textarea><div style="margin-top:12px"><button onclick="document.getElementById(\'__bkm_ta\').select();document.execCommand(\'copy\')" style="padding:8px 24px;font-size:14px;border:none;border-radius:6px;background:#2196F3;color:#fff;cursor:pointer">テキストをコピー</button> <button onclick="document.getElementById(\'__bkm_overlay\').remove()" style="padding:8px 24px;font-size:14px;border:none;border-radius:6px;background:#666;color:#fff;cursor:pointer;margin-left:8px">閉じる</button></div>';
    });
  }

  processPage();
}());