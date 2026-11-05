/* music_helper 前端公共部分：API 封装、格式化、任务轮询、共享组件 */

/* eslint-disable no-undef */
window.MH = window.MH || {};
(function (MH) {
  'use strict';

  const { ref } = Vue;

  /* ------------------------------------------------------------------ */
  /* API                                                                 */
  /* ------------------------------------------------------------------ */

  async function request(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body !== undefined && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    let response;
    try {
      response = await fetch(path, opts);
    } catch (err) {
      throw new Error('无法连接后端服务：' + err.message);
    }
    let data = null;
    const text = await response.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = { detail: text }; }
    }
    if (!response.ok) {
      const detail = (data && (data.detail || data.problems)) || response.statusText;
      const message = Array.isArray(detail) ? detail.join('；') : String(detail);
      const error = new Error(message || ('HTTP ' + response.status));
      error.payload = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function query(params) {
    const search = new URLSearchParams();
    Object.keys(params || {}).forEach(function (key) {
      const value = params[key];
      if (value === undefined || value === null || value === '') return;
      search.set(key, value);
    });
    const text = search.toString();
    return text ? '?' + text : '';
  }

  const api = {
    get: function (path, params) { return request(path + query(params)); },
    post: function (path, body) { return request(path, { method: 'POST', body: body || {} }); },
  };

  /* ------------------------------------------------------------------ */
  /* 格式化                                                             */
  /* ------------------------------------------------------------------ */

  function fmtSize(bytes) {
    const value = Number(bytes || 0);
    if (!value) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let index = 0;
    let size = value;
    while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
    return (size >= 100 || index === 0 ? size.toFixed(0) : size.toFixed(1)) + ' ' + units[index];
  }

  function fmtMonth(value) {
    if (!value || value.length !== 6) return value || '—';
    return value.slice(0, 4) + '-' + value.slice(4);
  }

  function fmtDuration(seconds) {
    const total = Math.round(Number(seconds || 0));
    if (!total) return '—';
    const m = Math.floor(total / 60);
    const s = total % 60;
    return m + ':' + String(s).padStart(2, '0');
  }

  function baseName(path) {
    if (!path) return '';
    const parts = String(path).split(/[\\/]/);
    return parts[parts.length - 1] || path;
  }

  MH.api = api;
  MH.fmt = { size: fmtSize, month: fmtMonth, duration: fmtDuration, baseName: baseName };

  /* ------------------------------------------------------------------ */
  /* 任务轮询 mixin                                                     */
  /* ------------------------------------------------------------------ */

  MH.taskMixin = {
    data: function () {
      return { task: null, taskError: '', timer: null, lastPayload: null };
    },
    computed: {
      taskRunning: function () {
        return !!(this.task && (this.task.status === 'running' || this.task.status === 'queued'));
      },
      taskDone: function () {
        return !!(this.task && (this.task.status === 'done' || this.task.status === 'error'));
      },
    },
    beforeUnmount: function () { this.stopPolling(); },
    methods: {
      async submitTask(kind, opts) {
        this.stopPolling();
        this.taskError = '';
        try {
          const res = await MH.api.post('/api/tasks', { kind: kind, opts: opts || {} });
          this.task = {
            id: res.task_id, label: res.label, kind: res.kind,
            status: 'queued', stage: '排队中', progress: 0,
            done: 0, total: 0, current: '', logs: [], items: [], result: null,
          };
          this.pollTask();
          return res.task_id;
        } catch (err) {
          this.taskError = err.message;
          this.message(err.message, 'err');
          return null;
        }
      },
      pollTask() {
        const id = this.task && this.task.id;
        if (!id) return;
        this.timer = setTimeout(async () => {
          try {
            const data = await MH.api.get('/api/tasks/' + id);
            this.task = data;
            if (data.status === 'queued' || data.status === 'running') {
              this.pollTask();
            } else {
              this.onTaskFinished(data);
            }
          } catch (err) {
            this.taskError = err.message;
          }
        }, 450);
      },
      stopPolling() {
        if (this.timer) { clearTimeout(this.timer); this.timer = null; }
      },
      /* 子页面覆盖：任务结束后的处理（弹结果、刷新列表等） */
      onTaskFinished() {},
    },
  };

  /* ------------------------------------------------------------------ */
  /* 共享组件                                                           */
  /* ------------------------------------------------------------------ */

  /* 任务进度面板 */
  MH.TaskPanel = {
    props: { task: Object, error: String },
    template: `
      <div class="taskbar" v-if="task || error">
        <div v-if="error" class="note err">{{ error }}</div>
        <template v-if="task">
          <div class="task-line">
            <span class="stage">{{ task.label || '' }} · {{ task.stage }}</span>
            <span class="pill" :class="statusClass">{{ statusText }}</span>
            <span class="cur">{{ task.current }}</span>
            <span class="mono dim" v-if="task.total">{{ task.done }} / {{ task.total }}</span>
          </div>
          <div class="progress"><i :style="{ width: (task.progress || 0) + '%' }"></i></div>
        </template>
        <details v-if="task && task.logs && task.logs.length">
          <summary class="dim" style="cursor:pointer;font-size:12px">运行日志（{{ task.logs.length }} 行）</summary>
          <div class="logs" ref="logs">
            <div v-for="(line, i) in task.logs" :key="i" :class="'lvl-' + line.level">{{ line.msg }}</div>
          </div>
        </details>
      </div>`,
    computed: {
      statusText: function () {
        const map = { queued: '排队中', running: '执行中', done: '已完成', error: '失败' };
        return map[this.task.status] || this.task.status;
      },
      statusClass: function () {
        return { done: 'ok', error: 'err', running: 'info', queued: '' }[this.task.status] || '';
      },
    },
    watch: {
      'task.logs': {
        handler: function () {
          this.$nextTick(() => {
            const el = this.$refs.logs;
            if (el) el.scrollTop = el.scrollHeight;
          });
        },
        deep: true,
      },
    },
  };

  /* 结果弹窗 */
  MH.ResultDialog = {
    props: { show: Boolean, title: String, tone: { type: String, default: 'info' } },
    emits: ['close'],
    template: `
      <div class="mask" v-if="show" @click.self="$emit('close')">
        <div class="dialog" style="width:min(560px,100%)">
          <header>
            <h3>{{ title }}</h3>
            <span class="pill" :class="tone">{{ tone === 'err' ? '失败' : (tone === 'warn' ? '有异常' : '完成') }}</span>
          </header>
          <div class="body"><slot></slot></div>
          <footer><button class="btn primary" @click="$emit('close')">知道了</button></footer>
        </div>
      </div>`,
  };

  /* 通用确认弹窗 */
  MH.ConfirmDialog = {
    props: { show: Boolean, title: String, confirmText: { type: String, default: '确认' } },
    emits: ['close', 'confirm'],
    template: `
      <div class="mask" v-if="show" @click.self="$emit('close')">
        <div class="dialog" style="width:min(520px,100%)">
          <header><h3>{{ title }}</h3></header>
          <div class="body"><slot></slot></div>
          <footer>
            <button class="btn ghost" @click="$emit('close')">取消</button>
            <button class="btn primary" @click="$emit('confirm')">{{ confirmText }}</button>
          </footer>
        </div>
      </div>`,
  };

  /* 目录选择器 */
  MH.DirPicker = {
    props: { show: Boolean, start: String },
    emits: ['close', 'pick'],
    data: function () { return { data: null, loading: false, error: '', manual: '' }; },
    watch: {
      show: function (value) { if (value) this.open(this.start || ''); },
    },
    methods: {
      async open(path) {
        this.loading = true;
        this.error = '';
        try {
          this.data = await MH.api.get('/api/fs/list', { path: path || '' });
          this.manual = this.data.path || '';
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      go(path) { this.open(path); },
      up() { if (this.data && this.data.parent) this.open(this.data.parent); },
      pick() { if (this.data && this.data.path) this.$emit('pick', this.data.path); },
      async mkdir() {
        const name = window.prompt('新建目录名');
        if (!name || !this.data || !this.data.path) return;
        const target = this.data.path.replace(/[\\/]+$/, '') + '\\' + name;
        try {
          const res = await MH.api.post('/api/fs/mkdir', { path: target });
          this.open(res.path);
        } catch (err) { this.error = err.message; }
      },
    },
    template: `
      <div class="mask" v-if="show" @click.self="$emit('close')">
        <div class="dialog">
          <header>
            <h3>选择目录</h3>
            <button class="btn sm" @click="up" :disabled="!data || !data.parent">上一级</button>
            <button class="btn sm" @click="mkdir" :disabled="!data || !data.path">新建</button>
          </header>
          <div class="body">
            <div class="note" v-if="error">{{ error }}</div>
            <div class="dir-state" style="margin-bottom:8px">
              <span class="mono">{{ data ? data.path : '（选择盘符）' }}</span>
            </div>
            <div class="dir-state" style="margin-bottom:10px;flex-wrap:wrap" v-if="data && data.shortcuts.length">
              <span>快捷：</span>
              <button class="btn link" v-for="s in data.shortcuts" :key="s.path" @click="go(s.path)">{{ s.label }}</button>
            </div>
            <div class="list-scroll" style="max-height:44vh">
              <div v-if="data">
                <div class="row-item" v-for="d in data.dirs" :key="d.path" @click="go(d.path)" style="cursor:pointer">
                  <span class="name">📁 {{ d.name }}</span>
                </div>
                <div v-if="!data.dirs.length" class="empty">没有子目录</div>
              </div>
              <div v-else class="empty">加载中…</div>
            </div>
            <div v-if="data && data.drives.length" style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn sm" v-for="d in data.drives" :key="d.path" @click="go(d.path)">{{ d.name }}</button>
            </div>
          </div>
          <footer>
            <button class="btn ghost" @click="$emit('close')">取消</button>
            <button class="btn primary" @click="pick" :disabled="!data || !data.path">选择这个目录</button>
          </footer>
        </div>
      </div>`,
  };
})(window.MH);
