"""Matriarch Prime victory edge cases (KOL-7014, PR #3 review P1).

Killing Matriarch Prime must win the run straight away and pay the final-wave rewards,
even when support centipedes or enemy bolts are still in the trench, when the strike
clock is down to its last second, or when the player is on the last ship.

Runs headless: python -m unittest tools.test_prime_victory   (from the repo root)
The kill goes through the game's own collision pass with a real player bullet; the
ending methods are not called directly.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.pop("SWARMBREAKER_HEADLESS_SMOKE_TEST", None)
os.environ.pop("BUGBLASTER_HEADLESS_SMOKE_TEST", None)
_staging = tempfile.mkdtemp(prefix="swarmbreaker-prime-test-")
os.environ["LOCALAPPDATA"] = _staging
os.environ["XDG_DATA_HOME"] = _staging

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import main  # noqa: E402


def prime_wave_game(mode_id: str, seed: int = 7) -> "main.Game":
    random.seed(seed)
    game = main.Game()
    game.sound_enabled = False
    game.start_run(mode_id, skip_briefing=True)
    level = next(lv for lv in range(1, 60) if game.build_wave_profile(lv).get("prime"))
    game.begin_wave(level)
    game.deploy_current_wave()
    assert game.game_phase == "playing", game.game_phase
    assert game.wave_profile["kind"] == "boss" and game.wave_profile["prime"], game.wave_profile
    assert len(game.bosses) == 1
    return game


def arm_kill_shot(game: "main.Game") -> None:
    """Leave Prime on her last hit point and put a player bullet on her."""
    boss = game.bosses.sprites()[0]
    boss.health = 1
    bullet = main.PlayerBullet(boss.rect.centerx, boss.rect.bottom - 4)
    game.player_bullets.add(bullet)
    game.all_sprites.add(bullet)


def bolt_on_player(game: "main.Game") -> None:
    """An enemy bolt overlapping the player, so it would cost a ship this frame."""
    game.player.invulnerable_timer = 0
    bolt = main.EnemyBolt(game.player.rect.centerx, game.player.rect.centery, velocity_y=0)
    game.enemy_projectiles.add(bolt)
    game.all_sprites.add(bolt)


def clear_bonus(game: "main.Game") -> int:
    if game.current_mode_id == "boss_rush":
        return int(160 * game.level)
    if game.current_mode_id in ("time_attack", "toxic_gauntlet"):
        return int(135 * game.level)
    return 120 * game.level


class PrimeVictory(unittest.TestCase):
    def assert_won(self, game, score_before, lives_before):
        self.assertEqual(game.game_phase, "victory")
        self.assertEqual(game.run_end_reason, "victory")
        self.assertEqual(game.lives, lives_before, "the run must not lose a ship after Prime falls")
        expected = clear_bonus(game) + int(game.wave_profile["boss_prime_bonus"])
        self.assertGreater(expected, 0)
        self.assertGreaterEqual(game.score - score_before, expected, "wave-clear and Prime bonuses must be paid")
        self.assertEqual(game.stats["waves_cleared"] >= 1, True)

    def test_support_centipedes_alive(self):
        game = prime_wave_game("classic")
        self.assertGreater(len(game.centipede_segments), 0, "Prime's wave should deploy support centipedes")
        score, lives = game.score, game.lives
        arm_kill_shot(game)
        game.handle_collisions()
        self.assertGreater(len(game.centipede_segments), 0, "support still alive when Prime falls")
        self.assert_won(game, score, lives)

    def test_projectile_in_flight_hits_player_same_frame(self):
        game = prime_wave_game("classic")
        bolt_on_player(game)
        score, lives = game.score, game.lives
        arm_kill_shot(game)
        game.handle_collisions()
        self.assertGreater(len(game.enemy_projectiles), 0, "the bolt is still in flight")
        self.assert_won(game, score, lives)

    def test_last_second_of_strike_clock(self):
        game = prime_wave_game("time_attack")
        self.assertIsNotNone(game.mode_timer_frames, "Time Attack runs a strike clock")
        game.mode_timer_frames = 61  # one second left
        score, lives = game.score, game.lives
        arm_kill_shot(game)
        game.update_mode_clock()  # same order as Game.update(): clock first, then collisions
        self.assertEqual(game.game_phase, "playing", "one second left must not time out yet")
        game.handle_collisions()
        self.assert_won(game, score, lives)
        self.assertGreater(game.mode_timer_frames, 60, "the boss time bonus is still granted")

    def test_last_ship_with_bolt_on_player(self):
        game = prime_wave_game("classic")
        game.lives = 1
        bolt_on_player(game)
        score = game.score
        arm_kill_shot(game)
        game.handle_collisions()
        self.assert_won(game, score, 1)

    def test_ordinary_matriarch_still_needs_the_trench_cleared(self):
        """Control: a non-Prime boss wave keeps the old rule (no early win)."""
        random.seed(7)
        game = main.Game()
        game.sound_enabled = False
        game.start_run("classic", skip_briefing=True)
        level = next(lv for lv in range(1, 60)
                     if game.build_wave_profile(lv)["kind"] == "boss" and not game.build_wave_profile(lv)["prime"])
        game.begin_wave(level)
        game.deploy_current_wave()
        self.assertGreater(len(game.centipede_segments), 0)
        arm_kill_shot(game)
        game.handle_collisions()
        self.assertEqual(len(game.bosses), 0)
        self.assertEqual(game.game_phase, "playing", "support must still be cleared after an ordinary Matriarch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
