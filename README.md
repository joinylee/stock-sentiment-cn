# A股市场情绪分析系统 V3

🤖 AI驱动的A股智能分析系统 - 基于 Minimax M2.1

## ✨ 功能特性

- 📊 **多数据源融合** - 腾讯财经 + 东方财富 + 同花顺
- 📈 **实时监控** - 自选股、板块资金、大盘指数
- 🧠 **AI决策** - Minimax M2.1 智能分析（支持规则版备用）
- 📱 **双通道推送** - Telegram + WhatsApp
- ⚡ **快速执行** - ~12秒完成全流程

## 📁 项目结构

```
stock-sentiment-cn/
├── scripts/
│   ├── full_report_v3.py      # 主程序 V3 AI决策版
│   ├── tonghua_shun_funds.py  # 同花顺数据模块
│   └── config_loader.py       # 配置加载
├── SKILL.md                    # Skill说明
└── README.md                   # 本文件
```

## 🚀 快速开始

```bash
# 安装依赖
pip3 install akshare requests pandas

# 运行报告
cd ~/.openclaw/workspace/skills/stock-sentiment-cn/scripts
python3 full_report_v3.py --dual
```

## 📊 数据来源

| 数据项 | 来源 | 状态 |
|--------|------|------|
| 股价/指数 | 腾讯财经API | ✅ |
| 热点板块 | 同花顺浏览器 | ✅ |
| 板块资金 | 东方财富API | ✅ |
| 市场概览 | AkShare | ✅ |
| AI分析 | Minimax M2.1 | ✅ |

## 🔧 配置

需要在 `~/.openclaw/openclaw.json` 中配置：

```json
{
  "telegram_bot_token": "your_token",
  "telegram_chat_id": "your_chat_id",
  "whatsapp_target": "+86138xxxx8809",
  "minimax_api_key": "your_key"
}
```

## 📝 使用方式

```bash
# 测试模式
python3 full_report_v3.py --test

# 双通道发送
python3 full_report_v3.py --dual
```

## 🐛 问题修复记录

### V3 修复
- ✅ 热点板块涨幅字段 (f136 → f3)
- ✅ 东方财富API不稳定 → 使用同花顺浏览器数据
- ✅ 市场涨跌统计 → 使用AkShare交易所总貌

## 📄 许可证

MIT License

## 👨‍💻 作者

Joiny Lee

---

*Built with ❤️ for A-share investors*
