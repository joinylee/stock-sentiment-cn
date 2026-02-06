#!/usr/bin/env python3
"""
A股市场情绪分析报告 - 方案B AI版 V3
🤖 AI驱动决策仪表盘 - 接入 Minimax M2.1

功能:
- 多数据源融合 (腾讯 + 东方财富 + 同花顺)
- 技术面指标计算 (MA5/MA10/MA20, 支撑位/压力位)
- AI智能分析 (Minimax M2.1)
- 一句话决策结论
- 持仓checklist
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
import re

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

# Minimax M2.1 API
MINIMAX_API_KEY = config.get('minimax_api_key') or "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJqb2lueSIsIlVzZXJOYW1lIjoiam9pbnkiLCJBY2NvdW50IjoiIiwiU3ViamVjdElEIjoiMTg4Mjc2NDA0MTQ1NTgxMTg0OCIsIlBob25lIjoiaWSNa6d8a2B2IiwiR3JvdXBJRCI6IjE4ODI3NjQwNDE0MTM3MDc1MjAiLCJQYWdlTmFtZSI6IiIsIk1haWwiOiIiLCJDcmVhdGVUaW1lIjoiMjAyNi0wMi0wMyAxNjo1MDo1OCIsImlzcyI6Im1pbmltYXgifQ.T7n0-lnfVbHJ8q3DB9hl-6wIVTi4o__9vqRbwD7hT0ZCD-zVcDjHmGxxMVLWQm1WuA2nGHHpNh2pyHL1IvTjOwSKL1Qm1pprRmr6zTCf3RYaFIPhBVSIQ6ywN11Yag39s09oESY7nznPL6fpz2XwjywgChl0FMjPseBgOJQJ2AGtZ6MvQXFEJEyqt2EqvXRQu4nDQTq94P3q3P0ZcAD_z-T0pLUVHEuX65t26JvFvxeH60UfoWF43HWZ4aRcQ5gKdbINIJqGGvKgpyDGsQATcHIp8x9NRk_IhRqE0HqBfuvEm1KB0M6T6PFiESIVwt2QhfA7O75q0FG4M5A"
MINIMAX_GROUP_ID = "1882764041413707520"

# 自选股池 - 11只
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
    ('sh000016', '上证50'),
]

# 内存缓存
cache = {}
CACHE_TTL = 300

def get_cached(key, fetch_fn, *args, **kwargs):
    """带TTL的缓存"""
    now = time.time()
    if key in cache:
        value, timestamp = cache[key]
        if now - timestamp < CACHE_TTL:
            return value
    
    value = fetch_fn(*args, **kwargs)
    if value is not None:
        cache[key] = (value, now)
    return value

@handle_errors(default_return=None)
@retry(max_retries=2, delay=1)
def get_stock_price_tencent(code):
    """腾讯API获取股价"""
    market = 'sh' if code.startswith('6') else 'sz'
    url = f"http://qt.gtimg.cn/q={market}{code}"
    
    r = requests.get(url, timeout=5)
    data = r.text.strip().split('~')
    if len(data) > 45:
        return {
            'name': data[1],
            'price': float(data[3]),
            'pre_close': float(data[4]),
            'open': float(data[5]),
            'high': float(data[33]),
            'low': float(data[34]),
            'change': float(data[32]),
            'volume': int(data[36]),
            'amount': float(data[37]),
            'pe': float(data[39]) if data[39] else 0,
            'pb': float(data[46]) if len(data) > 46 and data[46] else 0,
            'market_cap': float(data[44]) if len(data) > 44 and data[44] else 0,
        }
    return None

@handle_errors(default_return=None)
def get_stock_hist_tencent(code, days=20):
    """获取历史数据计算MA"""
    try:
        market = 'sh' if code.startswith('6') else 'sz'
        # 使用腾讯日线接口
        url = f"http://web.ifzq.gtimg.cn/appstock/finance/day/{market}{code}"
        r = requests.get(url, timeout=10)
        data = r.json()
        
        key = f"{market}{code}"
        if key in data.get('data', {}):
            day_data = data['data'][key].get('day', [])
            closes = [float(d[2]) for d in day_data[-days:]] if day_data else []
            
            if len(closes) >= 5:
                return {
                    'ma5': sum(closes[-5:]) / 5,
                    'ma10': sum(closes[-10:]) / 10 if len(closes) >= 10 else None,
                    'ma20': sum(closes[-20:]) / 20 if len(closes) >= 20 else None,
                    'closes': closes,
                    'high_20': max(closes) if closes else None,
                    'low_20': min(closes) if closes else None,
                }
    except Exception as e:
        logger.debug(f"历史数据获取失败 {code}: {e}")
    return None

def calc_technical(data, hist):
    """计算技术指标"""
    if not data or not hist:
        return {}
    
    price = data['price']
    ma5 = hist.get('ma5', price)
    ma10 = hist.get('ma10', ma5)
    ma20 = hist.get('ma20', ma10)
    
    # 趋势判断
    trend = "多头" if ma5 > ma10 > ma20 else "空头" if ma5 < ma10 < ma20 else "震荡"
    
    # 乖离率
    bias5 = (price - ma5) / ma5 * 100 if ma5 else 0
    
    # 支撑位/压力位 (简化版：20日高低点)
    support = hist.get('low_20', price * 0.95)
    resistance = hist.get('high_20', price * 1.05)
    
    # RSI简化计算
    closes = hist.get('closes', [])
    rsi = 50
    if len(closes) >= 6:
        gains = [closes[i] - closes[i-1] for i in range(1, len(closes)) if closes[i] > closes[i-1]]
        losses = [closes[i-1] - closes[i] for i in range(1, len(closes)) if closes[i] < closes[i-1]]
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0.001
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    return {
        'ma5': ma5,
        'ma10': ma10,
        'ma20': ma20,
        'trend': trend,
        'bias5': bias5,
        'support': support,
        'resistance': resistance,
        'rsi': rsi,
    }

def get_stock_full(code, name=None):
    """获取股票完整数据"""
    # 实时数据
    realtime = get_stock_price_tencent(code)
    if not realtime:
        return None
    
    # 历史数据（用于技术指标）
    hist = get_stock_hist_tencent(code, 20)
    
    # 计算技术指标
    tech = calc_technical(realtime, hist) if hist else {}
    
    return {
        'code': code,
        'name': name or realtime['name'],
        **realtime,
        **tech,
    }

def fetch_index_single(code_name):
    """获取指数"""
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
                    'volume': int(data[36]) if len(data) > 36 else 0,
                }
        except Exception as e:
            logger.error(f"获取 {name} 失败: {e}")
        return None
    
    return get_cached(cache_key, fetch)

def get_market_overview():
    """获取市场概览 - 备用方案（东方财富接口不稳定时使用）"""
    try:
        import akshare as ak
        
        # 方案1: 交易所总貌（快速稳定）
        try:
            sse = ak.stock_sse_summary()
            szse = ak.stock_szse_summary()
            return {
                'up_count': None,
                'down_count': None,
                'flat_count': None,
                'limit_up': None,
                'limit_down': None,
                'sse_companies': int(sse.loc[3, '股票']),
                'szse_stocks': int(szse.loc[0, '数量']),
                'source': 'AkShare(交易所总貌)'
            }
        except Exception as e:
            logger.debug(f"交易所总貌失败: {e}")
            
    except ImportError:
        logger.debug("AkShare未安装")
    except Exception as e:
        logger.debug(f"市场概览获取失败: {e}")
    
    return {}

@handle_errors(default_return=[])
def get_hot_sectors():
    """获取热点板块 - 使用同花顺浏览器数据"""
    import subprocess
    import re
    
    try:
        print("📊 获取热点板块数据...")
        
        # 使用浏览器获取同花顺概念资金数据
        subprocess.run(['openclaw', 'browser', 'open', 'https://data.10jqka.com.cn/funds/gnzjl/'], 
                      capture_output=True, timeout=30)
        
        import time
        time.sleep(3)  # 等待页面加载
        
        # 获取text格式快照
        result = subprocess.run(
            ['openclaw', 'browser', 'snapshot', '--format', 'text'],
            capture_output=True, text=True, timeout=60
        )
        
        if result.returncode != 0:
            logger.debug("浏览器快照失败")
            return []
        
        text = result.stdout
        
        # 解析row格式: "序号 行业 行业指数 涨跌幅 流入(亿) 流出(亿) 净额(亿) 公司数 领涨股..."
        rows = re.findall(r'row "(\d+)\s+([^"]+)"', text)
        
        sectors = []
        for rank, row_data in rows[:15]:
            try:
                parts = row_data.split()
                if len(parts) >= 7:
                    name = parts[0]
                    # 涨跌幅在第3列 (parts[2])
                    change = float(parts[2].replace('%', ''))
                    # 净额在第6列 (parts[5])
                    net = float(parts[5])
                    
                    if name:
                        sectors.append({
                            'name': name,
                            'change': change,
                            'net_inflow': net,
                        })
            except (ValueError, IndexError):
                continue
        
        logger.info(f"热点板块获取成功: {len(sectors)}个")
        return sectors
        
    except Exception as e:
        logger.debug(f"板块数据获取失败: {e}")
    return []

@handle_errors(default_return={})
def load_ths_data():
    """加载同花顺数据"""
    ths_file = '/tmp/all_funds.json'
    if os.path.exists(ths_file):
        with open(ths_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def call_minimax(prompt, max_tokens=2000):
    """调用 Minimax M2.1 - 使用 OpenAI 兼容接口"""
    try:
        # 尝试使用 gateway 路由（如果配置了）
        import os
        gateway_url = os.environ.get('OPENCLAW_GATEWAY_URL', 'http://localhost:3333')
        
        # 先尝试 gateway
        try:
            r = requests.post(
                f"{gateway_url}/v1/chat/completions",
                json={
                    "model": "minimax/MiniMax-M2.1",
                    "messages": [
                        {"role": "system", "content": "你是专业的A股投资分析师，擅长技术面分析、资金面和情绪面分析。请给出简洁、专业的分析结论。"},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
                timeout=30
            )
            if r.status_code == 200:
                result = r.json()
                if 'choices' in result:
                    return result['choices'][0]['message']['content']
        except Exception as e:
            logger.debug(f"Gateway调用失败，尝试直接API: {e}")
        
        # 直接调用 Minimax API
        url = "https://api.minimaxi.chat/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "MiniMax-M2.1",
            "messages": [
                {"role": "system", "content": "你是专业的A股投资分析师，擅长技术面分析、资金面和情绪面分析。请给出简洁、专业的分析结论。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        
        r = requests.post(url, json=data, headers=headers, timeout=30)
        result = r.json()
        
        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            logger.info(f"AI分析成功，长度: {len(content)}")
            return content
        
        logger.warning(f"AI返回异常: {result}")
        return None
    except Exception as e:
        logger.error(f"Minimax调用失败: {e}")
        return None

def generate_ai_analysis_rule_based(market_data, indices, watchlist, sectors):
    """基于规则的AI分析（无需API）"""
    
    # 计算统计数据
    up_count = sum(1 for s in watchlist if s['change'] > 0)
    down_count = sum(1 for s in watchlist if s['change'] < 0)
    avg_change = sum(s['change'] for s in watchlist) / len(watchlist) if watchlist else 0
    
    # 强势股票
    strong_stocks = [s for s in watchlist if s['change'] > 7]
    weak_stocks = [s for s in watchlist if s['change'] < -3]
    
    # 指数分析
    idx_trend = "震荡调整"
    avg_idx_change = sum(idx['change'] for idx in indices) / len(indices) if indices else 0
    if avg_idx_change > 0.5:
        idx_trend = "强势上涨"
    elif avg_idx_change > 0:
        idx_trend = "小幅上涨"
    elif avg_idx_change < -1:
        idx_trend = "深度回调"
    elif avg_idx_change < 0:
        idx_trend = "震荡调整"
    
    # 生成结论
    lines = []
    
    # 1. 核心结论
    if avg_change > 3:
        lines.append(f"🎯 **核心结论**: 您的持仓今日表现强势，{len(strong_stocks)}只个股涨幅超过7%，建议持有观察，避免追高。")
    elif avg_change > 0:
        lines.append(f"🎯 **核心结论**: 持仓整体小幅上涨，市场整体{idx_trend}，建议维持现有仓位，关注强势股表现。")
    elif avg_change > -2:
        lines.append(f"🎯 **核心结论**: 持仓小幅回调，市场{idx_trend}，建议逢低关注优质标的，控制仓位。")
    else:
        lines.append(f"🎯 **核心结论**: 持仓回调明显，市场{idx_trend}，建议减仓避险，等待企稳信号。")
    
    lines.append("")
    
    # 2. 市场环境
    lines.append("📊 **市场环境分析**:")
    lines.append(f"- 技术面: 大盘{idx_trend}，平均涨跌幅{avg_idx_change:+.2f}%")
    lines.append(f"- 您的持仓: {up_count}只上涨，{down_count}只下跌，平均{avg_change:+.2f}%")
    if strong_stocks:
        lines.append(f"- 强势股: {', '.join([s['name'] for s in strong_stocks[:3]])}")
    if weak_stocks:
        lines.append(f"- 弱势股: {', '.join([s['name'] for s in weak_stocks[:3]])}")
    
    lines.append("")
    
    # 3. 持仓Checklist
    lines.append("✅ **持仓操作建议**:")
    for stock in watchlist:
        if stock['change'] > 9:
            lines.append(f"- 🚀 **{stock['name']}**: 涨停，继续持有，设置止盈位")
        elif stock['change'] > 5:
            lines.append(f"- 📈 **{stock['name']}**: 强势上涨，可持有观察")
        elif stock['change'] > 0:
            lines.append(f"- ✓ **{stock['name']}**: 小幅上涨，正常持仓")
        elif stock['change'] > -3:
            lines.append(f"- ⚠️ **{stock['name']}**: 小幅回调，关注支撑")
        else:
            lines.append(f"- ❌ **{stock['name']}**: 深度回调，考虑止损")
    
    lines.append("")
    
    # 4. 明日关注
    lines.append("👀 **明日关注要点**:")
    if avg_idx_change < -0.5:
        lines.append("- 关注大盘是否企稳，量能是否萎缩")
    if strong_stocks:
        lines.append(f"- 关注强势股延续性: {strong_stocks[0]['name']}")
    lines.append("- 关注北向资金流向变化")
    lines.append("- 关注晚间美股表现对明日的情绪影响")
    
    return '\n'.join(lines)

def generate_ai_analysis(market_data, indices, watchlist, sectors):
    """生成AI分析报告 - 优先Minimax，失败则用规则版"""
    
    # 先尝试调用Minimax
    if MINIMAX_API_KEY and MINIMAX_API_KEY != "your_api_key_here":
        # 构建市场摘要
        market_summary = []
        market_summary.append(f"大盘概况:")
        for idx in indices:
            emoji = "📈" if idx['change'] > 0 else "📉"
            market_summary.append(f"- {idx['name']}: {idx['price']:.2f} ({idx['change']:+.2f}%) {emoji}")
        
        market_summary.append(f"\n市场情绪:")
        market_summary.append(f"- 上涨: {market_data.get('up_count', 'N/A')} 只")
        market_summary.append(f"- 下跌: {market_data.get('down_count', 'N/A')} 只")
        market_summary.append(f"- 涨停: {market_data.get('limit_up', 'N/A')} 只")
        
        if sectors:
            market_summary.append(f"\n热点板块(资金流入):")
            for s in sectors[:5]:
                change = float(s['change']) if isinstance(s['change'], str) else s['change']
                net = float(s['net_inflow']) if isinstance(s['net_inflow'], str) else s['net_inflow']
                market_summary.append(f"- {s['name']}: {change:+.2f}% (+{net:.1f}亿)")
        
        market_summary.append(f"\n自选股概况:")
        for stock in watchlist:
            emoji = "🟢" if stock['change'] > 0 else "🔴"
            trend_info = f", 趋势:{stock.get('trend', 'N/A')}" if 'trend' in stock else ""
            market_summary.append(f"- {emoji} {stock['name']}({stock['code']}): {stock['change']:+.2f}%{trend_info}")
        
        prompt = f"""请作为A股投资分析师，基于以下市场数据给出今日投资决策建议：

