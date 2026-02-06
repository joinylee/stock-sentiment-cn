#!/usr/bin/env python3
"""
A股市场情绪分析报告 - 优化版 V2
优化点:
- 并发请求提速 (ThreadPoolExecutor)
- 多数据源备份 (腾讯API主 + 东方财富备)
- 缓存机制 (5分钟TTL)
- 更新自选股池 (11只)
"""

import sys
import json
import subprocess
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import time
import os

# 🚀 使用共享模块
shared_dir = os.path.expanduser("~/.openclaw/workspace/shared")
sys.path.insert(0, shared_dir)

from config_loader import config
from error_handler import handle_errors, retry
from logger import setup_logger

logger = setup_logger(__name__)

# 配置
TELEGRAM_BOT_TOKEN = config.get('telegram_bot_token') or "8577720778:AAFnet0gNmJESRwhUihHPdBO4UNjFkS7Iqs"
TELEGRAM_CHAT_ID = config.get('telegram_chat_id') or "8338565544"
WHATSAPP_TARGET = config.get('whatsapp_target') or "+8613382188809"

# 自选股池 - 11只 (根据用户最新持仓)
WATCHLIST = [
    ('002565', '顺灏股份', '题材股'),
    ('600118', '中国卫星', '卫星制造'),
    ('002155', '湖南黄金', '黄金'),
    ('300456', '赛微电子', '半导体'),
    ('600879', '航天电子', '军工航天'),
    ('603667', '五洲新春', '汽车零部件'),
    ('601869', '长飞光纤', '通信设备'),
    ('002112', '三变科技', '电气设备'),
    ('002361', '神剑股份', '化工'),
    ('002342', '巨力索具', '索具制造'),
    ('300136', '信维通信', '消费电子'),
]

# 大盘指数
INDICES = [
    ('sh000001', '上证指数'),
    ('sz399001', '深证成指'),
    ('sz399006', '创业板指'),
    ('sh000688', '科创50'),
]

# 内存缓存
cache = {}
CACHE_TTL = 300  # 5分钟

def get_cached(key, fetch_fn, *args, **kwargs):
    """带TTL的缓存"""
    now = time.time()
    if key in cache:
        value, timestamp = cache[key]
        if now - timestamp < CACHE_TTL:
            logger.debug(f"缓存命中: {key}")
            return value
    
    value = fetch_fn(*args, **kwargs)
    if value is not None:
        cache[key] = (value, now)
    return value

@handle_errors(default_return=None)
@retry(max_retries=2, delay=1)
def get_stock_price_tencent(code):
    """腾讯API获取股价 - 主数据源"""
    market = 'sh' if code.startswith('6') else 'sz'
    url = f"http://qt.gtimg.cn/q={market}{code}"
    
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    
    data = r.text.strip().split('~')
    if len(data) > 32:
        return {
            'name': data[1],
            'price': float(data[3]),
            'change': float(data[32]),
            'volume': int(data[36]) if len(data) > 36 else 0,
            'source': 'tencent'
        }
    return None

@handle_errors(default_return=None)
def get_stock_price_eastmoney(code):
    """东方财富API - 备份数据源"""
    try:
        market = 1 if code.startswith('6') else 0
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{code}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60"
        r = requests.get(url, timeout=5)
        data = r.json()
        
        if data.get('data'):
            d = data['data']
            price = d.get('f43', 0) / 100
            pre_close = d.get('f44', 0) / 100
            change = ((price - pre_close) / pre_close * 100) if pre_close else 0
            return {
                'name': d.get('f58', 'Unknown'),
                'price': price,
                'change': change,
                'volume': d.get('f47', 0),
                'source': 'eastmoney'
            }
    except Exception as e:
        logger.debug(f"东方财富API失败: {e}")
    return None

def get_stock_price(code, name=None):
    """获取股价 - 主备切换"""
    cache_key = f"stock_{code}"
    
    def fetch():
        # 先尝试腾讯
        data = get_stock_price_tencent(code)
        if data:
            # 如果name不匹配，修正它
            if name and data['name'] != name:
                data['name'] = name
            return data
        
        # 备用: 东方财富
        logger.warning(f"腾讯API失败，切换东方财富: {code}")
        data = get_stock_price_eastmoney(code)
        if data and name:
            data['name'] = name
        return data
    
    return get_cached(cache_key, fetch)

def fetch_index_single(code_name):
    """获取单个指数"""
    code, name = code_name
    cache_key = f"index_{code}"
    
    def fetch():
        try:
            url = f"http://qt.gtimg.cn/q={code}"
            r = requests.get(url, timeout=5)
            data = r.text.strip().split('~')
            if len(data) > 32:
                return {
                    'name': name,
                    'price': float(data[3]),
                    'change': float(data[32]),
                }
        except Exception as e:
            logger.error(f"获取 {name} 失败: {e}")
        return None
    
    return get_cached(cache_key, fetch)

