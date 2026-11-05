/* 第 4 步：直接解密（VIP 目录 → 工作区，不经过暂存区） */
(function (MH) {
  'use strict';

  MH.StepDecrypt = {
    mixins: [MH.taskMixin],
    props: { state: Object },
    emits: ['prev', 'next'],
    data: function () {
      return {
        loading: false,
        error: '',
        preview: null,
        showResult: false,
        result: null,
        showSkip: false,
      };
    },
    computed: {
      groups: function () { return (this.preview && this.preview.groups) || []; },
      workspace: function () { return (this.preview && this.preview.workspace) || { files: [] }; },
      platform: function () { return (this.preview && this.preview.platform) || {}; },
      total: function () { return (this.preview && this.preview.total) || 0; },
      bytes: function () { return (this.preview && this.preview.bytes) || 0; },
      rangeLabel: function () {
        const r = this.state.range || {};
        if (r.mode === 'range') return MH.fmt.month(r.from) + ' ~ ' + MH.fmt.month(r.to);
        return MH.fmt.month(r.from);
      },
      tone: function () {
        if (!this.result) return 'info';
        const bad = (this.result.items || []).filter((i) => !i.ok).length;
        if (!bad) return 'info';
        return this.result.produced ? 'warn' : 'err';
      },
    },
    mounted: function () { this.load(); },
    methods: {
      params: function () {
        const r = this.state.range || {};
        if (r.mode === 'range') return { month_from: r.from, month_to: r.to };
        return { month_from: r.from, month_to: r.from };
      },
      async load() {
        this.loading = true;
        this.error = '';
        try {
          this.preview = await MH.api.get('/api/decrypt/preview', this.params());
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      async run() {
        this.result = null;
        const p = this.params();
        const id = await this.submitTask('decrypt-direct', {
          paths: [], month_from: p.month_from, month_to: p.month_to,
        });
        if (id) this.message('开始解密 ' + this.total + ' 个文件…');
      },
      onTaskFinished(task) {
        this.result = task.status === 'error'
          ? { items: [{ label: '任务', ok: false, message: task.error }], produced: 0 }
          : (task.result || {});
        this.showResult = true;
        if (this.result.produced) {
          this.$emit('mark', 'decrypt');
          this.load();
        }
      },
      closeResult() {
        this.showResult = false;
        this.load();
      },
      next() {
        if (!this.state.decryptDone && this.total) {
          this.showSkip = true;
          return;
        }
        this.$emit('next');
      },
      confirmSkip() { this.showSkip = false; this.$emit('next'); },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 4 步 · 解密加密文件</h2>
          <span class="sub">VIP 目录里的 .ncm / .mflac / .mgg 直接解密到工作区 · 月份 {{ rangeLabel }}</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="load" :disabled="loading || taskRunning">刷新列表</button>
        </div>

        <div class="note" style="margin-top:12px">
          解密直接从 VIP 下载目录读到工作区，<b>不再把加密文件搬进暂存区</b>：
          少一次复制、跨盘时也不会白搬一趟。加密原文件默认留在 VIP 目录原地
          （<span class="mono">encrypted_source_mode = return</span>）。
        </div>
        <div class="note warn" style="margin-top:8px" v-if="platform.qq">
          QQ 通道：{{ platform.qq.backend }}
        </div>
        <div class="note err" v-if="error" style="margin-top:8px">{{ error }}</div>

        <div class="dual" style="margin-top:14px">
          <div class="pane">
            <header>
              <span>待解密</span>
              <span class="path">按 VIP 目录分组</span>
              <span class="pill info">{{ total }} 个</span>
            </header>
            <div class="body">
              <div v-if="loading" class="empty">扫描中…</div>
              <template v-else>
                <div v-for="group in groups" :key="group.root">
                  <div class="group-head">
                    <span>{{ group.label }}</span>
                    <span class="path" :title="group.root">{{ group.root }}</span>
                    <span class="dim">{{ group.count }} 个 · {{ $fmt.size(group.bytes) }}</span>
                  </div>
                  <div class="row-item" v-for="file in group.files" :key="file.path">
                    <span class="name" :title="file.path">{{ file.name }}</span>
                    <span class="tag">{{ $fmt.month(file.month) }}</span>
                    <span class="meta">{{ $fmt.size(file.size) }}</span>
                    <span class="tag" v-if="file.existing" style="color:var(--warn)">工作区已有成品</span>
                  </div>
                  <div class="empty" v-if="group.missing" style="padding:14px">VIP 目录不存在：{{ group.root }}</div>
                </div>
                <div class="empty" v-if="!groups.length">没有待解密的文件</div>
              </template>
            </div>
            <footer>
              <span>{{ total }} 个文件</span>
              <span>{{ $fmt.size(bytes) }}</span>
            </footer>
          </div>

          <div class="pane">
            <header>
              <span>解密后</span>
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
            </footer>
          </div>
        </div>

        <div class="card" style="margin-top:16px" v-if="task">
          <h3>解密进度</h3>
          <mh-task-panel :task="task" :error="taskError"></mh-task-panel>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')" :disabled="taskRunning">← 上一步</button>
          <span class="spacer"></span>
          <button class="btn" @click="run" :disabled="taskRunning || !total">
            <span v-if="taskRunning" class="spin"></span> {{ taskRunning ? '解密中…' : '解密' }}
          </button>
          <button class="btn primary" @click="next" :disabled="taskRunning">下一步 →</button>
        </div>

        <mh-result :show="showResult" title="解密完成" :tone="tone" @close="closeResult">
          <div class="row-item" v-for="(item, i) in (result && result.items) || []" :key="i">
            <span class="pill" :class="item.ok ? 'ok' : 'err'">{{ item.ok ? '成功' : '失败' }}</span>
            <span class="name">{{ item.label }}</span>
            <span class="meta ellipsis" style="max-width:60%">
              加密 {{ item.encrypted || 0 }} / 产出 {{ item.produced || 0 }} · {{ item.message }}
            </span>
          </div>
          <div class="note" style="margin-top:12px" v-if="!result || !result.produced">
            没有任何产出。常见原因：客户端未登录（QQ）、文件其实是新版 qmc2（需要 mmkv + 密钥）、
            或该文件本身不是加密文件。详情见运行日志。
          </div>
          <div class="note" style="margin-top:8px">产物目录：<span class="mono">{{ (result && result.target_dir) || '' }}</span></div>
        </mh-result>

        <mh-confirm :show="showSkip" title="还没有解密文件" confirm-text="跳过解密，继续"
                    @close="showSkip = false" @confirm="confirmSkip">
          本次还没有执行解密。直接下一步将跳过解密，进入标签与歌词补全页面。
          <br>确认要跳过吗？
        </mh-confirm>
      </div>`,
  };
})(window.MH);
