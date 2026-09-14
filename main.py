# -*- coding: utf-8 -*-
"""
一箭又一箭 —— 关卡流程 + 飞出动画 + 失误机制 + 阻挡碰撞动画
三个关卡完整流程：第1关→第2关→第3关→全部通关。
点击可飞出的箭头后，箭头沿所指方向飞出棋盘，再从 BOARD 删除。
点击被阻挡的箭头时，箭头会向前移动→碰撞震动→原路返回，并扣除一次失误。
"""

import copy
import math
import pygame

# ---------- 基本配置 ----------
WINDOW_WIDTH = 900    # 窗口宽
WINDOW_HEIGHT = 700   # 窗口高
GRID_SIZE = 8         # 8x8 棋盘
CELL_SIZE = 60        # 每个格子的边长（像素）
ARROW_SPEED = 5.0     # 飞出动画每帧移动的像素数（60FPS 时约 300 像素/秒）
MAX_MISTAKES = 3      # 每关允许的最大失误次数

# 被阻挡箭头动画相关配置
BLOCKED_SPEED = 10.0      # 前进/返回速度（像素/帧，60FPS 时约 600 像素/秒）
COLLISION_DURATION = 0.2  # 碰撞震动持续时间（秒）
SHAKE_AMP = 6.0           # 震动幅度（像素）
SAFE_GAP = CELL_SIZE      # 与障碍箭头中心保持的安全距离（约一个格子）

# 颜色 (R, G, B)
COLOR_BG = (52, 73, 94)          # 游戏背景：深蓝灰
COLOR_BOARD = (236, 240, 241)    # 棋盘底色：浅灰白
COLOR_CELL_A = (255, 255, 255)   # 格子颜色 A：白
COLOR_CELL_B = (189, 215, 238)   # 格子颜色 B：淡蓝
COLOR_GRID_LINE = (44, 62, 80)   # 网格线：深色
COLOR_ARROW = (192, 57, 43)      # 箭头颜色：砖红

# 四种箭头方向：每个方向对应 (水平分量, 垂直分量)
# 例如 "up" 表示箭头指向上方（屏幕 y 轴向下为正，所以 y 取 -1）
DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# ---------- 关卡数据 ----------
# 每个关卡是一个 8x8 二维列表：空字符串表示空格子，
# "up"/"down"/"left"/"right" 表示对应方向的箭头。
# 三个关卡都经过 is_level_solvable 验证，确保可通关且无死锁。

LEVEL_1 = [
    ["right", "",      "", "", "", "", "", ""],
    ["",      "",      "", "", "", "", "", "left"],
    ["down",  "",      "", "", "", "", "", ""],
    ["",      "",      "", "", "", "", "", ""],
    ["",      "",      "", "", "", "", "", ""],
    ["",      "",      "", "", "", "", "", ""],
    ["",      "",      "", "", "", "", "", ""],
    ["",      "up",    "", "", "", "", "", ""],
]

LEVEL_2 = [
    ["right", "",      "", "", "",      "", "", ""],
    ["",      "",      "", "", "",      "", "", "left"],
    ["",      "",      "", "", "",      "", "", ""],
    ["right", "",      "", "", "right", "", "", ""],
    ["",      "",      "", "", "",      "", "", ""],
    ["",      "",      "", "", "",      "", "", ""],
    ["",      "",      "", "", "",      "", "", ""],
    ["",      "up",    "", "", "",      "", "", ""],
]

LEVEL_3 = [
    ["right", "", "",      "", "", "", "", ""],
    ["",      "", "",      "", "", "", "", "left"],
    ["",      "", "down",  "", "", "", "", ""],
    ["",      "", "",      "", "", "", "", ""],
    ["",      "", "down",  "", "", "", "", ""],
    ["",      "", "",      "", "", "", "", ""],
    ["",      "", "down",  "", "", "", "", ""],
    ["",      "up", "",    "", "", "", "", ""],
]

LEVELS = [LEVEL_1, LEVEL_2, LEVEL_3]

# 当前游戏使用的关卡（默认第 1 关；用副本避免修改 LEVELS 原始数据）
BOARD = [row[:] for row in LEVELS[0]]

# ---------- 游戏流程状态 ----------
current_level = 0  # 当前关卡索引：0=第1关, 1=第2关, 2=第3关

