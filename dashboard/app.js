/* ═══════════════════════════════════════════════════════════════════════
   TaskForge Dashboard — app.js
   Full SPA with demo data, Chart.js charts, live log simulation,
   theme switching, modal management, and all UI interactions.
═══════════════════════════════════════════════════════════════════════ */

'use strict';

/* ──────────────────────────────────────────────────────────────────────
   DEMO DATA
────────────────────────────────────────────────────────────────────── */
const DEMO_JOBS = [
  { id:'job-001', name:'daily-db-backup',      desc:'PostgreSQL backup to S3', trigger:'cron',     triggerExpr:'0 2 * * *',     executor:'shell',  status:'active',  tags:['production','database'], nextRun:'02:00 UTC',    lastRun:'02:00 UTC', lastDuration:'4m 12s', lastStatus:'success' },
  { id:'job-002', name:'cache-invalidation',   desc:'Flush Redis cache layers', trigger:'interval', triggerExpr:'every 30m',     executor:'python', status:'running', tags:['production'],            nextRun:'Running…',     lastRun:'30m ago',   lastDuration:'12s',    lastStatus:'success' },
  { id:'job-003', name:'security-scan',        desc:'Run Trivy image scanner',  trigger:'cron',     triggerExpr:'0 6 * * 0',     executor:'docker', status:'active',  tags:['security'],             nextRun:'Sun 06:00',    lastRun:'7d ago',    lastDuration:'8m 40s', lastStatus:'success' },
  { id:'job-004', name:'log-analysis',         desc:'Parse and aggregate logs', trigger:'cron',     triggerExpr:'0 */6 * * *',   executor:'python', status:'failed',  tags:['monitoring'],           nextRun:'18:00 UTC',    lastRun:'12:00',     lastDuration:'1m 03s', lastStatus:'failed'  },
  { id:'job-005', name:'container-deploy',     desc:'Deploy to k8s cluster',    trigger:'webhook',  triggerExpr:'on POST',       executor:'shell',  status:'active',  tags:['devops','k8s'],         nextRun:'On demand',    lastRun:'2h ago',    lastDuration:'2m 55s', lastStatus:'success' },
  { id:'job-006', name:'report-email',         desc:'Weekly KPI email report',  trigger:'cron',     triggerExpr:'0 9 * * 1',     executor:'python', status:'active',  tags:['reporting'],            nextRun:'Mon 09:00',    lastRun:'Mon 09:00', lastDuration:'22s',    lastStatus:'success' },
  { id:'job-007', name:'data-sync',            desc:'Sync DB to data warehouse',trigger:'interval', triggerExpr:'every 1h',      executor:'http',   status:'paused',  tags:['data'],                 nextRun:'Paused',       lastRun:'3h ago',    lastDuration:'45s',    lastStatus:'success' },
  { id:'job-008', name:'health-check-prod',    desc:'Ping all production APIs', trigger:'interval', triggerExpr:'every 5m',      executor:'http',   status:'running', tags:['monitoring','prod'],    nextRun:'Running…',     lastRun:'5m ago',    lastDuration:'3s',     lastStatus:'success' },
  { id:'job-009', name:'cleanup-old-runs',     desc:'Prune job runs older 30d', trigger:'cron',     triggerExpr:'0 1 * * *',     executor:'python', status:'active',  tags:['maintenance'],          nextRun:'01:00 UTC',    lastRun:'01:00',     lastDuration:'8s',     lastStatus:'success' },
  { id:'job-010', name:'k8s-scale-down',       desc:'Scale non-prod at night',  trigger:'cron',     triggerExpr:'0 22 * * 1-5',  executor:'shell',  status:'active',  tags:['devops','cost'],        nextRun:'22:00 UTC',    lastRun:'22:00',     lastDuration:'30s',    lastStatus:'success' },
  { id:'job-011', name:'ssl-cert-renew',       desc:'Auto-renew SSL with ACME', trigger:'cron',     triggerExpr:'0 3 1 * *',     executor:'shell',  status:'active',  tags:['security'],             nextRun:'Nov 01 03:00', lastRun:'Oct 01',    lastDuration:'1m 10s', lastStatus:'success' },
  { id:'job-012', name:'release-notify',       desc:'Post to Slack on deploy',  trigger:'event',    triggerExpr:'on job.success',executor:'http',   status:'active',  tags:['notifications'],        nextRun:'On event',     lastRun:'2h ago',    lastDuration:'2s',     lastStatus:'success' },
];

const DEMO_RUNS = [
  { id:'run-a1b2', jobId:'job-001', jobName:'daily-db-backup',   started:'2026-10-23 02:00:01', duration:'4m 12s', trigger:'cron',    exitCode:0,  status:'success'  },
  { id:'run-c3d4', jobId:'job-004', jobName:'log-analysis',      started:'2026-10-23 12:00:02', duration:'1m 03s', trigger:'cron',    exitCode:1,  status:'failed'   },
  { id:'run-e5f6', jobId:'job-005', jobName:'container-deploy',  started:'2026-10-23 10:31:00', duration:'2m 55s', trigger:'webhook', exitCode:0,  status:'success'  },
  { id:'run-g7h8', jobId:'job-008', jobName:'health-check-prod', started:'2026-10-23 12:55:00', duration:'3s',     trigger:'interval',exitCode:0,  status:'running'  },
  { id:'run-i9j0', jobId:'job-002', jobName:'cache-invalidation',started:'2026-10-23 12:30:00', duration:'12s',    trigger:'interval',exitCode:0,  status:'success'  },
  { id:'run-k1l2', jobId:'job-009', jobName:'cleanup-old-runs',  started:'2026-10-23 01:00:05', duration:'8s',     trigger:'cron',    exitCode:0,  status:'success'  },
  { id:'run-m3n4', jobId:'job-006', jobName:'report-email',      started:'2026-10-20 09:00:02', duration:'22s',    trigger:'cron',    exitCode:0,  status:'success'  },
  { id:'run-o5p6', jobId:'job-003', jobName:'security-scan',     started:'2026-10-19 06:00:00', duration:'8m 40s', trigger:'cron',    exitCode:0,  status:'success'  },
  { id:'run-q7r8', jobId:'job-011', jobName:'ssl-cert-renew',    started:'2026-10-01 03:00:00', duration:'1m 10s', trigger:'cron',    exitCode:0,  status:'success'  },
  { id:'run-s9t0', jobId:'job-007', jobName:'data-sync',         started:'2026-10-23 09:00:00', duration:'45s',    trigger:'interval',exitCode:0,  status:'success'  },
];

const DEMO_PLUGINS = [
  { id:'k8s_executor',    name:'K8s Executor',      version:'0.3.2', icon:'⚓', desc:'Run TaskForge jobs as Kubernetes Jobs. Supports resource limits, namespaces, service accounts, and pod tolerations.', type:'executor',     enabled:true  },
  { id:'discord_notifier',name:'Discord Notifier',  version:'0.2.0', icon:'💬', desc:'Send rich embed notifications to Discord channels via webhooks. Configurable color, emoji, and mention support.', type:'notifier',     enabled:false },
  { id:'git_trigger',     name:'Git Trigger',       version:'0.1.5', icon:'🐙', desc:'Trigger jobs on GitHub/GitLab push, PR, tag, and release events. Validates webhook signatures automatically.', type:'trigger',      enabled:true  },
  { id:'datadog_metrics', name:'Datadog Metrics',   version:'0.1.0', icon:'📊', desc:'Export TaskForge metrics to Datadog. Supports custom tags, service checks, and event tracking.', type:'observability', enabled:false },
  { id:'aws_executor',    name:'AWS Lambda Exec.',  version:'0.2.1', icon:'☁️', desc:'Invoke AWS Lambda functions as TaskForge executors. Async invocation with result polling and log streaming.',  type:'executor',     enabled:false },
  { id:'pagerduty_notif', name:'PagerDuty Alerts',  version:'0.1.1', icon:'🚨', desc:'Trigger PagerDuty incidents on job failures. Supports severity levels, deduplication keys, and auto-resolve.', type:'notifier',     enabled:false },
];

const DEMO_ENV = [
  { key:'TASKFORGE_STORAGE_URL',         value:'sqlite+aiosqlite:///taskforge.db', source:'env' },
  { key:'TASKFORGE_SECRET_KEY',          value:'***hidden***',                      source:'env' },
  { key:'TASKFORGE_LOG_LEVEL',           value:'info',                              source:'default' },
  { key:'TASKFORGE_METRICS_ENABLED',     value:'true',                              source:'default' },
  { key:'TASKFORGE_CORS_ORIGINS',        value:'*',                                 source:'default' },
  { key:'TASKFORGE_SLACK_BOT_TOKEN',     value:'(not set)',                         source:'—' },
  { key:'TASKFORGE_SMTP_HOST',           value:'(not set)',                         source:'—' },
  { key:'TASKFORGE_SMTP_PORT',           value:'587',                               source:'default' },
  { key:'TASKFORGE_SLACK_DEFAULT_CHANNEL', value:'#alerts',                         source:'default' },
];

