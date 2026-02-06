#!/usr/bin/env python3
"""
同花顺数据获取完整版
支持：概念资金、行业资金、个股资金、龙虎榜、营业部排名
"""

import subprocess
import json
import re
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional

class TonghuaShunAPI:
    """同花顺数据 API"""
    
    def get_browser_snapshot(self, url: str) -> Optional[str]:
        try:
            subprocess.run(['openclaw', 'browser', 'open', url], capture_output=True, timeout=30)
            result = subprocess.run(
                ['openclaw', 'browser', 'snapshot', '--format', 'aria'],
                capture_output=True, text=True, timeout=60
            )
            return result.stdout if result.returncode == 0 else None
        except Exception as e:
            print(f"❌ Browser获取失败: {e}")
            return None
    
    def parse_amount(self, text: str) -> float:
        if not text or text in ['0.00', '0']:
            return 0.0
        text = text.strip()
        try:
            if '亿' in text:
                return float(text.replace('亿', '')) * 10000
            elif '万' in text:
                return float(text.replace('万', ''))
            else:
                return float(text) / 10000
        except:
            return 0.0
    
    # ============ 概念资金 ============
    def get_concept_funds(self) -> Dict:
        print("📊 获取概念资金流向...")
        snapshot = self.get_browser_snapshot('https://data.10jqka.com.cn/funds/gnzjl/')
        if not snapshot:
            return {'error': '获取失败'}
        
        # 解析表格格式: cell "序号", cell "名称", cell "涨跌幅", cell "净额", etc.
        cells = re.findall(r'                    - cell "([^"]+)"\n', snapshot)
        
        items = []
        # 每12个cell为一行数据
        for i in range(0, min(len(cells) - 11, 200), 12):
            try:
                rank = int(cells[i])
                name = cells[i + 1]
                index_val = float(cells[i + 2])
                change = float(cells[i + 3].replace('%', ''))
                inflow = float(cells[i + 4])
                outflow = float(cells[i + 5])
                net = float(cells[i + 6])
                
                items.append({
                    'rank': rank, 'name': name,
                    'index': index_val, 'change': change,
                    'inflow': inflow, 'outflow': outflow, 'net': net
                })
            except (ValueError, IndexError):
                continue
        
        gainers = sorted([i for i in items if i['change'] > 0], key=lambda x: x['change'], reverse=True)[:10]
        losers = sorted([i for i in items if i['change'] < 0], key=lambda x: x['change'])[:10]
        
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'source': '同花顺',
            'type': '概念资金', 'total': len(items),
            'top_gainers': gainers, 'top_losers': losers,
        }
    
    # ============ 行业资金 ============
    def get_industry_funds(self) -> Dict:
        print("📊 获取行业资金流向...")
        snapshot = self.get_browser_snapshot('https://data.10jqka.com.cn/funds/hyzjl/')
        if not snapshot:
            return {'error': '获取失败'}
        
        # 解析表格格式
        cells = re.findall(r'                    - cell "([^"]+)"\n', snapshot)
        
        items = []
        for i in range(0, min(len(cells) - 11, 200), 12):
            try:
                rank = int(cells[i])
                name = cells[i + 1]
                index_val = float(cells[i + 2])
                change = float(cells[i + 3].replace('%', ''))
                inflow = float(cells[i + 4])
                outflow = float(cells[i + 5])
                net = float(cells[i + 6])
                
                items.append({
                    'rank': rank, 'name': name,
                    'index': index_val, 'change': change,
                    'inflow': inflow, 'outflow': outflow, 'net': net
                })
            except (ValueError, IndexError):
                continue
        
        gainers = sorted([i for i in items if i['change'] > 0], key=lambda x: x['change'], reverse=True)[:10]
        losers = sorted([i for i in items if i['change'] < 0], key=lambda x: x['change'])[:10]
        
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'source': '同花顺',
            'type': '行业资金', 'total': len(items),
            'top_gainers': gainers, 'top_losers': losers,
        }
    
    # ============ 个股资金 ============
    def get_stock_funds(self, limit: int = 50) -> Dict:
        print("📊 获取个股资金流向...")
        snapshot = self.get_browser_snapshot('https://data.10jqka.com.cn/funds/ggzjl/')
        if not snapshot:
            return {'error': '获取失败'}
        
        # 解析个股资金表格
        cells = re.findall(r'                    - cell "([^"]+)"\n', snapshot)
        
        items = []
        # 每行约10个cell: 序号,代码,名称,现价,涨跌幅,涨跌额,成交额,流入,流出,净额
        for i in range(0, min(len(cells) - 9, 500), 10):
            try:
                rank = int(cells[i])
                code = cells[i + 1]
                name = cells[i + 2]
                price = float(cells[i + 3])
                change = float(cells[i + 4].replace('%', ''))
                # 净额带单位，需要转换
                net_str = cells[i + 9]
                net = self.parse_amount(net_str)
                
                items.append({
                    'rank': rank, 'code': code, 'name': name,
                    'price': price, 'change': change, 'net': net
                })
            except (ValueError, IndexError):
                continue
        
        net_gainers = sorted([i for i in items if i['net'] > 0], key=lambda x: x['net'], reverse=True)[:limit]
        net_losers = sorted([i for i in items if i['net'] < 0], key=lambda x: x['net'])[:limit]
        
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'source': '同花顺',
            'type': '个股资金', 'total': len(items),
            'top_net_inflow': net_gainers, 'top_net_outflow': net_losers,
        }
    
    # ============ 龙虎榜个股明细 ============
    def get_longhu_detail(self) -> Dict:
        print("📊 获取龙虎榜个股明细...")
        snapshot = self.get_browser_snapshot('https://data.10jqka.com.cn/market/longhu/')
        if not snapshot:
            return {'error': '获取失败'}
        
        items = []
        # 解析深市和沪市的龙虎榜数据
        # 格式: cell "股票名 涨跌幅%"
        pattern = r'cell "([^"]+)"\s*\n\s*- link "([^"]+)"'
        for match in re.finditer(pattern, snapshot):
            try:
                full_text = match.group(1)
                name = match.group(2)
                # 提取涨跌幅
                change_match = re.search(r'([+-]?\d+\.?\d*)%$', full_text)
                if change_match:
                    change = float(change_match.group(1))
                    items.append({
                        'name': name,
                        'change': change,
                    })
            except:
                pass
        
        # 过滤并去重
        seen = set()
        unique_items = []
        for item in items:
            if item['name'] not in seen:
                seen.add(item['name'])
                unique_items.append(item)
        
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'source': '同花顺',
            'type': '龙虎榜个股明细', 'total': len(unique_items),
            'items': [{'rank': i+1, **item} for i, item in enumerate(unique_items[:50])],
        }
    
    # ============ 龙虎榜全部 ============
    def get_longhu_all(self) -> Dict:
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'detail': self.get_longhu_detail(),
        }
    
    # ============ 全部数据 ============
    def get_all(self) -> Dict:
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'concept': self.get_concept_funds(),
            'industry': self.get_industry_funds(),
            'stock': self.get_stock_funds(),
            'longhu': self.get_longhu_all(),
        }