# 游戏状态机：
#   "start"          —— 开始界面，等待玩家点"开始游戏"
#   "playing"       —— 正在游戏中，可以点击箭头
#   "level_complete" —— 当前关卡通关，等待玩家点"下一关"
#   "game_complete"  —— 全部关卡通关，等待玩家点"重新开始"
#   "game_over"      —— 失误次数耗尽，游戏失败，等待玩家点"重新开始"
game_state = "start"

# 玩家当前剩余的失误次数，进入新关卡时重置为 MAX_MISTAKES
mistakes_left = MAX_MISTAKES


def load_level(level_index):
    """加载第 level_index 关，把对应 LEVELS 数据复制一份到 BOARD。

    使用 deepcopy 确保每个关卡都是独立副本，
    避免不同关卡共享同一份棋盘数据。
    """
    global BOARD, current_level, mistakes_left, blocked_arrow_animation, pending_game_over
    current_level = level_index
    BOARD = copy.deepcopy(LEVELS[level_index])
    mistakes_left = MAX_MISTAKES  # 进入新关卡时重置失误次数
    blocked_arrow_animation = None  # 清空可能残留的被阻挡动画
    pending_game_over = False


def count_arrows():
    """统计当前 BOARD 中还剩多少个箭头。"""
    total = 0
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            if BOARD[row][col]:
                total += 1
    return total


# 正在飞出的箭头列表。每个元素是一个字典：
# {"row", "col", "direction", "x", "y", "speed"}
# x/y 是箭头中心点的像素坐标（用浮点数，方便平滑移动）。
flying_arrows = []

# 正在播放的“被阻挡箭头”动画；None 表示没有。
# 字典字段：
#   row, col, direction : 被点击箭头的位置与方向（direction 全程不变）
#   start_x, start_y     : 原始格子中心像素坐标（返回目标）
#   current_x, current_y : 当前像素坐标
#   target_x, target_y   : 碰撞位置（障碍箭头前的安全距离处）
#   block_row, block_col : 第一个障碍箭头的位置（仅用于绘制时轻微震动）
#   phase                : "moving_forward" / "collision" / "moving_back"
#   timer                : 碰撞阶段已持续的时间（秒）
#   speed                : 前进/返回速度
blocked_arrow_animation = None

# 当失误次数在被阻挡动画中耗尽时，延迟到动画结束再进入 game_over
pending_game_over = False


def find_blocking_arrow(row, col):
    """沿 (row, col) 箭头所指方向，寻找路径上的第一个障碍箭头。

    返回 (block_row, block_col)；如果方向上没有任何箭头，返回 None。
    注意：返回的是“第一个”障碍箭头，不是最后一个。
    """
    direction = BOARD[row][col]
    if not direction:
        return None

    if direction == "right":
        for c in range(col + 1, GRID_SIZE):
            if BOARD[row][c]:
                return row, c
    elif direction == "left":
        for c in range(col - 1, -1, -1):
            if BOARD[row][c]:
                return row, c
    elif direction == "down":
        for r in range(row + 1, GRID_SIZE):
            if BOARD[r][col]:
                return r, col
    elif direction == "up":
        for r in range(row - 1, -1, -1):
            if BOARD[r][col]:
                return r, col
    return None


def is_cell_blocked_animating(row, col):
    """判断 (row, col) 是否是正在播放被阻挡动画的箭头。"""
    if blocked_arrow_animation is None:
        return False
    ba = blocked_arrow_animation
    return ba["row"] == row and ba["col"] == col


def get_blocker_of_animation():
    """如果当前有被阻挡动画，返回其障碍箭头的 (row, col)；否则返回 None。"""
    if blocked_arrow_animation is None:
        return None
    return blocked_arrow_animation["block_row"], blocked_arrow_animation["block_col"]


