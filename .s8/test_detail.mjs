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
/* 実際のマウス操作。押す→離す。回さずに離せば「選んだ」。
   本物のブラウザでは click の宛先がすり替わるので、こちらが本筋の経路。 */
const tap = (el, dx = 0) => {
  const ev = (type, x) => el.dispatchEvent(new window.MouseEvent(type,
    { bubbles: true, clientX: x, clientY: 100 }));
  ev('pointerdown', 100);
  if (dx) ev('pointermove', 100 + dx);
  ev('pointerup', 100 + dx);
};
const key   = k  => window.dispatchEvent(new window.KeyboardEvent('keydown', { key: k }));
const wait  = ms => new Promise(r => setTimeout(r, ms));
const shown = () => [...doc.querySelectorAll('.item')].filter(e => !e.classList.contains('hide'));
const visibleNow = () => shown().length;

await wait(300);

const detail  = doc.getElementById('detail');

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
t('シリーズを選ぶ帯は無い', !doc.getElementById('works'));
t('初期状態で詳細は閉じている', !detail.classList.contains('open'));

{
  const el = shown()[0];
  t('作品の平均色が下地に入っている', /background/.test(el.getAttribute('style') || ''));
  const src = el.querySelector('img').getAttribute('src');
  t('TOPは作品そのものを出す', /^images\/thumbs\/\d\d\.webp$/.test(src), src);
  t('サムネイルが実在する', fs.existsSync(src));
  const cap = el.querySelector('.cap');
  t('ホバーで出す作品名とシリーズがある',
    !!cap && /\S/.test(cap.querySelector('.cap-title').textContent)
          && /\S/.test(cap.querySelector('.cap-size').textContent),
    cap ? cap.querySelector('.cap-title').textContent + ' | ' +
          cap.querySelector('.cap-size').textContent : 'なし');
}