const DEMO_ACTIVITY = [
  { color:'#10b981', title:'daily-db-backup completed successfully', time:'2 min ago' },
  { color:'#ef4444', title:'log-analysis failed — exit code 1',     time:'43 min ago' },
  { color:'#3b82f6', title:'container-deploy triggered via webhook', time:'2h 29m ago' },
  { color:'#10b981', title:'cache-invalidation ran in 12s',          time:'25m ago' },
  { color:'#f59e0b', title:'health-check-prod retry #1 scheduled',   time:'5m ago' },
  { color:'#10b981', title:'k8s-scale-down executed OK',             time:'6h ago' },
  { color:'#8b5cf6', title:'release-notify triggered on job.success','time':'2h ago' },
];

/* ──────────────────────────────────────────────────────────────────────
   APP STATE
────────────────────────────────────────────────────────────────────── */
const state = {
  authenticated: false,
  demoMode: true,
  theme: 'dark',
  accent: 'blue',
  currentPage: 'dashboard',
  jobs: [...DEMO_JOBS],
  runs: [...DEMO_RUNS],
  plugins: [...DEMO_PLUGINS],
  editingJobId: null,
  jobsPage: 1,
  jobsPerPage: 10,
  jobSortCol: 'name',
  jobSortDir: 1,
  jobSearch: '',
  jobStatusFilter: '',
  jobTriggerFilter: '',
  logLines: [],
  logTailing: false,
  logInterval: null,
  confirmCallback: null,
  charts: {},
};

/* ──────────────────────────────────────────────────────────────────────
   INIT
────────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  applySavedPreferences();
  bindSidebar();
  bindTopbar();
  bindLoginScreen();
  bindNavigation();
  bindJobsPage();
  bindLogsPage();
  bindTriggersPage();
  bindNotificationsPage();
  bindMetricsPage();
  bindHealthPage();
  bindSettingsPage();
  bindPluginsPage();
  bindJobModal();
  bindConfirmModal();
  bindLogModal();
  bindGlobalSearch();
  bindKeyboardShortcuts();
  startLiveFeed();
  updateUptime();
  initLiveBackendSync();
});

/* ──────────────────────────────────────────────────────────────────────
   PREFERENCES
────────────────────────────────────────────────────────────────────── */
function applySavedPreferences() {
  const savedTheme  = localStorage.getItem('tf_theme')  || 'dark';
  const savedAccent = localStorage.getItem('tf_accent') || 'blue';
  setTheme(savedTheme);
  setAccent(savedAccent);
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('tf_theme', theme);
  document.querySelectorAll('.theme-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.theme === theme);
  });
}

function setAccent(accent) {
  state.accent = accent;
  document.documentElement.setAttribute('data-accent', accent);
  localStorage.setItem('tf_accent', accent);
  document.querySelectorAll('.color-swatch').forEach(s => {
    s.classList.toggle('active', s.dataset.color === accent);
  });
  // Rebuild charts if needed
  if (state.charts.runsChart) rebuildCharts();
}

/* ──────────────────────────────────────────────────────────────────────
   SIDEBAR
────────────────────────────────────────────────────────────────────── */
function bindSidebar() {
  const sidebar = document.getElementById('sidebar');
  const toggle  = document.getElementById('sidebarToggle');
  const mobileBtn = document.getElementById('mobileMenuBtn');

  toggle?.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('tf_sidebar_collapsed', sidebar.classList.contains('collapsed'));
  });

  mobileBtn?.addEventListener('click', () => {
    sidebar.classList.toggle('mobile-open');
  });

  // Close mobile sidebar on outside click
  document.addEventListener('click', e => {
    if (window.innerWidth <= 768 &&
        !sidebar.contains(e.target) &&
        !mobileBtn.contains(e.target)) {
      sidebar.classList.remove('mobile-open');
    }
  });

  // Restore collapsed state
  if (localStorage.getItem('tf_sidebar_collapsed') === 'true') {
    sidebar.classList.add('collapsed');
  }
}

/* ──────────────────────────────────────────────────────────────────────
   TOPBAR
────────────────────────────────────────────────────────────────────── */
function bindTopbar() {
  // Theme toggle
  document.getElementById('themeToggle')?.addEventListener('click', () => {
    setTheme(state.theme === 'dark' ? 'light' : 'dark');
  });

  // User avatar dropdown
  const avatar   = document.getElementById('userAvatar');
  const dropdown = document.getElementById('userDropdown');
  avatar?.addEventListener('click', e => { e.stopPropagation(); dropdown.classList.toggle('hidden'); });
  document.addEventListener('click', () => dropdown?.classList.add('hidden'));

  // Logout
  document.getElementById('logoutBtn')?.addEventListener('click', e => {
    e.preventDefault();
    showConfirm('Sign Out', 'Are you sure you want to sign out?', () => {
      state.authenticated = false;
      document.getElementById('loginOverlay')?.classList.remove('hidden');
    });
  });

  // Notification bell (demo)
  document.getElementById('notifBell')?.addEventListener('click', () => {
    toast('info', 'Notifications', '3 new events — job.failed, 2× job.success');
  });
}

/* ──────────────────────────────────────────────────────────────────────
   LOGIN SCREEN
────────────────────────────────────────────────────────────────────── */
function bindLoginScreen() {
  document.getElementById('demoModeBtn')?.addEventListener('click', () => {
    state.authenticated = true;
    state.demoMode = true;
    document.getElementById('loginOverlay')?.classList.add('hidden');
    navigateTo('dashboard');
    toast('success', 'Demo Mode', 'Using sample data — no backend connection required.');
  });

  document.getElementById('loginBtn')?.addEventListener('click', () => {
    const url   = document.getElementById('loginApiUrl')?.value;
    const token = document.getElementById('loginToken')?.value;
    if (!token) { toast('error', 'Auth Error', 'JWT token is required.'); return; }
    // Simulate connection test
    toast('info', 'Connecting…', `Trying ${url}`);
    setTimeout(() => {
      toast('success', 'Connected', 'Successfully authenticated with TaskForge API.');
      state.authenticated = true;
      state.demoMode = false;
      document.getElementById('loginOverlay')?.classList.add('hidden');
      navigateTo('dashboard');
    }, 1200);
  });
}

/* ──────────────────────────────────────────────────────────────────────
   NAVIGATION
────────────────────────────────────────────────────────────────────── */
function bindNavigation() {
  document.querySelectorAll('[data-page]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      navigateTo(el.dataset.page);
      // Close user dropdown if open
      document.getElementById('userDropdown')?.classList.add('hidden');
    });
  });
}

function navigateTo(page) {
  state.currentPage = page;

  // Hide all pages
  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));

  // Show target page
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.remove('hidden');

  // Update nav links
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.getElementById(`nav-${page}`)?.classList.add('active');

  // Update breadcrumb
  const labels = { dashboard:'Dashboard', jobs:'Jobs', runs:'Run History', logs:'Live Logs', triggers:'Triggers', notifications:'Notifications', metrics:'Metrics', plugins:'Plugins', health:'Health', settings:'Settings' };
  document.getElementById('breadcrumbCurrent').textContent = labels[page] || page;

  // Initialize page on first visit
  switch(page) {
    case 'dashboard':    initDashboard(); break;
    case 'jobs':         initJobsTable(); break;
    case 'runs':         initRunsTable(); break;
    case 'logs':         initLogsPage();  break;
    case 'metrics':      initMetrics();   break;
    case 'plugins':      initPlugins();   break;
    case 'health':       initHealth();    break;
  }

  // Close mobile sidebar
  document.getElementById('sidebar')?.classList.remove('mobile-open');
}

/* ──────────────────────────────────────────────────────────────────────
   DASHBOARD PAGE
────────────────────────────────────────────────────────────────────── */
function initDashboard() {
  animateCounters();
  renderDashboardJobs();
  renderActivityFeed();
  initCharts();
  renderSparklines();
}

function animateCounters() {
  document.querySelectorAll('.stat-value[data-target]').forEach(el => {
    const target  = parseFloat(el.dataset.target);
    const isPct   = el.classList.contains('stat-value--pct');
    const dur     = 1200;
    const steps   = 60;
    const step    = target / steps;
    let current   = 0;
    let count     = 0;
    const iv = setInterval(() => {
      count++;
      current = Math.min(current + step, target);
      el.textContent = isPct
        ? current.toFixed(1)
        : Math.round(current).toLocaleString();
      if (count >= steps) {
        clearInterval(iv);
        el.textContent = isPct ? target.toFixed(1) : target.toLocaleString();
      }
    }, dur / steps);
  });
}

