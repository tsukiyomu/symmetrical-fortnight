# -*- coding: utf-8 -*-
"""
测试数据工具类
用于生成动态测试数据和处理接口关联数据

主要功能:
1. 从extract.yaml文件中读取接口关联数据
2. 生成时间戳等动态数据
3. 提供数据加密功能

Author: tsukiyomi
Created: 2025-08-15
Last Modified: 2025-08-16
"""

import base64
import hashlib
import time
import random
import re
from hashlib import sha1

from common.readyaml import ReadYamlData


class TestDataUtils:
    """测试数据工具类"""

    def __init__(self):
        self.read = ReadYamlData()

    def get_extract_data(self, node_name, randoms=None) -> str:
        """
        获取extract.yaml数据，首先判断randoms是否为数字类型，如果不是就获取下一个node节点的数据
        :param node_name: extract.yaml文件中的key值
        :param randoms: int类型，0：随机读取；-1：读取全部，返回字符串形式；-2：读取全部，返回列表形式；其他根据列表索引取值，取第一个值为1，第二个为2，以此类推;
        :return:
        """
        data = self.read.get_extract_yaml(node_name)
        if randoms is not None and bool(re.compile(r'^[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?$').match(randoms)):
            randoms = int(randoms)
            data_value = {
                randoms: self.get_extract_order_data(data, randoms),
                0: random.choice(data),
                -1: ','.join(data),
                -2: ','.join(data).split(','),
            }
            data = data_value[randoms]
        else:
            data = self.read.get_extract_yaml(node_name, randoms)
        return data

    @staticmethod
    def get_extract_order_data(data, randoms):
        """获取extract.yaml数据，不为0、-1、-2，则按顺序读取文件key的数据"""
        if randoms not in [0, -1, -2]:
            return data[randoms - 1]

    @staticmethod
    def md5_encryption(params):
        """参数MD5加密"""
        enc_data = hashlib.md5()
        enc_data.update(params.encode(encoding="utf-8"))
        return enc_data.hexdigest()

    @staticmethod
    def sha1_encryption(params):
        """参数sha1加密"""
        enc_data = sha1()
        enc_data.update(params.encode(encoding="utf-8"))
        return enc_data.hexdigest()

    @staticmethod
    def base64_encryption(params):
        """base64加密"""
        base_params = params.encode("utf-8")
        encr = base64.b64encode(base_params)
        return encr

    @staticmethod
    def timestamp():
        """获取当前时间戳，10位"""
        t = int(time.time())
        return t

    @staticmethod
    def timestamp_thirteen():
        """获取当前的时间戳，13位"""
        t = int(time.time()) * 1000
        return t