/* 第 5 步：标签与歌词补全 */
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
        opts: { fingerprint: true, cover: true, lyrics: true },
        showResult: false,
        result: null,
        merged: {},
      };
    },
    computed: {
      items: function () { return (this.data && this.data.items) || []; },
      total: function () { return this.items.length; },
      selectedPaths: function () {
        return Object.keys(this.selected).filter((path) => this.selected[path]);
      },
      selectedCount: function () { return this.selectedPaths.length; },
      stats: function () {
        const base = this.data || {};
        return {
          total: base.total || 0,
          ready: base.ready || 0,
          tags: base.missing_tags || 0,
          lrc: base.missing_lrc || 0,
          cover: base.missing_cover || 0,
        };
      },
      tone: function () {
        if (!this.result) return 'info';
        return this.result.failed ? 'warn' : 'info';
      },
    },
    mounted: function () { this.load(); },
    methods: {
      async load() {
        this.loading = true;
        this.error = '';
        try {
          this.data = await MH.api.get('/api/tags/preview');
          this.merged = {};
          this.selected = {};
          this.items.forEach((item) => {
            if (!item.ready || !item.has_lrc || !item.has_cover) this.selected[item.path] = true;
          });
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
      async run() {
        const paths = this.selectedPaths;
        if (!paths.length) {
          this.message('先选几个文件', 'err');
          return;
        }
        this.result = null;
        const id = await this.submitTask('tags', {
          paths: paths,
          with_fingerprint: this.opts.fingerprint,
          write_cover: this.opts.cover,
          write_lyrics: this.opts.lyrics,
        });
        if (id) this.message('开始补全 ' + paths.length + ' 个文件…');
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
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 5 步 · 标签与歌词补全</h2>
          <span class="sub">工作区顶层文件 · 只填空缺，不覆盖已有值</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load" :disabled="loading || taskRunning">刷新列表</button>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">工作区文件</div></div>
          <div class="stat"><div class="n">{{ stats.ready }}</div><div class="l">已可入库</div></div>
          <div class="stat"><div class="n" :class="stats.tags ? 'warn' : ''">{{ stats.tags }}</div><div class="l">缺核心标签</div></div>
          <div class="stat"><div class="n" :class="stats.lrc ? 'warn' : ''">{{ stats.lrc }}</div><div class="l">缺歌词</div></div>
          <div class="stat"><div class="n" :class="stats.cover ? 'warn' : ''">{{ stats.cover }}</div><div class="l">缺封面</div></div>
        </div>

        <div class="card" style="margin-top:14px;padding:12px 16px">
          <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
            <div class="seg">
              <button @click="selectFilter(i => true)">全选</button>
              <button @click="selectAll(false)">全不选</button>
              <button @click="selectFilter(i => i.problems.length)">仅缺标签</button>
              <button @click="selectFilter(i => !i.has_lrc)">仅缺歌词</button>
              <button @click="selectFilter(i => !i.has_cover)">仅缺封面</button>
            </div>
            <div class="checks">
              <label><input type="checkbox" v-model="opts.fingerprint"> 声纹识别（MusicBrainz，较慢但更准）</label>
              <label><input type="checkbox" v-model="opts.cover"> 写封面</label>
              <label><input type="checkbox" v-model="opts.lyrics"> 写歌词</label>
            </div>
            <span class="spacer" style="flex:1"></span>
            <span class="pill info">已选 {{ selectedCount }} / {{ total }}</span>
          </div>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>

        <div class="tbl-wrap" style="margin-top:14px">
          <table class="grid">
            <thead>
              <tr>
                <th style="width:34px"></th>
                <th>文件名</th>
                <th>艺术家</th>
                <th>歌名</th>
                <th>专辑</th>
                <th style="width:64px">年份</th>
                <th class="num" style="width:64px">时长</th>
                <th style="width:46px">封面</th>
                <th style="width:46px">歌词</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.path" :class="{ sel: selected[item.path] }">
                <td><input type="checkbox" :checked="!!selected[item.path]" @change="toggle(item.path)"></td>
                <td class="fname" :title="item.path">{{ item.name }}</td>
                <td :class="fieldOf(item, 'artist')">{{ item.artist || '—' }}</td>
                <td :class="fieldOf(item, 'title')">{{ item.title || '—' }}</td>
                <td :class="fieldOf(item, 'album')">{{ item.album || '—' }}</td>
                <td :class="fieldOf(item, 'year')">{{ item.year || '—' }}</td>
                <td class="num">{{ $fmt.duration(item.duration) }}</td>
                <td><span :class="item.has_cover ? 'ok' : 'dim'">{{ item.has_cover ? '有' : '无' }}</span></td>
                <td><span :class="item.has_lrc ? 'ok' : 'dim'">{{ item.has_lrc ? '有' : '无' }}</span></td>
                <td>
                  <span :class="rowState(item).cls" style="font-size:12px">{{ rowState(item).text }}</span>
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
      </div>`,
  };
})(window.MH);