function renderDashboardJobs() {
  const tbody = document.getElementById('dashboardJobsBody');
  if (!tbody) return;
  tbody.innerHTML = state.jobs.slice(0,6).map(job => `
    <tr>
      <td><div class="job-name-cell"><span class="job-name">${job.name}</span><span class="job-desc">${job.desc}</span></div></td>
      <td><span class="trigger-badge">${job.trigger}</span></td>
      <td>${job.nextRun}</td>
      <td>${statusBadge(job.lastStatus)}</td>
      <td>
        <div class="action-group">
          <button class="action-btn run"   onclick="triggerRun('${job.id}')">▶</button>
          <button class="action-btn edit"  onclick="openEditJob('${job.id}')">✏</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function renderActivityFeed() {
  const feed = document.getElementById('activityFeed');
  if (!feed) return;
  feed.innerHTML = state.activityItems
    ? state.activityItems.map(activityItemHtml).join('')
    : DEMO_ACTIVITY.map(activityItemHtml).join('');
}

function activityItemHtml(item) {
  return `<div class="activity-item">
    <span class="activity-dot" style="background:${item.color}"></span>
    <div class="activity-content">
      <div class="activity-title">${item.title}</div>
      <div class="activity-time">${item.time}</div>
    </div>
  </div>`;
}

function startLiveFeed() {
  const events = [
    { color:'#10b981', title:'health-check-prod completed — 3ms',       time:'just now' },
    { color:'#3b82f6', title:'data-sync triggered via interval',          time:'just now' },
    { color:'#f59e0b', title:'cache-invalidation retry scheduled',        time:'just now' },
    { color:'#10b981', title:'cleanup-old-runs — purged 142 records',    time:'just now' },
    { color:'#ef4444', title:'log-analysis failed — check logs',          time:'just now' },
    { color:'#10b981', title:'container-deploy webhook received',          time:'just now' },
  ];
  let idx = 0;
  setInterval(() => {
    if (state.currentPage !== 'dashboard') return;
    const feed = document.getElementById('activityFeed');
    if (!feed) return;
    const item = events[idx % events.length];
    item.time = 'just now';
    const el = document.createElement('div');
    el.className = 'activity-item';
    el.innerHTML = `<span class="activity-dot" style="background:${item.color}"></span>
      <div class="activity-content">
        <div class="activity-title">${item.title}</div>
        <div class="activity-time">${item.time}</div>
      </div>`;
    feed.insertBefore(el, feed.firstChild);
    // Keep max 12 items
    while(feed.children.length > 12) feed.removeChild(feed.lastChild);
    idx++;
  }, 5000);
}

document.getElementById('refreshDashboard')?.addEventListener('click', () => {
  initDashboard();
  toast('success', 'Refreshed', 'Dashboard data updated.');
});

document.getElementById('createJobBtn')?.addEventListener('click', openCreateJob);

/* ──────────────────────────────────────────────────────────────────────
   CHARTS (Chart.js)
────────────────────────────────────────────────────────────────────── */
function getChartColors() {
  const accentMap = { blue:'#3b82f6', emerald:'#10b981', purple:'#8b5cf6', amber:'#f59e0b', red:'#ef4444' };
  return accentMap[state.accent] || '#3b82f6';
}

function initCharts() {
  if (!window.Chart) return;
  destroyChart('runsChart');
  destroyChart('statusChart');

  const isDark = state.theme === 'dark';
  const gridColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
  const textColor = isDark ? '#8b949e' : '#57606a';
  const accent = getChartColors();

  Chart.defaults.font.family = "'Inter', sans-serif";

  // Runs bar chart
  const runsCtx = document.getElementById('runsChart');
  if (runsCtx) {
    state.charts.runsChart = new Chart(runsCtx, {
      type: 'bar',
      data: {
        labels: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
        datasets: [
          {
            label: 'Success',
            data: [18, 22, 19, 24, 28, 15, 12],
            backgroundColor: 'rgba(16,185,129,0.7)',
            borderRadius: 4,
          },
          {
            label: 'Failed',
            data: [1, 0, 2, 1, 0, 1, 0],
            backgroundColor: 'rgba(239,68,68,0.7)',
            borderRadius: 4,
          },
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position:'top', labels:{ color:textColor, font:{size:11}, boxWidth:12 } },
          tooltip: { backgroundColor:'#0d1117', borderColor: accent, borderWidth:1 }
        },
        scales: {
          x: { stacked:true, grid:{color:gridColor}, ticks:{color:textColor} },
          y: { stacked:true, grid:{color:gridColor}, ticks:{color:textColor} }
        }
      }
    });
  }

  // Status donut
  const statusCtx = document.getElementById('statusChart');
  if (statusCtx) {
    state.charts.statusChart = new Chart(statusCtx, {
      type: 'doughnut',
      data: {
        labels: ['Success', 'Failed', 'Running', 'Paused'],
        datasets: [{
          data: [134, 7, 6, 1],
          backgroundColor: ['rgba(16,185,129,0.8)', 'rgba(239,68,68,0.8)', 'rgba(59,130,246,0.8)', 'rgba(245,158,11,0.8)'],
          borderColor: isDark ? '#0d1117' : '#fff',
          borderWidth: 3,
          hoverOffset: 8,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { position:'right', labels:{ color:textColor, font:{size:11}, boxWidth:12, padding:16 } },
          tooltip: { backgroundColor:'#0d1117', borderColor: accent, borderWidth:1 }
        }
      }
    });
  }
}

function renderSparklines() {
  const datasets = {
    'spark-jobs':    [18,19,22,20,23,21,24],
    'spark-runs':    [110,125,118,139,145,132,148],
    'spark-success': [96.1,96.8,97.0,97.2,97.1,97.0,97.3],
    'spark-active':  [4,5,7,6,8,5,6],
  };
  const colors = {
    'spark-jobs':    '#3b82f6',
    'spark-runs':    '#10b981',
    'spark-success': '#06d6a0',
    'spark-active':  '#f59e0b',
  };
  Object.entries(datasets).forEach(([id, data]) => {
    const canvas = document.getElementById(id);
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
    ctx.clearRect(0,0,w,h);
    const color = colors[id];
    const grad = ctx.createLinearGradient(0,0,0,h);
    grad.addColorStop(0, color + '44');
    grad.addColorStop(1, color + '00');
    const pts = data.map((v,i) => [i * w/(data.length-1), h - ((v-min)/range) * (h-4) - 2]);
    ctx.beginPath();
    pts.forEach(([x,y],i) => i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y));
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
    // Fill area
    ctx.lineTo(pts[pts.length-1][0], h);
    ctx.lineTo(pts[0][0], h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
  });
}

function destroyChart(id) {
  if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; }
}

function rebuildCharts() {
  if (state.currentPage === 'dashboard') initCharts();
  if (state.currentPage === 'metrics')   initMetricsCharts();
}

/* ──────────────────────────────────────────────────────────────────────
   JOBS TABLE
────────────────────────────────────────────────────────────────────── */
function bindJobsPage() {
  document.getElementById('createJobBtn2')?.addEventListener('click', openCreateJob);

  document.getElementById('jobSearchInput')?.addEventListener('input', e => {
    state.jobSearch = e.target.value.toLowerCase();
    state.jobsPage  = 1;
    renderJobsTable();
  });
  document.getElementById('jobStatusFilter')?.addEventListener('change', e => {
    state.jobStatusFilter  = e.target.value;
    state.jobsPage         = 1;
    renderJobsTable();
  });
  document.getElementById('jobTriggerFilter')?.addEventListener('change', e => {
    state.jobTriggerFilter = e.target.value;
    state.jobsPage         = 1;
    renderJobsTable();
  });

  // Sorting
  document.querySelectorAll('#jobsTable .sortable-col').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (state.jobSortCol === col) {
        state.jobSortDir *= -1;
      } else {
        state.jobSortCol = col;
        state.jobSortDir = 1;
      }
      renderJobsTable();
    });
  });
}

function initJobsTable() {
  renderJobsTable();
}

function getFilteredJobs() {
  return state.jobs.filter(j => {
    const matchSearch  = !state.jobSearch  || j.name.includes(state.jobSearch) || j.desc.toLowerCase().includes(state.jobSearch);
    const matchStatus  = !state.jobStatusFilter  || j.status === state.jobStatusFilter;
    const matchTrigger = !state.jobTriggerFilter || j.trigger === state.jobTriggerFilter;
    return matchSearch && matchStatus && matchTrigger;
  }).sort((a,b) => {
    const av = a[state.jobSortCol] || '', bv = b[state.jobSortCol] || '';
    return av.localeCompare(bv) * state.jobSortDir;
  });
}

function renderJobsTable() {
  const filtered = getFilteredJobs();
  const start = (state.jobsPage - 1) * state.jobsPerPage;
  const page  = filtered.slice(start, start + state.jobsPerPage);

  document.getElementById('jobsTableCount').textContent = `${filtered.length} jobs`;

  const tbody = document.getElementById('jobsTableBody');
  if (!tbody) return;

  tbody.innerHTML = page.map(job => `
    <tr>
      <td>
        <div class="job-name-cell">
          <span class="job-name">${job.name}</span>
          <span class="job-desc">${job.desc}</span>
        </div>
      </td>
      <td><span class="trigger-badge">${job.trigger}</span></td>
      <td><span class="trigger-badge">${job.executor}</span></td>
      <td>${job.nextRun}</td>
      <td>${job.lastRun}</td>
      <td>${statusBadge(job.status)}</td>
      <td><div class="tag-list">${job.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div></td>
      <td>
        <div class="action-group">
          <button class="action-btn run"   onclick="triggerRun('${job.id}')" title="Run now">▶</button>
          <button class="action-btn pause" onclick="togglePause('${job.id}')" title="${job.status==='paused'?'Resume':'Pause'}">${job.status==='paused'?'↺':'⏸'}</button>
          <button class="action-btn edit"  onclick="openEditJob('${job.id}')" title="Edit">✏</button>
          <button class="action-btn logs"  onclick="openJobLogs('${job.id}')" title="Logs">📋</button>
          <button class="action-btn delete" onclick="deleteJob('${job.id}')" title="Delete">🗑</button>
        </div>
      </td>
    </tr>
  `).join('');

  renderPagination('jobsPagination', 'jobsPaginationInfo', filtered.length, state.jobsPage, state.jobsPerPage, p => {
    state.jobsPage = p;
    renderJobsTable();
  });
}

async function initLiveBackendSync() {
  try {
    const res = await fetch('/health');
    if (res.ok) {
      const data = await res.json();
      state.liveApi = true;
      state.authenticated = true;
      state.demoMode = false;
      document.getElementById('loginOverlay')?.classList.add('hidden');
      await syncFromLiveApi();
      toast('success', 'Backend Connected', `TaskForge v${data.version} live — ${state.jobs.length} jobs loaded`);
    }
  } catch (e) {
    console.log('TaskForge: running in demo mode');
  }
}

async function syncFromLiveApi() {
  try {
    const [jobsRes, runsRes] = await Promise.all([
      fetch('/api/jobs'),
      fetch('/api/runs')
    ]);
    if (jobsRes.ok) {
      const jobs = await jobsRes.json();
      if (jobs && jobs.length > 0) {
        state.jobs = jobs;
      }
    }
    if (runsRes.ok) {
      const runs = await runsRes.json();
      if (runs && runs.length > 0) {
        state.runs = runs;
      }
    }
    renderJobsTable();
    renderDashboardJobs();
    if (typeof renderLogsTable === 'function') renderLogsTable();
    const badge = document.getElementById('badge-jobs');
    if (badge) badge.textContent = state.jobs.length;
  } catch (e) {
    console.error('Failed to sync from live API', e);
  }
}

/* ──────────────────────────────────────────────────────────────────────
   JOB ACTIONS
────────────────────────────────────────────────────────────────────── */
window.triggerRun = async function(jobId) {
  const job = state.jobs.find(j => j.id === jobId);
  if (!job) return;
  toast('info', 'Job Triggered', `${job.name} queued for execution.`);
  if (state.liveApi) {
    try {
      const res = await fetch(`/api/jobs/${jobId}/run`, { method: 'POST' });
      const run = await res.json();
      if (res.ok) {
        toast('success', 'Job Complete', `${job.name} finished: ${run.status} (${run.duration})`);
        await syncFromLiveApi();
      } else {
        toast('error', 'Execution Failed', run.detail || 'Error running job');
      }
      return;
    } catch (e) {
      console.error(e);
    }
  }
  // Fallback demo simulation
  setTimeout(() => {
    toast('success', 'Job Complete', `${job.name} finished successfully.`);
  }, 2000);
};

window.togglePause = async function(jobId) {
  const job = state.jobs.find(j => j.id === jobId);
  if (!job) return;
  const endpoint = job.status === 'paused' ? 'resume' : 'pause';
  if (state.liveApi) {
    try {
      await fetch(`/api/jobs/${jobId}/${endpoint}`, { method: 'POST' });
      await syncFromLiveApi();
      toast(endpoint === 'resume' ? 'success' : 'warning', `Job ${endpoint === 'resume' ? 'Resumed' : 'Paused'}`, `${job.name}`);
      return;
    } catch (e) {
      console.error(e);
    }
  }
  if (job.status === 'paused') {
    job.status = 'active';
    toast('success', 'Job Resumed', `${job.name} is now scheduled again.`);
  } else {
    job.status = 'paused';
    toast('warning', 'Job Paused', `${job.name} has been paused.`);
  }
  renderJobsTable();
  renderDashboardJobs();
};

window.deleteJob = function(jobId) {
  const job = state.jobs.find(j => j.id === jobId);
  if (!job) return;
  showConfirm('Delete Job', `Are you sure you want to permanently delete "${job.name}"? This cannot be undone.`, async () => {
    if (state.liveApi) {
      try {
        await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        await syncFromLiveApi();
        toast('success', 'Job Deleted', `${job.name} has been removed.`);
        return;
      } catch (e) {
        console.error(e);
      }
    }
    state.jobs = state.jobs.filter(j => j.id !== jobId);
    renderJobsTable();
    renderDashboardJobs();
    toast('success', 'Job Deleted', `${job.name} has been removed.`);
  });
};

window.openEditJob = function(jobId) {
  const job = state.jobs.find(j => j.id === jobId);
  if (!job) return;
  state.editingJobId = jobId;
  openJobModal();
  document.getElementById('jobModalTitle').textContent = `Edit Job: ${job.name}`;
  // Populate fields
  document.getElementById('jobName').value = job.name;
  document.getElementById('jobDesc').value = job.desc;
  document.getElementById('jobTags').value = job.tags.join(', ');
};

window.openJobLogs = function(jobId) {
  const job  = state.jobs.find(j => j.id === jobId);
  const logs = generateSampleLogs(job?.name || jobId, 40);
  const term = document.getElementById('logModalTerminal');
  term.innerHTML = logs.map(l => `<span class="log-line">${l}</span>`).join('');
  document.getElementById('logModalTitle').textContent = `Logs: ${job?.name || jobId}`;
  document.getElementById('logModal').classList.remove('hidden');
};

/* ──────────────────────────────────────────────────────────────────────
   RUN HISTORY
────────────────────────────────────────────────────────────────────── */
function initRunsTable() {
  // Populate job filter
  const sel = document.getElementById('runsJobFilter');
  if (sel && sel.options.length <= 1) {
    state.jobs.forEach(j => {
      const opt = document.createElement('option');
      opt.value = j.id;
      opt.textContent = j.name;
      sel.appendChild(opt);
    });
  }
  renderRunsTable();

  document.getElementById('runsJobFilter')?.addEventListener('change', renderRunsTable);
  document.getElementById('runsStatusFilter')?.addEventListener('change', renderRunsTable);
  document.getElementById('runsDateFilter')?.addEventListener('change', renderRunsTable);
}

function renderRunsTable() {
  const tbody = document.getElementById('runsTableBody');
  if (!tbody) return;
  const jobFilter    = document.getElementById('runsJobFilter')?.value    || '';
  const statusFilter = document.getElementById('runsStatusFilter')?.value || '';
  const runs = state.runs.filter(r =>
    (!jobFilter    || r.jobId === jobFilter) &&
    (!statusFilter || r.status === statusFilter)
  );
  tbody.innerHTML = runs.map(r => `
    <tr>
      <td><span class="job-id">${r.id}</span></td>
      <td><strong>${r.jobName}</strong></td>
      <td>${r.started}</td>
      <td>${r.duration}</td>
      <td><span class="trigger-badge">${r.trigger}</span></td>
      <td><code style="font-family:var(--font-mono);color:${r.exitCode===0?'#10b981':'#ef4444'}">${r.exitCode}</code></td>
      <td>${statusBadge(r.status)}</td>
      <td><button class="action-btn logs" onclick="openRunLogs('${r.id}')">📋 View</button></td>
    </tr>
  `).join('');

  document.getElementById('runsPaginationInfo').textContent = `Showing 1–${runs.length} of ${state.runs.length}`;
}

window.openRunLogs = function(runId) {
  const run  = state.runs.find(r => r.id === runId);
  const logs = generateSampleLogs(run?.jobName || runId, 60);
  const term = document.getElementById('logModalTerminal');
  term.innerHTML = logs.map(l => `<span class="log-line">${l}</span>`).join('');
  document.getElementById('logModalTitle').textContent = `Logs: Run ${runId}`;
  document.getElementById('logModal').classList.remove('hidden');
};

/* ──────────────────────────────────────────────────────────────────────
   LIVE LOGS PAGE
────────────────────────────────────────────────────────────────────── */
function initLogsPage() {
  const sel = document.getElementById('logsJobSelect');
  if (sel && sel.options.length <= 1) {
    state.jobs.forEach(j => {
      const opt = document.createElement('option');
      opt.value = j.id;
      opt.textContent = j.name;
      sel.appendChild(opt);
    });
  }
}

function bindLogsPage() {
  document.getElementById('logsStartBtn')?.addEventListener('click', () => {
    const jobId = document.getElementById('logsJobSelect')?.value;
    if (!jobId) { toast('warning', 'Select a job', 'Please choose a job before starting the log tail.'); return; }
    startLogTail(jobId);
  });

  document.getElementById('logsClearBtn')?.addEventListener('click', () => {
    clearLogs();
  });

  document.querySelectorAll('.log-level-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.log-level-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterLogs(btn.dataset.level);
    });
  });

  document.getElementById('logsWrap')?.addEventListener('change', e => {
    document.querySelectorAll('#logTerminal .log-line').forEach(l => {
      l.classList.toggle('wrap', e.target.checked);
    });
  });

  document.getElementById('logsCopyBtn')?.addEventListener('click', () => {
    const text = state.logLines.join('\n');
    navigator.clipboard.writeText(text).then(() => toast('success', 'Copied', 'Log content copied to clipboard.'));
  });

  document.getElementById('logsDownloadBtn')?.addEventListener('click', () => {
    const blob = new Blob([state.logLines.join('\n')], {type:'text/plain'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'taskforge-logs.txt'; a.click();
    URL.revokeObjectURL(url);
  });
}

function startLogTail(jobId) {
  const job = state.jobs.find(j => j.id === jobId);
  if (state.logTailing) { stopLogTail(); }
  state.logTailing = true;
  state.logLines   = [];

  const placeholder = document.getElementById('logPlaceholder');
  if (placeholder) placeholder.style.display = 'none';

  document.getElementById('logsStartBtn').textContent = '⏹ Stop Tail';
  document.getElementById('logsStartBtn').onclick = stopLogTail;
  document.getElementById('logStatus').textContent = `Tailing: ${job?.name || jobId}`;

  const lines = generateSampleLogs(job?.name || jobId, 20);
  const term  = document.getElementById('logTerminal');

  // Add initial lines
  lines.forEach(l => appendLogLine(l));

  // Stream new lines
  state.logInterval = setInterval(() => {
    const newLines = generateSampleLogs(job?.name || jobId, 1 + Math.floor(Math.random()*3));
    newLines.forEach(l => appendLogLine(l));
  }, 1200);
}

function stopLogTail() {
  if (state.logInterval) { clearInterval(state.logInterval); state.logInterval = null; }
  state.logTailing = false;
  document.getElementById('logsStartBtn').textContent = '▶ Start Tail';
  document.getElementById('logsStartBtn').onclick = () => {
    const jobId = document.getElementById('logsJobSelect')?.value;
    if (jobId) startLogTail(jobId);
  };
  document.getElementById('logStatus').textContent = 'Stopped';
}

function appendLogLine(html) {
  const term = document.getElementById('logTerminal');
  if (!term) return;
  state.logLines.push(html.replace(/<[^>]+>/g,''));
  const el = document.createElement('span');
  el.className = 'log-line';
  el.innerHTML = html;
  term.appendChild(el);
  document.getElementById('logLineCount').textContent = `${state.logLines.length} lines`;
  if (document.getElementById('logsAutoScroll')?.checked) {
    term.scrollTop = term.scrollHeight;
  }
}

function clearLogs() {
  stopLogTail();
  state.logLines = [];
  const term = document.getElementById('logTerminal');
  if (term) { term.innerHTML = ''; }
  const placeholder = document.getElementById('logPlaceholder');
  if (placeholder) { placeholder.style.display = 'flex'; term.appendChild(placeholder); }
  document.getElementById('logLineCount').textContent = '0 lines';
  document.getElementById('logStatus').textContent = 'Idle';
}

function filterLogs(level) {
  document.querySelectorAll('#logTerminal .log-line').forEach(el => {
    if (level === 'all') { el.style.display = ''; return; }
    el.style.display = el.dataset.level === level ? '' : 'none';
  });
}

/* ──────────────────────────────────────────────────────────────────────
   LOG LINE GENERATION (demo)
────────────────────────────────────────────────────────────────────── */
function generateSampleLogs(jobName, count) {
  const levels = ['INFO','INFO','INFO','WARN','ERROR','DEBUG','INFO','INFO'];
  const messages = [
    'Starting job execution…',
    'Acquiring distributed lock',
    'Lock acquired successfully',
    'Connecting to database',
    'Connection established in 12ms',
    'Running command: /opt/scripts/run.sh',
    'Processing batch 1 of 5…',
    'Processing batch 2 of 5…',
    'Processing batch 3 of 5…',
    'Connection timeout — retrying (attempt 1/3)',
    'Retry successful after 2.3s',
    'Processing batch 4 of 5…',
    'Processing batch 5 of 5…',
    'Writing output to S3://bucket/path/result.json',
    'Upload complete — 2.3MB transferred',
    'Releasing distributed lock',
    'Job completed successfully in 14.2s',
    'Sending Slack notification to #devops-alerts',
    'Notification sent',
    'Cleaning up temporary files…',
    'Temp dir /tmp/tf-abc123 removed',
  ];
  const result = [];
  const now = new Date();
  for (let i = 0; i < count; i++) {
    const level   = levels[Math.floor(Math.random() * levels.length)];
    const msg     = messages[Math.floor(Math.random() * messages.length)];
    const ts      = new Date(now.getTime() + i * 800);
    const tsStr   = ts.toISOString().replace('T',' ').substr(0,23);
    const lvlClass = `log-level-${level.toLowerCase()}`;
    const msgClass = level==='ERROR' ? 'log-msg-error' : level==='WARN' ? 'log-msg-warn' : '';
    const line = `<span class="log-ts">${tsStr}</span><span class="${lvlClass}">[${level.padEnd(5)}]</span> [${jobName}] <span class="${msgClass}">${msg}</span>`;
    result.push(line);
  }
  return result;
}

/* ──────────────────────────────────────────────────────────────────────
   TRIGGERS PAGE
────────────────────────────────────────────────────────────────────── */
function bindTriggersPage() {
  document.getElementById('copyWebhookUrl')?.addEventListener('click', () => {
    const val = document.getElementById('webhookUrl')?.value;
    navigator.clipboard.writeText(val).then(() => toast('success', 'Copied', 'Webhook URL copied to clipboard.'));
  });

  document.getElementById('fireWebhookBtn')?.addEventListener('click', () => {
    const resp = document.getElementById('webhookResponse');
    resp.classList.remove('hidden');
    resp.className = 'webhook-response';
    resp.textContent = 'Sending…';
    setTimeout(() => {
      const ok = Math.random() > 0.2;
      resp.className = `webhook-response ${ok ? 'success' : 'error'}`;
      resp.textContent = ok
        ? `HTTP 200 OK\n{"status":"accepted","run_id":"run-${Date.now()}","queued_at":"${new Date().toISOString()}"}`
        : `HTTP 403 Forbidden\n{"detail":"Invalid HMAC signature"}`;
    }, 800);
  });

  document.getElementById('validateCronBtn')?.addEventListener('click', () => {
    const expr = document.getElementById('cronExpr')?.value;
    const preview = parseCronExpression(expr);
    document.getElementById('cronPreview').textContent = preview;
    updateCronFields(expr);
  });

  document.getElementById('cronExpr')?.addEventListener('input', e => {
    const preview = parseCronExpression(e.target.value);
    document.getElementById('cronPreview').textContent = preview;
    updateCronFields(e.target.value);
  });
}

function parseCronExpression(expr) {
  const parts = expr.trim().split(/\s+/);
  if (parts.length < 5) return 'Invalid cron expression';
  const [min, hour, dom, month, dow] = parts;
  if (min === '0' && hour !== '*' && dom === '*' && month === '*') {
    const h = parseInt(hour);
    if (!isNaN(h)) return `Runs every day at ${String(h).padStart(2,'0')}:00 UTC`;
  }
  if (min !== '*' && hour === '*') return `Runs every hour at minute ${min}`;
  if (expr === '* * * * *') return 'Runs every minute';
  if (expr === '0 * * * *') return 'Runs every hour at :00';
  if (expr === '0 0 * * *') return 'Runs every day at midnight UTC';
  if (expr === '0 0 * * 0') return 'Runs every Sunday at midnight UTC';
  if (expr === '0 0 1 * *') return 'Runs the 1st of every month at midnight UTC';
  return `Cron: ${expr}`;
}

function updateCronFields(expr) {
  const parts = (expr || '').trim().split(/\s+/);
  const fields = ['cf-min','cf-hour','cf-dom','cf-month','cf-dow'];
  fields.forEach((id, i) => {
    const el = document.getElementById(id);
    if (el) el.textContent = parts[i] || '*';
  });
}

/* ──────────────────────────────────────────────────────────────────────
   NOTIFICATIONS PAGE
────────────────────────────────────────────────────────────────────── */
function bindNotificationsPage() {
  document.getElementById('saveNotifBtn')?.addEventListener('click', () => {
    toast('success', 'Saved', 'Notification settings have been saved.');
  });
  ['testSlackBtn','testEmailBtn','testWebhookNotifBtn','testDiscordBtn'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', () => {
      toast('info', 'Test Sent', 'A test notification has been dispatched.');
    });
  });
}

/* ──────────────────────────────────────────────────────────────────────
   METRICS PAGE
────────────────────────────────────────────────────────────────────── */
function bindMetricsPage() {
  document.getElementById('metricsRange')?.addEventListener('change', () => {
    initMetricsCharts();
    toast('info', 'Range Updated', 'Metrics refreshed for selected time range.');
  });
  document.getElementById('exportMetricsBtn')?.addEventListener('click', () => {
    toast('success', 'Exported', 'Metrics CSV download started.');
  });
}

function initMetrics() {
  initMetricsCharts();
}

function initMetricsCharts() {
  if (!window.Chart) return;
  destroyChart('metricsTimelineChart');
  destroyChart('metricsDurationChart');
  destroyChart('metricsTopJobsChart');

  const isDark    = state.theme === 'dark';
  const gridColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
  const textColor = isDark ? '#8b949e' : '#57606a';
  const accent    = getChartColors();

  const labels24 = Array.from({length:24}, (_,i) => `${String(i).padStart(2,'0')}:00`);
  const randArr   = (min, max, n=24) => Array.from({length:n}, () => Math.floor(Math.random()*(max-min+1)+min));

  // Timeline
  const tlCtx = document.getElementById('metricsTimelineChart');
  if (tlCtx) {
    state.charts.metricsTimelineChart = new Chart(tlCtx, {
      type:'line',
      data:{
        labels: labels24,
        datasets:[
          { label:'Success', data: randArr(100,180), borderColor:'#10b981', backgroundColor:'rgba(16,185,129,0.1)', borderWidth:2, fill:true, tension:0.4, pointRadius:2 },
          { label:'Failed',  data: randArr(0,8),     borderColor:'#ef4444', backgroundColor:'rgba(239,68,68,0.1)',  borderWidth:2, fill:true, tension:0.4, pointRadius:2 },
        ]
      },
      options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{labels:{color:textColor}}, tooltip:{backgroundColor:'#0d1117', borderColor:accent, borderWidth:1} }, scales:{ x:{grid:{color:gridColor}, ticks:{color:textColor,maxTicksLimit:12}}, y:{grid:{color:gridColor}, ticks:{color:textColor}} } }
    });
  }

  // Duration distribution
  const durCtx = document.getElementById('metricsDurationChart');
  if (durCtx) {
    state.charts.metricsDurationChart = new Chart(durCtx, {
      type:'bar',
      data:{
        labels:['<1s','1-5s','5-15s','15-60s','1-5m','5-30m','>30m'],
        datasets:[{ label:'Runs', data:[12,58,142,267,98,34,8], backgroundColor: accent + 'cc', borderRadius:4 }]
      },
      options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{labels:{color:textColor}} }, scales:{ x:{grid:{color:gridColor}, ticks:{color:textColor}}, y:{grid:{color:gridColor}, ticks:{color:textColor}} } }
    });
  }

  // Top jobs
  const topCtx = document.getElementById('metricsTopJobsChart');
  if (topCtx) {
    state.charts.metricsTopJobsChart = new Chart(topCtx, {
      type:'bar',
      indexAxis:'y',
      data:{
        labels: state.jobs.slice(0,6).map(j => j.name),
        datasets:[{ label:'Runs', data:[148,82,72,60,48,36], backgroundColor:'rgba(139,92,246,0.7)', borderRadius:4 }]
      },
      options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{labels:{color:textColor}} }, scales:{ x:{grid:{color:gridColor}, ticks:{color:textColor}}, y:{grid:{color:gridColor}, ticks:{color:textColor}} } }
    });
  }
}

/* ──────────────────────────────────────────────────────────────────────
   PLUGINS PAGE
────────────────────────────────────────────────────────────────────── */
function bindPluginsPage() {
  document.getElementById('installPluginBtn')?.addEventListener('click', () => {
    toast('info', 'Coming Soon', 'Plugin marketplace will be available in v0.2.0.');
  });
}

function initPlugins() {
  const grid = document.getElementById('pluginsGrid');
  if (!grid) return;
  grid.innerHTML = state.plugins.map(p => `
    <div class="plugin-card">
      <div class="plugin-card-header">
        <span class="plugin-icon">${p.icon}</span>
        <div>
          <div class="plugin-name">${p.name}</div>
          <div class="plugin-version">v${p.version}</div>
        </div>
        <label class="toggle-switch" style="margin-left:auto">
          <input type="checkbox" ${p.enabled ? 'checked' : ''} onchange="togglePlugin('${p.id}', this.checked)" />
          <span class="toggle-slider"></span>
        </label>
      </div>
      <p class="plugin-desc">${p.desc}</p>
      <div class="plugin-footer">
        <span class="plugin-type-badge">${p.type}</span>
        <div style="display:flex;gap:0.4rem">
          <button class="btn btn-sm btn-secondary" onclick="toast('info','Config','Plugin config UI coming in v0.2.0.')">Configure</button>
          <button class="btn btn-sm btn-secondary" onclick="toast('info','Docs','Viewing ${p.name} documentation.')">Docs</button>
        </div>
      </div>
    </div>
  `).join('');
}

window.togglePlugin = function(id, enabled) {
  const p = state.plugins.find(pl => pl.id === id);
  if (p) {
    p.enabled = enabled;
    toast(enabled ? 'success' : 'warning', `Plugin ${enabled ? 'Enabled' : 'Disabled'}`, `${p.name} has been ${enabled ? 'activated' : 'deactivated'}.`);
  }
};

/* ──────────────────────────────────────────────────────────────────────
   HEALTH PAGE
────────────────────────────────────────────────────────────────────── */
function bindHealthPage() {
  document.getElementById('refreshHealthBtn')?.addEventListener('click', () => {
    initHealth();
    toast('success', 'Refreshed', 'Health data has been updated.');
  });
}

function initHealth() {
  // Banner
  const overview = document.getElementById('healthOverview');
  if (overview) {
    overview.innerHTML = `
      <div class="health-banner ok">
        <span class="health-banner-icon">💚</span>
        <div>
          <div class="health-banner-title">All Systems Operational</div>
          <div class="health-banner-sub">Last check: ${new Date().toLocaleTimeString()} · Uptime: 99.97% (30d)</div>
        </div>
      </div>
    `;
  }

  // Services
  const services = [
    { name:'API Server',      detail:'FastAPI / Uvicorn 4.x',        status:'ok'   },
    { name:'Scheduler',       detail:'APScheduler — 6 active jobs',  status:'ok'   },
    { name:'Database',        detail:'SQLite (aiosqlite)',            status:'ok'   },
    { name:'Event Bus',       detail:'In-process AsyncIO bus',        status:'ok'   },
    { name:'Plugin Loader',   detail:'2 active plugins',             status:'ok'   },
    { name:'Metrics Exporter',detail:'Prometheus on :8080/metrics',  status:'ok'   },
    { name:'Redis',           detail:'Not configured (optional)',     status:'warn' },
  ];

  const hsEl = document.getElementById('healthServices');
  if (hsEl) {
    hsEl.innerHTML = services.map(s => {
      const dot = s.status === 'ok'   ? 'status-online'
                : s.status === 'warn' ? 'status-degraded'
                :                        'status-offline';
      const badge = s.status === 'ok'   ? statusBadge('active')
                  : s.status === 'warn' ? statusBadge('paused')
                  :                       statusBadge('failed');
      return `<div class="health-service-row">
        <div>
          <div class="health-service-name">
            <span class="status-dot ${dot}" style="display:inline-block;margin-right:0.4rem"></span>
            ${s.name}
          </div>
          <div class="health-service-detail">${s.detail}</div>
        </div>
        ${badge}
      </div>`;
    }).join('');
  }

  // Scheduler info
  const siEl = document.getElementById('schedulerInfo');
  if (siEl) {
    const rows = [
      ['State',         'Running'],
      ['Active Jobs',   '6'],
      ['Pending Jobs',  '18'],
      ['Paused Jobs',   '1'],
      ['Backend',       'AsyncIOScheduler'],
      ['Thread Pool',   '4 workers'],
      ['Next Fire',     'in 3m 14s'],
    ];
    siEl.innerHTML = rows.map(([k,v]) => `
      <div class="scheduler-row">
        <span class="scheduler-key">${k}</span>
        <span class="scheduler-val">${v}</span>
      </div>
    `).join('');
  }

  // Env table
  const envBody = document.getElementById('envTableBody');
  if (envBody) {
    envBody.innerHTML = DEMO_ENV.map(e => `
      <tr>
        <td><code style="font-family:var(--font-mono);font-size:0.8rem;color:var(--accent)">${e.key}</code></td>
        <td><code style="font-family:var(--font-mono);font-size:0.8rem">${e.value}</code></td>
        <td><span class="trigger-badge">${e.source}</span></td>
      </tr>
    `).join('');
  }
}

/* ──────────────────────────────────────────────────────────────────────
   SETTINGS PAGE
────────────────────────────────────────────────────────────────────── */
function bindSettingsPage() {
  // Theme buttons
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => setTheme(btn.dataset.theme));
  });

  // Accent colors
  document.querySelectorAll('.color-swatch').forEach(swatch => {
    swatch.addEventListener('click', () => setAccent(swatch.dataset.color));
  });

  document.getElementById('saveSettingsBtn')?.addEventListener('click', () => {
    const url   = document.getElementById('apiBaseUrl')?.value;
    const token = document.getElementById('jwtToken')?.value;
    if (url) localStorage.setItem('tf_api_url', url);
    if (token) localStorage.setItem('tf_token', token);
    toast('success', 'Saved', 'Settings have been saved successfully.');
  });

  document.getElementById('testConnectionBtn')?.addEventListener('click', () => {
    const result = document.getElementById('connectionResult');
    result.classList.remove('hidden', 'ok', 'error');
    result.textContent = 'Testing connection…';
    setTimeout(() => {
      result.classList.add('ok');
      result.textContent = '✓ Connected — TaskForge API v0.1.0 · Latency: 8ms';
    }, 1000);
  });

  document.getElementById('revokeAllTokensBtn')?.addEventListener('click', () => {
    showConfirm('Revoke All Tokens', 'This will sign out all active sessions. Are you sure?', () => {
      toast('warning', 'Tokens Revoked', 'All active sessions have been terminated.');
    });
  });
}

/* ──────────────────────────────────────────────────────────────────────
   JOB MODAL
────────────────────────────────────────────────────────────────────── */
function bindJobModal() {
  // Open
  document.getElementById('createJobBtn')?.addEventListener('click', openCreateJob);
  document.getElementById('createJobBtn2')?.addEventListener('click', openCreateJob);

  // Close
  ['closeJobModal', 'cancelJobModal'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', closeJobModal);
  });
  document.getElementById('jobModal')?.addEventListener('click', e => {
    if (e.target.id === 'jobModal') closeJobModal();
  });

  // Tabs
  document.querySelectorAll('.modal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const pane = tab.dataset.tab;
      document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.modal-tab-pane').forEach(p => p.classList.add('hidden'));
      tab.classList.add('active');
      document.getElementById(`tab-${pane}`)?.classList.remove('hidden');
      if (pane === 'job-json') updateJobJsonPreview();
    });
  });

  // Trigger selector
  document.querySelectorAll('#triggerSelector .trigger-sel-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#triggerSelector .trigger-sel-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.trigger-config').forEach(c => c.classList.add('hidden'));
      document.getElementById(`trigConfig-${btn.dataset.trigger}`)?.classList.remove('hidden');
    });
  });

  // Executor selector
  document.querySelectorAll('#executorSelector .trigger-sel-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#executorSelector .trigger-sel-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.exec-config').forEach(c => c.classList.add('hidden'));
      document.getElementById(`execConfig-${btn.dataset.exec}`)?.classList.remove('hidden');
    });
  });

  // Retry preview
  ['retryMaxAttempts','retryBackoffBase','retryBackoffFactor','retryJitter'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateRetryPreview);
  });

  // Add env var
  document.getElementById('addEnvVarBtn')?.addEventListener('click', () => {
    const list = document.getElementById('shellEnvVars');
    const row  = document.createElement('div');
    row.className = 'env-var-row';
    row.innerHTML = `<input type="text" class="form-input" placeholder="KEY" /><input type="text" class="form-input" placeholder="value" /><button class="btn-icon-sm remove-env-btn" title="Remove">&#x2715;</button>`;
    list.appendChild(row);
    row.querySelector('.remove-env-btn').addEventListener('click', () => row.remove());
  });

  // Remove existing env var
  document.querySelectorAll('.remove-env-btn').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('.env-var-row')?.remove());
  });

  // Add notification rule
  document.getElementById('addNotifRuleBtn')?.addEventListener('click', () => {
    const container = document.getElementById('jobNotifChannels');
    const row = document.createElement('div');
    row.className = 'notif-rule-row';
    row.innerHTML = `<select class="select-input" name="notifChannel"><option value="">Channel…</option><option value="slack">Slack</option><option value="email">Email</option><option value="webhook">Webhook</option><option value="discord">Discord</option></select><select class="select-input" name="notifEvent"><option value="job.failed">job.failed</option><option value="job.success">job.success</option><option value="job.retry">job.retry</option></select><button class="btn-icon-sm remove-notif-btn" title="Remove">&#x2715;</button>`;
    container.appendChild(row);
    row.querySelector('.remove-notif-btn').addEventListener('click', () => row.remove());
  });

  // Remove notification rule
  document.querySelectorAll('.remove-notif-btn').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('.notif-rule-row')?.remove());
  });

  // JSON copy/download
  document.getElementById('copyJobJsonBtn')?.addEventListener('click', () => {
    const json = document.getElementById('jobJsonPreview')?.textContent || '';
    navigator.clipboard.writeText(json).then(() => toast('success', 'Copied', 'Job JSON copied.'));
  });
  document.getElementById('downloadJobJsonBtn')?.addEventListener('click', () => {
    const json = document.getElementById('jobJsonPreview')?.textContent || '';
    const name = document.getElementById('jobName')?.value || 'job';
    const blob = new Blob([json], {type:'application/json'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href=url; a.download=`${name}.json`; a.click();
    URL.revokeObjectURL(url);
  });

  // Save job
  document.getElementById('saveJobBtn')?.addEventListener('click', saveJob);

  // Cron field init
  updateCronFields('0 2 * * *');
  updateRetryPreview();
}

function openCreateJob() {
  state.editingJobId = null;
  document.getElementById('jobModalTitle').textContent = 'Create New Job';
  document.getElementById('jobName').value = '';
  document.getElementById('jobDesc').value = '';
  document.getElementById('jobTags').value = '';
  // Reset tabs
  document.querySelectorAll('.modal-tab').forEach((t,i) => t.classList.toggle('active', i===0));
  document.querySelectorAll('.modal-tab-pane').forEach((p,i) => p.classList.toggle('hidden', i!==0));
  openJobModal();
}

function openJobModal() {
  document.getElementById('jobModal')?.classList.remove('hidden');
}

function closeJobModal() {
  document.getElementById('jobModal')?.classList.add('hidden');
}

function saveJob() {
  const name = document.getElementById('jobName')?.value?.trim();
  if (!name) { toast('error', 'Validation Error', 'Job Name is required.'); return; }

  const triggerBtn  = document.querySelector('#triggerSelector .trigger-sel-btn.active');
  const executorBtn = document.querySelector('#executorSelector .trigger-sel-btn.active');
  const trigger = triggerBtn?.dataset.trigger || 'cron';
  const executor = executorBtn?.dataset.exec  || 'shell';

  if (state.editingJobId) {
    const job = state.jobs.find(j => j.id === state.editingJobId);
    if (job) {
      job.name    = name;
      job.desc    = document.getElementById('jobDesc')?.value || job.desc;
      job.tags    = (document.getElementById('jobTags')?.value || '').split(',').map(t=>t.trim()).filter(Boolean);
      job.trigger = trigger;
      job.executor= executor;
    }
    toast('success', 'Job Updated', `${name} has been updated.`);
  } else {
    const newJob = {
      id:         `job-${Date.now()}`,
      name,
      desc:       document.getElementById('jobDesc')?.value || '',
      trigger,
      triggerExpr: trigger === 'cron' ? (document.getElementById('cronExpr')?.value || '* * * * *') : `every ${document.getElementById('intMinutes')?.value||30}m`,
      executor,
      status:     'active',
      tags:       (document.getElementById('jobTags')?.value||'').split(',').map(t=>t.trim()).filter(Boolean),
      nextRun:    'Scheduled',
      lastRun:    '—',
      lastDuration: '—',
      lastStatus: 'pending',
    };
    state.jobs.unshift(newJob);
    if (state.liveApi) {
      fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: newJob.id,
          name: newJob.name,
          description: newJob.desc,
          trigger: newJob.trigger,
          trigger_expr: newJob.triggerExpr,
          executor: newJob.executor,
          command: "echo 'Executed " + newJob.name + "'",
          status: newJob.status,
          tags: newJob.tags
        })
      }).then(() => syncFromLiveApi()).catch(e => console.error(e));
    }
    toast('success', 'Job Created', `${name} has been created and is now scheduling.`);
  }

  closeJobModal();
  renderJobsTable();
  renderDashboardJobs();
  document.getElementById('badge-jobs').textContent = state.jobs.length;
}

