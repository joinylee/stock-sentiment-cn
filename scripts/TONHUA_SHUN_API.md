# 同花顺资金流向数据接口文档

## 数据类型

| 类型 | 路径 | 说明 |
|------|------|------|
| 概念资金 | `/funds/gnzjl/` | 概念板块资金流向 |
| 行业资金 | `/funds/hyzjl/` | 行业板块资金流向 |

## 数据结构

### 概念/行业资金项

```json
{
  "rank": 1,
  "name": "锂电池概念",
  "index": 1973.63,
  "change": 1.63,
  "inflow": 1057.19,
  "outflow": 836.39,
  "net": 220.80,
  "companies": 569,
  "leader": "震裕科技",
  "leader_change": 13.15,
  "leader_price": 176.18
}
```

字段说明:
- `rank`: 排名
- `name`: 概念/行业名称
- `index`: 指数点位
- `change`: 涨跌幅 (%)
- `inflow`: 流入资金 (亿)
- `outflow`: 流出资金 (亿)
- `net`: 净额 (亿)
- `companies`: 上市公司数量
- `leader`: 领涨股名称
- `leader_change`: 领涨股涨跌幅
- `leader_price`: 领涨股现价

## 获取方案

### 方案 1: Browser 访问 (推荐)

由于同花顺有防爬虫机制，直接 HTTP 请求会被封禁。

```python
import subprocess

# 获取概念资金页面
subprocess.run(['openclaw', 'browser', 'open', 
    'https://data.10jqka.com.cn/funds/gnzjl/'])

# 获取页面快照
result = subprocess.run(
    ['openclaw', 'browser', 'snapshot', '--format', 'aria'],
    capture_output=True, text=True
)
html = result.stdout
```

### 方案 2: 使用脚本

```bash
# 获取概念资金
python3 tonghua_shun_funds.py --concept

# 获取行业资金
python3 tonghua_shun_funds.py --industry

# 获取全部数据
python3 tonghua_shun_funds.py --all
```

## 数据特点

1. **服务端渲染**: 数据直接嵌入 HTML，非 JS 动态加载
2. **防爬虫**: 直接 HTTP 请求会被 403/封禁
3. **编码**: GBK 编码
4. **实时性**: 盘中最接近实时

## 注意事项

1. 使用 browser 工具可以绕过防爬虫
2. 数据获取频率不宜过高
3. 仅供参考，不构成投资建议
