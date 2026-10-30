# -*- coding: utf-8 -*-
"""
报告模块 - 实现规划中的模块 8

产出两份文件：
    report-YYYYmmdd_HHMMSS.md    人读的 Markdown 报告
    review-YYYYmmdd_HHMMSS.csv   待处理清单（类型/路径/原因），可直接丢给下一步处理

报告本身只做聚合与渲染，不移动任何文件；需要移动时由 main 把动作写进 Plan。
"""

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime

CSV_HEADERS = ('类型', '路径', '说明')


@dataclass
class Section:
    title: str
    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    note: str = ''
    export: bool = False


class Report:
    """一次运行的检查报告"""

    def __init__(self, title):
        self.title = title
        self.created = datetime.now()
        self.summary = []
        self.sections = []

    # ---------- 收集 ----------

    def add_summary(self, label, value):
        self.summary.append((label, value))

    def add(self, title, headers=None, rows=None, note='', export=False):
        section = Section(
            title=title,
            headers=list(headers or []),
            rows=list(rows or []),
            note=note,
            export=export,
        )
        self.sections.append(section)
        return section

    def add_review(self, title, rows, note=''):
        """待处理清单：rows 为 (类型, 路径, 说明) 三元组"""
        return self.add(title, CSV_HEADERS, rows, note=note, export=True)

    # ---------- 渲染 ----------

    def render(self):
        lines = [
            f'# {self.title}',
            '',
            f'- 生成时间：{self.created.strftime("%Y-%m-%d %H:%M:%S")}',
        ]
        for label, value in self.summary:
            lines.append(f'- {label}：{value}')
        lines.append('')

        for section in self.sections:
            lines.append(f'## {section.title}')
            if section.note:
                lines.append('')
                lines.append(f'> {section.note}')
            lines.append('')
            if section.export:
                # 明细已在 CSV 中，正文只留一行指引，避免报告重复两遍
                lines.append(f'共 {len(section.rows)} 条，明细见同目录下的 review-*.csv')
            elif section.headers and section.rows:
                lines.append('| ' + ' | '.join(section.headers) + ' |')
                lines.append('|' + '|'.join(['---'] * len(section.headers)) + '|')
                for row in section.rows:
                    cells = [str(cell).replace('|', '\\|') for cell in row]
                    lines.append('| ' + ' | '.join(cells) + ' |')
            elif not section.headers:
                for row in section.rows:
                    lines.append(f'- {row}')
            else:
                lines.append('_（无）_')
            lines.append('')

        return '\n'.join(lines)

    def save(self, output_dir, prefix='report'):
        """写出 md + csv，返回 {'md': path, 'csv': path}"""
        os.makedirs(output_dir, exist_ok=True)
        stamp = self.created.strftime('%Y%m%d_%H%M%S')

        md_path = os.path.join(output_dir, f'{prefix}-{stamp}.md')
        with open(md_path, 'w', encoding='utf-8') as handle:
            handle.write(self.render())

        csv_path = os.path.join(output_dir, f'review-{stamp}.csv')
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_HEADERS)
            for section in self.sections:
                if section.export:
                    writer.writerows(section.rows)

        return {'md': md_path, 'csv': csv_path}
