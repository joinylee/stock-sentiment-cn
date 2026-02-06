#!/usr/bin/env python3
"""
同花顺资金流向数据获取接口
支持：概念资金、行业资金
"""

import requests
import re
from datetime import datetime
from typing import List, Dict, Optional

class TonghuaShunDataAPI:
    """同花顺数据接口"""
    
    BASE_URL = "https://data.10jqka.com.cn"
    
    # 编码方式
    ENCODING = 'gbk'
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
    
    def _fetch_page(self, path: str) -> Optional[str]:
        """获取页面内容"""
        try:
            url = f"{self.BASE_URL}{path}"
            r = self.session.get(url, timeout=15)
            r.encoding = self.ENCODING
            return r.text
        except Exception as e:
            print(f"❌ 获取失败: {e}")
            return None
    
    def _parse_table(self, html: str) -> List[Dict]:
        """解析资金流向表格"""
        items = []
        
        # 匹配表格行: 排名 概念名 指数 涨幅 流入 流出 净额 公司数 领涨股 涨幅 现价
        pattern = r'''(\d+)\s+<a[^>]*>([^<]+)</a>\s+([\d.]+)\s+([+-]?[\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+([+-]?[\d.]+)\s+(\d+)\s+<a[^>]*>([^<]+)</a>\s+([+-]?[\d.]+)%\s+([\d.]+)'''
        
        matches = re.findall(pattern, html)
        
        for match in matches:
            try:
                items.append({
                    'rank': int(match[0]),
                    'name': match[1].strip(),
                    'index': float(match[2]),
                    'change': float(match[3]),
                    'inflow': float(match[4]),
                    'outflow': float(match[5]),
                    'net': float(match[6]),
                    'companies': int(match[7]),
                    'leader': match[8],
                    'leader_change': float(match[9]),
                    'leader_price': float(match[10]),
                })
            except:
                continue
        
        return items
    
    def get_concept_funds(self) -> Dict:
        """
        获取概念资金流向
        
        返回:
        {
            'update_time': str,
            'source': str,
            'top_gainers': [...],
            'top_losers': [...],
            'all': [...]
        }
        """
        print("📊 获取概念资金流向...")
        html = self._fetch_page('/funds/gnzjl/')
        
        if not html:
            return {'error': '获取失败'}
        
        items = self._parse_table(html)
        
        # 分离涨跌
        gainers = [i for i in items if i['change'] > 0]
        losers = [i for i in items if i['change'] < 0]
        
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'source': '同花顺',
            'type': '概念资金',
            'total_items': len(items),
            'top_gainers': sorted(gainers, key=lambda x: x['change'], reverse=True)[:10],
            'top_losers': sorted(losers, key=lambda x: x['change'])[:10],
            'all': items,
        }
    
    def get_industry_funds(self) -> Dict:
        """
        获取行业资金流向
        """
        print("📊 获取行业资金流向...")
        html = self._fetch_page('/funds/hyzjl/')
        
        if not html:
            return {'error': '获取失败'}
        
        items = self._parse_table(html)
        
        # 分离涨跌
        gainers = [i for i in items if i['change'] > 0]
        losers = [i for i in items if i['change'] < 0]
        
        return {
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'source': '同花顺',
            'type': '行业资金',
            'total_items': len(items),
            'top_gainers': sorted(gainers, key=lambda x: x['change'], reverse=True)[:10],
            'top_losers': sorted(losers, key=lambda x: x['change'])[:10],
            'all': items,
        }

def format_concept_report(data: Dict) -> str:
    """格式化概念资金报告"""
    if 'error' in data:
        return f"❌ 获取失败: {data['error']}"
    
    lines = [f"# 📊 概念资金流向 ({data['update_time']})"]
    lines.append(f"数据来源: {data['source']}\n")
    
    # 涨幅榜
    lines.append("## 🔥 资金流入 TOP 10")
    lines.append("| 排名 | 概念 | 涨跌幅 | 净额(亿) | 流入(亿) | 领涨股 |")
    lines.append("|------|------|--------|----------|----------|--------|")
    
    for item in data['top_gainers']:
        lines.append(f"| {item['rank']} | {item['name']} | {item['change']:+.2f}% | {item['net']:.2f} | {item['inflow']:.1f} | {item['leader']} |")
    
    # 跌幅榜
    lines.append("\n## 📉 资金流出 TOP 10")
    lines.append("| 排名 | 概念 | 涨跌幅 | 净额(亿) |")
    lines.append("|------|------|--------|----------|")
    
    for item in data['top_losers']:
        lines.append(f"| {item['rank']} | {item['name']} | {item['change']:.2f}% | {item['net']:.2f} |")
    
    return '\n'.join(lines)

def format_industry_report(data: Dict) -> str:
    """格式化行业资金报告"""
    if 'error' in data:
        return f"❌ 获取失败: {data['error']}"
    
    lines = [f"# 📊 行业资金流向 ({data['update_time']})"]
    lines.append(f"数据来源: {data['source']}\n")
    
    # 涨幅榜
    lines.append("## 🔥 资金流入 TOP 10")
    lines.append("| 排名 | 行业 | 涨跌幅 | 净额(亿) | 公司数 |")
    lines.append("|------|------|--------|----------|--------|")
    
    for item in data['top_gainers']:
        lines.append(f"| {item['rank']} | {item['name']} | {item['change']:+.2f}% | {item['net']:.2f} | {item['companies']} |")
    
    # 跌幅榜
    lines.append("\n## 📉 资金流出 TOP 10")
    lines.append("| 排名 | 行业 | 涨跌幅 | 净额(亿) |")
    lines.append("|------|------|--------|----------|")
    
    for item in data['top_losers']:
        lines.append(f"| {item['rank']} | {item['name']} | {item['change']:.2f}% | {item['net']:.2f} |")
    
    return '\n'.join(lines)

def main():
    api = TonghuaShunDataAPI()
    
    # 获取概念资金
    print("\n" + "="*50)
    concept_data = api.get_concept_funds()
    concept_report = format_concept_report(concept_data)
    print(concept_report)
    
    # 保存概念数据
    import json
    with open('/tmp/concept_funds.json', 'w', encoding='utf-8') as f:
        json.dump(concept_data, f, ensure_ascii=False, indent=2)
    
    # 获取行业资金
    print("\n" + "="*50)
    industry_data = api.get_industry_funds()
    industry_report = format_industry_report(industry_data)
    print(industry_report)
    
    # 保存行业数据
    with open('/tmp/industry_funds.json', 'w', encoding='utf-8') as f:
        json.dump(industry_data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*50)
    print("✅ 数据已保存到 /tmp/concept_funds.json 和 /tmp/industry_funds.json")

if __name__ == '__main__':
    main()
