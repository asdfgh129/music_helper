# -*- coding: utf-8 -*-
"""生成 docs/images/ 下的向导操作示意图（SVG）

图片是文档资产，界面改了重跑本脚本即可；不参与运行，也不被程序引用。

    python scripts/gen_web_guide_images.py
"""

import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'docs', 'images')

BG = '#16171b'
PANEL = '#1e1f24'
PANEL2 = '#25262c'
PANEL3 = '#2c2d34'
BORDER = '#34353d'
SOFT = '#2a2b32'
TEXT = '#e4e5ea'
MUTED = '#9a9ca8'
DIM = '#767884'
ACC = '#4f9cf9'
TEAL = '#37c2a8'
OK = '#5fb865'
WARN = '#d9a43b'
ERR = '#e8645c'

FONT = ('-apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, '
        '&quot;Microsoft YaHei&quot;, sans-serif')
MONO = '&quot;Consolas&quot;, &quot;Cascadia Mono&quot;, monospace'


def esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def rect(x, y, w, h, fill=PANEL, stroke=BORDER, rx=8, extra=''):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" {extra}/>')


def text(x, y, content, size=13, fill=TEXT, weight='normal', anchor='start',
         mono=False, opacity=None):
    attrs = f'font-size="{size}" fill="{fill}" font-weight="{weight}"'
    if anchor != 'start':
        attrs += f' text-anchor="{anchor}"'
    if opacity:
        attrs += f' opacity="{opacity}"'
    family = MONO if mono else FONT
    return f'<text x="{x}" y="{y}" font-family="{family}" {attrs}>{esc(content)}</text>'


def pill(x, y, label, color, size=11, align='left'):
    """胶囊标签；align='right' 时 x 视为右边界

    Returns: (svg, 宽度)
    """
    chinese = any(ord(char) > 127 for char in label)
    width = 12 + len(label) * (size * 0.78 if chinese else size * 0.58)
    width = max(width, 34)
    left = x - width if align == 'right' else x
    svg = (rect(left, y, width, 20, fill=color + '26', stroke='none', rx=10)
           + text(left + width / 2, y + 14, label, size=size, fill=color,
                  anchor='middle'))
    return svg, width


def dot(cx, cy, color, r=4):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'


def check(cx, cy, on=True):
    if not on:
        return (f'<rect x="{cx - 6}" y="{cy - 6}" width="12" height="12" rx="3" '
                f'fill="none" stroke="{DIM}"/>')
    return (f'<rect x="{cx - 6}" y="{cy - 6}" width="12" height="12" rx="3" '
            f'fill="{ACC}"/>'
            f'<path d="M{cx - 3} {cy} l2 2.4 l4.6 -4.8" stroke="#06111f" '
            f'stroke-width="1.8" fill="none" stroke-linecap="round"/>')


def button(x, y, label, w=96, primary=False, danger=False, h=30):
    if primary:
        fill, stroke, color = ACC, ACC, '#06111f'
    elif danger:
        fill, stroke, color = PANEL2, '#8c3f3a', ERR
    else:
        fill, stroke, color = PANEL2, BORDER, TEXT
    return (rect(x, y, w, h, fill=fill, stroke=stroke, rx=7)
            + text(x + w / 2, y + 19.5, label, size=12, fill=color, anchor='middle',
                   weight='600' if primary else 'normal'))


def frame(width, height, title, subtitle, step):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
             f'height="{height}" viewBox="0 0 {width} {height}" '
             f'font-family="{FONT}">',
             rect(0, 0, width, height, fill=BG, stroke=SOFT, rx=12),
             # 顶栏
             '<line x1="0" y1="52" x2="%d" y2="52" stroke="%s"/>' % (width, BORDER),
             dot(30, 26, ACC, 5),
             text(44, 31, 'music_helper · 音乐整理向导', size=13, fill=MUTED, weight='600')]
    for index in range(1, 9):
        cx = width - 250 + (index - 1) * 27
        active = index == step
        parts.append(f'<circle cx="{cx}" cy="26" r="11" fill="'
                     + (ACC if active else PANEL3) + '" stroke="'
                     + (ACC if active else BORDER) + '"/>')
        parts.append(text(cx, 30, str(index), size=11, anchor='middle',
                          fill='#06111f' if active else DIM,
                          weight='600' if active else 'normal'))
    parts.append(text(32, 90, title, size=19, fill=TEXT, weight='600'))
    parts.append(text(32, 114, subtitle, size=12.5, fill=DIM))
    return parts


