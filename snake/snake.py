#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贪吃蛇 - 终端版 (Terminal Snake)
================================

纯 Python 标准库实现，不需要安装任何第三方包。

功能
----
* 方向键 / WASD 控制，带方向输入缓冲（一帧内连按两下也不会反向撞死自己）
* 三档难度预设：easy / normal / hard
* 穿墙模式（游戏中按 T 随时切换，或用 --wrap 启动）
* 障碍物关卡：每升一关追加障碍物，生成时自动做可达性(BFS)校验，不会把蛇堵死
* 限时奖励食物：按概率刷新，越早吃到分数越高，超时自动消失
* 最高分按难度分别保存到 snake_scores.json
* 同时支持 Windows(msvcrt) 与 Linux/macOS(termios)
* 内置自测与自动演示：
      python snake.py --selftest
      python snake.py --headless 400 --seed 42

操作
----
    方向键 / WASD     转向
    空格              开始 / 暂停 / 继续
    R                 重新开始
    T                 切换穿墙模式
    + / -             调速
    Q / Esc           退出
"""

import argparse
import json
import os
import random
import sys
import time
import unicodedata
from collections import deque
from dataclasses import dataclass

IS_WINDOWS = os.name == "nt"

ESC = "\x1b"
CSI = ESC + "["

# ==================== 方向常量 ====================
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
DIRECTIONS = (UP, DOWN, LEFT, RIGHT)

# ==================== 游戏状态 ====================
ST_TITLE = "title"
ST_PLAYING = "playing"
ST_PAUSED = "paused"
ST_OVER = "game_over"
ST_WON = "won"

STATE_NAMES = {
    ST_TITLE: "准备开始",
    ST_PLAYING: "进行中",
    ST_PAUSED: "已暂停",
    ST_OVER: "游戏结束",
    ST_WON: "通关胜利",
}

# ==================== 按键常量 ====================
KEY_UP = "UP"
KEY_DOWN = "DOWN"
KEY_LEFT = "LEFT"
KEY_RIGHT = "RIGHT"
KEY_PAUSE = "PAUSE"
KEY_START = "START"
KEY_RESTART = "RESTART"
KEY_QUIT = "QUIT"
KEY_WRAP = "WRAP"
KEY_FASTER = "FASTER"
KEY_SLOWER = "SLOWER"

DIR_KEYS = {
    KEY_UP: UP,
    KEY_DOWN: DOWN,
    KEY_LEFT: LEFT,
    KEY_RIGHT: RIGHT,
}

CHAR_KEYS = {
    "w": KEY_UP, "W": KEY_UP, "k": KEY_UP,
    "s": KEY_DOWN, "S": KEY_DOWN, "j": KEY_DOWN,
    "a": KEY_LEFT, "A": KEY_LEFT, "h": KEY_LEFT,
    "d": KEY_RIGHT, "D": KEY_RIGHT, "l": KEY_RIGHT,
    " ": KEY_PAUSE, "\r": KEY_START, "\n": KEY_START,
    "r": KEY_RESTART, "R": KEY_RESTART,
    "q": KEY_QUIT, "Q": KEY_QUIT,
    "t": KEY_WRAP, "T": KEY_WRAP,
    "+": KEY_FASTER, "=": KEY_FASTER, "-": KEY_SLOWER, "_": KEY_SLOWER,
}

ANSI_LETTERS = {"A": KEY_UP, "B": KEY_DOWN, "C": KEY_RIGHT, "D": KEY_LEFT}

# ==================== 难度预设 ====================
# speed_ms         初始速度（毫秒/格）
# speed_step_ms    每吃一个食物加速多少毫秒
# min_speed_ms     速度下限
# obstacles_start  开局障碍物数量
# obstacles_per_level  每升一关追加的障碍物数量
# food_per_level   每吃多少个食物升一关
# bonus_chance     吃完食物后刷新奖励食物的概率
# bonus_lifetime   奖励食物存活时间（单位：格 / 步）
# bonus_points     奖励食物基础分数（再加上剩余时间）
# food_points      普通食物分数
DIFFICULTIES = {
    "easy": {
        "speed_ms": 180,
        "speed_step_ms": 6,
        "min_speed_ms": 90,
        "obstacles_start": 0,
        "obstacles_per_level": 2,
        "food_per_level": 6,
        "bonus_chance": 0.25,
        "bonus_lifetime": 20,
        "bonus_points": 40,
        "food_points": 10,
    },
    "normal": {
        "speed_ms": 130,
        "speed_step_ms": 10,
        "min_speed_ms": 60,
        "obstacles_start": 4,
        "obstacles_per_level": 3,
        "food_per_level": 5,
        "bonus_chance": 0.35,
        "bonus_lifetime": 25,
        "bonus_points": 50,
        "food_points": 10,
    },
    "hard": {
        "speed_ms": 95,
        "speed_step_ms": 14,
        "min_speed_ms": 40,
        "obstacles_start": 10,
        "obstacles_per_level": 4,
        "food_per_level": 4,
        "bonus_chance": 0.45,
        "bonus_lifetime": 30,
        "bonus_points": 60,
        "food_points": 10,
    },
}

DIFFICULTY_NAMES = {"easy": "简单", "normal": "普通", "hard": "困难"}


@dataclass
class Config:
    """游戏配置（所有可调数值集中在这里）。"""

    width: int = 28
    height: int = 20
    difficulty: str = "normal"

    speed_ms: int = 130
    speed_step_ms: int = 10
    min_speed_ms: int = 60

    obstacles_start: int = 4
    obstacles_per_level: int = 3
    food_per_level: int = 5

    bonus_chance: float = 0.35
    bonus_lifetime: int = 25
    bonus_points: int = 50

    food_points: int = 10

    wrap: bool = False
    seed: "int | None" = None
    score_file: str = ""


# ==================== 通用小工具 ====================

def enable_ansi():
    """在 Windows 上打开控制台的虚拟终端(VT)处理，返回是否可用 ANSI 转义。"""
    if not IS_WINDOWS:
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
    except Exception:
        return False


def display_width(text):
    """计算字符串在终端里占用的列数（东亚宽字符按 2 列算）。"""
    total = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            total += 2
        else:
            total += 1
    return total


def fit_text(text, width):
    """把文本裁剪到不超过 width 个显示列（按东亚字符宽度计算）。"""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    out = []
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + w > width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def scores_path(cfg):
    """最高分文件的路径。"""
    if cfg.score_file:
        return cfg.score_file
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "snake_scores.json")


def load_scores(cfg):
    """读取最高分；文件缺失或损坏时自动重建。"""
    data = {name: 0 for name in DIFFICULTIES}
    try:
        with open(scores_path(cfg), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            for name in DIFFICULTIES:
                value = raw.get(name, 0)
                if isinstance(value, (int, float)):
                    data[name] = int(value)
    except Exception:
        data = {name: 0 for name in DIFFICULTIES}
    return data


def save_scores(cfg, data):
    """保存最高分，失败时静默忽略（不影响游戏）。"""
    try:
        with open(scores_path(cfg), "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ==================== 游戏逻辑层 ====================

class SnakeGame:
    """贪吃蛇核心逻辑。

    该类不涉及任何终端输入输出，可以独立进行单元测试。
    坐标系：左上角为 (0, 0)，x 向右、y 向下。
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.width = cfg.width
        self.height = cfg.height
        self.rng = random.Random(cfg.seed)
        self.wrap = cfg.wrap
        self.high_score = 0
        self.reset()

    # ------------------------------ 初始化 ------------------------------

    def reset(self):
        """回到初始局面（标题界面）。"""
        cfg = self.cfg
        self.width = cfg.width
        self.height = cfg.height

        cx = max(2, self.width // 2)
        cy = max(0, self.height // 2)
        self.snake = deque([(cx, cy), (cx - 1, cy), (cx - 2, cy)])

        self.direction = RIGHT
        self.pending = deque()
        self.obstacles = set()
        self.food = None
        self.bonus = None
        self.bonus_timer = 0

        self.score = 0
        self.food_eaten = 0
        self.level = 1
        self.speed_ms = cfg.speed_ms
        self.elapsed = 0.0

        self.state = ST_TITLE
        self.death_reason = ""
        self.message = ""
        self.message_timer = 0
        self.new_record = False

        self._generate_obstacles(cfg.obstacles_start)
        self._spawn_food()

    # ------------------------------ 状态切换 ------------------------------

    def start(self):
        """开始游戏。"""
        if self.state in (ST_TITLE, ST_OVER, ST_WON):
            self.state = ST_PLAYING

    def toggle_pause(self):
        """暂停 / 继续。"""
        if self.state == ST_PLAYING:
            self.state = ST_PAUSED
        elif self.state == ST_PAUSED:
            self.state = ST_PLAYING

    def queue_direction(self, direction):
        """把转向指令放进缓冲队列。

        这样即使一帧内连按两次方向键，也不会出现“中间那一下”被丢掉、
        从而直接 180 度掉头把蛇咬死的情况。
        """
        last = self.pending[-1] if self.pending else self.direction
        if direction == last:
            return False
        if direction[0] == -last[0] and direction[1] == -last[1]:
            return False  # 不允许直接反向
        if len(self.pending) >= 2:
            return False
        self.pending.append(direction)
        return True


# ------------------------------ 坐标工具 ------------------------------

    def cell_next(self, cell, direction):
        """从 cell 沿 direction 走一步，返回新坐标（穿墙模式下自动取模）。"""
        x = cell[0] + direction[0]
        y = cell[1] + direction[1]
        if self.wrap:
            return (x % self.width, y % self.height)
        if 0 <= x < self.width and 0 <= y < self.height:
            return (x, y)
        return None

    def _blocked_cells(self):
        """寻路时视为障碍的格子：障碍物 + 蛇身（尾巴会让开，蛇头不算）。"""
        blocked = set(self.obstacles)
        body = list(self.snake)[1:]   # 去掉蛇头本身
        if body:
            body = body[:-1]          # 尾巴下一步会让开
        blocked.update(body)
        return blocked

    def is_reachable(self, start, goal):
        """BFS 判断 start 能否走到 goal（考虑障碍物与蛇身）。"""
        if start == goal:
            return True
        blocked = self._blocked_cells()
        if goal in blocked:
            return False
        seen = {start}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for direction in DIRECTIONS:
                nxt = self.cell_next(cur, direction)
                if nxt is None or nxt in seen:
                    continue
                if nxt == goal:
                    return True
                if nxt in blocked:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return False

    def find_path(self, start, goal):
        """BFS 求最短路径（含起点与终点），不可达时返回 None。"""
        blocked = self._blocked_cells()
        if start != goal and goal in blocked:
            return None
        prev = {start: None}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            if cur == goal:
                break
            for direction in DIRECTIONS:
                nxt = self.cell_next(cur, direction)
                if nxt is None or nxt in prev or nxt in blocked:
                    continue
                prev[nxt] = cur
                queue.append(nxt)
        if goal not in prev:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    # ------------------------------ 随机格子 ------------------------------

    def _random_free_cell(self, exclude_food=True, exclude_bonus=True,
                          require_reachable=False):
        """随机挑一个空格子；没有可用的格子时返回 None。"""
        occupied = set(self.snake) | self.obstacles
        if exclude_food and self.food is not None:
            occupied.add(self.food)
        if exclude_bonus and self.bonus is not None:
            occupied.add(self.bonus)

        free = [(x, y)
                for y in range(self.height)
                for x in range(self.width)
                if (x, y) not in occupied]
        if not free:
            return None

        if require_reachable:
            head = self.snake[0]
            reachable = [cell for cell in free if self.is_reachable(head, cell)]
            if reachable:
                free = reachable
        return self.rng.choice(free)

    # ------------------------------ 障碍物 ------------------------------

    def _generate_obstacles(self, count):
        """生成 count 个障碍物，并保证食物仍然可达。"""
        added = 0
        for _ in range(max(0, count)):
            cell = self._random_free_cell()
            if cell is None:
                break
            self.obstacles.add(cell)
            added += 1
        if added:
            self._ensure_reachable()
        return added

    def _ensure_reachable(self):
        """如果障碍物把食物堵死了，就从离蛇头最近的障碍开始拆除。"""
        if self.food is None:
            return
        head = self.snake[0]
        guard = 0
        limit = self.width * self.height
        while self.obstacles and not self.is_reachable(head, self.food):
            victim = min(self.obstacles,
                         key=lambda c: abs(c[0] - head[0]) + abs(c[1] - head[1]))
            self.obstacles.discard(victim)
            guard += 1
            if guard > limit:
                break


# ------------------------------ 食物 ------------------------------

    def _spawn_food(self):
        """刷新普通食物，优先选择蛇头可达的格子。"""
        self.food = None
        self.food = self._random_free_cell(require_reachable=True)

    def _spawn_bonus(self):
        """刷新限时奖励食物。"""
        cell = self._random_free_cell(require_reachable=True)
        if cell is None:
            return
        self.bonus = cell
        self.bonus_timer = self.cfg.bonus_lifetime

    # ------------------------------ 推进一格 ------------------------------

    def step(self):
        """推进一格；只有 playing 状态才会真正移动。"""
        if self.state != ST_PLAYING:
            return

        if self.message_timer > 0:
            self.message_timer -= 1
            if self.message_timer <= 0:
                self.message = ""

        if self.pending:
            self.direction = self.pending.popleft()

        head = self.snake[0]
        new_head = self.cell_next(head, self.direction)

        # 撞墙
        if new_head is None:
            self._die("撞到了墙壁")
            return

        # 撞障碍物
        if new_head in self.obstacles:
            self._die("撞到了障碍物")
            return

        eating_food = (self.food is not None and new_head == self.food)
        eating_bonus = (self.bonus is not None and new_head == self.bonus)
        grows = eating_food or eating_bonus

        # 撞自己（不吃东西时尾巴会让开）
        body = set(self.snake)
        if not grows:
            body.discard(self.snake[-1])
        if new_head in body:
            self._die("咬到了自己")
            return

        self.snake.appendleft(new_head)
        if not grows:
            self.snake.pop()

        if eating_food:
            self._eat_food()
        if eating_bonus:
            self._eat_bonus()

        self.elapsed += self.speed_ms / 1000.0

        # 奖励食物倒计时
        if self.bonus is not None:
            self.bonus_timer -= 1
            if self.bonus_timer <= 0:
                self.bonus = None
                self.bonus_timer = 0
                self.message = "奖励食物消失了"
                self.message_timer = 5

        self._check_win()

    def _eat_food(self):
        """吃到普通食物：加分、加速、可能刷新奖励食物、可能升级。"""
        cfg = self.cfg
        self.food_eaten += 1
        self.score += cfg.food_points
        self.speed_ms = max(cfg.min_speed_ms, self.speed_ms - cfg.speed_step_ms)

        if self.bonus is None and self.rng.random() < cfg.bonus_chance:
            self._spawn_bonus()

        if cfg.food_per_level > 0 and self.food_eaten % cfg.food_per_level == 0:
            self._level_up()

        self._spawn_food()

    def _eat_bonus(self):
        """吃到奖励食物：越早吃到，剩余时间越多，分数越高。"""
        points = self.cfg.bonus_points + self.bonus_timer
        self.score += points
        self.bonus = None
        self.bonus_timer = 0
        self.message = "吃到奖励食物 +%d 分" % points
        self.message_timer = 8

    def _level_up(self):
        """升级：追加障碍物并重新保证食物可达。"""
        self.level += 1
        added = self._generate_obstacles(self.cfg.obstacles_per_level)
        if added:
            self.message = "第 %d 关！新增 %d 个障碍物" % (self.level, added)
        else:
            self.message = "第 %d 关！" % self.level
        self.message_timer = 10
        if self.food is not None and not self.is_reachable(self.snake[0], self.food):
            self._spawn_food()

    def _check_win(self):
        """蛇身 + 障碍物铺满棋盘即通关。"""
        if self.food is None and self.occupied >= self.total_cells:
            self.state = ST_WON
            self._update_record()

    def _die(self, reason):
        """死亡处理。"""
        self.state = ST_OVER
        self.death_reason = reason
        self._update_record()

    def _update_record(self):
        """刷新并保存最高分记录。"""
        if self.score > self.high_score:
            self.high_score = self.score
            self.new_record = True
            data = load_scores(self.cfg)
            name = self.cfg.difficulty
            if self.high_score > data.get(name, 0):
                data[name] = self.high_score
                save_scores(self.cfg, data)

    def finalize(self):
        """退出时结算：把本局成绩计入最高分（中途退出也算）。"""
        self._update_record()

    # ------------------------------ 只读属性 ------------------------------

    @property
    def occupied(self):
        """已占用的格子总数。"""
        return len(self.snake) + len(self.obstacles)

    @property
    def total_cells(self):
        return self.width * self.height

    @property
    def bonus_seconds(self):
        """奖励食物剩余时间（秒），用于 HUD 显示。"""
        return self.bonus_timer * self.speed_ms / 1000.0


# ==================== 输入层 ====================

def parse_key_stream(text):
    """把一段输入文本翻译成按键列表（处理 ANSI 方向键序列）。"""
    keys = []
    index = 0
    length = len(text)
    while index < length:
        ch = text[index]
        if ch == ESC:
            # ESC [ A/B/C/D  或  ESC O A/B/C/D
            if index + 2 < length and text[index + 1] in ("[", "O"):
                letter = text[index + 2]
                if letter in ANSI_LETTERS:
                    keys.append(ANSI_LETTERS[letter])
                    index += 3
                    continue
            keys.append(KEY_QUIT)
            index += 1
            continue
        mapped = CHAR_KEYS.get(ch)
        if mapped is not None:
            keys.append(mapped)
        index += 1
    return keys


class KeyReader:
    """非阻塞键盘读取。

    Windows 使用 msvcrt，类 Unix 使用 termios + select。
    既可以作为上下文管理器使用，也可以手动调用 restore()。
    """

    def __init__(self):
        self._fd = None
        self._saved = None

    # ------------------------------ 上下文管理 ------------------------------

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.restore()
        return False

    def setup(self):
        if IS_WINDOWS:
            return
        try:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)  # 关闭行缓冲，保留 Ctrl+C
        except Exception:
            self._saved = None

    def restore(self):
        if IS_WINDOWS or self._saved is None:
            return
        try:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        except Exception:
            pass
        self._saved = None

    # ------------------------------ 读取 ------------------------------

    def poll(self):
        """返回自上次调用以来读取到的按键列表（不会阻塞）。"""
        if IS_WINDOWS:
            return self._poll_windows()
        return self._poll_posix()

    def _poll_windows(self):
        import msvcrt

        keys = []
        while msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):      # 功能键/方向键的前导字节
                nxt = msvcrt.getwch()
                if nxt in ("H", "P", "K", "M"):
                    keys.append({"H": KEY_UP, "P": KEY_DOWN,
                                 "K": KEY_LEFT, "M": KEY_RIGHT}[nxt])
                continue
            if ch == ESC:
                buffer = ch
                while msvcrt.kbhit():
                    buffer += msvcrt.getwch()
                keys.extend(parse_key_stream(buffer))
                continue
            mapped = CHAR_KEYS.get(ch)
            if mapped is not None:
                keys.append(mapped)
        return keys

    def _poll_posix(self):
        import select

        keys = []
        if self._fd is None:
            return keys
        while select.select([self._fd], [], [], 0)[0]:
            try:
                data = os.read(self._fd, 64)
            except OSError:
                break
            if not data:
                break
            keys.extend(parse_key_stream(data.decode("utf-8", "ignore")))
        return keys


