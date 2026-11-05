/* 第 8 步：按年份归档 */
(function (MH) {
  'use strict';

  MH.StepArchive = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['prev', 'finish'],
    data: function () {
      return {
        loading: false,
        error: '',
        intoLibrary: true,
        moveIncomplete: true,
        preview: null,
        showResult: false,
        result: null,
      };
    },
    computed: {
      groups: function () { return (this.preview && this.preview.groups) || []; },
      incomplete: function () { return (this.preview && this.preview.incomplete) || []; },
      total: function () { return (this.preview && this.preview.total) || 0; },
      bytes: function () { return (this.preview && this.preview.bytes) || 0; },
      baseDir: function () { return (this.preview && this.preview.base_dir) || ''; },
      tone: function () {
        if (!this.result) return 'info';
        if (this.result.failed) return 'warn';
        return 'info';
      },
    },
    watch: {
      intoLibrary: function () { this.load(); },
    },
    mounted: function () { this.load(); },
    methods: {
      async load() {
        this.loading = true;
        this.error = '';
        try {
          this.preview = await MH.api.get('/api/archive/preview', { into_library: this.intoLibrary });
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      async run() {
        this.result = null;
        const id = await this.submitTask('archive', {
          into_library: this.intoLibrary,
          move_incomplete: this.moveIncomplete,
        });
        if (id) this.message('开始归档…');
      },
      onTaskFinished(task) {
        this.result = task.status === 'error'
          ? { executed: 0, unknown: 0, items: [], error: task.error }
          : (task.result || {});
        this.showResult = true;
        this.load();
      },
      closeResult() { this.showResult = false; },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 8 步 · 按年份归档</h2>
          <span class="sub">按 &lt;年代&gt;/&lt;年份&gt; 两级目录整理，例如 1980-1989/1985/</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load" :disabled="loading || taskRunning">刷新</button>
        </div>

        <div class="card" style="margin-top:14px">
          <h3>归档到哪里</h3>
          <div class="note" v-if="intoLibrary" style="margin-bottom:10px">
            入库前应已完成第 6 步查重与第 7 步自检；这里只负责按年份落位，
            未达入库标准的文件会移入待确认目录。
          </div>
          <div class="option" :class="{ active: intoLibrary }" @click="intoLibrary = true">
            <div class="mark">{{ intoLibrary ? '✓' : '' }}</div>
            <div class="body">
              <div class="t">直接入库（推荐）</div>
              <div class="d">工作区 → <span class="mono">{{ state.dirs.items.length ? (state.dirs.items.find(i => i.key === 'library_dir') || {}).value : '' }}</span>，归档即入库。</div>
            </div>
          </div>
          <div class="option" :class="{ active: !intoLibrary }" @click="intoLibrary = false">
            <div class="mark">{{ !intoLibrary ? '✓' : '' }}</div>
            <div class="body">
              <div class="t">只在工作区整理</div>
              <div class="d">工作区内建立 <span class="mono">&lt;年代&gt;/&lt;年份&gt;</span> 结构，先不入库，方便再核对一遍。</div>
            </div>
          </div>
          <div class="checks" style="margin-top:12px">
            <label><input type="checkbox" v-model="moveIncomplete" :disabled="taskRunning">
              把不可归档的文件移入待确认目录（缺年份 / 缺歌手 / 文件名与标签矛盾）
            </label>
          </div>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ total }}</div><div class="l">待归档文件</div></div>
          <div class="stat"><div class="n">{{ groups.length }}</div><div class="l">年份分组</div></div>
          <div class="stat"><div class="n" :class="incomplete.length ? 'warn' : ''">{{ incomplete.length }}</div><div class="l">无法归档</div></div>
          <div class="stat"><div class="n">{{ $fmt.size(bytes) }}</div><div class="l">合计大小</div></div>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>
        <div class="note" style="margin-top:12px">目标根目录：<span class="mono">{{ baseDir }}</span></div>

        <div class="card" style="margin-top:16px">
          <h3>归档计划</h3>
          <div class="row-item" v-for="g in groups" :key="g.decade + g.year">
            <span class="name mono">{{ g.decade }} / {{ g.year }}</span>
            <span class="meta">{{ g.count }} 个 · {{ $fmt.size(g.bytes) }}</span>
          </div>
          <div class="empty" v-if="!groups.length">工作区没有可归档的文件</div>

          <template v-if="incomplete.length">
            <h3 style="margin-top:16px">无法归档 <span class="badge">{{ incomplete.length }}</span></h3>
            <div class="list-scroll">
              <div class="row-item" v-for="item in incomplete" :key="item.path">
                <span class="name" :title="item.path">{{ item.name }}</span>
                <span class="meta ellipsis" style="max-width:55%">{{ (item.problems || []).join('；') }}</span>
              </div>
            </div>
          </template>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>归档进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="taskRunning">← 上一步</button>
          <span class="spacer"></span>
          <button class="btn" @click="run" :disabled="taskRunning || (!total && !incomplete.length)">
            <span v-if="taskRunning" class="spin"></span> {{ taskRunning ? '归档中…' : '归档' }}
          </button>
          <button class="btn primary" @click="$emit('finish')" :disabled="taskRunning">完成</button>
        </div>

        <mh-result :show="showResult" title="归档完成" :tone="tone" @close="closeResult">
          <div class="stats" style="margin-bottom:12px">
            <div class="stat"><div class="n">{{ (result && result.executed) || 0 }}</div><div class="l">已移动</div></div>
            <div class="stat"><div class="n" :class="(result && result.failed) ? 'err' : ''">{{ (result && result.failed) || 0 }}</div><div class="l">失败</div></div>
            <div class="stat"><div class="n">{{ (result && result.unknown) || 0 }}</div><div class="l">转待确认</div></div>
          </div>
          <div class="note err" v-if="result && result.error">{{ result.error }}</div>
          <div class="note" style="margin-top:8px">
            {{ (result && result.summary) || '' }} · 目标：<span class="mono">{{ (result && result.base_dir) || '' }}</span>
          </div>
          <div class="note" style="margin-top:8px">
            所有移动都记在 <span class="mono">log/journal.jsonl</span>，可以据此回溯或还原。
          </div>
        </mh-result>
      </div>`,
  };
})(window.MH);
