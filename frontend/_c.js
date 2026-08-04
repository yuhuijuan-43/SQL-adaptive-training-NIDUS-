
/* ============================================================
   中英双语（了解我们页）
   ============================================================ */
const I18N = {
  page_title: { zh: '了解我们 · SQL 自适应训练', en: 'About Us · SQL Adaptive Training' },
  nav_home: { zh: '首页', en: 'Home' },
  nav_about: { zh: '了解我们', en: 'About' },
  nav_enter: { zh: '进入平台', en: 'Enter' },
  badge_news: { zh: '平台动态 · 持续更新', en: 'Platform updates · Continuously improving' },
  page_title_h: { zh: '了解<span class="grad">我们</span>', en: 'About <span class="grad">Us</span>' },
  page_sub: { zh: '最新功能上线与平台更新动态，从这里了解我们', en: 'Latest features and platform updates — get to know us here' },
  back_home: { zh: '返回首页', en: 'Back to Home' },
  footer: { zh: '© 2026 SQL 自适应训练 · 千人千面的 SQL 学习平台 — <a href="login_glass.html">进入做题前端</a>',
            en: '© 2026 SQL Adaptive Training · A personalized SQL learning platform — <a href="login_glass.html">Enter Practice</a>' },
  pinned: { zh: '置顶', en: 'Pinned' },
  view_detail: { zh: '查看详情', en: 'View details' },
  pg_info: { zh: '共 {0} 条（含置顶）· 第 {1}/{2} 页', en: '{0} items (pinned included) · Page {1}/{2}' },
  pg_prev: { zh: '上一页', en: 'Prev' },
  pg_next: { zh: '下一页', en: 'Next' },
  sec_what: { zh: '本次更新做了什么', en: 'What this update does' },
  sec_points: { zh: '实现要点', en: 'Implementation highlights' },
  sec_thinking: { zh: '我们的开发思路', en: 'Our thinking' },
  sec_stats: { zh: '数据速览', en: 'Quick numbers' },
  got_it: { zh: '知道了', en: 'Got it' },
};

let LANG = localStorage.getItem('lang') || 'zh';
function t(key) { const e = I18N[key]; return e ? (e[LANG] || e.zh) : key; }
function tf(key) {
  const s = t(key);
  const args = Array.prototype.slice.call(arguments, 1);
  return s.replace(/\{(\d+)\}/g, (m, i) => args[+i] != null ? args[+i] : m);
}
function pick(u, en) { return LANG === 'en' ? en : u; }

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.getAttribute('data-i18n')); });
  document.querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t(el.getAttribute('data-i18n-html')); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.getAttribute('data-i18n-placeholder')); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.getAttribute('data-i18n-title')); });
  document.title = t('page_title');
  const btn = document.getElementById('langBtn');
  if (btn) btn.textContent = LANG === 'zh' ? 'English' : '中文';
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
}

function toggleLang() {
  LANG = LANG === 'zh' ? 'en' : 'zh';
  localStorage.setItem('lang', LANG);
  applyI18n();
  renderUpdates();   // 更新列表/分页/弹窗跟随语言
}
applyI18n();

/* ============================================================
   更新通知数据 + 分页 + 详情弹窗
   新条目往 UPDATES 头部插入（日期最新在前），字段说明：
   date/tag/tagText/title/desc = 列表简版
   overview = 概述；points = 实现要点；thinking = 开发思路分享；stats = 数据速览
   面向所有用户：用文字讲清「做了什么 + 为什么这么做」
   英文版：VISION_EN / UPDATES_EN（与中文数组顺序一一对应）
   ============================================================ */
/* ============================================================
   置顶条目：项目初心（时间最早，但始终排在第一页首位）
   ============================================================ */
