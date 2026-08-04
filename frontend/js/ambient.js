/* ============================================================
   试题背景滚动组件
   从 /api/ambient 拉取题目轻量标题（仅标题+难度，公开装饰数据），
   以 45° 方向从左下向右上缓慢飘过。
   用法：页面放置 <div id="ambient-bg"></div> 并引入本脚本；
   深色页面给该容器加 ambient-dark 类。
   兼容性：系统开启“减少动态效果”时改为静态展示（不滚动但可见）。
   ============================================================ */
(function () {
  'use strict';

  var CONTAINER_ID = 'ambient-bg';
  var MAX_CARDS = 18;          // 同时存在的卡片上限（性能保护）
  var SPAWN_INTERVAL = 2200;   // 生成间隔 ms
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
        if (window.console) console.info('[ambient] 背景标题池:', items.length, '条');
      })
      .catch(function () {
        items = FALLBACK_KEYWORDS.map(function (t) { return { text: t, diff: '' }; });
      });
  }

  function buildCard(item) {
    var card = document.createElement('div');
    card.className = 'ambient-card';
    if (item.diff) {
      var dot = document.createElement('span');
      dot.className = 'ambient-diff ' + item.diff;
      card.appendChild(dot);
    }
    card.appendChild(document.createTextNode(item.text));
    return card;
  }

  // 静态模式（系统减少动态效果）：卡片固定排布、不滚动
  function spawnStatic(el) {
    if (el.querySelectorAll('.ambient-card').length >= MAX_CARDS) return;
    if (!items.length) return;
    var card = buildCard(items[(Math.random() * items.length) | 0]);
    card.classList.add('ambient-static');
    card.style.left = (Math.random() * 88) + 'vw';
    card.style.top = (10 + Math.random() * 80) + 'vh';
    el.appendChild(card);
  }

  function spawn(el) {
    if (el.querySelectorAll('.ambient-card').length >= MAX_CARDS) return;
    if (!items.length) return;
    var item = items[(Math.random() * items.length) | 0];
    var card = buildCard(item);

    // 起点：屏幕左侧偏下（部分在屏幕内，保证立刻可见）
    var startX = -60 - Math.random() * 200;
    var startY = window.innerHeight * (0.30 + Math.random() * 0.55);
    // 位移量：确保终点在右上屏幕外（等量位移 → 精确 45°）
    var dist = Math.max(window.innerWidth, window.innerHeight) * (1.25 + Math.random() * 1.3);
    var dur = 18 + Math.random() * 18;        // 18–36s 缓慢飘过
    var delay = Math.random() * 3;

    card.style.left = startX + 'px';
    card.style.top = startY + 'px';
    card.style.transform = 'translate(0, 0) rotate(-10deg)';
    card.style.transition = 'none';
    el.appendChild(card);

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
    var reducedMotion = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    loadItems();
    if (reducedMotion) {
      // 静态展示：可见但不滚动（尊重系统设置，功能不消失）
      var t = setInterval(function () { spawnStatic(el); }, 900);
      setTimeout(function () { clearInterval(t); }, 9000);  // 铺满即停
      return;
    }
    setInterval(function () { spawn(el); }, SPAWN_INTERVAL);
    // 立即生成，避免页面空白等待
    for (var i = 0; i < 4; i++) setTimeout(function () { spawn(el); }, i * 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
