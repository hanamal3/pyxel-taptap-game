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
from typing import Any, Callable, Dict, List, Optional

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

        def text(self, *args: Any, **kwargs: Any) -> None:
            pass

    pyxel: Any = _PyxelStub()

# 画面サイズとゲーム定数
WIDTH = 160
HEIGHT = 120
TARGET_MIN_R = 10
TARGET_MAX_R = 22
SPAWN_PADDING = 10

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

        # サウンド定義（環境差を考えて複数パターンで試行）
        # Pyxel のバージョン差による引数違いに対応するため try/except を使います。
        try:
            # よく使われる簡易パターン（音程データ, wave, env, volume, speed など）
            pyxel.sound(0).set(
                "c5",  # ノート（短いクリック音）
                "s",   # 波形: s(quare) 相当（環境により解釈される）
                "n",   # エンベロープ等（省略可）
                10,    # 音量的な数値（省略可）
                5      # 速さ（省略可）
            )
            # 追加の短い効果音を定義（果物ごとに使い分ける）
            try:
                pyxel.sound(1).set("e5", "s", "n", 8, 6)
                pyxel.sound(2).set("g4", "t", "n", 9, 5)
            except Exception:
                # 無視して継続
                pass
        except TypeError:
            try:
                # 引数が少ないバージョン向け
                pyxel.sound(0).set("c5")
            except Exception:
                # 最悪定義できなくても実行は続ける（無音になるだけ）
                pass

        # 短い効果音を再生するヘルパー
        # fruit_sound_map: tid -> sound index
        self.fruit_sound_map = {
            'apple': 0,
            'banana': 1,
            'orange': 2,
            'grape': 1,
            'melon': 2,
        }
        self.play_sound: Callable[[Optional[str]], None] = self._play_click_sound

        # 初期ゲーム状態
        self.score = 0
        self.combo = 0
        self.combo_timer = 0  # 連続タップ時間管理（連打ボーナス用）
        self.target_x = WIDTH // 2
        self.target_y = HEIGHT // 2
        self.target_r = 18
        self.target_timer = 0  # ターゲット自動移動タイマー
        self.particles: List[Particle] = []  # Particle のリスト
        # 果物タイプ（シンプルな色味で表現）
        from typing import Tuple
        self.fruit_types: List[Tuple[str, str, int, int]] = [
            ("りんご", "apple", 10, 11),   # (表示名, id, body_color, leaf_color)
            ("バナナ", "banana", 8, 7),
            ("オレンジ", "orange", 9, 7),
            ("ぶどう", "grape", 5, 7),
            ("メロン", "melon", 3, 7),
        ]
        self.target_type: Optional[Tuple[str, str, int, int]] = None
        # ピクセルアート用のパターン定義（小さなマップで描画）
        # '.' は透過、'B' は本体、 'L' は葉/ハイライト
        self.pixel_patterns = {
            "apple": [
                "..LL....",
                ".LLLL...",
                ".BBBBB..",
                ".BBBBB..",
                ".BBBBB..",
                "..BBB...",
                "...B....",
                "........",
            ],
            "banana": [
                "........",
                "..BBBBB.",
                ".BBBBBB.",
                ".BBBBB..",
                "..BBBB..",
                "...BB...",
                "........",
                "........",
            ],
            "orange": [
                "........",
                "..OOOO..",
                ".OOOOOO.",
                ".OOOOOO.",
                ".OOOOOO.",
                "..OOOO..",
                "...OO...",
                "........",
            ],
            "grape": [
                "........",
                "..GGG...",
                ".GGGGG..",
                ".GGGGG..",
                "..GGG...",
                "..GG....",
                "........",
                "........",
            ],
            "melon": [
                "........",
                ".MMMMM..",
                ".MMMMM..",
                ".MMMMM..",
                "..MMM...",
                "..MM....",
                "........",
                "........",
            ],
        }

        # 難易度やボーナス系
        self.spawn_interval = 60  # 毎何フレームで自動でターゲットを再配置するか
        self.max_combo_time = 30  # コンボを維持するためのフレーム数

        # 初回ターゲット設置
        self._respawn_target()
        # タップで一時停止するフレーム数（数秒間止まる）
        self.pause_frames = 120  # 120フレーム = 約2秒（60fps想定）
        self.paused_timer = 0

        pyxel.run(self.update, self.draw)

    # --------------------
    # サウンド再生（短いクリック音）
    # --------------------
    def _play_click_sound(self, tid: Optional[str] = None) -> None:
        """効果音を鳴らす。`tid` が与えられれば果物ごとの音を使う。"""
        try:
            if tid is None:
                pyxel.play(0, 0, loop=False)
            else:
                idx = self.fruit_sound_map.get(tid, 0)
                pyxel.play(0, idx, loop=False)
        except Exception:
            pass

    # --------------------
    # タップ判定（座標がターゲット内か）
    # --------------------
    def _is_hit(self, x: int, y: int) -> bool:
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

            # タップでターゲットを数秒間止める（シンプル挙動）
            self.paused_timer = self.pause_frames
            # ターゲットはそのまま表示し、pause が終わったら再出現させる
            # パーティクルをたくさん発生させる（楽しさアップ）
            self._spawn_particles(self.target_x, self.target_y, count=12 + min(18, self.combo))

            # 効果音を鳴らす（果物ごとに異なる音）
            if self.target_type is not None:
                _, tid, _, _ = self.target_type
            else:
                tid = None
            self.play_sound(tid)

            # （移動はしない）
            pass

        else:
            # ミスクリック：小さなパーティクルでフィードバック
            self._spawn_particles(x, y, count=6, weak=True)
            # コンボリセット（タップミスはコンボ切れ）
            self.combo = 0
            self.combo_timer = 0

    # --------------------
    # ターゲット再配置
    # --------------------
    def _respawn_target(self, quick: bool = False) -> None:
        # 画面のパディング内にランダム配置
        self.target_r = random.randint(TARGET_MIN_R, TARGET_MAX_R)
        self.target_x = random.randint(SPAWN_PADDING + self.target_r, WIDTH - SPAWN_PADDING - self.target_r)
        self.target_y = random.randint(SPAWN_PADDING + self.target_r, HEIGHT - SPAWN_PADDING - self.target_r)
        # 新しい果物タイプを選ぶ
        self.target_type = random.choice(self.fruit_types)
        # 早めに次の自動移動する場合は短いタイマー
        self.target_timer = 10 if quick else random.randint(self.spawn_interval // 2, self.spawn_interval * 2)

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
            # 停止中はタイマーを減らす
            self.paused_timer -= 1
            if self.paused_timer <= 0:
                # pause 終了後にターゲットを再配置
                self._respawn_target()
        else:
            if self.target_timer > 0:
                self.target_timer -= 1
                if self.target_timer <= 0:
                    self._respawn_target()

        # ターゲットが小さくなっている時は徐々に戻す（弾む演出）
        if self.target_r < TARGET_MAX_R:
            self.target_r = min(TARGET_MAX_R, self.target_r + 0.2)

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

        # 果物を描く（ピクセルアートパターンを使う）
        if self.target_type is None:
            self.target_type = random.choice(self.fruit_types)

        name, tid, body_col, leaf_col = self.target_type

        # ピクセルアート描画ヘルパー
        def draw_pixel_art(cx: int, cy: int, pattern: List[str], scale: int, color_map: Dict[str, int]) -> None:
            h = len(pattern)
            w = len(pattern[0]) if h > 0 else 0
            offset_x = cx - (w * scale) // 2
            offset_y = cy - (h * scale) // 2
            for ry, row in enumerate(pattern):
                for rx, ch in enumerate(row):
                    if ch == '.' or ch == ' ':
                        continue
                    col = color_map.get(ch, None)
                    if col is None:
                        continue
                    x = offset_x + rx * scale
                    y = offset_y + ry * scale
                    # ピクセルは小さな矩形でスケーリングして描く
                    pyxel.rect(x, y, scale, scale, col)

        # スケールはターゲット半径に応じて決める
        scale = max(1, int(self.target_r / 4))
        pattern = self.pixel_patterns.get(tid, self.pixel_patterns['apple'])
        color_map = {'B': body_col, 'L': leaf_col, 'O': body_col}
        draw_pixel_art(self.target_x, self.target_y, pattern, scale, color_map)

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