const VISION = {
  date: '2026-06', tag: 'origin', tagText: '项目初心',
  title: '我们的设想 · 为什么做这个平台',
  desc: '我们想做的不是又一个刷题网站，而是一个「懂你」的学习引擎——记住你答对的每一题、答错的每一题，只推送你此刻最该做的那道题。',
  overview: '立项之初，团队的目标非常朴素：让 SQL 学习告别千篇一律。市面上的题库只有「题」，没有「人」——每个人从第一题刷起，会的人浪费时间，不会的人挫败放弃。我们想做的是像 Duolingo 一样的体验：系统知道你已经会了什么，然后给你刚刚好的挑战。',
  points: [
    '<b>千人千面</b>：每个用户的学习路径不同——基础好的直接从多表连接起步，基础弱的先巩固 SELECT，不做统一进度的流水线。',
    '<b>知识图谱驱动</b>：37 个知识点按依赖关系织成地图，学 JOIN 之前必须先掌握 SELECT，杜绝知识断层。',
    '<b>算法内核</b>：贝叶斯知识追踪（BKT）维护掌握度画像，Thompson 采样在「巩固已知」与「探索未知」间动态平衡，答错的知识点自动加权强化。',
    '<b>务实路线</b>：MVP 用 Flask + SQLite 快速验证学习闭环，先跑通「答题 → 画像更新 → 智能推荐」，再谈规模与扩展。'
  ],
  thinking: '团队最初的设想很简单：学习不该是题海战术，而是一场「刚刚好」的挑战——太难劝退，太易无聊。我们希望每个用户打开平台时，看到的下一道题就是此刻最适合他的那一道。这条路还很长，但方向我们始终相信：让机器读懂人的学习，把人从重复劳动里解放出来。这个初心不会变，后续的每一次更新都朝着它走。',
  stats: [['37', '知识点图谱'], ['3', '自适应阶段'], ['0→1', '从立项到上线']]
};

