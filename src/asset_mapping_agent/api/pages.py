from __future__ import annotations

import json
from html import escape
from typing import Any


BASE_STYLES = """
  <style>
    :root {
      --paper: #f7f2e8;
      --ink: #1f1a17;
      --muted: #6e6258;
      --line: #d9ccbb;
      --panel: rgba(255,255,255,0.78);
      --accent: #a3482f;
      --accent-soft: #ead5ca;
      --accent-cool: rgba(47,107,79,0.14);
      --success: #2f6b4f;
      --warning: #8a5a16;
      --danger: #8a2f2f;
      --shadow: 0 18px 40px rgba(66, 44, 24, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(163,72,47,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(53,91,74,0.10), transparent 26%),
        linear-gradient(180deg, #f9f5ed 0%, #f2eadc 100%);
      min-height: 100vh;
    }
    .shell {
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }
    .hero {
      display: grid;
      gap: 12px;
      margin-bottom: 18px;
    }
    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--accent);
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1.05;
      font-weight: 800;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      max-width: 920px;
      line-height: 1.6;
    }
    .toolbar {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 8px;
    }
    button, .link-btn, select, input {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      padding: 10px 14px;
      border-radius: 999px;
      text-decoration: none;
      box-shadow: var(--shadow);
      font-size: 14px;
    }
    button, .link-btn { cursor: pointer; transition: transform .18s ease, border-color .18s ease; }
    button:hover, .link-btn:hover { transform: translateY(-1px); border-color: var(--accent); }
    input, select { min-width: 160px; }
    .panel {
      background: var(--panel);
      border: 1px solid rgba(217,204,187,0.92);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
      overflow: hidden;
    }
    .panel-inner {
      padding: 18px 20px 20px;
    }
    .panel-title {
      margin: 0 0 14px;
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .grid {
      display: grid;
      gap: 18px;
    }
    .two-col {
      grid-template-columns: 1.1fr 0.9fr;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      padding: 14px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.88), rgba(248,241,232,0.94));
      border: 1px solid rgba(217,204,187,0.9);
    }
    .metric label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
      letter-spacing: 0.04em;
    }
    .metric strong { font-size: 24px; }
    .meta-list {
      display: grid;
      gap: 10px;
    }
    .meta-row {
      display: grid;
      grid-template-columns: 112px 1fr;
      gap: 12px;
      align-items: start;
      padding: 10px 0;
      border-top: 1px dashed rgba(217,204,187,0.92);
    }
    .meta-row:first-child { border-top: 0; }
    .meta-row span { color: var(--muted); }
    .chips { display: flex; gap: 8px; flex-wrap: wrap; }
    .chip {
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      background: var(--accent-soft);
      color: var(--ink);
      border: 1px solid rgba(163,72,47,0.16);
    }
    .chip.success { background: rgba(47,107,79,0.14); color: var(--success); border-color: rgba(47,107,79,0.2); }
    .chip.warning { background: rgba(138,90,22,0.14); color: var(--warning); border-color: rgba(138,90,22,0.2); }
    .chip.danger { background: rgba(138,47,47,0.14); color: var(--danger); border-color: rgba(138,47,47,0.2); }
    .chip.cool { background: rgba(47,107,79,0.08); color: var(--success); border-color: rgba(47,107,79,0.12); }
    .mono { font-family: Consolas, "SFMono-Regular", monospace; word-break: break-all; }
    .timeline { display: grid; gap: 12px; }
    .event {
      padding: 12px 12px 12px 18px;
      border-left: 3px solid rgba(163,72,47,0.35);
      background: rgba(255,255,255,0.55);
      border-radius: 0 14px 14px 0;
    }
    .event time { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .query-list, .asset-list { display: grid; gap: 12px; }
    .query-card, .asset-card {
      padding: 14px;
      border: 1px solid rgba(217,204,187,0.92);
      border-radius: 18px;
      background: rgba(255,255,255,0.62);
    }
    .query-top, .asset-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 10px;
    }
    .asset-main {
      display: grid;
      gap: 10px;
    }
    .asset-url {
      font-size: 13px;
      color: var(--muted);
      word-break: break-all;
    }
    pre {
      margin: 0;
      padding: 12px;
      background: #201c19;
      color: #f9f5ed;
      border-radius: 14px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.5;
    }
    .warning-list { margin: 10px 0 0; padding-left: 18px; color: var(--warning); }
    .filters {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 14px;
    }
    .empty { color: var(--muted); font-size: 14px; }
    .footer-note { margin-top: 16px; color: var(--muted); font-size: 13px; }
    .stat-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    @media (max-width: 960px) {
      .two-col { grid-template-columns: 1fr; }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .metric-grid { grid-template-columns: 1fr; }
      .meta-row { grid-template-columns: 1fr; gap: 6px; }
      .shell { padding: 18px 14px 28px; }
    }
  </style>
"""


