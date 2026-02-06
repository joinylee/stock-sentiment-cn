#!/usr/bin/env python3
"""
A股市场情绪分析报告 - 完整版
整合：腾讯财经API + 同花顺Browser数据
使用共享模块: 配置加载、错误处理、日志
"""

import sys
import json
import subprocess
import requests
from datetime import datetime
import time
import os

# 🚀 使用共享模块
shared_dir = os.path.expanduser("~/.openclaw/workspace/shared")
sys.path.insert(0, shared_dir)

from config_loader import config
from error_handler import handle_errors, retry
from logger import setup_logger

logger = setup_logger(__name__)

# 配置从共享模块获取
TELEGRAM_BOT_TOKEN = config.get('telegram_bot_token') or "8577720778:AAFnet0gNmJESRwhUihHPdBO4UNjFkS7Iqs"
TELEGRAM_CHAT_ID = config.get('telegram_chat_id') or "8338565544"
WHATSAPP_TARGET = config.get('whatsapp_target') or "+8613382188809"

# 自选股
WATCHLIST = [
    ('300456', '赛微电子', '半导体'),
    ('600879', '航天电子', '军工航天'),
    ('300136', '信维通信', '消费电子'),
    ('301005', '超捷股份', '军工电子'),
]

@handle_errors(default_return=None)
@retry(max_retries=3, delay=2)
def get_stock_price(code):
    """获取实时股价"""
    market = 'sh' if code.startswith('6') else 'sz'
    url = f"http://qt.gtimg.cn/q={market}{code}"
    
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    
    data = r.text.strip().split('~')
    if len(data) > 32:
        return {
            'name': data[1],
            'price': float(data[3]),
            'change': float(data[32]),
        }
    return None

@handle_errors(default_return=[])
def get_market_index():
    """获取大盘指数"""
    indices = [
        ('sh000001', '上证指数'),
        ('sz399001', '深证成指'),
        ('sz399006', '创业板指'),
    ]
    result = []
    
    for code, name in indices:
        try:
            url = f"http://qt.gtimg.cn/q={code}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            
            data = r.text.strip().split('~')
            if len(data) > 32:
                result.append({
                    'name': name,
                    'price': float(data[3]),
                    'change': float(data[32]),
                })
                logger.info(f"获取指数 {name}: {result[-1]['price']:.2f}")
        except Exception as e:
            logger.error(f"获取 {name} 失败: {e}")
        
        time.sleep(0.5)
    
    return result

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

@handle_errors(default_return="")
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

@handle_errors(default_return="")
def format_report(market_data):
    """生成完整报告"""
    now = datetime.now()
    indices = get_market_index()
    
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
    for code, name, sector in WATCHLIST:
        data = get_stock_price(code)
        if data:
            emoji = "🟢" if data['change'] > 0 else "🔴"
            watchlist_lines.append(f"{emoji} {name} ({code}): ¥{data['price']:.2f} {data['change']:+.2f}%")
        else:
            watchlist_lines.append(f"⚠️ {name} ({code}): 数据获取失败")
    
    # 加载同花顺数据
    ths_data = load_ths_data()
    ths_section = format_ths_section(ths_data)
    
    report = f"""# 📊 A股市场情绪分析报告

**{now.strftime('%Y-%m-%d %H:%M')}**
*数据来源: 腾讯财经API + 同花顺Browser*

---

## 📊 市场涨跌统计

{chr(10).join(stats_lines)}

---

## 📈 大盘指数

{chr(10).join(index_lines)}

---

## 💼 您的自选股

{chr(10).join(watchlist_lines)}

{chr(10).join(['', ths_section]) if ths_section else ''}

---

*报告生成: {now.strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    return report

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--dual', action='store_true', help='双通道发送')
    args = parser.parse_args()
    
    logger.info("开始生成A股情绪分析报告")
    
    # 加载数据
    market_data = load_market_data()
    
    if not market_data:
        logger.warning("未找到市场数据")
    
    # 生成报告
    report = format_report(market_data)
    print(report)
    
    if args.dual:
        logger.info("开始双通道发送")
        send_telegram(report)
        send_whatsapp(report)

if __name__ == '__main__':
    main()
