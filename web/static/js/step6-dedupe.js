/* 第 6 步：查重（工作区 ↔ 库目录） */
(function (MH) {
  'use strict';

  MH.StepDedupe = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['prev', 'next'],
    data: function () {
      return {
        loading: false,
        error: '',
        data: null,
        selected: {},
        action: 'move',
        showResult: false,
        result: null,
        showSkipConfirm: false,
      };
    },
    computed: {
      items: function () { return (this.data && this.data.items) || []; },
      total: function () { return this.items.length; },
      duplicated: function () {
        return this.items.filter((item) => item.status === 'duplicate');
      },
      pending: function () {
        return this.items.filter((item) => item.status !== 'unique');
      },
      selectedPaths: function () {
        return Object.keys(this.selected).filter((path) => this.selected[path]);
      },
      selectedCount: function () { return this.selectedPaths.length; },
      stats: function () {
        const base = this.data || {};
        return {
          total: base.total || 0,
          unique: base.unique || 0,
          duplicate: base.duplicate || 0,
          unknown: base.unknown || 0,
          ready: base.ready_to_archive || 0,
          library: base.library_count || 0,
        };
      },
      library: function () { return (this.data && this.data.library) || ''; },
      workspace: function () { return (this.data && this.data.workspace) || ''; },
      tone: function () {
        if (!this.result) return 'info';
        return this.result.failed ? 'warn' : 'info';
      },
    },
    mounted: function () { this.load(false); },
    methods: {
      async load(refresh) {
        this.loading = true;
        this.error = '';
        try {
          const data = await MH.api.get('/api/dedupe/preview', { refresh: refresh ? 1 : '' });
          this.data = data;
          // 默认勾上「库中已有」的：这是唯一可以自动处理的一类
          const next = {};
          (data.items || []).forEach((item) => {
            if (item.status === 'duplicate') next[item.path] = true;
          });
          this.selected = next;
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      toggle: function (item) {
        if (item.status !== 'duplicate') return;   // 需人工确认的不让勾
        this.selected = Object.assign({}, this.selected, {
          [item.path]: !this.selected[item.path],
        });
      },
      selectDuplicates: function (value) {
        const next = {};
        this.duplicated.forEach((item) => { next[item.path] = value; });
        this.selected = next;
      },
      async run() {
        if (!this.selectedCount) {
          this.message('先选要处理的文件', 'err');
          return;
        }
        this.result = null;
        const id = await this.submitTask('dedupe-cross', {
          paths: this.selectedPaths,
          action: this.action,
        });
        if (id) this.message('开始处理 ' + this.selectedCount + ' 个重复文件…');
      },
      onTaskFinished(task) {
        this.result = task.status === 'error'
          ? { executed: 0, failed: 1, items: [], error: task.error }
          : (task.result || {});
        this.showResult = true;
        this.load(false);
      },
      closeResult() { this.showResult = false; },
      next() {
        if (this.pending.length) {
          this.showSkipConfirm = true;
          return;
        }
        this.$emit('next');
      },
      doNext() {
        this.showSkipConfirm = false;
        this.$emit('next');
      },
      statusClass: function (status) {
        if (status === 'duplicate') return 'err';
        if (status === 'unknown') return 'warn';
        return 'ok';
      },
      matchedTitle: function (item) {
        if (!item.matched || !item.matched.length) return '';
        return item.matched
          .map((m) => m.path + '（' + MH.fmt.size(m.size) + '）')
          .join('\n');
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 6 步 · 查重（工作区 ↔ 库目录）</h2>
          <span class="sub">库里已经有的文件不再入库，否则年份目录与声纹库都会重复</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load(true)" :disabled="loading || taskRunning">重新扫描库</button>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">工作区文件</div></div>
          <div class="stat"><div class="n">{{ stats.unique }}</div><div class="l">库中不存在</div></div>
          <div class="stat"><div class="n" :class="stats.duplicate ? 'err' : ''">{{ stats.duplicate }}</div><div class="l">库中已有</div></div>
          <div class="stat"><div class="n" :class="stats.unknown ? 'warn' : ''">{{ stats.unknown }}</div><div class="l">需人工确认</div></div>
          <div class="stat"><div class="n">{{ stats.ready }}</div><div class="l">可入库</div></div>
        </div>

        <div class="card" style="margin-top:14px;padding:12px 16px">
          <div class="toolbar">
            <div class="seg">
              <button @click="selectDuplicates(true)">选中全部重复</button>
              <button @click="selectDuplicates(false)">全不选</button>
            </div>
            <span class="divider"></span>
            <span class="lbl">处理方式</span>
            <label><input type="radio" value="move" v-model="action"> 移入重复目录</label>
            <label><input type="radio" value="trash" v-model="action"> 放进回收站</label>
            <span class="spacer"></span>
            <span class="pill info">已选 {{ selectedCount }} / {{ duplicated.length }}</span>
          </div>
          <div class="note" style="margin-top:10px">
            比对范围：<span class="mono">{{ workspace }}</span> ↔ <span class="mono">{{ library }}</span>
            （库内 {{ stats.library }} 首）。
            <b>只动工作区</b>，库目录里的那份永远不动；删除只是移到 <span class="mono">log/_trash</span>。
          </div>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>
        <div class="note warn" v-if="data && !data.library_exists" style="margin-top:12px">
          库目录不存在，无法比对。请先在第 1 步设置库目录，并在第 2 步初始化。
        </div>

        <div class="tbl-wrap" style="margin-top:14px">
          <table class="grid">
            <thead>
              <tr>
                <th style="width:34px"></th>
                <th>文件名</th>
                <th>艺术家</th>
                <th>歌名</th>
                <th class="num" style="width:64px">时长</th>
                <th class="num" style="width:78px">大小</th>
                <th style="width:96px">结论</th>
                <th>依据</th>
                <th>库中对应文件</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.path" :class="{ sel: selected[item.path] }">
                <td>
                  <input type="checkbox" :checked="!!selected[item.path]"
                         :disabled="item.status !== 'duplicate'" @change="toggle(item)">
                </td>
                <td class="fname" :title="item.path">{{ item.name }}</td>
                <td>{{ item.artist || '—' }}</td>
                <td>{{ item.title || '—' }}</td>
                <td class="num">{{ $fmt.duration(item.duration) }}</td>
                <td class="num">{{ $fmt.size(item.size) }}</td>
                <td><span :class="statusClass(item.status)" style="font-size:12px">{{ item.status_label }}</span></td>
                <td class="dim" style="font-size:12px">{{ item.reason }}</td>
                <td class="dim ellipsis" style="max-width:280px" :title="matchedTitle(item)">
                  {{ item.matched && item.matched.length ? item.matched[0].name : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
          <div class="empty" v-if="loading">扫描工作区与库目录…（首次比对大库会慢一些）</div>
          <div class="empty" v-else-if="!items.length">工作区没有文件（先做第 3、4 步）</div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>处理进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="taskRunning">← 上一步</button>
          <span class="hint">「需人工确认」多半是时长读不出来，先在第 7 步自检里看清楚再决定</span>
          <span class="spacer"></span>
          <button class="btn" @click="run" :disabled="taskRunning || !selectedCount">
            <span v-if="taskRunning" class="spin"></span>
            {{ taskRunning ? '处理中…' : (action === 'trash' ? '放进回收站' : '移入重复目录') }}
          </button>
          <button class="btn primary" @click="next" :disabled="taskRunning">下一步 →</button>
        </div>

        <mh-result :show="showResult" title="查重处理完成" :tone="tone" @close="closeResult">
          <div class="stats" style="margin-bottom:12px">
            <div class="stat"><div class="n">{{ (result && result.planned) || 0 }}</div><div class="l">计划处理</div></div>
            <div class="stat"><div class="n">{{ (result && result.executed) || 0 }}</div><div class="l">已移走</div></div>
            <div class="stat"><div class="n" :class="(result && result.failed) ? 'err' : ''">{{ (result && result.failed) || 0 }}</div><div class="l">失败</div></div>
          </div>
          <div class="note err" v-if="result && result.error">{{ result.error }}</div>
          <div class="note" v-if="result && result.moved_to">
            目标：<span class="mono">{{ result.moved_to }}</span>
          </div>
          <div class="list-scroll" v-if="result && result.items && result.items.length" style="margin-top:10px">
            <div class="row-item" v-for="item in result.items" :key="item.source">
              <span class="name" :title="item.source">{{ item.name }}</span>
              <span class="meta ellipsis" style="max-width:50%">{{ item.reason }}</span>
            </div>
          </div>
          <div class="note" style="margin-top:10px">列表已刷新，剩下的才是真正待入库的文件。</div>
        </mh-result>

        <mh-confirm :show="showSkipConfirm" title="还有文件没确认"
                    confirm-text="仍然继续" @close="showSkipConfirm = false" @confirm="doNext">
          <div class="note warn">
            还有 {{ pending.length }} 个文件没有确认：
            {{ stats.duplicate }} 个库中已有、{{ stats.unknown }} 个需人工确认。
          </div>
          <div class="note" style="margin-top:8px">
            继续下一步不会删除任何文件，但归档时这些文件会一起入库，可能造成库里重复。
          </div>
        </mh-confirm>
      </div>`,
  };
})(window.MH);