def finish(parts):
    parts.append('</svg>')
    return '\n'.join(parts)


def stat_strip(x, y, items, width, height=56):
    """一排统计块：[(数字, 标签, 颜色)]"""
    parts = []
    gap = 10
    cell = (width - gap * (len(items) - 1)) / len(items)
    for index, (number, label, color) in enumerate(items):
        left = x + index * (cell + gap)
        parts.append(rect(left, y, cell, height, fill=PANEL2, stroke=BORDER, rx=8))
        parts.append(text(left + 14, y + 26, number, size=18, fill=color, mono=True,
                          weight='600'))
        parts.append(text(left + 14, y + 45, label, size=11, fill=DIM))
    return parts


def pane(x, y, w, h, title, path, badge=None):
    parts = [rect(x, y, w, h, fill=PANEL, stroke=BORDER, rx=10),
             rect(x, y, w, 40, fill=PANEL2, stroke='none', rx=10),
             text(x + 14, y + 25, title, size=12.5, fill=TEXT, weight='600')]
    parts.append(text(x + 14 + len(title) * 13 + 12, y + 25, path, size=11,
                      fill=TEAL, mono=True))
    if badge:
        svg, bw = pill(x + w - 12 - 60, y + 10, badge, ACC)
        parts.append(svg)
    parts.append(f'<line x1="{x}" y1="{y + 40}" x2="{x + w}" y2="{y + 40}" '
                 f'stroke="{BORDER}"/>')
    return parts


def file_row(x, y, w, name, tags, checked=None, name_size=12):
    """文件行：复选框 + 文件名 + 右侧标签"""
    parts = []
    if checked is not None:
        parts.append(check(x + 16, y + 13, checked))
        left = x + 34
    else:
        left = x + 16
    parts.append(text(left, y + 17, name, size=name_size, fill=TEXT))
    right = x + w - 14
    for label, color in reversed(tags):
        svg, bw = pill(right, y + 3, label, color, align='right')
        parts.append(svg)
        right -= bw + 6
    parts.append(f'<line x1="{x}" y1="{y + 30}" x2="{x + w}" y2="{y + 30}" '
                 f'stroke="{SOFT}"/>')
    return parts


# --------------------------------------------------------------------------- #
# 各图                                                                        #
# --------------------------------------------------------------------------- #

def image_flow():
    width, height = 960, 380
    parts = frame(width, height, '八步流程',
                  '每一步只做一件事；前一步的输出就是后一步的输入', 0)
    steps = [
        ('1', '目录设置', '八个目录'), ('2', '操作类型', '初始化 / 自检'),
        ('3', '拷贝', '下载 → 工作区'), ('4', '解密', '加密格式 → 音频'),
        ('5', '标签歌词', '补全 / 手改'), ('6', '查重', '工作区 ↔ 库'),
        ('7', '工作区自检', '只报告'), ('8', '归档', '年代/年份'),
    ]
    box_w, box_h, gap = 205, 84, 24
    for index, (num, title, sub) in enumerate(steps):
        row, col = divmod(index, 4)
        x = 32 + col * (box_w + gap)
        y = 150 + row * (box_h + 54)
        active = index == 5
        parts.append(rect(x, y, box_w, box_h, fill=PANEL,
                          stroke=ACC if active else BORDER, rx=10))
        parts.append(f'<circle cx="{x + 26}" cy="{y + 28}" r="13" '
                     f'fill="{ACC if active else PANEL3}"/>')
        parts.append(text(x + 26, y + 33, num, size=12, anchor='middle',
                          fill='#06111f' if active else MUTED, weight='600'))
        parts.append(text(x + 48, y + 33, title, size=14, fill=TEXT, weight='600'))
        parts.append(text(x + 48, y + 56, sub, size=11.5, fill=DIM))
        if col < 3:
            parts.append(f'<path d="M{x + box_w + 4} {y + box_h / 2} l16 0" '
                         f'stroke="{DIM}" stroke-width="1.4"/>')
            parts.append(f'<path d="M{x + box_w + 14} {y + box_h / 2 - 5} '
                         f'l6 5 l-6 5" stroke="{DIM}" stroke-width="1.4" fill="none"/>')
    # 第二行回到左边
    parts.append(f'<path d="M{32 + 3 * (box_w + gap) + box_w / 2} {150 + box_h + 8} '
                 f'v22 h{-(3 * (box_w + gap))} v22" stroke="{DIM}" '
                 f'stroke-width="1.4" fill="none"/>')
    parts.append(f'<path d="M{32 + box_w / 2} {150 + box_h + 46} l-5 -6 l10 0 z" fill="{DIM}"/>')
    return finish(parts)


