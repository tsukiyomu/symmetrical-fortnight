# -*- coding: utf-8 -*-
"""
YAML数据处理工具类
用于处理YAML文件中的变量替换等公共逻辑
"""
import json
import traceback
from common.TestDataUtils import TestDataUtils
from common.recordlog import logs


class YamlUtils:
    """YAML数据处理工具类"""
    
    @staticmethod
    def replace_load(data, handler_yaml_list_func=None):
        """
        YAML数据替换解析的公共方法
        
        Args:
            data: 需要替换的数据
            handler_yaml_list_func: 可选的YAML列表处理函数，用于业务场景的特殊处理
            
        Returns:
            替换后的数据
        """
        str_data = data
        if not isinstance(data, str):
            str_data = json.dumps(data, ensure_ascii=False)
            
        for i in range(str_data.count('${')):
            if '${' in str_data and '}' in str_data:
                # 找到变量开始和结束位置
                start_index = str_data.index('$')
                end_index = str_data.index('}', start_index)
                # 提取完整的变量表达式，如：${get_yaml_data(loginname)}
                ref_all_params = str_data[start_index:end_index + 1]
                # 提取函数名
                func_name = ref_all_params[2:ref_all_params.index("(")]
                # 提取函数参数
                func_params = ref_all_params[ref_all_params.index("(") + 1:ref_all_params.index(")")]
                # 动态调用TestDataUtils中的方法获取替换值
                extract_data = getattr(TestDataUtils(), func_name)(*func_params.split(',') if func_params else "")
                
                # 处理列表类型的返回值
                if extract_data and isinstance(extract_data, list):
                    extract_data = ','.join(str(e) for e in extract_data)
                    
                # 执行替换
                str_data = str_data.replace(ref_all_params, str(extract_data))
        
        # 还原数据
        if data and isinstance(data, dict):
            data = json.loads(str_data)
            # 如果提供了YAML列表处理函数，则调用它
            if handler_yaml_list_func:
                data = handler_yaml_list_func(data)
        else:
            data = str_data
            
        return data
    
    @staticmethod
    def handler_yaml_list(data_dict):
        """
        处理YAML文件测试用例请求参数为list情况，以数组形式
        
        Args:
            data_dict: 需要处理的数据字典
            
        Returns:
            处理后的数据字典
        """
        try:
            for key, value in data_dict.items():
                if isinstance(value, list):
                    value_lst = ','.join(str(v) for v in value).split(',')
                    data_dict[key] = value_lst
            return data_dict
        except Exception:
            logs.error(str(traceback.format_exc()))
            return data_dict