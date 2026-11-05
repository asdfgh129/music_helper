# -*- coding: utf-8 -*-
"""目录设置的读写（config.ini `[paths]` 的唯一写入点）

放在 `services/` 的原因：它要写盘，属于副作用，`core/` 不允许写文件。
为什么不另存一份 json：`config.py` 的优先级是「环境变量 > config.ini > 默认值」，
再存一份就会出现「配置有两个真相」。向导里改的目录直接落到 config.ini，改完
立即 `config.reload()`，后续所有步骤（含 CLI）读到的是同一份值。

约定：
- 值写空 = 删除该项，回落到 `config.py` 的默认值（这样默认值只在 config.py 里维护一份）；
- 被环境变量覆盖的项仍然可以保存，但页面上会标注「环境变量生效中，保存不改变实际值」；
- 保存失败不写坏原文件（先写临时文件再 `os.replace`）。
"""

import configparser
import os
import re

import config

# 向导第一步列出的目录（顺序即页面顺序）
_PATH_FIELDS = (
    ('library_dir', '库目录', 'LIBRARY_DIR', '最终音乐库，按 <年代>/<年份> 归档', True),
    ('workspace_dir', '工作区目录', 'WORKSPACE_DIR', '解密 / 补标签 / 分流的临时舞台', True),
    ('incomplete_dir', '待确认目录', 'INCOMPLETE_DIR',
     '未达入库标准的文件暂存，人工确认后再决定补全或删除', True),
    ('duplicate_dir', '重复文件临时目录', 'DUPLICATE_DIR', '声纹去重挑出来的重复文件', True),
    ('netease_dir', '网易云目录', 'NETEASE_DIR', '网易云音乐下载目录', True),
    ('netease_vip_dir', '网易云 VIP 目录', 'NETEASE_VIP_DIR',
     '网易云 VIP 下载（.ncm），留空则取「网易云目录/VipSOngsDownload」', False),
    ('qq_dir', 'QQ 音乐目录', 'QQ_DIR', 'QQ 音乐下载目录', True),
    ('qq_vip_dir', 'QQ 音乐 VIP 目录', 'QQ_VIP_DIR',
     'QQ 音乐 VIP 下载（.mflac/.mgg），留空则取「QQ 目录/VipSOngsDownload」', False),
)

VIP_PARENT = {
    'netease_vip_dir': 'netease_dir',
    'qq_vip_dir': 'qq_dir',
}

_VIP_SUBDIR = 'VipSOngsDownload'

# 注意用 os.name 判断平台：sys.platform 在 Windows 上是 'win32' 而不是 'nt'，
# 写成 `sys.platform != 'nt'` 会让「非 Windows 才拦盘符路径」永远成立。
_IS_WINDOWS = os.name == 'nt'

# Windows 盘符路径（`D:\music`、`G:/music`），用于非 Windows 上给出更清楚的提示
_DRIVE_PATH = re.compile(r'^[A-Za-z]:([\\/]|$)')


def fields():
    """目录字段清单（供接口序列化）"""
    return [{'key': key, 'label': label, 'attr': attr, 'desc': desc,
             'required': required}
            for key, label, attr, desc, required in _PATH_FIELDS]


def env_key(attr):
    return 'MUSIC_HELPER_' + attr


def vip_default(parent_value):
    """VIP 目录的默认值：跟随下载目录"""
    if not parent_value:
        return ''
    return os.path.join(parent_value, _VIP_SUBDIR)


def _load_ini():
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config.ini_path(), encoding='utf-8')
    except (configparser.Error, OSError):
        return configparser.ConfigParser(interpolation=None)
    return parser


def _ini_has(parser, key):
    return parser.has_option('paths', key) and bool(parser.get('paths', key).strip())


def source_of(key, attr):
    """当前值来自哪里：env / ini / default"""
    if os.environ.get(env_key(attr)):
        return 'env'
    if _ini_has(_load_ini(), key):
        return 'ini'
    return 'default'


def _probe(path):
    """目录现状：存在 / 是目录 / 可写 / 最近的已存在父目录"""
    info = {'exists': False, 'is_dir': False, 'writable': False, 'parent': '',
            'error': ''}
    if not path:
        info['error'] = '未填写'
        return info
    info['exists'] = os.path.exists(path)
    info['is_dir'] = os.path.isdir(path)
    parent = path
    while parent and not os.path.exists(parent):
        upper = os.path.dirname(parent.rstrip('\\/'))
        if upper == parent:
            break
        parent = upper
    info['parent'] = parent
    try:
        info['writable'] = os.access(parent or path, os.W_OK)
    except OSError:
        info['writable'] = False
    if not info['exists']:
        info['error'] = '目录不存在（可以在这里直接创建）'
    elif not info['is_dir']:
        info['error'] = '同名路径已存在但不是目录'
    return info


