import traceback
import allure
import jsonpath
import operator
import time
from typing import Dict, Any, List, Optional, Union, Callable
from enum import Enum
from dataclasses import dataclass

from common.recordlog import logs
from common.connection import ConnectMysql


class AssertionType(Enum):
    """断言类型枚举"""
    CONTAINS = "contains"
    EQUAL = "eq"
    NOT_EQUAL = "ne"
    RESPONSE_VALUE = "rv"
    DATABASE = "db"


class BusinessErrorType(Enum):
    """业务错误类型枚举"""
    NETWORK_ERROR = "network_error"           # 网络错误
    TIMEOUT_ERROR = "timeout_error"           # 超时错误
    AUTH_ERROR = "auth_error"                 # 认证错误
    PERMISSION_ERROR = "permission_error"     # 权限错误
    DATA_ERROR = "data_error"                 # 数据错误
    BUSINESS_LOGIC_ERROR = "business_logic_error"  # 业务逻辑错误
    SYSTEM_ERROR = "system_error"             # 系统错误


@dataclass
class BusinessError:
    """业务错误信息"""
    error_type: BusinessErrorType
    error_code: str
    error_message: str
    retryable: bool = False
    max_retries: int = 3
    retry_delay: float = 1.0


class AssertionError(Exception):
    """自定义断言异常"""
    pass


class BusinessAssertionError(AssertionError):
    """业务断言异常"""
    def __init__(self, business_error: BusinessError, original_exception: Optional[Exception] = None):
        self.business_error = business_error
        self.original_exception = original_exception
        super().__init__(f"{business_error.error_type.value}: {business_error.error_message}")