function updateRetryPreview() {
  const max    = parseInt(document.getElementById('retryMaxAttempts')?.value) || 3;
  const base   = parseInt(document.getElementById('retryBackoffBase')?.value)   || 30;
  const factor = parseFloat(document.getElementById('retryBackoffFactor')?.value) || 2.0;
  const jitter = document.getElementById('retryJitter')?.checked;
  const steps  = document.getElementById('retrySteps');
  if (!steps) return;
  let html = '';
  for (let i = 1; i <= max; i++) {
    const wait = Math.round(base * Math.pow(factor, i-1));
    const j    = jitter ? `±${Math.round(wait*0.25)}s jitter` : '';
    html += `<div class="retry-step"><span class="retry-step-num">${i}</span><span class="retry-step-detail">Wait ${wait}s ${j} then retry</span></div>`;
  }
  steps.innerHTML = html;
}

function updateJobJsonPreview() {
  const name    = document.getElementById('jobName')?.value || 'my-job';
  const desc    = document.getElementById('jobDesc')?.value || '';
  const tags    = (document.getElementById('jobTags')?.value||'').split(',').map(t=>t.trim()).filter(Boolean);
  const tz      = document.getElementById('jobTimezone')?.value || 'UTC';
  const trigBtn = document.querySelector('#triggerSelector .trigger-sel-btn.active');
  const execBtn = document.querySelector('#executorSelector .trigger-sel-btn.active');
  const trigger = trigBtn?.dataset.trigger || 'cron';
  const executor= execBtn?.dataset.exec || 'shell';
  const cronExpr= document.getElementById('cronExpr')?.value || '0 2 * * *';
  const shellCmd= document.getElementById('shellCmd')?.value || '/opt/scripts/run.sh';
  const maxAttempts = parseInt(document.getElementById('retryMaxAttempts')?.value)||3;
  const backoffBase  = parseInt(document.getElementById('retryBackoffBase')?.value)||30;
  const backoffFactor= parseFloat(document.getElementById('retryBackoffFactor')?.value)||2.0;
  const jitter  = document.getElementById('retryJitter')?.checked ?? true;

  const obj = {
    name,
    description: desc,
    tags,
    trigger: { type: trigger, config: trigger==='cron' ? {expression:cronExpr,timezone:tz} : {minutes:30} },
    executor: { type: executor, config: executor==='shell' ? {command:shellCmd,timeout_seconds:3600} : {} },
    retry_policy: { max_attempts:maxAttempts, backoff_base:backoffBase, backoff_factor:backoffFactor, jitter },
  };

  document.getElementById('jobJsonPreview').textContent = JSON.stringify(obj, null, 2);
}