def image_step1():
    width, height = 960, 520
    parts = frame(width, height, '第 1 步 · 设置目录',
                  '填绝对路径，或点「浏览」从磁盘选；保存前会逐项校验', 1)
    rows = [
        ('音乐库', 'D:\\music', '库目录，归档的最终去处'),
        ('工作区', 'D:\\music_workspace', '所有中间产物先落这里'),
        ('待补全', 'D:\\music_workspace\\_unready', '标签不全的文件停这里'),
        ('重复文件', 'D:\\music_duplicates', '查重移走的文件'),
        ('网易云下载', 'D:\\CloudMusic', '普通下载目录'),
        ('网易云 VIP', 'D:\\CloudMusic\\VipSongsDownload', '加密格式来源'),
        ('QQ 音乐下载', 'D:\\QQMusic', '普通下载目录'),
        ('QQ VIP', 'D:\\QQMusic\\VipSongsDownload', '加密格式来源'),
    ]
    y = 138
    for index, (label, value, note) in enumerate(rows):
        top = y + index * 40
        if index % 2 == 0:
            parts.append(rect(24, top - 8, 912, 40, fill=PANEL, stroke='none', rx=6))
        parts.append(text(44, top + 18, label, size=12.5, fill=MUTED))
        parts.append(text(190, top + 18, value, size=12, fill=TEAL, mono=True))
        parts.append(text(560, top + 18, note, size=11, fill=DIM))
        parts.append(rect(830, top + 2, 76, 26, fill=PANEL2, stroke=BORDER, rx=6))
        parts.append(text(868, top + 19, '浏览', size=11.5, fill=TEXT, anchor='middle'))
    parts.append(button(760, 470, '保存并下一步', 148, primary=True, h=32))
    parts.append(button(650, 470, '校验', 96, h=32))
    return finish(parts)


def image_step2():
    width, height = 960, 470
    parts = frame(width, height, '第 2 步 · 选择操作',
                  '先看库是否已初始化，再决定这一步做什么', 2)
    parts.append(rect(24, 132, 912, 120, fill=PANEL, stroke=BORDER, rx=10))
    parts.append(text(44, 160, '库目录状态', size=14, fill=TEXT, weight='600'))
    svg, _ = pill(130, 146, '已初始化', OK)
    parts.append(svg)
    parts.append(text(250, 160, 'D:\\music', size=11.5, fill=TEAL, mono=True))
    parts += stat_strip(44, 176, [('12433', '音频文件', TEAL), ('37', '年份目录', TEAL),
                                  ('有', '声纹库', OK), ('有', '年代/年份结构', OK)],
                        872, 62)
    options = [
        ('1 · 初始化库目录', '建目录结构 + 建声纹库，幂等且不动任何文件', True),
        ('2 · 只做库目录自检', '检查文件名 / 标签 / 重复 / 歌词，只出报告', False),
    ]
    for index, (title, desc, active) in enumerate(options):
        y = 274 + index * 78
        parts.append(rect(24, y, 912, 70, fill=PANEL2 if active else PANEL,
                          stroke=ACC if active else BORDER, rx=10))
        parts.append(f'<circle cx="52" cy="{y + 35}" r="10" fill="none" '
                     f'stroke="{ACC if active else DIM}" stroke-width="1.5"/>')
        if active:
            parts.append(f'<circle cx="52" cy="{y + 35}" r="5.5" fill="{ACC}"/>')
        parts.append(text(76, y + 30, title, size=13.5, fill=TEXT, weight='600'))
        parts.append(text(76, y + 52, desc, size=11.5, fill=DIM))
    parts.append(button(760, 428, '继续 →', 130, primary=True, h=30))
    return finish(parts)