class Assertions:
    """
    接口断言模式，支持
    1）响应文本字符串包含模式断言
    2）响应结果相等断言
    3）响应结果不相等断言
    4）响应结果任意值断言
    5）数据库断言
    6）业务流程错误预判和处理
    """

    def __init__(self):
        # 断言策略映射
        self._assertion_strategies = {
            AssertionType.CONTAINS: self.contains_assert,
            AssertionType.EQUAL: self.equal_assert,
            AssertionType.NOT_EQUAL: self.not_equal_assert,
            AssertionType.RESPONSE_VALUE: self.assert_response_any,
            AssertionType.DATABASE: self.assert_mysql_data
        }
        
        # 业务错误码映射
        self._business_error_mapping = {
            "400": BusinessError(BusinessErrorType.DATA_ERROR, "400", "请求参数错误"),
            "401": BusinessError(BusinessErrorType.AUTH_ERROR, "401", "认证失败", retryable=True),
            "403": BusinessError(BusinessErrorType.PERMISSION_ERROR, "403", "权限不足"),
            "404": BusinessError(BusinessErrorType.DATA_ERROR, "404", "资源不存在"),
            "408": BusinessError(BusinessErrorType.TIMEOUT_ERROR, "408", "请求超时", retryable=True, max_retries=5),
            "429": BusinessError(BusinessErrorType.SYSTEM_ERROR, "429", "请求频率过高", retryable=True, retry_delay=2.0),
            "500": BusinessError(BusinessErrorType.SYSTEM_ERROR, "500", "服务器内部错误", retryable=True),
            "502": BusinessError(BusinessErrorType.NETWORK_ERROR, "502", "网关错误", retryable=True),
            "503": BusinessError(BusinessErrorType.SYSTEM_ERROR, "503", "服务不可用", retryable=True),
            "504": BusinessError(BusinessErrorType.TIMEOUT_ERROR, "504", "网关超时", retryable=True),
        }
        
        # 业务逻辑错误码映射
        self._business_logic_errors = {
            "USER_NOT_FOUND": BusinessError(BusinessErrorType.DATA_ERROR, "USER_NOT_FOUND", "用户不存在"),
            "INVALID_TOKEN": BusinessError(BusinessErrorType.AUTH_ERROR, "INVALID_TOKEN", "无效的令牌", retryable=True),
            "INSUFFICIENT_BALANCE": BusinessError(BusinessErrorType.BUSINESS_LOGIC_ERROR, "INSUFFICIENT_BALANCE", "余额不足"),
            "ORDER_NOT_FOUND": BusinessError(BusinessErrorType.DATA_ERROR, "ORDER_NOT_FOUND", "订单不存在"),
            "PRODUCT_OUT_OF_STOCK": BusinessError(BusinessErrorType.BUSINESS_LOGIC_ERROR, "PRODUCT_OUT_OF_STOCK", "商品库存不足"),
        }

    # ===== 初始化和配置方法 =====
    
    def add_business_error_mapping(self, error_code: str, business_error: BusinessError) -> None:
        """添加自定义业务错误映射"""
        self._business_error_mapping[error_code] = business_error

    def add_business_logic_error(self, error_code: str, business_error: BusinessError) -> None:
        """添加自定义业务逻辑错误"""
        self._business_logic_errors[error_code] = business_error

    # ===== 内部工具方法 =====
    
    def _get_business_error(self, status_code: int, response_data: Optional[Dict] = None) -> Optional[BusinessError]:
        """根据状态码和响应数据获取业务错误信息"""
        # 检查HTTP状态码
        if str(status_code) in self._business_error_mapping:
            return self._business_error_mapping[str(status_code)]
        
        # 检查业务逻辑错误码
        if response_data and isinstance(response_data, dict):
            error_code = response_data.get('error_code') or response_data.get('code')
            if error_code and error_code in self._business_logic_errors:
                return self._business_logic_errors[error_code]
        
        return None

    def _handle_business_error(self, business_error: BusinessError, retry_func: Callable, *args, **kwargs) -> Any:
        """处理业务错误，支持重试机制"""
        if not business_error.retryable:
            raise BusinessAssertionError(business_error)
        
        for attempt in range(business_error.max_retries):
            try:
                logs.info(f"第{attempt + 1}次尝试执行断言")
                return retry_func(*args, **kwargs)
            except Exception as e:
                logs.warning(f"第{attempt + 1}次尝试失败: {e}")
                if attempt < business_error.max_retries - 1:
                    time.sleep(business_error.retry_delay)
                else:
                    raise BusinessAssertionError(business_error, e)

    def _pre_check_response(self, response: Dict[str, Any], status_code: int) -> None:
        """响应预检查，识别业务错误"""
        business_error = self._get_business_error(status_code, response)
        if business_error:
            logs.warning(f"检测到业务错误: {business_error.error_message}")
            if not business_error.retryable:
                raise BusinessAssertionError(business_error)

    def _safe_jsonpath_extract(self, response: Dict[str, Any], path: str) -> List[Any]:
        """彻底解决JSONPath不确定性"""
        try:
            result = jsonpath.jsonpath(response, path)
            
            # 处理 False/None 返回值
            if result is False or result is None:
                return []
            
            # 确保返回列表格式
            if not isinstance(result, list):
                return [result]
            
            # 展平嵌套列表
            flattened = []
            for item in result:
                if isinstance(item, list):
                    flattened.extend(item)  # 展平一层嵌套
                else:
                    flattened.append(item)
            
            return flattened
            
        except Exception as e:
            logs.error(f"JSONPath异常：{e}")
            return []

    def _universal_contains_check(self, extracted_values: List[Any], assert_value: Any) -> tuple[bool, str]:
        """通用的包含检查，处理所有类型"""
        processed_assert = None if str(assert_value).upper() == 'NONE' else assert_value
        
        for value in extracted_values:
            try:
                # None值特殊处理
                if processed_assert is None:
                    if value is None:
                        return True, f"匹配None值"
                    continue
                
                # 统一转字符串比较（最安全）
                value_str = str(value) if value is not None else "None"
                assert_str = str(processed_assert)
                
                if assert_str in value_str:
                    return True, f"匹配：{value} (类型：{type(value).__name__})"
                    
            except Exception as e:
                logs.warning(f"值比较异常：{value}, 错误：{e}")
                continue
        
        return False, f"无匹配，所有值：{extracted_values}"

    def _log_assertion_success(self, assertion_type: str, expected: Any, actual: Any) -> None:
        """记录断言成功日志"""
        allure.attach(
            f"预期结果：{expected}\n实际结果：{actual}", 
            f'{assertion_type}结果：成功',
            attachment_type=allure.attachment_type.TEXT
        )

    def _log_assertion_failure(self, assertion_type: str, expected: Any, actual: Any) -> None:
        """记录断言失败日志"""
        allure.attach(
            f"预期结果：{expected}\n实际结果：{actual}", 
            f'{assertion_type}结果：失败',
            attachment_type=allure.attachment_type.TEXT
        )

    # ===== 各种断言方法 =====
    
    def contains_assert(self, value: Dict[str, Any], response: Dict[str, Any], status_code: int) -> int:
        """
        字符串包含断言模式，断言预期结果的字符串是否包含在接口的响应信息中
        :param value: 预期结果，yaml文件的预期结果值
        :param response: 接口实际响应结果
        :param status_code: 响应状态码
        :return: 返回结果的状态标识，0成功，其他失败
        """
        # 预检查业务错误
        self._pre_check_response(response, status_code)
        
        flag = 0
        for assert_key, assert_value in value.items():
            if assert_key == "status_code":
                if assert_value != status_code:
                    flag += 1
                    self._log_assertion_failure("响应代码断言", assert_value, status_code)
                    logs.error(f"contains断言失败：接口返回码【{status_code}】不等于【{assert_value}】")
            else:
                # 使用优化的JSONPath提取
                extracted_values = self._safe_jsonpath_extract(response, f"$..{assert_key}")
                if not extracted_values:
                    flag += 1
                    self._log_assertion_failure("响应文本断言", assert_value, "未找到匹配字段")
                    logs.error(f"响应文本断言失败：未找到字段【{assert_key}】")
                    continue
                
                # 使用通用的包含检查
                success, message = self._universal_contains_check(extracted_values, assert_value)
                if success:
                    logs.info(f"字符串包含断言成功：{message}")
                else:
                    flag += 1
                    self._log_assertion_failure("响应文本断言", assert_value, extracted_values)
                    logs.error(f"响应文本断言失败：{message}")
        return flag

    def equal_assert(self, expected_results: Dict[str, Any], actual_results: Dict[str, Any], status_code: Optional[int] = None) -> int:
        """
        相等断言模式
        :param expected_results: 预期结果，yaml文件validation值
        :param actual_results: 接口实际响应结果
        :param status_code: 响应状态码（未使用）
        :return: 断言结果标识
        """
        if not isinstance(actual_results, dict) or not isinstance(expected_results, dict):
            raise TypeError('相等断言--类型错误，预期结果和接口实际响应结果必须为字典类型！')
        
        flag = 0
        # 找出实际结果与预期结果共同的key
        common_keys = list(expected_results.keys() & actual_results.keys())
        if not common_keys:
            flag += 1
            logs.error("相等断言失败：没有找到共同的键")
            return flag
            
        common_key = common_keys[0]
        new_actual_results = {common_key: actual_results[common_key]}
        
        if operator.eq(new_actual_results, expected_results):
            logs.info(f"相等断言成功：接口实际结果：{new_actual_results}，等于预期结果：{expected_results}")
            self._log_assertion_success("相等断言", expected_results, new_actual_results)
        else:
            flag += 1
            logs.error(f"相等断言失败：接口实际结果{new_actual_results}，不等于预期结果：{expected_results}")
            self._log_assertion_failure("相等断言", expected_results, new_actual_results)
        return flag

    def not_equal_assert(self, expected_results: Dict[str, Any], actual_results: Dict[str, Any], status_code: Optional[int] = None) -> int:
        """
        不相等断言模式
        :param expected_results: 预期结果，yaml文件validation值
        :param actual_results: 接口实际响应结果
        :param status_code: 响应状态码（未使用）
        :return: 断言结果标识
        """
        if not isinstance(actual_results, dict) or not isinstance(expected_results, dict):
            raise TypeError('不相等断言--类型错误，预期结果和接口实际响应结果必须为字典类型！')
        
        flag = 0
        # 找出实际结果与预期结果共同的key
        common_keys = list(expected_results.keys() & actual_results.keys())
        if not common_keys:
            flag += 1
            logs.error("不相等断言失败：没有找到共同的键")
            return flag
            
        common_key = common_keys[0]
        new_actual_results = {common_key: actual_results[common_key]}
        
        if operator.ne(new_actual_results, expected_results):
            logs.info(f"不相等断言成功：接口实际结果：{new_actual_results}，不等于预期结果：{expected_results}")
            self._log_assertion_success("不相等断言", expected_results, new_actual_results)
        else:
            flag += 1
            logs.error(f"不相等断言失败：接口实际结果{new_actual_results}，等于预期结果：{expected_results}")
            self._log_assertion_failure("不相等断言", expected_results, new_actual_results)
        return flag

    def assert_response_any(self, expected_results: Dict[str, Any], actual_results: Dict[str, Any]) -> int:
        """
        断言接口响应信息中的body的任何属性值
        :param expected_results: 预期结果，yaml文件的预期值
        :param actual_results: 接口实际响应信息
        :return: 返回标识,0表示测试通过，非0则测试失败
        """
        flag = 0
        try:
            # 支持多个键值对断言
            for exp_key, exp_value in expected_results.items():
                if exp_key in actual_results:
                    act_value = actual_results[exp_key]
                    # 支持JSONPath表达式
                    if isinstance(act_value, str) and act_value.startswith("$."):
                        extracted_values = self._safe_jsonpath_extract(actual_results, act_value)
                        if not extracted_values:
                            flag += 1
                            self._log_assertion_failure("响应文本断言", exp_value, "未找到匹配字段")
                            logs.error(f"响应文本断言失败：未找到字段【{exp_key}】")
                            continue
                        act_value = extracted_values[0]
                    
                    if operator.eq(act_value, exp_value):
                        self._log_assertion_success("响应结果任意值断言", exp_value, act_value)
                        logs.info(f"响应结果任意值断言成功：{exp_key}={act_value}")
                    else:
                        flag += 1
                        self._log_assertion_failure("响应结果任意值断言", exp_value, act_value)
                        logs.error(f"响应结果任意值断言失败：{exp_key}预期值={exp_value}，实际值={act_value}")
                else:
                    flag += 1
                    self._log_assertion_failure("响应结果任意值断言", exp_key, "未找到键")
                    logs.error(f"响应结果任意值断言失败：未找到键【{exp_key}】")
        except Exception as e:
            logs.error(f"响应结果任意值断言异常：{e}")
            logs.error(traceback.format_exc())
            raise AssertionError(f"响应结果任意值断言异常：{e}") from e
        return flag

    def assert_response_time(self, res_time: float, exp_time: float) -> bool:
        """
        通过断言接口的响应时间与期望时间对比,接口响应时间小于预期时间则为通过
        :param res_time: 接口的响应时间
        :param exp_time: 预期的响应时间
        :return: 断言结果
        """
        try:
            assert res_time < exp_time, f'接口响应时间[{res_time}s]大于预期时间[{exp_time}s]'
            return True
        except AssertionError:
            logs.error(f'接口响应时间[{res_time}s]大于预期时间[{exp_time}s]')
            raise

    def assert_mysql_data(self, expected_results: str) -> int:
        """
        数据库断言
        :param expected_results: 预期结果，yaml文件的SQL语句
        :return: 返回flag标识，0表示正常，非0表示测试不通过
        """
        flag = 0
        try:
            with ConnectMysql() as conn:
                db_value = conn.query_all(expected_results)
                if db_value is not None:
                    logs.info("数据库断言成功")
                else:
                    flag += 1
                    logs.error("数据库断言失败，请检查数据库是否存在该数据！")
        except Exception as e:
            flag += 1
            logs.error(f"数据库断言异常：{e}")
        return flag

    # ===== 主断言执行方法 =====
    
    def assert_result(self, expected: List[Dict[str, Any]], response: Dict[str, Any], status_code: int) -> None:
        """
        断言入口方法，负责整体断言流程控制和异常处理
        :param expected: 预期结果
        :param response: 实际响应结果
        :param status_code: 响应code码
        """
        all_flag = 0
        try:
            logs.info(f"yaml文件预期结果：{expected}")
            
            # 业务错误预检查
            business_error = self._get_business_error(status_code, response)
            if business_error and business_error.retryable:
                logs.info(f"检测到可重试的业务错误: {business_error.error_message}")
                return self._handle_business_error(business_error, self._execute_assertions, expected, response, status_code)
            
            return self._execute_assertions(expected, response, status_code)
                        
        except Exception as exceptions:
            logs.error('接口断言异常，请检查yaml预期结果值是否正确填写!')
            raise AssertionError(f'接口断言异常: {exceptions}') from exceptions

    def _execute_assertions(self, expected: List[Dict[str, Any]], response: Dict[str, Any], status_code: int) -> None:
        """
        具体断言执行方法，负责遍历并执行各种类型的断言
        与assert_result的关系：作为assert_result的辅助方法，在assert_result中被调用，
        专门负责断言的具体执行逻辑
        :param expected: 预期结果列表
        :param response: 实际响应结果
        :param status_code: 响应状态码
        """
        all_flag = 0
        
        # 遍历所有预期结果
        for yq in expected:
            # 遍历每个断言项
            for key, value in yq.items():
                try:
                    # 获取断言类型
                    assertion_type = AssertionType(key)
                    # 获取对应的断言策略
                    strategy = self._assertion_strategies.get(assertion_type)
                    
                    if strategy:
                        # 根据断言类型调用相应的断言方法
                        if assertion_type == AssertionType.RESPONSE_VALUE:
                            flag = strategy(actual_results=response, expected_results=value)
                        elif assertion_type == AssertionType.DATABASE:
                            flag = strategy(value)
                        else:
                            flag = strategy(value, response, status_code)
                        all_flag += flag
                    else:
                        logs.error(f"不支持的断言方式: {key}")
                except ValueError:
                    logs.error(f"不支持的断言类型: {key}")

        # 根据断言结果判断测试是否通过
        if all_flag == 0:
            logs.info("测试成功")
            assert True
        else:
            logs.error(f"测试失败，失败数量: {all_flag}")
            assert False
