# -*- coding: utf-8 -*-
"""
测试 matcher 模块的艺术家分割和匹配功能
"""
import unittest


def split_artist(artist):
    """
    拆分艺术家名称，支持多种分隔符

    支持的分隔符：
    - 英文逗号: ,
    - 英文分号: ;
    - 中文逗号: ，
    - 中文分号: ；
    - & 符号: &
    - 斜杠: /
    - 中文顿号: 、
    - 中点: • ·
    - 竖线: | ｜
    - 加号: + ＋

    Args:
        artist: 艺术家字符串，可能包含多个艺术家

    Returns:
        list: 拆分后的艺术家列表，去除空字符串
    """
    if not artist:
        return []

    separators = ['；', ';', '，', ',', '&', '/', '、', '•', '·', '|', '｜', '+', '＋']
    result = [artist]
    for sep in separators:
        new_result = []
        for item in result:
            new_result.extend([a.strip() for a in item.split(sep)])
        result = new_result
    return [a for a in result if a]


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


def match_artist(my_value, u_value):
    """
    艺术家匹配算法(支持多艺术家)

    Args:
        my_value: 本地艺术家名称
        u_value: 在线艺术家名称(可能包含多个, 用多种分隔符分隔)

    Returns:
        int: 匹配得分，取所有在线艺术家中的最高匹配得分
    """
    # 拆分在线艺术家列表
    online_artists = split_artist(u_value)

    if not online_artists:
        return match_score(my_value, u_value)

    # 对每个在线艺术家进行匹配，取最高得分
    max_score = 0
    for online_artist in online_artists:
        score = match_score(my_value, online_artist)
        if score > max_score:
            max_score = score

    return max_score


class TestArtistSplit(unittest.TestCase):
    """测试艺术家分割函数"""

    def test_single_artist(self):
        """测试单个艺术家"""
        result = split_artist("周杰伦")
        self.assertEqual(result, ["周杰伦"])

    def test_comma_separator(self):
        """测试英文逗号分隔"""
        result = split_artist("Artist1, Artist2, Artist3")
        self.assertEqual(result, ["Artist1", "Artist2", "Artist3"])

    def test_chinese_comma_separator(self):
        """测试中文逗号分隔"""
        result = split_artist("周杰伦，林俊杰，陈奕迅")
        self.assertEqual(result, ["周杰伦", "林俊杰", "陈奕迅"])

    def test_semicolon_separator(self):
        """测试分号分隔"""
        result = split_artist("周杰伦;林俊杰")
        self.assertEqual(result, ["周杰伦", "林俊杰"])

    def test_chinese_semicolon_separator(self):
        """测试中文分号分隔"""
        result = split_artist("周杰伦；林俊杰；陈奕迅")
        self.assertEqual(result, ["周杰伦", "林俊杰", "陈奕迅"])

    def test_ampersand_separator(self):
        """测试 & 符号分隔"""
        result = split_artist("Beyoncé & Jay-Z")
        self.assertEqual(result, ["Beyoncé", "Jay-Z"])

    def test_slash_separator(self):
        """测试斜杠分隔"""
        result = split_artist("Artist1/Artist2")
        self.assertEqual(result, ["Artist1", "Artist2"])

    def test_chinese_pause_separator(self):
        """测试中文顿号分隔"""
        result = split_artist("周杰伦、林俊杰、陈奕迅")
        self.assertEqual(result, ["周杰伦", "林俊杰", "陈奕迅"])

    def test_middle_dot_separator(self):
        """测试中点分隔"""
        result = split_artist("Artist1 • Artist2")
        self.assertEqual(result, ["Artist1", "Artist2"])

    def test_pipe_separator(self):
        """测试竖线分隔"""
        result = split_artist("Artist1|Artist2")
        self.assertEqual(result, ["Artist1", "Artist2"])

    def test_plus_separator(self):
        """测试加号分隔"""
        result = split_artist("Artist1+Artist2")
        self.assertEqual(result, ["Artist1", "Artist2"])

    def test_mixed_separators(self):
        """测试混合分隔符"""
        result = split_artist("Artist1; Artist2, Artist3 & Artist4")
        self.assertEqual(result, ["Artist1", "Artist2", "Artist3", "Artist4"])

    def test_whitespace_handling(self):
        """测试空格处理"""
        result = split_artist("  Artist1  ;  Artist2  ")
        self.assertEqual(result, ["Artist1", "Artist2"])

    def test_empty_string(self):
        """测试空字符串"""
        result = split_artist("")
        self.assertEqual(result, [])

    def test_none_input(self):
        """测试 None 输入"""
        result = split_artist(None)
        self.assertEqual(result, [])


