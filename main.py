# File: main.py
# 実行方法:
#   pip install pyxel>=2.9.6
#   python main.py
#
# シンプルな「タップタップ」ゲーム（単一ファイル・Pyxel）
# - 画面をタップ（マウスクリック／タッチ）してターゲットを連打します。
# - 連打するとスコアが上がり、簡易パーティクルと効果音が鳴ります。
# - 外部ファイル不要。サウンドは pyxel.sound[N].set(...) でコード内定義しています。
#
# 子供向けの安全な内容のみ（外部通信・広告・課金無し）。
#
# 主要部分に日本語コメントあり（初心者向け説明）。

import math
import random
from typing import Any, List, Optional

# Pyxel がインストールされていない（または型情報が解決できない）場合の簡易スタブ
try:
    import pyxel  # type: ignore
except Exception:  # pragma: no cover - 開発環境の型チェック回避用スタブ
    class _PyxelStub:
        MOUSE_BUTTON_LEFT = 0
        KEY_SPACE = 32

        def init(self, *args: Any, **kwargs: Any) -> None:
            pass

        def mouse(self, *args: Any, **kwargs: Any) -> None:
            pass

        def sound(self, idx: int) -> Any:
            class _Snd:
                def set(self, *a: Any, **k: Any) -> None:
                    pass

            return _Snd()

        def play(self, *args: Any, **kwargs: Any) -> None:
            pass

        def run(self, update: Any, draw: Any) -> None:
            # スタブでは即座に終了
            return

        def cls(self, *args: Any, **kwargs: Any) -> None:
            pass

        def rect(self, *args: Any, **kwargs: Any) -> None:
            pass

        def rectb(self, *args: Any, **kwargs: Any) -> None:
            pass

        def circ(self, *args: Any, **kwargs: Any) -> None:
            pass

        def pset(self, *args: Any, **kwargs: Any) -> None:
            pass

        def load(self, *args: Any, **kwargs: Any) -> None:
            pass

        def blt(self, *args: Any, **kwargs: Any) -> None:
            pass

        def text(self, *args: Any, **kwargs: Any) -> None:
            pass

    pyxel: Any = _PyxelStub()

# 画面サイズとゲーム定数
WIDTH = 160
HEIGHT = 120
TARGET_R = 18  # ターゲットの大きさ（固定）
SPAWN_PADDING = 10

# りんご・バナナの実写ピクセルアート（fruits.pyxres, イメージバンク0）の座標
# (u, v, w, h): スプライトシート上の位置とサイズ
SPRITE_RECTS = {
    "apple": (0, 0, 14, 13),
    "banana": (16, 0, 12, 13),
}

# パーティクル数上限
MAX_PARTICLES = 120

class Particle:
    """パーティクル（エフェクト）を表す簡易クラス"""
    def __init__(self, x: float, y: float, vx: float, vy: float, life: int, col: int, size: float) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.col = col
        self.size = size

    def update(self) -> None:
        # 重力と減衰で自然な動きにする
        self.vy += 0.15
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        self.size *= 0.96

    def draw(self) -> None:
        if self.size > 0.6:
            pyxel.circ(int(self.x), int(self.y), max(1, int(self.size)), self.col)
        else:
            pyxel.pset(int(self.x), int(self.y), self.col)


