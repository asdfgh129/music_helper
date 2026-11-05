/* 第 2a 步：初始化库目录（做完回到第 2 步） */
(function (MH) {
  'use strict';

  MH.StepInit = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['back', 'done'],
    data: function () {
      return { makeDb: true, showResult: false, result: null };
    },
    computed: {
      library: function () { return this.state.library || {}; },
      actions: function () { return this.library.actions || []; },
      tone: function () {
        if (!this.result) return 'info';
        return this.result.ok ? 'info' : 'warn';
      },
    },
    methods: {
      async start() {
        this.result = null;
        const id = await this.submitTask('init', { make_db: this.makeDb });
        if (id) this.message('开始初始化…');
      },
      onTaskFinished(task) {
        if (task.status === 'error') {
          this.result = { ok: false, steps: [], error: task.error };
        } else {
          this.result = task.result || { ok: true, steps: [] };
        }
        this.showResult = true;
        this.$emit('refresh');
      },
      closeResult() {
        this.showResult = false;
        if (this.result && this.result.ok) this.$emit('done');
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>初始化库目录</h2>
          <span class="sub">建目录 + 建声纹库，幂等：已存在就跳过，不动任何音频文件</span>
          <span class="spacer"></span>
          <span class="pill" :class="library.initialized ? 'ok' : 'warn'">
            {{ library.initialized ? '当前已初始化' : '当前未初始化' }}
          </span>
        </div>

        <div class="card" style="margin-top:14px">
          <h3>将要执行 <span class="badge">{{ actions.length }} 项</span></h3>
          <div class="row-item" v-for="a in actions" :key="a.key">
            <span class="name">{{ a.label }}</span>
            <span class="meta ellipsis" style="max-width:60%">{{ a.detail }}</span>
          </div>
          <div class="empty" v-if="!actions.length">库看起来已经就绪，可以直接开始处理。</div>

          <div class="checks" style="margin-top:14px">
            <label><input type="checkbox" v-model="makeDb" :disabled="taskRunning"> 同时建立/刷新声纹库（首次较慢，需扫描整个库）</label>
          </div>
          <div class="note" style="margin-top:10px" v-if="library.tool && !library.tool.soundalike_ok">
            声纹工具不可用：{{ library.tool.soundalike_problem }}。可以先跳过建库，后续在命令行执行
            <span class="mono">python main.py --init</span>。
          </div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>执行进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('back')" :disabled="taskRunning">← 上一步</button>
          <span class="spacer"></span>
          <button class="btn primary" @click="start" :disabled="taskRunning">
            <span v-if="taskRunning" class="spin"></span> {{ taskRunning ? '正在执行…' : '开始初始化' }}
          </button>
        </div>

        <mh-result :show="showResult" :title="result && result.ok ? '初始化完成' : '初始化未全部成功'"
                   :tone="tone" @close="closeResult">
          <div class="row-item" v-for="(s, i) in (result && result.steps) || []" :key="i">
            <span class="pill" :class="s.ok ? 'ok' : 'err'">{{ s.ok ? 'OK' : '失败' }}</span>
            <span class="name">{{ s.label }}</span>
            <span class="meta ellipsis" style="max-width:55%">{{ s.detail }}</span>
          </div>
          <div class="note err" v-if="result && result.error" style="margin-top:10px">{{ result.error }}</div>
          <div class="note" style="margin-top:12px">确认后返回第 2 步。</div>
        </mh-result>
      </div>`,
  };
})(window.MH);