/* ──────────────────────────────────────────────────────────────────────
   CONFIRM MODAL
────────────────────────────────────────────────────────────────────── */
function bindConfirmModal() {
  ['closeConfirmModal','cancelConfirmModal'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', closeConfirmModal);
  });
  document.getElementById('okConfirmModal')?.addEventListener('click', () => {
    if (state.confirmCallback) state.confirmCallback();
    closeConfirmModal();
  });
  document.getElementById('confirmModal')?.addEventListener('click', e => {
    if (e.target.id === 'confirmModal') closeConfirmModal();
  });
}

function showConfirm(title, message, callback) {
  document.getElementById('confirmTitle').textContent  = title;
  document.getElementById('confirmMessage').textContent = message;
  state.confirmCallback = callback;
  document.getElementById('confirmModal').classList.remove('hidden');
}

function closeConfirmModal() {
  document.getElementById('confirmModal').classList.add('hidden');
  state.confirmCallback = null;
}

/* ──────────────────────────────────────────────────────────────────────
   LOG MODAL
────────────────────────────────────────────────────────────────────── */
function bindLogModal() {
  ['closeLogModal'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', () => {
      document.getElementById('logModal').classList.add('hidden');
    });
  });
  document.getElementById('logModal')?.addEventListener('click', e => {
    if (e.target.id === 'logModal') document.getElementById('logModal').classList.add('hidden');
  });
}

