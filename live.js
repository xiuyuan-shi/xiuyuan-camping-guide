'use strict';

// External-data adapters. Each value retains its supplier, time and coordinate basis.
window.Live = (() => {
  let initialized = false,
    viewRequest = 0,
    weatherRequest = 0,
    mapRequest = 0,
    imageSequence = 0,
    detailMap = null,
    weatherWorkers = 0;
  const weatherJobs = [];
  let config,
    weatherCache = CampServices.weather,
    routeCache = CampServices.routes,
    map,
    markers,
    routeLayer,
    selected,
    weatherDay = 0,
    screen = 'list',
    observer;
  let mapRows = [];
  const money = n => Number.isFinite(n) ? Math.round(n) : '—';
  const currentIcon = c => c.weather_code === 0 && c.is_day === 0 ? 'moon' : code(c.weather_code)[1];
  const code = c => c === 0 ? ['晴', 'sun'] : c <= 2 ? ['多云', 'cloud'] : c === 3 ? ['阴', 'cloud'] : c <= 48 ? ['雾', 'mist'] : c <= 67 ? ['雨', 'cloud-rain'] : c <= 77 ? ['雪', 'cloud-snow'] : c <= 82 ? ['阵雨', 'cloud-rain'] : c <= 86 ? ['阵雪', 'cloud-snow'] : ['雷雨', 'cloud-storm'];
  function byId(id) {
    return library.records.find(r => r.id === id);
  }
  function allowed(r) {
    return [...new Map((r.displayPhotos || []).filter(CampDomain.photoAllowed).map(p => [p.url, p])).values()].slice(0, 9);
  }
  const photoLabel = p => p.kind === 'source' ? p.origin === 'public-source' ? '公开来源景观照片' : p.reviewedAt ? '来源景观配图' : p.shared ? '来源合集配图 · 地点待核' : '来源笔记配图' : '实景 · ' + (p.takenAt || '日期待补').slice(0, 10);
  function nav(r) {
    if (!r.location) return `https://uri.amap.com/search?keyword=${encodeURIComponent(r.name)}&city=杭州&view=map`;
    const o = config.origin,
      g = r.location,
      p = new URLSearchParams({
        from: `${o.longitude},${o.latitude},${o.name}`,
        to: `${g.longitude},${g.latitude},${g.travelLabel || r.name}`,
        coordinate: 'wgs84',
        mode: 'car',
        src: 'xiuyuan-camping-guide',
        callnative: '0'
      });
    return 'https://uri.amap.com/navigation?' + p;
  }
  function photoBlock(r, priority = false) {
    const ps = allowed(r),
      badge = `<button class="weather-badge" data-weather="${r.id}" aria-label="查看${esc(r.name)}天气"><span>${r.location ? '查看天气' : config ? '天气待定位' : '天气待加载'}</span></button>`;
    return ps.length ? `<div class="media"><div class="slides" data-slides="${r.id}">${ps.map((p, i) => `<button class="photo-button" data-album="${r.id}" data-index="${i}" aria-label="查看${esc(r.name)}照片第${i + 1}张"><img ${i ? 'data-src' : 'src'}="${esc(p.url)}" alt="${esc(p.label)}" style="object-position:${esc(p.objectPosition || '50% 50%')}" decoding="async" loading="${!i && priority ? 'eager' : 'lazy'}" fetchpriority="${!i && priority ? 'high' : 'auto'}" referrerpolicy="no-referrer"></button>`).join('')}</div><span class="image-label">${esc(photoLabel(ps[0]))}</span><span class="image-count">${icon('photo')}<span data-counter="${r.id}">1/${ps.length}</span></span>${badge}</div>` : `<div class="media no-photo"><button data-album="${r.id}" class="photo-empty">${icon('photo')}<span>实景照片待补充</span><small>${r.photoReview?.withheld ? '已有配图的地点或授权依据待核' : '尚无可公开展示的照片'}</small></button>${badge}</div>`;
  }
  async function getWeather(r, force = false) {
    return CampServices.getWeather(r, force);
  }
  async function getRoute(r, geometry = false) {
    return CampServices.getRoute(r, geometry);
  }
  const routeText = r => CampServices.routeText(r);
  const routeCard = r => `<div class="route-copy"><span>${esc(routeText(r))}</span>${r.location?.pointKind ? `<small>至${esc(r.location.pointKind)}</small>` : ''}</div>`;
  function wirePhotos(root = document) {
    root.querySelectorAll('[data-slides]').forEach(s => {
      if (s.dataset.wired) return;
      s.dataset.wired = '1';
      s.addEventListener('scroll', () => {
        const idx = Math.max(0, Math.min(s.children.length - 1, Math.round(s.scrollLeft / Math.max(1, s.clientWidth)))),
          r = byId(s.dataset.slides);
        s.querySelectorAll('img[data-src]').forEach(img => {
          const n = Array.from(s.children).indexOf(img.parentElement);
          if (Math.abs(n - idx) <= 1) {
            img.src = img.dataset.src;
            delete img.dataset.src;
          }
        });
        wireImages(s);
        const count = s.parentElement.querySelector('[data-counter]'),
          label = s.parentElement.querySelector('.image-label');
        if (count) count.textContent = `${idx + 1}/${s.children.length}`;
        if (label && r) label.textContent = photoLabel(allowed(r)[idx] || allowed(r)[0]);
      }, {
        passive: true
      });
    });
    wireImages(root);
  }
  function wireImages(root = document) {
    root.querySelectorAll('.photo-button>img,.album-image,.map-preview>img').forEach(img => {
      if (img.dataset.wired || !img.getAttribute('src')) return;
      img.dataset.wired = '1';
      img.dataset.originalSrc = img.getAttribute('src');
      img.dataset.originalAria = img.parentElement.getAttribute('aria-label') || img.alt;
      if (!img.id) img.id = 'gallery-image-' + ++imageSequence;
      let timer;
      const clear = () => {
        clearTimeout(timer);
        img.hidden = false;
        const host = img.parentElement;
        host?.querySelector('.image-failure')?.remove();
        const retry = host?.querySelector('[data-image-target="' + img.id + '"]');
        if (retry && retry !== host) retry.remove();
        if (host?.classList.contains('photo-button')) {
          delete host.dataset.imageRetry;
          delete host.dataset.imageTarget;
          host.setAttribute('aria-label', img.dataset.originalAria);
        }
      };
      const fail = () => {
        clearTimeout(timer);
        if (!img.isConnected) return;
        img.hidden = true;
        const host = img.parentElement;
        if (!host.querySelector('.image-failure')) {
          const message = document.createElement('span');
          message.className = 'image-failure';
          message.textContent = '图片加载失败 · 重新加载';
          message.setAttribute('role', 'status');
          host.append(message);
        }
        if (host.classList.contains('photo-button')) {
          host.dataset.imageRetry = '1';
          host.dataset.imageTarget = img.id;
          host.setAttribute('aria-label', '图片加载失败，重新加载');
        } else if (!host.querySelector('[data-image-target="' + img.id + '"]')) {
          const button = document.createElement('button');
          button.dataset.imageRetry = '1';
          button.dataset.imageTarget = img.id;
          button.textContent = '重新加载图片';
          host.append(button);
        }
      };
      const start = () => {
        timer = setTimeout(() => {
          if (!img.complete || !img.naturalWidth) fail();
        }, 12000);
      };
      img.addEventListener('load', clear);
      img.addEventListener('error', fail);
      if (img.complete) {
        if (img.naturalWidth) clear();else fail();
      } else if (img.loading === 'lazy' && window.IntersectionObserver) {
        const io = new IntersectionObserver(es => {
          if (es.some(e => e.isIntersecting)) {
            io.disconnect();
            if (img.isConnected) start();
          }
        }, {
          rootMargin: '150px'
        });
        io.observe(img);
      } else start();
      img._retryPhoto = () => {
        clear();
        start();
        const url = new URL(img.dataset.originalSrc, location.href);
        url.searchParams.set('image-retry', Date.now());
        img.src = url.href;
      };
    });
  }
  function hydrate() {
    wirePhotos($('#cards'));
    if (observer) observer.disconnect();
    const load = element => {
      if (!element.isConnected) return;
      const r = byId(element.dataset.record),
        badge = element.querySelector('.weather-badge');
      if (!r?.location) {
        if (badge) badge.textContent = config ? '天气待定位' : '天气待加载';
        return;
      }
      getRoute(r).then(() => {
        const node = element.querySelector('.route');
        if (node && element.isConnected) node.innerHTML = icon('map-pin') + routeCard(r);
      }).catch(() => {
        const node = element.querySelector('.route');
        if (node && element.isConnected) node.innerHTML = icon('map-pin') + routeCard(r);
      });
      if (badge) badge.textContent = '天气查询中';
      weatherJobs.push(async () => {
        if (!element.isConnected) return;
        try {
          const w = await getWeather(r);
          if (!element.isConnected) return;
          if (badge) {
            badge.innerHTML = icon(currentIcon(w.current)) + money(w.current.temperature_2m) + '°';
            badge.title = '模型时间 ' + w.current.time + ' · 点击查看查询时间';
          }
          const media = element.querySelector('.media');
          if (media) media.dataset.weather = /雨/.test(code(w.current.weather_code)[0]) ? 'rain' : w.current.weather_code === 0 ? 'sun' : 'cloud';
        } catch {
          if (badge && element.isConnected) badge.textContent = '天气暂不可用';
        }
      });
      drainWeather();
    };
    if (window.IntersectionObserver) {
      const io = observer = new IntersectionObserver(es => es.forEach(e => {
        if (e.isIntersecting) {
          io.unobserve(e.target);
          load(e.target);
        }
      }), {
        rootMargin: '120px'
      });
      $('#cards').querySelectorAll('[data-record]').forEach(el => io.observe(el));
    } else $('#cards').querySelectorAll('[data-record]').forEach(load);
  }
  function setPage(type, id = '', idx = '') {
    CampRouter.navigate(type, id, idx);
  }
  function closePage() {
    CampRouter.back();
  }
  function pageFrame(title, content) {
    $('#live-page').hidden = false;
    $('#live-page').innerHTML = `<header class="page-header"><button data-back aria-label="返回">${icon('chevron-left')}</button><h1 class="page-title" tabindex="-1">${esc(title)}</h1><span></span></header>${content}`;
    $('#live-page').scrollTop = 0;
    document.body.classList.add('live-open');
    window.scrollTo(0, 0);
    $('#live-page .page-title')?.focus({
      preventScroll: true
    });
  }
  function detail(id) {
    const r = byId(id);
    if (!r) return;
    pageFrame('营地详情', `${photoBlock(r)}<section class="detail-heading"><h1>${esc(r.name)}</h1><div class="rating-row">${ratingButton(r)}</div><p class="environment">${esc(CampDomain.displayTags(r).join(' · ') || '环境信息待补充')}</p></section><nav class="detail-tabs" role="tablist" aria-label="地点详情栏目"><button role="tab" id="tab-overview" aria-controls="panel-overview" aria-selected="true" tabindex="0" data-tab="overview" class="active">概览</button><button role="tab" id="tab-facilities" aria-controls="panel-facilities" aria-selected="false" tabindex="-1" data-tab="facilities">设施</button><button role="tab" id="tab-fees" aria-controls="panel-fees" aria-selected="false" tabindex="-1" data-tab="fees">费用</button><button role="tab" id="tab-feedback" aria-controls="panel-feedback" aria-selected="false" tabindex="-1" data-tab="feedback">反馈</button><button role="tab" id="tab-source" aria-controls="panel-source" aria-selected="false" tabindex="-1" data-tab="source">依据</button></nav><div class="detail-panels">
<section role="tabpanel" id="panel-overview" aria-labelledby="tab-overview" data-section="overview">${overviewIntro(r)}${practicalInfo(r)}<h2>位置与交通</h2><p>${esc(r.area)}</p>${r.location ? `<p class="location-evidence">${esc(r.location.precision)} · WGS84<br><a href="${esc(r.location.sourceUrl)}" target="_blank" rel="noopener">查看坐标来源</a></p><div id="detail-map" class="detail-map"></div><p id="detail-route">正在查询参考路线…</p><p class="fine">起点：${esc(config.origin.name)}。车程为OSRM路网估算，无实时路况；终点为区域附近可通行道路，不代表已确认营位入口。</p>` : '<p class="panel-note">具体位置尚未核实，暂不显示地图点位或该营地天气。</p>'}<h2>适合谁</h2><p>${claims(r, 'audience').length ? claims(r, 'audience').map(esc).join('；') : (r.tags || []).some(t => /^适合/.test(t)) ? esc(CampDomain.displayTags(r).filter(t => /^适合/.test(t)).join('、')) + '（资料提及，尚未独立核验）' : '暂无可靠的人群适配介绍。'}</p><div class="detail-actions"><button data-weather="${id}">营地天气</button><button data-season="${id}">观景季节</button><button data-album="${id}">查看照片</button></div>${referenceNotes(r)}</section>
<section role="tabpanel" id="panel-facilities" aria-labelledby="tab-facilities" data-section="facilities" hidden><h2>设施与规则</h2><div class="facility-grid">${[['toilet', '卫生间'], ['overnight', '过夜'], ['stove', '卡式炉 / 用火'], ['parking', '停车'], ['utilities', '水电'], ['hiking', '徒步路线']].map(([k, n]) => `<article><h3>${n}</h3><p>${claims(r, k).map(esc).join('；') || '待核实'}</p></article>`).join('')}</div><p class="panel-note">以上为来源主张，不代表已向营地确认的现行规则。</p></section>
<section role="tabpanel" id="panel-fees" aria-labelledby="tab-fees" data-section="fees" hidden><h2>费用明细</h2>${evidence(r, ['fee', 'parking']) || '<p>费用尚未补充。不推算人均消费或套餐总价。</p>'}</section>
<section role="tabpanel" id="panel-feedback" aria-labelledby="tab-feedback" data-section="feedback" hidden><h2>真实反馈与注意事项</h2>${evidence(r, ['experience', 'conflict']) || '<p>暂无已整理的体验反馈。</p>'}<p class="fine">包含原文摘要和已标注的表格摘录，不代表所有游客评价。</p></section>
<section role="tabpanel" id="panel-source" aria-labelledby="tab-source" data-section="source" hidden><h2>详情依据</h2><p class="fine">以下为营地资料与来源。最近整理：${esc(r.lastCollected)}。费用与使用规则仍以营地方现行说明为准。</p>${primaryInfo(r)}${sources(r)}</section></div><div class="detail-bottom"><button data-tab="source">查看依据</button><a href="${esc(nav(r))}" target="_blank" rel="noopener">打开导航</a></div>`);
    wirePhotos($('#live-page'));
    if (r.location && window.L) {
      const m = detailMap = L.map('detail-map', {
        scrollWheelZoom: false
      }).setView([r.location.latitude, r.location.longitude], 13);
      CampMap.attach(m, {
        compact: true,
        point: r.location
      });
      L.marker([r.location.latitude, r.location.longitude], {
        title: r.name,
        alt: r.name
      }).addTo(m).bindPopup(esc(r.name));
      getRoute(r).then(v => {
        if (screen !== 'camp' || selected !== id || !$('#detail-route')) return;
        $('#detail-route').textContent = routeText(r) + ' · 路线资料 ' + v.queriedAt.slice(0, 10);
      }).catch(e => {
        if (screen === 'camp' && selected === id && $('#detail-route')) $('#detail-route').textContent = '路线暂不可用：' + e.message;
      });
    }
  }
  function imageReferences(s) {
    const refs = (s.imageReferences || []).filter(p => p.review?.status === 'keep' && /^https?:\/\//.test(p.url));
    if (!refs.length) return '';
    return `<details><summary>来源图片线索（${refs.length}条）</summary><p class="fine">来自表格，尚未核实地点归属及拍摄日期；可能含合集图片。</p><ul>${refs.map((p, i) => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">图片线索 ${i + 1}</a>${p.referencedByNotes > 1 ? ` <small>多篇笔记共用，归属待核</small>` : ''}</li>`).join('')}</ul></details>`;
  }
  function overviewIntro(r) {
    const ps = r.overview?.paragraphs || [];
    const main = ps.filter(p => p.rowNumber).sort((a, b) => b.text.length - a.text.length)[0] || ps[0];
    const clean = s => String(s || '').replace(/^来源介绍：/, '').replace(/；未提供分地点环境。?/g, '').replace(/；固定最佳月份待核。?/g, '').trim();
    let base = clean(r.overview?.presentationIntro?.text || main?.text || '');
    const extra = ps.filter(p => p !== main).flatMap(p => clean(p.text).split(/[；。]/)).flatMap(s => s.split(/[，、]/)).map(s => s.trim()).filter(s => s && s.length > 1 && !/^(?:来源摘要|未提供|表格摘录)/.test(s) && !base.includes(s) && !base.includes(s.replace(/^可|^可以/, ''))).slice(0, 2);
    if (extra.length) base = base.replace(/[。；\s]+$/, '。') + '资料还提到' + extra.join('、') + '。';
    if (!base) base = '详细介绍待补充。';
    return `<section class="camp-intro"><h2>营地介绍</h2><p>${esc(base)}</p><button data-tab="source" class="intro-evidence">查看介绍依据 ${icon('chevron-right')}</button></section>`;
  }
  const factLabels = {
    fee: '免费/付费',
    overnight: '是否可过夜',
    stove: '是否可用卡式炉',
    toilet: '是否有厕所',
    parking: '是否可开车直达'
  };
  function factRows(row) {
    return `<div class="primary-fact-grid"><div class="wide"><strong>原表位置/地址</strong><span>${esc(row.area || '未提供')}</span></div>${Object.entries(factLabels).map(([key, label]) => `<div><strong>${label}</strong><span>${esc(row.facts[key] || '未知')}</span></div>`).join('')}<div class="wide"><strong>特色亮点</strong><span>${esc(row.highlights || '未提供')}</span></div></div>`;
  }
  function primaryInfo(r) {
    const rows = (library.verifiedRows || []).filter(v => v.recordId === r.id);
    if (!rows.length) return '';
    const conflicts = Object.entries(r.primaryFacts || {}).filter(([key, v]) => v.status === 'conflict').map(([key]) => factLabels[key]);
    return `<section class="primary-info"><h2>原表资料</h2><p class="fine">以下保留用户提供的原表内容，尚未逐项复核原文；地址可能包含其他地点信息，不作为导航或露营许可。费用、过夜、用火和设施需确认现场规则。${conflicts.length ? '合并条目中 ' + esc(conflicts.join('、')) + ' 存在不同记录，已逐行列出。' : ''}</p>${rows.map(v => `<div class="primary-row"><h3>原表记录 ${rows.indexOf(v) + 1}</h3>${factRows(v)}<a class="row-audit-link" href="#verified-row/${v.rowNumber}">查看来源详情</a></div>`).join('')}</section>`;
  }
  function practicalInfo(r) {
    const items = (r.overview?.practical || []).filter(p => p.values.length);
    return items.length ? `<h2>出行信息</h2><div class="practical-grid">${items.map(p => `<article><h3>${esc(p.label)}</h3><p>${claims(r, p.key).slice(0, 2).map(v => esc(v.replace(/^表格摘录（未复核原文）：/, ''))).join('；')}</p></article>`).join('')}</div><p class="fine">来源记录供行前参考，未确认项请向营地方核实。</p>` : '';
  }
  function noteCards(r, ids, numbered = true) {
    return ids.map((id, i) => {
      const s = library.sources[id];
      return `<article class="note-card" data-note-id="${esc(id)}"><a class="note-link" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${numbered ? `<span class="note-number">${i + 1}</span>` : ''}<span>${esc(s.title || '来源笔记')}</span>${icon('chevron-right')}</a><p>${esc(s.author || '作者未提供')} · ${esc(s.date || '日期未提供')}${r.primaryData?.sourceIds.includes(id) ? ' · 地点关联待核' : ''}</p></article>`;
    }).join('');
  }
  function workbookNotes(row) {
    return `<div class="workbook-note-group">${row.notes.map((n, i) => `<article class="note-card"><a class="note-link" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer"><span class="note-number">${i + 1}</span><span>${esc(n.title)}</span>${icon('chevron-right')}</a><p>${esc(n.author)} · ${n.association === 'matched' ? '地点关联已检查' : '地点关联待核，不作为营地事实依据'}</p></article>`).join('')}</div>`;
  }
  function referenceNotes(r) {
    const rows = (library.verifiedRows || []).filter(v => v.recordId === r.id);
    if (rows.length) return `<section class="reference-notes"><h2>来源笔记 · ${rows.length * 3} 篇</h2><p class="fine">笔记链接可供核对；地点尚未确认的链接已标记。</p>${workbookNotes(rows[0])}${rows.slice(1).map(v => `<details class="more-notes"><summary>更多来源笔记 · 3 篇</summary>${workbookNotes(v)}</details>`).join('')}</section>`;
    const ids = [...new Set(r.sourceIds)].filter(id => library.sources[id]);
    return `<section class="reference-notes"><h2>来源笔记 · ${ids.length} 篇</h2>${noteCards(r, ids.slice(0, 3))}${ids.length > 3 ? `<details class="more-notes"><summary>更多来源（${ids.length - 3}篇）</summary>${noteCards(r, ids.slice(3), false)}</details>` : ''}</section>`;
  }
  function sources(r) {
    const rows = (library.verifiedRows || []).filter(v => v.recordId === r.id);
    const workbookUrls = new Set(rows.flatMap(v => v.notes.map(n => n.url)));
    const rest = [...new Set(r.sourceIds)].filter(id => library.sources[id] && !workbookUrls.has(library.sources[id].url));
    return referenceNotes(r) + (rows.length && rest.length ? `<details class="more-notes"><summary>其他来源（${rest.length}篇）</summary>${noteCards(r, rest, false)}</details>` : '');
  }
  function verifiedPage() {
    pageFrame('资料核对', `<section class="verified-page"><h1>资料记录 · ${library.verifiedRows.length} 条</h1><p class="panel-note">每条记录均有三篇笔记链接。链接存在与地点匹配是两回事；待核条目暂不进入营地推荐。</p><label class="search"><input id="verified-search" type="search" placeholder="搜索营地名称或位置" aria-label="搜索地点资料"></label><p id="verified-count" class="fine"></p><div id="verified-list"></div></section>`);
    const field = $('#verified-search');
    field.oninput = () => renderVerifiedList(field.value);
    renderVerifiedList('');
  }
  function renderVerifiedList(query) {
    const q = query.trim().toLowerCase(),
      rows = library.verifiedRows.filter(v => !q || (v.name + ' ' + v.area).toLowerCase().includes(q));
    $('#verified-count').textContent = `找到 ${rows.length} 条 · 已合并 ${rows.filter(v => v.status === 'merge').length} 条 · 待核 ${rows.filter(v => v.status !== 'merge').length} 条`;
    $('#verified-list').innerHTML = rows.map(v => `<button class="verified-row" data-verified-row="${v.rowNumber}"><strong>${esc(v.rowNumber + '. ' + v.name)}</strong><small>${esc(v.area || '位置待核')} · ${v.status === 'merge' ? '已合并到营地详情' : '地点待核'} · 3 篇来源链接</small></button>`).join('');
  }
  function verifiedRowPage(number) {
    const row = library.verifiedRows.find(v => v.rowNumber === Number(number));
    if (!row) return;
    pageFrame('来源资料', `<section class="verified-page"><h1>${esc(row.name)}</h1><p>${esc(row.area || '位置待核')}</p><p class="panel-note">${row.status === 'merge' ? '已与现有地点合并名单；原表字段和笔记地点关联仍需核对。' : '暂未收录为可推荐营地。' + row.reason}</p>${row.recordId ? `<button class="primary" data-open="${esc(row.recordId)}">查看合并后的营地详情</button>` : ''}<h2>营地资料</h2>${factRows(row)}<h2>地点介绍</h2><p>${esc(row.description || '暂无介绍。')}</p><p class="fine">已移除容易串到其他地点的自由文本地址和通用提示；活动与设施规则需看原文或现场确认。</p><details><summary>查看完整来源描述</summary><p>${esc(row.rawDescription || '暂无介绍。')}</p></details><h2>笔记互动数据</h2><p>笔记1：点赞 ${esc(row.interactions['笔记1点赞'] ?? '未提供')} · 收藏 ${esc(row.interactions['笔记1收藏'] ?? '未提供')} · 评论 ${esc(row.interactions['笔记1评论'] ?? '未提供')}；总互动量 ${esc(row.interactions['总互动量'] ?? '未提供')}</p><h2>图片内容筛选</h2><p>${row.imageReview.supplied} 张不同图片 · ${row.imageReview.approved} 张内容通过 · ${row.imageReview.existing} 张沿用旧内容审核 · ${row.imageReview.withheld} 张未采用</p><p class="fine">内容筛选不等于地点或授权确认；相册另外执行统一发布门槛，未通过的图仅保留来源线索。</p><section class="reference-notes"><h2>来源笔记 · 3 篇</h2><p class="fine">来源链接保留，地点关联状态见每篇下方。</p>${workbookNotes(row)}</section></section>`);
  }
  function evidence(r, keys) {
    return r.evidence.map(e => {
      const fs = e.fields.filter(f => keys.includes(f.key));
      if (!fs.length) return '';
      const s = library.sources[e.sourceId];
      return `<article class="source-item">${e.caveat ? `<p class="fine">${esc(e.caveat)}</p>` : ''}${fs.map(f => `<h3>${esc(f.label)}</h3><p>${esc(f.value)}</p>`).join('')}<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.author)} · ${esc(s.date)} · 原文</a></article>`;
    }).join('');
  }
  async function weatherPage(id, force = false) {
    const r = byId(id);
    if (!r) return;
    const token = ++weatherRequest;
    pageFrame('营地天气', `<div class="weather-body"><h1>${esc(r.name)}</h1><p class="fine">地点附近的模型预报 · 非现场监测</p><div id="weather-data"><p class="panel-note">${r.location ? '正在查询当前天气与未来7天…' : config ? '参考位置尚未核实，无法查询此地点天气。' : '正在加载位置资料…'}</p></div></div>`);
    if (!r.location) return;
    try {
      const w = await getWeather(r, force);
      if (screen !== 'weather' || selected !== id || token !== weatherRequest) return;
      drawWeather(r, w);
    } catch (e) {
      if (screen === 'weather' && selected === id && token === weatherRequest && $('#weather-data')) $('#weather-data').innerHTML = `<p class="panel-note">天气查询失败：${esc(e.message)}。请重新查询。</p><button class="primary" data-retry-weather="${id}">重新查询</button>`;
    }
  }
  function drawWeather(r, w) {
    const cur = w.current,
      d = w.daily,
      i = Math.min(weatherDay, d.time.length - 1),
      text = code(cur.weather_code)[0],
      ic = currentIcon(cur);
    $('#weather-data').innerHTML = `<div class="weather-now"><div class="temperature">${icon(ic)}<strong>${money(cur.temperature_2m)}°</strong></div><p>${text} · 体感${money(cur.apparent_temperature)}°</p><small>模型时间 ${esc(cur.time.replace('T', ' '))}<br>查询 ${esc(w.queriedAt)}</small></div><div class="weather-tabs"><button data-weather-mode="now">当前天气</button><button data-weather-mode="week" class="active">7天预报</button></div><div id="current-panel" hidden><div class="weather-metrics"><div>湿度<strong>${money(cur.relative_humidity_2m)}%</strong></div><div>风速<strong>${cur.wind_speed_10m}m/s</strong></div><div>体感<strong>${money(cur.apparent_temperature)}°</strong></div></div></div><div id="week-panel"><table class="forecast-table"><thead><tr><th>日期</th><th>天气</th><th>温度</th><th>日降雨概率</th></tr></thead><tbody>${d.time.map((day, n) => `<tr class="${n === i ? 'chosen' : ''}"><td><button data-day="${n}">${day === CampDomain.today() ? '今天' : n === 1 ? '明天' : new Date(day + 'T12:00:00').toLocaleDateString('zh-CN', {
      weekday: 'short'
    })}<small>${day.slice(5)}</small></button></td><td>${icon(code(d.weather_code[n])[1])}${code(d.weather_code[n])[0]}</td><td>${money(d.temperature_2m_min[n])}–${money(d.temperature_2m_max[n])}°</td><td>${d.precipitation_probability_max[n] ?? '—'}%</td></tr>`).join('')}</tbody></table></div><h2>${i === 0 ? '今天' : d.time[i]}的风雨情况</h2><div class="weather-metrics"><div>阵风<strong>${d.wind_gusts_10m_max[i] ?? '—'}m/s</strong></div><div>降水量<strong>${d.precipitation_sum[i] ?? '—'}mm</strong></div><div>全天最低<strong>${money(d.temperature_2m_min[i])}°</strong></div><div>日落<strong>${d.sunset[i]?.slice(-5) || '—'}</strong></div></div><p class="weather-alert">预报会变化，出发前再确认。<br><small>尚未接入官方预警；没有预警信息不代表安全。</small></p><p class="fine">查询点：${esc(r.location.precision)}。<br><a href="https://open-meteo.com/" target="_blank" rel="noopener">Weather data by Open-Meteo</a> · 模型估算，非营地传感器观测。</p><button class="primary" data-open="${r.id}">查看营地详情</button><button class="refresh-weather" data-retry-weather="${r.id}">刷新天气</button>`;
  }
  function seasonPage(id) {
    const r = byId(id);
    if (!r) return;
    const v = claims(r, 'season');
    pageFrame('观景季节', `<div class="season-body"><h1>${esc(r.name)}</h1><p class="fine">长期观景资料 · 不作为未来天气预报</p><div class="season-tabs"><button data-weather="${id}">天气</button><strong>观景季节</strong></div><h2>什么时候来更漂亮</h2>${allowed(r).length ? photoBlock(r) : '<p class="panel-note">该地点的季节实拍尚未补齐。</p>'}<p>${v.map(esc).join('；') || '尚无足够依据标注最佳月份，不统一套用春秋推荐。'}</p><h2>常年观景参考</h2><div class="months">${Array.from({
      length: 12
    }, (_, i) => `<button data-month="${i + 1}">${i + 1}月</button>`).join('')}</div><p id="month-result" class="fine">选择月份查看已有拍摄记录；照片只证明拍摄当日的景观。</p>${evidence(r, ['season'])}<button class="primary" data-weather="${id}">查看近7天天气</button></div>`);
    wirePhotos($('#live-page'));
  }
  function albumPage(id, idx = 0) {
    const r = byId(id);
    if (!r) return;
    const ps = allowed(r),
      i = Math.max(0, Math.min(idx, ps.length - 1)),
      p = ps[i];
    pageFrame('营地照片', ps.length ? `<div class="album-body"><img class="album-image" src="${esc(p.url)}" alt="${esc(p.label)}" referrerpolicy="no-referrer"><div class="album-controls"><button data-album="${id}" data-index="${i - 1}" ${i === 0 ? 'disabled' : ''} aria-label="上一张">${icon('chevron-left')}</button><span>${i + 1} / ${ps.length}</span><button data-album="${id}" data-index="${i + 1}" ${i === ps.length - 1 ? 'disabled' : ''} aria-label="下一张">${icon('chevron-right')}</button></div><h2>${esc(p.label)}</h2>${p.kind === 'source' ? `<p>${p.origin === 'public-source' ? '图片来源' : '来源笔记'}：${esc(p.sourceTitle)}<br>${p.origin === 'public-source' ? '来源署名' : '笔记作者'}：${esc(p.author)}<br>拍摄日期：未提供${p.publishedAt ? `<br>来源发布日期：${esc(p.publishedAt)}` : ''}</p><p class="panel-note">${p.origin === 'public-source' ? '图片来源页明确标注该地点；历史景观照片不代表实时场景或当前营位状态。' : p.shared ? '该图来自包含多个地点的来源笔记，具体拍摄地点待核。' : '用户提供的笔记配图，具体拍摄地点与日期尚未复核。'}</p>` : `<p>拍摄日期：${esc(p.takenAt)}<br>作者：${esc(p.author)}</p><p>${esc(p.description)}</p><p class="panel-note">真实历史照片，不是实时画面；公园景观不代表已确认的露营营位。</p>`}<a href="${esc(p.originalUrl)}" target="_blank" rel="noopener">查看原图</a> · <a href="${esc(p.sourceUrl)}" target="_blank" rel="noopener">图片来源</a>${p.license ? `<p>图片许可：${p.licenseUrl ? `<a href="${esc(p.licenseUrl)}" target="_blank" rel="noopener">${esc(p.license)}</a>` : esc(p.license)} · ${esc(p.derivativeNote||'展示可能裁切，原始照片见来源链接')}</p>` : ''}</div>` : `<div class="album-body"><p class="panel-note">暂无可公开展示的照片。已有配图的拍摄地点、使用授权或可用性需补齐；来源线索保留在下方。</p>${sources(r)}</div>`);
    wireImages($('#live-page'));
  }
  function showMap() {
    if (!config || !window.L || !window.CampMap) {
      pageFrame('地图', `<p class="panel-note">${config ? '地图组件加载失败，请刷新后重试。' : '正在加载地图位置资料…'}</p>`);
      return;
    }
    document.body.classList.add('map-mode');
    $('#map-view').hidden = false;
    $('#map-open').innerHTML = icon('users') + '列表';
    $('#map-open').setAttribute('aria-label', '返回列表');
    if (!map) {
      map = L.map('camp-map', {
        zoomControl: false,
        minZoom: 6,
        maxZoom: 16
      }).setView([30.22, 120.1], 11);
      L.control.zoom({
        position: 'bottomright'
      }).addTo(map);
      CampMap.attach(map);
      markers = L.layerGroup().addTo(map);
      map.on('moveend zoomend', drawMapMarkers);
    }
    map.invalidateSize();
    updateMap(true);
  }
  function updateMap(fit = false) {
    if (!map) return;
    const rows = filtered(),
      rs = rows.filter(r => CampDomain.pointValid(r.location));
    mapRows = rs;
    $('#map-status').textContent = `${mapBounds ? '此区域 · ' : ''}已定位 ${rs.length} / ${rows.length} 处 · 参考点不等于营位入口`;
    if (routeLayer && (!rs.some(r => r.id === selected) || !rs.length)) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
    if (rs.length) {
      if (fit) map.fitBounds(rs.map(r => [r.location.latitude, r.location.longitude]), {
        paddingTopLeft: [28, 60],
        paddingBottomRight: [28, 220],
        maxZoom: 13
      });
      selectMap(rs.some(r => r.id === selected) ? selected : rs[0].id);
    } else {
      selected = null;
      $('#map-selection').innerHTML = '<p>当前筛选没有已定位的地点。</p>';
      CampMap.showPoint(map, null);
    }
    drawMapMarkers();
    $('#clear-map-area').hidden = !mapBounds;
  }
  function drawMapMarkers() {
    if (!map || !markers) return;
    markers.clearLayers();
    const points = mapRows.map((record, index) => {
      const pixel = map.latLngToContainerPoint([record.location.latitude, record.location.longitude]);
      return {x:pixel.x,y:pixel.y,record,index};
    });
    for (const group of CampDomain.clusterPoints(points)) {
      const multiple = group.items.length > 1, first = group.items[0],
        label = multiple ? `此处附近 ${group.items.length} 处地点，点击选择` : first.record.name;
      const marker = L.marker(map.containerPointToLatLng([group.x, group.y]), {
        title: label,
        alt: label,
        icon: L.divIcon({
          className: 'camp-map-pin' + (multiple ? ' camp-map-cluster' : ''),
          html: `<span data-point-count="${group.items.length}">${multiple ? group.items.length : first.index + 1}</span>`,
          iconSize: [30,30],
          iconAnchor: [15,15]
        })
      }).addTo(markers).bindTooltip(esc(label), {
        direction:'top',permanent:false,className:'camp-pin-label',offset:[0,-10]
      }).on('click', () => {
        if (!multiple) { selectMap(first.record.id); return; }
        if (routeLayer) { map.removeLayer(routeLayer); routeLayer=null; }
        mapRequest++;
        $('#map-selection').classList.remove('collapsed');
        $('#map-selection').innerHTML = `<div class="map-sheet-top"><strong>附近 ${group.items.length} 处地点</strong><span>选择地点查看详情</span></div><div class="map-cluster-list">${group.items.map(p=>`<button data-map-point="${p.record.id}">${esc(p.record.name)}</button>`).join('')}</div>`;
        CampMap.showPoint(map,null);
        if (map.getZoom() < 16) map.fitBounds(group.items.map(p=>[p.record.location.latitude,p.record.location.longitude]),{paddingTopLeft:[28,60],paddingBottomRight:[28,220],maxZoom:Math.min(16,map.getZoom()+2)});
      });
      marker.getElement()?.setAttribute('aria-label',label);
    }
  }
  function selectMap(id) {
    if (selected !== id && routeLayer) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
    selected = id;
    const token = ++mapRequest,
      r = byId(id),
      p = allowed(r)[0];
    CampMap.showPoint(map, r.location);
    $('#map-selection').innerHTML = `<div class="map-sheet-top"><strong>${esc(r.name)}</strong><button id="collapse-map">收起</button></div><div class="map-preview">${p ? `<img src="${esc(p.url)}" alt="${esc(p.label)}" referrerpolicy="no-referrer">` : ''}<div><p>${esc(CampDomain.displayTags(r).slice(0,4).join(' · ') || r.type)}</p>${ratingButton(r)}<p id="map-route">${routeText(r)}</p><small>${esc(r.location.precision)}</small></div></div><div class="map-sheet-actions"><button class="primary" data-open="${id}">查看营地详情</button><a href="${esc(nav(r))}" target="_blank" rel="noopener">导航</a><button data-route-map="${id}">路线</button></div>`;
    wireImages($('#map-selection'));
    $('#collapse-map').onclick = () => {
      $('#map-selection').classList.toggle('collapsed');
      $('#collapse-map').textContent = $('#map-selection').classList.contains('collapsed') ? '展开' : '收起';
    };
    getRoute(r).then(() => {
      if (screen === 'map' && selected === id && token === mapRequest && $('#map-route')) $('#map-route').textContent = routeText(r);
    }).catch(() => {
      if (screen === 'map' && selected === id && token === mapRequest && $('#map-route')) $('#map-route').textContent = routeText(r);
    });
  }
  async function showRoute(id) {
    const r = byId(id),
      token = ++mapRequest;
    try {
      const d = await getRoute(r, true);
      if (screen !== 'map' || selected !== id || token !== mapRequest) return;
      if (routeLayer) map.removeLayer(routeLayer);
      routeLayer = L.geoJSON(d.geometry, {
        style: {
          color: '#20584a',
          weight: 5
        }
      }).addTo(map);
      L.circleMarker([config.origin.latitude, config.origin.longitude], {
        radius: 5,
        color: '#fff',
        weight: 2,
        fillColor: '#20584a',
        fillOpacity: 1
      }).addTo(routeLayer).bindTooltip(config.origin.name + '出发', {
        permanent: false,
        direction: 'top',
        className: 'camp-pin-label'
      });
      map.fitBounds(routeLayer.getBounds(), {
        paddingTopLeft: [30, 60],
        paddingBottomRight: [30, 220]
      });
      $('#map-status').textContent = `${config.origin.name}出发 · ${routeText(r)} · 参考路线 ${d.queriedAt.slice(0, 10)}`;
    } catch (e) {
      if (screen === 'map' && selected === id && token === mapRequest) $('#map-status').textContent = e.message;
    }
  }
  async function show() {
    if (!library) return;
    const token = ++viewRequest,
      route = CampRouter.parse();
    weatherRequest++;
    mapRequest++;
    if (detailMap) {
      detailMap.remove();
      detailMap = null;
    }
    document.body.classList.remove('live-open', 'map-mode');
    $('#live-page').hidden = true;
    $('#map-view').hidden = true;
    $('#map-open').innerHTML = icon('map-2') + '地图';
    $('#map-open').removeAttribute('aria-label');
    screen = route.type;
    if (route.id) selected = route.id;
    if (route.type === 'list') {
      restoreFilters();
      render();
      CampRouter.restoreList();
      return;
    }
    if (route.type === 'map') {
      restoreFilters();
      showMap();
      return;
    }
    if (route.type === 'invalid') {
      pageFrame('链接无效', '<p class="panel-note">这个链接无法识别，请返回列表重新选择地点。</p><button class="primary" data-back>返回列表</button>');
      return;
    }
    try {
      if (route.type === 'verified' || route.type === 'verified-row') {
        pageFrame('来源资料', '<p class="panel-note">正在加载逐行来源资料…</p>');
        await CampStore.workbook(library);
        if (token !== viewRequest) return;
        if (route.type === 'verified') verifiedPage();else if (library.verifiedRows.some(v => v.rowNumber === Number(route.id))) verifiedRowPage(route.id);else pageFrame('资料未找到', '<p class="panel-note">该来源记录不存在。</p>');
        return;
      }
      const r = byId(route.id);
      if (!r) {
        const held = library.excludedPlaces?.find(p => p.id === route.id);
        pageFrame(held ? '地点暂缓展示' : '地点未找到', `<p class="panel-note">${esc(held?.reason || '这个链接中的地点不存在，请返回列表搜索。')}</p><button class="primary" data-back>返回列表</button>`);
        return;
      }
      pageFrame(r.name, '<p class="panel-note">正在加载地点详情…</p>');
      await CampStore.detail(library, route.id);
      if (token !== viewRequest) return;
      if (route.type === 'camp') detail(route.id);else if (route.type === 'weather') {
        weatherDay = 0;
        weatherPage(route.id);
      } else if (route.type === 'season') seasonPage(route.id);else if (route.type === 'photos') albumPage(route.id, route.index);
    } catch (e) {
      if (token === viewRequest) pageFrame('资料暂不可用', `<p class="panel-note">${esc(e.message)}</p><button class="primary" data-retry-page>重新加载详情</button><button data-back>返回</button>`);
    }
  }
  async function init(data) {
    if (!initialized) {
      initialized = true;
      CampMap.configure(data.basemapUrl);
      CampRouter.start(show);
      document.addEventListener('click', e => {
        const b = e.target.closest('button');
        if (!b) return;
        if (b.hasAttribute('data-back')) closePage();
        if (b.hasAttribute('data-retry-page')) show();
        if (b.hasAttribute('data-verified-row')) setPage('verified-row', b.dataset.verifiedRow);
        if (b.dataset.tab) activateTab(b.dataset.tab);
        if (b.dataset.retryWeather) weatherPage(b.dataset.retryWeather, true);
        if (b.dataset.day !== undefined) {
          const w = weatherCache.get(selected);
          if (w && !CampDomain.weatherIssue(w)) {
            weatherDay = Number(b.dataset.day);
            drawWeather(byId(selected), w);
          } else if (selected) weatherPage(selected, true);
        }
        if (b.dataset.weatherMode) {
          $('#current-panel').hidden = b.dataset.weatherMode !== 'now';
          $('#week-panel').hidden = b.dataset.weatherMode !== 'week';
          document.querySelectorAll('[data-weather-mode]').forEach(x => x.classList.toggle('active', x === b));
        }
        if (b.dataset.routeMap) showRoute(b.dataset.routeMap);
        if (b.dataset.mapPoint && mapRows.some(r=>r.id===b.dataset.mapPoint)) selectMap(b.dataset.mapPoint);
        if (b.dataset.month) {
          const r = byId(selected),
            n = Number(b.dataset.month),
            matches = allowed(r).filter(p => p.takenAt && /^\d{4}-\d{2}/.test(p.takenAt) && Number(p.takenAt.slice(5, 7)) === n);
          $('#month-result').textContent = matches.length ? `${n}月有${matches.length}张历史照片；可在相册核对日期，尚未评为最佳月份。` : `暂无${n}月的可核实观景记录。`;
        }
      });
      document.addEventListener('keydown', e => {
        const tabs = Array.from(document.querySelectorAll('.detail-tabs [role="tab"]')),
          i = tabs.indexOf(e.target);
        if (i < 0 || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const next = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        activateTab(tabs[next].dataset.tab);
        tabs[next].focus();
      });
      $('#map-open').onclick = () => setPage(screen === 'map' ? 'list' : 'map');
      $('#search-map-area').onclick = () => {
        if (!map) return;
        const b = map.getBounds();
        mapBounds = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
        render();
      };
      $('#map-fit').onclick = () => {
        mapBounds = null;
        render();
        updateMap(true);
      };
    }
    try {
      config = await CampStore.json('live-data.json?v=' + ($('meta[name=camp-live-version]')?.content || '2'), 10000);
      if (!CampDomain.pointValid(config.origin) || !config.records || !CampDomain.https(config.providers?.weather) || !CampDomain.https(config.providers?.routing)) throw Error('扩展资料格式无效');
      for (const r of data.records) {
        const extension = config.records[r.id];
        if (extension && CampDomain.pointValid(extension.location)) Object.assign(r, extension);
      }
      CampServices.configure(config);
      $('#live-status').textContent = `地图参考点 ${Object.keys(config.records).length} 处 · 入口与开放规则另行核实`;
    } catch (e) {
      config = {
        origin: {
          name: '杭州武林门地铁站'
        },
        providers: {},
        records: {}
      };
      CampServices.configure(config);
      $('#live-status').textContent = '扩展资料未能加载，文字资料与来源仍可查询';
    }
  }
  function drainWeather() {
    while (weatherWorkers < 2 && weatherJobs.length) {
      weatherWorkers++;
      Promise.resolve().then(weatherJobs.shift()).finally(() => {
        weatherWorkers--;
        drainWeather();
      });
    }
  }
  function activateTab(tab) {
    if (!['overview', 'facilities', 'fees', 'feedback', 'source'].includes(tab)) return;
    document.querySelectorAll('[data-section]').forEach(s => s.hidden = s.dataset.section !== tab);
    document.querySelectorAll('.detail-tabs [role="tab"]').forEach(b => {
      const active = b.dataset.tab === tab;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
      b.tabIndex = active ? 0 : -1;
    });
  }
  return {
    retryImage: button => document.getElementById(button.dataset.imageTarget)?._retryPhoto?.(),
    init,
    hydrate,
    photoBlock,
    allowed,
    routeText,
    routeCard,
    nav,
    getWeather,
    getRoute,
    show,
    showMap,
    updateMap,
    setPage,
    code,
    weatherCache,
    routeCache
  };
})();