def get_market_index_concurrent():
    """并发获取大盘指数"""
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_index_single, item): item for item in INDICES}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
                logger.info(f"获取指数 {result['name']}: {result['price']:.2f}")
    
    # 按原始顺序排序
    order_map = {item[1]: i for i, item in enumerate(INDICES)}
    results.sort(key=lambda x: order_map.get(x['name'], 99))
    return results

def get_watchlist_concurrent():
    """并发获取自选股"""
    results = []
    errors = []
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(get_stock_price, code, name): (code, name, sector)
            for code, name, sector in WATCHLIST
        }
        
        for future in as_completed(futures):
            code, name, sector = futures[future]
            try:
                data = future.result()
                if data:
                    results.append({
                        'code': code,
                        'name': name,
                        'sector': sector,
                        **data
                    })
                else:
                    errors.append((code, name))
            except Exception as e:
                logger.error(f"获取 {name} 异常: {e}")
                errors.append((code, name))
    
    # 按原始顺序排序
    order_map = {item[0]: i for i, item in enumerate(WATCHLIST)}
    results.sort(key=lambda x: order_map.get(x['code'], 99))
    
    return results, errors

@handle_errors(default_return={})
def load_market_data():
    """加载市场数据"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_file = os.path.join(script_dir, 'market_data.json')
    
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@handle_errors(default_return={})
def load_ths_data():
    """加载同花顺数据"""
    ths_file = '/tmp/all_funds.json'
    if os.path.exists(ths_file):
        with open(ths_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def format_ths_section(ths_data):
    """格式化同花顺数据板块"""
    if not ths_data or 'error' in ths_data:
        return ""
    
    lines = ["---", "## 🔥 同花顺资金流向", ""]
    
    # 概念资金
    if 'concept' in ths_data and ths_data['concept'].get('total', 0) > 0:
        concept = ths_data['concept']
        lines.append(f"### 📊 概念资金 ({concept.get('update_time', '')})")
        if concept.get('top_gainers'):
            lines.append("**资金流入 TOP 5:**")
            for item in concept['top_gainers'][:5]:
                lines.append(f"- {item['name']}: {item['change']:+.2f}% ({item['net']:.2f}亿)")
        if concept.get('top_losers'):
            lines.append("**资金流出 TOP 5:**")
            for item in concept['top_losers'][:5]:
                lines.append(f"- {item['name']}: {item['change']:.2f}% ({item['net']:.2f}亿)")
        lines.append("")
    
    # 行业资金
    if 'industry' in ths_data and ths_data['industry'].get('total', 0) > 0:
        industry = ths_data['industry']
        lines.append(f"### 🏭 行业资金 ({industry.get('update_time', '')})")
        if industry.get('top_gainers'):
            lines.append("**资金流入 TOP 5:**")
            for item in industry['top_gainers'][:5]:
                lines.append(f"- {item['name']}: {item['change']:+.2f}% ({item['net']:.2f}亿)")
        lines.append("")
    
    # 个股资金
    if 'stock' in ths_data and ths_data['stock'].get('total', 0) > 0:
        stock = ths_data['stock']
        lines.append(f"### 💰 个股资金 ({stock.get('update_time', '')})")
        if stock.get('top_net_inflow'):
            lines.append("**资金流入 TOP 10:**")
            for item in stock['top_net_inflow'][:10]:
                net_val = item['net']
                net_str = f"{net_val/10000:.1f}亿" if net_val >= 10000 else f"{net_val:.0f}万"
                lines.append(f"- {item['name']} ({item['code']}): {item['change']:+.2f}% ({net_str})")
        if stock.get('top_net_outflow'):
            lines.append("**资金流出 TOP 10:**")
            for item in stock['top_net_outflow'][:10]:
                net_val = item['net']
                net_str = f"{net_val/10000:.1f}亿" if net_val <= -10000 else f"{net_val:.0f}万"
                lines.append(f"- {item['name']} ({item['code']}): {item['change']:.2f}% ({net_str})")
        lines.append("")
    
    # 龙虎榜
    if 'longhu' in ths_data and 'detail' in ths_data['longhu']:
        longhu = ths_data['longhu']['detail']
        lines.append(f"### 🐲 龙虎榜个股 ({longhu.get('update_time', '')})")
        lines.append(f"共 {longhu.get('total', 0)} 只龙虎榜个股")
        
        gainers = [i for i in longhu.get('items', []) if i.get('change', 0) > 0]
        losers = [i for i in longhu.get('items', []) if i.get('change', 0) < 0]
        
        if gainers:
            lines.append("**涨幅榜:**")
            for item in gainers[:10]:
                lines.append(f"✅ {item['name']}: {item['change']:+.2f}%")
        if losers:
            lines.append("**跌幅榜:**")
            for item in losers[:10]:
                lines.append(f"❌ {item['name']}: {item['change']:.2f}%")
    
    return '\n'.join(lines)

def send_telegram(message):
    """发送到Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        resp = requests.post(url, json=data, timeout=10)
        resp.raise_for_status()
        logger.info("Telegram发送成功")
        return True
    except Exception as e:
        logger.error(f"Telegram发送失败: {e}")
        return False