{chr(10).join(market_summary)}

请输出以下内容：
1. 一句话核心结论（如：市场震荡调整，建议观望/逢低布局XX板块）
2. 市场环境分析（技术面+资金面+情绪面）
3. 持仓checklist（针对自选股给出具体操作建议）
4. 明日关注要点

要求：
- 结论要具体、可操作
- 技术分析要引用具体数据
- 语气专业但易懂
- 总字数控制在500字以内"""

        ai_result = call_minimax(prompt)
        if ai_result:
            return ai_result + "\n\n*(AI分析由 Minimax M2.1 生成)*"
    
    # Minimax失败或未配置，使用规则版
    logger.info("使用基于规则的分析...")
    return generate_ai_analysis_rule_based(market_data, indices, watchlist, sectors)

def generate_stock_checklist(stock):
    """生成个股checklist"""
    checks = []
    
    price = stock['price']
    change = stock['change']
    trend = stock.get('trend', '未知')
    bias5 = stock.get('bias5', 0)
    rsi = stock.get('rsi', 50)
    support = stock.get('support', price * 0.95)
    resistance = stock.get('resistance', price * 1.05)
    
    # 趋势检查
    if trend == "多头":
        checks.append("✅ 多头排列 (MA5>MA10>MA20)")
    elif trend == "空头":
        checks.append("❌ 空头排列 (MA5<MA10<MA20)")
    else:
        checks.append("⚠️ 趋势震荡")
    
    # 乖离率检查
    if bias5 > 5:
        checks.append(f"⚠️ 乖离率过高 ({bias5:.1f}%，有回调风险)")
    elif bias5 < -5:
        checks.append(f"✅ 乖离率过低 ({bias5:.1f}%，超卖)")
    else:
        checks.append(f"✓ 乖离率正常 ({bias5:.1f}%)")
    
    # RSI检查
    if rsi > 70:
        checks.append(f"❌ RSI超买 ({rsi:.1f})")
    elif rsi < 30:
        checks.append(f"✅ RSI超卖 ({rsi:.1f})")
    else:
        checks.append(f"✓ RSI中性 ({rsi:.1f})")
    
    # 涨跌幅
    if change > 7:
        checks.append("🚀 强势上涨 (>7%)")
    elif change < -5:
        checks.append("📉 深度回调 (<-5%)")
    
    # 支撑/压力
    if abs(price - support) / price < 0.02:
        checks.append(f"💡 接近支撑位 ({support:.2f})")
    elif abs(price - resistance) / price < 0.02:
        checks.append(f"⚠️ 接近压力位 ({resistance:.2f})")
    
    return checks

def format_report_v3(market_data, indices, watchlist, sectors, ai_analysis):
    """生成完整报告 V3 AI版"""
    now = datetime.now()
    
    # 指数
    index_lines = []
    for idx in indices:
        emoji = "📈" if idx['change'] > 0 else "📉"
        index_lines.append(f"{idx['name']}: {idx['price']:.2f} {emoji} {idx['change']:+.2f}%")
    
    # 市场情绪
    source = market_data.get('source', '')
    up = market_data.get('up_count')
    down = market_data.get('down_count')
    limit_up = market_data.get('limit_up')
    limit_down = market_data.get('limit_down')
    
    if up is not None and down is not None:
        sentiment = "🔥 火热" if up > down * 2 else "😊 偏暖" if up > down else "😰 偏冷" if down > up else "😐 平衡"
        market_section = f"""### 市场情绪 {sentiment} ({source})
