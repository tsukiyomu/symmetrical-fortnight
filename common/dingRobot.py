import urllib.parse
import requests
import time
import hmac
import hashlib
import base64
from common.recordlog import logs


def generate_sign():
    """
    签名计算
    把timestamp+"\n"+密钥当做签名字符串，使用HmacSHA256算法计算签名，然后进行Base64 encode，
    最后再把签名参数再进行urlEncode，得到最终的签名（需要使用UTF-8字符集）
    :return: 返回当前时间戳、加密后的签名
    """
    # 当前时间戳
    timestamp = str(round(time.time() * 1000))
    # 钉钉机器人中的加签密钥
    secret = 'SEC93839e9bf7f21dcf119da06e3a8a7c2abbf15285324c9d50a707faca3fbeda6d'
    secret_enc = secret.encode('utf-8')
    str_to_sign = '{}\n{}'.format(timestamp, secret)
    # 转成byte类型
    str_to_sign_enc = str_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, str_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def send_dd_msg(content_str, at_all=True):
    """
    向钉钉机器人推送结果
    :param content_str: 发送的内容
    :param at_all: @全员，默认为True
    :return:
    """
    timestamp_and_sign = generate_sign()
    # url(钉钉机器人Webhook地址) + timestamp + sign
    url = f'https://oapi.dingtalk.com/robot/send?access_token=8f38193f5d2af46999717bf6fd5572e2a8b1fbec96f65fb28f158b27c06e975a&timestamp={timestamp_and_sign[0]}&sign={timestamp_and_sign[1]}'
    headers = {'Content-Type': 'application/json;charset=utf-8'}
    
    data = {
        "msgtype": "text",
        "text": {
            "content": content_str
        },
        "at": {
            "isAtAll": at_all
        },
    }
    try:
        logs.info("调用钉钉Webhook发送通知...")
        res = requests.post(url, json=data, headers=headers, timeout=10)
        logs.info(f"钉钉响应状态码: {res.status_code}")
        return res.text
    except Exception as ex:
        logs.error(f"调用钉钉Webhook失败: {ex}")
        raise