class TapTapGame:
    """メインゲームクラス"""
    def __init__(self):
        pyxel.init(WIDTH, HEIGHT, title="TapTap - タップタップ", fps=60)
        pyxel.mouse(True)  # マウス座標を有効化（タッチの座標も扱える）

        # りんご・バナナのピクセルアートと、タップ音楽（イメージ／サウンドバンク0）を読み込む
        pyxel.load("fruits.pyxres")

        # 初期ゲーム状態
        self.score = 0
        self.combo = 0
        self.combo_timer = 0  # 連続タップ時間管理（連打ボーナス用）
        self.target_x = WIDTH // 2
        self.target_y = HEIGHT // 2
        self.target_r = TARGET_R
        self.target_visible = True  # タップされると消え、再配置されると再び表示される
        self.target_timer = 0  # ターゲット自動移動タイマー
        self.particles: List[Particle] = []  # Particle のリスト
        # 果物タイプ（シンプルな色味で表現）
        from typing import Tuple
        self.fruit_types: List[Tuple[str, str, int, int]] = [
            ("りんご", "apple", 10, 11),   # (表示名, id, body_color, leaf_color)
            ("バナナ", "banana", 8, 7),
        ]
        self.target_type: Optional[Tuple[str, str, int, int]] = None

        # 難易度やボーナス系
        self.stay_frames = 180  # 1つの果物が一箇所に留まる時間（約3秒、60fps想定）
        self.max_combo_time = 30  # コンボを維持するためのフレーム数

        # 初回ターゲット設置
        self._respawn_target()
        self.paused_timer = 0  # タップ後、次が出るまでのカウントダウン

        pyxel.run(self.update, self.draw)

    # --------------------
    # サウンド再生（短いクリック音）
    # --------------------
    def _play_tap_music(self) -> None:
        """タップされた瞬間に鳴らす短い音楽。"""
        pyxel.play(0, 0, loop=False)

    # --------------------
    # タップ判定（座標がターゲット内か）
    # --------------------
    def _is_hit(self, x: int, y: int) -> bool:
        if not self.target_visible:
            return False
        dx = x - self.target_x
        dy = y - self.target_y
        return dx * dx + dy * dy <= self.target_r * self.target_r

    # --------------------
    # タップ時の処理：スコア加算、コンボ、エフェクト、音
    # --------------------
    def _on_tap(self, x: int, y: int) -> None:
        # ターゲットに命中したらスコア
        if self._is_hit(x, y):
            # コンボ処理：短時間に連続でタップするとコンボ数が増える
            if self.combo_timer > 0:
                self.combo += 1
            else:
                self.combo = 1
            self.combo_timer = self.max_combo_time

            # スコアはコンボ倍率で増える（単純な加算）
            gained = 1 + (self.combo - 1) // 3  # 3回で+1ボーナス等
            self.score += gained

            # タップしたターゲットは消え、少し経つと別の場所へ再出現する
            self.target_visible = False
            self.paused_timer = self.stay_frames
            # パーティクルをたくさん発生させる（楽しさアップ）
            self._spawn_particles(self.target_x, self.target_y, count=12 + min(18, self.combo))

            # タップされた瞬間に音楽を鳴らす
            self._play_tap_music()

        else:
            # ミスクリック：小さなパーティクルでフィードバック
            self._spawn_particles(x, y, count=6, weak=True)
            # コンボリセット（タップミスはコンボ切れ）
            self.combo = 0
            self.combo_timer = 0

    # --------------------
    # ターゲット再配置
    # --------------------
    def _respawn_target(self) -> None:
        # 画面のパディング内にランダム配置（大きさは固定）
        self.target_x = random.randint(SPAWN_PADDING + self.target_r, WIDTH - SPAWN_PADDING - self.target_r)
        self.target_y = random.randint(SPAWN_PADDING + self.target_r, HEIGHT - SPAWN_PADDING - self.target_r)
        # 新しい果物タイプを選ぶ
        self.target_type = random.choice(self.fruit_types)
        self.target_visible = True
        # タップしなければこの秒数だけ同じ場所に留まる
        self.target_timer = self.stay_frames

    # --------------------
    # パーティクル発生
    # --------------------
    def _spawn_particles(self, x: float, y: float, count: int = 10, weak: bool = False) -> None:
        for _ in range(count):
            if len(self.particles) >= MAX_PARTICLES:
                break
            angle = random.random() * math.pi * 2
            speed = random.uniform(0.8, 3.6) * (0.6 if weak else 1.0)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed - random.uniform(0.0, 1.8)
            life = random.randint(10, 24) if weak else random.randint(18, 36)
            # 色は現在のターゲット果物に合わせてシンプルにする
            if self.target_type is not None:
                _, _, body_col, leaf_col = self.target_type
                col = random.choice([body_col, leaf_col, 7])
            else:
                col = random.choice([7, 6])
            size = random.uniform(1.6, 3.8) if not weak else random.uniform(1.0, 2.4)
            self.particles.append(Particle(x, y, vx, vy, life, col, size))

    # --------------------
    # 毎フレームの更新処理
    # --------------------
    def update(self):
        # 画面クリック／タップ検出：
        # pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT) を使い、座標は pyxel.mouse_x / mouse_y で取得
        # またキーボードのスペースでのタップも許可（テスト用）
        tapped = False
        tx = ty = 0
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            tapped = True
            tx, ty = pyxel.mouse_x, pyxel.mouse_y
        elif pyxel.btnp(pyxel.KEY_SPACE):
            # スペースの場合は画面中央をタップしたことにする（キーボードテスト用）
            tapped = True
            tx, ty = WIDTH // 2, HEIGHT // 2

        if tapped:
            # タップを処理
            self._on_tap(tx, ty)

        # ターゲットの自動移動タイマー更新
        if self.paused_timer > 0:
            # タップ後、消えている間はこちらのタイマーを減らす
            self.paused_timer -= 1
            if self.paused_timer <= 0:
                self._respawn_target()
        else:
            # タップされずに stay_frames 経過したら自動で再配置
            if self.target_timer > 0:
                self.target_timer -= 1
                if self.target_timer <= 0:
                    self._respawn_target()

        # コンボタイマー更新
        if self.combo_timer > 0:
            self.combo_timer -= 1
        else:
            self.combo = 0

        # パーティクル更新。life が 0 以下なら削除
        for p in list(self.particles):
            p.update()
            if p.life <= 0:
                try:
                    self.particles.remove(p)
                except ValueError:
                    pass

        # シンプルにランダムでアイテム的な小イベントを入れても楽しい（省略）

    # --------------------
    # 描画処理
    # --------------------
    def draw(self):

        # 背景は落ち着いた単色にする（シンプル）
        pyxel.cls(1)

        # 果物を描く（fruits.pyxres の実写ピクセルアート）
        if self.target_type is None:
            self.target_type = random.choice(self.fruit_types)

        name, tid, _, _ = self.target_type

        # タップされて消えている間は描画しない
        if self.target_visible:
            u, v, sw, sh = SPRITE_RECTS[tid]
            # 大きさは固定（直径 = target_r * 2）
            blt_scale = (self.target_r * 2) / sw
            draw_w = sw * blt_scale
            draw_h = sh * blt_scale
            draw_x = int(self.target_x - draw_w / 2)
            draw_y = int(self.target_y - draw_h / 2)
            pyxel.blt(draw_x, draw_y, 0, u, v, sw, sh, 0, scale=blt_scale)

        # パーティクル描画（色は果物のボディに合わせつつ控えめに）
        for p in self.particles:
            p.draw()

        # スコア・コンボ表示（日本語）
        pyxel.text(6, 6, f"スコア: {self.score}", 7)
        if self.combo >= 2:
            pyxel.text(6, 16, f"コンボ x{self.combo}！", 7)

        # ターゲットの名前表示（日本語）
        pyxel.text(WIDTH - 70, 6, f"ターゲット: {name}", 7)

        # ヘルプ表示（短く）
        pyxel.text(6, HEIGHT - 12, "画面をタップして果物をタップ！", 7)

        # 簡素な枠
        pyxel.rectb(2, 2, WIDTH - 4, HEIGHT - 6, 5)


if __name__ == "__main__":
    # ゲーム開始
    TapTapGame()