def _json_embed(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_task_status_page(task: dict[str, Any], queries: list[dict[str, Any]]) -> str:
    task_json = _json_embed(task)
    queries_json = _json_embed(queries)
    task_id = escape(str(task.get("task_id") or ""))
    source_text = escape(str(task.get("source_text") or ""))
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>任务执行状态 - {task_id}</title>
{BASE_STYLES}
</head>
<body>
  <main class=\"shell\">
    <section class=\"hero\">
      <div class=\"eyebrow\">Task Status</div>
      <h1>任务执行状态页</h1>
      <p class=\"subtitle\">这里展示任务当前阶段、平台查询概况、资产计数、审计日志和报告入口。状态为 <span class=\"mono\">running/pending</span> 时页面会自动轮询刷新。</p>
      <div class=\"toolbar\">
        <button type=\"button\" id=\"refresh-btn\">立即刷新</button>
        <a class=\"link-btn\" href=\"/tasks/history-page\" target=\"_blank\">历史任务页</a>
        <a class=\"link-btn\" href=\"/tasks/{task_id}/results-page\" target=\"_blank\">打开结果页</a>
        <a class=\"link-btn\" id=\"task-json-link\" href=\"/tasks/{task_id}\" target=\"_blank\">查看任务 JSON</a>
        <a class=\"link-btn\" id=\"report-link\" href=\"/tasks/{task_id}/report\" target=\"_blank\" hidden>下载 xlsx 报告</a>
      </div>
    </section>

    <section class=\"grid two-col\">
      <div class=\"panel\">
        <div class=\"panel-inner\">
          <h2 class=\"panel-title\">任务总览</h2>
          <div class=\"metric-grid\">
            <div class=\"metric\"><label>任务状态</label><strong id=\"task-status\">-</strong></div>
            <div class=\"metric\"><label>当前阶段</label><strong id=\"task-stage\">-</strong></div>
            <div class=\"metric\"><label>查询数量</label><strong id=\"query-count\">0</strong></div>
            <div class=\"metric\"><label>资产数量</label><strong id=\"asset-count\">0</strong></div>
          </div>
          <div class=\"meta-list\" style=\"margin-top:16px\">
            <div class=\"meta-row\"><span>任务ID</span><div class=\"mono\" id=\"task-id\">{task_id}</div></div>
            <div class=\"meta-row\"><span>原始输入</span><div id=\"source-text\">{source_text}</div></div>
            <div class=\"meta-row\"><span>平台</span><div class=\"chips\" id=\"platform-list\"></div></div>
            <div class=\"meta-row\"><span>解析告警</span><div id=\"parse-warnings\" class=\"empty\">无</div></div>
            <div class=\"meta-row\"><span>报告输出</span><div class=\"mono\" id=\"report-path\">未生成</div></div>
            <div class=\"meta-row\"><span>创建时间</span><div class=\"mono\" id=\"created-at\">-</div></div>
            <div class=\"meta-row\"><span>更新时间</span><div class=\"mono\" id=\"updated-at\">-</div></div>
            <div class=\"meta-row\"><span>错误信息</span><div id=\"error-message\" class=\"empty\">无</div></div>
          </div>
        </div>
      </div>

      <div class=\"panel\">
        <div class=\"panel-inner\">
          <h2 class=\"panel-title\">审计日志</h2>
          <div id=\"audit-log\" class=\"timeline\"></div>
          <p class=\"footer-note\">状态页默认轮询任务详情与查询摘要，不直接拉取大体量资产明细。</p>
        </div>
      </div>
    </section>

    <section class=\"panel\" style=\"margin-top:18px\">
      <div class=\"panel-inner\">
        <h2 class=\"panel-title\">平台查询状态</h2>
        <div id=\"query-list\" class=\"query-list\"></div>
      </div>
    </section>
  </main>

  <script>
    const initialTask = {task_json};
    const initialQueries = {queries_json};
    const taskId = initialTask.task_id;
    let pollTimer = null;

    const statusEl = document.getElementById('task-status');
    const stageEl = document.getElementById('task-stage');
    const queryCountEl = document.getElementById('query-count');
    const assetCountEl = document.getElementById('asset-count');
    const sourceTextEl = document.getElementById('source-text');
    const platformListEl = document.getElementById('platform-list');
    const parseWarningsEl = document.getElementById('parse-warnings');
    const reportPathEl = document.getElementById('report-path');
    const createdAtEl = document.getElementById('created-at');
    const updatedAtEl = document.getElementById('updated-at');
    const errorMessageEl = document.getElementById('error-message');
    const auditLogEl = document.getElementById('audit-log');
    const queryListEl = document.getElementById('query-list');
    const reportLinkEl = document.getElementById('report-link');

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>\"]/g, (char) => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }})[char]);
    }}

    function renderSimpleList(values, emptyText='无') {{
      if (!values || values.length === 0) return `<span class=\"empty\">${{escapeHtml(emptyText)}}</span>`;
      return values.map((value) => `<span class=\"chip\">${{escapeHtml(value)}}</span>`).join('');
    }}

    function renderTask(task) {{
      statusEl.textContent = task.status || '-';
      stageEl.textContent = task.current_stage || '-';
      queryCountEl.textContent = String(task.query_count ?? 0);
      assetCountEl.textContent = String(task.asset_count ?? 0);
      sourceTextEl.textContent = task.source_text || '';
      platformListEl.innerHTML = renderSimpleList(task.platforms, '无平台');
      parseWarningsEl.innerHTML = renderSimpleList(task.parse_warnings, '无');
      createdAtEl.textContent = task.created_at || '-';
      updatedAtEl.textContent = task.updated_at || '-';
      errorMessageEl.innerHTML = task.error_message ? `<span class=\"chip danger\">${{escapeHtml(task.error_message)}}</span>` : '<span class=\"empty\">无</span>';
      reportPathEl.textContent = task.report?.output_path || '未生成';
      reportLinkEl.hidden = !task.report?.output_path;
      if (task.report?.output_path) {{
        reportLinkEl.href = `/tasks/${{task.task_id}}/report`;
      }}

      const auditItems = task.audit_log || [];
      auditLogEl.innerHTML = auditItems.length
        ? auditItems.map((item) => `
            <article class=\"event\">
              <time class=\"mono\">${{escapeHtml(item.timestamp)}}</time>
              <strong>${{escapeHtml(item.event)}}</strong>
              <div>${{escapeHtml(item.detail || '无')}}</div>
            </article>
          `).join('')
        : '<p class=\"empty\">暂无审计日志</p>';
    }}

    function renderQueries(queries) {{
      queryListEl.innerHTML = (queries && queries.length)
        ? queries.map((item) => `
            <article class=\"query-card\">
              <div class=\"query-top\">
                <div class=\"chips\">
                  <span class=\"chip\">${{escapeHtml(item.platform)}}</span>
                  <span class=\"chip\">命中 ${{escapeHtml(item.record_count)}}</span>
                  <span class=\"chip\">HTTP ${{escapeHtml(item.response?.status_code ?? '-')}}</span>
                </div>
              </div>
              <pre>${{escapeHtml(item.compiled_query || '')}}</pre>
              ${{item.warnings && item.warnings.length ? `<ul class=\"warning-list\">${{item.warnings.map((warning) => `<li>${{escapeHtml(warning)}}</li>`).join('')}}</ul>` : ''}}
            </article>
          `).join('')
        : '<p class=\"empty\">暂无查询记录</p>';
    }}

    async function refresh() {{
      const [taskResp, queriesResp] = await Promise.all([
        fetch(`/tasks/${{taskId}}`),
        fetch(`/tasks/${{taskId}}/queries`),
      ]);
      if (!taskResp.ok) throw new Error(`task http ${{taskResp.status}}`);
      if (!queriesResp.ok) throw new Error(`queries http ${{queriesResp.status}}`);
      const task = await taskResp.json();
      const queryPayload = await queriesResp.json();
      renderTask(task);
      renderQueries(queryPayload.queries || []);
      syncPolling(task);
    }}

    function syncPolling(task) {{
      const shouldPoll = ['pending', 'running'].includes(task.status);
      if (shouldPoll && !pollTimer) {{
        pollTimer = window.setInterval(() => {{ refresh().catch(console.error); }}, 3000);
      }}
      if (!shouldPoll && pollTimer) {{
        window.clearInterval(pollTimer);
        pollTimer = null;
      }}
    }}

    document.getElementById('refresh-btn').addEventListener('click', () => {{
      refresh().catch(console.error);
    }});

    renderTask(initialTask);
    renderQueries(initialQueries);
    syncPolling(initialTask);
  </script>
</body>
</html>"""


def render_task_results_page(task: dict[str, Any], assets: list[dict[str, Any]]) -> str:
    task_json = _json_embed(task)
    assets_json = _json_embed(assets)
    task_id = escape(str(task.get("task_id") or ""))
    source_text = escape(str(task.get("source_text") or ""))
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>资产结果页 - {task_id}</title>
{BASE_STYLES}
</head>
<body>
  <main class=\"shell\">
    <section class=\"hero\">
      <div class=\"eyebrow\">Asset Results</div>
      <h1>任务资产结果页</h1>
      <p class=\"subtitle\">这里聚焦归并后的资产结果，支持本地筛选、验证状态查看和直接下载报告。任务尚未完成时，页面会自动轮询等待资产就绪。</p>
      <div class=\"toolbar\">
        <button type=\"button\" id=\"refresh-btn\">立即刷新</button>
        <a class=\"link-btn\" href=\"/tasks/history-page\" target=\"_blank\">历史任务页</a>
        <a class=\"link-btn\" href=\"/tasks/{task_id}/status-page\" target=\"_blank\">返回状态页</a>
        <a class=\"link-btn\" href=\"/tasks/{task_id}\" target=\"_blank\">查看任务 JSON</a>
        <a class=\"link-btn\" id=\"report-link\" href=\"/tasks/{task_id}/report\" target=\"_blank\" hidden>下载 xlsx 报告</a>
      </div>
    </section>

    <section class=\"panel\">
      <div class=\"panel-inner\">
        <h2 class=\"panel-title\">任务概览</h2>
        <div class=\"metric-grid\">
          <div class=\"metric\"><label>总资产</label><strong id=\"total-assets\">0</strong></div>
          <div class=\"metric\"><label>重点资产</label><strong id=\"key-assets\">0</strong></div>
          <div class=\"metric\"><label>已验证</label><strong id=\"verified-assets\">0</strong></div>
          <div class=\"metric\"><label>无效资产</label><strong id=\"invalid-assets\">0</strong></div>
        </div>
        <div class=\"meta-list\" style=\"margin-top:16px\">
          <div class=\"meta-row\"><span>任务ID</span><div class=\"mono\">{task_id}</div></div>
          <div class=\"meta-row\"><span>原始输入</span><div>{source_text}</div></div>
          <div class=\"meta-row\"><span>当前状态</span><div class=\"chips\" id=\"task-status-chips\"></div></div>
          <div class=\"meta-row\"><span>报告输出</span><div class=\"mono\" id=\"report-path\">未生成</div></div>
        </div>
      </div>
    </section>

    <section class=\"panel\" style=\"margin-top:18px\">
      <div class=\"panel-inner\">
        <h2 class=\"panel-title\">筛选器</h2>
        <div class=\"filters\">
          <input id=\"search-input\" type=\"search\" placeholder=\"按 host / title / url / org 搜索\">
          <select id=\"verification-filter\">
            <option value=\"all\">全部验证状态</option>
            <option value=\"success\">仅成功</option>
            <option value=\"invalid\">仅无效</option>
            <option value=\"unverified\">仅未验证</option>
          </select>
          <select id=\"tag-filter\">
            <option value=\"all\">全部标签</option>
            <option value=\"key\">仅重点资产</option>
            <option value=\"login_page\">login_page</option>
            <option value=\"admin_panel\">admin_panel</option>
            <option value=\"middleware_console\">middleware_console</option>
          </select>
        </div>
        <div id=\"asset-list\" class=\"asset-list\"></div>
      </div>
    </section>
  </main>

  <script>
    const initialTask = {task_json};
    const initialAssets = {assets_json};
    const taskId = initialTask.task_id;
    let state = {{ task: initialTask, assets: initialAssets }};
    let pollTimer = null;

    const totalAssetsEl = document.getElementById('total-assets');
    const keyAssetsEl = document.getElementById('key-assets');
    const verifiedAssetsEl = document.getElementById('verified-assets');
    const invalidAssetsEl = document.getElementById('invalid-assets');
    const taskStatusChipsEl = document.getElementById('task-status-chips');
    const reportPathEl = document.getElementById('report-path');
    const assetListEl = document.getElementById('asset-list');
    const reportLinkEl = document.getElementById('report-link');
    const searchInputEl = document.getElementById('search-input');
    const verificationFilterEl = document.getElementById('verification-filter');
    const tagFilterEl = document.getElementById('tag-filter');

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>\"]/g, (char) => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }})[char]);
    }}

    function latestVerification(asset) {{
      const verifications = asset.verification_results || [];
      return verifications.length ? verifications[verifications.length - 1] : null;
    }}

    function isKeyAsset(asset) {{
      return (asset.tags || []).some((tag) => ['login_page', 'admin_panel', 'middleware_console'].includes(tag) || tag.startsWith('middleware:'));
    }}

    function isInvalidAsset(asset) {{
      const latest = latestVerification(asset);
      return latest && ['network_error', 'timeout', 'refused'].includes(latest.status);
    }}

    function renderSummary(task, assets) {{
      const verifiedCount = assets.filter((asset) => latestVerification(asset)).length;
      const keyCount = assets.filter((asset) => isKeyAsset(asset)).length;
      const invalidCount = assets.filter((asset) => isInvalidAsset(asset)).length;
      totalAssetsEl.textContent = String(assets.length);
      keyAssetsEl.textContent = String(task.report?.key_assets ?? keyCount);
      verifiedAssetsEl.textContent = String(verifiedCount);
      invalidAssetsEl.textContent = String(task.report?.invalid_assets ?? invalidCount);
      taskStatusChipsEl.innerHTML = `
        <span class=\"chip\">${{escapeHtml(task.status || '-')}}</span>
        <span class=\"chip cool\">${{escapeHtml(task.current_stage || '-')}}</span>
      `;
      reportPathEl.textContent = task.report?.output_path || '未生成';
      reportLinkEl.hidden = !task.report?.output_path;
      if (task.report?.output_path) {{
        reportLinkEl.href = `/tasks/${{task.task_id}}/report`;
      }}
    }}

    function matchesFilters(asset) {{
      const keyword = searchInputEl.value.trim().toLowerCase();
      const verificationFilter = verificationFilterEl.value;
      const tagFilter = tagFilterEl.value;
      const latest = latestVerification(asset);
      const searchable = [asset.host, asset.domain, asset.ip, asset.url, asset.title, asset.product, asset.org].join(' ').toLowerCase();

      if (keyword && !searchable.includes(keyword)) return false;
      if (verificationFilter === 'success' && (!latest || latest.status !== 'success')) return false;
      if (verificationFilter === 'invalid' && !isInvalidAsset(asset)) return false;
      if (verificationFilter === 'unverified' && latest) return false;
      if (tagFilter === 'key' && !isKeyAsset(asset)) return false;
      if (!['all', 'key'].includes(tagFilter) && !(asset.tags || []).includes(tagFilter)) return false;
      return true;
    }}

    function renderAssets(task, assets) {{
      const filtered = assets.filter(matchesFilters);
      if (!filtered.length) {{
        assetListEl.innerHTML = '<p class=\"empty\">当前筛选条件下没有资产记录。</p>';
        return;
      }}
      assetListEl.innerHTML = filtered.map((asset) => {{
        const latest = latestVerification(asset);
        const verificationText = latest ? `${{escapeHtml(latest.status)}}${{latest.status_code ? ` / ${{escapeHtml(latest.status_code)}}` : ''}}` : '未验证';
        const chips = [
          ...(asset.tags || []).map((tag) => `<span class=\"chip\">${{escapeHtml(tag)}}</span>`),
          ...(asset.source_platforms || []).map((platform) => `<span class=\"chip cool\">${{escapeHtml(platform)}}</span>`),
        ].join('');
        return `
          <article class=\"asset-card\">
            <div class=\"asset-top\">
              <div class=\"asset-main\">
                <strong>${{escapeHtml(asset.title || asset.host || asset.domain || asset.ip || '未命名资产')}}</strong>
                <div class=\"asset-url mono\">${{escapeHtml(asset.url || asset.host || asset.domain || asset.ip || '')}}</div>
                <div class=\"chips\">${{chips || '<span class=\"empty\">无标签</span>'}}</div>
              </div>
              <div class=\"stat-row\">
                <span class=\"chip\">${{escapeHtml(asset.scheme || '-')}}:${{escapeHtml(asset.port ?? '-')}}</span>
                <span class=\"chip ${{latest?.status === 'success' ? 'success' : isInvalidAsset(asset) ? 'danger' : latest ? 'warning' : ''}}\">${{verificationText}}</span>
              </div>
            </div>
            <div class=\"meta-list\">
              <div class=\"meta-row\"><span>主机 / 域名</span><div class=\"mono\">${{escapeHtml(asset.host || asset.domain || asset.ip || '')}}</div></div>
              <div class=\"meta-row\"><span>组织</span><div>${{escapeHtml(asset.org || '-')}}</div></div>
              <div class=\"meta-row\"><span>服务 / 产品</span><div>${{escapeHtml(asset.service || '-')}} / ${{escapeHtml(asset.product || '-')}}</div></div>
              <div class=\"meta-row\"><span>地域</span><div>${{escapeHtml(asset.geo?.country || '-')}} / ${{escapeHtml(asset.geo?.province || '-')}} / ${{escapeHtml(asset.geo?.city || '-')}}</div></div>
              <div class=\"meta-row\"><span>验证结果</span><div>${{latest ? escapeHtml(latest.detail || latest.title || latest.status) : '未验证'}}</div></div>
            </div>
          </article>
        `;
      }}).join('');
    }}

    async function refresh() {{
      const [taskResp, assetsResp] = await Promise.all([
        fetch(`/tasks/${{taskId}}`),
        fetch(`/tasks/${{taskId}}/assets`),
      ]);
      if (!taskResp.ok) throw new Error(`task http ${{taskResp.status}}`);
      if (!assetsResp.ok) throw new Error(`assets http ${{assetsResp.status}}`);
      const task = await taskResp.json();
      const assetsPayload = await assetsResp.json();
      state = {{ task, assets: assetsPayload.assets || [] }};
      renderSummary(state.task, state.assets);
      renderAssets(state.task, state.assets);
      syncPolling(task);
    }}

    function syncPolling(task) {{
      const shouldPoll = ['pending', 'running'].includes(task.status);
      if (shouldPoll && !pollTimer) {{
        pollTimer = window.setInterval(() => {{ refresh().catch(console.error); }}, 4000);
      }}
      if (!shouldPoll && pollTimer) {{
        window.clearInterval(pollTimer);
        pollTimer = null;
      }}
    }}

    [searchInputEl, verificationFilterEl, tagFilterEl].forEach((element) => {{
      element.addEventListener('input', () => renderAssets(state.task, state.assets));
      element.addEventListener('change', () => renderAssets(state.task, state.assets));
    }});

    document.getElementById('refresh-btn').addEventListener('click', () => {{
      refresh().catch(console.error);
    }});

    renderSummary(state.task, state.assets);
    renderAssets(state.task, state.assets);
    syncPolling(state.task);
  </script>
