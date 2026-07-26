/* index.html を jsdom で動かして、画面の作りが崩れていないかを確かめる。
 *
 *   node tools/test_detail.mjs
 *
 * ブラウザを開かずに済むので、手を入れるたびに流せる。
 * 実際に踏んだ抜け（描画ループ前に位置が入らない、matchMedia が無い環境で落ちる、
 * TOP から詳細へ飛んでしまう）はここで捕まえられるようにしてある。
 */
import { JSDOM } from '/tmp/jt/node_modules/jsdom/lib/api.js';
import fs from 'fs';

const html = fs.readFileSync('index.html', 'utf8');
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://nu-art.xyz/'
});
const { window } = dom;
window.scrollTo = () => {};                 // jsdom には無い
const doc = window.document;

const ok = [], fail = [];
const t = (name, cond, extra = '') => (cond ? ok : fail).push(name + (extra ? ' — ' + extra : ''));
const click = el => el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
const key   = k  => window.dispatchEvent(new window.KeyboardEvent('keydown', { key: k }));
const wait  = ms => new Promise(r => setTimeout(r, ms));
const shown = () => [...doc.querySelectorAll('.item')].filter(e => !e.classList.contains('hide'));

await wait(300);

const detail  = doc.getElementById('detail');
const navBtns = () => [...doc.querySelectorAll('#filters button')];
const label   = () => doc.querySelector('.bar-label').textContent;

/* ---------- データ ---------- */
{
  const src  = doc.documentElement.outerHTML;
  const srs  = [...src.matchAll(/sr:"([^"]+)"/g)].map(m => m[1]);
  const tops = [...src.matchAll(/,top:1/g)].length;
  const ids  = [...src.matchAll(/b:"(\d+)"/g)].map(m => m[1]);
  t('作品は40点', srs.length === 40, srs.length + '点');
  t('シリーズは6つ', new Set(srs).size === 6, [...new Set(srs)].join(' / '));
  t('TOP掲載は18点', tops === 18, tops + '点');
  t('各シリーズ3点ずつ', new Set(srs).size * 3 === tops);
  t('全作品にBASEの商品IDがある', ids.length === 40, ids.length + '件');
  t('商品IDに重複がない', new Set(ids).size === ids.length);
}

/* ---------- TOP ---------- */
t('TOPに出るのは18点', shown().length === 18, shown().length + '点');
t('ナビは Top ＋ シリーズ6つ', navBtns().length === 7, navBtns().map(b => b.textContent).join('/'));
t('ナビの先頭は Top', navBtns()[0].textContent === 'Top');
t('初期状態で詳細は閉じている', !detail.classList.contains('open'));

{
  const el = shown()[0];
  const st = (el.getAttribute('style') || '') + (el.querySelector('.shot')?.getAttribute('style') || '');
  t('作品の平均色が下地に入っている', /background/.test(st));
  t('サムネイルを参照している',
    el.querySelector('img').getAttribute('src').startsWith('images/thumbs/'));
  const tag = el.querySelector('.tag');
  t('キャプションに作品名とシリーズが出る',
    !!tag && /\S/.test(tag.textContent) && !!tag.querySelector('b') && !!tag.querySelector('span'),
    tag ? tag.querySelector('b').textContent + ' | ' + tag.querySelector('span').textContent : 'なし');
}