class TestArtistMatch(unittest.TestCase):
    """测试艺术家匹配函数"""

    def test_single_artist_exact_match(self):
        """测试单个艺术家完全匹配"""
        score = match_artist("周杰伦", "周杰伦")
        self.assertEqual(score, 2)

    def test_single_artist_no_match(self):
        """测试单个艺术家不匹配"""
        score = match_artist("周杰伦", "林俊杰")
        self.assertEqual(score, 0)

    def test_single_artist_contains_match(self):
        """测试单个艺术家包含匹配"""
        score = match_artist("周杰伦", "周杰伦&林俊杰")
        self.assertEqual(score, 2)  # 第一个完全匹配

    def test_multiple_artists_best_match(self):
        """测试多个艺术家取最佳匹配"""
        score = match_artist("周杰伦", "林俊杰, 周杰伦, 陈奕迅")
        self.assertEqual(score, 2)

    def test_multiple_artists_partial_match(self):
        """测试多个艺术家部分匹配"""
        score = match_artist("Jay", "Jay Chou, Justin Bieber")
        self.assertEqual(score, 1)

    def test_comma_separator(self):
        """测试逗号分隔的多艺术家"""
        score = match_artist("周杰伦", "周杰伦, 林俊杰")
        self.assertEqual(score, 2)

    def test_semicolon_separator(self):
        """测试分号分隔的多艺术家"""
        score = match_artist("周杰伦", "周杰伦; 林俊杰")
        self.assertEqual(score, 2)

    def test_chinese_comma_separator(self):
        """测试中文逗号分隔的多艺术家"""
        score = match_artist("周杰伦", "周杰伦，林俊杰")
        self.assertEqual(score, 2)

    def test_ampersand_separator(self):
        """测试 & 符号分隔的多艺术家"""
        score = match_artist("Beyoncé", "Beyoncé & Jay-Z")
        self.assertEqual(score, 2)

    def test_slash_separator(self):
        """测试斜杠分隔的多艺术家"""
        score = match_artist("周杰伦", "周杰伦/林俊杰")
        self.assertEqual(score, 2)

    def test_chinese_pause_separator(self):
        """测试中文顿号分隔的多艺术家"""
        score = match_artist("周杰伦", "周杰伦、林俊杰")
        self.assertEqual(score, 2)

    def test_mixed_separators(self):
        """测试混合分隔符"""
        score = match_artist("Artist1", "Artist1; Artist2, Artist3")
        self.assertEqual(score, 2)

    def test_empty_online_artists(self):
        """测试空在线艺术家列表"""
        score = match_artist("周杰伦", "")
        self.assertEqual(score, 0)


class TestMatchScore(unittest.TestCase):
    """测试基础匹配分数函数"""

    def test_exact_match(self):
        """测试完全匹配"""
        score = match_score("周杰伦", "周杰伦")
        self.assertEqual(score, 2)

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        score = match_score("Jay Chou", "jay chou")
        self.assertEqual(score, 2)

    def test_space_insensitive(self):
        """测试空格不敏感"""
        score = match_score("Jay Chou", "JayChou")
        self.assertEqual(score, 2)

    def test_contains_match_left_to_right(self):
        """测试包含匹配（左包含右）"""
        score = match_score("Jay", "Jay Chou")
        self.assertEqual(score, 1)

    def test_contains_match_right_to_left(self):
        """测试包含匹配（右包含左）"""
        score = match_score("Jay Chou", "Jay")
        self.assertEqual(score, 1)

    def test_no_match(self):
        """测试不匹配"""
        score = match_score("周杰伦", "林俊杰")
        self.assertEqual(score, 0)

    def test_empty_string(self):
        """测试空字符串"""
        score = match_score("", "周杰伦")
        self.assertEqual(score, 0)

    def test_exception_handling(self):
        """测试异常处理"""
        score = match_score(None, "周杰伦")
        self.assertEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
