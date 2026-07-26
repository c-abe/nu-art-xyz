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
  t('TOP掲載は24点', tops === 24, tops + '点');
  t('各シリーズ4点ずつ', new Set(srs).size * 4 === tops);
  t('全作品にBASEの商品IDがある', ids.length === 40, ids.length + '件');
  t('商品IDに重複がない', new Set(ids).size === ids.length);
}

/* ---------- TOP ---------- */
t('TOPに出るのは24点', shown().length === 24, shown().length + '点');
t('ナビは Top ＋ シリーズ6つ', navBtns().length === 7, navBtns().map(b => b.textContent).join('/'));
t('ナビの先頭は Top', navBtns()[0].textContent === 'Top');
t('初期状態で詳細は閉じている', !detail.classList.contains('open'));

{
  const el = shown()[0];
  t('作品の平均色が下地に入っている', /background/.test(el.getAttribute('style') || ''));
  // 壁に並ぶのは作品そのものではなく「部屋に飾った1カット目」
  const src = el.querySelector('img').getAttribute('src');
  t('壁は部屋に飾った写真を出す', /^images\/scenes\/\d\d_1\.webp/.test(src), src);
  t('壁の画像URLにも版番号が付いている', /\?v=\d+$/.test(src), src);
  t('版番号を外すと実在する', fs.existsSync(src.split('?')[0]));
  const cap = el.querySelector('.cap');
  t('キャプションに作品名とシリーズが出る',
    !!cap && /\S/.test(cap.querySelector('.cap-title').textContent)
          && /\S/.test(cap.querySelector('.cap-size').textContent),
    cap ? cap.querySelector('.cap-title').textContent + ' | ' +
          cap.querySelector('.cap-size').textContent : 'なし');
}

/* 敷き詰められているか。1行4枚で、行がそのまま1シリーズになること。 */
{
  const tiles = [...doc.querySelectorAll('.wall > .item')];
  t('壁に直接タイルが並ぶ', tiles.length === shown().length, tiles.length + '枚');
  const srs = tiles.map(e => e.querySelector('.cap-size').textContent);
  const runs = srs.filter((s, i) => s !== srs[i - 1]);
  t('シリーズが散らばらず固まっている', runs.length === new Set(srs).size,
    runs.join(' / '));
  const rows = [];
  for (let i = 0; i < srs.length; i += 4) rows.push(new Set(srs.slice(i, i + 4)));
  t('1行が1シリーズで揃う', rows.every(r => r.size === 1),
    rows.map(r => [...r].join('+')).join(' / '));
  // 行の高さが揃うか。モックの比がばらつくと段差になる
  const ar = tiles.map(e => {
    const im = e.querySelector('img');
    return (+im.getAttribute('width') / +im.getAttribute('height')).toFixed(3);
  });
  t('モックの縦横比が全部同じ', new Set(ar).size === 1, [...new Set(ar)].join(','));
}

/* 同じシリーズは同じ部屋・同じ額で撮ってあるか。
   TOPに並べたとき4枚がひとかたまりに見えるための条件。 */
{
  const man = JSON.parse(fs.readFileSync('images/scenes/manifest.json', 'utf8'));
  const bySeries = {};
  for (const v of Object.values(man)) (bySeries[v.series] ||= []).push(v.scenes[0]);
  const mixed = Object.entries(bySeries)
    .filter(([, ss]) => new Set(ss.map(s => s.replace(/_(tall|wide)$/, ''))).size > 1);
  t('シリーズごとに1カット目の部屋が揃っている', mixed.length === 0,
    mixed.map(([k]) => k).join(','));
  const rooms = new Set(Object.values(bySeries)
    .map(ss => ss[0].replace(/_(tall|wide)$/, '')));
  t('シリーズごとに違う部屋', rooms.size === Object.keys(bySeries).length,
    [...rooms].join(','));
}

/* ---------- TOP → シリーズ ---------- */
click(shown()[0]);
await wait(150);
t('TOPから押しても詳細は開かない', !detail.classList.contains('open'));
t('シリーズ一覧に切り替わる', shown().length > 0 && shown().length !== 24, shown().length + '点');
t('見出しがシリーズ名になる', label() !== 'Selected works', label());
t('その一覧は同じシリーズだけ',
  shown().every(e => e.querySelector('.cap-size').textContent === label()));

/* ---------- シリーズ → 作品詳細 ---------- */
click(shown()[0]);
await wait(280);
t('シリーズ内では詳細が開く', detail.classList.contains('open'));
t('背景スクロールが止まる', doc.body.classList.contains('locked'));

const cnt = () => doc.getElementById('dCount').textContent;
const img = doc.getElementById('dImg');
const total = +cnt().split('/')[1];
t('原画＋飾ったところが2枚以上', total >= 2, total + '枚');
t('1枚目は原画',
  img.getAttribute('src').startsWith('images/') && !img.getAttribute('src').includes('/scenes/'));
t('サムネの数が枚数と合う', doc.getElementById('dThumbs').children.length === total);

click(doc.getElementById('dNext'));
await wait(100);
t('次へで部屋の写真になる', img.getAttribute('src').includes('/scenes/'), img.getAttribute('src'));
t('画像URLに版番号が付いている（古い画像が残らない）',
  /\?v=\d+$/.test(img.getAttribute('src')), img.getAttribute('src'));
t('版番号を外すと実在する',
  fs.existsSync(img.getAttribute('src').split('?')[0]));
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
t('Topに戻ると24点', shown().length === 24, shown().length + '点');
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
    wide.every(v => v.scenes.every(s => s.endsWith('_wide'))),
    [...new Set(wide.flatMap(v => v.scenes))].join(','));

  // 額の内側が 1:√2（A判・B判）か。ずれていると作品の端が切れる。
  const sc = JSON.parse(fs.readFileSync('images/scene_bg/scenes.json', 'utf8'));
  const off = Object.entries(sc).map(([k, v]) => {
    const q = v.quads[0];
    const w = Math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]);
    const h = Math.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]);
    const r = Math.min(w, h) / Math.max(w, h);
    return [k, Math.abs(r - 1 / Math.SQRT2) / (1 / Math.SQRT2)];
  }).filter(([, d]) => d > 0.04);
  t('額の内側がA/B判の比', off.length === 0,
    off.map(([k, d]) => k + ' ' + (d * 100).toFixed(1) + '%').join(' / '));

  // 詳細画面が出すURLが、実在するファイルだけか。
  // 枚数を取り違えると、壊れた画像アイコンが並ぶ。
  const ks = [...doc.documentElement.outerHTML.matchAll(/,k:(\d+)/g)].map(m => +m[1]);
  t('全作品にカット枚数が入っている', ks.length === 40, ks.length + '件');
  const bad = [];
  ks.forEach((k, i) => {
    const n = String(i + 1).padStart(2, '0');
    if (k !== man[n].cuts.length) bad.push(n + ' 埋め込み' + k + ' 実際' + man[n].cuts.length);
    for (let c = 1; c <= k; c++)
      if (!fs.existsSync('images/scenes/' + n + '_' + c + '.webp')) bad.push(n + '_' + c);
  });
  t('出すURLが実在するファイルと一致', bad.length === 0, bad.slice(0, 3).join(' / '));

  // 額いっぱいに入っているか。余白が出ると、傾いた額で白帯が斜めに走る。
  const gen = fs.readFileSync('tools/make_mockups.py', 'utf8');
  const tol = parseFloat((gen.match(/COVER_TOLERANCE = ([\d.]+)/) || [])[1]);
  t('額いっぱいに入れる設定がある', tol > 1, 'COVER_TOLERANCE=' + tol);
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