const UPDATES = [
  {
    date: '2026-08-03', tag: 'new', tagText: '新功能',
    title: '玻璃拟态门户体系上线',
    desc: '全新门户首页 + 登录注册页上线，全站统一浅色玻璃拟态风格，路径改为「门户 → 登录 → 做题」三级流转。',
    overview: '参照 DeepSeek / Codex 等大厂前端风格，为平台打造了完整的对外门户：品牌门户首页、了解我们动态页、玻璃拟态登录注册页，并将做题前端同步改版为同一设计语言。',
    points: [
      '<b>门户首页</b>：左右分栏布局，左侧品牌文案与数据背书，右侧「进入平台 / 了解我们」双入口卡片；全站统一浅色玻璃拟态（磨砂卡片 + 漂浮光球 + 蓝紫渐变）。',
      '<b>登录注册页</b>：登录/注册选项卡，集成随机用户名、随机安全密码、密码强度检测等工具；图标全部换用 Lucide 线性 SVG，无卡通 emoji。',
      '<b>做题页改版</b>：白底界面升级为玻璃拟态，导航、卡片、按钮全量统一；摸底小测功能正式下线，聚焦自适应进阶、自主练习、真题测试、错题集四大模块。',
      '<b>品牌化</b>：接入 NIDUS 品牌 logo（透明底处理），页脚文案去除技术栈信息。'
    ],
    thinking: '产品要有门面：用户第一眼看到的页面决定了第一印象。我们专门花了一轮打磨对外门户——统一的视觉语言让「门户、登录、做题」看起来像一个完整的产品，而不是三个拼凑的页面。同时明确产品边界：摸底小测不是我们的特色，砍掉它，把资源聚焦到自适应引擎这条主线上。',
    stats: [['3', '级页面体系'], ['4', '个页面改版'], ['0', 'CDN 依赖']]
  },
  {
    date: '2026-08-03', tag: 'new', tagText: '新功能',
    title: '自定义级联分类筛选器',
    desc: '题库分类筛选升级为悬停级联面板——鼠标滑过大分类即显示子分类，自由切换不锁定，选中后可一键清除。',
    overview: '把分类筛选从传统的下拉框升级为「悬停级联」交互：鼠标滑过大分类立即预览其下的子分类，可自由跨分类切换，不再有旧版选中后无法灵活更换的问题。',
    points: [
      '<b>交互方式</b>：鼠标悬停即弹出子分类面板，移开片刻后面板自动收起；选中的筛选会以「✕ 标签」形式挂在筛选栏右侧，点击即可一键清除。',
      '<b>不锁定原则</b>：面板只是「预览层」，从选定到反悔都是一次连续动作——看到哪层到哪层，随时可以换，不再强制先切回「全部」。',
      '<b>一致性</b>：题型、难度、分类三组筛选统一样式与高度，视觉上是一套控件。'
    ],
    thinking: '最初的下拉框是平铺列表，想换分类得先切回「全部」再重选，误操作率高、路径也长。我们的核心思路是把「选完再改」变成「先看后定」——让筛选像逛菜单一样轻松，滑过即预览、离开不锁定，选中后还能一键反悔。筛选不该是负担，而应是探索题库的入口。',
    stats: [['6 条', '新增样式规则'], ['5 个', '交互状态'], ['200ms', '面板收起延迟']]
  },
  {
    date: '2026-08-02', tag: 'fix', tagText: '修复',
    title: '层级分类筛选 + 难度筛选修复',
    desc: '难度筛选改为全量题目统一生效（含静态选择题）；分类筛选升级为知识图谱层级结构，支持逐级下钻。',
    overview: '两个筛选问题修复：难度筛选此前只作用于部分题目，另一些题完全不响应；分类下拉框则是平铺列表，无法体现知识点间的从属关系。',
    points: [
      '<b>难度筛选统一生效</b>：把难度过滤从「后端局部过滤」改为「前端全量统一过滤」，无论题目来自哪个题库，筛选结果一视同仁。',
      '<b>分类层级化</b>：筛选选项直接复用知识图谱的层级关系——选大分类自动覆盖其全部子知识点，选具体子节点则只匹配该点。',
      '<b>静态题映射</b>：静态选择题也建立了到知识节点的映射，保证它们和动态题一样参与层级筛选。'
    ],
    thinking: '筛选的本质是「帮用户把题库读薄」。平铺的 29 个标签无法传达知识点之间的关系，而知识图谱本身就是现成的层级字典——我们让它直接驱动筛选：选「多表连接」就是连同它的内连接、左连接、自连接一起看。难度筛选的修复则是原则问题：规则要么对所有题生效，要么就别叫规则。',
    stats: [['29 个', '标签接入层级'], ['58 道', '静态题纳入过滤'], ['2 个', '筛选问题修复']]
  },
  {
    date: '2026-08-02', tag: 'bank', tagText: '题库扩充',
    title: '牛客 182 题标准答案全部生成',
    desc: '用大模型逐题生成答案并在真实数据库执行验证、自动重试修正。题库总量增至 507 题，上线 50 道笔试真题。',
    overview: '牛客采集的 182 道题全部缺少标准答案。我们搭了一条「生成-验证-修复」流水线：大模型逐题写答案 → 放进数据库真实执行 → 结果不对就让模型重试，最终 182/182 全部通过执行验证。',
    points: [
      '<b>机器可验证</b>：每道题的答案必须能在数据库里执行成功并产出结果，而不是「看起来合理」——用执行结果代替人工抽检。',
      '<b>自动修复闭环</b>：首轮生成后分批修复：类型转换误伤列名、MySQL 方言缺少关键字、建表语句分散在多文件等，都是「答了但跑不通」的典型案例。',
      '<b>分轨入库</b>：入门 / 必知必会 / 热题进入自主练习（增至 457 题）；大厂笔试真题单独成册（50 题），练习与测试分开。'
    ],
    thinking: '182 道题没有参考答案，等于有卷子没答案。人工逐题手写量大且容易出错，我们的思路是「让机器做裁判」：大模型负责生成、数据库负责验证，不合格就重来。踩过的坑（改类型把列名也改了、方言差异、路径兼容）本身就是一次很好的实践——题库质量的底线应该是「每条答案可执行、可复现」，而不是「有人看过」。',
    stats: [['182/182', '答案验证通过'], ['457', '自主练习总量'], ['50', '笔试真题']]
  },
  {
    date: '2026-07-31', tag: 'opt', tagText: '优化',
    title: '知识图谱重构上线',
    desc: '图谱升级为 37 节点三层结构（根 → 7 大分类 → 29 子节点），学习路径一目了然，推荐权重重排。',
    overview: '知识图谱重构为清晰的三层结构：一个根节点、7 大分类（增删改、表定义、函数、连接、约束、子查询、查询）、29 个子知识点。图谱同时驱动解锁规则与推荐权重，学习路径收敛成一张可读的地图。',
    points: [
      '<b>权重重排</b>：做对过的题大幅降低推送优先级；没做过的题优先推送；答错过的题 ×1.5 加权强化练习。',
      '<b>60% 巩固规则</b>：当前知识点的答对率不足 60% 时强制停留练习，达标才推下一个知识点，保证基础不虚。',
      '<b>解锁链修复</b>：发现旧逻辑下「答对选择题永远解锁不了填空题」的断链问题——改为首次答对进阶选择题即解锁全部填空题并立即推送一道。'
    ],
    thinking: '旧图谱和题目关联松散，用户看不清「该学什么、学到哪了」。这次重构的核心是收敛：把学习路径收成一张 37 节点的地图，7 大分类打底、知识点挂在其下；同时把推荐逻辑和地图对齐——按掌握度配权重、按答对率卡进度。过程中暴露的解锁断链是最大收获：自适应系统最怕的是一环扣不上，用户就永远到不了下一环。',
    stats: [['37', '节点总数'], ['29', '知识标签'], ['60%', '掌握阈值']]
  },
  {
    date: '2026-07-30', tag: 'fix', tagText: '修复',
    title: 'LeetCode 310 题标准答案更新',
    desc: '批量更新标准答案，295 题通过真实执行生成预期输出；为 MySQL 方言新增翻译层，移除 15 道不兼容题。',
    overview: '310 道题有标准答案但没有可运行的预期输出，判题机无法工作。我们让答案在数据库里真实执行生成输出表格，并为此解决了 MySQL 与 SQLite 的方言差异；3 道答案本身有误的题做了人工修正。',
    points: [
      '<b>真实执行出预期</b>：判题对比的是「实际跑出来的结果」，而不是手写的参考表——295 题成功生成。',
      '<b>方言翻译层</b>：MySQL 特有语法（枚举类型、日期格式化、字段类型差异等）在移植时做了逐项适配。',
      '<b>果断裁剪</b>：15 道涉及正则、函数定义等无法在 SQLite 运行的功能，直接移除——判题准确比题量数字更重要。'
    ],
    thinking: '判题机的底线是「你的答案真的能跑出那个结果」。我们把 310 道题的答案全部放进数据库执行了一遍，跑不通就查原因：方言差异写翻译层，答案本身错了就人工修，实在跑不了的 15 道果断移除。题量是可以再补的，但「判错」会直接击穿用户信任——数据质量优先于数量。',
    stats: [['295', '题验证通过'], ['15', '题果断移除'], ['3', '题人工修正']]
  },
    {
    date: '2026-07-28', tag: 'new', tagText: '新功能',
    title: '深度模式上线',
    desc: '选择题答对后自动推送同知识点填空题，举一反三，形成「概念记忆 → 实战验证」的学习闭环。',
    overview: '深度模式上线：选择题答对后自动推送同一知识点的填空题——概念题是预习，填空题才是实战，趁热打铁。',
    points: [
      '<b>深度模式</b>：答对选择题后自动推送同一知识点的填空题——概念题是预习，填空题才是实战，趁热打铁。',
      '<b>解锁规则</b>：首次答对基础题解锁全部选择题；首次答对进阶题直接解锁全部填空题并立即推送一道；答错则留在当前知识点巩固。'
    ],
    thinking: '选择题能检验「认不认识」，填空题才能检验「会不会写」——只刷选择题容易产生「我懂了」的错觉。深度模式的思路是概念题答对立刻上实战题，趁热打铁形成闭环，把「看懂」真正变成「会写」。',
    stats: [['1', '个核心功能'], ['4', '条解锁规则'], ['×1.5', '答错强化权重']]
  },,
  {
    date: '2026-07-25', tag: 'opt', tagText: '优化',
    title: '题库导入与标签难度同步',
    desc: '58 道静态选择题解析入库；全库 371 道题统一难度与知识标签口径，修正 272 题数据问题。',
    overview: '题库来自多个渠道（采集、表格、手工页面），格式五花八门。这次做了一次系统性对齐：统一 371 道题的难度与知识标签口径，并顺手修复了标签分隔符不一致、编码乱码等数据质量问题。',
    points: [
      '<b>静态题入库</b>：58 道基础/进阶选择题（含建表、选项、预期输出）完整解析导入，补上填空之外的题型拼图。',
      '<b>口径统一</b>：全库 371 道题的难度与知识标签与标准表逐一对齐，筛选和星级显示从此口径一致。',
      '<b>数据净化</b>：批量修复 272 道题的标签分隔符不一致，并解决编码乱码导致的星级读取失败。'
    ],
    thinking: '题库是产品的地基，而多来源汇集的数据最怕口径不一——同一个知识点有的题叫「窗口函数」有的叫「排名函数」，筛选就会漏题。这次对齐的收益不在表面：难度、标签、编码这些看不见的数据口径统一后，筛选、推荐、统计才能建立在可信的基础上。地基修好了，上面才能盖楼。',
    stats: [['58', '题静态导入'], ['371', '题同步对齐'], ['272', '题数据修复']]
  }
];