def image_step3():
    width, height = 960, 500
    parts = frame(width, height, '第 3 步 · 拷贝到工作区',
                  '按月份筛选来源；点组头可以整组排除', 3)
    parts.append(text(32, 146, '月份', size=12, fill=DIM))
    parts.append(rect(74, 132, 110, 26, fill=PANEL2, stroke=BORDER, rx=6))
    parts.append(text(86, 150, '2026-08', size=11.5, fill=TEXT, mono=True))
    for index, label in enumerate(['全选', '全不选', '仅未拷贝']):
        parts.append(button(700 + index * 74, 132, label, 66, h=26))
    parts += pane(24, 176, 440, 258, '待拷贝', '网易云 / QQ', '12 / 42')
    parts += pane(496, 176, 440, 258, '工作区', 'D:\\music_workspace', '36 个')
    files = [('周杰伦 - 晴天.flac', [('8月', DIM), ('32.1 MB', MUTED)]),
             ('林俊杰 - 江南.flac', [('8月', DIM), ('28.4 MB', MUTED)]),
             ('陈奕迅 - 十年.mp3', [('8月', DIM), ('9.8 MB', MUTED)]),
             ('五月天 - 倔强.flac', [('8月', DIM), ('30.2 MB', MUTED)]),
             ('邓紫棋 - 光年之外.flac', [('8月', DIM), ('27.6 MB', MUTED)])]
    for index, (name, tags) in enumerate(files):
        y = 220 + index * 38
        parts += file_row(24, y, 440, name, tags, checked=True)
        parts += file_row(496, y, 440, name, [('已有', OK)])
    parts.append(button(760, 456, '开始拷贝', 130, primary=True, h=30))
    return finish(parts)


def image_step4():
    width, height = 960, 480
    parts = frame(width, height, '第 4 步 · 解密加密音频',
                  'ncm / mflac / mgg 需要先解密才能读标签、算声纹', 4)
    parts.append(text(32, 146, '月份范围', size=12, fill=DIM))
    parts.append(rect(98, 132, 90, 26, fill=PANEL2, stroke=BORDER, rx=6))
    parts.append(text(110, 150, '2026-07', size=11.5, fill=TEXT, mono=True))
    parts.append(text(196, 150, '→', size=12, fill=DIM))
    parts.append(rect(216, 132, 90, 26, fill=PANEL2, stroke=BORDER, rx=6))
    parts.append(text(228, 150, '2026-08', size=11.5, fill=TEXT, mono=True))
    parts += pane(24, 176, 440, 240, '加密文件', '待解密', '6 个')
    parts += pane(496, 176, 440, 240, '解密后', '工作区', '5 个')
    for index, (name, out) in enumerate([
            ('晴天.ncm', '周杰伦 - 晴天.flac'), ('江南.mflac', '林俊杰 - 江南.flac'),
            ('十年.mgg', '陈奕迅 - 十年.mp3'), ('倔强.ncm', '五月天 - 倔强.flac'),
            ('光年之外.mflac', '邓紫棋 - 光年之外.flac')]):
        y = 220 + index * 38
        parts += file_row(24, y, 440, name, [('待解密', WARN)])
        parts += file_row(496, y, 440, out, [('已存在' if index == 4 else '新文件',
                                              DIM if index == 4 else OK)])
    parts.append(button(760, 436, '开始解密', 130, primary=True, h=30))
    return finish(parts)


