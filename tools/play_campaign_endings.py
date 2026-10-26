"""Play Classic Defence from the title screen through a loss and a win.

Uses the same key and fire inputs as a player. It does not call the ending
methods directly and it does not enable the headless smoke-test autostart.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from pathlib import Path


def configure_environment() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.pop("SWARMBREAKER_HEADLESS_SMOKE_TEST", None)
    os.environ.pop("BUGBLASTER_HEADLESS_SMOKE_TEST", None)
    staging_root = Path(tempfile.mkdtemp(prefix="swarmbreaker-campaign-"))
    os.environ["LOCALAPPDATA"] = str(staging_root)
    os.environ["XDG_DATA_HOME"] = str(staging_root)


configure_environment()

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pygame

import main


EVIDENCE_DIR = Path(tempfile.gettempdir()) / "swarmbreaker-campaign-evidence"
FRAME_LIMIT = 500_000


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def tap(game: main.Game, key: int) -> None:
    game.handle_keydown(key)
    game.handle_keyup(key)


def save_frame(game: main.Game, filename: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    game.render()
    path = EVIDENCE_DIR / filename
    pygame.image.save(game.screen, path)
    return path


def fresh_game(seed: int) -> main.Game:
    random.seed(seed)
    game = main.Game()
    game.sound_enabled = False
    game.profile = game.default_profile()
    game.high_score = 0
    game.save_profile()
    game.save_high_score()
    expect(game.game_phase == "title", f"A new game should open on the title screen, got {game.game_phase}")
    expect(game.current_mode_id == "classic", "A new profile should offer Classic Defence")
    expect(not game.mode_is_unlocked("toxic_gauntlet"), "Toxic Gauntlet should start locked")
    expect(not game.mode_is_unlocked("boss_rush"), "Boss Rush should start locked")
    return game


def start_quick(game: main.Game) -> None:
    expect(game.title_menu_index == 0, "Quick Start should be the first title item")
    tap(game, pygame.K_RETURN)
    expect(game.game_phase == "wave_intro", f"Quick Start should deploy a wave, got {game.game_phase}")


def start_briefed_classic(game: main.Game) -> None:
    tap(game, pygame.K_DOWN)
    tap(game, pygame.K_RETURN)
    expect(game.game_phase == "mode_select", f"Select Mode should open the rules list, got {game.game_phase}")
    expect(game.mode_ids[game.mode_select_index] == "classic", "Classic Defence should be the selected ruleset")
    tap(game, pygame.K_RETURN)
    expect(game.game_phase == "briefing", f"Classic Defence should brief before the first wave, got {game.game_phase}")
    tap(game, pygame.K_RETURN)
    expect(game.game_phase == "wave_intro", f"The briefing should deploy wave 1, got {game.game_phase}")


def release_controls(game: main.Game) -> None:
    game.move_left = False
    game.move_right = False
    game.move_up = False
    game.move_down = False
    game.fire_held = False


def centipede_heads(game: main.Game) -> list:
    heads = []
    for chain in game.centipedes:
        if chain and chain[0].alive():
            heads.append(chain[0])
    return heads


def lowest_blocker(game: main.Game, aim_x: float, player: main.Player):
    blocker = None
    for mushroom in game.mushrooms:
        if not mushroom.alive():
            continue
        if mushroom.rect.bottom > player.rect.top + 2:
            continue
        if abs(mushroom.rect.centerx - aim_x) > max(14, mushroom.rect.width * 0.55):
            continue
        if blocker is None or mushroom.rect.bottom > blocker.rect.bottom:
            blocker = mushroom
    return blocker


def hazard_near_player(game: main.Game, player: main.Player):
    zone = player.rect.inflate(32, 20)
    nearest = None
    nearest_distance = 10**9
    for group in (
        game.centipede_segments,
        game.spiders,
        game.fleas,
        game.scorpions,
        game.enemy_projectiles,
        game.bosses,
    ):
        for sprite in group:
            if not sprite.alive() or not sprite.rect.colliderect(zone):
                continue
            distance = abs(sprite.rect.centerx - player.rect.centerx) + abs(sprite.rect.centery - player.rect.centery)
            if distance < nearest_distance:
                nearest = sprite
                nearest_distance = distance
    return nearest


def predict_actor(sprite, frames: int) -> pygame.Rect:
    rect = sprite.rect.copy()
    if frames <= 0:
        return rect
    if isinstance(sprite, main.Spider):
        velocity_y = sprite.speed_y
        for _ in range(frames):
            rect.x = int(rect.x + sprite.speed_x)
            rect.y = int(rect.y + velocity_y)
            if rect.top < sprite.top_boundary or rect.bottom > sprite.bottom_boundary:
                velocity_y *= -1
        return rect
    if isinstance(sprite, main.Flea):
        for _ in range(frames):
            rect.y = int(rect.y + sprite.speed_y)
        return rect
    if isinstance(sprite, main.EnemyBolt):
        for _ in range(frames):
            rect.x = int(rect.x + sprite.velocity_x)
            rect.y = int(rect.y + sprite.velocity_y)
        return rect
    return rect


def project_player(player: main.Player, move_x: int, move_y: int, frames: int) -> pygame.Rect:
    rect = player.rect.copy()
    step_x = int(round(move_x * player.speed))
    step_y = int(round(move_y * player.speed))
    for _ in range(frames):
        rect.x += step_x
        rect.y += step_y
        rect.left = main.clamp(rect.left, 0, main.SCREEN_WIDTH - rect.width)
        rect.bottom = main.clamp(rect.bottom, main.PLAYER_MIN_BOTTOM, main.PLAYER_START_BOTTOM)
    return rect


class LanePilot:
    """Fire and dodge with the same held keys a player uses."""

    def __init__(self):
        self.boss_lane_segments = 0
        self.boss_lane_mushrooms = 0

    def shot_column(self, player: main.Player, aim_x: float) -> pygame.Rect:
        column = pygame.Rect(0, 0, 6, max(1, player.rect.top))
        column.midbottom = (int(aim_x), player.rect.top)
        return column

    def lane_block(self, game: main.Game, player: main.Player, aim_x: float) -> tuple[int, int]:
        column = self.shot_column(player, aim_x)
        segments = 0
        mushrooms = 0
        for mushroom in game.mushrooms:
            if mushroom.alive() and mushroom.rect.colliderect(column):
                mushrooms += mushroom.health
        for segment in game.centipede_segments:
            if segment.alive() and segment.rect.colliderect(column):
                segments += 1
        return segments, mushrooms

    def predict_boss_center(self, boss, frames: int) -> float:
        x = boss.rect.x
        speed = boss.speed_x
        width = boss.rect.width
        for _ in range(max(0, frames)):
            x += int(round(speed))
            if x < 40 or x + width > main.SCREEN_WIDTH - 40:
                speed *= -1
        return x + width / 2

    def aim_x(self, game: main.Game, player: main.Player) -> float:
        center = main.SCREEN_WIDTH / 2
        best_x = center

        if game.bosses:
            boss = game.bosses.sprites()[0]
            travel = max(1, int(round((player.rect.top - boss.rect.bottom) / 11)))
            future_center = self.predict_boss_center(boss, travel)
            half = boss.rect.width / 2
            left = max(120, future_center - half + 10)
            right = min(main.SCREEN_WIDTH - 120, future_center + half - 10)
            best_x = future_center
            best_cost = None
            self.boss_lane_segments = 99
            self.boss_lane_mushrooms = 99
            if right >= left:
                sample = left
                while sample <= right:
                    segments, mushrooms = self.lane_block(game, player, sample)
                    rank = (segments, mushrooms, abs(sample - future_center))
                    if best_cost is None or rank < best_cost:
                        best_cost = rank
                        best_x = sample
                        self.boss_lane_segments = segments
                        self.boss_lane_mushrooms = mushrooms
                    sample += 8
        else:
            best_distance = 10**6
            for group in (game.spiders, game.fleas, game.centipede_segments):
                for sprite in group:
                    if not sprite.alive() or sprite.rect.bottom > player.rect.top + 6:
                        continue
                    distance = abs(sprite.rect.centerx - player.rect.centerx)
                    if distance < best_distance and distance < 240:
                        best_distance = distance
                        best_x = sprite.rect.centerx

        if not game.bosses:
            for spider in game.spiders:
                if not spider.alive() or spider.rect.bottom > player.rect.top + 6:
                    continue
                if abs(spider.rect.centerx - player.rect.centerx) < 70:
                    best_x = spider.rect.centerx
                    break

        if not (game.bosses and self.boss_lane_segments == 0 and self.boss_lane_mushrooms == 0):
            blocker = lowest_blocker(game, best_x, player)
            if blocker is not None:
                best_x = blocker.rect.centerx
        return main.clamp(best_x, 120, main.SCREEN_WIDTH - 120)

    def moving_threats(self, game: main.Game) -> list:
        threats = []
        for group in (game.spiders, game.fleas, game.enemy_projectiles):
            for sprite in group:
                if sprite.alive():
                    threats.append(sprite)
        return threats

    def choose_move(self, game: main.Game, player: main.Player, aim_x: float) -> tuple[int, int]:
        threats = self.moving_threats(game)
        segments = [segment.rect.copy() for segment in game.centipede_segments if segment.alive()]
        horizon = 22
        predicted = []
        if threats:
            for frame in range(1, horizon + 1):
                predicted.append([predict_actor(sprite, frame).inflate(8, 6) for sprite in threats])

        best = (0, 1)
        best_score = -10**12
        for move_x, move_y in ((0, 1), (-1, 1), (1, 1), (0, 0), (-1, 0), (1, 0)):
            score = 30 if move_y > 0 else 0
            survived = True
            for frame in range(1, horizon + 1):
                rect = project_player(player, move_x, move_y, frame)
                if any(rect.colliderect(segment) for segment in segments):
                    score -= 8000 * (horizon + 1 - frame)
                    survived = False
                    break
                if predicted and any(rect.colliderect(box) for box in predicted[frame - 1]):
                    score -= 8000 * (horizon + 1 - frame)
                    survived = False
                    break
            soon = project_player(player, move_x, move_y, 1)
            score -= abs(soon.centerx - aim_x) * 4
            score -= abs(soon.bottom - main.PLAYER_START_BOTTOM) * 2
            if soon.centerx < 180:
                score -= (180 - soon.centerx) * 25
            elif soon.centerx > main.SCREEN_WIDTH - 180:
                score -= (soon.centerx - (main.SCREEN_WIDTH - 180)) * 25
            if survived and abs(soon.centerx - aim_x) <= 6:
                score += 35
            if score > best_score:
                best_score = score
                best = (move_x, move_y)
        return best

    def steer(self, game: main.Game) -> None:
        release_controls(game)
        if game.game_phase == "wave_intro":
            if game.wave_intro_timer > 0:
                game.handle_keydown(pygame.K_RETURN)
            return
        if game.game_phase != "playing":
            return

        player = game.player
        aim_x = self.aim_x(game, player)
        move_x, move_y = self.choose_move(game, player, aim_x)
        if move_x < 0:
            game.move_left = True
        elif move_x > 0:
            game.move_right = True
        if move_y < 0:
            game.move_up = True
        elif move_y > 0:
            game.move_down = True

        column = pygame.Rect(player.rect.centerx - 8, 0, 16, max(1, player.rect.top))
        lowest_kind = None
        lowest_bottom = -1
        for kind, group in (
            ("mushroom", game.mushrooms),
            ("segment", game.centipede_segments),
            ("spider", game.spiders),
            ("flea", game.fleas),
            ("boss", game.bosses),
        ):
            for sprite in group:
                if not sprite.alive() or sprite.rect.bottom > player.rect.top + 4:
                    continue
                if not sprite.rect.colliderect(column):
                    continue
                if sprite.rect.bottom >= lowest_bottom:
                    lowest_bottom = sprite.rect.bottom
                    lowest_kind = kind
        boss_aligned = False
        if game.bosses:
            boss = game.bosses.sprites()[0]
            boss_aligned = boss.rect.left + 4 <= player.rect.centerx <= boss.rect.right - 4
        open_lane = game.bosses and self.boss_lane_segments == 0 and self.boss_lane_mushrooms == 0
        if open_lane:
            standing_segments, standing_mushrooms = self.lane_block(game, player, player.rect.centerx)
            if standing_segments == 0 and standing_mushrooms == 0 and abs(player.rect.centerx - aim_x) <= 8:
                game.fire_held = True
            return
        if lowest_kind == "segment" and game.bosses and self.boss_lane_segments == 0:
            return
        if lowest_kind is not None or boss_aligned:
            game.fire_held = True


def play_until_end(game: main.Game, pilot: LanePilot | None, frame_limit: int = FRAME_LIMIT) -> int:
    frames = 0
    last_progress = None
    last_clear_progress = None
    last_clear_frame = 0
    while game.game_phase not in ("game_over", "victory") and frames < frame_limit:
        if pilot is not None:
            pilot.steer(game)
        else:
            release_controls(game)
        hit_by = []
        if game.game_phase == "playing":
            for name, group in (
                ("segment", game.centipede_segments),
                ("spider", game.spiders),
                ("flea", game.fleas),
                ("scorpion", game.scorpions),
                ("bolt", game.enemy_projectiles),
                ("boss", game.bosses),
            ):
                if pygame.sprite.spritecollideany(game.player, group):
                    hit_by.append(name)
        game.update()
        frames += 1
        boss_health = game.bosses.sprites()[0].health if game.bosses else None
        boss_bucket = None if boss_health is None else boss_health // 4
        progress = (game.game_phase, game.level, game.lives, game.stats["bosses_destroyed"], game.stats["waves_cleared"], boss_bucket)
        clear_progress = (game.level, game.stats["segments_destroyed"], game.stats["bosses_destroyed"], boss_health)
        if progress != last_progress:
            print(
                f"frame {frames} phase {game.game_phase} level {game.level} "
                f"lives {game.lives} score {game.score} segments {game.stats['segments_destroyed']} "
                f"bosses {game.stats['bosses_destroyed']} waves {game.stats['waves_cleared']}"
                + (f" boss_hp {boss_health}" if boss_health is not None else "")
                + (f" hit_by {hit_by}" if hit_by else ""),
                flush=True,
            )
            last_progress = progress
        if frames % 2500 == 0:
            boss_left = int(game.bosses.sprites()[0].rect.left) if game.bosses else None
            print(
                f"tick {frames} level {game.level} lives {game.lives} "
                f"boss_hp {boss_health} boss_left {boss_left} player_x {int(game.player.rect.centerx)} "
                f"segments {len(game.centipede_segments)} bolts {len(game.enemy_projectiles)}",
                flush=True,
            )
        if clear_progress != last_clear_progress:
            last_clear_progress = clear_progress
            last_clear_frame = frames
        elif pilot is not None and frames - last_clear_frame > 40_000:
            boss_health = game.bosses.sprites()[0].health if game.bosses else None
            head_rows = [(head.rect.centerx, head.rect.centery) for head in centipede_heads(game)[:4]]
            raise AssertionError(
                f"No wave progress for 40000 frames at level {game.level}, "
                f"segments left {len(game.centipede_segments)}, boss {boss_health}, heads {head_rows}"
            )
    return frames


def assert_contract() -> None:
    expect(main.campaign_finale_wave(main.GAME_MODES["classic"]) == 12, "Classic finale should be wave 12")
    expect(main.campaign_finale_wave(main.GAME_MODES["time_attack"]) == 9, "Time Attack finale should be wave 9")
    expect(main.campaign_finale_wave(main.GAME_MODES["toxic_gauntlet"]) == 12, "Toxic finale should be wave 12")
    expect(main.campaign_finale_wave(main.GAME_MODES["boss_rush"]) == 3, "Boss Rush finale should be wave 3")
    expect("endless" not in main.GAME_MODES["classic"]["description"].lower(), "Classic should not be described as endless")
    for mode in main.GAME_MODES.values():
        expect("Matriarch Prime" in mode["description"], f"{mode['label']} should name the winning queen")


class IntoTheSwarm:
    """Walk into the centipede. A stationary ship can miss a swarm that never reaches its row."""

    def steer(self, game: main.Game) -> None:
        release_controls(game)
        if game.game_phase != "playing":
            return
        segments = [segment for segment in game.centipede_segments if segment.alive()]
        if not segments:
            game.move_right = True
            return
        target = min(
            segments,
            key=lambda segment: abs(segment.rect.centerx - game.player.rect.centerx)
            + abs(segment.rect.centery - game.player.rect.centery),
        )
        if target.rect.centerx > game.player.rect.centerx + 3:
            game.move_right = True
        elif target.rect.centerx < game.player.rect.centerx - 3:
            game.move_left = True
        if target.rect.centery < game.player.rect.centery - 3:
            game.move_up = True
        elif target.rect.centery > game.player.rect.centery + 3:
            game.move_down = True


def play_loss() -> dict:
    game = fresh_game(11)
    title_shot = save_frame(game, "title-before-quick-start.png")
    start_quick(game)
    started = time.perf_counter()
    frames = play_until_end(game, pilot=IntoTheSwarm(), frame_limit=30_000)
    elapsed = time.perf_counter() - started
    expect(game.game_phase == "game_over", f"Idling should lose the run, got {game.game_phase}")
    expect(game.run_end_reason == "destroyed", f"The loss reason should be destroyed, got {game.run_end_reason}")
    expect(game.stats["waves_cleared"] == 0, "Dying must not count as clearing a wave")
    expect(game.stats["segments_destroyed"] == 0, "An idle loss should not destroy segments")
    expect(game.lives <= 0, "A destroyed run should have no ships left")
    loss_shot = save_frame(game, "classic-loss.png")
    result = {
        "frames": frames,
        "seconds": round(elapsed, 2),
        "score": game.score,
        "level": game.level,
        "title": str(title_shot),
        "ending": str(loss_shot),
    }
    print("loss", result, flush=True)
    return result


def play_win() -> dict:
    game = fresh_game(7)
    save_frame(game, "title-before-briefing.png")
    tap(game, pygame.K_DOWN)
    tap(game, pygame.K_RETURN)
    mode_shot = save_frame(game, "mode-select-classic.png")
    tap(game, pygame.K_RETURN)
    briefing_shot = save_frame(game, "classic-briefing.png")
    expect(game.game_phase == "briefing", "Mode select should reach the briefing")
    tap(game, pygame.K_RETURN)
    expect(game.game_phase == "wave_intro", f"The briefing should deploy wave 1, got {game.game_phase}")
    started = time.perf_counter()
    frames = play_until_end(game, LanePilot())
    elapsed = time.perf_counter() - started
    expect(game.game_phase == "victory", f"Classic Defence should end in victory, got {game.game_phase} reason {game.run_end_reason} level {game.level}")
    expect(game.run_end_reason == "victory", game.run_end_reason)
    expect(game.level == 12, f"The win should be Matriarch Prime on wave 12, got wave {game.level}")
    expect(game.stats["waves_cleared"] == 12, f"All 12 waves should be cleared, got {game.stats['waves_cleared']}")
    expect(game.stats["bosses_destroyed"] >= 3, f"Prime is the third queen, got {game.stats['bosses_destroyed']}")
    expect(game.mode_is_unlocked("toxic_gauntlet"), "Winning the campaign should unlock Toxic Gauntlet")
    expect(game.mode_is_unlocked("boss_rush"), "Winning the campaign should unlock Boss Rush")
    unlock_notes = " ".join(game.run_unlocks)
    expect("Toxic Gauntlet unlocked." in unlock_notes, f"Victory should announce Toxic Gauntlet, got {game.run_unlocks}")
    expect("Boss Rush unlocked." in unlock_notes, f"Victory should announce Boss Rush, got {game.run_unlocks}")
    victory_shot = save_frame(game, "classic-victory.png")
    result = {
        "frames": frames,
        "seconds": round(elapsed, 2),
        "score": game.score,
        "bosses": game.stats["bosses_destroyed"],
        "modeSelect": str(mode_shot),
        "briefing": str(briefing_shot),
        "ending": str(victory_shot),
    }
    print("win", result, flush=True)
    return result


def install_hit_log() -> None:
    original = main.Game.handle_player_hit

    def wrapped(self):
        kinds = []
        for name, group in (
            ("segment", self.centipede_segments),
            ("spider", self.spiders),
            ("flea", self.fleas),
            ("scorpion", self.scorpions),
            ("bolt", self.enemy_projectiles),
            ("boss", self.bosses),
        ):
            if pygame.sprite.spritecollideany(self.player, group):
                kinds.append(name)
        print(f"player hit at {self.player.rect.center} by {kinds} level {self.level}", flush=True)
        original(self)

    main.Game.handle_player_hit = wrapped


def main_cli() -> None:
    install_hit_log()
    assert_contract()
    loss = play_loss()
    win = play_win()
    print("campaign-endings", {"loss": loss, "win": win}, flush=True)


if __name__ == "__main__":
    main_cli()
