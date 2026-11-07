# -*- coding: utf-8 -*-
"""网易云音乐 API 请求签名（AES + RSA）

**这不是音频解密**。项目里 `decrypto/` 负责把加密音频（.ncm/.mflac/.mgg）还原成
普通文件；本模块只负责给网易云的 HTTP 请求做参数签名——weapi 用 AES-CBC + RSA，
linuxapi 用 AES-ECB。两者同名容易混，所以文件名带 `_netease_` 前缀并加上下划线，
表示它是 `platforms` 包的私有实现，不对外导出。

上游算法与密钥常量来自：
    weapi      https://github.com/darknessomi/musicbox/blob/master/NEMbox/encrypt.py
    linuxapi   https://github.com/Binaryify/NeteaseCloudMusicApi/blob/master/util/crypto.js
"""

from base64 import b64encode
from binascii import hexlify
from json import dumps
from os import urandom

from Cryptodome.Cipher import AES

MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
    "b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280"
    "104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932"
    "575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b"
    "3ece0462db0a22b8e7"
)
PUBKEY = "010001"
NONCE = b"0CoJUm6Qyw8W8jud"
LINUXKEY = b"rFgB&h#%2?^eDg:Q"


def aes(text, key, method={}):
    """AES 加密；method 带 iv 走 CBC，带 base64 则输出 Base64 而非十六进制"""
    pad = 16 - len(text) % 16
    text = text + bytearray([pad] * pad)
    if "iv" in method:
        encryptor = AES.new(key, AES.MODE_CBC, b"0102030405060708")
    else:
        encryptor = AES.new(key, AES.MODE_ECB)
    ciphertext = encryptor.encrypt(text)
    if "base64" in method:
        return b64encode(ciphertext)
    return hexlify(ciphertext).upper()


def rsa(text, pubkey, modulus):
    """RSA 加密（网易云用的是教科书式裸 RSA，文本先反转）"""
    text = text[::-1]
    rs = pow(int(hexlify(text), 16),
             int(pubkey, 16), int(modulus, 16))
    return format(rs, 'x').zfill(256)


def create_key(size):
    """生成随机密钥（weapi 每次请求都换一把）"""
    return hexlify(urandom(size))[:16]


def weEncrypt(text):
    """网易云网页版 API（weapi）加密：AES-CBC 两次 + RSA 加密随机密钥"""
    data = dumps(text).encode("utf-8")
    secret = create_key(16)
    method = {"iv": True, "base64": True}
    params = aes(aes(data, NONCE, method), secret, method)
    encseckey = rsa(secret, PUBKEY, MODULUS)
    return {"params": params, "encSecKey": encseckey}


def linuxEncrypt(text):
    """网易云 Linux 版 API（linuxapi）加密：单层 AES-ECB"""
    text = str(text).encode()
    data = aes(text, LINUXKEY)
    return {"eparams": data.decode()}
