"""账户与资金（只读）。

对应接口：
  AccountService/getAccountInfo   账户基本信息
  BalanceService/getBalanceInfo   账户余额与预算

注意：这两个接口需要账户管理类权限。当前若 scope 只有「工具」权限，
调用会返回权限错误——脚本会把 code / position 原样抛出，不要当成网络问题排查。
"""

from __future__ import annotations


def info(client, body=None):
    """账户基本信息。body 结构随账户类型不同，默认为空。"""
    return client.call("AccountService", "getAccountInfo", body or {})


def balance(client, body=None):
    """账户余额。返回结构含现金、赠款、预算等字段。"""
    return client.call("BalanceService", "getBalanceInfo", body or {})


def payment_record(client, body=None):
    """付款/充值记录。"""
    return client.call("PaymentService", "getPaymentRecord", body or {})
