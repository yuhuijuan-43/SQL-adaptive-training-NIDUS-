/* ============================================================
   试题背景滚动组件
   从 /api/ambient 拉取题目轻量标题（仅标题+难度，公开装饰数据），
   以 45° 方向从左下向右上缓慢飘过。
   用法：页面放置 <div id="ambient-bg"></div> 并引入本脚本；
   深色页面给该容器加 ambient-dark 类。
   ============================================================ */
(function () {
  'use strict';

  var CONTAINER_ID = 'ambient-bg';
  var MAX_CARDS = 14;          // 同时存在的卡片上限（性能保护）
  var SPAWN_INTERVAL = 2800;   // 生成间隔 ms
  var API = '/api/ambient';

  // 离线 / 接口失败时的回退装饰内容（SQL 关键字，非题库内容）
  var FALLBACK_KEYWORDS = [
    'SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY', 'ORDER BY', 'HAVING',
    'LIMIT', 'DISTINCT', 'CASE WHEN', 'LEFT JOIN', 'WITH ... AS', 'COUNT(*)',
    'INNER JOIN', 'UNION', 'EXISTS', 'BETWEEN', 'LIKE', 'AVG', 'SUM',
  ];

  var items = [];   // {text, diff}

  function stripSourcePrefix(title) {
    // 去掉 [Kaggle·练手题库] 之类的前缀，只留题面
    return title.replace(/^\s*\[[^\]]*\]\s*/, '');
  }

  function loadItems() {
    return fetch(API)
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (list) {
        items = (list || []).map(function (q) {
          return { text: stripSourcePrefix(q.title || ''), diff: q.difficulty || '' };
        }).filter(function (i) { return i.text; });
        if (!items.length) items = FALLBACK_KEYWORDS.map(function (t) { return { text: t, diff: '' }; });
      })
      .catch(function () { items = FALLBACK_KEYWORDS.map(function (t) { return { text: t, diff: '' }; }); });
  }

  function spawn(el) {
    if (el.querySelectorAll('.ambient-card').length >= MAX_CARDS) return;
    if (!items.length) return;
    var item = items[(Math.random() * items.length) | 0];

    var card = document.createElement('div');
    card.className = 'ambient-card';
    if (item.diff) card.classList.add('ambient-diff-' + item.diff);
    var dot = document.createElement('span');
    if (item.diff) { dot.className = 'ambient-diff ' + item.diff; card.appendChild(dot); }
    card.appendChild(document.createTextNode(item.text));
    el.appendChild(card);

    // 起点：左下区域（部分在屏幕内，保证入场可见）
    var startX = -160 - Math.random() * 240;
    var startY = window.innerHeight * (0.30 + Math.random() * 0.55);
    // 位移量：确保终点在右上屏幕外（等量位移 → 精确 45°）
    var dist = Math.max(window.innerWidth, window.innerHeight) * (1.25 + Math.random() * 1.3);
    var dur = 26 + Math.random() * 24;      // 26–50s 缓慢飘过
    var delay = Math.random() * 8;

    card.style.left = startX + 'px';
    card.style.top = startY + 'px';
    card.style.transform = 'translate(0, 0) rotate(-10deg)';
    card.style.transition = 'none';

    // 双 rAF 确保浏览器先完成初始布局再启动过渡
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        card.style.transition =
          'transform ' + dur + 's cubic-bezier(0.33, 0, 0.2, 1) ' + delay + 's, ' +
          'opacity ' + (dur * 0.9) + 's linear ' + delay + 's';
        card.style.transform = 'translate(' + dist + 'px, -' + dist + 'px) rotate(7deg)';
        card.style.opacity = '0';
      });
    });

    setTimeout(function () {
      if (card.parentNode) card.parentNode.removeChild(card);
    }, (dur + delay) * 1000 + 800);
  }

  function init() {
    var el = document.getElementById(CONTAINER_ID);
    if (!el) return;
    // 尊重系统“减少动态效果”偏好
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    loadItems();
    setInterval(function () { spawn(el); }, SPAWN_INTERVAL);
    // 立即生成几个，避免页面空白
    for (var i = 0; i < 4; i++) setTimeout(function () { spawn(el); }, i * 400);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