/* ──────────────────────────────────────────────────────────────────────
   GLOBAL SEARCH
────────────────────────────────────────────────────────────────────── */
function bindGlobalSearch() {
  document.getElementById('globalSearch')?.addEventListener('input', e => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) return;
    const match = state.jobs.find(j => j.name.includes(q) || j.desc.toLowerCase().includes(q));
    if (match && e.key === 'Enter') {
      navigateTo('jobs');
      state.jobSearch = q;
      document.getElementById('jobSearchInput').value = q;
      renderJobsTable();
    }
  });
  document.getElementById('globalSearch')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const q = e.target.value.toLowerCase().trim();
      if (q) { navigateTo('jobs'); state.jobSearch = q; renderJobsTable(); }
    }
  });
}

/* ──────────────────────────────────────────────────────────────────────
   KEYBOARD SHORTCUTS
────────────────────────────────────────────────────────────────────── */
function bindKeyboardShortcuts() {
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      document.getElementById('globalSearch')?.focus();
    }
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => {
        if (m.id === 'loginOverlay') return;
        m.classList.add('hidden');
      });
      closeConfirmModal();
    }
  });
}

/* ──────────────────────────────────────────────────────────────────────
   PAGINATION
────────────────────────────────────────────────────────────────────── */
function renderPagination(paginationId, infoId, total, current, perPage, onChange) {
  const totalPages = Math.ceil(total / perPage);
  const start = (current - 1) * perPage + 1;
  const end   = Math.min(current * perPage, total);

  if (infoId) {
    document.getElementById(infoId).textContent = `Showing ${start}–${end} of ${total}`;
  }

  const container = document.getElementById(paginationId);
  if (!container) return;
  container.innerHTML = '';

  const mkBtn = (label, page, disabled=false, active=false) => {
    const btn = document.createElement('button');
    btn.className = `page-btn${active?' active':''}`;
    btn.textContent = label;
    btn.disabled = disabled;
    btn.addEventListener('click', () => onChange(page));
    return btn;
  };

  container.appendChild(mkBtn('‹', current-1, current===1));

  const range = pageRange(current, totalPages);
  range.forEach(p => {
    if (p === '…') {
      const span = document.createElement('span');
      span.textContent = '…';
      span.style.padding = '0.35rem 0.4rem';
      span.style.color = 'var(--text-3)';
      container.appendChild(span);
    } else {
      container.appendChild(mkBtn(p, p, false, p===current));
    }
  });

  container.appendChild(mkBtn('›', current+1, current===totalPages));
}

