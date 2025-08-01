# -*- coding: utf-8 -*-
"""
数据提取工具类
统一处理接口响应数据的提取逻辑
"""
import json
import re
import jsonpath
from common.recordlog import logs
from common.readyaml import ReadYamlData


class ExtractUtils:
    """数据提取工具类"""
    
    def __init__(self):
        self.read = ReadYamlData()
    
    def extract_data(self, testcase_extract, response):
        """
        提取接口的返回参数，支持正则表达式和json提取，提取单个参数
        
        Args:
            testcase_extract: testcase文件yaml中的extract值
            response: 接口的实际返回值,str类型
            
        Returns:
            None，提取的数据会写入YAML文件
        """
        pattern_lst = ['(.+?)', '(.*?)', r'(\d+)', r'(\d*)']
        try:
            for key, value in testcase_extract.items():
                # 处理正则表达式提取
                for pat in pattern_lst:
                    if pat in value:
                        ext_list = re.search(value, response)
                        if ext_list:
                            if pat in [r'(\d+)', r'(\d*)']:
                                extract_date = {key: int(ext_list.group(1))}
                            else:
                                extract_date = {key: ext_list.group(1)}
                            logs.info('正则提取到的参数：%s' % extract_date)
                            self.read.write_yaml_data(extract_date)
                            break  # 找到匹配就跳出循环
                
                # 处理json提取参数
                if "$" in value:
                    try:
                        ext_json = jsonpath.jsonpath(json.loads(response), value)
                        if ext_json and len(ext_json) > 0:
                            extract_date = {key: ext_json[0]}
                        else:
                            extract_date = {key: "未提取到数据，该接口返回结果可能为空"}
                        logs.info('json提取到参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
                    except (IndexError, TypeError):
                        extract_date = {key: "未提取到数据，该接口返回结果可能为空"}
                        logs.info('json提取到参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
        except Exception as e:
            logs.error('接口返回值提取异常，请检查yaml文件extract表达式是否正确！错误信息：%s' % str(e))
    
    def extract_data_list(self, testcase_extract_list, response):
        """
        提取多个参数，支持正则表达式和json提取，提取结果以列表形式返回
        
        Args:
            testcase_extract_list: yaml文件中的extract_list信息
            response: 接口的实际返回值,str类型
            
        Returns:
            None，提取的数据会写入YAML文件
        """
        try:
            for key, value in testcase_extract_list.items():
                # 处理正则表达式提取
                if "(.+?)" in value or "(.*?)" in value:
                    ext_list = re.findall(value, response, re.S)
                    if ext_list:
                        extract_date = {key: ext_list}
                        logs.info('正则提取到的参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
                
                # 处理json提取参数
                if "$" in value:
                    try:
                        ext_json = jsonpath.jsonpath(json.loads(response), value)
                        if ext_json:
                            extract_date = {key: ext_json}
                        else:
                            extract_date = {key: "未提取到数据，该接口返回结果可能为空"}
                        logs.info('json提取到参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
                    except Exception:
                        extract_date = {key: "未提取到数据，该接口返回结果可能为空"}
                        logs.info('json提取到参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
        except Exception as e:
            logs.error('接口返回值提取异常，请检查yaml文件extract_list表达式是否正确！错误信息：%s' % str(e)) 