</body>
</html>"""


def render_task_history_page(tasks: list[dict[str, Any]]) -> str:
    tasks_json = _json_embed(tasks)
    template = """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>历史任务页</title>
{BASE_STYLES}
</head>
<body>
  <main class=\"shell\">
    <section class=\"hero\">
      <div class=\"eyebrow\">Task History</div>
      <h1>历史任务与审计入口</h1>
      <p class=\"subtitle\">这里聚合当前进程中的历史任务记录。你可以直接跳转到单任务的状态页、结果页、JSON、审计日志和报告下载入口，也可以查看最近一次审计事件。</p>
      <div class=\"toolbar\">
        <button type=\"button\" id=\"refresh-btn\">立即刷新</button>
        <input id=\"search-input\" type=\"search\" placeholder=\"按任务文本、任务ID或平台搜索\">
        <select id=\"status-filter\">
          <option value=\"all\">全部状态</option>
          <option value=\"pending\">pending</option>
          <option value=\"running\">running</option>
          <option value=\"succeeded\">succeeded</option>
          <option value=\"failed\">failed</option>
        </select>
      </div>
    </section>

    <section class=\"panel\">
      <div class=\"panel-inner\">
        <h2 class=\"panel-title\">任务汇总</h2>
        <div class=\"metric-grid\">
          <div class=\"metric\"><label>任务总数</label><strong id=\"total-tasks\">0</strong></div>
          <div class=\"metric\"><label>运行中</label><strong id=\"running-tasks\">0</strong></div>
          <div class=\"metric\"><label>已完成</label><strong id=\"succeeded-tasks\">0</strong></div>
          <div class=\"metric\"><label>失败任务</label><strong id=\"failed-tasks\">0</strong></div>
        </div>
      </div>
    </section>

    <section class=\"panel\" style=\"margin-top:18px\">
      <div class=\"panel-inner\">
        <h2 class=\"panel-title\">任务列表</h2>
        <div id=\"task-list\" class=\"asset-list\"></div>
      </div>
    </section>
  </main>

  <script>
    const initialTasks = __TASKS_JSON__;
    let tasksState = initialTasks;
    let pollTimer = null;

    const totalTasksEl = document.getElementById('total-tasks');
    const runningTasksEl = document.getElementById('running-tasks');
    const succeededTasksEl = document.getElementById('succeeded-tasks');
    const failedTasksEl = document.getElementById('failed-tasks');
    const taskListEl = document.getElementById('task-list');
    const searchInputEl = document.getElementById('search-input');
    const statusFilterEl = document.getElementById('status-filter');

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>\"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[char]);
    }

    function latestAudit(task) {
      const auditLog = task.audit_log || [];
      return auditLog.length ? auditLog[auditLog.length - 1] : null;
    }

    function matchesFilters(task) {
      const keyword = searchInputEl.value.trim().toLowerCase();
      const status = statusFilterEl.value;
      const searchable = [task.task_id, task.source_text, ...(task.platforms || [])].join(' ').toLowerCase();
      if (keyword && !searchable.includes(keyword)) return false;
      if (status !== 'all' && task.status !== status) return false;
      return true;
    }

    function renderSummary(tasks) {
      totalTasksEl.textContent = String(tasks.length);
      runningTasksEl.textContent = String(tasks.filter((item) => item.status === 'running').length);
      succeededTasksEl.textContent = String(tasks.filter((item) => item.status === 'succeeded').length);
      failedTasksEl.textContent = String(tasks.filter((item) => item.status === 'failed').length);
    }

    function renderTasks(tasks) {
      const filtered = tasks.filter(matchesFilters);
      if (!filtered.length) {
        taskListEl.innerHTML = '<p class=\"empty\">当前没有符合条件的历史任务。</p>';
        return;
      }
      taskListEl.innerHTML = filtered.map((task) => {
        const latest = latestAudit(task);
        const latestText = latest ? `${escapeHtml(latest.event)} / ${escapeHtml(latest.timestamp)}` : '暂无审计日志';
        return `
          <article class=\"asset-card\">
            <div class=\"asset-top\">
              <div class=\"asset-main\">
                <strong>${escapeHtml(task.source_text || task.task_id)}</strong>
                <div class=\"asset-url mono\">${escapeHtml(task.task_id)}</div>
                <div class=\"chips\">
                  <span class=\"chip\">${escapeHtml(task.status)}</span>
                  <span class=\"chip cool\">${escapeHtml(task.current_stage)}</span>
                  ${(task.platforms || []).map((platform) => `<span class=\"chip\">${escapeHtml(platform)}</span>`).join('')}
                </div>
              </div>
              <div class=\"stat-row\">
                <span class=\"chip\">查询 ${escapeHtml(task.query_count ?? 0)}</span>
                <span class=\"chip\">资产 ${escapeHtml(task.asset_count ?? 0)}</span>
              </div>
            </div>
            <div class=\"meta-list\">
              <div class=\"meta-row\"><span>最近审计</span><div>${latestText}</div></div>
              <div class=\"meta-row\"><span>更新时间</span><div class=\"mono\">${escapeHtml(task.updated_at || '-')}</div></div>
              <div class=\"meta-row\"><span>快捷入口</span><div class=\"chips\">
                <a class=\"link-btn\" href=\"/tasks/${escapeHtml(task.task_id)}/status-page\" target=\"_blank\">状态页</a>
                <a class=\"link-btn\" href=\"/tasks/${escapeHtml(task.task_id)}/results-page\" target=\"_blank\">结果页</a>
                <a class=\"link-btn\" href=\"/tasks/${escapeHtml(task.task_id)}/audit-log\" target=\"_blank\">审计日志</a>
                <a class=\"link-btn\" href=\"/tasks/${escapeHtml(task.task_id)}\" target=\"_blank\">JSON</a>
                ${task.report?.output_path ? `<a class=\"link-btn\" href=\"/tasks/${escapeHtml(task.task_id)}/report\" target=\"_blank\">报告</a>` : ''}
              </div></div>
            </div>
          </article>
        `;
      }).join('');
    }

    function syncPolling(tasks) {
      const shouldPoll = tasks.some((task) => ['pending', 'running'].includes(task.status));
      if (shouldPoll && !pollTimer) {
        pollTimer = window.setInterval(() => { refresh().catch(console.error); }, 5000);
      }
      if (!shouldPoll && pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    async function refresh() {
      const response = await fetch('/tasks');
      if (!response.ok) throw new Error(`tasks http ${response.status}`);
      const payload = await response.json();
      tasksState = payload.tasks || [];
      renderSummary(tasksState);
      renderTasks(tasksState);
      syncPolling(tasksState);
    }

    [searchInputEl, statusFilterEl].forEach((element) => {
      element.addEventListener('input', () => renderTasks(tasksState));
      element.addEventListener('change', () => renderTasks(tasksState));
    });

    document.getElementById('refresh-btn').addEventListener('click', () => {
      refresh().catch(console.error);
    });

    renderSummary(tasksState);
    renderTasks(tasksState);
    syncPolling(tasksState);
  </script>
</body>
</html>"""
    return template.replace('{BASE_STYLES}', BASE_STYLES).replace('__TASKS_JSON__', tasks_json)

