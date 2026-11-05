/* 第 7 步：工作区自检（只读，重点展示「文件名 ↔ 标签」逐项比对） */
(function (MH) {
  'use strict';

  MH.StepSelfCheck = {
    props: { state: Object },
    emits: ['prev', 'next'],
    data: function () {
      return {
        loading: false,
        error: '',
        data: null,
        expanded: {},
        onlyProblems: false,
      };
    },
    computed: {
      items: function () { return (this.data && this.data.items) || []; },
      total: function () { return this.items.length; },
      sortedItems: function () {
        const rows = this.items.slice();
        if (this.onlyProblems) {
          return rows.filter((item) => item.problems.length);
        }
        rows.sort((a, b) => {
          const diff = b.problems.length - a.problems.length;
          if (diff) return diff;
          return String(a.name).localeCompare(String(b.name), 'zh-Hans-CN', { numeric: true });
        });
        return rows;
      },
      stats: function () {
        const base = this.data || {};
        const counts = base.counts || {};
        return {
          total: base.total || 0,
          ready: base.ready || 0,
          mismatch: base.mismatch || 0,
          notCanonical: base.not_canonical || 0,
          noLrc: base.no_lrc || 0,
          orphan: base.orphan_lrc || 0,
          dupGroups: base.dup_groups || 0,
          tags: counts['标签不完整'] || 0,
        };
      },
      groups: function () {
        const findings = (this.data && this.data.findings) || [];
        const map = {};
        findings.forEach((item) => {
          if (!map[item.kind]) map[item.kind] = { kind: item.kind, items: [] };
          map[item.kind].items.push(item);
        });
        return Object.keys(map)
          .map((kind) => map[kind])
          .sort((a, b) => b.items.length - a.items.length);
      },
    },
    mounted: function () { this.load(); },
    methods: {
      async load() {
        this.loading = true;
        this.error = '';
        try {
          this.data = await MH.api.get('/api/selfcheck/preview');
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      toggle: function (kind) {
        this.expanded = Object.assign({}, this.expanded, { [kind]: !this.expanded[kind] });
      },
      stateClass: function (state) {
        return state === 'ok' ? 'ok' : (state === 'mismatch' ? 'err' : 'dim');
      },
      stateMark: function (state) {
        if (state === 'ok') return '✓';
        return state === 'mismatch' ? '✗' : '—';
      },
      chipTitle: function (item) {
        if (item.state === 'skipped') return item.reason;
        return item.file + ' ↔ ' + item.tag;
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 7 步 · 工作区自检</h2>
          <span class="sub">只出报告，不动任何文件；重点核对「文件名 ↔ 标签」是否一致</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load" :disabled="loading">重新检查</button>
        </div>

        <div class="stats" style="margin-top:14px">
          <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">工作区文件</div></div>
          <div class="stat"><div class="n" :class="stats.ready === stats.total ? 'ok' : ''">{{ stats.ready }}</div><div class="l">可入库</div></div>
          <div class="stat"><div class="n" :class="stats.mismatch ? 'err' : ''">{{ stats.mismatch }}</div><div class="l">文件名与标签矛盾</div></div>
          <div class="stat"><div class="n" :class="stats.tags ? 'warn' : ''">{{ stats.tags }}</div><div class="l">标签不完整</div></div>
          <div class="stat"><div class="n" :class="stats.notCanonical ? 'warn' : ''">{{ stats.notCanonical }}</div><div class="l">文件名不规范</div></div>
          <div class="stat"><div class="n" :class="stats.noLrc ? 'warn' : ''">{{ stats.noLrc }}</div><div class="l">缺歌词</div></div>
          <div class="stat"><div class="n" :class="stats.orphan ? 'warn' : ''">{{ stats.orphan }}</div><div class="l">孤立 .lrc</div></div>
          <div class="stat"><div class="n" :class="stats.dupGroups ? 'err' : ''">{{ stats.dupGroups }}</div><div class="l">工作区内重复</div></div>
        </div>

        <div class="note err" v-if="error" style="margin-top:12px">{{ error }}</div>

        <div class="card" style="margin-top:14px">
          <h3>文件名 ↔ 标签 逐项比对</h3>
          <div class="note" style="margin-bottom:10px">
            歌手按 token 比对（<span class="mono">周杰伦</span> 与 <span class="mono">周杰伦 (Jay Chou)</span> 视为一致）；
            歌名归一化后允许一方包含另一方；群星/未知歌手与文件名没有「歌手 - 歌名」结构的不参与比对（显示 —）。
          </div>
          <div class="checks" style="margin-bottom:10px">
            <label><input type="checkbox" v-model="onlyProblems"> 只看有问题的文件</label>
            <span class="spacer" style="flex:1"></span>
            <span class="pill info">{{ sortedItems.length }} 行</span>
          </div>
          <div class="tbl-wrap" style="max-height:46vh">
            <table class="grid">
              <thead>
                <tr>
                  <th>文件名</th>
                  <th>文件名解析</th>
                  <th>标签</th>
                  <th style="width:130px">一致性</th>
                  <th>问题</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in sortedItems" :key="item.path">
                  <td class="fname" :title="item.path">{{ item.name }}</td>
                  <td class="dim" style="font-size:12px">
                    {{ item.consistency.file.artist || '（无歌手）' }} / {{ item.consistency.file.title || '—' }}
                  </td>
                  <td class="dim" style="font-size:12px">
                    {{ item.artist || '（无歌手）' }} / {{ item.title || '—' }}
                  </td>
                  <td>
                    <span v-for="it in item.consistency.items" :key="it.field"
                          class="cn-chip" :class="stateClass(it.state)" :title="chipTitle(it)">
                      {{ it.label }} {{ stateMark(it.state) }}
                    </span>
                  </td>
                  <td style="font-size:12px">
                    <span v-if="!item.problems.length" class="ok">可入库</span>
                    <span v-else class="warn">{{ item.problems.join('；') }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="empty" v-if="loading">扫描工作区…</div>
            <div class="empty" v-else-if="!sortedItems.length">
              {{ onlyProblems ? '没有有问题的文件' : '工作区没有文件（先做第 3、4 步）' }}
            </div>
          </div>
        </div>

        <div class="card" style="margin-top:16px" v-if="groups.length">
          <h3>其他检查项 <span class="badge">点击展开明细</span></h3>
          <div v-for="group in groups" :key="group.kind" class="group-block">
            <div class="group-head clickable" @click="toggle(group.kind)">
              <span class="name">{{ group.kind }}</span>
              <span class="meta">{{ group.items.length }}</span>
              <span class="dim">{{ expanded[group.kind] ? '收起' : '展开' }}</span>
            </div>
            <div class="list-scroll" v-if="expanded[group.kind]" style="max-height:26vh">
              <div class="row-item" v-for="item in group.items" :key="item.kind + item.path">
                <span class="name" :title="item.path">{{ item.name }}</span>
                <span class="meta ellipsis" style="max-width:60%">{{ item.detail }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="note" style="margin-top:16px">
          自检只报告，不改文件。标签问题回到第 5 步改；文件名不规范与可入库判定由第 8 步归档时统一处理
          （未达标的进待确认目录）。
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="loading">← 上一步</button>
          <span class="hint">有矛盾的先回第 5 步改标签，比归档后再修省事</span>
          <span class="spacer"></span>
          <button class="btn primary" @click="$emit('next')" :disabled="loading">下一步 →</button>
        </div>
      </div>`,
  };
})(window.MH);