def image_step5():
    width, height = 960, 520
    parts = frame(width, height, '第 5 步 · 标签与歌词补全',
                  '只填空缺、不覆盖已有值、不改文件名；可排序、可单曲编辑', 5)
    parts += stat_strip(24, 132, [('36', '工作区文件', TEAL), ('31', '已可入库', OK),
                                  ('5', '缺核心标签', WARN), ('1', '文件名矛盾', ERR)],
                        912, 54)
    # 字段开关
    parts.append(rect(24, 198, 912, 62, fill=PANEL, stroke=BORDER, rx=10))
    parts.append(text(40, 220, '要补的字段', size=11.5, fill=DIM))
    tags = [('歌曲名', True), ('歌手', True), ('专辑', True), ('年份', True),
            ('流派', False), ('封面', True), ('歌词', False)]
    x = 124
    for label, on in tags:
        parts.append(check(x, 216, on))
        parts.append(text(x + 12, 220, label, size=11.5, fill=MUTED))
        x += 62
    parts.append(text(40, 245, '勾选只表示「允许写入」：字段为空才填，已有值不会被覆盖', size=11, fill=DIM))
    # 表格
    parts.append(rect(24, 272, 912, 176, fill=PANEL, stroke=BORDER, rx=10))
    headers = [('文件名', 50), ('艺术家', 380), ('歌名', 470), ('年份', 590),
               ('封面', 660), ('歌词', 716), ('状态', 780)]
    for label, hx in headers:
        parts.append(text(hx, 296, label, size=11, fill=DIM))
    parts.append(f'<line x1="24" y1="306" x2="936" y2="306" stroke="{BORDER}"/>')
    rows = [('周杰伦 - 晴天.flac', '周杰伦', '晴天', '2003', '有', '无', '缺歌词', WARN),
            ('林俊杰 - 江南.flac', '林俊杰', '江南', '2004', '有', '有', '可入库', OK),
            ('陈奕迅 - 十年.mp3', '陈奕迅', '十年', '2003', '无', '有', '缺封面', WARN),
            ('徐良 - 坏女孩.flac', '徐良', '—', '—', '无', '无', '文件名矛盾', ERR)]
    for index, (name, artist, title, year, cover, lrc, state, color) in enumerate(rows):
        y = 320 + index * 32
        parts.append(check(40, y + 7, index < 2))
        parts.append(text(58, y + 11, name, size=11.5, fill=TEXT))
        for value, vx in ((artist, 380), (title, 470), (year, 590)):
            parts.append(text(vx, y + 11, value, size=11.5, fill=MUTED))
        parts.append(text(664, y + 11, cover, size=11.5,
                          fill=OK if cover == '有' else DIM))
        parts.append(text(720, y + 11, lrc, size=11.5,
                          fill=OK if lrc == '有' else DIM))
        parts.append(text(780, y + 11, state, size=11, fill=color))
        parts.append(text(884, y + 11, '编辑', size=11, fill=ACC))
        parts.append(f'<line x1="24" y1="{y + 22}" x2="936" y2="{y + 22}" stroke="{SOFT}"/>')
    parts.append(button(770, 468, '开始补全', 120, primary=True, h=30))
    parts.append(text(32, 488, '点「编辑」可单曲手工改标签与歌词，可先「在线取标签」预览再保存',
                      size=11.5, fill=DIM))
    return finish(parts)