/* 読み込み直後に散っているか。描画ループ待ちだと裏タブで原点に固まる */
{
  const ns = [...doc.querySelectorAll('.node')];
  if (ns.length){
    const pts = ns.map(n => {
      const m = /translate3d\((-?[\d.]+)px,\s*(-?[\d.]+)px/.exec(n.style.transform || '');
      return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
    });
    t('全ノードに初期位置が入っている', pts.every(Boolean), pts.filter(Boolean).length + '/' + ns.length);
    t('原点に固まっていない', pts.filter(p => p && Math.abs(p[0]) < 1 && Math.abs(p[1]) < 1).length <= 1);
    t('位置が重複していない', new Set(pts.map(p => p && p.join(','))).size >= ns.length - 1);
  }
}

/* ---------- TOP → シリーズ ---------- */
click(shown()[0]);
await wait(150);
t('TOPから押しても詳細は開かない', !detail.classList.contains('open'));
t('シリーズ一覧に切り替わる', shown().length > 0 && shown().length !== 18, shown().length + '点');
t('見出しがシリーズ名になる', label() !== 'Selected works', label());
t('その一覧は同じシリーズだけ',
  shown().every(e => e.querySelector('.tag span').textContent === label()));

/* ---------- シリーズ → 作品詳細 ---------- */
click(shown()[0]);
await wait(280);
t('シリーズ内では詳細が開く', detail.classList.contains('open'));
t('背景スクロールが止まる', doc.body.classList.contains('locked'));

const cnt = () => doc.getElementById('dCount').textContent;
const img = doc.getElementById('dImg');
const total = +cnt().split('/')[1];
t('原画＋飾ったところで4〜6枚', total >= 4 && total <= 6, total + '枚');
t('1枚目は原画',
  img.getAttribute('src').startsWith('images/') && !img.getAttribute('src').includes('/scenes/'));
t('サムネの数が枚数と合う', doc.getElementById('dThumbs').children.length === total);

click(doc.getElementById('dNext'));
await wait(100);
t('次へで部屋の写真になる', img.getAttribute('src').includes('/scenes/'), img.getAttribute('src'));
t('カウンタが 2 になる', cnt().startsWith('2 /'), cnt());
t('サムネの現在位置が動く',
  doc.getElementById('dThumbs').children[1].getAttribute('aria-current') === 'true');

key('ArrowLeft'); await wait(80);
t('←キーで戻る', cnt().startsWith('1 /'), cnt());

{
  const before = doc.getElementById('dTitle').textContent;
  key('ArrowDown'); await wait(150);
  t('↓キーで次の作品へ', doc.getElementById('dTitle').textContent !== before,
    before + ' → ' + doc.getElementById('dTitle').textContent);
  key('ArrowUp'); await wait(150);
  t('↑キーで戻る', doc.getElementById('dTitle').textContent === before);
}

{
  const spec = doc.getElementById('dSpec').textContent;
  t('価格が出る', /¥[\d,]+/.test(spec), (spec.match(/¥[\d,]+/) || [])[0]);
  t('サイズが出る', /Size/.test(spec));
  t('BASE未公開なので購入ボタンは隠れる', doc.getElementById('dBuy').style.display === 'none');
  t('代わりに準備中の案内が出る', /準備中/.test(doc.getElementById('dNote').textContent));
}

key('Escape'); await wait(100);
t('Escで閉じる', !detail.classList.contains('open'));
t('スクロールが戻る', !doc.body.classList.contains('locked'));

/* ---------- シリーズ → TOP ---------- */
click(navBtns()[0]);
await wait(150);
t('Topに戻ると18点', shown().length === 18, shown().length + '点');
t('見出しが戻る', label() === 'Selected works', label());

/* ---------- 画像の実在 ---------- */
{
  const man = JSON.parse(fs.readFileSync('images/scenes/manifest.json', 'utf8'));
  const miss = [];
  for (const v of Object.values(man))
    for (const c of v.cuts)
      if (!fs.existsSync('images/scenes/' + c)) miss.push(c);
  t('モックアップが全部ある', miss.length === 0, miss.slice(0, 3).join(','));
  const wide = Object.values(man).filter(v => v.orient === 'wide');
  t('横長作品は横向きの額だけ',
    wide.every(v => v.scenes.every(s => ['bedroom', 'frame_wide', 'plain_wide'].includes(s))));
}

console.log('OK  (' + ok.length + ')');
ok.forEach(s => console.log('  ✓ ' + s));
if (fail.length){
  console.log('\nNG (' + fail.length + ')');
  fail.forEach(s => console.log('  ✗ ' + s));
  dom.window.close();
  process.exit(1);
}
dom.window.close();
process.exit(0);
