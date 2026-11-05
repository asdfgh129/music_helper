/* 第 3 步：把下载目录里的普通文件拷到工作区 */
(function (MH) {
  'use strict';

  MH.StepCopy = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['prev', 'next'],
    data: function () {
      return {
        loading: false,
        error: '',
        preview: null,
        disabled: {},
        showResult: false,
        result: null,
        showSkip: false,
      };
    },
    computed: {
      groups: function () { return (this.preview && this.preview.groups) || []; },
      workspace: function () { return (this.preview && this.preview.workspace) || { files: [] }; },
      total: function () { return (this.preview && this.preview.total) || 0; },
      bytes: function () { return (this.preview && this.preview.bytes) || 0; },
      selectedCount: function () {
        let count = 0;
        this.groups.forEach((g) => { if (!this.disabled[g.root]) count += g.count; });
        return count;
      },
      rangeLabel: function () {
        const r = this.state.range || {};
        if (r.mode === 'range') return MH.fmt.month(r.from) + ' ~ ' + MH.fmt.month(r.to);
        return MH.fmt.month(r.from);
      },
      copiedNames: function () {
        const map = {};
        const items = (this.task && this.task.items) || [];
        items.forEach((item) => { if (item.ok) map[item.name] = item.output; });
        return map;
      },
      tone: function () {
        if (!this.result) return 'info';
        const failed = (this.result.failed || []).length;
        if (!failed) return 'info';
        return this.result.copied ? 'warn' : 'err';
      },
    },
    mounted: function () { this.load(); },
    methods: {
      params: function () {
        const r = this.state.range || {};
        if (r.mode === 'range') return { month_from: r.from, month_to: r.to };
        return { month: r.from };
      },
      async load() {
        this.loading = true;
        this.error = '';
        try {
          this.preview = await MH.api.get('/api/copy/preview', this.params());
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      toggleGroup: function (root) {
        this.disabled = Object.assign({}, this.disabled, { [root]: !this.disabled[root] });
      },
      async run() {
        const paths = [];
        this.groups.forEach((group) => {
          if (this.disabled[group.root]) return;
          group.files.forEach((file) => paths.push(file.path));
        });
        this.result = null;
        const id = await this.submitTask('copy', Object.assign({ paths: paths }, this.params()));
        if (id) this.message('开始拷贝 ' + paths.length + ' 个文件…');
      },
      onTaskFinished(task) {
        this.result = task.status === 'error'
          ? { copied: 0, failed: [{ name: '任务异常', message: task.error }], total: 0 }
          : (task.result || {});
        this.showResult = true;
        if (this.result.copied) {
          this.$emit('mark', 'copy');
          this.load();
        }
      },
      closeResult() {
        this.showResult = false;
        this.load();
      },
      next() {
        if (!this.state.copyDone) {
          this.showSkip = true;
          return;
        }
        this.$emit('next');
      },
      confirmSkip() {
        this.showSkip = false;
        this.$emit('next');
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 3 步 · 拷贝文件到工作区</h2>
          <span class="sub">来源：下载目录里的普通音频（已排除 VIP 子目录） · 月份 {{ rangeLabel }}</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load" :disabled="loading || taskRunning">刷新列表</button>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>

        <div class="dual" style="margin-top:14px">
          <!-- 待移动 -->
          <div class="pane">
            <header>
              <span>待拷贝</span>
              <span class="path">按原目录分组</span>
              <span class="pill info">{{ selectedCount }} / {{ total }} 个</span>
            </header>
            <div class="body">
              <div v-if="loading" class="empty">扫描中…</div>
              <template v-else>
                <div v-for="group in groups" :key="group.root">
                  <div class="group-head" v-if="group.files.length || group.missing">
                    <input type="checkbox" :checked="!disabled[group.root]"
                           @change="toggleGroup(group.root)" :disabled="!group.files.length">
                    <span>{{ group.label }}</span>
                    <span class="path" :title="group.root">{{ group.root }}</span>
                    <span class="dim">{{ group.count }} 个 · {{ $fmt.size(group.bytes) }}</span>
                  </div>
                  <div class="row-item" v-for="file in group.files" :key="file.path">
                    <span class="name" :title="file.path">{{ file.name }}</span>
                    <span class="tag">{{ $fmt.month(file.month) }}</span>
                    <span class="meta">{{ $fmt.size(file.size) }}</span>
                    <span class="tag" v-if="copiedNames[file.name]" style="color:var(--ok)">已拷贝</span>
                    <span class="tag" v-else-if="file.existing" style="color:var(--warn)">工作区已有同名</span>
                  </div>
                  <div class="empty" v-if="group.missing" style="padding:14px">目录不存在：{{ group.root }}</div>
                </div>
                <div class="empty" v-if="!groups.length">没有可拷贝的文件（换个月份试试）</div>
              </template>
            </div>
            <footer>
              <span>{{ total }} 个文件</span>
              <span>{{ $fmt.size(bytes) }}</span>
            </footer>
          </div>

          <!-- 移动后 -->
          <div class="pane">
            <header>
              <span>工作区</span>
              <span class="path" :title="workspace.dir">{{ workspace.dir }}</span>
              <span class="pill">{{ workspace.total || 0 }} 个</span>
            </header>
            <div class="body">
              <div class="row-item" v-for="file in workspace.files" :key="file.name">
                <span class="name" :title="file.name">{{ file.name }}</span>
                <span class="tag">{{ $fmt.month(file.month) }}</span>
                <span class="meta">{{ $fmt.size(file.size) }}</span>
              </div>
              <div class="empty" v-if="!workspace.files || !workspace.files.length">工作区还是空的</div>
            </div>
            <footer>
              <span>{{ workspace.total || 0 }} 个文件</span>
              <span>{{ $fmt.size(workspace.bytes) }}</span>
              <span v-if="workspace.truncated" class="warn">列表已截断</span>
            </footer>
          </div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>拷贝进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="taskRunning">← 上一步</button>
          <span class="spacer"></span>
          <button class="btn" @click="run" :disabled="taskRunning || !selectedCount">
            <span v-if="taskRunning" class="spin"></span> {{ taskRunning ? '拷贝中…' : '拷贝' }}
          </button>
          <button class="btn primary" @click="next" :disabled="taskRunning">下一步 →</button>
        </div>

        <mh-result :show="showResult" title="拷贝完成" :tone="tone" @close="closeResult">
          <div class="stats" style="margin-bottom:12px">
            <div class="stat"><div class="n">{{ (result && result.copied) || 0 }}</div><div class="l">成功</div></div>
            <div class="stat"><div class="n" :class="(result && result.failed && result.failed.length) ? 'err' : ''">
              {{ (result && result.failed && result.failed.length) || 0 }}</div><div class="l">失败</div></div>
            <div class="stat"><div class="n">{{ (result && result.total) || 0 }}</div><div class="l">总计</div></div>
          </div>
          <div v-if="result && result.failed && result.failed.length">
            <div class="note err" style="margin-bottom:8px">以下文件没能拷贝，来源文件保持原样：</div>
            <div class="list-scroll">
              <div class="row-item" v-for="f in result.failed" :key="f.name">
                <span class="name">{{ f.name }}</span>
                <span class="meta ellipsis" style="max-width:55%">{{ f.message }}</span>
              </div>
            </div>
          </div>
          <div class="note" style="margin-top:12px">目标目录：<span class="mono">{{ (result && result.target_dir) || '' }}</span></div>
        </mh-result>

        <mh-confirm :show="showSkip" title="还没有拷贝文件" confirm-text="跳过拷贝，继续"
                    @close="showSkip = false" @confirm="confirmSkip">
          本次还没有执行拷贝。直接下一步将跳过拷贝，进入解密页面。
          <br>确认要跳过吗？
        </mh-confirm>
      </div>`,
  };
})(window.MH);