# ==================== 渲染层 ====================

COLORS = {
    "reset": CSI + "0m",
    "head": CSI + "1;92m",
    "body": CSI + "32m",
    "food": CSI + "1;91m",
    "bonus": CSI + "1;93m",
    "wall": CSI + "90m",
    "border": CSI + "36m",
    "title": CSI + "1;96m",
    "text": CSI + "97m",
    "dim": CSI + "90m",
    "ok": CSI + "1;92m",
    "warn": CSI + "1;91m",
}

FIG_UNICODE = {
    "empty": " ",
    "head": "◆",
    "body": "●",
    "food": "○",
    "bonus": "★",
    "wall": "▓",
}

FIG_ASCII = {
    "empty": ".",
    "head": "@",
    "body": "o",
    "food": "$",
    "bonus": "*",
    "wall": "#",
}

BORDER_UNICODE = ("┌", "─", "┐", "│", "└", "┘")
BORDER_ASCII = ("+", "-", "+", "|", "+", "+")

LAYOUT_TOP = 5      # 标题 + 分数 + 状态 + 提示 + 空行
LAYOUT_BOTTOM = 1   # 棋盘下方留白


class Renderer:
    """把游戏状态画到终端上。

    plain=True 时只输出纯文本（用于 --headless 与自动化测试），
    不写任何 ANSI 转义序列。
    """

    def __init__(self, cfg, cell_w=2, color=True, ascii_mode=False, plain=False):
        self.cfg = cfg
        self.cell_w = max(1, cell_w)
        self.color = bool(color) and not plain
        self.ascii_mode = ascii_mode
        self.plain = plain
        self.use_ansi = (not plain) and enable_ansi()
        self.fig = dict(FIG_ASCII if ascii_mode else FIG_UNICODE)
        self.border = BORDER_ASCII if ascii_mode else BORDER_UNICODE
        self.frame_count = 0

    # ------------------------------ 终端尺寸 ------------------------------

    @staticmethod
    def terminal_size():
        try:
            size = os.get_terminal_size()
            return int(size.columns), int(size.lines)
        except Exception:
            return 80, 24

    # ------------------------------ 画笔 ------------------------------

    def paint(self, text, color):
        if not self.color or color is None:
            return text
        return COLORS.get(color, "") + text + COLORS["reset"]

    def join_cells(self, cells):
        """cells 是 (颜色名, 文本) 列表，相同颜色会合并以减少转义序列。"""
        if not self.color:
            return "".join(text for _, text in cells)
        parts = []
        previous = None
        for color, text in cells:
            if color != previous:
                parts.append(COLORS.get(color, ""))
                previous = color
            parts.append(text)
        if previous is not None:
            parts.append(COLORS["reset"])
        return "".join(parts)

    def cell_text(self, kind):
        ch = self.fig[kind]
        if kind == "empty":
            return " " * self.cell_w
        return ch + " " * (self.cell_w - 1)

    def cell_of(self, game, cell, body):
        """判断某个格子应该画成什么。"""
        if cell == game.snake[0]:
            kind = "head"
        elif cell in body:
            kind = "body"
        elif game.bonus is not None and cell == game.bonus:
            kind = "bonus"
        elif cell == game.food:
            kind = "food"
        elif cell in game.obstacles:
            kind = "wall"
        else:
            kind = "empty"
        # 奖励食物闪烁提示（每 4 帧闪一次）
        if kind == "bonus" and (self.frame_count // 4) % 2 == 1:
            kind = "empty"
        return kind

    # ------------------------------ 屏幕控制 ------------------------------

    def enter(self):
        """进入游戏画面：切换备用屏幕、隐藏光标、清屏。"""
        if self.plain or not self.use_ansi:
            return
        sys.stdout.write(CSI + "?1049h" + CSI + "?25l" + CSI + "2J" + CSI + "H")
        sys.stdout.flush()

    def cleanup(self):
        """退出游戏画面：恢复光标、离开备用屏幕。"""
        if self.plain or not self.use_ansi:
            return
        sys.stdout.write(CSI + "?25h" + CSI + "0m" + CSI + "?1049l")
        sys.stdout.flush()

    def clear(self):
        if not self.plain:
            os.system("cls" if IS_WINDOWS else "clear")

    def draw(self, lines):
        """把整帧一次性写出去，避免闪烁。"""
        if self.plain:
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()
            return
        if self.use_ansi:
            body = "\r\n".join(line + CSI + "K" for line in lines)
            sys.stdout.write(CSI + "H" + body + CSI + "K")
        else:
            self.clear()
            sys.stdout.write("\r\n".join(lines) + "\r\n")
        sys.stdout.flush()


# ------------------------------ 构建整帧 ------------------------------

    def hud_lines(self, game):
        """棋盘上方的四行信息。"""
        difficulty = DIFFICULTY_NAMES.get(game.cfg.difficulty, game.cfg.difficulty)
        wrap_state = "开" if game.wrap else "关"
        wrap_color = "warn" if game.wrap else "dim"

        line1 = " " + self.paint("贪吃蛇", "title") + "  " + \
            self.paint("[%s]" % difficulty, "text")

        line2 = " 得分 %s   长度 %d   关卡 %d   速度 %dms/格   最高分 %s   穿墙 %s" % (
            self.paint(str(game.score), "ok"),
            len(game.snake),
            game.level,
            game.speed_ms,
            self.paint(str(game.high_score), "food"),
            self.paint(wrap_state, wrap_color),
        )

        if game.message:
            status = self.paint(game.message, "ok")
        elif game.bonus is not None:
            status = " %s 剩余 %.1fs" % (self.paint("★ 奖励食物", "bonus"),
                                        game.bonus_seconds)
        else:
            status = self.paint(" 本关还需 %d 个食物升级" % self.food_to_level_up(game),
                                "dim")

        line3 = " 状态: %s" % self.paint(STATE_NAMES.get(game.state, game.state), "text")
        line3 += "   " + status

        line4 = self.paint(
            " ←↑→↓/WASD 转向   空格 暂停/继续   R 重开   T 穿墙   +/- 调速   Q 退出",
            "dim")

        return [line1, line2, line3, line4, ""]

    @staticmethod
    def food_to_level_up(game):
        per = game.cfg.food_per_level
        if per <= 0:
            return 0
        done = game.food_eaten % per
        return 0 if done == 0 else per - done

    def overlay_lines(self, game, inner=0):
        """标题 / 暂停 / 结束时的提示文字，返回 [(文本, 颜色), ...]。

        inner 是棋盘内部可用列数，超长的文字会被裁剪，避免撑破边框。
        """
        if game.state == ST_TITLE:
            lines = [
                ("贪 吃 蛇", "title"),
                ("", None),
                ("按 空格 开始游戏", "ok"),
                ("方向键 或 WASD 控制", "text"),
                ("空格 暂停    R 重开", "dim"),
                ("T 穿墙    Q 退出", "dim"),
            ]
        elif game.state == ST_PAUSED:
            lines = [
                ("— 已 暂 停 —", "warn"),
                ("", None),
                ("按 空格 继续游戏", "text"),
                ("R 重开    Q 退出", "dim"),
            ]
        elif game.state == ST_WON:
            lines = [
                ("通 关 胜 利 !", "ok"),
                ("", None),
                ("得分 %d   长度 %d" % (game.score, len(game.snake)), "text"),
                ("关卡 %d   用时 %.1fs" % (game.level, game.elapsed), "text"),
                ("最高分 %d" % game.high_score, "dim"),
                ("", None),
                ("按 R 再玩一局", "dim"),
            ]
        elif game.state == ST_OVER:
            lines = [
                (game.death_reason or "游戏结束", "warn"),
                ("", None),
                ("得分 %d   长度 %d" % (game.score, len(game.snake)), "text"),
                ("关卡 %d   用时 %.1fs" % (game.level, game.elapsed), "text"),
                ("最高分 %d%s" % (game.high_score,
                                  "   新纪录!" if game.new_record else ""), "dim"),
                ("", None),
                ("按 R 再玩一次", "dim"),
            ]
        else:
            return []
        if inner > 0:
            lines = [(fit_text(text, inner), color) for text, color in lines]
        return lines

    def board_lines(self, game):
        """棋盘（含边框），必要时叠加居中提示文字。"""
        inner = game.width * self.cell_w
        overlay = self.overlay_lines(game, inner)
        if len(overlay) > game.height:
            overlay = overlay[:game.height]
        start_row = (game.height - len(overlay)) // 2 if overlay else -1

        body = set(game.snake)
        lines = []
        top = self.border[0] + self.border[1] * inner + self.border[2]
        lines.append(self.paint(top, "border"))

        for y in range(game.height):
            index = y - start_row
            if 0 <= index < len(overlay):
                text, color = overlay[index]
                pad = max(0, inner - display_width(text))
                left = pad // 2
                right = pad - left
                content = " " * left + text + " " * right
                lines.append(self.paint(self.border[3], "border") +
                             self.paint(content, color) +
                             self.paint(self.border[3], "border"))
                continue

            cells = [("border", self.border[3])]
            for x in range(game.width):
                cell = (x, y)
                kind = self.cell_of(game, cell, body)
                cells.append((kind, self.cell_text(kind)))
            cells.append(("border", self.border[3]))
            lines.append(self.join_cells(cells))

        bottom = self.border[4] + self.border[1] * inner + self.border[5]
        lines.append(self.paint(bottom, "border"))
        return lines

    def build_frame(self, game):
        """返回整帧文本（字符串列表）。"""
        self.frame_count += 1
        lines = self.hud_lines(game)
        lines.extend(self.board_lines(game))
        lines.extend([""] * LAYOUT_BOTTOM)
        return lines

    def render(self, game):
        self.draw(self.build_frame(game))


# ==================== 自动演示（--headless 用） ====================

def simulate_head(game, direction):
    """假设下一步走 direction，返回新蛇头坐标。"""
    return game.cell_next(game.snake[0], direction)


def direction_safe(game, direction):
    """判断某方向是否立刻安全（不会撞墙/障碍/自己）。"""
    nxt = simulate_head(game, direction)
    if nxt is None or nxt in game.obstacles:
        return False
    grows = (nxt == game.food) or (game.bonus is not None and nxt == game.bonus)
    body = set(game.snake)
    if not grows:
        body.discard(game.snake[-1])
    return nxt not in body


def flood_area(game, direction):
    """走一步之后，蛇头所在连通区域的大小（越大越不容易把自己困死）。"""
    start = simulate_head(game, direction)
    if start is None or start in game.obstacles:
        return -1
    blocked = set(game.obstacles)
    body = list(game.snake)[1:]
    if body:
        body = body[:-1]
    blocked.update(body)
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for step_dir in DIRECTIONS:
            nxt = game.cell_next(cur, step_dir)
            if nxt is None or nxt in seen or nxt in blocked:
                continue
            seen.add(nxt)
            queue.append(nxt)
    return len(seen)


def direction_between(game, start, target):
    """求 start 到相邻格 target 对应的方向（兼容穿墙模式）。"""
    dx = (target[0] - start[0]) % game.width
    dy = (target[1] - start[1]) % game.height
    if dx == 1:
        return RIGHT
    if dx == game.width - 1:
        return LEFT
    if dy == 1:
        return DOWN
    if dy == game.height - 1:
        return UP
    return None


def ai_direction(game):
    """贪心 AI：优先沿最短路径冲向食物，无路可走时选最开阔的方向。"""
    head = game.snake[0]
    target = game.food if game.food is not None else game.bonus
    if target is not None:
        path = game.find_path(head, target)
        if path and len(path) > 1:
            direction = direction_between(game, head, path[1])
            if direction is not None and direction_safe(game, direction):
                return direction

    best = None
    best_area = -1
    for direction in DIRECTIONS:
        if not direction_safe(game, direction):
            continue
        area = flood_area(game, direction)
        if area > best_area:
            best_area = area
            best = direction
    return best if best is not None else game.direction


def run_headless(cfg, steps, cell_w=1, ascii_mode=True):
    """无需人工操作，用 AI 自动跑 steps 步，用于验证逻辑与渲染。"""
    game = SnakeGame(cfg)
    game.state = ST_PLAYING
    renderer = Renderer(cfg, cell_w=cell_w, color=False,
                        ascii_mode=ascii_mode, plain=True)

    frames = 0
    while frames < steps and game.state == ST_PLAYING:
        game.direction = ai_direction(game)
        game.step()
        frames += 1
        renderer.build_frame(game)   # 每一步都渲染，确保渲染路径不会出错

    print("=" * 62)
    print("自动演示结果（--headless %d）" % steps)
    print("  难度      : %s" % DIFFICULTY_NAMES.get(cfg.difficulty, cfg.difficulty))
    print("  棋盘      : %d x %d" % (cfg.width, cfg.height))
    print("  穿墙      : %s" % ("开" if game.wrap else "关"))
    print("  随机种子  : %s" % str(cfg.seed))
    print("  实际步数  : %d" % frames)
    print("  结束状态  : %s %s" % (STATE_NAMES.get(game.state, game.state),
                                  game.death_reason))
    print("  得分      : %d" % game.score)
    print("  蛇长      : %d" % len(game.snake))
    print("  关卡      : %d" % game.level)
    print("  障碍物    : %d" % len(game.obstacles))
    print("  最高分    : %d" % game.high_score)
    print("=" * 62)
    print("最终画面（纯文本渲染，每帧 %d 行）：" % len(renderer.build_frame(game)))
    print("\n".join(renderer.build_frame(game)))
    return 0


# ==================== 内置自测 ====================

def temp_score_file():
    """自测使用临时最高分文件，避免污染真实记录。"""
    base = os.environ.get("TEMP") or os.environ.get("TMP") or "."
    return os.path.join(base, "snake_selftest_scores.json")


def build_test_game(width=20, height=12, wrap=False, seed=7, **overrides):
    """构造一个干净的可测局面（无障碍、食物可控）。"""
    preset = dict(DIFFICULTIES["normal"])
    preset.update(overrides)
    cfg = Config(width=width, height=height, wrap=wrap, seed=seed,
                 difficulty="normal", score_file=temp_score_file(), **preset)
    game = SnakeGame(cfg)
    game.obstacles = set()
    game.bonus = None
    game.bonus_timer = 0
    game.food = None
    game.state = ST_PLAYING
    return game


def run_selftest():
    """不需要终端交互的自测，覆盖移动、吃食物、撞墙、穿墙、升级等逻辑。"""
    results = []

    def check(name, condition, detail=""):
        results.append((name, bool(condition), detail))

    # ---- 1. 直行 ----
    game = build_test_game()
    head = game.snake[0]
    size = len(game.snake)
    game.direction = RIGHT
    game.step()
    check("向右直行一格", game.snake[0] == (head[0] + 1, head[1]),
          "head=%s" % (game.snake[0],))
    check("直行时长度不变", len(game.snake) == size)

    # ---- 2. 吃普通食物 ----
    game = build_test_game()
    head = game.snake[0]
    size = len(game.snake)
    score = game.score
    speed = game.speed_ms
    game.direction = RIGHT
    game.food = (head[0] + 1, head[1])
    game.step()
    check("吃到食物蛇变长", len(game.snake) == size + 1)
    check("吃到食物加分", game.score == score + game.cfg.food_points)
    check("吃到食物后加速", game.speed_ms < speed)
    check("吃完食物会刷新新食物", game.food is not None)

    # ---- 3. 撞墙 ----
    game = build_test_game(width=10, height=8)
    game.snake = deque([(9, 4), (8, 4), (7, 4)])
    game.direction = RIGHT
    game.step()
    check("撞墙判负", game.state == ST_OVER and "墙壁" in game.death_reason,
          "state=%s reason=%s" % (game.state, game.death_reason))

    # ---- 4. 穿墙 ----
    game = build_test_game(width=10, height=8, wrap=True)
    game.snake = deque([(9, 4), (8, 4), (7, 4)])
    game.direction = RIGHT
    game.step()
    check("穿墙模式可从右侧穿到左侧",
          game.state == ST_PLAYING and game.snake[0] == (0, 4),
          "head=%s state=%s" % (game.snake[0], game.state))

    # ---- 5. 撞自己 ----
    game = build_test_game()
    game.snake = deque([(5, 5), (5, 6), (6, 6), (6, 5)])
    game.direction = DOWN
    game.step()
    check("咬到自己判负", game.state == ST_OVER and "自己" in game.death_reason,
          "state=%s reason=%s" % (game.state, game.death_reason))

    # ---- 6. 追尾不算死（尾巴会让开） ----
    game = build_test_game()
    game.snake = deque([(5, 5), (6, 5), (6, 6), (5, 6)])
    game.direction = DOWN
    game.step()
    check("追到尾巴位置不算死", game.state == ST_PLAYING and game.snake[0] == (5, 6),
          "state=%s head=%s" % (game.state, game.snake[0]))

    # ---- 7. 撞障碍物 ----
    game = build_test_game()
    game.snake = deque([(5, 5), (4, 5), (3, 5)])
    game.obstacles = {(6, 5)}
    game.direction = RIGHT
    game.step()
    check("撞障碍物判负", game.state == ST_OVER and "障碍" in game.death_reason,
          "state=%s reason=%s" % (game.state, game.death_reason))

    # ---- 8. 方向缓冲不允许反向，但允许两次转弯 ----
    game = build_test_game()
    game.direction = RIGHT
    game.pending.clear()
    check("禁止直接 180 度掉头", game.queue_direction(LEFT) is False)
    check("允许先向上转", game.queue_direction(UP) is True)
    check("允许再向左转", game.queue_direction(LEFT) is True)
    check("缓冲最多暂存两步", game.queue_direction(DOWN) is False)
    game.snake = deque([(5, 5), (4, 5), (3, 5)])
    game.step()
    check("缓冲的方向第一步生效", game.snake[0] == (5, 4), "head=%s" % (game.snake[0],))
    game.step()
    check("缓冲的方向第二步生效", game.snake[0] == (4, 4), "head=%s" % (game.snake[0],))


# ---- 9. 障碍物生成不会覆盖蛇身与食物 ----
    game = build_test_game(width=20, height=12)
    head = game.snake[0]
    game.food = (head[0] + 1, head[1])   # 紧贴蛇头，保证一定可达
    game.obstacles = set()
    game._generate_obstacles(20)
    check("障碍物数量正确", len(game.obstacles) == 20,
          "count=%d" % len(game.obstacles))
    check("障碍物不与蛇身重叠", not (game.obstacles & set(game.snake)))
    check("障碍物不与食物重叠", game.food not in game.obstacles)

    # ---- 10. BFS 可达性 ----
    game = build_test_game(width=11, height=11)
    game.snake = deque([(5, 5)])
    game.food = (10, 10)
    game.obstacles = {(4, 4), (5, 4), (6, 4), (4, 5), (6, 5), (4, 6), (5, 6), (6, 6)}
    check("被围住时判定为不可达", game.is_reachable((5, 5), (10, 10)) is False)
    game.obstacles.discard((6, 5))
    check("缺口打开后判定为可达", game.is_reachable((5, 5), (10, 10)) is True)

    # ---- 11. 障碍物把食物堵死时自动拆墙 ----
    game = build_test_game(width=11, height=11)
    game.snake = deque([(5, 5)])
    game.food = (10, 10)
    game.obstacles = {(4, 4), (5, 4), (6, 4), (4, 5), (6, 5), (4, 6), (5, 6), (6, 6)}
    game._ensure_reachable()
    check("堵死时自动拆墙直到可达",
          game.is_reachable(game.snake[0], game.food) is True,
          "obstacles=%d" % len(game.obstacles))
    check("拆墙只拆必要的（保留其余障碍）", len(game.obstacles) >= 7,
          "obstacles=%d" % len(game.obstacles))

    # ---- 12. 奖励食物：吃到加分 ----
    game = build_test_game(width=15, height=10)
    game.snake = deque([(1, 1), (0, 1)])
    game.direction = RIGHT
    game.food = None
    game.bonus = (2, 1)
    game.bonus_timer = 10
    game.score = 0
    game.step()
    check("吃到奖励食物加高分",
          game.score == game.cfg.bonus_points + 10 and game.bonus is None,
          "score=%d bonus=%s" % (game.score, game.bonus))
    check("吃奖励食物也会变长", len(game.snake) == 3)

    # ---- 13. 奖励食物：超时消失 ----
    game = build_test_game(width=15, height=10, wrap=True)
    game.snake = deque([(1, 1), (0, 1)])
    game.direction = RIGHT
    game.food = None
    game.bonus = (5, 5)                 # 与蛇的路线不重合
    game.bonus_timer = game.cfg.bonus_lifetime
    lifetime = game.cfg.bonus_lifetime
    for _ in range(lifetime):
        game.step()
    check("奖励食物超时后消失", game.bonus is None and game.bonus_timer == 0,
          "bonus=%s timer=%d" % (game.bonus, game.bonus_timer))
    check("超时期间没有意外死亡", game.state == ST_PLAYING, "state=%s" % game.state)

    # ---- 14. 关卡晋升会追加障碍物 ----
    game = build_test_game(width=25, height=15, food_per_level=3,
                           obstacles_per_level=2, obstacles_start=0)
    game.snake = deque([(1, 1), (0, 1), (0, 0)])
    game.food = (2, 1)                  # 紧贴蛇头，保证可达
    game.obstacles = set()
    before = len(game.obstacles)
    game._level_up()
    check("升级后关卡 +1", game.level == 2, "level=%d" % game.level)
    check("升级后新增障碍物", len(game.obstacles) == before + 2,
          "before=%d after=%d" % (before, len(game.obstacles)))
    check("升级后食物依然可达",
          game.food is None or game.is_reachable(game.snake[0], game.food))


# ---- 15. 铺满棋盘即通关 ----
    game = build_test_game(width=3, height=3)
    game.obstacles = set()
    game.bonus = None
    game.snake = deque([(1, 0), (0, 0), (0, 1), (0, 2),
                        (1, 2), (2, 2), (2, 1), (2, 0)])
    game.direction = DOWN
    game.food = (1, 1)
    game.step()
    check("铺满棋盘判定通关", game.state == ST_WON,
          "state=%s food=%s" % (game.state, game.food))

    # ---- 16. 暂停时不移动 ----
    game = build_test_game()
    game.direction = RIGHT
    head = game.snake[0]
    game.toggle_pause()
    game.step()
    check("暂停时蛇不动", game.snake[0] == head)
    game.toggle_pause()
    game.step()
    check("继续后蛇重新移动", game.snake[0] == (head[0] + 1, head[1]))

    # ---- 17. 随机格子不会落在蛇身/障碍物上 ----
    game = build_test_game(width=12, height=10)
    game.obstacles = set()
    game._generate_obstacles(5)
    ok = True
    for _ in range(200):
        cell = game._random_free_cell()
        if cell is None or cell in game.snake or cell in game.obstacles:
            ok = False
            break
    check("随机格子避开蛇身与障碍物", ok)

    # ---- 18. 渲染帧结构 ----
    game = build_test_game(width=8, height=6)
    expected = LAYOUT_TOP + game.height + 2 + LAYOUT_BOTTOM
    plain_renderer = Renderer(game.cfg, cell_w=1, color=False,
                              ascii_mode=True, plain=True)
    frame = plain_renderer.build_frame(game)
    check("纯文本渲染行数正确", len(frame) == expected,
          "got=%d want=%d" % (len(frame), expected))
    check("渲染出棋盘边框", "+" in frame[LAYOUT_TOP])
    color_renderer = Renderer(game.cfg, cell_w=2, color=True,
                              ascii_mode=False, plain=False)
    color_frame = color_renderer.build_frame(game)
    check("彩色渲染包含转义序列", any(CSI in line for line in color_frame))
    check("彩色渲染行数一致", len(color_frame) == expected,
          "got=%d want=%d" % (len(color_frame), expected))
    game.state = ST_TITLE
    check("标题界面会叠加提示文字",
          "贪 吃 蛇" in "".join(plain_renderer.build_frame(game)))
    game.state = ST_OVER
    game.death_reason = "测试死因"
    check("结束界面会叠加死因",
          "测试死因" in "".join(plain_renderer.build_frame(game)))

    # ---- 19. 按键解析 ----
    keys = parse_key_stream("\x1b[A\x1b[B\x1b[C\x1b[D")
    check("解析 ANSI 方向键", keys == [KEY_UP, KEY_DOWN, KEY_RIGHT, KEY_LEFT],
          "keys=%s" % keys)
    keys = parse_key_stream("wasd")
    check("解析 WASD", keys == [KEY_UP, KEY_LEFT, KEY_DOWN, KEY_RIGHT],
          "keys=%s" % keys)
    keys = parse_key_stream(" \x1b")
    check("解析空格与 ESC", keys == [KEY_PAUSE, KEY_QUIT], "keys=%s" % keys)

    # ---- 20. 最高分文件读写 ----
    cfg = Config(score_file=temp_score_file())
    try:
        os.remove(temp_score_file())
    except OSError:
        pass
    check("最高分文件缺失时自动重建",
          load_scores(cfg) == {k: 0 for k in DIFFICULTIES})
    save_scores(cfg, {"normal": 123, "easy": 5, "hard": 0})
    check("最高分可以保存并读回", load_scores(cfg).get("normal") == 123,
          "data=%s" % load_scores(cfg))
    with open(temp_score_file(), "w", encoding="utf-8") as handle:
        handle.write("{ 这不是合法的 json")
    check("最高分文件损坏时不崩溃",
          load_scores(cfg) == {k: 0 for k in DIFFICULTIES})
    try:
        os.remove(temp_score_file())
    except OSError:
        pass

    # ---- 输出结果 ----
    name_width = max(display_width(name) for name, _, _ in results)
    passed = 0
    for name, ok, detail in results:
        if ok:
            passed += 1
        pad = " " * (name_width - display_width(name))
        line = "  [%s] %s%s" % ("PASS" if ok else "FAIL", name, pad)
        if detail and not ok:
            line += "   -> %s" % detail
        print(line)

    print("-" * 62)
    if passed == len(results):
        print("ALL TESTS PASSED  (%d/%d)" % (passed, len(results)))
        return 0
    print("TESTS FAILED  (%d/%d)" % (passed, len(results)))
    return 1


# ==================== 终端布局 ====================

def resolve_layout(cfg, term_cols, term_lines):
    """按终端尺寸调整棋盘大小，返回 (每格字符数, 错误信息)。

    棋盘太大会溢出、太小会看不清，这里统一夹到合适范围。
    """
    if term_cols < 24 or term_lines < 14:
        return 1, ("终端窗口太小了（当前 %d 列 x %d 行）。\n"
                   "请把窗口调到至少 24 列 x 14 行再运行，"
                   "或直接双击 run_snake.bat（它会自动设置窗口大小）。"
                   % (term_cols, term_lines))

    cell_w = 2 if term_cols >= 70 else 1
    max_width = max(8, (term_cols - 2) // cell_w)
    max_height = max(6, term_lines - LAYOUT_TOP - LAYOUT_BOTTOM - 2)

    if cfg.width > max_width:
        cfg.width = max_width
    if cfg.height > max_height:
        cfg.height = max_height
    return cell_w, ""


# ==================== 主循环 ====================

def start_fresh(game, cfg):
    """重开一局（不回到标题界面）。"""
    game.reset()
    saved = load_scores(cfg).get(cfg.difficulty, 0)
    game.high_score = max(game.high_score, saved)
    game.state = ST_PLAYING


def handle_key(game, cfg, key):
    """处理一个按键，返回 False 表示要退出游戏。"""
    if key == KEY_QUIT:
        return False

    if key == KEY_RESTART:
        start_fresh(game, cfg)
        return True

    if key in (KEY_PAUSE, KEY_START):
        if game.state == ST_TITLE:
            game.start()
        elif game.state in (ST_OVER, ST_WON):
            start_fresh(game, cfg)
        else:
            game.toggle_pause()
        return True

    if key in DIR_KEYS:
        if game.state in (ST_TITLE, ST_OVER, ST_WON):
            start_fresh(game, cfg)
        game.queue_direction(DIR_KEYS[key])
        return True

    if key == KEY_WRAP:
        game.wrap = not game.wrap
        game.message = "穿墙模式已%s" % ("开启" if game.wrap else "关闭")
        game.message_timer = 8
        return True

    if key == KEY_FASTER:
        game.speed_ms = max(cfg.min_speed_ms, game.speed_ms - 10)
        game.message = "当前速度 %d 毫秒/格" % game.speed_ms
        game.message_timer = 6
        return True

    if key == KEY_SLOWER:
        game.speed_ms = min(400, game.speed_ms + 10)
        game.message = "当前速度 %d 毫秒/格" % game.speed_ms
        game.message_timer = 6
        return True

    return True


def run_game(cfg, renderer, autoplay=0):
    """交互式主循环。

    autoplay > 0 时改由 AI 自动操作，用于带画面的演示与自检。
    """
    auto = autoplay
    game = SnakeGame(cfg)
    game.high_score = load_scores(cfg).get(cfg.difficulty, 0)

    reader = KeyReader()
    renderer.enter()
    reader.setup()
    if auto > 0:
        game.start()

    running = True
    dirty = True
    accumulator = 0.0
    last_time = time.perf_counter()
    last_render = 0.0

    try:
        while running:
            now = time.perf_counter()
            delta = now - last_time
            last_time = now
            if delta > 0.25:          # 电脑卡顿/休眠后不要一次补太多帧
                delta = 0.25

            for key in reader.poll():
                dirty = True
                if not handle_key(game, cfg, key):
                    running = False

            if not running:
                break

            if game.state == ST_PLAYING:
                accumulator += delta
                step_seconds = game.speed_ms / 1000.0
                while accumulator >= step_seconds and game.state == ST_PLAYING:
                    accumulator -= step_seconds
                    if auto > 0:
                        game.direction = ai_direction(game)
                    game.step()
                    dirty = True
                    if auto > 0:
                        auto -= 1
                        if auto <= 0:
                            running = False
                    step_seconds = game.speed_ms / 1000.0
                if accumulator > step_seconds:
                    accumulator = 0.0
            else:
                accumulator = 0.0

            if dirty or (now - last_render) > 0.2:
                renderer.render(game)
                last_render = now
                dirty = False

            time.sleep(0.008)
    finally:
        reader.restore()
        renderer.cleanup()

    # 退出后把成绩打印到普通屏幕上
    game.finalize()
    print("本局得分 %d，蛇长 %d，关卡 %d，用时 %.1f 秒。"
          % (game.score, len(game.snake), game.level, game.elapsed))
    print("%s 最高分：%d"
          % (DIFFICULTY_NAMES.get(cfg.difficulty, cfg.difficulty), game.high_score))
    if game.new_record:
        print("恭喜！刷新了最高分记录。")
    return 0


# ==================== 命令行入口 ====================

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="snake.py",
        description="终端贪吃蛇（纯 Python 标准库实现，无需第三方依赖）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-d", "--difficulty", choices=["easy", "normal", "hard"],
                        default="normal",
                        help="难度预设：easy(简单) / normal(普通) / hard(困难)，默认 normal")
    parser.add_argument("-W", "--width", type=int, default=None,
                        help="棋盘宽度（格子数），默认按终端大小自动适配")
    parser.add_argument("-H", "--height", type=int, default=None,
                        help="棋盘高度（格子数），默认按终端大小自动适配")
    parser.add_argument("--speed", type=int, default=None,
                        help="初始速度（毫秒/格），覆盖难度预设，越小越快")
    parser.add_argument("--wrap", action="store_true",
                        help="开启穿墙模式（游戏中也可按 T 切换）")
    parser.add_argument("--obstacles", type=int, default=None,
                        help="初始障碍物数量，覆盖难度预设")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色显示")
    parser.add_argument("--ascii", action="store_true",
                        help="使用纯 ASCII 字符绘制（对齐最稳，但不美观）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，指定后每次开局完全一样（便于复现）")
    parser.add_argument("--headless", type=int, default=0, metavar="N",
                        help="不用人工操作，让 AI 自动跑 N 步（用于验证与演示）")
    parser.add_argument("--demo", type=int, default=0, metavar="N",
                        help="进入游戏画面后由 AI 自动操作 N 步（带画面的演示）")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    return parser.parse_args(argv)


def build_config(args):
    """把命令行参数与难度预设合并成一份完整配置。"""
    preset = dict(DIFFICULTIES[args.difficulty])
    cfg = Config(difficulty=args.difficulty, **preset)

    if args.width:
        cfg.width = max(8, args.width)
    if args.height:
        cfg.height = max(6, args.height)
    if args.speed:
        cfg.speed_ms = max(20, args.speed)
        cfg.min_speed_ms = min(cfg.min_speed_ms, cfg.speed_ms)
    if args.obstacles is not None:
        cfg.obstacles_start = max(0, args.obstacles)
    if args.wrap:
        cfg.wrap = True
    cfg.seed = args.seed
    return cfg


def main(argv=None):
    # 中文在部分终端上可能编码不匹配，用 replace 兜底，避免直接抛异常
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    args = parse_args(argv)

    if args.selftest:
        return run_selftest()

    cfg = build_config(args)

    if args.headless:
        return run_headless(cfg, args.headless, cell_w=1, ascii_mode=True)

    # 非交互式环境（输出被重定向、没有终端）无法读取键盘，
    # 提前给出提示，避免游戏在后台空转。
    if args.demo <= 0 and not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("当前不是交互式终端（stdin/stdout 被重定向），无法接收键盘输入。")
        print("请在真实终端里运行：Windows Terminal / VS Code 终端 / cmd / Git Bash")
        print("想先看效果可以用：python snake.py --demo 200   或   python snake.py --headless 400")
        return 3

    term_cols, term_lines = Renderer.terminal_size()
    cell_w, error = resolve_layout(cfg, term_cols, term_lines)
    if error:
        print(error)
        return 2

    renderer = Renderer(cfg, cell_w=cell_w, color=not args.no_color,
                        ascii_mode=args.ascii)

    print("贪吃蛇 正在启动……")
    print("难度 %s，棋盘 %d x %d，穿墙 %s"
          % (DIFFICULTY_NAMES.get(cfg.difficulty, cfg.difficulty),
             cfg.width, cfg.height,
             "开" if cfg.wrap else "关"))
    print("操作：方向键/WASD 转向，空格 暂停，R 重开，T 穿墙，+/- 调速，Q 退出")
    time.sleep(0.8)
    return run_game(cfg, renderer, autoplay=args.demo)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已退出，感谢游玩！")
        sys.exit(0)