"""Real pygame collision regressions. SDL dummy drivers prevent windows/audio."""
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Override, rather than setdefault: a caller must not accidentally open a window.
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
profile_root = ROOT / ".test-runtime"
profile_root.mkdir(exist_ok=True)
profile = tempfile.mkdtemp(prefix="prime-", dir=profile_root)
os.environ["LOCALAPPDATA"] = profile
os.environ["XDG_DATA_HOME"] = profile
sys.path.insert(0, str(ROOT))
import pygame
import main


class PrimeVictoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = main.Game()
        cls.game.sound_enabled = False

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def exercise(self, *, support=False, projectile=False, near_timeout=False, last_ship=False):
        for mode, level, clear_reward in [("classic", 12, 1440), ("time_attack", 9, 1215),
                                          ("toxic_gauntlet", 12, 1620), ("boss_rush", 3, 480)]:
            with self.subTest(mode=mode):
                random.seed(1287)
                game = self.game
                game.profile = game.default_profile()
                game.start_run(mode, skip_briefing=True)
                game.begin_wave(level)
                game.deploy_current_wave()
                self.assertTrue(game.wave_profile["prime"])
                game.mushrooms.empty()
                if not support:
                    for s in list(game.centipede_segments):
                        s.kill()
                    game.centipedes.clear()
                else:
                    self.assertTrue(game.centipedes)
                game.lives = 1 if last_ship else 3
                game.next_extra_life_score = 10**9
                game.player.invulnerable_timer = 0
                if near_timeout:
                    # Two frames: the final live frame reaches collisions before expiry.
                    game.mode_timer_frames = 2
                if projectile or last_ship:
                    bolt = main.EnemyBolt(*game.player.rect.center, velocity_y=0)
                    game.add_sprite(bolt, 4, game.all_sprites, game.enemy_projectiles)
                boss = next(iter(game.bosses))
                boss.health = 1
                shot = main.PlayerBullet(boss.rect.centerx, boss.rect.centery + 18)
                game.add_sprite(shot, 6, game.all_sprites, game.player_bullets)
                before = game.score
                game.update()
                self.assertFalse(game.bosses, "The actual bullet must kill Prime")
                self.assertEqual(game.game_phase, "victory")
                self.assertEqual(game.run_end_reason, "victory")
                self.assertEqual(game.stats["waves_cleared"], 1)
                self.assertEqual(game.stats["bosses_destroyed"], 1)
                # Hit + combo kill + wave clear + Prime collapse, exactly once.
                expected = 18 + 4200 + clear_reward + game.wave_profile["boss_prime_bonus"]
                self.assertEqual(game.score - before, expected)
                self.assertEqual(game.profile["recent_runs"][0]["result"], "victory")
                self.assertEqual(game.profile["recent_runs"][0]["waves_cleared"], 1)
                if support:
                    self.assertTrue(game.centipedes)
                if projectile or last_ship:
                    self.assertTrue(game.enemy_projectiles)
                if last_ship:
                    self.assertEqual(game.lives, 1)
                awarded = game.score
                game.update()
                game.resolve_wave_completion()
                game.enter_game_over("timeout")
                self.assertEqual(game.game_phase, "victory")
                self.assertEqual(game.score, awarded)
                self.assertEqual(game.stats["waves_cleared"], 1)

    def test_prime_dies_with_support_alive(self):
        self.exercise(support=True)

    def test_prime_dies_with_projectiles_in_flight(self):
        self.exercise(projectile=True)

    def test_prime_dies_near_timeout(self):
        self.exercise(near_timeout=True)

    def test_prime_dies_on_the_last_ship_with_an_incoming_hit(self):
        self.exercise(last_ship=True)


if __name__ == "__main__":
    unittest.main()