def image_step6():
    width, height = 960, 560
    parts = frame(width, height, '第 6 步 · 查重（两栏比对）',
                  '左栏工作区、右栏库内；右栏逐条勾选哪几个旧版本让位', 6)
    parts += stat_strip(24, 132, [('36', '工作区文件', TEAL), ('31', '库中不存在', OK),
                                  ('1', '库中已有', ERR), ('4', '可替换库内', WARN),
                                  ('0', '需人工确认', MUTED)], 912, 54)
    parts += pane(24, 200, 440, 236, '工作区待入库', '点一行查看对应副本', '36')
    left_items = [('Uu (刘梦妤) - 气象站台.flac', [('可替换', WARN)], True),
                  ('周杰伦 - 等你下课.flac', [('可替换', WARN)], True),
                  ('张杰 - 三生三世.flac', [('库中已有', ERR)], False),
                  ('海来阿木 - 来跳舞.flac', [('可替换', WARN)], False)]
    for index, (name, tags, focus) in enumerate(left_items):
        y = 246 + index * 42
        if focus:
            parts.append(rect(24, y, 440, 40, fill='#233046', stroke='none', rx=0))
            parts.append(rect(24, y, 3, 40, fill=ACC, stroke='none', rx=0))
        parts += file_row(24, y, 440, name, tags, checked=index < 2)
    parts += pane(496, 200, 440, 236, '库中对应文件', 'Uu (刘梦妤) - 气象站台.flac', '1')
    right = [('uU(刘梦妤)-气象站台.wav', [('更占地方', WARN)], True, True)]
    for index, (name, tags, checked, enabled) in enumerate(right):
        y = 246 + index * 38
        parts += file_row(496, y, 440, name, tags, checked=checked if enabled else None)
    parts.append(text(516, 330, 'WAV 48kHz/24bit · 38.2 MB', size=11, fill=DIM, mono=True))
    parts.append(text(516, 356, '勾上的旧版本移入重复目录；库里的文件不会被直接删除',
                      size=11, fill=DIM))
    # 底部按钮
    parts.append(text(32, 462, '默认只勾「库中已有」（只动工作区）；可替换项需要逐项确认',
                      size=11.5, fill=DIM))
    parts.append(button(520, 480, '移入重复目录', 130, h=32))
    parts.append(button(658, 480, '删除所选（1 项）', 148, danger=True, h=32))
    parts.append(button(814, 480, '下一步 →', 98, primary=True, h=32))
    # 确认框提示
    parts.append(rect(24, 452, 470, 76, fill=PANEL2, stroke=BORDER, rx=8))
    parts.append(text(40, 474, '执行前弹出两栏确认：', size=11.5, fill=MUTED))
    parts.append(text(40, 492, '左 · 工作区将删除 1 个', size=11, fill=ERR))
    parts.append(text(40, 510, '右 · 库目录将移出 1 个旧版本', size=11, fill=WARN))
    return finish(parts)


def image_step7():
    width, height = 960, 520
    parts = frame(width, height, '第 7 步 · 工作区自检',
                  '只出报告、不动文件；重点核对「文件名 ↔ 标签」', 7)
    parts += stat_strip(24, 132, [('36', '工作区文件', TEAL), ('31', '可入库', OK),
                                  ('4', '文件名矛盾', ERR), ('5', '缺歌词', WARN),
                                  ('0', '孤立 .lrc', MUTED)], 912, 54)
    parts.append(rect(24, 198, 912, 244, fill=PANEL, stroke=BORDER, rx=10))
    headers = [('文件名', 44), ('文件名解析', 330), ('标签', 520), ('一致性', 700),
               ('问题', 830)]
    for label, hx in headers:
        parts.append(text(hx, 222, label, size=11, fill=DIM))
    parts.append(f'<line x1="24" y1="232" x2="936" y2="232" stroke="{BORDER}"/>')
    rows = [
        ('林俊杰 - 江南.flac', '林俊杰 / 江南', '林俊杰 / 江南', [('歌手 ✓', OK), ('歌名 ✓', OK)], '可入库', OK),
        ('徐良 - 坏女孩.flac', '徐良 / 坏女孩', '许嵩 / 坏女孩', [('歌手 ✗', ERR), ('歌名 ✓', OK)], '歌手矛盾', ERR),
        ('周杰伦 - 晴天.flac', '周杰伦 / 晴天', '周杰伦 (Jay Chou) / 晴天', [('歌手 ✓', OK), ('歌名 ✓', OK)], '可入库', OK),
        ('Intro.flac', '（无歌手） / Intro', '某某 / Intro', [('歌手 —', DIM), ('歌名 ✓', OK)], '歌手不可比', DIM),
    ]
    for index, (name, parsed, tags, chips, problem, color) in enumerate(rows):
        y = 248 + index * 46
        parts.append(text(44, y + 16, name, size=11.5, fill=TEXT))
        parts.append(text(330, y + 16, parsed, size=11, fill=DIM, mono=True))
        parts.append(text(520, y + 16, tags, size=11, fill=DIM, mono=True))
        x = 700
        for label, chip_color in chips:
            svg, bw = pill(x, y + 3, label, chip_color)
            parts.append(svg)
            x += bw + 4
        parts.append(text(830, y + 16, problem, size=11, fill=color))
        parts.append(f'<line x1="24" y1="{y + 32}" x2="936" y2="{y + 32}" stroke="{SOFT}"/>')
    parts.append(text(44, 470, '✓ 一致 · ✗ 矛盾（会被挡在入库之外）· — 不可比（不算问题）',
                      size=11.5, fill=DIM))
    parts.append(button(812, 484, '下一步 →', 104, primary=True, h=30))
    return finish(parts)


