# EasyWay Quit Smoking Coach (easyway-quit-smoking-coach)

基于亚伦·卡尔（Allen Carr）《这书能让你戒烟》（Easyway）方法论打造的极简轻量级戒烟私教 Agent。

---

## 🌟 核心设计原则

1. **极简轻量**：
   - **零数据库**：单个 JSON 状态管理。
   - **零第三方 Python 依赖**：纯 Python 3 标准库（`datetime`, `json`, `pathlib`, `argparse`），无兼容负担。
   - **零冗余日志**：心跳未命中时极简 JSON 输出退出，绝不侵占磁盘空间。
2. **代码与数据严格分离**：
   - 个人进度保存在仓库外部的独立 `state.json` 文件中，通过环境变量 `EASYWAY_STATE_PATH` 指向。
   - 仓库内仅保留 `templates/state.example.json` 模板，`.gitignore` 严格忽略所有真实状态数据，保护个人隐私。
3. **Easyway 方法论**：
   - 坚决不用意志力硬扛，不恐吓，不用尼古丁替代品。
   - 拆解“心理大怪兽”（看穿减压/解闷/社交的假象），重塑“生理小怪兽”（饥饿感是毒虫正在饿死的胜利信号）。
   - 四阶段动态主动节奏与情绪缩放。

---

## 📂 项目结构

```text
easyway-quit-smoking-coach/
├── .gitignore                      # 忽略敏感 state 及环境文件
├── README.md                       # 项目与接入说明
├── SKILL.md                        # Easyway 私教技能 Prompt 与状态机规范
├── templates/
│   └── state.example.json          # 状态文件模板（字段说明与默认配置）
└── scripts/
    └── heartbeat.py                # 零依赖心跳判断与无烟时长计算脚本
```

---

## 🛠️ 本地调试与 Dry-run 验证

### 1. 初始化外部状态文件
```bash
# 设置外部状态路径（或使用参数 --state-path）
export EASYWAY_STATE_PATH="/path/to/my_state.json"

# 从模板一键初始化
python3 scripts/heartbeat.py --init
```

### 2. 模拟不同状态验证（Dry-run）
脚本内置了 `--dry-run` 与 `--mock-scenario` 模式，便于在不改变真实数据的前提下完整测试各类场景：

```bash
# 模拟场景 1：未到点（时间未到下一次 check 点）
python3 scripts/heartbeat.py --dry-run --mock-scenario not_due
# 输出: {"should_trigger": false, "reason": "not_due_yet"}

# 模拟场景 2：静默期（处于 23:00 - 07:30 夜间静默时段）
python3 scripts/heartbeat.py --dry-run --mock-scenario quiet
# 输出: {"should_trigger": false, "reason": "quiet_hours"}

# 模拟场景 3：已到点（触发主动关怀与阶段计算）
python3 scripts/heartbeat.py --dry-run --mock-scenario due
# 输出: {"should_trigger": true, "elapsed_text": "3小时20分钟", "stage": 1, "state_path": "..."}
```

---

## 🚀 部署至 GitHub 私有仓库

在 GitHub 创建全新的空私有仓库（例如 `easyway-quit-smoking-coach`）后，在本地终端执行：

```bash
cd easyway-quit-smoking-coach

# 添加远端地址
git remote add origin git@github.com:<YOUR_GITHUB_USERNAME>/easyway-quit-smoking-coach.git

# 设为主分支并推送
git branch -M main
git push -u origin main
```

---

## 🤖 云端 Hermes Agent 接入清单

将本技能部署到云端运行 Hermes Agent 的主机（如 Debian VPS）：

### 1. 克隆仓库至技能目录
```bash
mkdir -p ~/.hermes/skills
git clone git@github.com:<YOUR_GITHUB_USERNAME>/easyway-quit-smoking-coach.git ~/.hermes/skills/easyway-quit-smoking-coach
```

### 2. 配置文件持久化与环境变量
将真实的个人进度文件存放在外部安全目录（如 `~/.hermes/data/easyway_state.json`）：

```bash
export EASYWAY_STATE_PATH="$HOME/.hermes/data/easyway_state.json"

# 初始化真实状态
python3 ~/.hermes/skills/easyway-quit-smoking-coach/scripts/heartbeat.py --init
```
并在用户的环境变量配置（如 `~/.bashrc` 或 systemd 服务环境）中持久化 `EASYWAY_STATE_PATH`。

### 3. 配置定时任务（Cron）
配置系统定时任务（如每 10 分钟执行一次心跳预检）：
```bash
crontab -e
```
添加以下任务。心跳脚本零开销执行，仅在 `should_trigger` 为 `true` 时才唤醒 Hermes Agent 处理，极大节省模型 Token：

```cron
*/10 * * * * bash -c 'OUTPUT=$(python3 $HOME/.hermes/skills/easyway-quit-smoking-coach/scripts/heartbeat.py); if echo "$OUTPUT" | grep -q "\"should_trigger\": true"; then hermes run --skill easyway-quit-smoking-coach --input "$OUTPUT"; fi'
```

### 4. 绑定独立 Telegram Topic
为防止戒烟私教消息打扰其他日常对话：
1. 在 Telegram 群组或 Hermes 频道中创建一个专用 Topic（例如命名为 `🚭 轻松戒烟教练`）。
2. 在 Hermes Agent 路由配置中，将 `easyway-quit-smoking-coach` 产生的主动推送与会话路由绑定到该 Topic ID。
3. Agent 发出消息后，自动根据用户反馈或阶段更新 `state.json` 中的 `next_check_at` 与 `unread_streak`。
