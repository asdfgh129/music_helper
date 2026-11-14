/* 全局试听播放器：挂在 app.js 根组件模板里，切步骤不中断播放。
   只消费后端的结构化歌词（core.lyrics.parse_lrc），前端不再解析一遍 LRC。
   契约见 docs/media-player.md。 */
(function (MH) {
  'use strict';

  let audioEl = null;

  /* 返回第一个 > time 的下标；当前行 = 返回值 - 1 */
  function upperBound(lines, time) {
    let lo = 0;
    let hi = lines.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (lines[mid].time <= time) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  MH.Player = {
    name: 'MhPlayer',
    data: function () {
      return {
        visible: false,
        path: '',
        name: '',
        info: null,
        lyric: null,
        playing: false,
        busy: false,
        currentTime: 0,
        duration: 0,
        volume: 0.8,
        error: '',
        message: '',
        activeIndex: -1,
        showLyrics: true,
        following: true,
        offsetMs: 0,
      };
    },
    computed: {
      playable: function () { return !!(this.info && this.info.browser_playable); },
      lyricLines: function () { return (this.lyric && this.lyric.lines) || []; },
      hasTiming: function () { return !!(this.lyric && this.lyric.has_timing); },
      hasLyric: function () { return !!(this.lyric && (this.lyric.exists || this.lyric.plain)); },
    },
    mounted: function () {
      audioEl = new Audio();
      audioEl.preload = 'metadata';
      audioEl.addEventListener('timeupdate', this.onTimeUpdate);
      audioEl.addEventListener('loadedmetadata', this.onLoaded);
      audioEl.addEventListener('ended', this.onEnded);
      audioEl.addEventListener('error', this.onAudioError);
      audioEl.addEventListener('play', this.onPlayState);
      audioEl.addEventListener('pause', this.onPauseState);
      this._playHandler = (event) => {
        const detail = event.detail || {};
        this.play(detail.path, detail.name);
      };
      window.addEventListener('mh-play', this._playHandler);
    },
    beforeUnmount: function () {
      window.removeEventListener('mh-play', this._playHandler);
      if (audioEl) {
        audioEl.pause();
        audioEl.removeAttribute('src');
        audioEl.load();
      }
    },
    methods: {
      async play(path, name) {
        if (!path) return;
        if (audioEl) audioEl.pause();
        this.visible = true;
        this.path = path;
        this.name = name || MH.fmt.baseName(path);
        this.info = null;
        this.lyric = null;
        this.error = '';
        this.message = '';
        this.currentTime = 0;
        this.duration = 0;
        this.activeIndex = -1;
        this.following = true;
        this.playing = false;
        this.busy = true;
        try {
          const results = await Promise.all([
            MH.api.get('/api/media/info', { path: path }),
            MH.api.get('/api/media/lyric', { path: path }),
          ]);
          this.info = results[0];
          this.lyric = results[1];
          this.offsetMs = Number(this.lyric.offset || 0);
          this.duration = Number(this.info.duration || 0);
        } catch (err) {
          this.error = err.message;
          this.busy = false;
          return;
        }
        this.busy = false;
        if (!this.playable) {
          this.message = this.info.playable_reason || '浏览器无法解码此格式';
          return;
        }
        audioEl.src = '/api/media/stream?path=' + encodeURIComponent(path);
        audioEl.volume = this.volume;
        try {
          await audioEl.play();
        } catch (err) {
          this.message = '浏览器阻止了自动播放，点播放按钮继续（' + err.message + '）';
        }
      },
      toggle: function () {
        if (!this.playable || !audioEl) return;
        if (audioEl.paused) {
          if (!audioEl.getAttribute('src')) { this.play(this.path, this.name); return; }
          audioEl.play().catch((err) => { this.message = '播放失败：' + err.message; });
        } else {
          audioEl.pause();
        }
      },
      close: function () {
        if (audioEl) {
          audioEl.pause();
          audioEl.removeAttribute('src');
          audioEl.load();
        }
        this.visible = false;
        this.playing = false;
        this.info = null;
        this.lyric = null;
        this.path = '';
        this.currentTime = 0;
        this.duration = 0;
        this.activeIndex = -1;
        this.error = '';
        this.message = '';
      },
      onTimeUpdate: function () {
        this.currentTime = audioEl ? (audioEl.currentTime || 0) : 0;
        this.syncLyric();
      },
      onLoaded: function () {
        if (audioEl && Number.isFinite(audioEl.duration) && audioEl.duration > 0) {
          this.duration = audioEl.duration;
        }
      },
      onEnded: function () { this.playing = false; },
      onPlayState: function () { this.playing = true; },
      onPauseState: function () { this.playing = false; },
      onAudioError: function () {
        if (audioEl && audioEl.getAttribute('src')) {
          this.error = '浏览器无法解码该文件或读取失败（不是网络问题）';
        }
      },
      syncLyric: function () {
        if (!this.hasTiming || !this.showLyrics) return;
        const time = this.currentTime + this.offsetMs / 1000;
        const index = upperBound(this.lyricLines, time) - 1;
        if (index !== this.activeIndex) {
          this.activeIndex = index;
          this.$nextTick(this.scrollToActive);
        }
      },
      scrollToActive: function () {
        if (!this.following) return;
        const box = this.$refs.lyricBox;
        const line = box && box.querySelector('.player-line.active');
        if (line) box.scrollTop = line.offsetTop - box.clientHeight / 2 + line.clientHeight / 2;
      },
      onWheel: function () { this.following = false; },
      resumeFollow: function () {
        this.following = true;
        this.scrollToActive();
      },
      seekTo: function (line) {
        if (!audioEl || !this.playable) return;
        const time = Math.max(0, Number(line.time) - this.offsetMs / 1000);
        audioEl.currentTime = time;
        this.currentTime = time;
        this.following = true;
        this.syncLyric();
      },
      onSeek: function (event) {
        if (!audioEl || !this.playable) return;
        const time = Number(event.target.value);
        audioEl.currentTime = time;
        this.currentTime = time;
        this.syncLyric();
      },
      onVolume: function (event) {
        this.volume = Number(event.target.value);
        if (audioEl) audioEl.volume = this.volume;
      },
      async openExternal() {
        try {
          await MH.api.post('/api/media/open', { path: this.path });
          this.message = '已交给系统默认播放器';
        } catch (err) {
          this.error = err.message;
        }
      },
    },
    template: `
      <div class="player" v-if="visible">
        <div class="player-bar">
          <button class="player-toggle" @click="toggle" :disabled="!playable || busy"
                  :title="playable ? (playing ? '暂停' : '播放') : '浏览器无法解码此格式'">
            {{ playing ? '❚❚' : '▶' }}
          </button>
          <div class="player-meta">
            <div class="player-name" :title="path">{{ name }}</div>
            <div class="player-sub">
              <span v-if="busy">读取中…</span>
              <span v-else-if="info">
                {{ info.ext }} · {{ $fmt.size(info.size) }}
                <span v-if="info.has_cover"> · 有封面</span>
                <span v-if="info.has_lrc"> · 有歌词</span>
              </span>
            </div>
          </div>
          <input class="player-progress" type="range" min="0" :max="duration || 1" step="0.1"
                 :value="currentTime" :disabled="!playable" @input="onSeek" title="拖动进度">
          <span class="player-time mono">{{ $fmt.duration(currentTime) }} / {{ $fmt.duration(duration) }}</span>
          <input class="player-volume" type="range" min="0" max="1" step="0.05"
                 :value="volume" @input="onVolume" title="音量">
          <button class="btn sm" :class="{ primary: showLyrics }" @click="showLyrics = !showLyrics">歌词</button>
          <button class="btn sm ghost" @click="close">关闭</button>
        </div>

        <div class="player-alert err" v-if="error">{{ error }}</div>
        <div class="player-alert" v-if="message">
          {{ message }}
          <button class="btn link" v-if="!playable && path" @click="openExternal">用系统播放器打开</button>
        </div>

        <div class="player-lyrics-wrap" v-if="showLyrics">
          <div class="player-lyrics" ref="lyricBox" @wheel.passive="onWheel">
            <div class="player-lyrics-empty" v-if="!hasLyric">无歌词（同目录下没有同名 .lrc）</div>
            <div class="player-plain" v-else-if="!hasTiming">{{ lyric.plain }}</div>
            <template v-else>
              <div v-for="(line, i) in lyricLines" :key="i"
                   class="player-line" :class="{ active: i === activeIndex }"
                   @click="seekTo(line)">
                <div class="player-line-text">{{ line.text }}</div>
                <div class="player-line-trans" v-if="line.translation">{{ line.translation }}</div>
              </div>
            </template>
          </div>
          <div class="player-lyrics-foot">
            <span class="dim" v-if="hasTiming">点歌词行跳转 · 歌词偏移 {{ offsetMs }} ms</span>
            <span class="dim" v-else-if="hasLyric">无时间戳，静态全文（不跟随进度）</span>
            <span class="spacer"></span>
            <button class="btn link" v-if="hasTiming && !following" @click="resumeFollow">恢复跟随</button>
            <span class="dim" v-if="hasTiming && following">自动跟随中</span>
          </div>
        </div>
      </div>`,
  };
})(window.MH);
