/* 第 1 步：目录设置 */
(function (MH) {
  'use strict';

  MH.StepDirs = {
    props: { state: Object },
    emits: ['next', 'saved'],
    data: function () {
      return {
        form: {},
        problems: [],
        saving: false,
        picking: '',
        showPicker: false,
        dirty: false,
      };
    },
    computed: {
      items: function () { return this.state.dirs.items || []; },
      fields: function () { return this.state.dirs.fields || []; },
      iniPath: function () { return this.state.iniPath || ''; },
      ready: function () { return this.problems.length === 0; },
    },
    watch: {
      'state.dirs.items': {
        handler: function (items) {
          if (!items || this.dirty) return;
          const form = {};
          items.forEach((item) => { form[item.key] = item.value || ''; });
          this.form = form;
        },
        immediate: true,
        deep: true,
      },
    },
    methods: {
      meta: function (key) {
        return this.items.find((item) => item.key === key) || {};
      },
      onChange: function () { this.dirty = true; this.problems = []; },
      inherited: function (key) {
        const info = this.meta(key);
        return !!info.inherited;
      },
      pick: function (key) {
        this.picking = key;
        this.showPicker = true;
      },
      onPicked: function (path) {
        this.form[this.picking] = path;
        this.showPicker = false;
        this.dirty = true;
        this.problems = [];
      },
      async createDir(key) {
        const path = (this.form[key] || '').trim();
        if (!path) return;
        try {
          await MH.api.post('/api/fs/mkdir', { path: path });
          this.problems = [];
          this.dirty = true;
          await this.save(true);
        } catch (err) {
          this.problems = [err.message];
        }
      },
      suggestVip(key, parentKey) {
        const parent = (this.form[parentKey] || '').trim();
        if (!parent) return;
        this.form[key] = parent.replace(/[\\/]+$/, '') + '\\VipSOngsDownload';
        this.dirty = true;
      },
      async save(silent) {
        this.saving = true;
        this.problems = [];
        try {
          const res = await MH.api.post('/api/wizard/dirs', { values: this.form });
          this.dirty = false;
          this.$emit('saved', res);
          if (!silent) this.message('目录设置已保存到 ' + this.iniPath);
          return true;
        } catch (err) {
          const payload = err.payload || {};
          this.problems = payload.problems || [err.message];
          return false;
        } finally {
          this.saving = false;
        }
      },
      async next() {
        if (this.dirty || !this.ready) {
          const ok = await this.save(true);
          if (!ok) return;
        }
        this.$emit('next');
      },
    },
    template: `
      <div>
        <div class="title-row">
          <h2>第 1 步 · 设置目录</h2>
          <span class="sub">这些值会写入 config.ini，下次打开自动带出</span>
          <span class="spacer"></span>
          <button class="btn" @click="save(false)" :disabled="saving">
            <span v-if="saving" class="spin"></span> 保存
          </button>
        </div>

        <div class="card" style="margin-top:14px">
          <h3>目录位置 <span class="badge">共 {{ fields.length }} 项 · 双击「选择」可浏览</span></h3>

          <div class="field" v-for="f in fields" :key="f.key">
            <div class="label">
              {{ f.label }}
              <span class="pill info" v-if="meta(f.key).source === 'env'" title="环境变量优先级高于 config.ini">环境变量</span>
              <span class="pill" v-else-if="inherited(f.key)">跟随上级目录</span>
              <span class="desc">{{ f.desc }}</span>
            </div>
            <div class="control">
              <input class="path" type="text" v-model="form[f.key]" @input="onChange"
                     :placeholder="meta(f.key).vip_default || '绝对路径，如 D:\\\\music'" spellcheck="false">
              <button class="btn sm" @click="pick(f.key)">选择</button>
              <button class="btn sm" v-if="f.key === 'qq_vip_dir' || f.key === 'netease_vip_dir'"
                      @click="suggestVip(f.key, f.key === 'qq_vip_dir' ? 'qq_dir' : 'netease_dir')"
                      title="取「下载目录/VipSOngsDownload」">按默认</button>
              <button class="btn sm" v-if="!meta(f.key).exists" @click="createDir(f.key)">创建</button>
              <span class="dir-state">
                <span class="pill ok" v-if="meta(f.key).exists && meta(f.key).is_dir">存在</span>
                <span class="pill err" v-else-if="meta(f.key).exists">不是目录</span>
                <span class="pill warn" v-else>不存在</span>
              </span>
            </div>
          </div>

          <div class="note" style="margin-top:12px" v-if="meta('incomplete_dir')">
            待确认目录用来暂存「未达入库标准」的文件：人工补全后重新走归档，确认没救的再手动清理。
            本工具不会真正删除任何文件，删除一律移入 <span class="mono">log/_trash</span>。
          </div>
          <div class="note err" style="margin-top:10px" v-for="p in problems" :key="p">{{ p }}</div>
          <div class="note" style="margin-top:10px">
            配置文件：<span class="mono">{{ iniPath }}</span>
            <br>被环境变量覆盖的项，保存后也不会改变实际生效值（优先用环境变量）。
          </div>
        </div>

        <div class="footbar">
          <span class="hint">下一步：确认库是否已初始化，并选择本次要做什么</span>
          <span class="spacer"></span>
          <button class="btn primary" @click="next" :disabled="saving || problems.length">下一步 →</button>
        </div>

        <mh-dir-picker :show="showPicker" :start="form[picking]"
                       @close="showPicker = false" @pick="onPicked"></mh-dir-picker>
      </div>`,
  };
})(window.MH);
