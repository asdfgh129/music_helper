/* 第 6 步：查重（工作区 ↔ 库目录） */
(function (MH) {
  'use strict';

  /* 两栏比对：左栏是工作区待入库的文件，右栏是库里与它对应的副本。
     左栏勾选 = 这一项要处理；右栏勾选 = 库里哪几个旧版本让位。
     右栏是 1:N，同一个工作区文件可能对上库里好几份。 */

  MH.StepDedupe = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['prev', 'next'],
    data: function () {
      return {
        loading: false,
        error: '',
        data: null,
        filter: 'all',
        selected: {},          // 工作区 path -> bool
        replaces: {},          // 工作区 path -> {库内 path: bool}
        focusPath: '',
        pendingAction: '',     // trash（删除）| move（移入重复目录）
        showConfirm: false,
        showResult: false,
        result: null,
        showSkipConfirm: false,
      };
    },
    computed: {
      items: function () { return (this.data && this.data.items) || []; },
      fingerprintStatus: function () {
        return (this.data && this.data.fingerprint) || { status: '', count: 0, reason: '' };
      },
      fingerprintBlocked: function () {
        return !!this.data && this.data.fingerprint_ready === false;
      },
      filtered: function () {
        if (this.filter === 'all') return this.items;
        if (this.filter === 'pending') {
          return this.items.filter((item) => item.status !== 'unique');
        }
        return this.items.filter((item) => item.status === this.filter);
      },
      /* 试听队列：左栏按当前筛选，右栏按当前聚焦文件的库内副本 */
      auditionQueue: function () {
        return this.filtered.map((item) => ({ path: item.path, name: item.name }));
      },
      matchedQueue: function () {
        return ((this.focus && this.focus.matched) || [])
          .map((row) => ({ path: row.path, name: row.name }));
      },
      focus: function () {
        if (!this.focusPath) return null;
        return this.items.find((item) => item.path === this.focusPath) || null;
      },
      handleable: function () {
        return this.items.filter((item) =>
          item.status === 'duplicate' || item.status === 'upgrade');
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
      selectedDuplicates: function () {
        return this.selectedItems.filter((item) => item.status === 'duplicate');
      },
      selectedUpgrades: function () {
        return this.selectedItems.filter((item) => item.status === 'upgrade');
      },
      /* 库里将被移出的文件：[{ item, row }]，按当前勾选实时算 */
      libraryRemovals: function () {
        const list = [];
        this.selectedUpgrades.forEach((item) => {
          const map = this.replaces[item.path] || {};
          (item.replace || []).forEach((row) => {
            if (map[row.path]) list.push({ item: item, row: row });
          });
        });
        return list;
      },
      libraryRemoveCount: function () { return this.libraryRemovals.length; },
      /* 「删除」只作用于工作区那份；upgrade 的工作区文件要留着入库 */
      workspaceActionCount: function () { return this.selectedDuplicates.length; },
      actionTotal: function () {
        return this.workspaceActionCount + this.libraryRemoveCount;
      },
      confirmTitle: function () {
        return this.pendingAction === 'trash' ? '确认删除所选文件' : '确认移入重复目录';
      },
      confirmText: function () {
        return this.pendingAction === 'trash' ? '确认删除' : '确认移走';
      },
      pending: function () {
        return this.items.filter((item) =>
          (item.status === 'duplicate' || item.status === 'upgrade')
          && !this.selected[item.path]);
      },
      stats: function () {
        const base = this.data || {};
        return {
          total: base.total || 0,
          unique: base.unique || 0,
          duplicate: base.duplicate || 0,
          upgrade: base.upgrade || 0,
          upgradeQuality: base.upgrade_quality || 0,
          upgradeFormat: base.upgrade_format || 0,
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
        return !this.taskRunning && this.actionTotal > 0;
      },
      /* 「删除」只作用于工作区那份；只选了可替换项时没有可删的文件 */
      canTrash: function () {
        return !this.taskRunning && this.workspaceActionCount > 0;
      },
      trashLabel: function () {
        if (!this.actionTotal) return '删除所选';
        const parts = [];
        if (this.workspaceActionCount) parts.push(this.workspaceActionCount + ' 项');
        if (this.libraryRemoveCount) parts.push('替换 ' + this.libraryRemoveCount);
        return '删除所选（' + parts.join(' · ') + '）';
      },
      moveLabel: function () {
        if (this.taskRunning) return '处理中…';
        const parts = [];
        if (this.workspaceActionCount) parts.push('移走 ' + this.workspaceActionCount + ' 项');
        if (this.libraryRemoveCount) parts.push('替换 ' + this.libraryRemoveCount + ' 项');
        return parts.length ? parts.join(' · ') : '移入重复目录';
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
          this.resetSelection(data.items || []);
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      /* 默认只勾「库中已有」——那只动工作区，随时可恢复。
         「音质/格式替换」会移动库里的文件，默认不勾，必须逐项确认。 */
      resetSelection(items) {
        const selected = {};
        const replaces = {};
        items.forEach((item) => {
          selected[item.path] = item.status === 'duplicate';
          if (item.status === 'upgrade') {
            const map = {};
            (item.replace || []).forEach((row) => { map[row.path] = true; });
            replaces[item.path] = map;
          }
        });
        this.selected = selected;
        this.replaces = replaces;
        if (!items.some((item) => item.path === this.focusPath)) {
          const first = items.find((item) =>
            item.status === 'duplicate' || item.status === 'upgrade') || items[0];
          this.focusPath = first ? first.path : '';
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
        const next = Object.assign({}, this.selected);
        this.handleable.forEach((item) => { next[item.path] = value; });
        this.selected = next;
      },
      selectOnly: function (status) {
        const next = {};
        this.items.forEach((item) => { next[item.path] = item.status === status; });
        this.selected = next;
      },
      focusItem: function (item) { this.focusPath = item.path; },
      /* 右栏：只有「库里这份更差」时才允许勾选移出 */
      canReplace: function (item, row) {
        return item.status === 'upgrade' && row.relation === 'better';
      },
      isReplacing: function (item, row) {
        const map = this.replaces[item.path] || {};
        return !!map[row.path];
      },
      toggleReplace: function (item, row) {
        if (!this.canReplace(item, row)) return;
        const map = Object.assign({}, this.replaces[item.path] || {});
        map[row.path] = !map[row.path];
        this.replaces = Object.assign({}, this.replaces, { [item.path]: map });
      },
      toggleAllReplaces: function (value) {
        const next = Object.assign({}, this.replaces);
        this.selectedUpgrades.forEach((item) => {
          const map = {};
          (item.replace || []).forEach((row) => { map[row.path] = value; });
          next[item.path] = map;
        });
        this.replaces = next;
      },
      ask: function (action) {
        if (!this.actionTotal) {
          this.message('先勾选要处理的文件', 'err');
          return;
        }
        this.pendingAction = action;
        this.showConfirm = true;
      },
      async doRun() {
        const action = this.pendingAction;
        this.showConfirm = false;
        if (!action) return;
        const statuses = [];
        this.selectedItems.forEach((item) => {
          if (statuses.indexOf(item.status) < 0) statuses.push(item.status);
        });
        const replaces = {};
        this.selectedUpgrades.forEach((item) => {
          const map = this.replaces[item.path] || {};
          replaces[item.path] = (item.replace || [])
            .filter((row) => map[row.path])
            .map((row) => row.path);
        });
        this.result = null;
        const id = await this.submitTask('dedupe-cross', {
          paths: this.selectedPaths,
          action: action,
          statuses: statuses,
          replaces: replaces,
        });
        if (id) {
          const extra = this.libraryRemoveCount
            ? '，库里 ' + this.libraryRemoveCount + ' 个旧版本让位'
            : '';
          this.message((action === 'trash' ? '开始删除 ' : '开始移走 ')
            + this.workspaceActionCount + ' 项' + extra + '…');
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
      statusColor: function (status) {
        const map = { duplicate: 'var(--err)', upgrade: 'var(--warn)',
          unknown: 'var(--warn)', unique: 'var(--ok)' };
        return map[status] || 'var(--muted)';
      },
      relationLabel: function (row) {
        if (row.relation === 'better') {
          return row.basis === 'format' ? '更占地方' : '音质更低';
        }
        if (row.relation === 'worse') return '音质更高';
        if (row.relation === 'same') return '音质相同';
        return '需人工';
      },
      relationColor: function (row) {
        if (row.relation === 'better') return 'var(--warn)';
        if (row.relation === 'same') return 'var(--muted)';
        return 'var(--dim)';
      },
      sideLabel: function (side) {
        return side === 'library' ? '库' : '工作区';
      },
      filterLabel: function (key) {
        const map = { all: '全部', pending: '待处理', duplicate: '库中已有',
          upgrade: '音质升级', unknown: '需人工', unique: '库中不存在' };
        return map[key] || key;
      },
      filterCount: function (key) {
        if (key === 'all') return this.items.length;
        if (key === 'pending') return this.items.filter((i) => i.status !== 'unique').length;
        return this.items.filter((i) => i.status === key).length;
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 6 步 · 查重（工作区 ↔ 库目录）</h2>
          <span class="sub">逐条比对：库里已有的不再入库；库里音质更低或更占地方的，由工作区这份替换</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load(true)" :disabled="loading || taskRunning">重新扫描库</button>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">工作区文件</div></div>
          <div class="stat"><div class="n">{{ stats.unique }}</div><div class="l">库中不存在</div></div>
          <div class="stat"><div class="n" :class="stats.duplicate ? 'err' : ''">{{ stats.duplicate }}</div><div class="l">库中已有</div></div>
          <div class="stat"><div class="n" :class="stats.upgrade ? 'warn' : ''">{{ stats.upgrade }}</div><div class="l">可替换库内</div></div>
          <div class="stat"><div class="n" :class="stats.unknown ? 'warn' : ''">{{ stats.unknown }}</div><div class="l">需人工确认</div></div>
          <div class="stat"><div class="n">{{ stats.ready }}</div><div class="l">可入库</div></div>
        </div>

        <div v-if="fingerprintBlocked" class="note" style="margin-top:12px">
          <b class="err">声纹库未就绪（{{ fingerprintStatus.status }}）</b>：
          {{ fingerprintStatus.reason }}。本轮所有文件都不会标记为「可入库」，
          第 8 步也会拒绝归档。请回第 2 步补建声纹库或执行
          <span class="mono">python main.py --init</span>，再点「重新扫描库」。
        </div>
        <div v-else-if="fingerprintStatus.status === 'ready'" class="note" style="margin-top:12px">
          声纹比对已启用：库内 {{ fingerprintStatus.count }} 条指纹参与判定，
          不同文件名、不同标签的同一录音也会被认出来；版本标记不同的候选仍转人工。
        </div>

        <div class="card" style="margin-top:14px;padding:12px 16px">
          <div class="toolbar">
            <div class="seg">
              <button v-for="key in ['all', 'pending', 'duplicate', 'upgrade', 'unique', 'unknown']"
                      :key="key" :class="{ on: filter === key }" @click="filter = key">
                {{ filterLabel(key) }} {{ filterCount(key) }}
              </button>
            </div>
            <span class="divider"></span>
            <button class="btn sm" @click="selectAll(true)">全选可处理</button>
            <button class="btn sm" @click="selectAll(false)">全不选</button>
            <button class="btn sm" v-if="stats.duplicate" @click="selectOnly('duplicate')">仅库中已有</button>
            <button class="btn sm" v-if="stats.upgrade" @click="selectOnly('upgrade')">仅可替换</button>
            <span class="spacer"></span>
            <span class="pill info">已选 {{ selectedCount }} / {{ handleable.length }}</span>
          </div>
          <div class="note" style="margin-top:10px">
            比对范围：<span class="mono">{{ workspace }}</span> ↔ <span class="mono">{{ library }}</span>
            （库内 {{ stats.library }} 首）。
            <b>「库中已有」默认勾选</b>（只动工作区）；<b>「可替换库内」默认不勾</b>，
            要到右侧逐个确认哪几个旧版本让位。
          </div>
          <div class="note warn" style="margin-top:8px"
               v-if="selectedUpgrades.length && !libraryRemoveCount">
            已选中的 {{ selectedUpgrades.length }} 个「可替换」项里没有勾选任何库内文件，
            这些项本次不会处理（选中后到右栏勾上要移走的旧版本）。
          </div>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>
        <div class="note warn" v-if="data && !data.library_exists" style="margin-top:12px">
          库目录不存在，无法比对。请先在第 1 步设置库目录，并在第 2 步初始化。
        </div>

        <div class="dual" style="margin-top:14px">
          <!-- 左栏：工作区 -->
          <div class="pane">
            <header>
              <span>工作区待入库</span>
              <span class="path">点一行查看库里对应的副本</span>
              <span class="pill">{{ filtered.length }} / {{ items.length }}</span>
            </header>
            <div class="body">
              <div class="row-item" v-for="item in filtered" :key="item.path"
                   :class="{ sel: focusPath === item.path }"
                   style="cursor:pointer" @click="focusItem(item)">
                <input type="checkbox" :checked="!!selected[item.path]"
                       :disabled="!selectable(item)" @click.stop @change="toggle(item)">
                <span class="name" :title="item.path">{{ item.name }}</span>
                <span class="tag" :style="{ color: statusColor(item.status) }">{{ item.status_label }}</span>
                <span class="meta">{{ item.quality }}</span>
                <button class="btn link dedupe-play"
                        @click.stop="playTrack(item.path, item.name, auditionQueue)"
                        title="试听这份工作区文件">▶</button>
              </div>
              <div class="empty" v-if="loading">扫描工作区与库目录…（首次比对大库会慢一些）</div>
              <div class="empty" v-else-if="!filtered.length">这个筛选下没有文件</div>
            </div>
            <footer>
              <span>共 {{ stats.total }} 个</span>
              <span>库中已有 {{ stats.duplicate }}</span>
              <span>可替换 {{ stats.upgrade }}</span>
            </footer>
          </div>

          <!-- 右栏：库内对应文件（1:N） -->
          <div class="pane">
            <header>
              <span>库中对应文件</span>
              <span class="path" :title="focus ? focus.path : ''">
                {{ focus ? focus.name : '（左侧选一个文件）' }}
              </span>
              <span class="pill" v-if="focus">{{ (focus.matched || []).length }} 个</span>
            </header>
            <div class="body">
              <template v-if="focus">
                <div class="note" v-if="!focus.matched || !focus.matched.length" style="margin:12px">
                  库里没有这首歌，第 8 步会作为新文件入库。
                </div>
                <div class="row-item" v-for="row in focus.matched" :key="row.path">
                  <input type="checkbox" v-if="canReplace(focus, row)"
                         :checked="isReplacing(focus, row)" @change="toggleReplace(focus, row)">
                  <span v-else class="tag" style="color:var(--dim)">保留</span>
                  <span class="name" :title="row.path">{{ row.name }}</span>
                  <span class="tag" :style="{ color: relationColor(row) }">{{ relationLabel(row) }}</span>
                  <span class="meta">{{ row.quality }}</span>
                  <button class="btn link dedupe-play"
                          @click.stop="playTrack(row.path, row.name, matchedQueue)"
                          title="试听库里的这份副本">▶</button>
                </div>
                <div class="group-head" v-if="focus.status === 'upgrade'" style="position:static">
                  <button class="btn link" @click="toggleAllReplaces(true)">全勾</button>
                  <button class="btn link" @click="toggleAllReplaces(false)">全不勾</button>
                  <span class="path">勾上的旧版本会移入重复目录，库目录里的文件不会被直接删除</span>
                </div>
                <div class="group-head" v-if="focus.status === 'duplicate'" style="position:static">
                  <span class="path">库中已有同等或更好的版本：右侧全部保留，左侧这份可以删除</span>
                </div>
                <div class="group-head" v-if="focus.status === 'unknown'" style="position:static">
                  <span class="path">大小与时长都对不上，程序不下结论，请自己核对后决定</span>
                </div>
                <div class="note dim" v-if="focus.matched_truncated" style="margin:10px 12px">
                  只列出前 {{ focus.matched.length }} 个，共 {{ focus.matched_total }} 个。
                </div>
                <div class="note" style="margin:10px 12px" v-if="focus.reason">
                  {{ focus.reason }}
                </div>
              </template>
              <div class="empty" v-else>在左侧点选一个文件，这里会列出库里与它对应的所有副本</div>
            </div>
            <footer>
              <span v-if="focus && focus.status === 'upgrade'">
                库里 {{ (focus.replace || []).length }} 个旧版本可让位
              </span>
              <span v-else-if="focus">依据：{{ focus.kind || '—' }}</span>
              <span class="spacer"></span>
              <span>本次将移出库 {{ libraryRemoveCount }} 个</span>
            </footer>
          </div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>处理进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="taskRunning">← 上一步</button>
          <span class="hint">「需人工确认」是大小与时长都对不上，一律不自动处理，先在第 7 步自检里看清楚</span>
          <span class="spacer"></span>
          <button class="btn" @click="ask('move')" :disabled="!canRun">
            <span v-if="taskRunning && pendingAction === 'move'" class="spin"></span>
            {{ moveLabel }}
          </button>
          <button class="btn danger" @click="ask('trash')" :disabled="!canTrash">
            {{ trashLabel }}
          </button>
          <button class="btn primary" @click="next" :disabled="taskRunning">下一步 →</button>
        </div>

        <mh-confirm :show="showConfirm" :title="confirmTitle" :confirm-text="confirmText"
                    @close="showConfirm = false" @confirm="doRun">
          <div class="note" v-if="pendingAction === 'trash'">
            工作区里的重复文件会移入回收站 <span class="mono">log/_trash</span>，可以找回，不进重复目录。
          </div>
          <div class="note" v-else>
            工作区里的重复文件会移入重复目录，保留一份可对照的副本。
          </div>

          <div style="margin-top:10px">
            <div class="lbl dim" style="font-size:12px">
              工作区 · {{ pendingAction === 'trash' ? '将删除' : '将移走' }} {{ workspaceActionCount }} 个
            </div>
            <div class="list-scroll" style="max-height:150px;margin-top:4px">
              <div class="row-item" v-for="item in selectedDuplicates" :key="item.path">
                <span class="name ellipsis" :title="item.path">{{ item.name }}</span>
                <span class="meta">{{ $fmt.size(item.size) }}</span>
              </div>
              <div class="empty" v-if="!selectedDuplicates.length" style="padding:10px">
                工作区没有选中的重复文件
              </div>
            </div>
          </div>

          <div style="margin-top:10px">
            <div class="lbl dim" style="font-size:12px">
              库目录 · 将移出 {{ libraryRemoveCount }} 个旧版本（进重复目录，不删除）
            </div>
            <div class="list-scroll" style="max-height:150px;margin-top:4px">
              <div class="row-item" v-for="entry in libraryRemovals" :key="entry.row.path">
                <span class="tag warn">库</span>
                <span class="name ellipsis" :title="entry.row.path">{{ entry.row.name }}</span>
                <span class="meta">{{ entry.row.quality }}</span>
              </div>
              <div class="empty" v-if="!libraryRemovals.length" style="padding:10px">
                库里没有文件会被移动
              </div>
            </div>
          </div>

          <div class="note warn" v-if="selectedUpgrades.length && !libraryRemoveCount">
            {{ selectedUpgrades.length }} 个「可替换」项里没有勾选任何库内文件，这些项本次不做处理。
          </div>
        </mh-confirm>

        <mh-result :show="showResult" title="查重处理完成" :tone="tone" @close="closeResult">
          <div class="stats" style="margin-bottom:12px">
            <div class="stat"><div class="n">{{ (result && result.planned) || 0 }}</div><div class="l">计划处理</div></div>
            <div class="stat"><div class="n">{{ (result && result.executed) || 0 }}</div><div class="l">已完成</div></div>
            <div class="stat"><div class="n">{{ (result && result.library_replaced) || 0 }}</div><div class="l">库内旧版本让位</div></div>
            <div class="stat"><div class="n" :class="(result && result.failed) ? 'err' : ''">{{ (result && result.failed) || 0 }}</div><div class="l">失败</div></div>
          </div>
          <div class="note err" v-if="result && result.error">{{ result.error }}</div>
          <div class="note" v-if="result && result.moved_to">
            目标：<span class="mono">{{ result.moved_to }}</span>
          </div>
          <div class="note" v-if="result && result.skipped">
            {{ result.skipped }} 项没有勾选库内文件，本次跳过，保持原样。
          </div>
          <div class="list-scroll" v-if="result && result.items && result.items.length" style="margin-top:10px">
            <div class="row-item" v-for="item in result.items" :key="item.source">
              <span class="tag"
                    :style="{ color: item.side === 'library' ? 'var(--warn)' : 'var(--accent)', marginRight: '8px' }">
                {{ sideLabel(item.side) }}</span>
              <span class="name" :title="item.source">{{ item.name }}</span>
              <span class="meta ellipsis" style="max-width:45%">{{ item.reason }}</span>
            </div>
          </div>
          <div class="note" style="margin-top:10px">
            列表已刷新。库内旧版本移走后，工作区这份会在第 8 步归档进库。
          </div>
        </mh-result>

        <mh-confirm :show="showSkipConfirm" title="还有文件没确认"
                    confirm-text="仍然继续" @close="showSkipConfirm = false" @confirm="doNext">
          <div class="note warn">
            还有 {{ pending.length }} 个文件没有勾选：
            {{ stats.duplicate }} 个库中已有、{{ stats.upgrade }} 个可替换库内、
            {{ stats.unknown }} 个需人工确认。
          </div>
          <div class="note" style="margin-top:8px">
            继续下一步不会删除任何文件，但归档时这些文件会一起入库，可能造成库里重复。
          </div>
        </mh-confirm>
      </div>`,
  };
})(window.MH);