/* ============================================================
   英文版内容（与上方 VISION / UPDATES 顺序一一对应）
   ============================================================ */
const VISION_EN = {
  date: '2026-06', tag: 'origin', tagText: 'Our Vision',
  title: 'Our vision · why we built this platform',
  desc: 'We didn\'t want to build just another question bank — we built a learning engine that knows you: it remembers every question you got right and wrong, and only serves the one you need right now.',
  overview: 'At the start, our goal was simple: make SQL learning anything but one-size-fits-all. Question banks on the market have "questions" but no "learner" — everyone starts from question one, so people who already know the material waste time, and people who don\'t get discouraged and quit. We wanted a Duolingo-like experience: the system knows what you already know, and hands you exactly the right level of challenge.',
  points: [
    '<b>Tailored to you</b>: every learner takes a different path — strong students start with multi-table joins, beginners consolidate SELECT first. No uniform assembly line.',
    '<b>Knowledge-graph driven</b>: 37 knowledge points woven into a dependency map — you master JOIN only after SELECT, with no knowledge gaps.',
    '<b>Algorithm core</b>: Bayesian Knowledge Tracing (BKT) maintains a mastery profile; Thompson sampling balances "reinforce what you know" against "explore what you don\'t" — wrong answers automatically get extra weight.',
    '<b>Pragmatic roadmap</b>: the MVP uses Flask + SQLite to validate the learning loop fast — first prove "answer → profile update → smart recommendation", then scale.'
  ],
  thinking: 'Our original idea was simple: learning shouldn\'t be a war of attrition, but a challenge that fits — too hard discourages, too easy bores. We want every learner, on opening the platform, to find that the next question is exactly the one they need right now. The road is long, but we believe in the direction: let machines understand how people learn, and free people from repetitive work. This vision won\'t change — every update moves toward it.',
  stats: [['37', 'knowledge points'], ['3', 'adaptive phases'], ['0→1', 'from idea to launch']]
};