def current():
    """当前生效的目录值 + 现状（向导第一步的初始数据）"""
    items = []
    for key, label, attr, desc, required in _PATH_FIELDS:
        value = str(getattr(config, attr, '') or '')
        item = {
            'key': key, 'label': label, 'attr': attr, 'desc': desc,
            'required': required, 'value': value,
            'source': source_of(key, attr),
            'vip_default': (vip_default(str(getattr(config, VIP_PARENT[key].upper(), '') or ''))
                            if key in VIP_PARENT else ''),
        }
        item.update(_probe(value))
        items.append(item)
    return items


def _normalize(value):
    value = str(value or '').strip().strip('"')
    if not value:
        return ''
    return os.path.normpath(os.path.expanduser(value))


def validate(values):
    """校验一组目录设置，返回问题列表（不写盘）

    Returns:
        (problems, normalized)：problems 为空表示可以保存
    """
    problems = []
    normalized = {}
    for key, label, attr, _desc, required in _PATH_FIELDS:
        raw = values.get(key, '')
        value = _normalize(raw)
        normalized[key] = value
        if not value:
            if required:
                problems.append(f'{label}：不能留空')
            continue
        if not config.is_absolute_path(value):
            problems.append(f'{label}：请填写绝对路径（如 D:\\music）')
            continue
        if os.path.exists(value) and not os.path.isdir(value):
            problems.append(f'{label}：该路径已存在但不是目录')

    # VIP 目录留空时跟随下载目录，这里先把有效值补出来再比较
    effective = dict(normalized)
    for vip_key, parent_key in VIP_PARENT.items():
        if not effective.get(vip_key):
            effective[vip_key] = vip_default(effective.get(parent_key) or '')

    # 两个目录完全相同一定是配错了：移动会变成「自己移到自己」
    seen = {}
    for key, label, _attr, _desc, _required in _PATH_FIELDS:
        value = effective.get(key)
        if not value:
            continue
        folded = os.path.normcase(value)
        if folded in seen:
            problems.append(f'{label}：与「{seen[folded]}」是同一个目录')
        else:
            seen[folded] = label

    # 嵌套会让「移动」把一个目录搬进它自己的子目录，必然出错
    labels = {key: label for key, label, _a, _d, _r in _PATH_FIELDS}
    structural = ('library_dir', 'workspace_dir', 'incomplete_dir', 'duplicate_dir')
    for index, left_key in enumerate(structural):
        for right_key in structural[index + 1:]:
            left, right = effective.get(left_key), effective.get(right_key)
            if not left or not right:
                continue
            try:
                left_abs, right_abs = os.path.abspath(left), os.path.abspath(right)
                if os.path.commonpath([left_abs, right_abs]) == right_abs:
                    problems.append(f'{labels[left_key]}：不能放在「{labels[right_key]}」里面')
                elif os.path.commonpath([left_abs, right_abs]) == left_abs:
                    problems.append(f'{labels[right_key]}：不能放在「{labels[left_key]}」里面')
            except ValueError:
                # 不同盘符时 commonpath 会抛 ValueError，说明本来就没有嵌套关系
                pass

    if not _IS_WINDOWS:
        for key, label, _attr, _desc, _required in _PATH_FIELDS:
            value = effective.get(key) or ''
            if _DRIVE_PATH.match(value):
                problems.append(f'{label}：当前系统不是 Windows，盘符路径不可用')
    return problems, normalized


def save(values):
    """保存目录设置到 config.ini 并重载配置

    Returns:
        (problems, items)：problems 非空表示没有保存（原文件不动）
    """
    problems, normalized = validate(values)
    if problems:
        return problems, current()

    parser = _load_ini()
    if not parser.has_section('paths'):
        parser.add_section('paths')
    for key, _label, attr, _desc, _required in _PATH_FIELDS:
        value = normalized.get(key, '')
        if not value:
            if parser.has_option('paths', key):
                parser.remove_option('paths', key)
            continue
        # 与「跟随父目录」的默认值一致时不落盘，保持 ini 干净
        if key in VIP_PARENT:
            parent = normalized.get(VIP_PARENT[key]) or str(
                getattr(config, VIP_PARENT[key].upper(), '') or '')
            if os.path.normcase(value) == os.path.normcase(vip_default(parent)):
                if parser.has_option('paths', key):
                    parser.remove_option('paths', key)
                continue
        parser.set('paths', key, value)

    path = config.ini_path()
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    os.makedirs(directory, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        handle.write('# 由 music_helper Web 向导写入；手工编辑同样生效\n')
        parser.write(handle)
    os.replace(tmp, path)

    config.reload()
    return [], current()
