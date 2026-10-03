# 贪吃蛇（终端版）

一个用纯 Python 标准库写的终端贪吃蛇小游戏，不需要安装任何第三方包。

## 功能

- 方向键 / WASD 控制，带方向输入缓冲（连按两下也不会反向把自己咬死）
- 三档难度预设：`easy` / `normal` / `hard`
- 穿墙模式：游戏中按 `T` 随时切换，也可以用 `--wrap` 启动
- 障碍物关卡：每升一关追加障碍物，生成时自动做 BFS 可达性校验，不会把蛇堵死
- 限时奖励食物：按概率刷新，越早吃到分越高，超时自动消失
- 最高分按难度分开保存到 `snake_scores.json`
- 同时支持 Windows（`msvcrt`）与 Linux / macOS（`termios`）
- 自适应终端大小：自动决定棋盘格数与每格宽度
- 内置自测与自动演示，方便验证与调试

## 运行

最简单的方式是双击 `run_snake.bat`，它会设置好代码页和窗口大小。

也可以在终端里直接运行：

```bat
python snake.py
```

常用参数：

```bat
python snake.py --difficulty hard          :: 困难模式
python snake.py --wrap                     :: 开局就是穿墙模式
python snake.py --width 30 --height 20     :: 指定棋盘大小
python snake.py --speed 80                 :: 指定初始速度（毫秒/格，越小越快）
python snake.py --obstacles 20             :: 指定初始障碍物数量
python snake.py --ascii --no-color         :: 纯 ASCII + 无颜色（对齐最稳）
python snake.py --seed 42                  :: 固定随机种子，便于复现
python snake.py --demo 200                 :: 带画面的自动演示（AI 自动操作 200 步）
python snake.py --headless 400             :: 纯文本快跑 400 步并打印统计
python snake.py --selftest                 :: 运行内置自测（47 项断言）
```

## 操作

| 按键 | 功能 |
| --- | --- |
| `←` `↑` `→` `↓` 或 `WASD` | 转向（也支持 `kjhl`） |
| `空格` | 开始游戏 / 暂停 / 继续 / 结束后重开 |
| `R` | 重新开始一局 |
| `T` | 切换穿墙模式 |
| `+` / `-` | 加速 / 减速 |
| `Q` 或 `Esc` | 退出 |

## 难度预设

| 参数 | easy | normal | hard |
| --- | --- | --- | --- |
| 初始速度 | 180 ms/格 | 130 ms/格 | 95 ms/格 |
| 每吃食物加速 | 6 ms | 10 ms | 14 ms |
| 速度下限 | 90 ms | 60 ms | 40 ms |
| 初始障碍物 | 0 | 4 | 10 |
| 每关新增障碍物 | 2 | 3 | 4 |
| 每关需要食物数 | 6 | 5 | 4 |
| 奖励食物概率 | 25% | 35% | 45% |

分数规则：普通食物 `+10` 分；奖励食物 `+基础分（40/50/60） + 剩余时间`，越早吃到分越高。

## 文件结构

```text
snake/
├── snake.py           游戏本体（单文件，纯标准库）
├── run_snake.bat      Windows 一键启动脚本
├── README.md          项目说明
└── snake_scores.json  最高分记录（首次游玩后自动生成）
```

## 代码结构

`snake.py` 分成四层，便于阅读和测试：

1. `Config` + `DIFFICULTIES`：所有可调数值集中在一处
2. `SnakeGame`：纯逻辑层，不碰任何输入输出，可单独做单元测试
3. `KeyReader`：输入层，Windows 用 `msvcrt`，类 Unix 用 `termios + select`
4. `Renderer`：渲染层，整帧拼成一个字符串后一次性写出，避免闪烁

## 说明与注意事项

- 游戏需要窗口至少有 24 列 x 14 行；窗口太小会给出提示而不是崩溃。
- 字符集使用 `● ○ ◆ ★ ▓ ┌ ─ ┐ │ └ ┘`，这些字符在 UTF-8 与 GBK 下都能正常显示；
  如果终端字体导致边框对不齐，可以加 `--ascii` 改用纯 ASCII 绘制。
- 键盘输入依赖真实终端，如果在管道 / 重定向环境里运行会直接给出提示；
  只想看效果可以用 `--demo` 或 `--headless`。
- 退出时用备用屏幕（alternate screen）恢复现场，不会把终端画面搞乱。