function pageRange(current, total) {
  if (total <= 7) return Array.from({length:total},(_,i)=>i+1);
  if (current <= 4) return [1,2,3,4,5,'…',total];
  if (current >= total-3) return [1,'…',total-4,total-3,total-2,total-1,total];
  return [1,'…',current-1,current,current+1,'…',total];
}

/* ──────────────────────────────────────────────────────────────────────
   TOAST SYSTEM
────────────────────────────────────────────────────────────────────── */
function toast(type, title, message, duration=4000) {
  const icons = { success:'✅', error:'❌', warning:'⚠️', info:'ℹ️' };
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `
    <span class="toast-icon">${icons[type]||'ℹ️'}</span>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      ${message ? `<div class="toast-msg">${message}</div>` : ''}
    </div>
    <button class="toast-close" onclick="this.closest('.toast').remove()">✕</button>
  `;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add('dismissing');
    setTimeout(() => el.remove(), 350);
  }, duration);
}

/* ──────────────────────────────────────────────────────────────────────
   STATUS BADGE HELPER
────────────────────────────────────────────────────────────────────── */
function statusBadge(status) {
  const map = {
    success:   'badge-success',
    failed:    'badge-failed',
    running:   'badge-running',
    paused:    'badge-paused',
    pending:   'badge-pending',
    cancelled: 'badge-cancelled',
    active:    'badge-active',
  };
  const cls = map[status] || 'badge-pending';
  return `<span class="badge ${cls}">${status}</span>`;
}

/* ──────────────────────────────────────────────────────────────────────
   UPTIME COUNTER
────────────────────────────────────────────────────────────────────── */
function updateUptime() {
  const el = document.getElementById('uptimeValue');
  if (!el) return;
  let seconds = 2 * 86400 + 14 * 3600 + 38 * 60;
  setInterval(() => {
    seconds++;
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    el.innerHTML = `<code>${d}d ${h}h ${m}m</code>`;
  }, 60000);
}
