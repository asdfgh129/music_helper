/* 第 5 步：标签与歌词补全（可选字段、可排序、可单曲编辑） */
(function (MH) {
  'use strict';

  MH.StepTags = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['prev', 'next'],
    data: function () {
      return {
        loading: false,
        error: '',
        data: null,
        selected: {},
        // 勾选只表示「允许写入」；已有值仍然不会被覆盖
        fields: { title: true, artist: true, album: true, year: true, genre: true },
        opts: { fingerprint: true, cover: true, lyrics: true },
        sortStack: [{ key: 'name', dir: 1 }],
        showResult: false,
        result: null,
        merged: {},
        // 单曲编辑抽屉
        editing: null,
        form: { title: '', artist: '', album: '', year: '', genre: '' },
        lyric: '',
        drawerBusy: false,
        drawerError: '',
        drawerNote: '',
      };
    },
    computed: {
      fieldDefs: function () {
        return [
          { key: 'title', label: '歌名' },
          { key: 'artist', label: '歌手' },
          { key: 'album', label: '专辑' },
          { key: 'year', label: '年份' },
          { key: 'genre', label: '流派' },
        ];
      },
      items: function () { return (this.data && this.data.items) || []; },
      total: function () { return this.items.length; },
      sortedItems: function () {
        const stack = this.sortStack.length ? this.sortStack : [{ key: 'name', dir: 1 }];
        const rows = this.items.slice();
        rows.sort((a, b) => {
          for (let i = 0; i < stack.length; i += 1) {
            const cmp = this.compareRows(a, b, stack[i].key) * stack[i].dir;
            if (cmp) return cmp;
          }
          return 0;
        });
        return rows;
      },
      selectedPaths: function () {
        return Object.keys(this.selected).filter((path) => this.selected[path]);
      },
      selectedCount: function () { return this.selectedPaths.length; },
      fieldKeys: function () {
        return this.fieldDefs
          .map((def) => def.key)
          .filter((key) => this.fields[key]);
      },
      stats: function () {
        const base = this.data || {};
        return {
          total: base.total || 0,
          ready: base.ready || 0,
          tags: base.missing_tags || 0,
          lrc: base.missing_lrc || 0,
          cover: base.missing_cover || 0,
          mismatch: base.mismatch || 0,
        };
      },
      tone: function () {
        if (!this.result) return 'info';
        return this.result.failed ? 'warn' : 'info';
      },
    },
    mounted: function () { this.load(); },
    methods: {
      async load(silent) {
        if (!silent) this.loading = true;
        this.error = '';
        try {
          const data = await MH.api.get('/api/tags/preview');
          this.data = data;
          if (!silent) {
            this.selected = {};
            (data.items || []).forEach((item) => {
              if (!item.ready || !item.has_lrc || !item.has_cover) {
                this.selected[item.path] = true;
              }
            });
          }
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      toggle: function (path) {
        this.selected = Object.assign({}, this.selected, { [path]: !this.selected[path] });
      },
      selectAll: function (value) {
        const next = {};
        this.items.forEach((item) => { next[item.path] = value; });
        this.selected = next;
      },
      selectFilter: function (predicate) {
        const next = {};
        this.items.forEach((item) => { if (predicate(item)) next[item.path] = true; });
        this.selected = next;
      },
      allFields: function (value) {
        const next = {};
        this.fieldDefs.forEach((def) => { next[def.key] = value; });
        this.fields = next;
      },
      onlyMissing: function () {
        // 只看已勾选的行（没勾就看全部），把「当前为空」的字段打开
        const rows = this.selectedCount
          ? this.items.filter((item) => this.selected[item.path])
          : this.items;
        const next = {};
        this.fieldDefs.forEach((def) => {
          next[def.key] = rows.some((item) => !item[def.key]);
        });
        this.fields = next;
        this.message('已按当前选中行把空字段打开');
      },
      /* ---------------- 排序 ---------------- */
      rowValue: function (item, key) {
        if (key === 'duration') return Number(item.duration) || 0;
        if (key === 'size') return Number(item.size) || 0;
        if (key === 'state') return item.ready ? 1 : 0;
        return item[key] || '';
      },
      compareRows: function (a, b, key) {
        const left = this.rowValue(a, key);
        const right = this.rowValue(b, key);
        if (typeof left === 'number' && typeof right === 'number') return left - right;
        return String(left).localeCompare(String(right), 'zh-Hans-CN', { numeric: true });
      },
      sortBy: function (key, event) {
        const stack = this.sortStack.slice();
        const index = stack.findIndex((item) => item.key === key);
        if (!event || !event.shiftKey) {
          // 单击：升序 → 降序 → 取消（回到默认的文件名升序）
          const current = index === 0 ? stack[0].dir : 0;
          const next = current === 1 ? -1 : (current === -1 ? 0 : 1);
          this.sortStack = next ? [{ key: key, dir: next }] : [];
          return;
        }
        // Shift + 单击：追加第二、第三排序键（如 艺术家 → 专辑 → 时长）
        if (index > 0) {
          stack[index] = { key: key, dir: stack[index].dir === 1 ? -1 : 1 };
        } else {
          stack.push({ key: key, dir: 1 });
        }
        this.sortStack = stack;
      },
      arrow: function (key) {
        const index = this.sortStack.findIndex((item) => item.key === key);
        if (index < 0) return '';
        const mark = this.sortStack[index].dir === 1 ? '▲' : '▼';
        return index === 0 ? mark : mark + (index + 1);
      },
      /* ---------------- 批量补全 ---------------- */
      async run() {
        if (!this.selectedCount) {
          this.message('先选几个文件', 'err');
          return;
        }
        if (!this.fieldKeys.length && !this.opts.cover && !this.opts.lyrics) {
          this.message('至少勾选一个要补的字段', 'err');
          return;
        }
        this.result = null;
        const id = await this.submitTask('tags', {
          paths: this.selectedPaths,
          with_fingerprint: this.opts.fingerprint,
          write_cover: this.opts.cover,
          write_lyrics: this.opts.lyrics,
          fields: this.fieldKeys,
        });
        if (id) this.message('开始补全 ' + this.selectedCount + ' 个文件…');
      },
      onTaskFinished(task) {
        if (task.status === 'error') {
          this.result = { total: 0, updated: 0, failed: 1, items: [], error: task.error };
        } else {
          this.result = task.result || {};
        }
        const merged = Object.assign({}, this.merged);
        (this.result.items || []).forEach((item) => { merged[item.path] = item; });
        this.merged = merged;
        this.showResult = true;
      },
      closeResult() {
        this.showResult = false;
        this.load(true);
      },
      rowState: function (item) {
        const done = this.merged[item.path];
        if (done) {
          if (done.message && !done.updated) return { text: done.message, cls: '' };
          const parts = [];
          if (done.fields && done.fields.length) parts.push('+' + done.fields.join('/'));
          if (done.cover) parts.push('+封面');
          if (done.lyric) parts.push('+歌词');
          return { text: parts.length ? parts.join(' ') : '无变化', cls: parts.length ? 'ok' : '' };
        }
        if (!item.problems.length) return { text: '可入库', cls: 'ok' };
        return { text: item.problems.join('；'), cls: 'warn' };
      },
      fieldOf: function (item, key) {
        const done = this.merged[item.path];
        return (done && done.fields && done.fields.indexOf(key) >= 0) ? 'field-new' : '';
      },
      /* ---------------- 单曲编辑 ---------------- */
      async openEdit(item) {
        this.drawerError = '';
        this.drawerNote = '';
        this.editing = { path: item.path, name: item.name, loading: true, consistency: item.consistency };
        this.form = {
          title: item.title || '',
          artist: item.artist || '',
          album: item.album || '',
          year: item.year || '',
          genre: item.genre || '',
        };
        this.lyric = '';
        try {
          const detail = await MH.api.get('/api/track', { path: item.path });
          this.editing = detail;
          this.form = Object.assign({}, detail.tags);
          this.lyric = detail.lyric || '';
        } catch (err) {
          this.drawerError = err.message;
        }
      },
      closeEdit() {
        if (this.drawerBusy) return;
        this.editing = null;
      },
      async fetchOnline() {
        if (!this.editing || !this.editing.path) return;
        this.drawerBusy = true;
        this.drawerError = '';
        try {
          const res = await MH.api.post('/api/track/fetch', {
            path: this.editing.path,
            fields: this.fieldKeys,
          });
          if (res.error) this.drawerError = res.error;
          this.form = Object.assign({}, this.form, res.tags || {});
          this.drawerNote = res.source
            ? '来自 ' + res.source + '，已填入空缺字段（不会覆盖已有值）'
            : '在线没有查到结果，可以手填';
        } catch (err) {
          this.drawerError = err.message;
        } finally {
          this.drawerBusy = false;
        }
      },
      async saveEdit() {
        if (!this.editing || !this.editing.path) return;
        this.drawerBusy = true;
        this.drawerError = '';
        try {
          const res = await MH.api.post('/api/track/save', {
            path: this.editing.path,
            tags: this.form,
            lyric: this.lyric,
          });
          if (!res.ok) {
            this.drawerError = res.error || '保存失败';
            return;
          }
          const parts = [];
          if (res.changed && res.changed.length) parts.push('已更新 ' + res.changed.join('/'));
          if (res.lyric_saved) parts.push('歌词已保存');
          if (res.ignored && res.ignored.length) {
            parts.push('以下字段不能置空，已保留原值：' + res.ignored.join('/'));
          }
          this.message(parts.length ? parts.join('；') : '没有变化');
          this.editing = null;
          this.load(true);
        } catch (err) {
          this.drawerError = err.message;
        } finally {
          this.drawerBusy = false;
        }
      },
      stateClass: function (state) {
        return state === 'ok' ? 'ok' : (state === 'mismatch' ? 'err' : 'dim');
      },
      stateMark: function (state) {
        if (state === 'ok') return '✓';
        return state === 'mismatch' ? '✗' : '—';
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 5 步 · 标签与歌词补全</h2>
          <span class="sub">工作区顶层文件 · 只填空缺，不覆盖已有值 · 不改文件名</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load()" :disabled="loading || taskRunning">刷新列表</button>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">工作区文件</div></div>
          <div class="stat"><div class="n">{{ stats.ready }}</div><div class="l">已可入库</div></div>
          <div class="stat"><div class="n" :class="stats.tags ? 'warn' : ''">{{ stats.tags }}</div><div class="l">缺核心标签</div></div>
          <div class="stat"><div class="n" :class="stats.mismatch ? 'err' : ''">{{ stats.mismatch }}</div><div class="l">文件名与标签矛盾</div></div>
          <div class="stat"><div class="n" :class="stats.lrc ? 'warn' : ''">{{ stats.lrc }}</div><div class="l">缺歌词</div></div>
          <div class="stat"><div class="n" :class="stats.cover ? 'warn' : ''">{{ stats.cover }}</div><div class="l">缺封面</div></div>
        </div>

        <div class="card" style="margin-top:14px;padding:12px 16px">
          <div class="toolbar">
            <div class="seg">
              <button @click="selectFilter(i => true)">全选</button>
              <button @click="selectAll(false)">全不选</button>
              <button @click="selectFilter(i => i.problems.length)">仅缺标签</button>
              <button @click="selectFilter(i => !i.has_lrc)">仅缺歌词</button>
              <button @click="selectFilter(i => !i.has_cover)">仅缺封面</button>
              <button @click="selectFilter(i => !i.consistency.ok)">仅文件名矛盾</button>
            </div>
            <span class="spacer"></span>
            <span class="pill info">已选 {{ selectedCount }} / {{ total }}</span>
          </div>

          <div class="field-row" style="margin-top:10px">
            <span class="lbl">要补的字段</span>
            <label v-for="def in fieldDefs" :key="def.key">
              <input type="checkbox" v-model="fields[def.key]" :disabled="taskRunning"> {{ def.label }}
            </label>
            <label><input type="checkbox" v-model="opts.cover" :disabled="taskRunning"> 封面</label>
            <label><input type="checkbox" v-model="opts.lyrics" :disabled="taskRunning"> 歌词</label>
            <span class="spacer"></span>
            <button class="btn link" @click="allFields(true)">全开</button>
            <button class="btn link" @click="allFields(false)">全关</button>
            <button class="btn link" @click="onlyMissing">仅缺失项</button>
          </div>

          <div class="checks" style="margin-top:8px">
            <label><input type="checkbox" v-model="opts.fingerprint" :disabled="taskRunning">
              声纹识别（MusicBrainz，较慢但更准）
            </label>
          </div>
          <div class="note" style="margin-top:8px">
            勾选只表示「允许写入」：字段为空才填，已有值不会被覆盖。所以「只补歌词」就是关掉其余 5 个字段和封面。
          </div>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>

        <div class="tbl-wrap" style="margin-top:14px">
          <table class="grid">
            <thead>
              <tr>
                <th style="width:34px"></th>
                <th class="sortable" @click="sortBy('name', $event)">文件名 <i class="arrow">{{ arrow('name') }}</i></th>
                <th class="sortable" @click="sortBy('artist', $event)">艺术家 <i class="arrow">{{ arrow('artist') }}</i></th>
                <th class="sortable" @click="sortBy('title', $event)">歌名 <i class="arrow">{{ arrow('title') }}</i></th>
                <th class="sortable" @click="sortBy('album', $event)">专辑 <i class="arrow">{{ arrow('album') }}</i></th>
                <th class="sortable" style="width:64px" @click="sortBy('year', $event)">年份 <i class="arrow">{{ arrow('year') }}</i></th>
                <th class="sortable" style="width:84px" @click="sortBy('genre', $event)">流派 <i class="arrow">{{ arrow('genre') }}</i></th>
                <th class="sortable num" style="width:64px" @click="sortBy('duration', $event)">时长 <i class="arrow">{{ arrow('duration') }}</i></th>
                <th style="width:44px">封面</th>
                <th style="width:44px">歌词</th>
                <th class="sortable" @click="sortBy('state', $event)">状态 <i class="arrow">{{ arrow('state') }}</i></th>
                <th style="width:100px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in sortedItems" :key="item.path" :class="{ sel: selected[item.path] }">
                <td><input type="checkbox" :checked="!!selected[item.path]" @change="toggle(item.path)"></td>
                <td class="fname" :title="item.path">{{ item.name }}</td>
                <td :class="fieldOf(item, 'artist')">{{ item.artist || '—' }}</td>
                <td :class="fieldOf(item, 'title')">{{ item.title || '—' }}</td>
                <td :class="fieldOf(item, 'album')">{{ item.album || '—' }}</td>
                <td :class="fieldOf(item, 'year')">{{ item.year || '—' }}</td>
                <td :class="fieldOf(item, 'genre')">{{ item.genre || '—' }}</td>
                <td class="num">{{ $fmt.duration(item.duration) }}</td>
                <td><span :class="item.has_cover ? 'ok' : 'dim'">{{ item.has_cover ? '有' : '无' }}</span></td>
                <td><span :class="item.has_lrc ? 'ok' : 'dim'">{{ item.has_lrc ? '有' : '无' }}</span></td>
                <td>
                  <span :class="rowState(item).cls" style="font-size:12px">{{ rowState(item).text }}</span>
                </td>
                <td>
                  <button class="btn link" @click="playTrack(item.path, item.name)" title="试听并显示歌词">▶ 试听</button>
                  <button class="btn link" @click="openEdit(item)" :disabled="taskRunning">编辑</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="empty" v-if="loading">读取工作区…</div>
          <div class="empty" v-else-if="!items.length">工作区没有待处理文件（先做第 3、4 步）</div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>补全进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="taskRunning">← 上一步</button>
          <span class="hint">补全失败通常是没有网络或该曲目在线库里找不到，可稍后重试</span>
          <span class="spacer"></span>
          <button class="btn" @click="run" :disabled="taskRunning || !selectedCount">
            <span v-if="taskRunning" class="spin"></span> {{ taskRunning ? '补全中…' : '开始补全' }}
          </button>
          <button class="btn primary" @click="$emit('next')" :disabled="taskRunning">下一步 →</button>
        </div>

        <mh-result :show="showResult" title="补全完成" :tone="tone" @close="closeResult">
          <div class="stats" style="margin-bottom:12px">
            <div class="stat"><div class="n">{{ (result && result.total) || 0 }}</div><div class="l">处理</div></div>
            <div class="stat"><div class="n">{{ (result && result.updated) || 0 }}</div><div class="l">有更新</div></div>
            <div class="stat"><div class="n" :class="(result && result.failed) ? 'err' : ''">{{ (result && result.failed) || 0 }}</div><div class="l">失败</div></div>
          </div>
          <div class="note err" v-if="result && result.error">{{ result.error }}</div>
          <div class="list-scroll" v-if="result && result.items && result.items.length">
            <div class="row-item" v-for="item in result.items" :key="item.path">
              <span class="name" :title="item.path">{{ item.name }}</span>
              <span class="tag" v-if="item.cover" style="color:var(--ok)">封面</span>
              <span class="tag" v-if="item.lyric" style="color:var(--ok)">歌词</span>
              <span class="meta ellipsis" style="max-width:45%">{{ item.message }}</span>
            </div>
          </div>
          <div class="note" style="margin-top:12px">表格已就地更新，可继续补全或直接下一步。</div>
        </mh-result>

        <div class="mask" v-if="editing" @click.self="closeEdit">
          <div class="drawer">
            <header>
              <h3>编辑标签</h3>
              <span class="pill" v-if="editing && editing.loading">读取中</span>
              <button class="btn sm" @click="closeEdit" :disabled="drawerBusy">关闭</button>
            </header>
            <div class="body">
              <div class="note mono" style="word-break:break-all">{{ editing.name }}</div>
              <div class="note" style="margin-top:8px">只改标签与歌词，<b>不改文件名</b>。</div>
              <div class="note err" v-if="drawerError" style="margin-top:8px">{{ drawerError }}</div>
              <div class="note" v-if="drawerNote" style="margin-top:8px">{{ drawerNote }}</div>

              <div class="consistency" v-if="editing.consistency">
                <span
                  v-for="it in editing.consistency.items"
                  :key="it.field"
                  class="cn-item"
                  :class="stateClass(it.state)"
                  :title="it.reason || (it.file + ' ↔ ' + it.tag)"
                >
                  {{ it.label }} {{ stateMark(it.state) }}
                  <span class="cn-value">{{ it.state === 'skipped' ? it.reason : (it.file + ' ↔ ' + it.tag) }}</span>
                </span>
              </div>

              <div class="form-grid">
                <label v-for="def in fieldDefs" :key="def.key">
                  <span>{{ def.label }}</span>
                  <input v-model="form[def.key]" :disabled="drawerBusy" :placeholder="'留空表示不改'">
                </label>
              </div>

              <label class="lyric-box">
                <span>歌词（同名 .lrc）<em class="dim">留空表示不写；填写则覆盖</em></span>
                <textarea v-model="lyric" rows="9" :disabled="drawerBusy"
                          placeholder="粘贴 LRC 歌词…"></textarea>
              </label>
            </div>
            <footer>
              <button class="btn ghost" @click="fetchOnline" :disabled="drawerBusy">
                <span v-if="drawerBusy" class="spin"></span> 在线取标签
              </button>
              <button class="btn ghost" @click="playTrack(editing.path, editing.name)"
                      :disabled="!editing || !editing.path" title="试听并对照歌词校准时间轴">
                试听并校准歌词
              </button>
              <span class="spacer"></span>
              <button class="btn ghost" @click="closeEdit" :disabled="drawerBusy">取消</button>
              <button class="btn primary" @click="saveEdit" :disabled="drawerBusy || editing.loading">保存</button>
            </footer>
          </div>
        </div>
      </div>`,
  };
})(window.MH);
