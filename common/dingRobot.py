import urllib.parse
import requests
import time
import hmac
import hashlib
import base64
import json
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

from common.recordlog import logs
from conf.operationConfig import OperationConfig

"""
dingRobot：钉钉群机器人
Author: tsukiyomi
"""
class MessageType(Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    LINK = "link"
    ACTION_CARD = "actionCard"
    FEED_CARD = "feedCard"


# 简化配置类，完全移除access_token
@dataclass
class DingTalkConfig:
    """钉钉机器人配置类

    配置与代码分离

    - 配置信息从外部读取，支持多环境配置
    - 仅支持加签方式，不使用access_token
    """
    webhook_url: str
    secret: str
    timeout: int = 10  # 超时时间可配置，默认10秒
    max_retries: int = 3  # 添加重试次数配置
    retry_delay: int = 2  # 重试延迟时间（秒）

    @classmethod
    def from_config(cls, config: Optional[OperationConfig] = None) -> 'DingTalkConfig':
        """从配置文件加载配置

        工厂方法模式
        - 提供工厂方法，支持多种配置来源
        """
        config = config or OperationConfig()
        try:
            return cls(
                webhook_url=config.get_section_for_data('DINGTALK', 'webhook_url'),
                secret=config.get_section_for_data('DINGTALK', 'secret'),
                timeout=int(config.get_section_for_data('DINGTALK', 'timeout', '10')),
                max_retries=int(config.get_section_for_data('DINGTALK', 'max_retries', '3')),
                retry_delay=int(config.get_section_for_data('DINGTALK', 'retry_delay', '2'))
            )
        except Exception as e:
            logs.error(f"加载钉钉配置失败: {e}")
            # 配置加载失败时的降级处理
            raise ValueError(f"钉钉机器人配置不完整或格式错误: {e}")


class SignatureGenerator:
    """签名生成器

    单一职责原则
    - 独立签名生成逻辑，提高代码可测试性和复用性
    """

    @staticmethod
    def generate(secret: str) -> tuple[str, str]:
        """生成钉钉机器人签名
        Args:
            secret: 钉钉机器人密钥
        Returns:
            (timestamp, sign): 时间戳和签名的元组
        Raises:
            ValueError: 当密钥为空时
        """
        if not secret:
            raise ValueError("密钥不能为空")

        # 使用更精确的时间戳生成方式
        # 使用int直接截断，避免四舍五入
        timestamp = str(int(time.time() * 1000))

        # 使用f-string格式化，更简洁高效
        str_to_sign = f'{timestamp}\n{secret}'

        # 计算签名
        secret_enc = secret.encode('utf-8')
        str_to_sign_enc = str_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, str_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        return timestamp, sign

# 消息构建器基类，支持多种消息类型
class MessageBuilder(ABC):
    """消息构建器抽象基类
    策略模式
    - 使用策略模式，便于扩展不同消息类型
    """

    @abstractmethod
    def build(self, **kwargs) -> Dict[str, Any]:
        """构建消息体"""
        pass


class TextMessageBuilder(MessageBuilder):
    """文本消息构建器"""

    def build(
            self,
            content: str,
            at_mobiles: Optional[List[str]] = None,
            at_user_ids: Optional[List[str]] = None,
            is_at_all: bool = False
    ) -> Dict[str, Any]:
        """构建文本消息

        更灵活的@功能
        - 支持@指定手机号或用户ID

        Args:
            content: 消息内容
            at_mobiles: 需要@的手机号列表
            at_user_ids: 需要@的用户ID列表
            is_at_all: 是否@所有人

        Returns:
            消息字典
        """
        # 参数验证
        if not content:
            raise ValueError("消息内容不能为空")

        # 消息长度限制检查
        # 钉钉文本消息限制为2048个字符
        if len(content) > 2048:
            logs.warning(f"消息内容超过2048字符限制，将被截断: {len(content)}")
            content = content[:2045] + "..."

        message = {
            "msgtype": MessageType.TEXT.value,
            "text": {
                "content": content
            },
            "at": {
                "isAtAll": is_at_all
            }
        }

        # 动态添加@列表，避免空列表
        if at_mobiles:
            message["at"]["atMobiles"] = at_mobiles
        if at_user_ids:
            message["at"]["atUserIds"] = at_user_ids

        return message


class MarkdownMessageBuilder(MessageBuilder):
    """Markdown消息构建器 """

    def build(
            self,
            title: str,
            text: str,
            at_mobiles: Optional[List[str]] = None,
            at_user_ids: Optional[List[str]] = None,
            is_at_all: bool = False
    ) -> Dict[str, Any]:
        """构建Markdown消息"""
        if not title or not text:
            raise ValueError("标题和内容都不能为空")

        message = {
            "msgtype": MessageType.MARKDOWN.value,
            "markdown": {
                "title": title,
                "text": text
            },
            "at": {
                "isAtAll": is_at_all
            }
        }

        if at_mobiles:
            message["at"]["atMobiles"] = at_mobiles
        if at_user_ids:
            message["at"]["atUserIds"] = at_user_ids

        return message


class DingTalkBot:
    """钉钉机器人客户端"""
    def __init__(self, config: Optional[DingTalkConfig] = None):
        """初始化钉钉机器人
        依赖注入
        - 优化：支持外部注入配置，提高灵活性
        """
        self.config = config or DingTalkConfig.from_config()
        self.signature_generator = SignatureGenerator()

        # 使用消息构建器注册表，便于扩展新的消息类型
        self.message_builders: Dict[MessageType, MessageBuilder] = {
            MessageType.TEXT: TextMessageBuilder(),
            MessageType.MARKDOWN: MarkdownMessageBuilder(),
        }

        # 复用session，提高性能
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json;charset=utf-8'})

    def _build_url(self) -> str:
        """构建完整的Webhook URL
        URL构建逻辑独立
        - 独立成方法，便于测试和维护
        - 直接使用配置的webhook_url，仅添加签名参数
        """
        timestamp, sign = self.signature_generator.generate(self.config.secret)

        # 解析配置的webhook_url并添加签名参数
        parsed_url = urllib.parse.urlparse(self.config.webhook_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # 添加签名参数
        query_params['timestamp'] = timestamp
        query_params['sign'] = sign
        
        # 重新构建URL
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        new_url = urllib.parse.urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        
        return new_url

    def _send_with_retry(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息with重试机制

        添加重试机制
        - 添加指数退避重试，提高可靠性
        """
        last_exception = None

        for attempt in range(self.config.max_retries):
            try:
                # 每次重试重新生成签名，避免签名过期问题
                url = self._build_url()

                logs.info(f"发送钉钉消息，第{attempt + 1}次尝试...")
                response = self.session.post(
                    url,
                    json=message,
                    timeout=self.config.timeout
                )

                # 状态码检查
                response.raise_for_status()

                # 解析响应并验证
                result = response.json()

                # 钉钉API返回码检查
                # 钉钉成功返回 {"errcode": 0, "errmsg": "ok"}
                if result.get('errcode') == 0:
                    logs.info(f"钉钉消息发送成功: {result}")
                    return result
                else:
                    # 详细的错误信息
                    error_msg = f"钉钉API返回错误: errcode={result.get('errcode')}, errmsg={result.get('errmsg')}"
                    logs.error(error_msg)

                    # 以下错误不应重试
                    # 例如：关键词不匹配(310000)、IP不在白名单(310000)等
                    non_retryable_codes = [310000, 400001, 400002]
                    if result.get('errcode') in non_retryable_codes:
                        raise ValueError(error_msg)

                    last_exception = Exception(error_msg)

            except requests.exceptions.Timeout as e:
                logs.warning(f"请求超时 (尝试 {attempt + 1}/{self.config.max_retries}): {e}")
                last_exception = e

            except requests.exceptions.RequestException as e:
                logs.warning(f"网络请求失败 (尝试 {attempt + 1}/{self.config.max_retries}): {e}")
                last_exception = e

            except json.JSONDecodeError as e:
                logs.error(f"响应解析失败: {e}")
                last_exception = e

            except ValueError:
                # 不可重试的错误，直接抛出
                raise

            # 指数退避策略
            if attempt < self.config.max_retries - 1:
                delay = self.config.retry_delay * (2 ** attempt)
                logs.info(f"等待{delay}秒后重试...")
                time.sleep(delay)

        # 所有重试都失败
        raise Exception(f"发送钉钉消息失败，已重试{self.config.max_retries}次: {last_exception}")

    def send_text(
            self,
            content: str,
            at_mobiles: Optional[List[str]] = None,
            at_user_ids: Optional[List[str]] = None,
            is_at_all: bool = False
    ) -> bool:
        """发送文本消息

        Args:
            content: 消息内容
            at_mobiles: 需要@的手机号列表
            at_user_ids: 需要@的用户ID列表
            is_at_all: 是否@所有人

        Returns:
            是否发送成功
        """
        try:
            builder = self.message_builders[MessageType.TEXT]
            message = builder.build(
                content=content,
                at_mobiles=at_mobiles,
                at_user_ids=at_user_ids,
                is_at_all=is_at_all
            )

            result = self._send_with_retry(message)
            return result.get('errcode') == 0

        except Exception as e:
            logs.error(f"发送文本消息失败: {e}")
            return False

    def send_markdown(
            self,
            title: str,
            text: str,
            at_mobiles: Optional[List[str]] = None,
            at_user_ids: Optional[List[str]] = None,
            is_at_all: bool = False
    ) -> bool:
        """发送Markdown消息 """
        try:
            builder = self.message_builders[MessageType.MARKDOWN]
            message = builder.build(
                title=title,
                text=text,
                at_mobiles=at_mobiles,
                at_user_ids=at_user_ids,
                is_at_all=is_at_all
            )

            result = self._send_with_retry(message)
            return result.get('errcode') == 0

        except Exception as e:
            logs.error(f"发送Markdown消息失败: {e}")
            return False

    def send_test_report(
            self,
            total: int,
            success: int,
            failed: int,
            error: int,
            duration: Optional[float] = None,
            is_at_all: bool = True
    ) -> bool:
        """发送测试报告"""
        # 计算通过率
        executed = success + failed + error
        pass_rate = f"{(success / executed * 100):.2f}%" if executed > 0 else "N/A"

        # 使用Markdown格式化测试报告
        title = "接口测试报告"

        # 根据测试结果使用不同的emoji
        status_emoji = "✅" if failed == 0 and error == 0 else "❌"

        text = f"""## {status_emoji} 接口自动化测试报告

### 📊 测试概况
- **总用例数**: {total}
- **执行用例数**: {executed}
- **通过数**: {success} ✅
- **失败数**: {failed} ❌
- **错误数**: {error} ⚠️

### 📈 执行统计
- **通过率**: {pass_rate}
- **执行时间**: {f'{duration:.2f}秒' if duration else 'N/A'}
- **测试时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}

### 📝 详情
> 详细测试结果请查看测试报告附件
"""

        return self.send_markdown(title, text, is_at_all=is_at_all)

    def __enter__(self):
        """上下文管理器入口
        支持上下文管理器
        - 支持with语句，自动管理资源
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，关闭会话"""
        self.session.close()


# 保持向后兼容的函数接口
# - 提供兼容函数，同时建议使用新接口
def send_dd_msg(content_str: str, at_all: bool = True) -> str:
    """向钉钉机器人推送结果（向后兼容接口）

    Args:
        content_str: 发送的内容
        at_all: @全员，默认为True

    Returns:
        响应文本
    """
    logs.warning("send_dd_msg函数已弃用，建议使用DingTalkBot类")

    try:
        bot = DingTalkBot()
        success = bot.send_text(content_str, is_at_all=at_all)
        return json.dumps({"success": success})
    except Exception as e:
        logs.error(f"发送钉钉消息失败: {e}")
        return json.dumps({"success": False, "error": str(e)})