def image_step8():
    width, height = 960, 520
    parts = frame(width, height, '第 8 步 · 按年份归档',
                  '按 <年代>/<年份> 两级目录落位；未达标文件进待确认目录', 8)
    options = [('直接入库（推荐）', '工作区 → D:\\music，归档即入库', True),
               ('只在工作区整理', '工作区内建 <年代>/<年份>，先不入库', False)]
    for index, (title, desc, active) in enumerate(options):
        y = 132 + index * 52
        parts.append(rect(24, y, 600, 44, fill=PANEL2 if active else PANEL,
                          stroke=ACC if active else BORDER, rx=8))
        parts.append(f'<circle cx="48" cy="{y + 22}" r="8" fill="none" stroke="{ACC if active else DIM}"/>')
        if active:
            parts.append(f'<circle cx="48" cy="{y + 22}" r="4" fill="{ACC}"/>')
        parts.append(text(70, y + 19, title, size=12.5, fill=TEXT, weight='600'))
        parts.append(text(70, y + 35, desc, size=10.5, fill=DIM))
    parts.append(rect(640, 132, 296, 96, fill=PANEL, stroke=BORDER, rx=8))
    parts.append(check(662, 156, True))
    parts.append(text(680, 160, '把不可归档的移入待确认目录', size=11.5, fill=MUTED))
    parts.append(text(662, 186, '缺年份 / 缺歌手 / 文件名与标签矛盾', size=10.5, fill=DIM))
    parts.append(text(662, 208, '不勾选则保持在工作区不动', size=10.5, fill=DIM))
    parts += stat_strip(24, 244, [('30', '待归档文件', TEAL), ('12', '年份分组', TEAL),
                                  ('6', '无法归档', WARN)], 912, 54)
    parts.append(rect(24, 312, 912, 158, fill=PANEL, stroke=BORDER, rx=10))
    parts.append(text(44, 338, '归档计划', size=13, fill=TEXT, weight='600'))
    rows = [('2000-2009 / 2003', '8 个 · 246 MB'), ('2010-2019 / 2016', '12 个 · 402 MB'),
            ('2020-2029 / 2023', '6 个 · 188 MB'), ('1990-1999 / 1997', '4 个 · 129 MB')]
    for index, (folder, detail) in enumerate(rows):
        y = 356 + (index // 2) * 42
        x = 44 + (index % 2) * 440
        parts.append(text(x, y + 14, folder, size=12, fill=TEAL, mono=True))
        parts.append(text(x + 150, y + 14, detail, size=11, fill=DIM))
    parts.append(f'<line x1="44" y1="426" x2="916" y2="426" stroke="{SOFT}"/>')
    parts.append(text(44, 448, '未达标（缺年份 / 缺歌手 / 文件名与标签矛盾）的文件单独列出，勾选后可一键移入待确认目录',
                      size=11, fill=DIM))
    parts.append(button(796, 478, '开始归档', 124, primary=True, h=30))
    return finish(parts)


def main():
    os.makedirs(OUT, exist_ok=True)
    images = {
        'flow.svg': image_flow,
        'step1-dirs.svg': image_step1,
        'step2-actions.svg': image_step2,
        'step3-copy.svg': image_step3,
        'step4-decrypt.svg': image_step4,
        'step5-tags.svg': image_step5,
        'step6-dedupe.svg': image_step6,
        'step7-check.svg': image_step7,
        'step8-archive.svg': image_step8,
    }
    for name, builder in images.items():
        path = os.path.join(OUT, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(builder())
        print('写入', os.path.relpath(path, os.path.dirname(OUT)))


if __name__ == '__main__':
    main()