def draw_arrow(surface, color, center_x, center_y, direction, length=36):
    """在指定中心点画一个箭头（一条线 + 三角形箭头尖）。"""
    dx, dy = DIRECTIONS[direction]
    # 箭杆：从中心向“箭头所指方向”画一条线
    tail_x = center_x - dx * (length // 2)
    tail_y = center_y - dy * (length // 2)
    tip_x = center_x + dx * (length // 2)
    tip_y = center_y + dy * (length // 2)
    pygame.draw.line(surface, color, (tail_x, tail_y), (tip_x, tip_y), 4)

    # 箭头尖：一个三角形。先画一个朝右的三角，再旋转到目标方向。
    size = 10
    if direction == "up":
        points = [(tip_x, tip_y - size), (tip_x - size, tip_y + size // 2),
                  (tip_x + size, tip_y + size // 2)]
    elif direction == "down":
        points = [(tip_x, tip_y + size), (tip_x - size, tip_y - size // 2),
                  (tip_x + size, tip_y - size // 2)]
    elif direction == "left":
        points = [(tip_x - size, tip_y), (tip_x + size // 2, tip_y - size),
                  (tip_x + size // 2, tip_y + size)]
    else:  # right
        points = [(tip_x + size, tip_y), (tip_x - size // 2, tip_y - size),
                  (tip_x - size // 2, tip_y + size)]
    pygame.draw.polygon(surface, color, points)


def build_board_rect(window):
    """计算居中棋盘的整体矩形位置，返回 (棋盘左上角x, 棋盘左上角y, 棋盘边长)。"""
    board_px = GRID_SIZE * CELL_SIZE
    board_x = (WINDOW_WIDTH - board_px) // 2   # 水平居中
    board_y = (WINDOW_HEIGHT - board_px) // 2  # 垂直居中
    return board_x, board_y, board_px


def is_cell_flying(row, col):
    """判断 (row, col) 是否是正在飞出的箭头所在的格子。"""
    for fa in flying_arrows:
        if fa["row"] == row and fa["col"] == col:
            return True
    return False


def draw_board(surface, board_x, board_y):
    """绘制棋盘背景格子、网格线，以及每个格子里的箭头。"""
    # 棋盘底色
    board_px = GRID_SIZE * CELL_SIZE
    pygame.draw.rect(surface, COLOR_BOARD,
                     (board_x, board_y, board_px, board_px))

    # 逐格绘制：棋盘交替色 + 箭头
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            cell_x = board_x + col * CELL_SIZE
            cell_y = board_y + row * CELL_SIZE
            cell_rect = (cell_x, cell_y, CELL_SIZE, CELL_SIZE)

            # (行 + 列) 奇偶交替，形成类似国际象棋的棋盘纹
            if (row + col) % 2 == 0:
                color = COLOR_CELL_A
            else:
                color = COLOR_CELL_B
            pygame.draw.rect(surface, color, cell_rect)
            pygame.draw.rect(surface, COLOR_GRID_LINE, cell_rect, 1)

            # 如果这个格子有箭头且没有正在飞出，也没有在播放被阻挡动画，
            # 就画出来。
            # 注意：障碍箭头只在“碰撞”阶段改由动画代码绘制（带震动），
            # 其余阶段仍在这里正常绘制，避免前进/返回时障碍箭头消失。
            direction = BOARD[row][col]
            blocker = get_blocker_of_animation()
            is_blocker = (blocker is not None and blocker[0] == row and blocker[1] == col)
            in_collision = (blocked_arrow_animation is not None
                            and blocked_arrow_animation["phase"] == "collision")
            skip_blocker = is_blocker and in_collision
            if direction and not is_cell_flying(row, col) \
                    and not is_cell_blocked_animating(row, col) and not skip_blocker:
                center_x = cell_x + CELL_SIZE // 2
                center_y = cell_y + CELL_SIZE // 2
                draw_arrow(surface, COLOR_ARROW, center_x, center_y, direction)


def get_clicked_cell(board_x, board_y, mouse_pos):
    """根据鼠标坐标算出点击的行列号；不在棋盘内则返回 None。"""
    mx, my = mouse_pos
    col = (mx - board_x) // CELL_SIZE
    row = (my - board_y) // CELL_SIZE
    if 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE:
        return row, col
    return None


def can_arrow_exit_on_board(board, row, col):
    """判断 board 中 (row, col) 处的箭头能否沿所指方向飞出棋盘。

    与 can_arrow_exit 的判断逻辑完全相同，只是作用于传入的 board（副本），
    用于关卡可解性模拟，不会修改游戏实际使用的 BOARD。
    """
    direction = board[row][col]
    if not direction:
        return False

    if direction == "right":
        for c in range(col + 1, GRID_SIZE):
            if board[row][c]:
                return False
        return True

    elif direction == "left":
        for c in range(col - 1, -1, -1):
            if board[row][c]:
                return False
        return True

    elif direction == "down":
        for r in range(row + 1, GRID_SIZE):
            if board[r][col]:
                return False
        return True

    elif direction == "up":
        for r in range(row - 1, -1, -1):
            if board[r][col]:
                return False
        return True

    return False


def can_arrow_exit(row, col):
    """判断 BOARD 中 (row, col) 处的箭头能否沿所指方向飞出棋盘。

    规则：从箭头所在格子出发，沿箭头方向一路检查到棋盘边界，
    只要路径上出现其他箭头（任意方向）就会被阻挡，返回 False；
    如果一路到边界都没有其他箭头，返回 True。
    如果该格本身没有箭头，返回 False。
    """
    return can_arrow_exit_on_board(BOARD, row, col)


def is_level_solvable(level):
    """判断一个关卡是否可解，并返回一种通关顺序。

    参数 level: 8x8 二维列表（关卡数据）。
    返回值: (是否可解 bool, 通关顺序 list)。
        通关顺序中每个元素是 (row, col, direction)，表示消除该箭头。

    模拟思路：
    1. 用 deepcopy 复制关卡，避免修改原始数据。
    2. 每一轮找出所有"当前可以飞出"的箭头。
    3. 如果没有可飞出的箭头但棋盘仍有箭头 → 死锁，返回 False。
    4. 否则消除其中一个（贪心），记录顺序，重复。
    5. 直到棋盘清空 → 返回 True 和顺序。

    说明：在本游戏规则下，消除一个箭头只会"解开"其他箭头的阻挡，
    不会制造新的阻挡，因此贪心策略一定能找到解（如果存在的话）。
    """
    board = copy.deepcopy(level)
    order = []

    while True:
        # 收集当前所有可以飞出的箭头
        exitable = []
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if board[r][c] and can_arrow_exit_on_board(board, r, c):
                    exitable.append((r, c))

        if not exitable:
            # 没有可飞出的箭头，结束模拟
            break

        # 消除第一个可飞出的箭头（贪心）
        r, c = exitable[0]
        order.append((r, c, board[r][c]))
        board[r][c] = ""

    # 检查棋盘是否已经完全清空
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if board[r][c]:
                # 还有箭头但无法消除 → 死锁
                return False, order

    return True, order


def verify_levels():
    """验证所有关卡是否可解，并在控制台输出结果与一种通关顺序。

    本函数仅用于开发和测试阶段，不在游戏界面显示。
    """
    print("========== 关卡可解性验证 ==========")
    all_ok = True
    for i, level in enumerate(LEVELS, start=1):
        solvable, order = is_level_solvable(level)
        if solvable:
            print(f"Level {i}: Solvable")
            # 把通关顺序格式化为 "(行,列)方向" 的箭头链
            steps = [f"({r},{c}){d}" for (r, c, d) in order]
            print(f"Level {i} 通关顺序: {' -> '.join(steps)}")
        else:
            print(f"Level {i}: Unsolvable (死锁)")
            all_ok = False
    print("====================================")
    if all_ok:
        print("所有关卡均可通关。")
    else:
        print("警告：存在不可通关的关卡，请检查设计！")
    return all_ok


def is_flying_arrow_off_board(fa, board_x, board_y):
    """判断一个正在飞出的箭头是否已经完全离开棋盘区域。

    fa: 飞出箭头字典，包含 x, y（中心点像素坐标）。
    用箭头中心点距离棋盘边界的余量来判断，确保整支箭头都飞出。
    """
    board_px = GRID_SIZE * CELL_SIZE
    margin = CELL_SIZE // 2  # 半个格子的余量，保证箭头完全离开
    x = fa["x"]
    y = fa["y"]
    if x < board_x - margin or x > board_x + board_px + margin:
        return True
    if y < board_y - margin or y > board_y + board_px + margin:
        return True
    return False


def draw_button(surface, rect, text, font, bg_color, text_color):
    """在 surface 上绘制一个带文字的按钮。

    rect: (x, y, width, height) 按钮矩形
    """
    pygame.draw.rect(surface, bg_color, rect, border_radius=6)
    pygame.draw.rect(surface, (255, 255, 255), rect, 2, border_radius=6)
    text_surf = font.render(text, True, text_color)
    text_rect = text_surf.get_rect(center=(rect[0] + rect[2] // 2,
                                           rect[1] + rect[3] // 2))
    surface.blit(text_surf, text_rect)


def is_click_in_rect(pos, rect):
    """判断鼠标点击坐标 pos 是否落在 rect 矩形内。"""
    x, y = pos
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


# 可能存在的中文字体文件路径（按优先级排列）
CJK_FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
]


def load_cjk_font(size):
    """加载一个支持中文的字体。

    优先从已知的 Windows 字体文件直接加载（避免 SysFont 枚举系统字体时崩溃），
    如果都找不到，则回退到 pygame 默认字体。
    """
    for path in CJK_FONT_PATHS:
        try:
            return pygame.font.Font(path, size)
        except (FileNotFoundError, OSError):
            continue
    # 兜底：使用 pygame 默认字体（可能不支持中文，但不会崩溃）
    return pygame.font.Font(None, size)


def main():
    global game_state, mistakes_left, blocked_arrow_animation, pending_game_over

    # 开发阶段：启动时验证所有关卡的可解性（输出到控制台，不影响游戏界面）
    verify_levels()

    pygame.init()
    window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("一箭又一箭")
    clock = pygame.time.Clock()

    board_x, board_y, _ = build_board_rect(window)

    # ---------- 字体（支持中文） ----------
    # 用字体文件直接加载，避免 SysFont 在某些 Windows 机器上枚举字体时崩溃
    font_big = load_cjk_font(36)
    font_mid = load_cjk_font(24)
    font_btn = load_cjk_font(28)

    # ---------- 按钮矩形 ----------
    # 棋盘下方居中放一个按钮（下一关 / 重新开始 共用位置）
    btn_w, btn_h = 180, 54
    btn_x = (WINDOW_WIDTH - btn_w) // 2
    btn_y = board_y + GRID_SIZE * CELL_SIZE + 30
    action_button_rect = (btn_x, btn_y, btn_w, btn_h)

    # 开始界面的“开始游戏”按钮（屏幕垂直居中偏下）
    start_btn_w, start_btn_h = 200, 60
    start_btn_x = (WINDOW_WIDTH - start_btn_w) // 2
    start_btn_y = WINDOW_HEIGHT // 2 + 40
    start_button_rect = (start_btn_x, start_btn_y, start_btn_w, start_btn_h)

    # 游戏进行中随时可用的“重新开始”按钮（左上角，关卡文字下方）
    restart_btn_w, restart_btn_h = 120, 38
    restart_button_rect = (20, 56, restart_btn_w, restart_btn_h)

    # 启动时进入开始界面（不直接进入游戏）
    load_level(0)
    game_state = "start"

    running = True
    while running:
        # 每帧时间增量（秒），用于碰撞震动等需要真实时间的动画
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # ---- 根据当前游戏状态决定如何响应点击 ----
                if game_state == "start":
                    # 开始界面：只响应“开始游戏”按钮，点击棋盘不产生任何操作
                    if is_click_in_rect(event.pos, start_button_rect):
                        flying_arrows.clear()       # 清空可能残留的飞出箭头
                        load_level(0)               # 从第1关全新开始（重置失误等）
                        game_state = "playing"
                        print("开始游戏，进入第 1 关")

                elif game_state == "playing":
                    # 游戏中：优先处理“重新开始”按钮（随时可用，不受动画限制）
                    if is_click_in_rect(event.pos, restart_button_rect):
                        flying_arrows.clear()        # 清空飞出箭头
                        load_level(0)                # 回到第1关并重置失误
                        game_state = "playing"
                        print("重新开始，回到第 1 关")
                    else:
                        # 否则处理棋盘点击
                        # 如果正在播放被阻挡动画，则暂时禁止点击其他箭头（避免多动画混乱）
                        if blocked_arrow_animation is not None:
                            pass
                        else:
                            cell = get_clicked_cell(board_x, board_y, event.pos)
                            if cell is not None:
                                row, col = cell
                                # 如果点到的是正在飞出的箭头，则不响应（防止重复点击）
                                if is_cell_flying(row, col):
                                    pass
                                else:
                                    direction = BOARD[row][col]
                                    if direction:
                                        if can_arrow_exit(row, col):
                                            print("箭头可以飞出")
                                            # 启动飞出动画：记录像素坐标，加入飞出列表
                                            # （不从 BOARD 立即删除，等飞出棋盘后再删）
                                            center_x = board_x + col * CELL_SIZE + CELL_SIZE // 2
                                            center_y = board_y + row * CELL_SIZE + CELL_SIZE // 2
                                            flying_arrows.append({
                                                "row": row,
                                                "col": col,
                                                "direction": direction,
                                                "x": float(center_x),
                                                "y": float(center_y),
                                                "speed": ARROW_SPEED,
                                            })
                                        else:
                                            # 箭头被阻挡：启动“前进→碰撞→震动→返回”动画
                                            # 一次点击只扣一次失误（在点击时扣，动画过程中不重复扣）
                                            mistakes_left -= 1
                                            print(f"箭头被阻挡，剩余失误次数：{mistakes_left}")

                                            block = find_blocking_arrow(row, col)
                                            # 计算原始中心与碰撞目标位置
                                            start_x = board_x + col * CELL_SIZE + CELL_SIZE // 2
                                            start_y = board_y + row * CELL_SIZE + CELL_SIZE // 2
                                            if block is not None:
                                                br, bc = block
                                                block_x = board_x + bc * CELL_SIZE + CELL_SIZE // 2
                                                block_y = board_y + br * CELL_SIZE + CELL_SIZE // 2
                                            else:
                                                # 理论上被阻挡时一定能找到障碍箭头，这里兜底用棋盘边界
                                                block_x, block_y = start_x, start_y

                                            # 根据方向计算碰撞目标点（停在障碍箭头前 SAFE_GAP 处）
                                            if direction == "right":
                                                target_x = block_x - SAFE_GAP
                                                target_y = start_y
                                            elif direction == "left":
                                                target_x = block_x + SAFE_GAP
                                                target_y = start_y
                                            elif direction == "down":
                                                target_x = start_x
                                                target_y = block_y - SAFE_GAP
                                            else:  # up
                                                target_x = start_x
                                                target_y = block_y + SAFE_GAP

                                            blocked_arrow_animation = {
                                                "row": row,
                                                "col": col,
                                                "direction": direction,  # 方向全程不变
                                                "start_x": float(start_x),
                                                "start_y": float(start_y),
                                                "current_x": float(start_x),
                                                "current_y": float(start_y),
                                                "target_x": float(target_x),
                                                "target_y": float(target_y),
                                                "block_row": block[0] if block else row,
                                                "block_col": block[1] if block else col,
                                                "phase": "moving_forward",
                                                "timer": 0.0,
                                                "speed": BLOCKED_SPEED,
                                            }

                                            # 如果失误耗尽，延迟到动画结束再进入 game_over
                                            if mistakes_left <= 0:
                                                pending_game_over = True
                                    else:
                                        print("这里没有箭头")
                            else:
                                print("点击在棋盘外")

                elif game_state == "level_complete":
                    # 关卡通关：只响应"下一关"按钮
                    if is_click_in_rect(event.pos, action_button_rect):
                        next_level = current_level + 1
                        # 防御：确保不会进入不存在的第 4 关
                        if next_level < len(LEVELS):
                            load_level(next_level)
                            game_state = "playing"
                            print(f"进入第 {current_level + 1} 关")

                elif game_state == "game_complete":
                    # 全部通关：只响应"重新开始"按钮
                    if is_click_in_rect(event.pos, action_button_rect):
                        load_level(0)
                        game_state = "playing"
                        print("重新开始游戏")

                elif game_state == "game_over":
                    # 游戏失败：只响应"重新开始"按钮
                    if is_click_in_rect(event.pos, action_button_rect):
                        flying_arrows.clear()  # 清空残留的飞出箭头
                        load_level(0)
                        game_state = "playing"
                        print("重新开始游戏")

        # ---------- 更新飞出的箭头 ----------
        still_flying = []
        for fa in flying_arrows:
            dx, dy = DIRECTIONS[fa["direction"]]
            fa["x"] += dx * fa["speed"]
            fa["y"] += dy * fa["speed"]
            if is_flying_arrow_off_board(fa, board_x, board_y):
                # 完全飞出棋盘，从 BOARD 中删除该箭头
                BOARD[fa["row"]][fa["col"]] = ""
                print("箭头已飞出棋盘")
                # 飞出后检查本关是否完成
                if game_state == "playing" and count_arrows() == 0:
                    if current_level < len(LEVELS) - 1:
                        game_state = "level_complete"
                    else:
                        game_state = "game_complete"
            else:
                still_flying.append(fa)
        # 原地更新列表，避免重新赋值触发全局变量问题
        flying_arrows.clear()
        flying_arrows.extend(still_flying)

        # ---------- 更新被阻挡箭头动画 ----------
        if blocked_arrow_animation is not None:
            ba = blocked_arrow_animation
            phase = ba["phase"]

            if phase == "moving_forward":
                # 沿箭头所指方向向目标点移动
                dx, dy = DIRECTIONS[ba["direction"]]
                ba["current_x"] += dx * ba["speed"]
                ba["current_y"] += dy * ba["speed"]

                # 判断是否到达（或越过）目标点
                reached = False
                if ba["direction"] == "right" and ba["current_x"] >= ba["target_x"]:
                    reached = True
                elif ba["direction"] == "left" and ba["current_x"] <= ba["target_x"]:
                    reached = True
                elif ba["direction"] == "down" and ba["current_y"] >= ba["target_y"]:
                    reached = True
                elif ba["direction"] == "up" and ba["current_y"] <= ba["target_y"]:
                    reached = True

                if reached:
                    # 吸附到目标点，进入碰撞阶段
                    ba["current_x"] = ba["target_x"]
                    ba["current_y"] = ba["target_y"]
                    ba["phase"] = "collision"
                    ba["timer"] = 0.0

            elif phase == "collision":
                # 碰撞震动阶段：累加计时，到时后进入返回阶段
                ba["timer"] += dt
                if ba["timer"] >= COLLISION_DURATION:
                    ba["phase"] = "moving_back"

            elif phase == "moving_back":
                # 沿与前进相反的方向返回起点（注意：不改变 direction！）
                dx, dy = DIRECTIONS[ba["direction"]]
                ba["current_x"] -= dx * ba["speed"]
                ba["current_y"] -= dy * ba["speed"]

                # 判断是否回到起点
                back = False
                if ba["direction"] == "right" and ba["current_x"] <= ba["start_x"]:
                    back = True
                elif ba["direction"] == "left" and ba["current_x"] >= ba["start_x"]:
                    back = True
                elif ba["direction"] == "down" and ba["current_y"] <= ba["start_y"]:
                    back = True
                elif ba["direction"] == "up" and ba["current_y"] >= ba["start_y"]:
                    back = True

                if back:
                    # 精确回到起点，动画结束
                    ba["current_x"] = ba["start_x"]
                    ba["current_y"] = ba["start_y"]
                    blocked_arrow_animation = None
                    # BOARD[row][col] 保持原来的 direction，箭头不消失

                    # 如果本次失误耗尽了次数，此时才真正进入 game_over
                    if pending_game_over:
                        pending_game_over = False
                        game_state = "game_over"
                        print("游戏失败")

        # ---------- 绘制 ----------
        window.fill(COLOR_BG)

        if game_state == "start":
            # ===== 开始界面：不绘制棋盘和状态栏 =====
            # 标题
            title_surf = font_big.render("一箭又一箭", True, (255, 215, 0))
            title_rect = title_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 80))
            window.blit(title_surf, title_rect)

            # 游戏说明
            tip_surf = font_mid.render("点击箭头，让所有箭头飞出棋盘！", True, (255, 255, 255))
            tip_rect = tip_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 20))
            window.blit(tip_surf, tip_rect)

            # 开始游戏按钮
            draw_button(window, start_button_rect, "开始游戏", font_btn,
                        (39, 174, 96), (255, 255, 255))

        else:
            # ===== 游戏中 / 通关 / 失败 界面 =====
            # 1) 棋盘
            draw_board(window, board_x, board_y)
            # 在棋盘上方绘制所有正在飞出的箭头
            for fa in flying_arrows:
                draw_arrow(window, COLOR_ARROW, int(fa["x"]), int(fa["y"]), fa["direction"])

            # 绘制正在播放的被阻挡动画箭头
            if blocked_arrow_animation is not None:
                ba = blocked_arrow_animation
                # 碰撞阶段：被点击箭头产生震动；障碍箭头产生轻微反向震动
                shake_x = 0.0
                shake_y = 0.0
                if ba["phase"] == "collision":
                    # 用 sin 产生平滑的来回震动
                    shake_x = SHAKE_AMP * math.sin(ba["timer"] * 40.0)
                    shake_y = SHAKE_AMP * math.sin(ba["timer"] * 40.0)

                # 始终使用 ba["direction"] 绘制，绝不因 moving_back 而改变方向
                ax = ba["current_x"] + shake_x
                ay = ba["current_y"] + shake_y
                draw_arrow(window, COLOR_ARROW, int(ax), int(ay), ba["direction"])

                # 碰撞阶段让障碍箭头也轻微震动（不修改 BOARD，仅绘制偏移）
                if ba["phase"] == "collision":
                    br, bc = ba["block_row"], ba["block_col"]
                    blocker_dir = BOARD[br][bc]
                    if blocker_dir:
                        bx = board_x + bc * CELL_SIZE + CELL_SIZE // 2
                        by = board_y + br * CELL_SIZE + CELL_SIZE // 2
                        b_shake_x = -SHAKE_AMP * 0.3 * math.sin(ba["timer"] * 40.0)
                        b_shake_y = -SHAKE_AMP * 0.3 * math.sin(ba["timer"] * 40.0)
                        draw_arrow(window, COLOR_ARROW,
                                   int(bx + b_shake_x), int(by + b_shake_y), blocker_dir)

            # 2) 顶部状态栏：当前关卡 + 剩余箭头
            level_text = font_mid.render(f"当前关卡：第 {current_level + 1} 关", True, (255, 255, 255))
            window.blit(level_text, (20, 20))

            arrow_text = font_mid.render(f"剩余箭头：{count_arrows()}", True, (255, 255, 255))
            arrow_rect = arrow_text.get_rect(topright=(WINDOW_WIDTH - 20, 20))
            window.blit(arrow_text, arrow_rect)

            # 剩余失误次数
            mistake_text = font_mid.render(f"剩余失误：{mistakes_left}", True, (255, 255, 255))
            mistake_rect = mistake_text.get_rect(topright=(WINDOW_WIDTH - 20, 50))
            window.blit(mistake_text, mistake_rect)

            # 随时可用的“重新开始”按钮（左上角，关卡文字下方）
            draw_button(window, restart_button_rect, "重新开始", font_mid,
                        (192, 57, 43), (255, 255, 255))

            # 3) 通关 / 全部通关的覆盖层与按钮
            if game_state == "level_complete":
                # 半透明遮罩
                overlay = pygame.Surface((GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 160))
                window.blit(overlay, (board_x, board_y))

                msg = f"第 {current_level + 1} 关通关！"
                msg_surf = font_big.render(msg, True, (255, 215, 0))
                msg_rect = msg_surf.get_rect(center=(WINDOW_WIDTH // 2, board_y - 30))
                window.blit(msg_surf, msg_rect)

                draw_button(window, action_button_rect, "下一关", font_btn,
                            (39, 174, 96), (255, 255, 255))

            elif game_state == "game_complete":
                overlay = pygame.Surface((GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 160))
                window.blit(overlay, (board_x, board_y))

                msg = "恭喜！全部关卡通关！"
                msg_surf = font_big.render(msg, True, (255, 215, 0))
                msg_rect = msg_surf.get_rect(center=(WINDOW_WIDTH // 2, board_y - 30))
                window.blit(msg_surf, msg_rect)

                draw_button(window, action_button_rect, "重新开始", font_btn,
                            (41, 128, 185), (255, 255, 255))

            elif game_state == "game_over":
                # 失败界面：半透明遮罩 + 提示文字 + 重新开始按钮
                overlay = pygame.Surface((GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 160))
                window.blit(overlay, (board_x, board_y))

                msg = "游戏失败"
                msg_surf = font_big.render(msg, True, (231, 76, 60))
                msg_rect = msg_surf.get_rect(center=(WINDOW_WIDTH // 2, board_y - 30))
                window.blit(msg_surf, msg_rect)

                draw_button(window, action_button_rect, "重新开始", font_btn,
                            (192, 57, 43), (255, 255, 255))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
