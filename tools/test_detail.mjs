import { JSDOM } from '/tmp/jt/node_modules/jsdom/lib/api.js';
import fs from 'fs';

const html = fs.readFileSync('index.html','utf8');
const dom = new JSDOM(html, { runScripts:'dangerously', pretendToBeVisual:true, url:'https://nu-art.xyz/' });
const { window } = dom;
const doc = window.document;
const fail = [];
const ok   = [];
const t = (name, cond, extra='') => (cond ? ok : fail).push(name + (extra?' — '+extra:''));

await new Promise(r => setTimeout(r, 300));

// --- 壁 ---
const items = doc.querySelectorAll('.item');
t('作品が40枚ある', items.length === 40, items.length+'枚');
t('狭い環境では列組みに落ちる', doc.querySelectorAll('.col').length >= 2 || doc.querySelectorAll('.node').length > 0);
t('サムネイルを参照している',
  doc.querySelector('.item img').getAttribute('src').startsWith('images/thumbs/'),
  doc.querySelector('.item img').getAttribute('src'));
{
  const el = doc.querySelector('.item');
  const st = (el.getAttribute('style')||'') + (el.querySelector('.shot')?.getAttribute('style')||'');
  t('平均色が下地に入っている', /background/.test(st), st.slice(0,50));
}

// --- 詳細画面を開く ---
const detail = doc.getElementById('detail');
t('初期状態では詳細は閉じている', !detail.classList.contains('open'));
items[0].dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
await new Promise(r=>setTimeout(r,200));
t('クリックで詳細が開く', detail.classList.contains('open'));
t('背景スクロールが止まる', doc.body.classList.contains('locked'));

// --- スライド ---
const thumbs = doc.getElementById('dThumbs').children;
t('スライドは原画＋5カットの6枚', thumbs.length === 6, thumbs.length+'枚');
const img = doc.getElementById('dImg');
t('1枚目は原画', img.getAttribute('src').startsWith('images/') && !img.getAttribute('src').includes('scenes'),
  img.getAttribute('src'));
t('カウンタ 1/6', doc.getElementById('dCount').textContent === '1 / 6', doc.getElementById('dCount').textContent);

doc.getElementById('dNext').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
t('次へで部屋の写真になる', img.getAttribute('src') === 'images/scenes/01_1.webp', img.getAttribute('src'));
t('カウンタ 2/6', doc.getElementById('dCount').textContent === '2 / 6');
t('サムネの現在位置が動く', thumbs[1].getAttribute('aria-current') === 'true');

// 末尾から先頭へ回り込む
for (let i=0;i<4;i++) doc.getElementById('dNext').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
t('最後は 6/6 で cut5', img.getAttribute('src') === 'images/scenes/01_5.webp', img.getAttribute('src'));
doc.getElementById('dNext').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
t('末尾の次で原画に戻る', doc.getElementById('dCount').textContent === '1 / 6');

// --- 作品送り ---
doc.getElementById('dWorkNext').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
t('次の作品でタイトルが変わる', doc.getElementById('dTitle').textContent === 'Beautiful memory', doc.getElementById('dTitle').textContent);
t('次の作品のカットを見ている', doc.getElementById('dThumbs').children[1].querySelector('img').getAttribute('src') === 'images/scenes/02_1.webp');
doc.getElementById('dWorkPrev').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
t('前の作品で戻る', doc.getElementById('dTitle').textContent === 'Chopsticks');

// --- 購入ボタン（SHOP.base 未設定） ---
t('BASE未設定なら購入ボタンは隠れる', doc.getElementById('dBuy').style.display === 'none');
t('代わりにDM案内が出る', /DM/.test(doc.getElementById('dNote').textContent));

// --- キーボードと閉じる ---
window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowRight'}));
t('→キーで1枚進む', doc.getElementById('dCount').textContent === '2 / 6', doc.getElementById('dCount').textContent);
window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowLeft'}));
t('←キーで1枚戻る', doc.getElementById('dCount').textContent === '1 / 6', doc.getElementById('dCount').textContent);
window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowDown'}));
t('↓キーで次の作品', doc.getElementById('dTitle').textContent === 'Beautiful memory', doc.getElementById('dTitle').textContent);
window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowUp'}));
t('↑キーで前の作品', doc.getElementById('dTitle').textContent === 'Chopsticks');
window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape'}));
t('Escで閉じる', !detail.classList.contains('open'));
t('スクロールが戻る', !doc.body.classList.contains('locked'));

// --- 絞り込み ---
const b4 = [...doc.querySelectorAll('#filters button')].find(b=>b.textContent==='B4');
b4.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
const shown = [...doc.querySelectorAll('.item')].filter(e=>!e.classList.contains('hide')).length;
t('B4で絞れる', shown === 11, shown+'枚');
t('件数表示が追従', doc.getElementById('count').textContent === shown+' works', doc.getElementById('count').textContent);

// --- BASE 紐付け ---
const W = window.WORKS || null;
{
  const ids = [...doc.documentElement.outerHTML.matchAll(/b:"(\d+)"/g)].map(m=>m[1]);
  t('40作品すべてに商品IDがある', ids.length === 40, ids.length+'件');
  t('商品IDに重複がない', new Set(ids).size === 40);
}
// 販売開始後の表示を確認する
items[0].dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
await new Promise(r=>setTimeout(r,200));
t('準備中の案内が出る', /準備中/.test(doc.getElementById('dNote').textContent));
t('価格が仕様に出る', /¥7,000/.test(doc.getElementById('dSpec').textContent), doc.getElementById('dSpec').textContent.slice(0,60));
window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape'}));

// --- 縦横で額の向きが分かれているか ---
{
  const fs2 = await import('fs');
  const man = JSON.parse(fs2.readFileSync('images/scenes/manifest.json','utf8'));
  const wide = Object.values(man).filter(v=>v.orient==='wide');
  const tall = Object.values(man).filter(v=>v.orient==='tall');
  t('横長の作品は10点', wide.length===10, wide.length+'点');
  t('横長は横向きの額だけを使う',
    wide.every(v=>v.scenes.every(s=>['bedroom','frame_wide','plain_wide'].includes(s))),
    JSON.stringify(wide[0].scenes));
  t('縦長は横向きの額を使わない',
    tall.every(v=>v.scenes.every(s=>!['bedroom','frame_wide','plain_wide'].includes(s))));
  t('縦長は5枚', tall.every(v=>v.cuts.length===5));
  t('横長は3枚', wide.every(v=>v.cuts.length===3));
}

console.log('OK  ('+ok.length+')');
ok.forEach(s=>console.log('  ✓ '+s));
if (fail.length){ console.log('\nNG ('+fail.length+')'); fail.forEach(s=>console.log('  ✗ '+s)); process.exit(1); }
// 流れる動きの rAF ループが回り続けるので、明示的に終わらせる
dom.window.close();
process.exit(0);