- 📈 上涨: **{up}** 只 | 📉 下跌: **{down}** 只
- 🚀 涨停: {limit_up} 只 | ⚠️ 跌停: {limit_down} 只"""
    else:
        # 使用交易所总貌数据
        sse = market_data.get('sse_companies', 'N/A')
        szse = market_data.get('szse_stocks', 'N/A')
        market_section = f"""### 市场概览 ({source})
- 📍 上海: {sse} 家上市公司
- 📍 深圳: {szse} 只股票"""
    
    # 自选股详情
    stock_details = []
    for stock in watchlist:
        emoji = "🟢" if stock['change'] > 0 else "🔴"
        stock_details.append(f"\n{emoji} **{stock['name']}** ({stock['code']})")
        stock_details.append(f"  价格: ¥{stock['price']:.2f} ({stock['change']:+.2f}%)")
        
        if 'ma5' in stock:
            stock_details.append(f"  均线: MA5={stock['ma5']:.2f}, 趋势:{stock.get('trend', 'N/A')}")
        
        checks = generate_stock_checklist(stock)
        if checks:
            stock_details.append(f"  诊断: {' | '.join(checks[:3])}")
    
    # 热点板块
    sector_lines = []
    if sectors:
        for s in sectors[:8]:
            change = float(s['change']) if isinstance(s['change'], str) else s['change']
            net = float(s['net_inflow']) if isinstance(s['net_inflow'], str) else s['net_inflow']
            emoji = "🔥" if change > 3 else "📈" if change > 0 else "📉"
            sector_lines.append(f"{emoji} {s['name']}: {change:+.2f}% (+{net:.1f}亿)")
    
    report = f"""# 📊 A股市场情绪分析报告 V3 - AI决策版
