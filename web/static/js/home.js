/* 播放器首页：音乐库曲目列表 + 复用八步页的全局试听播放器组件。
   首页只做「选歌 + 播放」，不碰任何文件；播放/歌词/封面/解码全部走 player.js
   与 /api/media/* 那套只读旁路。跳转八步向导用顶部链接（/wizard）。 */
(function (MH) {
  'use strict';

  const Home = {
    data: function () {
      return {
        loading: true,
        error: '',
        dir: '',
        tracks: [],
        total: 0,
        truncated: false,
        query: '',
        filter: '',
        toast: '',
        toastTimer: null,
        currentPath: '',
      };
    },
    computed: {
      shown: function () {
        const needle = this.filter.trim().toLowerCase();
        if (!needle) return this.tracks;
        return this.tracks.filter((t) => [t.title, t.artist, t.name].some(
          (value) => String(value || '').toLowerCase().indexOf(needle) >= 0));
      },
    },
    mounted: function () {
      this._playHandler = (event) => {
        const detail = event.detail || {};
        this.currentPath = detail.path || '';
      };
      this._toastHandler = (event) => {
        const detail = event.detail || {};
        this.message(detail.text);
      };
      window.addEventListener('mh-play', this._playHandler);
      window.addEventListener('mh-home-toast', this._toastHandler);
      this.load();
    },
    beforeUnmount: function () {
      window.removeEventListener('mh-play', this._playHandler);
      window.removeEventListener('mh-home-toast', this._toastHandler);
      clearTimeout(this.toastTimer);
    },
    methods: {
      async load() {
        this.loading = true;
        this.error = '';
        try {
          const data = await MH.api.get('/api/library/tracks', { q: this.query });
          this.dir = data.dir || '';
          this.tracks = (data.tracks || []).map((t) => Object.assign({}, t, {
            label: t.artist ? (t.artist + ' - ' + t.title) : (t.title || t.name),
          }));
          this.total = data.total || 0;
          this.truncated = !!data.truncated;
        } catch (err) {
          this.error = err.message;
        } finally {
          this.loading = false;
        }
      },
      /* 传给播放器的队列是所有展示中的曲目，支持上一曲/下一曲 */
      queue() {
        return this.shown.map((t) => ({ path: t.path, name: t.label }));
      },
      play(track) {
        if (!track || !track.path) return;
        this.currentPath = track.path;
        window.dispatchEvent(new CustomEvent('mh-play', {
          detail: { path: track.path, name: track.label, queue: this.queue() },
        }));
      },
      isCurrent: function (track) {
        return !!this.currentPath && this.currentPath === track.path;
      },
      message: function (text) {
        if (!text) return;
        this.toast = String(text);
        clearTimeout(this.toastTimer);
        this.toastTimer = setTimeout(() => { this.toast = ''; }, 2600);
      },
    },
    template: `
      <div class="shell">
        <header class="topbar">
          <div class="brand">
            <h1>music_helper</h1>
            <span class="ver">音乐库播放器</span>
          </div>
          <nav class="home-nav">
            <span class="home-tag">正在播放：音乐库（最终库）</span>
          </nav>
          <div class="actions">
            <a class="btn primary" href="/wizard">八步归档整理 →</a>
          </div>
        </header>

        <main class="main home-main">
          <div class="home-head">
            <div>
              <h2>我的音乐库</h2>
              <div class="dim mono home-dir" :title="dir">{{ dir || '（未设置音乐库目录）' }}</div>
            </div>
            <button class="btn sm" @click="load" :disabled="loading">刷新列表</button>
          </div>

          <div class="home-tools">
            <input class="input" type="search" v-model="filter" placeholder="筛选已加载的曲目（歌名 / 歌手）">
            <input class="input" type="search" v-model="query" placeholder="按关键字重新扫描音乐库，回车确认" @keyup.enter="load">
            <span class="dim home-count">{{ shown.length }} / {{ total }} 首</span>
          </div>

          <div class="note err" v-if="error">{{ error }}</div>
          <div class="empty" v-else-if="loading">正在读取音乐库…</div>
          <div class="note" v-else-if="!tracks.length">
            音乐库里还没有曲目，或目录未设置。到「八步归档整理」里配置目录、走一遍归档流程后再回来播放。
          </div>

          <div class="home-list" v-else>
            <div class="track" v-for="(t, i) in shown" :key="t.path"
                 :class="{ current: isCurrent(t) }" @click="play(t)">
              <span class="track-no mono">{{ String(i + 1).padStart(3, '0') }}</span>
              <span class="track-play">{{ isCurrent(t) ? '♪' : '▶' }}</span>
              <span class="track-main">
                <span class="track-title">{{ t.title }}</span>
                <span class="track-sub dim">{{ t.artist || '未知歌手' }} · {{ $fmt.size(t.size) }}</span>
              </span>
              <span class="track-flags">
                <span class="pill" v-if="t.has_lrc">歌词</span>
              </span>
              <span class="track-ext mono dim">{{ t.ext }}</span>
            </div>
            <div class="note dim" v-if="truncated">仅显示前 {{ tracks.length }} 首（库较大），用上方关键字缩小范围。</div>
          </div>
        </main>

        <mh-player></mh-player>
        <div class="toast" v-if="toast">{{ toast }}</div>
      </div>`,
  };

  const app = Vue.createApp(Home);
  app.mixin({
    methods: {
      message: function (text) {
        if (!text) return;
        window.dispatchEvent(new CustomEvent('mh-home-toast', { detail: { text: String(text) } }));
      },
    },
  });
  app.component('mh-player', MH.Player);
  app.config.globalProperties.$fmt = MH.fmt;
  app.mount('#app');
})(window.MH);