const UPDATES_EN = [
  {
    date: '2026-08-03', tag: 'new', tagText: 'New Feature',
    title: 'Glassmorphism portal system launched',
    desc: 'A brand-new portal homepage and login/register pages are live, unifying the whole site in a light glassmorphism style. The flow is now "Portal → Login → Practice".',
    overview: 'Following the design language of leading products like DeepSeek and Codex, we built a complete public-facing portal: a branded homepage, an "About us" updates page, and a glassmorphism login/register page — with the practice frontend redesigned in the same visual language.',
    points: [
      '<b>Portal homepage</b>: split layout — brand copy and data highlights on the left, "Enter Platform / About Us" entry cards on the right; whole site in light glassmorphism (frosted cards + floating orbs + blue-purple gradient).',
      '<b>Login/register page</b>: tabbed login and registration with random username, random secure password and password-strength tools; all icons replaced with Lucide line SVGs, no cartoon emoji.',
      '<b>Practice page redesign</b>: the flat white UI upgraded to glassmorphism — navigation, cards and buttons unified; the diagnostic test was retired to focus on four modules: adaptive journey, self practice, exam tests and wrong-answer review.',
      '<b>Branding</b>: NIDUS brand logo integrated (transparent background); tech-stack details removed from the footer.'
    ],
    thinking: 'A product needs a face: the first page a user sees shapes their first impression. We spent a full round polishing the public portal — one unified visual language makes "portal, login, practice" feel like one complete product rather than three stitched-together pages. We also clarified the product boundary: the diagnostic test wasn\'t our differentiator, so we cut it and focused resources on the adaptive engine — the main thread.',
    stats: [['3', 'page tiers'], ['4', 'pages redesigned'], ['0', 'CDN dependencies']]
  },
  {
    date: '2026-08-03', tag: 'new', tagText: 'New Feature',
    title: 'Custom cascading category filter',
    desc: 'Question-bank filtering upgraded to a hover-cascade panel — hover over a major category to preview its subcategories, switch freely without locking in, and clear with one click.',
    overview: 'We upgraded category filtering from a traditional dropdown to a "hover cascade" interaction: hovering over a major category instantly previews its subcategories, and you can switch across categories freely — no more being stuck with a previous selection.',
    points: [
      '<b>Interaction</b>: hovering pops the subcategory panel; it auto-collapses shortly after the mouse leaves; the active filter shows as a "✕ tag" on the filter bar — one click to clear.',
      '<b>No-lock principle</b>: the panel is just a preview layer — choosing and changing your mind is one continuous gesture. See a level, go to a level, switch anytime; no need to return to "All" first.',
      '<b>Consistency</b>: type, difficulty and category filters share the same style and height — they read as one control set.'
    ],
    thinking: 'The old dropdown was a flat list: switching categories meant going back to "All" and re-selecting — high mis-click rate and a long path. Our core idea was to turn "choose then change" into "preview then decide" — filtering should feel like browsing a menu: hover to preview, leave without locking, one click to undo. Filtering shouldn\'t be a burden; it\'s the doorway into the question bank.',
    stats: [['6', 'new style rules'], ['5', 'interaction states'], ['200ms', 'panel collapse delay']]
  },
  {
    date: '2026-08-02', tag: 'fix', tagText: 'Fix',
    title: 'Hierarchical category & difficulty filter fixes',
    desc: 'Difficulty filtering now applies uniformly across all questions (including static MCQs); category filtering upgraded to the knowledge-graph hierarchy with drill-down.',
    overview: 'Two filter bugs fixed: difficulty previously only applied to some questions while others ignored it entirely; the category dropdown was a flat list that couldn\'t express the parent-child structure of knowledge points.',
    points: [
      '<b>Uniform difficulty filtering</b>: moved difficulty filtering from backend partial filtering to unified frontend filtering — every question, whatever its source bank, is treated the same.',
      '<b>Hierarchical categories</b>: filter options now reuse the knowledge graph\'s hierarchy — selecting a major category covers all its child knowledge points; selecting a specific node matches only that point.',
      '<b>Static question mapping</b>: static MCQs are now mapped to knowledge nodes too, so they participate in hierarchical filtering like dynamic questions.'
    ],
    thinking: 'Filtering is about helping users "read a thinner question bank". A flat list of 29 tags can\'t convey the relationships between knowledge points — but the knowledge graph is already a ready-made hierarchy dictionary, so we let it drive the filter: choosing "joins" shows inner, left and self joins together. The difficulty fix was a matter of principle: a rule either applies to everything, or it isn\'t a rule.',
    stats: [['29', 'tags in hierarchy'], ['58', 'static questions covered'], ['2', 'filter bugs fixed']]
  },
  {
    date: '2026-08-02', tag: 'bank', tagText: 'Question Bank',
    title: 'All 182 Nowcoder answer keys generated',
    desc: 'LLM-generated answers validated by real database execution, with automatic retry and repair. Question bank now totals 507, with 50 written-test questions online.',
    overview: 'All 182 scraped Nowcoder questions were missing answer keys. We built a "generate-verify-repair" pipeline: the LLM writes an answer per question → it is executed for real in a database → if wrong, the model retries. Final result: 182/182 passed execution validation.',
    points: [
      '<b>Machine-verifiable</b>: every answer must execute successfully in a database and produce output — not merely "look reasonable". Execution results replace manual spot checks.',
      '<b>Automatic repair loop</b>: after the first pass, fixes were batched: type conversions that corrupted column names, MySQL dialect keywords, CREATE TABLE statements scattered across files — classic "answered but won\'t run" cases.',
      '<b>Separate tracks</b>: beginner / must-know / hot questions enter self-practice (now 457); big-company written-test questions form their own set (50) — practice and testing stay separate.'
    ],
    thinking: '182 questions without answers is an exam paper with no answer sheet. Hand-writing them all is slow and error-prone, so we made the machine the judge: the LLM generates, the database verifies, and failures go back for another try. The pitfalls we hit (modifying types also renamed columns, dialect differences, path compatibility) were themselves a great lesson — the quality floor for a question bank should be "every answer runs and reproduces", not "somebody looked at it".',
    stats: [['182/182', 'answers verified'], ['457', 'self-practice total'], ['50', 'written-test questions']]
  },
  {
    date: '2026-07-31', tag: 'opt', tagText: 'Optimization',
    title: 'Knowledge graph rebuild launched',
    desc: 'The graph is now a 37-node, 3-tier structure (root → 7 major categories → 29 sub-nodes); learning paths are clear at a glance; recommendation weights rebalanced.',
    overview: 'The knowledge graph was rebuilt as a clear three-tier structure: one root node, 7 major categories (DML, DDL, functions, joins, constraints, subqueries, queries) and 29 sub-knowledge-points. The graph now drives both unlock rules and recommendation weights — the learning path converges into one readable map.',
    points: [
      '<b>Rebalanced weights</b>: questions answered correctly drop far in priority; never-seen questions get priority; previously-wrong questions get ×1.5 extra practice weight.',
      '<b>60% consolidation rule</b>: if accuracy on the current knowledge point falls below 60%, the learner stays there to practice until passing — foundations stay solid.',
      '<b>Unlock chain fix</b>: found a broken chain in the old logic where "answering MCQs never unlocked fill-ins" — fixed: the first correct advanced MCQ unlocks all fill-ins and pushes one immediately.'
    ],
    thinking: 'The old graph had loose question connections — learners couldn\'t see "what to learn, where I am". This rebuild\'s core was convergence: compress the learning path into a 37-node map with 7 categories as the backbone and knowledge points hanging beneath; and align the recommendation logic with the map — weights by mastery, progress gated by accuracy. The exposed unlock-chain break was the biggest lesson: the worst thing for an adaptive system is a missing link that keeps users from ever reaching the next step.',
    stats: [['37', 'total nodes'], ['29', 'knowledge tags'], ['60%', 'mastery threshold']]
  },
  {
    date: '2026-07-30', tag: 'fix', tagText: 'Fix',
    title: 'LeetCode 310 answer keys updated',
    desc: 'Batch-updated answer keys: 295 questions now generate expected output via real execution; added a translation layer for MySQL dialect; removed 15 incompatible questions.',
    overview: '310 questions had answer keys but no runnable expected output, so the judge couldn\'t work. We executed the answers in a real database to generate output tables, solving MySQL-vs-SQLite dialect differences along the way; 3 answers that were themselves wrong got manual fixes.',
    points: [
      '<b>Expected output from real execution</b>: the judge compares "what actually runs", not hand-written reference tables — 295 questions generated successfully.',
      '<b>Dialect translation layer</b>: MySQL-specific syntax (enum types, date formatting, field type differences) was adapted item by item during migration.',
      '<b>Decisive trimming</b>: 15 questions requiring regex or function definitions that SQLite can\'t run were removed outright — accurate judging matters more than question count.'
    ],
    thinking: 'The judge\'s bottom line is "your answer can really produce that result". We executed all 310 answers in a database: failures were investigated — dialect differences got a translation layer, genuinely wrong answers got manual fixes, and the 15 that simply couldn\'t run were removed. Question count can always grow, but a wrong judgment directly destroys user trust — data quality beats quantity.',
    stats: [['295', 'verified'], ['15', 'removed'], ['3', 'manually fixed']]
  },
  {
    date: '2026-07-28', tag: 'new', tagText: 'New Feature',
    title: 'Deep mode launched',
    desc: 'After answering an MCQ correctly, the same knowledge point\'s fill-in question is pushed automatically — one-to-many practice forming a "concept memory → hands-on verification" loop.',
    overview: 'Deep mode is live: answer an MCQ correctly and the same knowledge point\'s fill-in question is pushed automatically — MCQs are the preview, fill-ins are the real deal. Strike while the iron is hot.',
    points: [
      '<b>Deep mode</b>: after a correct MCQ, push the fill-in question of the same knowledge point — MCQs preview concepts, fill-ins test real writing, strike while the iron is hot.',
      '<b>Unlock rules</b>: the first correct answer on a basic question unlocks all MCQs; the first correct on an advanced question unlocks all fill-ins and pushes one immediately; wrong answers keep you consolidating the current point.'
    ],
    thinking: 'MCQs test whether you recognize something; fill-ins test whether you can write it. Practicing only MCQs creates the illusion of "I get it". Deep mode\'s idea: the moment a concept question is answered correctly, immediately serve a hands-on question — strike while the iron is hot and turn "understanding" into "writing".',
    stats: [['1', 'core feature'], ['4', 'unlock rules'], ['×1.5', 'wrong-answer weight']]
  },
  {
    date: '2026-07-25', tag: 'opt', tagText: 'Optimization',
    title: 'Bank import & tag/difficulty sync',
    desc: '58 static MCQs parsed and imported; all 371 questions aligned to unified difficulty and knowledge-tag standards; 272 questions\' data issues fixed.',
    overview: 'The bank came from multiple sources (scraping, spreadsheets, hand-made pages) with wildly different formats. This round was systematic alignment: unify difficulty and knowledge-tag standards across 371 questions, fixing tag separator inconsistencies and encoding corruption along the way.',
    points: [
      '<b>Static questions imported</b>: 58 basic/advanced MCQs (with schema, options, expected output) fully parsed and imported — completing the question-type picture beyond fill-ins.',
      '<b>Unified standards</b>: difficulty and knowledge tags of all 371 questions aligned against the standard table — filtering and star ratings are consistent from now on.',
      '<b>Data cleansing</b>: batch-fixed separator inconsistencies in 272 questions\' tags, plus encoding corruption that broke star ratings.'
    ],
    thinking: 'The question bank is the product\'s foundation, and multi-source data fears inconsistent standards the most — one bank calls it "window functions", another "ranking functions", and filters start missing questions. This alignment\'s payoff isn\'t surface-level: once invisible standards like difficulty, tags and encoding are unified, filtering, recommendations and statistics can stand on trustworthy ground. Foundations first — then you can build floors on top.',
    stats: [['58', 'static imports'], ['371', 'aligned'], ['272', 'data fixes']]
  }
];