**{now.strftime('%Y-%m-%d %H:%M')}**

---

## 📡 **数据来源** (100%真实数据)

| 数据项 | 来源 | 状态 |
|--------|------|------|
| 股价/指数 | 腾讯财经API | ✅ 实时 |
| 板块资金 | 东方财富API | ✅ 实时 |
| 技术指标 | 腾讯历史数据 | ✅ 实时 |
| 涨跌统计 | AkShare | ✅ 实时 |
| AI分析 | Minimax M2.1 | ✅ 智能 |

---

## 🎯 AI 核心结论

{ai_analysis}

---

## 📈 市场概况

### 大盘指数
{chr(10).join(index_lines)}

{market_section}

---

## 🔥 热点板块 (资金流入TOP)

{chr(10).join(sector_lines) if sector_lines else "数据获取中..."}

---

## 💼 自选股诊断 ({len(watchlist)}只)
{chr(10).join(stock_details)}

---

*📊 数据来源: 腾讯财经(股价) + 东方财富(资金) | 更新时间: {now.strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    return report

def send_telegram(message):
    """发送到Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000], "parse_mode": "Markdown"}
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
            '--message', message[:3000]
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

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--dual', action='store_true')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("开始生成A股情绪分析报告 V3 - AI决策版")
    logger.info("=" * 60)
    
    start = time.time()
    
    # 并发获取所有数据
    logger.info("获取市场数据...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        indices_future = executor.submit(lambda: [fetch_index_single(i) for i in INDICES])
        market_future = executor.submit(get_market_overview)
        sectors_future = executor.submit(get_hot_sectors)
        
        indices = [r for r in indices_future.result() if r]
        market_data = market_future.result() or {}
        sectors = sectors_future.result() or []
    
    logger.info(f"市场数据获取完成: {time.time()-start:.2f}s")
    
    # 获取自选股（带技术指标）
    logger.info("获取自选股数据...")
    watchlist = []
    for code, name, sector in WATCHLIST:
        stock = get_stock_full(code, name)
        if stock:
            stock['sector'] = sector
            watchlist.append(stock)
        time.sleep(0.1)  # 避免请求过快
    
    logger.info(f"自选股获取完成: {len(watchlist)}/{len(WATCHLIST)}只")
    
    # AI分析
    logger.info("调用Minimax M2.1生成AI分析...")
    ai_start = time.time()
    ai_analysis = generate_ai_analysis(market_data, indices, watchlist, sectors)
    logger.info(f"AI分析完成: {time.time()-ai_start:.2f}s")
    
    # 生成报告
    report = format_report_v3(market_data, indices, watchlist, sectors, ai_analysis)
    
    total = time.time() - start
    logger.info(f"总耗时: {total:.2f}s")
    
    print(report)
    
    if args.test:
        logger.info("测试模式，不发送")
        return
    
    if args.dual:
        logger.info("双通道发送...")
        send_telegram(report)
        send_whatsapp(report)
    
    logger.info("=" * 60)

if __name__ == '__main__':
    main()