def format_output(data: Dict, data_type: str = 'concept') -> str:
    if 'error' in data:
        return f"❌ 获取失败: {data['error']}"
    
    lines = [f"# 📊 {data['type']} ({data['update_time']})"]
    lines.append(f"数据来源: {data['source']}\n")
    
    if data_type == 'stock':
        lines.append("## 🔥 资金流入 TOP 20")
        lines.append("| 排名 | 代码 | 名称 | 现价 | 涨跌幅 | 净额 |")
        for item in data['top_net_inflow'][:20]:
            net_val = item['net']
            if net_val >= 10000:
                net_str = f"{net_val/10000:.1f}亿"
            else:
                net_str = f"{net_val:.0f}万"
            lines.append(f"| {item['rank']} | {item['code']} | {item['name'][:6]} | {item['price']:.2f} | {item['change']:+.2f}% | {net_str} |")
        
        lines.append("\n## 📉 资金流出 TOP 20")
        for item in data['top_net_outflow'][:20]:
            net_val = item['net']
            if net_val <= -10000:
                net_str = f"{net_val/10000:.1f}亿"
            else:
                net_str = f"{net_val:.0f}万"
            lines.append(f"| {item['rank']} | {item['code']} | {item['name'][:6]} | {item['price']:.2f} | {item['change']:+.2f}% | {net_str} |")
    
    elif data_type == 'longhu_detail':
        lines.append(f"共 {data['total']} 只龙虎榜个股\n")
        lines.append("| 排名 | 名称 | 涨跌幅 |")
        lines.append("|------|------|--------|")
        for item in data['items'][:20]:
            lines.append(f"| {item['rank']} | {item['name'][:8]} | {item['change']:+.2f}% |")
    
    else:
        lines.append("## 🔥 资金流入 TOP 10")
        lines.append("| 排名 | 名称 | 涨跌幅 | 净额(亿) |")
        for item in data['top_gainers']:
            lines.append(f"| {item['rank']} | {item['name'][:10]} | {item['change']:+.2f}% | {item['net']:.2f} |")
        lines.append("\n## 📉 资金流出 TOP 10")
        for item in data['top_losers']:
            lines.append(f"| {item['rank']} | {item['name'][:10]} | {item['change']:.2f}% | {item['net']:.2f} |")
    
    return '\n'.join(lines)


