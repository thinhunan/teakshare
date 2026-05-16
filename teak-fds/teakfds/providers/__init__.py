#!/usr/bin/env python3
"""
teakfds — 数据源 Provider 注册与按名加载。
"""

from __future__ import annotations

from teakfds.datasource_log import log_error

from teakfds.providers.base_provider import (
    BaseProvider,
    RealtimeProvider,
    HistoricalProvider,
    FinancialProvider,
    CompositeProvider,
    ProviderCapabilities,
)

__all__ = [
    "BaseProvider",
    "RealtimeProvider",
    "HistoricalProvider",
    "FinancialProvider",
    "CompositeProvider",
    "ProviderCapabilities",
    "get_all_providers",
    "get_provider_by_name",
]


def get_all_providers():
    """获取所有可用的 Provider（各模块自行 is_available）。"""
    providers = []

    try:
        from teakfds.providers.qlib_provider import get_qlib_provider

        p = get_qlib_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"qlib init error: {e}")

    try:
        from teakfds.providers.local_tdx_provider import get_local_tdx_provider

        p = get_local_tdx_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"local_tdx init error: {e}")

    try:
        from teakfds.providers.tencent_provider import get_tencent_provider

        p = get_tencent_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"tencent init error: {e}")

    try:
        from teakfds.providers.tdx_provider import get_tdx_provider

        p = get_tdx_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"tdx init error: {e}")

    try:
        from teakfds.providers.tushare_provider import tushare_provider

        if tushare_provider.is_available():
            providers.append(tushare_provider)
    except Exception as e:
        log_error(f"tushare init error: {e}")

    try:
        from teakfds.providers.lixinger_provider import get_lixinger_provider

        p = get_lixinger_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"lixinger init error: {e}")

    try:
        from teakfds.providers.sina_provider import get_sina_provider

        p = get_sina_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"sina init error: {e}")

    try:
        from teakfds.providers.xueqiu_provider import get_xueqiu_provider

        p = get_xueqiu_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"xueqiu init error: {e}")

    try:
        from teakfds.providers.mx_data_provider import get_mx_data_provider

        p = get_mx_data_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"mx_data init error: {e}")

    try:
        from teakfds.providers.mx_search_provider import get_mx_search_provider

        p = get_mx_search_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"mx_search init error: {e}")

    try:
        from teakfds.providers.search_fallback_provider import get_search_fallback_provider

        p = get_search_fallback_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"search_fallback init error: {e}")

    try:
        from teakfds.providers.aggregate_provider import get_aggregate_provider

        p = get_aggregate_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"aggregate init error: {e}")

    try:
        from teakfds.providers.iwencai_provider import get_iwencai_provider

        p = get_iwencai_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"iwencai init error: {e}")

    try:
        from teakfds.providers.cninfo_provider import get_cninfo_provider

        p = get_cninfo_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"cninfo init error: {e}")

    try:
        from teakfds.providers.baidu_provider import get_baidu_provider

        p = get_baidu_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"baidu init error: {e}")

    try:
        from teakfds.providers.ths_provider import get_ths_provider

        p = get_ths_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"ths init error: {e}")

    try:
        from teakfds.providers.eastmoney_provider import get_eastmoney_provider

        p = get_eastmoney_provider()
        if p.is_available():
            providers.append(p)
    except Exception as e:
        log_error(f"eastmoney init error: {e}")

    return providers


def get_provider_by_name(name: str):
    """根据名称获取 Provider（延迟导入）。"""
    try:
        if name == "qlib":
            from teakfds.providers.qlib_provider import get_qlib_provider

            return get_qlib_provider()
        if name == "local_tdx":
            from teakfds.providers.local_tdx_provider import get_local_tdx_provider

            return get_local_tdx_provider()
        if name == "tencent":
            from teakfds.providers.tencent_provider import get_tencent_provider

            return get_tencent_provider()
        if name == "tdx":
            from teakfds.providers.tdx_provider import get_tdx_provider

            return get_tdx_provider()
        if name == "tushare":
            from teakfds.providers.tushare_provider import tushare_provider

            return tushare_provider
        if name == "lixinger":
            from teakfds.providers.lixinger_provider import get_lixinger_provider

            return get_lixinger_provider()
        if name == "sina":
            from teakfds.providers.sina_provider import get_sina_provider

            return get_sina_provider()
        if name == "xueqiu":
            from teakfds.providers.xueqiu_provider import get_xueqiu_provider

            return get_xueqiu_provider()
        if name == "mx_search":
            from teakfds.providers.mx_search_provider import get_mx_search_provider

            return get_mx_search_provider()
        if name == "mx_data":
            from teakfds.providers.mx_data_provider import get_mx_data_provider

            return get_mx_data_provider()
        if name == "search_fallback":
            from teakfds.providers.search_fallback_provider import get_search_fallback_provider

            return get_search_fallback_provider()
        if name == "aggregate":
            from teakfds.providers.aggregate_provider import get_aggregate_provider

            return get_aggregate_provider()
        if name == "akshare":
            from teakfds.providers.aggregate_provider import get_akshare_provider

            return get_akshare_provider()
        if name == "iwencai":
            from teakfds.providers.iwencai_provider import get_iwencai_provider

            return get_iwencai_provider()
        if name == "cninfo":
            from teakfds.providers.cninfo_provider import get_cninfo_provider

            return get_cninfo_provider()
        if name == "baidu":
            from teakfds.providers.baidu_provider import get_baidu_provider

            return get_baidu_provider()
        if name == "ths":
            from teakfds.providers.ths_provider import get_ths_provider

            return get_ths_provider()
        if name == "eastmoney":
            from teakfds.providers.eastmoney_provider import get_eastmoney_provider

            return get_eastmoney_provider()
    except Exception as e:
        log_error(f"Provider {name} error: {e}")

    return None


if __name__ == "__main__":
    print("Available Providers:")
    for p in get_all_providers():
        print(f"  - {p.name}: {p.display_name} (priority={p.priority}, available={p.is_available()})")
