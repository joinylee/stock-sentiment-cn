#!/usr/bin/env python3
"""
获取同花顺市场数据 - 优化版
使用共享模块: 错误处理、日志
"""

import subprocess
import json
import sys
import os
import re
import requests
import time
from datetime import datetime

# 🚀 使用共享模块
# 添加 shared 目录到 Python 路径
shared_dir = os.path.expanduser("~/.openclaw/workspace/shared")
sys.path.insert(0, shared_dir)

from error_handler import handle_errors, retry
from logger import setup_logger

logger = setup_logger(__name__)

@handle_errors(default_return={})
@retry(max_retries=3, delay=1)
def get_market_index():
    """获取大盘指数 - 腾讯API"""
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
                logger.info(f"获取 {name}: {result[-1]['price']:.2f}")
        except Exception as e:
            logger.error(f"获取 {name} 失败: {e}")
        
        time.sleep(0.3)
    
    return result

@handle_errors(default_return={})
def parse_aria_tree(text):
    """解析 ARIA 格式的 Accessibility Tree"""
    
    data = {
        'up_count': None,
        'down_count': None,
        '涨停': None,
        '跌停': None,
        '昨日涨停收益': None,
        '大盘评级': None,
        '大盘建议': None,
        'indices': [],
        'fetched_at': datetime.now().isoformat(),
        'source': '10jqka_browser'
    }
    
    static_texts = re.findall(r'StaticText "([^"]+)"', text)
    
    for line in static_texts:
        if '上涨' in line and '只' in line:
            match = re.search(r'上涨[：:]\s*(\d+)', line)
            if match:
                data['up_count'] = int(match.group(1))
        if '下跌' in line and '只' in line:
            match = re.search(r'下跌[：:]\s*(\d+)', line)
            if match:
                data['down_count'] = int(match.group(1))
        if '涨停' in line and '只' in line:
            match = re.search(r'涨停[：:]\s*(\d+)', line)
            if match:
                data['涨停'] = int(match.group(1))
        if '跌停' in line and '只' in line:
            match = re.search(r'跌停[：:]\s*(\d+)', line)
            if match:
                data['跌停'] = int(match.group(1))
        if '今收益' in line:
            match = re.search(r'今收益[：:]\s*([+-]?\d+\.?\d*)%?', line)
            if match:
                data['昨日涨停收益'] = float(match.group(1))
        
        if '建议' in line and static_texts.index(line) + 1 < len(static_texts):
            next_line = static_texts[static_texts.index(line) + 1]
            if next_line and len(next_line) <= 20:
                data['大盘建议'] = next_line.strip()
    
    return data

@handle_errors(default_return={})
def fetch_browser_data():
    """获取市场数据"""
    logger.info("开始通过 Browser 获取数据")
    
    try:
        cmd = [
            'openclaw', 'browser', 'snapshot',
            '--format', 'aria'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"获取快照失败: {result.stderr}")
            return {}
        
        data = parse_aria_tree(result.stdout)
        logger.info(f"Browser数据获取完成: 上涨{data.get('up_count')}只")
        
        return data
        
    except Exception as e:
        logger.error(f"Browser获取异常: {e}")
        return {}

@handle_errors()
def save_data(data):
    """保存数据到JSON文件"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, 'market_data.json')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"数据已保存: {filepath}")

@handle_errors()
def main():
    """主函数"""
    logger.info("🔍 开始获取市场数据...")
    
    data = fetch_browser_data()
    
    if data:
        logger.info("📈 获取大盘指数...")
        indices = get_market_index()
        data['indices'] = indices
        
        save_data(data)
        
        logger.info(f"✅ 数据获取成功:")
        logger.info(f"  上涨: {data.get('up_count', 'N/A')} 只")
        logger.info(f"  下跌: {data.get('down_count', 'N/A')} 只")
        logger.info(f"  涨停: {data.get('涨停', 'N/A')} 只")
        
        for idx in indices:
            logger.info(f"  {idx['name']}: {idx['price']:.2f}")
    else:
        logger.error("❌ 获取数据失败")

if __name__ == '__main__':
    main()
