/* 根组件：步骤状态机 + 步骤条 + 全局提示 */
(function (MH) {
  'use strict';

  const STEPS = [
    { key: 'dirs', num: 1, label: '目录设置', view: 'dirs' },
    { key: 'actions', num: 2, label: '操作类型', view: 'actions' },
    { key: 'copy', num: 3, label: '拷贝', view: 'copy' },
    { key: 'decrypt', num: 4, label: '解密', view: 'decrypt' },
    { key: 'tags', num: 5, label: '标签歌词', view: 'tags' },
    { key: 'archive', num: 6, label: '归档', view: 'archive' },
  ];

  const VIEW_COMPONENT = {
    dirs: 'step-dirs',
    actions: 'step-actions',
    init: 'step-init',
    check: 'step-check',
    copy: 'step-copy',
    decrypt: 'step-decrypt',
    tags: 'step-tags',
    archive: 'step-archive',
  };

  MH.root = {
    data: function () {
      return {
        loading: true,
        error: '',
        view: 'dirs',
        maxStep: 1,
        dirs: { items: [], fields: [] },
        library: {},
        months: [],
        month: '',
        range: { mode: 'single', from: '', to: '' },
        copyDone: false,
        decryptDone: false,
        version: '',
        iniPath: '',
        busy: false,
        toast: '',
        toastTone: '',
        toastTimer: null,
      };
    },
    computed: {
      steps: function () { return STEPS; },
      activeStepNum: function () {
        if (this.view === 'init' || this.view === 'check') return 2;
        const found = STEPS.find((step) => step.view === this.view);
        return found ? found.num : 1;
      },
      componentName: function () { return VIEW_COMPONENT[this.view] || 'step-dirs'; },
      state: function () {
        return {
          dirs: this.dirs,
          library: this.library,
          months: this.months,
          month: this.month,
          range: this.range,
          copyDone: this.copyDone,
          decryptDone: this.decryptDone,
          iniPath: this.iniPath,
        };
      },
    },
    mounted: function () {
      this._toastHandler = (event) => {
        const detail = event.detail || {};
        this.toast = detail.text || '';
        this.toastTone = detail.tone || '';
        clearTimeout(this.toastTimer);
        this.toastTimer = setTimeout(() => { this.toast = ''; }, 3200);
      };
      window.addEventListener('mh-toast', this._toastHandler);
      this.loadState();
    },
    beforeUnmount: function () {
      window.removeEventListener('mh-toast', this._toastHandler);
    },
    methods: {
      /* 子组件通过全局 mixin 的 message() 发事件，这里只负责显示 */
      async loadState(silent) {
        if (!silent) this.loading = true;
        this.error = '';
        try {
          const data = await MH.api.get('/api/wizard/state');
          this.dirs = data.dirs || { items: [], fields: [] };
          this.library = data.library || {};
          this.months = data.months || [];
          this.month = data.month || (this.months[0] || '');
          this.version = data.version || '';
          this.iniPath = data.ini_path || '';
          this.busy = !!data.busy;
          if (!this.range.from) {
            this.range = { mode: 'single', from: this.month, to: this.month };
          }
          if (!silent && data.problems && data.problems.length) {
            this.message('配置提示：' + data.problems.join('；'), 'err');
          }
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      /* 子页面里的「刷新状态」：静默刷新，避免把正在显示的弹窗/进度一起卸载 */
      onRefresh: function () { this.loadState(true); },
      goStep: function (step) {
        if (step.num > this.maxStep) return;
        this.view = step.view;
      },
      onNext: function () {
        // 每个页面的「下一步」目标不同，按当前视图决定，避免同名事件互相串台
        const forward = {
          dirs: { view: 'actions', step: 2 },
          copy: { view: 'decrypt', step: 4 },
          decrypt: { view: 'tags', step: 5 },
          tags: { view: 'archive', step: 6 },
        };
        const target = forward[this.view];
        if (!target) return;
        this.maxStep = Math.max(this.maxStep, target.step);
        this.view = target.view;
      },
      onPrev: function () {
        const order = ['dirs', 'actions', 'copy', 'decrypt', 'tags', 'archive'];
        const index = order.indexOf(this.view);
        this.view = index > 0 ? order[index - 1] : 'dirs';
      },
      onGo: function (payload) {
        if (payload && payload.range) this.range = payload.range;
        if (!payload || !payload.mode) return;
        if (payload.mode === 'init') { this.view = 'init'; return; }
        if (payload.mode === 'check') { this.view = 'check'; return; }
        this.maxStep = Math.max(this.maxStep, 3);
        this.view = 'copy';
      },
      onBack: function () {
        this.view = 'actions';
        this.loadState();
      },
      onDone: function () {
        this.view = 'actions';
        this.loadState();
      },
      onSaved: function (res) {
        this.dirs = (res && res.dirs) || this.dirs;
        if (res && res.library) this.library = res.library;
      },
      onMark: function (which) {
        if (which === 'copy') this.copyDone = true;
        if (which === 'decrypt') this.decryptDone = true;
      },
      onFinish: function () {
        this.message('这一轮流程走完了，可以回到第 2 步再处理下一批');
        this.view = 'actions';
        this.loadState();
      },
    },
    template: `
      <div class="shell">
        <header class="topbar">
          <div class="brand">
            <h1>music_helper</h1>
            <span class="ver">v{{ version }}</span>
          </div>

          <nav class="stepper">
            <template v-for="(step, i) in steps" :key="step.key">
              <span class="sep" v-if="i"></span>
              <button class="node"
                      :class="{ active: activeStepNum === step.num, done: step.num < activeStepNum }"
                      :disabled="step.num > maxStep"
                      @click="goStep(step)">
                <span class="num">{{ step.num }}</span>{{ step.label }}
              </button>
            </template>
          </nav>

          <div class="actions">
            <span class="pill warn" v-if="busy">有任务在跑</span>
            <a class="btn ghost" href="/legacy" target="_blank" rel="noopener">旧版面板</a>
            <button class="btn sm" @click="loadState" :disabled="loading">刷新</button>
          </div>
        </header>

        <main class="main">
          <div class="empty" v-if="loading">读取配置中…</div>
          <div class="note err" v-else-if="error">
            {{ error }} —— 确认后端已启动：<span class="mono">python -m uvicorn web.api:app --port 8000</span>
          </div>
          <component v-else
                     :is="componentName"
                     :state="state"
                     @next="onNext"
                     @prev="onPrev"
                     @go="onGo"
                     @back="onBack"
                     @done="onDone"
                     @saved="onSaved"
                     @mark="onMark"
                     @finish="onFinish"
                     @refresh="onRefresh"></component>
        </main>

        <div class="toast" :class="toastTone" v-if="toast">{{ toast }}</div>
      </div>`,
  };

  /* ------------------------------------------------------------------ */

  const app = Vue.createApp(MH.root);

  /* 全局 message()：任何子页面都能弹一条提示，由根组件统一显示 */
  app.mixin({
    methods: {
      message: function (text, tone) {
        if (!text) return;
        window.dispatchEvent(new CustomEvent('mh-toast', {
          detail: { text: String(text), tone: tone || '' },
        }));
      },
    },
  });

  app.component('mh-task-panel', MH.TaskPanel);
  app.component('mh-result', MH.ResultDialog);
  app.component('mh-confirm', MH.ConfirmDialog);
  app.component('mh-dir-picker', MH.DirPicker);
  app.component('step-dirs', MH.StepDirs);
  app.component('step-actions', MH.StepActions);
  app.component('step-init', MH.StepInit);
  app.component('step-check', MH.StepCheck);
  app.component('step-copy', MH.StepCopy);
  app.component('step-decrypt', MH.StepDecrypt);
  app.component('step-tags', MH.StepTags);
  app.component('step-archive', MH.StepArchive);

  app.config.globalProperties.$fmt = MH.fmt;

  app.mount('#app');
})(window.MH);