def send_whatsapp(message):
    """发送到WhatsApp"""
    try:
        cmd = [
            'openclaw', 'message', 'send',
            '--channel', 'whatsapp',
            '--target', WHATSAPP_TARGET,
            '--message', message
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info("WhatsApp发送成功")
            return True
        else:
            logger.error(f"WhatsApp发送失败: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"WhatsApp异常: {e}")
        return False

def format_report_optimized(market_data):
    """生成完整报告 - 优化版"""
    start_time = time.time()
    now = datetime.now()
    
    logger.info("开始并发获取数据...")
    
    # 并发获取指数和自选股
    with ThreadPoolExecutor(max_workers=2) as executor:
        indices_future = executor.submit(get_market_index_concurrent)
        watchlist_future = executor.submit(get_watchlist_concurrent)
        
        indices = indices_future.result()
        watchlist_data, watchlist_errors = watchlist_future.result()
    
    fetch_time = time.time() - start_time
    logger.info(f"数据获取完成: {fetch_time:.2f}秒")
    
    # 指数
    index_lines = []
    for idx in indices:
        emoji = "📈" if idx['change'] > 0 else "📉"
        index_lines.append(f"{idx['name']}: {idx['price']:.2f} {emoji} {idx['change']:+.2f}%")
    
    # 涨跌统计
    if market_data.get('source') == '10jqka_browser':
        stats_lines = [
            f"📈 **上涨**: {market_data.get('up_count', 'N/A')} 只",
            f"📉 **下跌**: {market_data.get('down_count', 'N/A')} 只",
            f"🚀 **涨停**: {market_data.get('涨停', 'N/A')} 只",
            f"⚠️ **跌停**: {market_data.get('跌停', 'N/A')} 只",
        ]
    else:
        stats_lines = ["⚠️ 涨跌统计: 数据获取失败"]
    
    # 自选股
    watchlist_lines = []
    gainers = [s for s in watchlist_data if s['change'] > 0]
    losers = [s for s in watchlist_data if s['change'] < 0]
    
    for stock in watchlist_data:
        emoji = "🟢" if stock['change'] > 0 else "🔴" if stock['change'] < 0 else "➖"
        source_tag = ""
        if stock.get('source') == 'eastmoney':
            source_tag = " [东财]"
        watchlist_lines.append(
            f"{emoji} {stock['name']} ({stock['code']}): "
            f"¥{stock['price']:.2f} {stock['change']:+.2f}%{source_tag}"
        )
    
    # 显示失败的股票
    for code, name in watchlist_errors:
        watchlist_lines.append(f"⚠️ {name} ({code}): 数据获取失败")
    
    # 自选股统计
    watchlist_stats = f"\n**统计**: 🟢 {len(gainers)}只 | 🔴 {len(losers)}只 | ➖ {len(watchlist_data)-len(gainers)-len(losers)}只"
    
    # 加载同花顺数据
    ths_data = load_ths_data()
    ths_section = format_ths_section(ths_data)
    
    total_time = time.time() - start_time
    logger.info(f"报告生成完成: {total_time:.2f}秒")
    
    report = f"""# 📊 A股市场情绪分析报告 (V2优化版)

**{now.strftime('%Y-%m-%d %H:%M')}**
*数据源: 腾讯API + 东方财富备 + 同花顺Browser*
*生成耗时: {total_time:.1f}秒 ⚡*

---

## 📊 市场涨跌统计

{chr(10).join(stats_lines)}

---

## 📈 大盘指数

{chr(10).join(index_lines)}

---

## 💼 您的自选股 ({len(watchlist_data)}/{len(WATCHLIST)})

{chr(10).join(watchlist_lines)}
{watchlist_stats}

{chr(10).join(['', ths_section]) if ths_section else ''}

---
*报告生成: {now.strftime('%Y-%m-%d %H:%M:%S')} | V2并发优化*
"""
    
    return report

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--dual', action='store_true', help='双通道发送')
    parser.add_argument('--test', action='store_true', help='测试模式')
    args = parser.parse_args()
    
    logger.info("=" * 50)
    logger.info("开始生成A股情绪分析报告 (V2优化版)")
    logger.info("=" * 50)
    
    # 加载数据
    market_data = load_market_data()
    
    if not market_data:
        logger.warning("未找到同花顺市场数据")
    
    # 生成报告
    report = format_report_optimized(market_data)
    print(report)
    
    if args.test:
        logger.info("测试模式，不发送")
        return
    
    if args.dual:
        logger.info("开始双通道发送")
        send_telegram(report)
        send_whatsapp(report)
    
    logger.info("=" * 50)

if __name__ == '__main__':
    main()