const PER_PAGE = 4;   // 每页条数，功能更新多了可以调大
const TOTAL_PAGES = Math.ceil(UPDATES.length / PER_PAGE);
let page = 1;

function renderUpdates() {
  const start = (page - 1) * PER_PAGE;
  const items = UPDATES.slice(start, start + PER_PAGE);
  // 置顶条目：项目初心，永远在第一页首位（不参与分页）
  const vision = pick(VISION, VISION_EN);
  const visionHtml = `
    <div class="update-item glass origin fade-up" style="animation-delay:0s" onclick="openDetail(-1)">
      <div class="u-date">${vision.date}</div>
      <div class="u-body">
        <div class="u-top"><span class="pin-badge">${t('pinned')}</span><span class="utag ${vision.tag}">${vision.tagText}</span><span class="u-title">${vision.title}</span></div>
        <div class="u-desc">${vision.desc}</div>
        <div class="u-more">${t('view_detail')} <span class="arr">›</span></div>
      </div>
    </div>`;
  const listHtml = items.map((u0, i) => {
    const idx = start + i;
    const u = pick(u0, UPDATES_EN[idx]);
    return `
    <div class="update-item glass fade-up" style="animation-delay:${i * 0.06}s" onclick="openDetail(${idx})">
      <div class="u-date">${u.date}</div>
      <div class="u-body">
        <div class="u-top"><span class="utag ${u.tag}">${u.tagText}</span><span class="u-title">${u.title}</span></div>
        <div class="u-desc">${u.desc}</div>
        <div class="u-more">${t('view_detail')} <span class="arr">›</span></div>
      </div>
    </div>`;
  }).join('');
  document.getElementById('updateList').innerHTML = visionHtml + listHtml;
  renderPager();
}

