/* 第 2 步：选择操作类型（含库初始化状态与日期范围） */
(function (MH) {
  'use strict';

  MH.StepActions = {
    props: { state: Object },
    emits: ['prev', 'go'],
    data: function () {
      return {
        selfCheck: false,
        doInit: false,
        mode: 'single',
        from: this.state.range.from,
        to: this.state.range.to,
        showPicker: false,
        showDbConfirm: false,
        dbRunning: false,
      };
    },
    computed: {
      library: function () { return this.state.library || {}; },
      initialized: function () { return !!this.library.initialized; },
      db: function () { return this.library.db || {}; },
      months: function () { return this.state.months || []; },
      nextLabel: function () {
        if (this.doInit) return '去初始化 →';
        if (this.selfCheck) return '去自检 →';
        return '去拷贝文件 →';
      },
      blocked: function () { return !this.initialized && !this.doInit; },
      rangeText: function () {
        if (this.mode === 'single') return MH.fmt.month(this.from);
        return MH.fmt.month(this.from) + ' ~ ' + MH.fmt.month(this.to);
      },
    },
    watch: {
      initialized: {
        handler: function (value) { if (!value) this.doInit = true; },
        immediate: true,
      },
      selfCheck: function (value) { if (value) this.doInit = false; },
      doInit: function (value) { if (value) this.selfCheck = false; },
      'state.range': {
        handler: function (value) {
          if (!value) return;
          this.mode = value.mode;
          this.from = value.from;
          this.to = value.to;
        },
        deep: true,
      },
    },
    methods: {
      monthLabel: function (value) { return MH.fmt.month(value); },
      selectInit: function () {
        if (!this.initialized) { this.doInit = true; this.selfCheck = false; }
      },
      selectCheck: function () {
        if (!this.initialized) return;
        this.selfCheck = !this.selfCheck;
        if (this.selfCheck) this.doInit = false;
      },
      normalizeRange: function () {
        if (this.mode === 'range' && this.from && this.to && this.from > this.to) {
          const tmp = this.from;
          this.from = this.to;
          this.to = tmp;
        }
      },
      next: function () {
        this.normalizeRange();
        this.$emit('go', {
          mode: this.doInit ? 'init' : (this.selfCheck ? 'check' : 'copy'),
          range: {
            mode: this.mode,
            from: this.from,
            to: this.mode === 'range' ? this.to : this.from,
          },
        });
      },
      async rebuildDb() {
        this.dbRunning = true;
        try {
          const res = await MH.api.post('/api/tasks', { kind: 'init', opts: { make_db: true } });
          this.message('已开始建声纹库，完成后刷新状态');
          this.pollDb(res.task_id);
        } catch (err) {
          this.message(err.message, 'err');
          this.dbRunning = false;
        }
      },
      pollDb(id) {
        setTimeout(async () => {
          try {
            const task = await MH.api.get('/api/tasks/' + id);
            if (task.status === 'running' || task.status === 'queued') {
              this.pollDb(id);
            } else {
              this.dbRunning = false;
              this.message(task.status === 'done' ? '声纹库已更新' : '建库失败：' + (task.error || ''),
                task.status === 'done' ? '' : 'err');
              this.$emit('refresh');
            }
          } catch (err) {
            this.dbRunning = false;
            this.message(err.message, 'err');
          }
        }, 600);
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 2 步 · 选择操作</h2>
          <span class="sub">先确认库是否已初始化，再决定这一步做什么</span>
          <span class="spacer"></span>
          <button class="btn sm" @click="$emit('refresh')">刷新状态</button>
        </div>

        <!-- 库状态 -->
        <div class="card" style="margin-top:14px">
          <h3>
            库目录状态
            <span class="pill" :class="initialized ? 'ok' : 'warn'">{{ initialized ? '已初始化' : '未初始化' }}</span>
            <span class="badge mono">{{ library.dir }}</span>
          </h3>

          <div class="stats">
            <div class="stat">
              <div class="n">{{ library.audio_count <= 20000 ? library.audio_count : '20000+' }}</div>
              <div class="l">音频文件{{ library.count_truncated ? '（已达统计上限）' : '' }}</div>
            </div>
            <div class="stat">
              <div class="n">{{ library.year_count || 0 }}</div>
              <div class="l">年份目录</div>
            </div>
            <div class="stat">
              <div class="n" :class="db.exists ? '' : 'warn'">{{ db.exists ? '有' : '无' }}</div>
              <div class="l">声纹库</div>
            </div>
            <div class="stat">
              <div class="n" :class="library.has_year_layout ? '' : 'warn'">{{ library.has_year_layout ? '有' : '无' }}</div>
              <div class="l">年代/年份结构</div>
            </div>
          </div>

          <div class="note warn" style="margin-top:12px" v-for="p in library.problems" :key="p">{{ p }}</div>
          <div class="note" style="margin-top:10px" v-for="s in library.suggestions" :key="s">{{ s }}</div>
          <div class="note" style="margin-top:10px" v-if="!db.exists">
            缺少声纹库不会挡住流程，但「归档入库」前的重复判断需要它。
            <button class="btn link" @click="rebuildDb" :disabled="dbRunning">
              {{ dbRunning ? '正在建库…' : '现在补建 →' }}
            </button>
          </div>
        </div>

        <!-- 选项 -->
        <div class="card" style="margin-top:16px">
          <h3>这一步做什么</h3>

          <div class="option" :class="{ disabled: initialized || selfCheck, active: doInit }"
               @click="selectInit">
            <div class="mark">{{ doInit ? '✓' : '' }}</div>
            <div class="body">
              <div class="t">1 · 初始化库目录</div>
              <div class="d">
                建目录结构 + 建声纹库，幂等且不动任何文件。
                <span class="warn" v-if="initialized">库已初始化，此项不可用。</span>
                <span class="warn" v-else>库未初始化，必须先做这一步，其余操作暂不可用。</span>
              </div>
            </div>
          </div>

          <div class="option" :class="{ disabled: !initialized, active: selfCheck }" @click="selectCheck">
            <div class="mark">{{ selfCheck ? '✓' : '' }}</div>
            <div class="body">
              <div class="t">2 · 只做库目录自检</div>
              <div class="d">
                检查文件名 / 标签 / 重复 / 歌词，只出报告。
                这是排它选项：勾上后初始化与日期范围都不可用，也不会进入后续步骤。
                <span class="warn" v-if="!initialized">库未初始化，不能自检。</span>
              </div>
            </div>
          </div>

          <div class="option" :class="{ disabled: !initialized || selfCheck, active: (!doInit && !selfCheck && initialized) }"
               @click="initialized && !selfCheck && (doInit = false)">
            <div class="mark">{{ (!doInit && !selfCheck && initialized) ? '✓' : '' }}</div>
            <div class="body">
              <div class="t">3 · 走完整流程（拷贝 → 解密 → 标签歌词 → 归档）</div>
              <div class="d">按下面的月份范围挑选要处理的下载文件。</div>
            </div>
          </div>
        </div>

        <!-- 日期 -->
        <div class="card" style="margin-top:16px" :class="{ muted: !initialized || selfCheck }">
          <h3>
            处理哪几个月
            <span class="badge">按月筛选，默认当月</span>
          </h3>
          <div class="range">
            <div class="seg">
              <button :class="{ on: mode === 'single' }" @click="mode = 'single'"
                      :disabled="!initialized || selfCheck">单个</button>
              <button :class="{ on: mode === 'range' }" @click="mode = 'range'"
                      :disabled="!initialized || selfCheck">范围</button>
            </div>
            <select v-model="from" :disabled="!initialized || selfCheck" @change="normalizeRange">
              <option v-for="m in months" :key="m" :value="m">{{ monthLabel(m) }}</option>
            </select>
            <template v-if="mode === 'range'">
              <span class="dash">~</span>
              <select v-model="to" :disabled="!initialized || selfCheck" @change="normalizeRange">
                <option v-for="m in months" :key="m" :value="m">{{ monthLabel(m) }}</option>
              </select>
            </template>
            <span class="pill info">{{ rangeText }}</span>
          </div>
          <div class="note" style="margin-top:12px">
            月份按文件修改时间判定。自检不使用月份范围（它检查整个库）。
          </div>
        </div>

        <div class="footbar">
          <button class="btn ghost" @click="$emit('prev')">← 上一步</button>
          <span class="hint" v-if="blocked">库未初始化，请先选择「初始化库目录」</span>
          <span class="spacer"></span>
          <button class="btn primary" @click="next" :disabled="blocked">{{ nextLabel }}</button>
        </div>
      </div>`,
  };
})(window.MH);