def main():
    api = TonghuaShunAPI()
    
    args = sys.argv[1:] if len(sys.argv) > 1 else ['--help']
    
    if '--help' in args or not args:
        print("""使用参数:
  --concept    获取概念资金流向
  --industry   获取行业资金流向
  --stock      获取个股资金流向
  --longhu     获取龙虎榜个股明细
  --longhu-all 获取龙虎榜全部数据
  --all       获取全部数据

示例:
  python3 tonghua_shun_funds.py --longhu
""")
        return
    
    if '--concept' in args:
        data = api.get_concept_funds()
        print(format_output(data, 'concept'))
        with open('/tmp/concept_funds.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 已保存到 /tmp/concept_funds.json")
    
    elif '--industry' in args:
        data = api.get_industry_funds()
        print(format_output(data, 'industry'))
        with open('/tmp/industry_funds.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 已保存到 /tmp/industry_funds.json")
    
    elif '--stock' in args:
        data = api.get_stock_funds()
        print(format_output(data, 'stock'))
        with open('/tmp/stock_funds.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 已保存到 /tmp/stock_funds.json")
    
    elif '--longhu' in args:
        data = api.get_longhu_detail()
        print(format_output(data, 'longhu_detail'))
        with open('/tmp/longhu_detail.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 已保存到 /tmp/longhu_detail.json")
    
    elif '--longhu-all' in args:
        data = api.get_longhu_all()
        print("="*60)
        print(format_output(data['detail'], 'longhu_detail'))
        with open('/tmp/longhu_all.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 已保存到 /tmp/longhu_all.json")
    
    elif '--all' in args:
        data = api.get_all()
        print("="*60)
        print(format_output(data['concept'], 'concept'))
        print("\n" + "="*60)
        print(format_output(data['industry'], 'industry'))
        print("\n" + "="*60)
        print(format_output(data['stock'], 'stock'))
        print("\n" + "="*60)
        print(format_output(data['longhu']['detail'], 'longhu_detail'))
        with open('/tmp/all_funds.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n✅ 已保存到 /tmp/all_funds.json")


if __name__ == '__main__':
    main()