function renderPager() {
  const pager = document.getElementById('pager');
  let html = `<span class="pg-info">${tf('pg_info', UPDATES.length + 1, page, TOTAL_PAGES)}</span>`;
  html += `<button class="pg-btn" ${page === 1 ? 'disabled' : ''} onclick="gotoPage(${page - 1})"><span class="arr">‹</span>${t('pg_prev')}</button>`;
  for (let i = 1; i <= TOTAL_PAGES; i++) {
    html += `<button class="pg-btn ${i === page ? 'on' : ''}" onclick="gotoPage(${i})">${i}</button>`;
  }
  html += `<button class="pg-btn" ${page === TOTAL_PAGES ? 'disabled' : ''} onclick="gotoPage(${page + 1})">${t('pg_next')}<span class="arr">›</span></button>`;
  pager.innerHTML = html;
}

function gotoPage(p) {
  if (p < 1 || p > TOTAL_PAGES || p === page) return;
  page = p;
  renderUpdates();
  document.querySelector('.updates').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ---- 详情弹窗 ---- */
function openDetail(idx) {
  const u = idx === -1 ? pick(VISION, VISION_EN) : pick(UPDATES[idx], UPDATES_EN[idx]);
  if (!u) return;
  document.getElementById('detailBody').innerHTML = `
    <div class="modal-head">
      <div class="modal-title">${u.title}</div>
      <button class="modal-close" onclick="closeDetail()">✕</button>
    </div>
    <div class="modal-meta">
      <span class="utag ${u.tag}">${u.tagText}</span>
      <span class="m-date">${u.date}</span>
    </div>
    <div class="m-section">
      <h4>${t('sec_what')}</h4>
      <div class="m-overview">${u.overview}</div>
    </div>
    <div class="m-section">
      <h4>${t('sec_points')}</h4>
      <ul class="m-points">${u.points.map(p => `<li>${p}</li>`).join('')}</ul>
    </div>
    <div class="m-section">
      <h4>${t('sec_thinking')}</h4>
      <div class="m-overview thinking">${u.thinking}</div>
    </div>
    ${u.stats ? `<div class="m-section"><h4>${t('sec_stats')}</h4><div class="m-stats">${u.stats.map(s => `<div class="m-stat"><div class="v">${s[0]}</div><div class="l">${s[1]}</div></div>`).join('')}</div></div>` : ''}
    <div class="modal-foot"><button class="btn-ok" onclick="closeDetail()">${t('got_it')}</button></div>`;
  document.getElementById('detailModal').classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeDetail() {
  document.getElementById('detailModal').classList.remove('show');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

renderUpdates();
