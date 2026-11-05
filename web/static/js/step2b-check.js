/* 第 2b 步：库目录自检（做完回到第 2 步） */
(function (MH) {
  'use strict';

  MH.StepCheck = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['back', 'done'],
    data: function () {
      return { fix: false, showResult: false, result: null, reports: [] };
    },
    computed: {
      library: function () { return this.state.library || {}; },
      summary: function () {
        return (this.result && this.result.summary) || [];
      },
      tone: function () {
        if (!this.result) return 'info';
        const text = JSON.stringify(this.result);
        return /失败|异常/.test(text) ? 'warn' : 'info';
      },
    },
    mounted: function () { this.loadReports(); },
    methods: {
      async loadReports() {
        try {
          const data = await MH.api.get('/api/reports');
          this.reports = (data.reports || []).slice(0, 5);
        } catch (err) { /* 报告列表拿不到不影响自检 */ }
      },
      async start() {
        this.result = null;
        const id = await this.submitTask('check', {
          fix: this.fix, dry_run: false, report_dir: null,
        });
        if (id) this.message('开始自检，大库可能需要几分钟…');
      },
      onTaskFinished(task) {
        this.result = task.status === 'error'
          ? { summary: [], error: task.error }
          : (task.result || {});
        this.showResult = true;
        this.loadReports();
      },
      closeResult() {
        this.showResult = false;
        this.$emit('done');
      },
      pretty: function (value) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>库目录自检</h2>
          <span class="sub">检查文件名 / 标签 / 重复 / 歌词，只出报告不动文件（勾选修复才会动）</span>
          <span class="spacer"></span>
          <span class="pill mono">{{ library.dir }}</span>
        </div>

        <div class="card" style="margin-top:14px">
          <h3>自检范围</h3>
          <div class="kv">
            <dt>目标目录</dt><dd>{{ library.dir }}</dd>
            <dt>音频文件</dt><dd>{{ library.audio_count }}{{ library.count_truncated ? '（统计上限）' : '' }}</dd>
            <dt>检查项</dt><dd>文件名格式 / 标签完整性 / 文件名与标签一致性 / 重复 / 歌词</dd>
          </div>
          <div class="checks" style="margin-top:14px">
            <label>
              <input type="checkbox" v-model="fix" :disabled="taskRunning">
              顺便执行可自动修复项（文件名规范化、严重缺失移入待确认目录、重复移入重复目录）
            </label>
          </div>
          <div class="note warn" style="margin-top:10px" v-if="fix">
            勾选后会产生真实文件移动，全部经 journal 记录，删除只会移入回收站。
          </div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>执行进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="card" style="margin-top:16px" v-if="reports.length">
          <h3>最近报告 <span class="badge">log/reports</span></h3>
          <div class="row-item" v-for="r in reports" :key="r.name">
            <span class="name mono">{{ r.name }}</span>
            <span class="meta">{{ r.mtime_str }}</span>
          </div>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('back')" :disabled="taskRunning">← 上一步</button>
          <span class="spacer"></span>
          <button class="btn primary" @click="start" :disabled="taskRunning || !library.initialized">
            <span v-if="taskRunning" class="spin"></span> {{ taskRunning ? '正在自检…' : '开始自检' }}
          </button>
        </div>

        <mh-result :show="showResult" title="自检完成" :tone="tone" @close="closeResult">
          <div class="note err" v-if="result && result.error">{{ result.error }}</div>
          <div class="kv" v-else-if="summary.length">
            <template v-for="(pair, i) in summary" :key="i">
              <dt>{{ pair[0] }}</dt><dd>{{ pretty(pair[1]) }}</dd>
            </template>
          </div>
          <div class="empty" v-else>没有汇总数据，详情见 log/reports 下的报告。</div>
          <div class="note" style="margin-top:12px">确认后返回第 2 步。</div>
        </mh-result>
      </div>`,
  };
})(window.MH);
