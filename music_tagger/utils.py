# -*- coding: utf-8 -*-
"""
工具函数模块
"""
import time
import re
import copy
from mako import codegen, lexer
from mako.exceptions import MakoException
from mako.template import Template

# 繁简转换库
try:
    from component.zhconv.zhconv import convert, issimp
except ImportError:
    # 如果没有繁简转换库, 提供简化版本
    def convert(text, target):
        """简化的繁简转换(不实际转换)"""
        return text
    
    def issimp(text):
        """简化的简体判断"""
        return True


TEMPLATE_PATTERN = re.compile(r"\${[^${}#]+}")


def timestamp_to_dt(timestamp, format_type="%Y-%m-%d %H:%M:%S"):
    """时间戳转日期时间字符串"""
    time_local = time.localtime(timestamp)
    dt = time.strftime(format_type, time_local)
    return dt


def match_score(my_value, u_value):
    """
    字符串匹配评分算法
    
    Args:
        my_value: 本地值
        u_value: 在线值
    
    Returns:
        int: 2(完全匹配) | 1(包含匹配) | 0(不匹配)
    """
    try:
        my_value = my_value.lower().replace(" ", "")
        u_value = u_value.lower().replace(" ", "")
        
        # 繁简转换
        if not issimp(my_value):
            my_value = convert(my_value, 'zh-cn')
        if not issimp(u_value):
            u_value = convert(u_value, 'zh-cn')
        
        if not my_value or not u_value:
            return 0
        
        # 完全匹配
        if my_value == u_value:
            return 2
        # 包含匹配
        elif my_value in u_value or u_value in my_value:
            return 1
        # 不匹配
        return 0
    except Exception:
        return 0


class ConstantTemplate:
    """模板字符串解析器(支持${变量}语法)"""

    def __init__(self, data):
        self.data = data

    def resolve_data(self, value_maps):
        """
        解析模板字符串, 替换变量
        
        Args:
            value_maps: 变量字典, 如 {"title": "歌名", "artist": "艺术家"}
        
        Returns:
            解析后的数据
        """
        data = self.data

        if isinstance(data, str):
            return self.resolve_string(data, value_maps)
        if isinstance(data, list):
            ldata = [""] * len(data)
            for index, item in enumerate(data):
                ldata[index] = ConstantTemplate(copy.deepcopy(item)).resolve_data(value_maps)
            return ldata
        if isinstance(data, tuple):
            ldata = [""] * len(data)
            for index, item in enumerate(data):
                ldata[index] = ConstantTemplate(copy.deepcopy(item)).resolve_data(value_maps)
            return tuple(ldata)
        if isinstance(data, dict):
            for key, value in list(data.items()):
                data[key] = ConstantTemplate(copy.deepcopy(value)).resolve_data(value_maps)
            return data
        return data

    @staticmethod
    def get_string_templates(string):
        """提取字符串中的模板变量"""
        return list(set(TEMPLATE_PATTERN.findall(string)))

    @staticmethod
    def deformat_constant_key(key):
        """移除模板变量的${}包裹"""
        return key[2:-1]

    @staticmethod
    def resolve_string(string, value_maps):
        """解析字符串中的模板变量"""
        if not isinstance(string, str):
            return string

        templates = ConstantTemplate.get_string_templates(string)

        # 单一模板直接替换
        if len(templates) == 1 and templates[0] == string:
            key = ConstantTemplate.deformat_constant_key(string)
            if key in value_maps:
                return value_maps[key]

        # 多个模板逐个替换
        for tpl in templates:
            resolved = ConstantTemplate.resolve_template(tpl, value_maps)
            string = string.replace(tpl, resolved)
        return string

    @staticmethod
    def resolve_template(template, value_maps):
        """
        使用Mako模板引擎解析单个模板
        
        Args:
            template: 模板字符串, 如 "${title}"
            value_maps: 变量字典
        
        Returns:
            解析后的字符串
        """
        data = {}
        data.update(value_maps)
        
        if not isinstance(template, str):
            raise Exception(f"constant resolve error, template[{template}] is not a string")
        
        try:
            tm = Template(template)
        except (MakoException, SyntaxError) as e:
            print(f"pipeline resolve template[{template}] error[{e}]")
            return template
        
        try:
            resolved = tm.render_unicode(**data)
        except Exception as e:
            print(f"constant content({template}) is invalid, data({value_maps}), error: {e}")
            return template
        else:
            return resolved


__all__ = [
    "timestamp_to_dt",
    "match_score",
    "ConstantTemplate",
]