/* TOPの球。読み込んだ時点で位置が入っていること。
   描画ループ待ちにすると、裏で開いたタブで原点に固まる。 */
{
  const tiles = [...doc.querySelectorAll('#field .item')];
  t('球にTOPの24点が入っている', tiles.length === 24, tiles.length + '点');
  t('一覧側は空', doc.getElementById('wall').children.length === 0);

  const read = () => tiles.map(e => {
    const m = /translate3d\((-?[\d.]+)px,\s*(-?[\d.]+)px/.exec(e.style.transform || '');
    return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
  });
  const pts = read();
  t('全部に初期位置が入っている', pts.every(Boolean), pts.filter(Boolean).length + '/' + tiles.length);
  t('原点に固まっていない',
    pts.filter(p => p && Math.abs(p[0]) < 1 && Math.abs(p[1]) < 1).length <= 1);
  t('位置が重複していない', new Set(pts.map(p => p && p.join(','))).size >= tiles.length - 1);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const spanX = Math.max(...xs) - Math.min(...xs), spanY = Math.max(...ys) - Math.min(...ys);
  t('縦にも横にも広がっている', spanX > 0 && spanY > 0 && spanX / spanY > 0.4 && spanX / spanY < 2.5,
    Math.round(spanX) + 'x' + Math.round(spanY));

  // 奥行き。手前は大きく不透明、奥は小さく薄い
  const ws = tiles.map(e => parseFloat(e.style.width));
  const op = tiles.map(e => parseFloat(e.style.opacity));
  t('大きさに手前と奥の差がある', Math.max(...ws) / Math.min(...ws) > 1.3,
    Math.round(Math.min(...ws)) + '〜' + Math.round(Math.max(...ws)) + 'px');
  // 遠近が逆だと奥のほうが大きくなる。向きまで見る
  const zi = tiles.map(e => +e.style.zIndex);
  const iF = zi.indexOf(Math.max(...zi)), iB = zi.indexOf(Math.min(...zi));
  t('手前のほうが大きい', ws[iF] > ws[iB],
    Math.round(ws[iB]) + '→' + Math.round(ws[iF]) + 'px');
  t('手前のほうが濃い', op[iF] > op[iB]);
  t('薄さにも差がある', Math.max(...op) - Math.min(...op) > 0.3);
  t('奥のものは押せない', tiles.some(e => e.style.pointerEvents === 'none'));
  t('手前のものは押せる', tiles.some(e => e.style.pointerEvents === 'auto'));

  const back = tiles.filter(e => e.style.pointerEvents === 'auto').length;
  t('押せるのはおよそ半分', back > 6 && back < 20, back + '/24');
}

/* 放っておいても回り続けるか */
{
  const tiles = [...doc.querySelectorAll('#field .item')];
  const read = () => tiles.map(e => e.style.transform);
  const a = read();
  await wait(700);
  const moved = read().filter((s, i) => s !== a[i]).length;
  t('放っておいても回り続ける', moved >= tiles.length * 0.8, moved + '/' + tiles.length + '点');
}

/* ---------- TOP → 作品詳細 ----------
   間にシリーズ一覧を挟まない。詳細の右にシリーズ全部が並ぶので不要。 */
const topTitle = shown()[0].querySelector('.cap-title').textContent;
tap(shown()[0]);
await wait(700);             // 押した1点が正面に回りきるのを待つ
// 描画が止まっていても時間で必ず進むこと。ここが伸びると「押しても何も起きない」になる。
t('TOPから押すと1秒以内に詳細が開く', detail.classList.contains('open'));
t('押した作品が開く', doc.getElementById('dTitle').textContent === topTitle,
  topTitle + ' → ' + doc.getElementById('dTitle').textContent);
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

/* 詳細画面の組み。左に戻る、中央に作品と飾ったところ、右に同シリーズと購入。 */
{
  const sib = [...doc.querySelectorAll('#dSib button')];
  const src  = doc.documentElement.outerHTML;
  const srs  = [...src.matchAll(/sr:"([^"]+)"/g)].map(m => m[1]);
  const here = doc.getElementById('dSeries').textContent;
  t('右にはそのシリーズの全作品が並ぶ',
    sib.length === srs.filter(x => x === here).length,
    here + ' ' + sib.length + '点');
  t('今見ている作品に印が付く',
    sib.filter(b => b.getAttribute('aria-current') === 'true').length === 1);
  t('シリーズ名が出る', /\S/.test(doc.getElementById('dSeries').textContent),
    doc.getElementById('dSeries').textContent);
  t('戻るボタンがある', !!doc.getElementById('dBack'));
  t('飾ったところのサムネイルは中央側にある',
    !!doc.querySelector('.d-main #dThumbs'));
  t('大きい画像も中央側', !!doc.querySelector('.d-main #dImg'));
  t('購入ボタンは右側', !!doc.querySelector('.d-side #dBuy'));

  // 右の1点を押すと、その作品に入れ替わる
  const before = doc.getElementById('dTitle').textContent;
  click(sib[sib.length - 1]);
  await wait(150);
  t('右の作品を押すと入れ替わる', doc.getElementById('dTitle').textContent !== before,
    before + ' → ' + doc.getElementById('dTitle').textContent);
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

/* ---------- 詳細 → TOP ---------- */
{
  // 大きく動かしてから離したときは「回した」ので開かない
  tap(shown()[0], 120); await wait(700);
  t('回しただけでは開かない', !detail.classList.contains('open'));

  tap(shown()[0]); await wait(700);
  t('もう一度開ける', detail.classList.contains('open'));
  click(doc.getElementById('dBack')); await wait(150);
  t('戻るボタンで閉じる', !detail.classList.contains('open'));
  t('TOPに戻っている', shown().length === 24, shown().length + '点');
}
/* ---------- 画像の実在 ---------- */
{
  const man = JSON.parse(fs.readFileSync('images/scenes/manifest.json', 'utf8'));
  const miss = [];
  for (const v of Object.values(man))
    for (const c of v.cuts)
      if (!fs.existsSync('images/scenes/' + c)) miss.push(c);
  t('モックアップが全部ある', miss.length === 0, miss.slice(0, 3).join(','));
  // 1作品の中に同じ部屋を2枚入れない。額の色が違うだけの使い回しに見える。
  const bare = id => id.replace(/_(A4|B4|A3|B3)$/, '');
  const room = id => bare(id).replace(/_(tall|wide)$/, '').replace(/_[ab]$/, '');
  const dup = Object.entries(man).filter(([, v]) => {
    const rs = v.scenes.map(room);
    return new Set(rs).size !== rs.length;
  });
  t('1作品に同じ部屋が重ならない', dup.length === 0,
    dup.slice(0, 3).map(([k, v]) => k + ':' + v.scenes.join('+')).join(' / '));

  const wide = Object.values(man).filter(v => v.orient === 'wide');
  t('横長作品は横向きの額だけ',
    wide.every(v => v.scenes.every(s => bare(s).endsWith('_wide'))),
    [...new Set(wide.flatMap(v => v.scenes))].join(','));

  // 額の内側が 1:√2（A判・B判）か。ずれていると作品の端が切れる。
  const sc = JSON.parse(fs.readFileSync('images/scene_bg/scenes.json', 'utf8'));

  /* 部屋の額が、その作品の判型のものになっているか。
     ここが揃っていないと、A4 も B3 も部屋の中で同じ大きさに見えて、
     詳細に書いてあるサイズと値段の差が伝わらない。 */
  {
    const size = [...html.matchAll(/sz:"(\w+)/g)].map(m => m[1]);
    const bad = Object.entries(man).filter(([n, v]) =>
      v.scenes.some(id => (sc[id] || {}).print !== size[+n - 1]));
    t('部屋の額は作品の判型に合っている', bad.length === 0,
      bad.slice(0, 2).map(([n, v]) => n + ':' + v.scenes.join('+')).join(' / '));

    // 同じ部屋なら、判型が大きいほど額も大きい
    const inner = id => {
      const q = sc[id].quads[0];
      return Math.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]);
    };
    const order = ['A4', 'B4', 'A3', 'B3'].map(z =>
      inner('white_ledge_a_tall' + (z === 'B3' ? '' : '_' + z)));
    t('判型が大きいほど額も大きい',
      order.every((v, i) => i === 0 || v > order[i - 1]),
      order.map(Math.round).join(' < '));
  }
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

/* 詳細は球より上に出す。
   球の1点は手前ほど z を上げるので、詳細の z がそれ以下だと
   詳細を開いても TOP の作品が上に浮いたまま残る。 */
{
  const zItem = Math.max(...[...html.matchAll(/zIndex\s*=\s*Math\.round\(\s*d\s*\*\s*(\d+)\s*\)/g)]
    .map(m => +m[1]));
  const zDetail = +(html.match(/\.detail\{[\s\S]*?z-index:\s*(\d+)/) || [])[1];
  t('詳細は球より上に出る', zDetail > zItem, '詳細' + zDetail + ' / 球' + zItem);
}

/* BASE の商品との突き合わせ。
   詳細に出しているサイズと値段が、実際に売っている商品と違うと、
   買う人は「¥10,000のB3」を見て別の商品の購入画面に飛ぶことになる。
   tools/link_base.py が BASE 側の控え。 */
{
  const py = fs.readFileSync('tools/link_base.py', 'utf8');
  const tbl = {};
  for (const m of py.matchAll(/"([^"]+)":\s*\("(\d+)",\s*"[^"]*",\s*(\d+),\s*"([^"]+)"\)/g))
    tbl[m[1].normalize('NFC')] = { id: m[2], price: +m[3], series: m[4] };
  const works = [...html.matchAll(
    /\{f:"([^"]+)",[\s\S]*?b:"(\d*)",p:(\d+),sz:"([^"]+)"[\s\S]*?sr:"([^"]+)"/g)];
  t('BASEの控えに40件そろっている', Object.keys(tbl).length === 40,
    Object.keys(tbl).length + '件');
  const gap = works.filter(w => {
    const e = tbl[w[1].replace(/\.[^.]+$/, '').normalize('NFC')];
    return !e || e.id !== w[2] || e.price !== +w[3] || e.series !== w[5];
  });
  t('値段・商品ID・シリーズがBASEの控えと合っている', gap.length === 0,
    gap.slice(0, 3).map(w => w[1]).join(' / '));
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
