"""A lost key-up while switching apps must not cost the player a run."""
import unittest

from tools.test_prime_victory import main, prime_wave_game


class FocusRecovery(unittest.TestCase):
    def test_focus_loss_pauses_and_releases_every_control(self):
        game = prime_wave_game("time_attack")
        for key in (main.pygame.K_LEFT, main.pygame.K_RIGHT, main.pygame.K_UP,
                    main.pygame.K_DOWN, main.pygame.K_SPACE):
            game.handle_keydown(key)
        game.handle_focus_lost()
        self.assertEqual(game.game_phase, "paused")
        self.assertFalse(any((game.move_left, game.move_right, game.move_up,
                              game.move_down, game.fire_held)))
        timer, position = game.mode_timer_frames, game.player.rect.center
        for _ in range(60):
            game.update()
        self.assertEqual(game.mode_timer_frames, timer)
        self.assertEqual(game.player.rect.center, position)
        game.handle_keydown(main.pygame.K_p)
        self.assertEqual(game.game_phase, "playing")
        game.handle_keydown(main.pygame.K_SPACE)
        self.assertTrue(game.fire_held)

    def test_focus_loss_preserves_menus_and_endings(self):
        game = prime_wave_game("classic")
        for phase in ("title", "briefing", "paused", "game_over", "victory"):
            with self.subTest(phase=phase):
                game.game_phase = phase
                game.fire_held = True
                game.handle_focus_lost()
                self.assertEqual(game.game_phase, phase)
                self.assertFalse(game.fire_held)

    def test_focus_loss_suspends_intro_until_explicit_resume(self):
        for level, resume_key in ((1, main.pygame.K_p), (2, main.pygame.K_RETURN)):
            with self.subTest(level=level):
                game = main.Game()
                game.sound_enabled = False
                game.start_run("time_attack", skip_briefing=True)
                if level == 2:
                    game.begin_wave(level)
                self.assertEqual(game.game_phase, "wave_intro")
                intro_timer, clock, lives = game.wave_intro_timer, game.mode_timer_frames, game.lives
                game.handle_focus_lost()
                game.handle_focus_lost()  # repeated notifications must preserve the return phase
                for _ in range(intro_timer + 120):
                    game.update()
                self.assertEqual(game.game_phase, "paused")
                self.assertEqual(game.wave_intro_timer, intro_timer)
                self.assertEqual(game.mode_timer_frames, clock)
                self.assertEqual(game.lives, lives)
                game.handle_keydown(resume_key)
                self.assertEqual(game.game_phase, "wave_intro")
                for _ in range(intro_timer + 1):
                    game.update()
                self.assertEqual(game.game_phase, "playing")
                # A later ordinary pause must return to gameplay, not the introduction.
                game.handle_keydown(main.pygame.K_p)
                game.handle_keydown(main.pygame.K_p)
                self.assertEqual(game.game_phase, "playing")


if __name__ == "__main__":
    unittest.main()
