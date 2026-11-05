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
        showUpgradeConfirm: false,
      };
    },
    computed: {
      items: function () { return (this.data && this.data.items) || []; },
      total: function () { return this.items.length; },
      duplicated: function () {
        return this.items.filter((item) => item.status === 'duplicate');
      },
      upgradable: function () {
        return this.items.filter((item) => item.status === 'upgrade');
      },
      handleable: function () {
        return this.items.filter((item) =>
          item.status === 'duplicate' || item.status === 'upgrade');
      },
      pending: function () {
        return this.items.filter((item) => item.status !== 'unique');
      },
      selectedPaths: function () {
        return Object.keys(this.selected).filter((path) => this.selected[path]);
      },
      selectedCount: function () { return this.selectedPaths.length; },
      selectedItems: function () {
        const map = {};
        this.items.forEach((item) => { map[item.path] = item; });
        return this.selectedPaths.map((path) => map[path]).filter(Boolean);
      },
      selectedUpgrades: function () {
        return this.selectedItems.filter((item) => item.status === 'upgrade');
      },
      selectedDuplicates: function () {
        return this.selectedItems.filter((item) => item.status === 'duplicate');
      },
      // 选中项里会被移出库目录的文件总数（upgrade 才会产生）
      replaceCount: function () {
        let count = 0;
        this.selectedUpgrades.forEach((item) => {
          count += (item.replace || []).length;
        });
        return count;
      },
      stats: function () {
        const base = this.data || {};
        return {
          total: base.total || 0,
          unique: base.unique || 0,
          duplicate: base.duplicate || 0,
          upgrade: base.upgrade || 0,
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
      canRun: function () {
        return !this.taskRunning && this.selectedCount > 0;
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
          // 默认勾上两类可自动处理的：重复的移走，音质更低的替换
          const next = {};
          (data.items || []).forEach((item) => {
            if (item.status === 'duplicate' || item.status === 'upgrade') {
              next[item.path] = true;
            }
          });
          this.selected = next;
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      selectable: function (item) {
        return item.status === 'duplicate' || item.status === 'upgrade';
      },
      toggle: function (item) {
        if (!this.selectable(item)) return;
        this.selected = Object.assign({}, this.selected, {
          [item.path]: !this.selected[item.path],
        });
      },
      selectAll: function (value) {
        const next = {};
        this.handleable.forEach((item) => { next[item.path] = value; });
        this.selected = next;
      },
      selectOnly: function (status) {
        const next = {};
        this.items.forEach((item) => { next[item.path] = item.status === status; });
        this.selected = next;
      },
      async run() {
        if (!this.selectedCount) {
          this.message('先选要处理的文件', 'err');
          return;
        }
        // 动库目录属于不可轻视的操作，单独确认一次
        if (this.replaceCount > 0) {
          this.showUpgradeConfirm = true;
          return;
        }
        this.submit();
      },
      async submit() {
        this.showUpgradeConfirm = false;
        const statuses = [];
        this.selectedItems.forEach((item) => {
          if (statuses.indexOf(item.status) < 0) statuses.push(item.status);
        });
        this.result = null;
        const id = await this.submitTask('dedupe-cross', {
          paths: this.selectedPaths,
          action: this.action,
          statuses: statuses,
        });
        if (id) {
          const extra = this.replaceCount
            ? '，其中 ' + this.replaceCount + ' 个库内旧版本会让位'
            : '';
          this.message('开始处理 ' + this.selectedCount + ' 项' + extra + '…');
        }
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
        if (status === 'upgrade') return 'warn';
        if (status === 'unknown') return 'warn';
        return 'ok';
      },
      matchedTitle: function (item) {
        if (!item.matched || !item.matched.length) return '';
        return item.matched
          .map((m) => m.path + '\n    ' + MH.fmt.size(m.size) +
            (m.quality ? ' · ' + m.quality : ''))
          .join('\n');
      },
      replaceTitle: function (item) {
        const list = item.replace || [];
        if (!list.length) return '';
        return '将被移出库目录：\n' + list.map((m) => m.path).join('\n');
      },
      sideLabel: function (side) {
        return side === 'library' ? '库' : '工作区';
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 6 步 · 查重（工作区 ↔ 库目录）</h2>
          <span class="sub">库里已经有的不再入库；库里音质更低时，由工作区这份替换掉它</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load(true)" :disabled="loading || taskRunning">重新扫描库</button>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">工作区文件</div></div>
          <div class="stat"><div class="n">{{ stats.unique }}</div><div class="l">库中不存在</div></div>
          <div class="stat"><div class="n" :class="stats.duplicate ? 'err' : ''">{{ stats.duplicate }}</div><div class="l">库中已有</div></div>
          <div class="stat"><div class="n" :class="stats.upgrade ? 'warn' : ''">{{ stats.upgrade }}</div><div class="l">音质可升级</div></div>
          <div class="stat"><div class="n" :class="stats.unknown ? 'warn' : ''">{{ stats.unknown }}</div><div class="l">需人工确认</div></div>
          <div class="stat"><div class="n">{{ stats.ready }}</div><div class="l">可入库</div></div>
        </div>

        <div class="card" style="margin-top:14px;padding:12px 16px">
          <div class="toolbar">
            <div class="seg">
              <button @click="selectAll(true)">选中可处理</button>
              <button @click="selectOnly('duplicate')" v-if="stats.duplicate">仅库中已有</button>
              <button @click="selectOnly('upgrade')" v-if="stats.upgrade">仅音质升级</button>
              <button @click="selectAll(false)">全不选</button>
            </div>
            <span class="divider"></span>
            <span class="lbl">工作区那份</span>
            <label><input type="radio" value="move" v-model="action"> 移入重复目录</label>
            <label><input type="radio" value="trash" v-model="action"> 放进回收站</label>
            <span class="spacer"></span>
            <span class="pill info">已选 {{ selectedCount }} / {{ handleable.length }}</span>
          </div>
          <div class="note" style="margin-top:10px">
            比对范围：<span class="mono">{{ workspace }}</span> ↔ <span class="mono">{{ library }}</span>
            （库内 {{ stats.library }} 首）。
          </div>
          <div class="note warn" style="margin-top:8px" v-if="replaceCount">
            <b>{{ selectedUpgrades.length }}</b> 项音质更低，会移走库目录里对应的
            <b>{{ replaceCount }}</b> 个旧版本（移入重复目录，不会直接删除）；
            工作区这份保留，留给第 8 步归档。取消勾选即可跳过其中某一项。
          </div>
          <div class="note" style="margin-top:8px" v-else>
            「库中已有」只移走工作区这份，库目录不动。删除一律只是移到
            <span class="mono">log/_trash</span>。
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
                <th style="width:132px">音质</th>
                <th style="width:104px">结论</th>
                <th>依据</th>
                <th>库中对应文件</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.path" :class="{ sel: selected[item.path] }">
                <td>
                  <input type="checkbox" :checked="!!selected[item.path]"
                         :disabled="!selectable(item)" @change="toggle(item)">
                </td>
                <td class="fname" :title="item.path">{{ item.name }}</td>
                <td>{{ item.artist || '—' }}</td>
                <td>{{ item.title || '—' }}</td>
                <td class="num">{{ $fmt.duration(item.duration) }}</td>
                <td class="num">{{ $fmt.size(item.size) }}</td>
                <td class="dim" style="font-size:12px">{{ item.quality || '—' }}</td>
                <td><span :class="statusClass(item.status)" style="font-size:12px">{{ item.status_label }}</span></td>
                <td class="dim" style="font-size:12px">{{ item.reason }}</td>
                <td class="dim ellipsis" style="max-width:260px"
                    :title="item.status === 'upgrade' ? replaceTitle(item) : matchedTitle(item)">
                  <span v-if="item.status === 'upgrade'" class="pill warn" style="margin-right:6px">库内替换</span>
                  {{ item.matched && item.matched.length ? item.matched[0].name : '—' }}
                  <span v-if="item.matched && item.matched.length && item.matched[0].quality"
                        class="dim"> · {{ item.matched[0].quality }}</span>
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
          <span class="hint">「需人工确认」是时长或音频规格读不出来，一律不自动处理，先在第 7 步自检里看清楚</span>
          <span class="spacer"></span>
          <button class="btn" @click="run" :disabled="!canRun">
            <span v-if="taskRunning" class="spin"></span>
            {{ taskRunning ? '处理中…' : (replaceCount ? '移走重复并替换旧版本' : '移走重复文件') }}
          </button>
          <button class="btn primary" @click="next" :disabled="taskRunning">下一步 →</button>
        </div>

        <mh-result :show="showResult" title="查重处理完成" :tone="tone" @close="closeResult">
          <div class="stats" style="margin-bottom:12px">
            <div class="stat"><div class="n">{{ (result && result.planned) || 0 }}</div><div class="l">计划处理</div></div>
            <div class="stat"><div class="n">{{ (result && result.executed) || 0 }}</div><div class="l">已移走</div></div>
            <div class="stat"><div class="n">{{ (result && result.library_replaced) || 0 }}</div><div class="l">库内旧版本让位</div></div>
            <div class="stat"><div class="n" :class="(result && result.failed) ? 'err' : ''">{{ (result && result.failed) || 0 }}</div><div class="l">失败</div></div>
          </div>
          <div class="note err" v-if="result && result.error">{{ result.error }}</div>
          <div class="note" v-if="result && result.moved_to">
            目标：<span class="mono">{{ result.moved_to }}</span>
          </div>
          <div class="list-scroll" v-if="result && result.items && result.items.length" style="margin-top:10px">
            <div class="row-item" v-for="item in result.items" :key="item.source">
              <span class="pill" :class="item.side === 'library' ? 'warn' : 'info'"
                    style="margin-right:8px">{{ sideLabel(item.side) }}</span>
              <span class="name" :title="item.source">{{ item.name }}</span>
              <span class="meta ellipsis" style="max-width:45%">{{ item.reason }}</span>
            </div>
          </div>
          <div class="note" style="margin-top:10px">
            列表已刷新。库内旧版本移走后，工作区这份会在第 8 步归档进库。
          </div>
        </mh-result>

        <mh-confirm :show="showUpgradeConfirm" title="会移动库目录里的文件"
                    confirm-text="确认替换" @close="showUpgradeConfirm = false" @confirm="submit">
          <div class="note warn">
            本次会移走库目录里 <b>{{ replaceCount }}</b> 个音质更低的旧版本
            （{{ selectedUpgrades.length }} 个文件需要替换）。
          </div>
          <div class="note" style="margin-top:8px">
            它们会被移入 <span class="mono">重复文件目录</span>，不直接删除，需要时可以找回。
            原文件路径：
          </div>
          <div class="list-scroll" style="max-height:220px;margin-top:6px">
            <div class="row-item" v-for="item in selectedUpgrades" :key="item.path">
              <span class="name ellipsis" :title="replaceTitle(item)">{{ item.name }}</span>
              <span class="meta" style="max-width:55%">{{ (item.replace || []).length }} 个旧版本</span>
            </div>
          </div>
        </mh-confirm>

        <mh-confirm :show="showSkipConfirm" title="还有文件没确认"
                    confirm-text="仍然继续" @close="showSkipConfirm = false" @confirm="doNext">
          <div class="note warn">
            还有 {{ pending.length }} 个文件没有确认：
            {{ stats.duplicate }} 个库中已有、{{ stats.upgrade }} 个音质可升级、
            {{ stats.unknown }} 个需人工确认。
          </div>
          <div class="note" style="margin-top:8px">
            继续下一步不会删除任何文件，但归档时这些文件会一起入库，可能造成库里重复。
          </div>
        </mh-confirm>
      </div>`,
  };
})(window.MH);
