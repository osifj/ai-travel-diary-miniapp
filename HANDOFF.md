# 交接文档 — AI 游玩日志生成系统

## 当前状态

项目 5 个 Phase 全部完成，后端 API 全通、小程序骨架就绪、测试通过。  
**当前卡点**：微信开发者工具真机调试时 `result.wxml` 编译报错，正在排查。

---

## 项目位置

```
/tmp/ai-travel-diary-miniapp/
```

已打包：`/tmp/ai-travel-diary-miniapp-v1.zip` (56 KB, 48 源文件)  
Git 仓库已初始化（1 commit, main 分支），待推送到 `https://github.com/osifj/ai-travel-diary-miniapp`

---

## 文件改动记录（本轮会话最后操作）

以下是你接管时文件的最新状态：

1. **`result.wxml`** — 已替换为**极简测试版**（原版备份在 `result.wxml.backup`）
   ```
   /tmp/ai-travel-diary-miniapp/miniapp/pages/result/result.wxml        ← 当前极简版
   /tmp/ai-travel-diary-miniapp/miniapp/pages/result/result.wxml.backup ← 原版
   /tmp/ai-travel-diary-miniapp/miniapp/pages/result/result.wxml.minimal ← 极简版副本
   ```

2. **`result.js`** — 已改为预计算模式，所有布尔/字符串运算在 JS 层完成传给 WXML
   ```
   /tmp/ai-travel-diary-miniapp/miniapp/pages/result/result.js
   ```

3. 其他文件未改动（upload、analyzing、index、map 页面保持原始版本）

---

## 卡点详情

**错误信息**：
```
真机调试 Error: wxml 编译错误
./pages/result/result.wxml:1:1024: Bad attr `wx:for-items` with message: error at token `wxml 编译错误`
```

**环境**：
- 微信开发者工具 `2.01.2510290`（darwin-arm64）
- AppID: `wxeac4f835b97182bf`
- 真机调试模式

**已尝试的修复**（均无效）：
1. 移除 `diary.content.split('\n\n')`（WXML 不支持方法调用）→ 改为 JS 预计算
2. 移除所有 `||`、`&&`、`>`、三元表达式 → 改为 JS 预计算布尔值
3. 用 `block` + `wx:for-item="xxx"` 替换所有 `wx:for` + `item` → 避免 `item` 关键字冲突
4. 移除所有 `wx:key` 属性 → 避免 `*this` 兼容问题

**当前极简版**（已写入 `result.wxml`）只有三个块：
- `wx:if="{{loading}}"` → 加载中
- `wx:elif="{{!diary}}"` → 空状态
- `wx:else` → 标题 + 日期 + 正文 + 按钮

没有循环、没有复杂表达式、没有 `wx:for`。

---

## 下一步排查方向

按优先级：

1. **先清除缓存再编译**  
   微信开发者工具 → 菜单「项目」→「清除全部缓存」→「清除文件缓存」→ 点击「编译」

2. **如果极简版仍报错**，问题不在 result.wxml：
   - 检查 `result.js` 是否有语法错误（ES6 `...p` 展开运算符可能不被小程序支持？）
   - 检查 `result.json` 和 `result.wxss`
   - 检查其他页面是否有 WXML 编译错误被误报为 result.wxml
   - 尝试逐个删除 page 注册（`app.json` 中临时移除 result 页面看是否还报错）

3. **如果极简版编译通过**，逐步从 `.backup` 加回内容定位：
   - 先加回关键词循环
   - 再加回段落循环
   - 最后加回照片详情循环
   - 每次加一个部分就编译一次，找到触发错误的具体区块

4. **终极手段**：把 `result.wxml` 的 `wx:else` 分支内容全部注释，只留一个 `<text>test</text>`，确认 if-elif-else 结构是否正常。

---

## 项目结构速览

```
ai-travel-diary-miniapp/
├── README.md
├── .gitignore
│
├── backend/                        # Python FastAPI ✅ 已跑通
│   ├── app.py                      # 入口，注册 3 个 router
│   ├── requirements.txt            # fastapi uvicorn Pillow httpx python-dotenv
│   ├── .env.example                # MIMO_API_KEY / MIMO_BASE_URL / MIMO_MODEL
│   ├── api/
│   │   ├── upload.py               # POST /upload, POST /upload/batch
│   │   ├── analyze.py              # POST /analyze (支持 Mock 模式)
│   │   └── diary.py                # POST /diary/generate, GET /diary/{id}, GET /diary/
│   ├── services/
│   │   ├── exif_reader.py          # exiftool + Pillow 双引擎
│   │   ├── image_preprocess.py     # 压缩 1024px + 去 EXIF
│   │   ├── mimo_client.py          # OpenAI-compatible + Mock 回退
│   │   ├── geocoder.py             # Mock / Nominatim / 腾讯地图
│   │   └── diary_generator.py      # 模板驱动中文日记生成
│   ├── models/
│   │   └── database.py             # SQLite: photos + diaries 表
│   └── tests/
│       ├── test_exif_reader.py     # 8 tests ✅
│       └── test_diary_generator.py # 9 tests ✅
│
├── miniapp/                        # 微信小程序
│   ├── app.js / .json / .wxss
│   ├── utils/request.js            # wx.request 封装, baseUrl: 127.0.0.1:8000
│   └── pages/
│       ├── index/                  # 首页 ✅
│       ├── upload/                 # 上传页 ✅ (有复杂表达式，可能也需修)
│       ├── analyzing/              # 分析进度 ✅
│       ├── result/                 # 结果页 ❌ 编译报错
│       └── map/                    # 地图占位 ✅
│
└── docs/
    ├── project_design.md
    ├── api_design.md
    └── demo_script.md
```

---

## 后端启动命令

```bash
cd /tmp/ai-travel-diary-miniapp/backend
cp .env.example .env
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

验证：`curl http://127.0.0.1:8000/health` → `{"status":"ok"}`

**Mock 模式**：MiMo API 未配置时自动返回模拟数据，不影响前后端联调。

---

## 关键提醒

- 真机调试需要 HTTPS 后端（ngrok: `ngrok http 8000`，然后改 `request.js` 的 `baseUrl`）
- 微信开发者工具必须勾选「不校验合法域名」
- 后端 `.env` 不提交（.gitignore 已排除）
- 测试用：`PYTHONPATH=/tmp/ai-travel-diary-miniapp/backend python3 -m pytest /tmp/ai-travel-diary-miniapp/backend/tests/ -v`
