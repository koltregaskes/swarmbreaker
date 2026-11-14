import asyncio
import glob
import io
import json
import math
import os
import random
import struct
import sys
from datetime import datetime
from urllib.parse import parse_qs

import pygame


class SilentSound:
    def play(self):
        return None


IS_WEB = sys.platform == "emscripten"
WEB_STORAGE_PREFIX = "swarmbreaker:"
WEB_QUERY_PARAMS = {}
WEB_PLATFORM = None
WEB_WINDOW = None
WEB_BRIDGE_KIND = "none"

if IS_WEB:
    try:
        import js  # type: ignore

        WEB_WINDOW = js.window
        WEB_BRIDGE_KIND = "js"
    except Exception:
        WEB_WINDOW = None

    if WEB_WINDOW is None:
        try:
            import platform as WEB_PLATFORM  # type: ignore[assignment]

            WEB_WINDOW = getattr(WEB_PLATFORM, "window", None)
            if WEB_WINDOW is not None:
                WEB_BRIDGE_KIND = "platform"
        except Exception:
            WEB_PLATFORM = None
            WEB_WINDOW = None

    try:
        location = getattr(WEB_WINDOW, "location", None) if WEB_WINDOW is not None else None
        search = str(getattr(location, "search", "") or "")
        WEB_QUERY_PARAMS = parse_qs(search.lstrip("?"))
    except Exception:
        WEB_QUERY_PARAMS = {}


pygame.init()
try:
    pygame.mixer.init()
    pygame.mixer.set_num_channels(16)
    pygame.mixer.set_reserved(1)
    AUDIO_AVAILABLE = True
except pygame.error:
    AUDIO_AVAILABLE = False


def is_mixer_sound(sound):
    return AUDIO_AVAILABLE and isinstance(sound, pygame.mixer.Sound)


HEADLESS_SMOKE_TEST = (
    os.environ.get("SWARMBREAKER_HEADLESS_SMOKE_TEST") == "1"
    or os.environ.get("BUGBLASTER_HEADLESS_SMOKE_TEST") == "1"
)
SMOKE_TEST_FRAME_LIMIT = 300

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
GRID_STEP = 20
PLAYER_ZONE_TOP = SCREEN_HEIGHT - 120
PLAYER_START_BOTTOM = SCREEN_HEIGHT - 26
PLAYER_VERTICAL_RANGE = GRID_STEP * 4
PLAYER_MIN_BOTTOM = PLAYER_START_BOTTOM - PLAYER_VERTICAL_RANGE
EXTRA_LIFE_STEP = 10_000
LEGACY_HIGH_SCORE_PATH = "swarmbreaker_highscore.json"
LEGACY_SETTINGS_PATH = "swarmbreaker_settings.json"
LEGACY_PROFILE_PATH = "swarmbreaker_profile.json"
BOSS_WAVE_INTERVAL = 4
SCORING_MODEL_VERSION = 2
RECENT_RUN_LIMIT = 18
TOP_RUNS_PER_MODE = 5

BLACK = (0, 0, 0)
WHITE = (245, 247, 252)
TITLE_COLOR = (96, 221, 255)
PANEL_COLOR = (16, 20, 30)
PANEL_BORDER = (52, 88, 122)
SUCCESS_COLOR = (112, 235, 157)
WARNING_COLOR = (255, 204, 94)
DANGER_COLOR = (255, 110, 110)
AUDIO_ON_COLOR = (132, 232, 179)
AUDIO_OFF_COLOR = (255, 160, 160)
RANK_THRESHOLDS = [
    ("C", 3_000),
    ("B", 7_000),
    ("A", 12_000),
    ("S", 18_000),
]
OPTIONAL_SOUND_ROOTS = (
    os.path.join("assets", "sounds", "desktop"),
    os.path.join("assets", "sounds"),
)

LEVEL_THEMES = [
    {
        "name": "Signal Blue",
        "top": (7, 11, 19),
        "bottom": (15, 18, 33),
        "band": (12, 22, 34),
        "grid": (19, 31, 47),
        "lane_edge": (62, 108, 142),
        "lane_glow": (25, 200, 190),
        "diagonal": (25, 45, 64),
        "panel_border": (52, 88, 122),
        "title": (96, 221, 255),
        "warning": (255, 204, 94),
        "status": (172, 186, 205),
    },
    {
        "name": "Amber Bloom",
        "top": (24, 10, 8),
        "bottom": (44, 20, 12),
        "band": (38, 22, 18),
        "grid": (66, 42, 28),
        "lane_edge": (196, 118, 72),
        "lane_glow": (255, 170, 96),
        "diagonal": (82, 52, 34),
        "panel_border": (168, 104, 68),
        "title": (255, 196, 118),
        "warning": (255, 227, 135),
        "status": (228, 198, 170),
    },
    {
        "name": "Venom Violet",
        "top": (14, 8, 24),
        "bottom": (28, 16, 42),
        "band": (24, 18, 42),
        "grid": (42, 31, 70),
        "lane_edge": (118, 92, 188),
        "lane_glow": (183, 120, 255),
        "diagonal": (54, 36, 84),
        "panel_border": (108, 86, 174),
        "title": (198, 164, 255),
        "warning": (255, 210, 114),
        "status": (204, 191, 232),
    },
    {
        "name": "Toxin Green",
        "top": (8, 18, 12),
        "bottom": (16, 34, 20),
        "band": (12, 30, 19),
        "grid": (24, 54, 32),
        "lane_edge": (86, 154, 100),
        "lane_glow": (124, 240, 148),
        "diagonal": (28, 62, 41),
        "panel_border": (74, 138, 94),
        "title": (144, 244, 188),
        "warning": (255, 228, 118),
        "status": (186, 216, 192),
    },
    {
        "name": "Solar Red",
        "top": (20, 7, 10),
        "bottom": (42, 10, 16),
        "band": (33, 12, 18),
        "grid": (62, 19, 30),
        "lane_edge": (184, 78, 88),
        "lane_glow": (255, 112, 122),
        "diagonal": (74, 24, 35),
        "panel_border": (156, 72, 86),
        "title": (255, 142, 142),
        "warning": (255, 210, 126),
        "status": (224, 182, 186),
    },
]

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Swarmbreaker")


def clamp(value, low, high):
    return max(low, min(high, value))


def format_seconds(total_seconds):
    minutes, seconds = divmod(max(0, int(total_seconds)), 60)
    return f"{minutes:02d}:{seconds:02d}"


def query_param(name, default=""):
    values = WEB_QUERY_PARAMS.get(name)
    if not values:
        return default
    return values[-1]


def query_flag(name):
    value = query_param(name, "")
    return value.lower() in {"1", "true", "yes", "on"}


def web_storage_get(storage_name):
    if not IS_WEB or WEB_WINDOW is None:
        return None
    try:
        return WEB_WINDOW.localStorage.getItem(f"{WEB_STORAGE_PREFIX}{storage_name}")
    except Exception:
        return None


def web_storage_set(storage_name, value):
    if not IS_WEB or WEB_WINDOW is None:
        return False
    try:
        WEB_WINDOW.localStorage.setItem(f"{WEB_STORAGE_PREFIX}{storage_name}", value)
    except Exception:
        return False
    return True


def web_console_log(label, payload=None):
    if not IS_WEB or WEB_WINDOW is None:
        return
    try:
        if payload is None:
            WEB_WINDOW.console.log(label)
        else:
            WEB_WINDOW.console.log(label, payload)
    except Exception:
        return


def web_console_error(label, payload=None):
    if not IS_WEB or WEB_WINDOW is None:
        return
    try:
        if payload is None:
            WEB_WINDOW.console.error(label)
        else:
            WEB_WINDOW.console.error(label, payload)
    except Exception:
        return


def web_debug_event(label, payload=None):
    if not IS_WEB:
        return
    try:
        if payload is None:
            print(label)
        else:
            print(f"{label} {json.dumps(payload, sort_keys=True)}")
    except Exception:
        print(label)
    web_console_log(label, payload)
    if payload is None:
        storage_payload = {"label": label}
    else:
        storage_payload = {"label": label, "payload": payload}
    web_storage_set("debug:last", json.dumps(storage_payload, sort_keys=True))


def render_boot_probe(stage, detail=""):
    if not IS_WEB:
        return
    surface = pygame.display.get_surface()
    if surface is None:
        return

    surface.fill((9, 15, 26))
    panel = pygame.Rect(72, 82, max(300, surface.get_width() - 144), max(180, surface.get_height() - 164))
    pygame.draw.rect(surface, (16, 24, 38), panel, border_radius=20)
    pygame.draw.rect(surface, (66, 118, 160), panel, width=3, border_radius=20)
    pygame.draw.line(surface, (35, 80, 110), (panel.left + 24, panel.top + 80), (panel.right - 24, panel.top + 80), 2)

    title_font = pygame.font.Font(None, 58)
    body_font = pygame.font.Font(None, 30)
    tiny_font = pygame.font.Font(None, 24)
    title = title_font.render("Swarmbreaker Browser Review", True, TITLE_COLOR)
    subtitle = body_font.render(stage, True, WHITE)
    surface.blit(title, title.get_rect(midtop=(surface.get_width() // 2, panel.top + 22)))
    surface.blit(subtitle, subtitle.get_rect(midtop=(surface.get_width() // 2, panel.top + 100)))

    if detail:
        detail_lines = [detail[i:i + 52] for i in range(0, len(detail), 52)]
        for index, line in enumerate(detail_lines[:3]):
            detail_surface = tiny_font.render(line, True, (186, 205, 223))
            surface.blit(detail_surface, detail_surface.get_rect(midtop=(surface.get_width() // 2, panel.top + 144 + index * 28)))

    badge_font = pygame.font.Font(None, 26)
    badge = badge_font.render("Experimental browser runtime", True, WARNING_COLOR)
    surface.blit(badge, badge.get_rect(midbottom=(surface.get_width() // 2, panel.bottom - 24)))
    pygame.display.flip()
    web_debug_event(
        "swarmbreaker:web-stage",
        {
            "stage": stage,
            "detail": detail,
            "surface": list(surface.get_size()),
        },
    )


def get_data_dir():
    if os.name == "nt":
        base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base_dir = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base_dir, "Swarmbreaker")


DATA_DIR = get_data_dir()
HIGH_SCORE_PATH = os.path.join(DATA_DIR, LEGACY_HIGH_SCORE_PATH)
SETTINGS_PATH = os.path.join(DATA_DIR, LEGACY_SETTINGS_PATH)
PROFILE_PATH = os.path.join(DATA_DIR, LEGACY_PROFILE_PATH)

RANK_VALUES = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4}
WIN_LINE = "Win: destroy Matriarch Prime."
LOSS_LINE = "Loss: no ships left, clock hits zero, or you abandon."

GAME_MODES = {
    "classic": {
        "label": "Classic Defence",
        "short_label": "Classic",
        "tagline": "Break Matriarch Prime to hold Sector Seven.",
        "description": "The campaign. A boss every fourth wave. Destroy Matriarch Prime on wave 12 to win.",
        "rules": [
            "Destroy Matriarch Prime on wave 12.",
            "A boss arrives every fourth wave.",
            "Loss: no ships left, or you abandon.",
        ],
        "briefing_lines": [
            "Standard trench doctrine is still holding around Sector Seven.",
            "Build score, preserve the lane, and survive into matriarch territory.",
        ],
        "start_lives": 3,
        "mushroom_count": 52,
        "extra_life_step": 10_000,
        "boss_interval": 4,
        "boss_health_scale": 1.0,
        "centipede_length_bonus": 0,
        "secondary_wave_bonus": 0,
        "centipede_delay_bonus": 0,
        "spider_rate_scale": 1.0,
        "spider_limit_bonus": 0,
        "scorpion_rate_scale": 1.0,
        "flea_threshold_bonus": 0,
        "poison_seed": 0.0,
        "time_limit_seconds": None,
        "time_cap_seconds": None,
        "time_bonus_wave": 0,
        "time_bonus_boss": 0,
        "boss_support_length": 0,
        "unlock": None,
    },
    "time_attack": {
        "label": "Time Attack",
        "short_label": "Time Attack",
        "tagline": "Break Matriarch Prime before the strike clock dies.",
        "description": "A three-minute sprint. Destroy Matriarch Prime on wave 9, or the clock ends the run.",
        "rules": [
            "Destroy Matriarch Prime on wave 9.",
            "Clock starts at 3:00. Clears add time.",
            "Loss: clock zero, no ships, or abandon.",
        ],
        "briefing_lines": [
            "Command wants a hot extraction score before the lane collapses.",
            "Every clear buys seconds. Keep moving or the clock will bury the run.",
        ],
        "start_lives": 3,
        "mushroom_count": 48,
        "extra_life_step": 14_000,
        "boss_interval": 3,
        "boss_health_scale": 0.92,
        "centipede_length_bonus": 1,
        "secondary_wave_bonus": 0,
        "centipede_delay_bonus": -1,
        "spider_rate_scale": 0.86,
        "spider_limit_bonus": 1,
        "scorpion_rate_scale": 0.9,
        "flea_threshold_bonus": 2,
        "poison_seed": 0.04,
        "time_limit_seconds": 180,
        "time_cap_seconds": 240,
        "time_bonus_wave": 12,
        "time_bonus_boss": 18,
        "boss_support_length": 0,
        "unlock": None,
    },
    "toxic_gauntlet": {
        "label": "Toxic Gauntlet",
        "short_label": "Toxic",
        "tagline": "Break Matriarch Prime through the venom lane.",
        "description": "The campaign on a poisoned field. Destroy Matriarch Prime on wave 12.",
        "rules": [
            "Destroy Matriarch Prime on wave 12.",
            "Fewer ships, and more venom caps.",
            "Loss: no ships left, or you abandon.",
        ],
        "briefing_lines": [
            "The lower orchard is saturated with venom caps and collapsing cover.",
            "Clear safe lanes early or the dive chains will own the trench.",
        ],
        "start_lives": 2,
        "mushroom_count": 58,
        "extra_life_step": 12_000,
        "boss_interval": 4,
        "boss_health_scale": 1.08,
        "centipede_length_bonus": 1,
        "secondary_wave_bonus": 1,
        "centipede_delay_bonus": -1,
        "spider_rate_scale": 0.9,
        "spider_limit_bonus": 1,
        "scorpion_rate_scale": 0.58,
        "flea_threshold_bonus": 4,
        "poison_seed": 0.22,
        "time_limit_seconds": None,
        "time_cap_seconds": None,
        "time_bonus_wave": 0,
        "time_bonus_boss": 0,
        "boss_support_length": 0,
        "unlock": {
            "type": "bosses_destroyed",
            "value": 1,
            "label": "Break 1 Hive Matriarch in any mode.",
        },
    },
    "boss_rush": {
        "label": "Boss Rush",
        "short_label": "Boss Rush",
        "tagline": "Break Matriarch Prime. Every wave is a queen.",
        "description": "No warm-up. Destroy Matriarch Prime on wave 3.",
        "rules": [
            "Destroy Matriarch Prime on wave 3.",
            "Every wave is a hive queen.",
            "Loss: no ships left, or you abandon.",
        ],
        "briefing_lines": [
            "Command cut the scouting phase. The brood queens are hitting in sequence.",
            "Break each matriarch fast before the support swarms stack up behind her.",
        ],
        "start_lives": 2,
        "mushroom_count": 44,
        "extra_life_step": 18_000,
        "boss_interval": 1,
        "boss_health_scale": 0.9,
        "centipede_length_bonus": 0,
        "secondary_wave_bonus": 0,
        "centipede_delay_bonus": -1,
        "spider_rate_scale": 1.0,
        "spider_limit_bonus": 0,
        "scorpion_rate_scale": 1.0,
        "flea_threshold_bonus": 1,
        "poison_seed": 0.12,
        "time_limit_seconds": None,
        "time_cap_seconds": None,
        "time_bonus_wave": 0,
        "time_bonus_boss": 0,
        "boss_support_length": 5,
        "unlock": {
            "type": "bosses_destroyed",
            "value": 3,
            "label": "Break 3 Hive Matriarchs across all runs.",
        },
    },
}


def campaign_finale_wave(mode):
    interval = mode["boss_interval"] or BOSS_WAVE_INTERVAL
    return 3 * interval


def ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        return False
    return True


def rank_value(rank_label):
    return RANK_VALUES.get(rank_label, -1)


def better_rank(current_rank, candidate_rank):
    if rank_value(candidate_rank) > rank_value(current_rank):
        return candidate_rank
    return current_rank


def scale_surface(surface, scale):
    if scale == 1:
        return surface.copy()
    width = max(1, int(surface.get_width() * scale))
    height = max(1, int(surface.get_height() * scale))
    return pygame.transform.smoothscale(surface, (width, height))


def load_image(path, scale=1):
    image = pygame.image.load(path).convert_alpha()
    return scale_surface(image, scale)


def load_sequence(pattern, scale=1, max_frames=None):
    frames = []
    paths = sorted(glob.glob(pattern))
    if max_frames is not None:
        paths = paths[:max_frames]
    for path in paths:
        frames.append(load_image(path, scale))
    return frames


def tint_surface(surface, color, add_alpha=0):
    tinted = surface.copy()
    overlay = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
    overlay.fill((*color, 255))
    tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if add_alpha:
        glow = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
        glow.fill((*color, add_alpha))
        tinted.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted


def make_boss_surface():
    surface = pygame.Surface((132, 92), pygame.SRCALPHA)
    pygame.draw.ellipse(surface, (48, 9, 20), (20, 22, 92, 54))
    pygame.draw.ellipse(surface, (121, 27, 41), (24, 26, 84, 44))
    pygame.draw.ellipse(surface, (187, 72, 86), (34, 34, 64, 28))
    pygame.draw.ellipse(surface, (255, 173, 78), (10, 35, 16, 22))
    pygame.draw.ellipse(surface, (255, 173, 78), (106, 35, 16, 22))
    pygame.draw.polygon(surface, (157, 27, 47), [(60, 12), (72, 4), (84, 12), (72, 26)])
    pygame.draw.polygon(surface, (206, 88, 102), [(64, 16), (72, 9), (80, 16), (72, 24)])
    pygame.draw.circle(surface, (255, 244, 235), (50, 43), 10)
    pygame.draw.circle(surface, (255, 244, 235), (82, 43), 10)
    pygame.draw.circle(surface, (27, 10, 18), (50, 43), 5)
    pygame.draw.circle(surface, (27, 10, 18), (82, 43), 5)
    pygame.draw.circle(surface, (255, 97, 97), (50, 43), 2)
    pygame.draw.circle(surface, (255, 97, 97), (82, 43), 2)
    pygame.draw.arc(surface, (255, 193, 114), (38, 46, 56, 20), math.pi * 0.1, math.pi - 0.1, 3)
    for x in (28, 44, 92, 108):
        pygame.draw.line(surface, (78, 33, 48), (x, 54), (x - 18 if x < 70 else x + 18, 86), 5)
        pygame.draw.line(surface, (145, 72, 86), (x, 52), (x - 18 if x < 70 else x + 18, 84), 2)
    pygame.draw.line(surface, (115, 29, 44), (66, 68), (56, 90), 5)
    pygame.draw.line(surface, (115, 29, 44), (66, 68), (76, 90), 5)
    pygame.draw.line(surface, (236, 99, 116), (66, 68), (72, 86), 2)
    return surface


def make_player_surface():
    surface = pygame.Surface((44, 34), pygame.SRCALPHA)
    pygame.draw.polygon(surface, (88, 228, 255), [(22, 2), (42, 28), (30, 32), (22, 22), (14, 32), (2, 28)])
    pygame.draw.polygon(surface, (224, 252, 255), [(22, 6), (33, 24), (22, 18), (11, 24)])
    pygame.draw.rect(surface, (255, 167, 92), (18, 18, 8, 12), border_radius=4)
    return surface


def make_mushroom_surface():
    surface = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.ellipse(surface, (230, 236, 248), (2, 2, 20, 12))
    pygame.draw.ellipse(surface, (132, 198, 255), (4, 4, 16, 8))
    pygame.draw.rect(surface, (180, 206, 235), (9, 10, 6, 10), border_radius=3)
    return surface


def make_centipede_segment_surface(is_head=False):
    surface = pygame.Surface((26, 22), pygame.SRCALPHA)
    shell_color = (255, 173, 84) if is_head else (250, 114, 96)
    accent_color = (255, 240, 204) if is_head else (255, 199, 174)
    pygame.draw.ellipse(surface, shell_color, (2, 2, 22, 18))
    pygame.draw.ellipse(surface, accent_color, (6, 5, 14, 8))
    if is_head:
        pygame.draw.circle(surface, (22, 18, 30), (8, 10), 2)
        pygame.draw.circle(surface, (22, 18, 30), (18, 10), 2)
        pygame.draw.line(surface, (255, 221, 123), (7, 3), (2, 0), 2)
        pygame.draw.line(surface, (255, 221, 123), (19, 3), (24, 0), 2)
    return surface


def make_spider_surface():
    surface = pygame.Surface((44, 26), pygame.SRCALPHA)
    abdomen_color = (122, 94, 224)
    thorax_color = (92, 70, 178)
    leg_color = (70, 56, 148)
    eye_color = (255, 212, 118)

    left_leg_points = [
        ((16, 14), (4, 4), (0, 2)),
        ((16, 14), (3, 10), (0, 10)),
        ((16, 14), (3, 18), (0, 22)),
        ((16, 14), (7, 24), (4, 26)),
    ]
    right_leg_points = [
        ((28, 14), (40, 4), (44, 2)),
        ((28, 14), (41, 10), (44, 10)),
        ((28, 14), (41, 18), (44, 22)),
        ((28, 14), (37, 24), (40, 26)),
    ]
    for start, joint, end in left_leg_points + right_leg_points:
        pygame.draw.line(surface, leg_color, start, joint, 2)
        pygame.draw.line(surface, leg_color, joint, end, 2)

    pygame.draw.ellipse(surface, abdomen_color, (12, 8, 22, 14))
    pygame.draw.ellipse(surface, (150, 126, 242), (16, 10, 14, 7))
    pygame.draw.circle(surface, thorax_color, (11, 15), 6)
    pygame.draw.circle(surface, (118, 95, 205), (11, 15), 4)
    pygame.draw.circle(surface, eye_color, (8, 13), 2)
    pygame.draw.circle(surface, eye_color, (12, 13), 2)
    pygame.draw.line(surface, eye_color, (8, 19), (2, 23), 2)
    pygame.draw.line(surface, eye_color, (12, 19), (6, 24), 2)
    return surface


def make_flea_surface():
    surface = pygame.Surface((18, 28), pygame.SRCALPHA)
    pygame.draw.ellipse(surface, (112, 235, 157), (3, 2, 12, 24))
    pygame.draw.ellipse(surface, (231, 255, 240), (5, 6, 8, 8))
    return surface


def make_scorpion_surface():
    surface = pygame.Surface((40, 24), pygame.SRCALPHA)
    pygame.draw.ellipse(surface, (255, 124, 140), (6, 6, 20, 12))
    pygame.draw.arc(surface, (255, 184, 92), (16, 0, 18, 18), math.pi * 1.6, math.pi * 0.25, 3)
    pygame.draw.circle(surface, (255, 208, 138), (31, 8), 4)
    pygame.draw.line(surface, (255, 124, 140), (7, 16), (0, 20), 2)
    pygame.draw.line(surface, (255, 124, 140), (25, 16), (34, 20), 2)
    return surface


def make_effect_frames(size, ring_color, glow_color, frame_count):
    frames = []
    center = size // 2
    for index in range(frame_count):
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        progress = (index + 1) / frame_count
        ring_radius = max(2, int((size * 0.18) + (size * 0.34 * progress)))
        glow_radius = max(ring_radius + 2, int(ring_radius * 1.35))
        alpha = max(30, int(220 - progress * 150))
        pygame.draw.circle(surface, (*glow_color, max(18, alpha // 3)), (center, center), glow_radius)
        pygame.draw.circle(surface, (*ring_color, alpha), (center, center), ring_radius, width=max(2, size // 10))
        spark = max(2, int(size * 0.06))
        pygame.draw.line(surface, (*ring_color, alpha), (center, center - ring_radius - spark), (center, center + ring_radius + spark), spark)
        pygame.draw.line(surface, (*ring_color, alpha), (center - ring_radius - spark, center), (center + ring_radius + spark, center), spark)
        frames.append(surface)
    return frames


def build_web_review_assets():
    return {
        "player": make_player_surface(),
        "mushroom": make_mushroom_surface(),
        "centipede_head": make_centipede_segment_surface(is_head=True),
        "centipede_body": make_centipede_segment_surface(is_head=False),
        "spider": make_spider_surface(),
        "flea": make_flea_surface(),
        "scorpion": make_scorpion_surface(),
        "hit_frames": make_effect_frames(34, (255, 214, 120), (255, 150, 76), 6),
        "muzzle_frames": make_effect_frames(26, (120, 232, 255), (52, 130, 255), 5),
        "explosion_frames": make_effect_frames(56, (255, 164, 110), (255, 86, 92), 7),
        "boss_explosion_frames": make_effect_frames(92, (255, 206, 122), (255, 84, 114), 9),
        "boss": make_boss_surface(),
    }


def build_tone_sound(notes, volume=0.3):
    if not AUDIO_AVAILABLE or IS_WEB:
        return SilentSound()

    try:
        import wave
    except ImportError:
        return SilentSound()

    sample_rate = 44_100
    buffer = io.BytesIO()
    frames = bytearray()
    for frequency, duration, waveform in notes:
        sample_count = max(1, int(sample_rate * duration))
        attack = max(1, int(sample_count * 0.08))
        release = max(1, int(sample_count * 0.18))
        for index in range(sample_count):
            t = index / sample_rate
            if waveform == "square":
                sample = 1.0 if math.sin(2 * math.pi * frequency * t) >= 0 else -1.0
            elif waveform == "triangle":
                phase = (t * frequency) % 1.0
                sample = 4 * abs(phase - 0.5) - 1
            else:
                sample = math.sin(2 * math.pi * frequency * t)

            envelope = 1.0
            if index < attack:
                envelope = index / attack
            elif index > sample_count - release:
                envelope = max(0.0, (sample_count - index) / release)

            value = int(32767 * volume * envelope * sample)
            frames.extend(struct.pack("<h", value))

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)

    buffer.seek(0)
    return pygame.mixer.Sound(file=buffer)


def load_sound(path):
    if not AUDIO_AVAILABLE:
        return SilentSound()
    if IS_WEB and path.lower().endswith(".wav"):
        ogg_path = f"{os.path.splitext(path)[0]}.ogg"
        if os.path.exists(ogg_path):
            path = ogg_path
        else:
            return SilentSound()
    try:
        return pygame.mixer.Sound(path)
    except pygame.error:
        return SilentSound()


def find_optional_sound(base_name):
    for root in OPTIONAL_SOUND_ROOTS:
        for extension in (".ogg", ".wav"):
            candidate = os.path.join(root, f"{base_name}{extension}")
            if os.path.exists(candidate):
                return candidate
    return None


def load_sound_bank_entry(base_name, fallback_notes=None, volume=0.3):
    sound_path = find_optional_sound(base_name)
    if sound_path:
        return load_sound(sound_path)
    if fallback_notes is None:
        return SilentSound()
    return build_tone_sound(fallback_notes, volume)


class AnimatedEffect(pygame.sprite.Sprite):
    def __init__(self, frames, position, frame_step=0.55):
        super().__init__()
        self.frames = frames or [pygame.Surface((1, 1), pygame.SRCALPHA)]
        self.frame_step = frame_step
        self.progress = 0.0
        self.image = self.frames[0]
        self.rect = self.image.get_rect(center=position)

    def update(self):
        self.progress += self.frame_step
        frame_index = int(self.progress)
        if frame_index >= len(self.frames):
            self.kill()
            return
        center = self.rect.center
        self.image = self.frames[frame_index]
        self.rect = self.image.get_rect(center=center)


class FloatingText(pygame.sprite.Sprite):
    def __init__(self, game, text, position, color=WHITE, life=45, size=18):
        super().__init__()
        self.game = game
        self.velocity_y = -0.9
        self.life = life
        self.image = self.game.render_text(text, size, color, bold=True)
        self.rect = self.image.get_rect(center=position)

    def update(self):
        self.life -= 1
        self.rect.y += self.velocity_y
        alpha = int(255 * max(0, self.life) / 45)
        self.image.set_alpha(alpha)
        if self.life <= 0:
            self.kill()


class Player(pygame.sprite.Sprite):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.base_image = self.game.assets["player"]
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect(midbottom=(SCREEN_WIDTH // 2, PLAYER_START_BOTTOM))
        self.speed = 5.5
        self.fire_cooldown = 0
        self.fire_interval = 10
        self.invulnerable_timer = 0

    def reset_position(self):
        self.rect.midbottom = (SCREEN_WIDTH // 2, PLAYER_START_BOTTOM)
        self.fire_cooldown = 0
        self.invulnerable_timer = 75

    def update(self):
        horizontal = int(self.game.move_right) - int(self.game.move_left)
        vertical = int(self.game.move_down) - int(self.game.move_up)
        self.rect.x += int(round(horizontal * self.speed))
        self.rect.y += int(round(vertical * self.speed))
        self.rect.left = clamp(self.rect.left, 0, SCREEN_WIDTH - self.rect.width)
        self.rect.bottom = clamp(self.rect.bottom, PLAYER_MIN_BOTTOM, PLAYER_START_BOTTOM)

        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if self.invulnerable_timer > 0:
            self.invulnerable_timer -= 1

        self.image = self.base_image.copy()
        if self.invulnerable_timer > 0 and (self.invulnerable_timer // 4) % 2 == 0:
            self.image.set_alpha(110)

        if self.game.game_phase == "playing" and self.game.fire_held:
            self.try_fire()

    def try_fire(self):
        if self.fire_cooldown > 0:
            return
        self.fire_cooldown = self.fire_interval
        bullet = PlayerBullet(self.rect.centerx, self.rect.top)
        self.game.add_sprite(bullet, 6, self.game.all_sprites, self.game.player_bullets)
        self.game.play_sound(self.game.sounds["shoot"])
        self.game.spawn_effect("muzzle", (self.rect.centerx, self.rect.top + 6))


class PlayerBullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((6, 16), pygame.SRCALPHA)
        pygame.draw.rect(self.image, (255, 226, 160), (1, 0, 4, 16), border_radius=3)
        pygame.draw.rect(self.image, (255, 255, 255), (2, 1, 2, 10), border_radius=2)
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.speed_y = -11

    def update(self):
        self.rect.y += self.speed_y
        if self.rect.bottom < 0:
            self.kill()


class EnemyBolt(pygame.sprite.Sprite):
    def __init__(self, x, y, velocity_x=0.0, velocity_y=5.2):
        super().__init__()
        self.image = pygame.Surface((10, 18), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, (255, 108, 92), (0, 0, 10, 18))
        pygame.draw.ellipse(self.image, (255, 214, 148), (2, 2, 6, 9))
        self.rect = self.image.get_rect(center=(x, y))
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y

    def update(self):
        self.rect.x += self.velocity_x
        self.rect.y += self.velocity_y
        if self.rect.top > SCREEN_HEIGHT or self.rect.right < -20 or self.rect.left > SCREEN_WIDTH + 20:
            self.kill()


class Mushroom(pygame.sprite.Sprite):
    def __init__(self, game, x, y):
        super().__init__()
        self.game = game
        self.base_image = self.game.assets["mushroom"]
        self.rect = self.base_image.get_rect(topleft=(x, y))
        self.health = 4
        self.poisoned = False
        self.image = self.base_image.copy()
        self.refresh_image()

    def hit(self):
        self.health -= 1
        if self.health <= 0:
            self.kill()
            return 8
        self.refresh_image()
        return 2

    def poison(self):
        if not self.poisoned:
            self.poisoned = True
            self.refresh_image()

    def refresh_image(self):
        palette = {
            (False, 4): (232, 240, 252),
            (False, 3): (255, 218, 92),
            (False, 2): (255, 155, 79),
            (False, 1): (255, 93, 93),
            (True, 4): (167, 97, 255),
            (True, 3): (147, 82, 239),
            (True, 2): (125, 67, 220),
            (True, 1): (103, 52, 188),
        }
        glow = 35 if self.poisoned else 0
        self.image = tint_surface(self.base_image, palette[(self.poisoned, self.health)], glow)


class CentipedeSegment(pygame.sprite.Sprite):
    def __init__(self, game, x, y, is_head=False):
        super().__init__()
        self.game = game
        self.is_head = is_head
        self.diving = False
        self.direction = 1
        self.speed = GRID_STEP
        self.base_head = self.game.assets["centipede_head"]
        self.base_body = self.game.assets["centipede_body"]
        self.image = self.base_head.copy() if is_head else self.base_body.copy()
        self.rect = self.image.get_rect(topleft=(x, y))
        self.refresh_image()

    def refresh_image(self):
        base = self.base_head if self.is_head else self.base_body
        if self.diving and self.is_head:
            self.image = tint_surface(base, (210, 82, 255), 65)
        else:
            self.image = base.copy()

    def move_down(self):
        self.rect.y += GRID_STEP
        self.direction *= -1
        if self.is_head:
            collided = pygame.sprite.spritecollide(self, self.game.mushrooms, False)
            if collided and collided[0].poisoned:
                self.diving = True
                self.refresh_image()

    def move_dive(self):
        self.rect.y += GRID_STEP
        dive_floor = PLAYER_ZONE_TOP - 8
        if self.rect.top >= dive_floor:
            self.rect.top = dive_floor
            self.diving = False
            self.direction = random.choice([-1, 1])
            self.refresh_image()

    def update(self):
        return None


class Spider(pygame.sprite.Sprite):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.image = self.game.assets["spider"]
        self.rect = self.image.get_rect()
        speed_base = 3 + min(2, self.game.level * 0.15)
        if random.choice([True, False]):
            self.rect.x = -self.rect.width
            self.speed_x = speed_base
        else:
            self.rect.x = SCREEN_WIDTH
            self.speed_x = -speed_base
        self.rect.y = random.randrange(PLAYER_MIN_BOTTOM - 6, SCREEN_HEIGHT - 70)
        self.speed_y = random.choice([-2.2, 2.2])
        self.top_boundary = PLAYER_MIN_BOTTOM - 8
        self.bottom_boundary = SCREEN_HEIGHT - 34

    def update(self):
        self.rect.x += self.speed_x
        self.rect.y += self.speed_y
        if self.rect.top < self.top_boundary or self.rect.bottom > self.bottom_boundary:
            self.speed_y *= -1
        if self.rect.right < -40 or self.rect.left > SCREEN_WIDTH + 40:
            self.kill()


class Flea(pygame.sprite.Sprite):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.image = self.game.assets["flea"]
        self.rect = self.image.get_rect()
        self.rect.x = random.randrange(0, SCREEN_WIDTH - GRID_STEP, GRID_STEP)
        self.rect.y = -self.rect.height
        self.speed_y = 4.2 + min(2.2, self.game.level * 0.18)
        self.health = 2 + self.game.level // 6
        self.last_mushroom_y = self.rect.y

    def update(self):
        self.rect.y += self.speed_y
        if self.rect.y - self.last_mushroom_y >= GRID_STEP:
            if not pygame.sprite.spritecollide(self, self.game.mushrooms, False):
                mushroom = Mushroom(self.game, self.rect.x, int(self.rect.y))
                self.game.add_sprite(mushroom, 2, self.game.all_sprites, self.game.mushrooms)
            self.last_mushroom_y = self.rect.y
        if self.rect.top > SCREEN_HEIGHT:
            self.kill()

    def take_hit(self):
        self.health -= 1
        return self.health <= 0


class Scorpion(pygame.sprite.Sprite):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.image = self.game.assets["scorpion"]
        self.rect = self.image.get_rect()
        speed_base = 2.5 + min(2.0, self.game.level * 0.12)
        if random.choice([True, False]):
            self.rect.x = -self.rect.width
            self.speed_x = speed_base
        else:
            self.rect.x = SCREEN_WIDTH
            self.speed_x = -speed_base
        self.rect.y = random.randrange(52, PLAYER_ZONE_TOP - 120)

    def update(self):
        self.rect.x += self.speed_x
        collided = pygame.sprite.spritecollide(self, self.game.mushrooms, False)
        for mushroom in collided:
            mushroom.poison()
        if self.rect.right < -30 or self.rect.left > SCREEN_WIDTH + 30:
            self.kill()


class HiveMatriarch(pygame.sprite.Sprite):
    def __init__(self, game, profile):
        super().__init__()
        self.game = game
        self.profile = profile
        self.prime = profile.get("prime", False)
        self.base_image = self.game.assets["boss"]
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect(midtop=(SCREEN_WIDTH // 2, 42))
        self.max_health = profile["boss_health"]
        self.health = self.max_health
        self.speed_x = 2.2 + profile["boss_rank"] * 0.45
        self.float_phase = 0.0
        self.fire_timer = 75
        self.reinforcement_timer = 200
        self.damage_flash_timer = 0
        self.phase = 1
        self.prime_burst_used = False

    def update(self):
        self.float_phase += 0.06
        self.rect.x += int(round(self.speed_x))
        self.rect.y = 40 + int(math.sin(self.float_phase) * 10)
        if self.rect.left < 40 or self.rect.right > SCREEN_WIDTH - 40:
            self.speed_x *= -1

        if self.damage_flash_timer > 0:
            self.damage_flash_timer -= 1

        self.update_phase()
        self.refresh_image()

        self.fire_timer -= 1
        if self.fire_timer <= 0:
            self.fire_timer = max(28, 74 - self.phase * 10)
            self.fire_volley()

        self.reinforcement_timer -= 1
        if self.reinforcement_timer <= 0:
            self.reinforcement_timer = max(110, 200 - self.phase * 18)
            self.release_reinforcements()

    def update_phase(self):
        health_ratio = self.health / self.max_health
        if health_ratio <= 0.33:
            new_phase = 3
        elif health_ratio <= 0.66:
            new_phase = 2
        else:
            new_phase = 1
        if new_phase > self.phase:
            self.phase = new_phase
            self.game.play_sound(self.game.sounds["boss_phase"])
            if self.prime and self.phase == 3:
                self.speed_x = math.copysign(abs(self.speed_x) + 0.6, self.speed_x)
                self.reinforcement_timer = min(self.reinforcement_timer, 70)
                self.fire_prime_burst()
                self.game.trigger_shake(6, 22)
                self.game.trigger_flash(DANGER_COLOR, 135, 10)
                self.game.set_status_message("Matriarch Prime is breaking the trench.", 130)
            elif self.prime and self.phase == 2:
                self.game.set_status_message("Matriarch Prime is arming a trench break.", 120)
            else:
                self.game.set_status_message(f"Hive pressure rising. Phase {self.phase}.", 120)

    def refresh_image(self):
        self.image = self.base_image.copy()
        if self.phase >= 2:
            glow = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)
            glow.fill((255, 64, 96, 18 if self.phase == 2 else 32))
            self.image.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        if self.damage_flash_timer > 0:
            flash = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 115))
            self.image.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    def fire_volley(self):
        self.game.play_sound(self.game.sounds["boss_shot"])
        self.game.spawn_effect("hit", self.rect.midbottom)
        volley_size = 1 + self.phase
        center_bias = (self.game.player.rect.centerx - self.rect.centerx) / 110
        spread = 1.15
        for index in range(volley_size):
            offset = index - (volley_size - 1) / 2
            bolt = EnemyBolt(
                self.rect.centerx + int(offset * 18),
                self.rect.bottom - 4,
                velocity_x=center_bias + offset * spread,
                velocity_y=4.5 + self.phase * 0.8,
            )
            self.game.add_sprite(bolt, 5, self.game.all_sprites, self.game.enemy_projectiles)

    def fire_prime_burst(self):
        if self.prime_burst_used:
            return
        self.prime_burst_used = True
        self.game.play_sound(self.game.sounds["surge"])
        self.game.spawn_effect("explosion", self.rect.midbottom, large=False)
        volley_size = 7
        spread = 1.35
        for index in range(volley_size):
            offset = index - (volley_size - 1) / 2
            bolt = EnemyBolt(
                self.rect.centerx + int(offset * 20),
                self.rect.bottom - 2,
                velocity_x=offset * spread,
                velocity_y=5.1 + abs(offset) * 0.24,
            )
            self.game.add_sprite(bolt, 5, self.game.all_sprites, self.game.enemy_projectiles)

    def release_reinforcements(self):
        if self.phase >= 2 and len(self.game.spiders) < 2:
            spider = Spider(self.game)
            self.game.add_sprite(spider, 4, self.game.all_sprites, self.game.spiders)
        short_wave = max(4, 3 + self.phase + (1 if self.prime and self.phase == 3 else 0))
        spawn_x = GRID_STEP * random.randint(3, 10)
        self.game.spawn_centipede_wave(length=short_wave, start_x=spawn_x, start_y=GRID_STEP * random.randint(2, 4))
        if self.phase == 3 and len(self.game.scorpions) == 0:
            scorpion = Scorpion(self.game)
            self.game.add_sprite(scorpion, 4, self.game.all_sprites, self.game.scorpions)
        if self.prime and self.phase == 3:
            self.game.set_status_message("Matriarch Prime is flooding the trench.", 100)
        else:
            self.game.set_status_message("Matriarch releases reinforcements.", 90)

    def take_hit(self, damage):
        self.health -= damage
        self.damage_flash_timer = 4
        self.game.spawn_effect("hit", self.rect.center)
        self.game.play_sound(self.game.sounds["boss_hit"])
        if self.health <= 0:
            self.kill()
            return True
        return False


class Game:
    def __init__(self):
        self.review_mode = query_flag("review")
        self.autostart_requested = query_flag("autostart")
        requested_mode = query_param("mode", "").strip().lower()
        self.requested_mode_id = requested_mode if requested_mode in GAME_MODES else None

        if IS_WEB:
            web_debug_event(
                "swarmbreaker:web-boot",
                {
                    "bridge": WEB_BRIDGE_KIND,
                    "review": self.review_mode,
                    "autostart": self.autostart_requested,
                    "requestedMode": self.requested_mode_id,
                    "surface": list(screen.get_size()),
                },
            )
            render_boot_probe("Booting runtime", "Preparing browser review session.")

        if HEADLESS_SMOKE_TEST or self.review_mode:
            random.seed(7)

        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.font_cache = {}
        self.mode_ids = list(GAME_MODES.keys())
        self.level_theme = self.theme_for_level(1)
        render_boot_probe("Loading assets", "Building lightweight review sprites and effects.")
        self.assets = self.load_assets()
        if IS_WEB:
            web_debug_event(
                "swarmbreaker:web-assets",
                {
                    "hitFrames": len(self.assets["hit_frames"]),
                    "muzzleFrames": len(self.assets["muzzle_frames"]),
                    "explosionFrames": len(self.assets["explosion_frames"]),
                    "bossExplosionFrames": len(self.assets["boss_explosion_frames"]),
                },
            )
        render_boot_probe("Loading audio", "Preparing sound bank and scene backdrop.")
        self.sounds = self.load_sounds()
        self.static_background = self.build_background_surface()
        self.world_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.starfield = self.build_starfield()
        self.music_channel = pygame.mixer.Channel(0) if AUDIO_AVAILABLE else None
        self.current_music_key = None

        self.show_briefing = True
        self.screen_shake_enabled = True
        self.reduced_flash = False
        self.sound_enabled = AUDIO_AVAILABLE
        self.load_settings()

        self.high_score = self.load_high_score()
        self.current_mode_id = "classic"
        self.mode_best_score = 0
        self.profile = self.load_profile()
        self.sync_profile_high_score()
        self.run_unlocks = []
        self.run_record_highlights = []
        self.last_run_entry = None
        self.run_end_reason = "destroyed"
        self.run_recorded = False
        self.menu_return_phase = "title"
        self.title_menu_index = 0
        self.mode_select_index = 0
        self.records_mode_index = 0
        self.pause_menu_index = 0
        self.options_menu_index = 0
        self.game_over_menu_index = 0
        self.move_left = False
        self.move_right = False
        self.move_up = False
        self.move_down = False
        self.fire_held = False
        self.evaluate_unlocks(announce=False)
        self.mode_best_score = self.mode_record(self.current_mode_id)["best_score"]

        render_boot_probe("Preparing run state", "Syncing saves, unlocks, and menu state.")
        self.reset_world()
        self.reset_run_values()
        self.game_phase = "title"

        autostart_mode = self.current_mode_id
        if self.requested_mode_id and self.mode_is_unlocked(self.requested_mode_id):
            self.current_mode_id = self.requested_mode_id
            self.mode_best_score = self.mode_record(self.current_mode_id)["best_score"]
            autostart_mode = self.current_mode_id

        if HEADLESS_SMOKE_TEST:
            self.start_run(mode_id=autostart_mode, skip_briefing=True)
        elif self.autostart_requested:
            self.start_run(mode_id=autostart_mode, skip_briefing=True)

        if IS_WEB:
            web_debug_event(
                "swarmbreaker:web-init",
                {
                    "phase": self.game_phase,
                    "mode": self.current_mode_id,
                    "review": self.review_mode,
                    "autostart": self.autostart_requested,
                    "audio": AUDIO_AVAILABLE,
                    "surface": list(screen.get_size()),
                },
            )
            render_boot_probe("Ready", f"{self.current_mode()['label']} / {self.game_phase}")

    def load_assets(self):
        if IS_WEB and self.review_mode:
            web_debug_event("swarmbreaker:web-assets-mode", {"mode": "procedural_review"})
            return build_web_review_assets()
        frame_limit = 8 if IS_WEB or self.review_mode else None
        boss_frame_limit = 10 if IS_WEB or self.review_mode else None
        return {
            "player": load_image("assets/images/player.png", 1.35),
            "mushroom": load_image("assets/images/mushroom.png", 1.15),
            "centipede_head": load_image("assets/images/centipede_head.png", 1.25),
            "centipede_body": load_image("assets/images/centipede_body.png", 1.25),
            "spider": scale_surface(make_spider_surface(), 1.0),
            "flea": load_image("assets/images/flea.png", 1.2),
            "scorpion": load_image("assets/images/scorpion.png", 1.2),
            "hit_frames": load_sequence("assets/sounds/images/hit/hit_*.png", 0.6, max_frames=frame_limit),
            "muzzle_frames": load_sequence("assets/sounds/images/muzzle/muzzle2_*.png", 0.25, max_frames=frame_limit),
            "explosion_frames": load_sequence("assets/sounds/images/explosion/expl_07_*.png", 0.5, max_frames=frame_limit),
            "boss_explosion_frames": load_sequence("assets/sounds/images/explosion/expl_10_*.png", 0.55, max_frames=boss_frame_limit),
            "boss": make_boss_surface(),
        }

    def load_sounds(self):
        return {
            "shoot": load_sound_bank_entry("shoot"),
            "enemy_hit": load_sound_bank_entry("enemy_hit"),
            "player_die": load_sound_bank_entry("player_die"),
            "warning": load_sound_bank_entry("warning", [(220, 0.08, "triangle"), (165, 0.08, "triangle"), (220, 0.14, "triangle")], 0.32),
            "combo": load_sound_bank_entry("combo", [(440, 0.05, "square"), (554, 0.05, "square"), (659, 0.09, "square")], 0.22),
            "bonus": load_sound_bank_entry("bonus", [(392, 0.08, "triangle"), (523, 0.08, "triangle"), (784, 0.16, "triangle")], 0.28),
            "wave": load_sound_bank_entry("wave", [(262, 0.04, "square"), (330, 0.04, "square"), (392, 0.08, "triangle")], 0.22),
            "surge": load_sound_bank_entry("surge", [(262, 0.06, "square"), (196, 0.06, "square"), (262, 0.12, "triangle")], 0.28),
            "boss_shot": load_sound_bank_entry("boss_shot", [(185, 0.08, "square"), (147, 0.08, "square")], 0.25),
            "boss_hit": load_sound_bank_entry("boss_hit", [(780, 0.03, "triangle"), (620, 0.03, "triangle")], 0.18),
            "boss_die": load_sound_bank_entry("boss_die", [(220, 0.09, "triangle"), (185, 0.08, "triangle"), (147, 0.08, "triangle"), (110, 0.18, "triangle")], 0.34),
            "boss_phase": load_sound_bank_entry("boss_phase", [(220, 0.05, "square"), (277, 0.05, "square"), (185, 0.06, "triangle"), (110, 0.18, "triangle")], 0.26),
            "menu": load_sound_bank_entry("menu", [(440, 0.04, "triangle")], 0.12),
            "menu_confirm": load_sound_bank_entry("menu_confirm", [(392, 0.05, "triangle"), (523, 0.08, "triangle")], 0.18),
            "record": load_sound_bank_entry("record", [(523, 0.05, "triangle"), (659, 0.06, "triangle"), (784, 0.18, "triangle")], 0.24),
            "record_break": load_sound_bank_entry("record_break", [(587, 0.05, "triangle"), (784, 0.06, "triangle"), (988, 0.16, "triangle")], 0.26),
            "rank_up": load_sound_bank_entry("rank_up", [(392, 0.05, "triangle"), (523, 0.05, "triangle"), (659, 0.1, "triangle")], 0.24),
            "deploy": load_sound_bank_entry("deploy", [(196, 0.05, "triangle"), (262, 0.05, "triangle"), (330, 0.12, "triangle")], 0.22),
            "unlock": load_sound_bank_entry("unlock", [(330, 0.06, "triangle"), (392, 0.06, "triangle"), (523, 0.08, "triangle"), (659, 0.18, "triangle")], 0.24),
            "last_life": load_sound_bank_entry("last_life", [(196, 0.08, "triangle"), (165, 0.08, "triangle"), (147, 0.12, "triangle")], 0.26),
            "title_theme": load_sound_bank_entry(
                "title_theme",
                [
                    (262, 0.18, "triangle"), (330, 0.18, "triangle"), (392, 0.18, "triangle"), (523, 0.24, "triangle"),
                    (392, 0.14, "triangle"), (330, 0.14, "triangle"), (262, 0.22, "triangle"), (196, 0.22, "triangle"),
                ],
                0.12,
            ),
            "mode_select_theme": load_sound_bank_entry(
                "mode_select_theme",
                [
                    (220, 0.14, "triangle"), (277, 0.14, "triangle"), (330, 0.14, "triangle"), (440, 0.18, "triangle"),
                    (330, 0.12, "triangle"), (277, 0.12, "triangle"), (220, 0.18, "triangle"), (262, 0.18, "triangle"),
                ],
                0.1,
            ),
            "briefing_theme": load_sound_bank_entry(
                "briefing_theme",
                [
                    (196, 0.16, "triangle"), (247, 0.16, "triangle"), (294, 0.16, "triangle"), (330, 0.2, "triangle"),
                    (294, 0.16, "triangle"), (247, 0.16, "triangle"), (196, 0.22, "triangle"), (220, 0.22, "triangle"),
                ],
                0.1,
            ),
            "run_theme": load_sound_bank_entry(
                "run_theme",
                [
                    (220, 0.1, "square"), (220, 0.1, "square"), (330, 0.08, "square"), (392, 0.12, "triangle"),
                    (220, 0.1, "square"), (220, 0.1, "square"), (330, 0.08, "square"), (440, 0.14, "triangle"),
                    (262, 0.1, "square"), (262, 0.1, "square"), (349, 0.08, "square"), (392, 0.12, "triangle"),
                    (262, 0.1, "square"), (262, 0.1, "square"), (349, 0.08, "square"), (494, 0.16, "triangle"),
                ],
                0.1,
            ),
            "boss_theme": load_sound_bank_entry(
                "boss_theme",
                [
                    (147, 0.12, "square"), (147, 0.12, "square"), (175, 0.1, "square"), (196, 0.14, "triangle"),
                    (147, 0.12, "square"), (147, 0.12, "square"), (131, 0.1, "square"), (165, 0.16, "triangle"),
                    (98, 0.14, "triangle"), (147, 0.12, "square"), (196, 0.1, "square"), (220, 0.18, "triangle"),
                ],
                0.11,
            ),
            "surge_theme": load_sound_bank_entry(
                "surge_theme",
                [
                    (131, 0.1, "square"), (165, 0.1, "square"), (196, 0.12, "triangle"), (247, 0.14, "triangle"),
                    (147, 0.1, "square"), (196, 0.1, "square"), (262, 0.12, "triangle"), (294, 0.14, "triangle"),
                ],
                0.12,
            ),
        }

    def theme_for_level(self, level):
        return LEVEL_THEMES[(max(1, level) - 1) % len(LEVEL_THEMES)]

    def refresh_level_theme(self, level=None, preserve_star_positions=False):
        target_level = self.level if level is None else level
        self.level_theme = self.theme_for_level(target_level)
        self.static_background = self.build_background_surface()
        self.starfield = self.build_starfield(preserve_positions=preserve_star_positions)

    def build_background_surface(self):
        surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        theme = self.level_theme
        top = theme["top"]
        bottom = theme["bottom"]
        for y in range(SCREEN_HEIGHT):
            blend = y / SCREEN_HEIGHT
            color = (
                int(top[0] + (bottom[0] - top[0]) * blend),
                int(top[1] + (bottom[1] - top[1]) * blend),
                int(top[2] + (bottom[2] - top[2]) * blend),
            )
            pygame.draw.line(surface, color, (0, y), (SCREEN_WIDTH, y))

        player_band = pygame.Rect(0, PLAYER_ZONE_TOP, SCREEN_WIDTH, SCREEN_HEIGHT - PLAYER_ZONE_TOP)
        pygame.draw.rect(surface, theme["band"], player_band)
        for x in range(0, SCREEN_WIDTH, GRID_STEP * 2):
            pygame.draw.line(surface, theme["grid"], (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(60, SCREEN_HEIGHT, GRID_STEP * 2):
            pygame.draw.line(surface, theme["grid"], (0, y), (SCREEN_WIDTH, y), 1)

        pygame.draw.line(surface, theme["lane_edge"], (0, PLAYER_ZONE_TOP), (SCREEN_WIDTH, PLAYER_ZONE_TOP), 2)
        pygame.draw.line(surface, theme["lane_glow"], (0, PLAYER_ZONE_TOP + 1), (SCREEN_WIDTH, PLAYER_ZONE_TOP + 1), 1)

        for x in range(0, SCREEN_WIDTH, GRID_STEP * 4):
            pygame.draw.line(surface, theme["diagonal"], (x, PLAYER_ZONE_TOP), (x + GRID_STEP * 2, SCREEN_HEIGHT), 1)
        return surface

    def build_starfield(self, preserve_positions=False):
        theme = self.level_theme
        stars = []
        existing = getattr(self, "starfield", []) if preserve_positions else []
        for index in range(70):
            shade = random.randint(120, 235)
            if existing and index < len(existing):
                star = existing[index]
                x = star["x"]
                y = star["y"]
                speed = star["speed"]
                radius = star["radius"]
            else:
                x = random.uniform(0, SCREEN_WIDTH)
                y = random.uniform(0, PLAYER_ZONE_TOP - 40)
                speed = random.uniform(0.15, 0.55)
                radius = random.choice([1, 1, 2])
            stars.append(
                {
                    "x": x,
                    "y": y,
                    "speed": speed,
                    "radius": radius,
                    "color": (
                        clamp((shade + theme["title"][0]) // 2, 0, 255),
                        clamp((shade + theme["title"][1]) // 2, 0, 255),
                        clamp((shade + theme["title"][2]) // 2, 0, 255),
                    ),
                }
            )
        return stars

    def reset_world(self):
        self.all_sprites = pygame.sprite.LayeredUpdates()
        self.player_bullets = pygame.sprite.Group()
        self.enemy_projectiles = pygame.sprite.Group()
        self.effects = pygame.sprite.Group()
        self.mushrooms = pygame.sprite.Group()
        self.centipede_segments = pygame.sprite.Group()
        self.spiders = pygame.sprite.Group()
        self.fleas = pygame.sprite.Group()
        self.scorpions = pygame.sprite.Group()
        self.bosses = pygame.sprite.Group()
        self.floaters = pygame.sprite.Group()
        self.centipedes = []
        self.player = Player(self)
        self.add_sprite(self.player, 7, self.all_sprites)

    def reset_run_values(self):
        mode = self.current_mode()
        self.score = 0
        self.lives = mode["start_lives"]
        self.level = 1
        self.extra_life_step = mode["extra_life_step"]
        self.next_extra_life_score = mode["extra_life_step"]
        self.multiplier = 1
        self.combo_charge = 0
        self.combo_timer = 0
        self.best_multiplier = 1
        self.status_message = ""
        self.status_timer = 0
        self.wave_profile = None
        self.wave_intro_lines = []
        self.wave_intro_timer = 0
        self.spider_spawn_counter = 0
        self.scorpion_spawn_counter = 0
        self.centipede_move_counter = 0
        self.flash_alpha = 0
        self.flash_color = WHITE
        self.flash_decay = 0
        self.shake_frames = 0
        self.shake_strength = 0
        self.play_frames = 0
        self.mode_timer_frames = int(mode["time_limit_seconds"] * 60) if mode["time_limit_seconds"] else None
        self.timer_warning_stage = 0
        self.mode_best_score = self.mode_record(self.current_mode_id)["best_score"]
        self.mode_best_score_start = self.mode_best_score
        self.run_unlocks = []
        self.run_record_highlights = []
        self.last_run_entry = None
        self.run_end_reason = "destroyed"
        self.run_recorded = False
        self.score_record_announced = False
        self.stats = {
            "segments_destroyed": 0,
            "mushrooms_cleared": 0,
            "specials_destroyed": 0,
            "bosses_destroyed": 0,
            "waves_cleared": 0,
        }
        self.tutorial_notice_seen = False
        self.rank_label = "C"
        self.live_rank_label = "D"

    def default_mode_record(self):
        return {
            "runs": 0,
            "best_score": 0,
            "best_rank": "D",
            "best_wave": 0,
            "best_multiplier": 1,
            "best_time_seconds": 0,
            "top_runs": [],
        }

    def default_profile(self):
        return {
            "career_high_score": 0,
            "unlocked_modes": [mode_id for mode_id in self.mode_ids if GAME_MODES[mode_id]["unlock"] is None],
            "lifetime": {
                "runs": 0,
                "time_seconds": 0,
                "score_total": 0,
                "segments_destroyed": 0,
                "mushrooms_cleared": 0,
                "specials_destroyed": 0,
                "bosses_destroyed": 0,
                "waves_cleared": 0,
            },
            "mode_records": {mode_id: self.default_mode_record() for mode_id in self.mode_ids},
            "recent_runs": [],
        }

    def normalize_run_entry(self, entry, fallback_mode_id="classic"):
        if not isinstance(entry, dict):
            return None
        mode_id = entry.get("mode_id", fallback_mode_id)
        if mode_id not in GAME_MODES:
            return None
        rank_label = entry.get("rank", "D")
        if rank_label not in RANK_VALUES:
            rank_label = "D"
        return {
            "mode_id": mode_id,
            "score_version": int(entry.get("score_version", SCORING_MODEL_VERSION)),
            "score": int(entry.get("score", 0)),
            "wave_reached": int(entry.get("wave_reached", 1)),
            "waves_cleared": int(entry.get("waves_cleared", 0)),
            "bosses_destroyed": int(entry.get("bosses_destroyed", 0)),
            "best_multiplier": int(entry.get("best_multiplier", 1)),
            "duration_seconds": int(entry.get("duration_seconds", 0)),
            "lives_remaining": int(entry.get("lives_remaining", 0)),
            "result": entry.get("result", "destroyed"),
            "rank": rank_label,
            "ended_at": str(entry.get("ended_at", "")),
        }

    def load_profile(self):
        data = None
        if IS_WEB:
            raw = web_storage_get("profile")
            if raw:
                try:
                    data = json.loads(raw)
                except (ValueError, TypeError, json.JSONDecodeError):
                    data = None
        else:
            for path in (PROFILE_PATH, LEGACY_PROFILE_PATH):
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        break
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue

        profile = self.default_profile()
        if not isinstance(data, dict):
            return profile

        profile["career_high_score"] = int(data.get("career_high_score", 0))

        lifetime = data.get("lifetime", {})
        if isinstance(lifetime, dict):
            for key in profile["lifetime"]:
                profile["lifetime"][key] = int(lifetime.get(key, profile["lifetime"][key]))

        unlocked_modes = data.get("unlocked_modes", [])
        if isinstance(unlocked_modes, list):
            unlocked = set(profile["unlocked_modes"])
            unlocked.update(mode_id for mode_id in unlocked_modes if mode_id in GAME_MODES)
            profile["unlocked_modes"] = [mode_id for mode_id in self.mode_ids if mode_id in unlocked]

        mode_records = data.get("mode_records", {})
        if isinstance(mode_records, dict):
            for mode_id in self.mode_ids:
                saved_record = mode_records.get(mode_id, {})
                if not isinstance(saved_record, dict):
                    continue
                record = profile["mode_records"][mode_id]
                record["runs"] = int(saved_record.get("runs", record["runs"]))
                record["best_score"] = int(saved_record.get("best_score", record["best_score"]))
                record["best_rank"] = better_rank(record["best_rank"], saved_record.get("best_rank", record["best_rank"]))
                record["best_wave"] = int(saved_record.get("best_wave", record["best_wave"]))
                record["best_multiplier"] = int(saved_record.get("best_multiplier", record["best_multiplier"]))
                record["best_time_seconds"] = int(saved_record.get("best_time_seconds", record["best_time_seconds"]))
                top_runs = []
                for entry in saved_record.get("top_runs", []):
                    normalized = self.normalize_run_entry(entry, fallback_mode_id=mode_id)
                    if normalized:
                        top_runs.append(normalized)
                record["top_runs"] = sorted(top_runs, key=self.record_sort_key)[:TOP_RUNS_PER_MODE]

        recent_runs = []
        for entry in data.get("recent_runs", []):
            normalized = self.normalize_run_entry(entry)
            if normalized:
                recent_runs.append(normalized)
        profile["recent_runs"] = recent_runs[:RECENT_RUN_LIMIT]
        return profile

    def save_profile(self):
        if IS_WEB:
            web_storage_set("profile", json.dumps(self.profile))
            return
        if not ensure_data_dir():
            return
        try:
            with open(PROFILE_PATH, "w", encoding="utf-8") as file:
                json.dump(self.profile, file, indent=2)
        except OSError:
            pass

    def sync_profile_high_score(self):
        career_high = max(self.high_score, int(self.profile.get("career_high_score", 0)))
        classic_record = self.mode_record("classic")
        if classic_record["best_score"] == 0 and career_high > 0:
            classic_record["best_score"] = career_high
            classic_record["best_rank"] = better_rank(classic_record["best_rank"], "C")
        for mode_id in self.mode_ids:
            career_high = max(career_high, self.mode_record(mode_id)["best_score"])
        self.profile["career_high_score"] = career_high
        self.high_score = career_high

    def current_mode(self):
        return GAME_MODES[self.current_mode_id]

    def mode_record(self, mode_id):
        return self.profile["mode_records"][mode_id]

    def mode_is_unlocked(self, mode_id):
        if GAME_MODES[mode_id]["unlock"] is None:
            return True
        return mode_id in self.profile["unlocked_modes"]

    def unlock_progress(self, mode_id):
        rule = GAME_MODES[mode_id]["unlock"]
        if not rule:
            return (1, 1)
        if rule["type"] == "bosses_destroyed":
            current = self.profile["lifetime"]["bosses_destroyed"]
            return (current, int(rule["value"]))
        return (0, int(rule.get("value", 1)))

    def unlock_requirement_text(self, mode_id):
        rule = GAME_MODES[mode_id]["unlock"]
        if not rule:
            return "Available from the start."
        return rule["label"]

    def unlock_progress_text(self, mode_id):
        current, target = self.unlock_progress(mode_id)
        if GAME_MODES[mode_id]["unlock"] is None:
            return "Ready"
        if self.mode_is_unlocked(mode_id):
            return "Unlocked"
        return f"{current}/{target} progress"

    def evaluate_unlocks(self, announce=True):
        unlocked = set(self.profile["unlocked_modes"])
        new_unlocks = []
        for mode_id in self.mode_ids:
            rule = GAME_MODES[mode_id]["unlock"]
            if rule is None:
                unlocked.add(mode_id)
                continue
            current, target = self.unlock_progress(mode_id)
            if current >= target and mode_id not in unlocked:
                unlocked.add(mode_id)
                new_unlocks.append(mode_id)
        self.profile["unlocked_modes"] = [mode_id for mode_id in self.mode_ids if mode_id in unlocked]

        if announce and new_unlocks:
            self.play_sound(self.sounds["unlock"])
            for mode_id in new_unlocks:
                self.run_unlocks.append(f"{GAME_MODES[mode_id]['label']} unlocked.")
        return new_unlocks

    def record_sort_key(self, entry):
        result_penalty = {"victory": 0, "cleared": 0, "timeout": 1, "destroyed": 1, "abandoned": 2}.get(entry["result"], 2)
        return (
            -int(entry["score"]),
            -int(entry["waves_cleared"]),
            -int(entry["bosses_destroyed"]),
            -int(entry["best_multiplier"]),
            result_penalty,
            int(entry["duration_seconds"]),
            entry.get("ended_at", ""),
        )

    def load_high_score(self):
        if IS_WEB:
            raw = web_storage_get("high_score")
            if raw:
                try:
                    return int(json.loads(raw).get("high_score", 0))
                except (ValueError, TypeError, json.JSONDecodeError):
                    return 0
            return 0
        for path in (HIGH_SCORE_PATH, LEGACY_HIGH_SCORE_PATH):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    return int(json.load(file).get("high_score", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return 0

    def save_high_score(self):
        payload = {"high_score": int(max(self.high_score, self.score))}
        if IS_WEB:
            web_storage_set("high_score", json.dumps(payload))
            return
        if not ensure_data_dir():
            return
        try:
            with open(HIGH_SCORE_PATH, "w", encoding="utf-8") as file:
                json.dump(payload, file)
        except OSError:
            pass

    def load_settings(self):
        data = None
        if IS_WEB:
            raw = web_storage_get("settings")
            if raw:
                try:
                    data = json.loads(raw)
                except (ValueError, TypeError, json.JSONDecodeError):
                    data = None
        else:
            for path in (SETTINGS_PATH, LEGACY_SETTINGS_PATH):
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        break
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        if data is None:
            return

        self.show_briefing = bool(data.get("show_briefing", self.show_briefing))
        self.screen_shake_enabled = bool(data.get("screen_shake_enabled", self.screen_shake_enabled))
        self.reduced_flash = bool(data.get("reduced_flash", self.reduced_flash))
        if AUDIO_AVAILABLE:
            self.sound_enabled = bool(data.get("sound_enabled", self.sound_enabled))

    def save_settings(self):
        payload = {
            "show_briefing": self.show_briefing,
            "screen_shake_enabled": self.screen_shake_enabled,
            "reduced_flash": self.reduced_flash,
            "sound_enabled": self.sound_enabled if AUDIO_AVAILABLE else False,
        }
        if IS_WEB:
            web_storage_set("settings", json.dumps(payload))
            return
        if not ensure_data_dir():
            return
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
        except OSError:
            pass

    def get_font(self, size, bold=False):
        key = (size, bold)
        if key not in self.font_cache:
            self.font_cache[key] = pygame.font.SysFont("arial", size, bold=bold)
        return self.font_cache[key]

    def render_text(self, text, size, color=WHITE, bold=False):
        return self.get_font(size, bold=bold).render(text, True, color)

    def draw_text(self, surface, text, size, x, y, color=WHITE, align="midtop", bold=False):
        text_surface = self.render_text(text, size, color, bold=bold)
        shadow_surface = self.render_text(text, size, (0, 0, 0), bold=bold)
        shadow_rect = shadow_surface.get_rect()
        setattr(shadow_rect, align, (x + 2, y + 2))
        surface.blit(shadow_surface, shadow_rect)
        rect = text_surface.get_rect()
        setattr(rect, align, (x, y))
        surface.blit(text_surface, rect)
        return rect

    def draw_wrapped_text(self, surface, text, size, rect, color=WHITE, bold=False, line_gap=4, max_bottom=None):
        font = self.get_font(size, bold=bold)
        y = rect.y
        line_height = font.get_linesize() + line_gap

        def room_for_line():
            if max_bottom is None:
                return True
            return y + font.get_linesize() <= max_bottom

        for paragraph in text.splitlines():
            words = paragraph.split()
            if not words:
                if room_for_line():
                    y += line_height
                continue
            current_line = words[0]
            for word in words[1:]:
                test_line = f"{current_line} {word}"
                if font.size(test_line)[0] <= rect.width:
                    current_line = test_line
                else:
                    if not room_for_line():
                        return y
                    self.draw_text(surface, current_line, size, rect.x, y, color, align="topleft", bold=bold)
                    y += line_height
                    current_line = word
            if not room_for_line():
                return y
            self.draw_text(surface, current_line, size, rect.x, y, color, align="topleft", bold=bold)
            y += line_height
        return y

    def draw_panel(self, surface, rect):
        pygame.draw.rect(surface, PANEL_COLOR, rect, border_radius=18)
        pygame.draw.rect(surface, PANEL_BORDER, rect, width=2, border_radius=18)

    def draw_meter(self, surface, rect, ratio, fill_color, empty_color=(18, 26, 38)):
        pygame.draw.rect(surface, empty_color, rect, border_radius=10)
        inner = rect.inflate(-2, -2)
        inner.width = max(0, int(inner.width * clamp(ratio, 0, 1)))
        if inner.width > 0:
            pygame.draw.rect(surface, fill_color, inner, border_radius=9)
        pygame.draw.rect(surface, PANEL_BORDER, rect, width=1, border_radius=10)

    def add_sprite(self, sprite, layer, *groups):
        self.all_sprites.add(sprite, layer=layer)
        for group in groups:
            if group is not self.all_sprites:
                group.add(sprite)

    def spawn_effect(self, effect_type, position, large=False):
        if effect_type == "muzzle":
            frames = self.assets["muzzle_frames"]
            step = 0.75
        elif effect_type == "hit":
            frames = self.assets["hit_frames"]
            step = 0.7
        else:
            frames = self.assets["boss_explosion_frames"] if large else self.assets["explosion_frames"]
            step = 0.48

        if not frames:
            return
        effect = AnimatedEffect(frames, position, step)
        self.add_sprite(effect, 8, self.all_sprites, self.effects)

    def spawn_floating_text(self, text, position, color=WHITE, size=18):
        floater = FloatingText(self, text, position, color=color, size=size)
        self.add_sprite(floater, 9, self.all_sprites, self.floaters)

    def play_sound(self, sound):
        if self.sound_enabled:
            sound.play()

    def set_status_message(self, message, frames=120):
        self.status_message = message
        self.status_timer = frames

    def trigger_flash(self, color, alpha, decay):
        if self.reduced_flash:
            alpha = int(alpha * 0.45)
        self.flash_color = color
        self.flash_alpha = max(self.flash_alpha, alpha)
        self.flash_decay = max(1, decay)

    def trigger_shake(self, strength, frames):
        if not self.screen_shake_enabled:
            return
        self.shake_strength = max(self.shake_strength, strength)
        self.shake_frames = max(self.shake_frames, frames)

    def add_points(self, points):
        previous_rank = self.rank_for_score(self.rating_score())
        self.score += int(points)
        self.high_score = max(self.high_score, self.score)
        self.mode_best_score = max(self.mode_best_score, self.score)
        if not self.score_record_announced and self.mode_best_score_start > 0 and self.score >= self.mode_best_score_start:
            self.score_record_announced = True
            self.play_sound(self.sounds["record_break"])
            self.set_status_message("New mode record pace.", 140)
            self.spawn_floating_text("Record pace!", (SCREEN_WIDTH // 2, 96), SUCCESS_COLOR, 22)
        while self.score >= self.next_extra_life_score:
            self.lives += 1
            self.next_extra_life_score += self.extra_life_step
            self.play_sound(self.sounds["bonus"])
            self.set_status_message("Bonus life awarded.", 150)
            self.spawn_floating_text("+1 LIFE", (SCREEN_WIDTH // 2, 86), SUCCESS_COLOR, 24)
        current_rank = self.rank_for_score(self.rating_score())
        self.live_rank_label = current_rank
        if rank_value(current_rank) > rank_value(previous_rank):
            self.live_rank_label = current_rank
            self.play_sound(self.sounds["rank_up"])
            self.set_status_message(f"Rank up: {current_rank}.", 120)
            self.spawn_floating_text(f"Rank {current_rank}", (SCREEN_WIDTH // 2, 118), TITLE_COLOR, 22)

    def reset_combo(self, announce=False):
        if announce and (self.multiplier > 1 or self.combo_charge > 0):
            self.set_status_message("Multiplier link lost.", 90)
        self.multiplier = 1
        self.combo_charge = 0
        self.combo_timer = 0

    def register_combo_kill(self, base_points, position, label):
        awarded = base_points * self.multiplier
        self.add_points(awarded)
        self.combo_timer = 240
        self.combo_charge += 1
        threshold = 2 + self.multiplier
        self.spawn_floating_text(
            f"{label} +{awarded}",
            position,
            TITLE_COLOR if self.multiplier > 1 else WARNING_COLOR,
        )
        if self.combo_charge >= threshold and self.multiplier < 6:
            self.combo_charge = 0
            self.multiplier += 1
            self.best_multiplier = max(self.best_multiplier, self.multiplier)
            self.play_sound(self.sounds["combo"])
            self.set_status_message(f"Multiplier locked at {self.multiplier}x.", 120)
            self.spawn_floating_text(f"{self.multiplier}x", (position[0], position[1] - 20), SUCCESS_COLOR, 24)

    def build_mushroom_field(self, count=None):
        if count is None:
            count = self.current_mode()["mushroom_count"]
        positions = set()
        while len(positions) < count:
            positions.add(
                (
                    random.randrange(0, SCREEN_WIDTH - GRID_STEP, GRID_STEP),
                    random.randrange(60, PLAYER_ZONE_TOP - GRID_STEP, GRID_STEP),
                )
            )
        for x, y in positions:
            mushroom = Mushroom(self, x, y)
            self.add_sprite(mushroom, 2, self.all_sprites, self.mushrooms)

    def stabilize_mushroom_field(self):
        current_positions = {(m.rect.x, m.rect.y) for m in self.mushrooms}
        desired_count = max(36, self.current_mode()["mushroom_count"] - 6)
        repair_candidates = list(self.mushrooms)
        random.shuffle(repair_candidates)
        for mushroom in repair_candidates[: max(4, len(repair_candidates) // 5)]:
            mushroom.health = 4
            mushroom.poisoned = False
            mushroom.refresh_image()

        while len(current_positions) < desired_count:
            position = (
                random.randrange(0, SCREEN_WIDTH - GRID_STEP, GRID_STEP),
                random.randrange(60, PLAYER_ZONE_TOP - GRID_STEP, GRID_STEP),
            )
            if position in current_positions:
                continue
            current_positions.add(position)
            mushroom = Mushroom(self, *position)
            self.add_sprite(mushroom, 2, self.all_sprites, self.mushrooms)

    def seed_poisoned_mushrooms(self, ratio=None, minimum=0):
        if ratio is None:
            ratio = self.current_mode()["poison_seed"]
        if ratio <= 0 or not self.mushrooms:
            return 0
        available = [mushroom for mushroom in self.mushrooms if not mushroom.poisoned]
        if not available:
            return 0
        poison_count = max(minimum, int(len(self.mushrooms) * ratio))
        poison_count = min(poison_count, len(available))
        if poison_count <= 0:
            return 0
        for mushroom in random.sample(available, poison_count):
            mushroom.poison()
        return poison_count

    def apply_mode_field_state(self):
        mode = self.current_mode()
        ratio = mode["poison_seed"]
        if self.current_mode_id == "toxic_gauntlet":
            ratio = min(0.42, ratio + max(0, self.level - 1) * 0.025)
        minimum = 2 if self.current_mode_id == "boss_rush" else 0
        poisoned_count = self.seed_poisoned_mushrooms(ratio, minimum=minimum)
        if poisoned_count and self.current_mode_id == "toxic_gauntlet":
            self.set_status_message("Toxic caps are flooding the lane.", 120)

    def clear_enemies(self, include_mushrooms=False):
        groups = [
            self.player_bullets,
            self.enemy_projectiles,
            self.centipede_segments,
            self.spiders,
            self.fleas,
            self.scorpions,
            self.bosses,
            self.effects,
            self.floaters,
        ]
        if include_mushrooms:
            groups.append(self.mushrooms)
        for group in groups:
            for sprite in list(group):
                sprite.kill()
        self.centipedes = []

    def spawn_centipede_wave(self, length=12, start_x=None, start_y=GRID_STEP * 2):
        start_x = SCREEN_WIDTH // 2 if start_x is None else start_x
        new_centipede = []
        for index in range(length):
            x = start_x - index * GRID_STEP
            y = start_y
            segment = CentipedeSegment(self, x, y, is_head=index == 0)
            self.add_sprite(segment, 4, self.all_sprites, self.centipede_segments)
            new_centipede.append(segment)
        self.centipedes.append(new_centipede)

    def wave_name_for_level(self, level):
        if self.current_mode_id == "time_attack":
            labels = [
                ("Hot Drop", "The strike window is open. Score fast and keep the clock alive."),
                ("Fast Break", "The route is tightening and the board wants speed."),
                ("Kill Chain", "Pressure rises hard. Keep the timer bought in blood."),
                ("Queen Clock", "Matriarch pressure is spiking against the timer."),
            ]
        elif self.current_mode_id == "toxic_gauntlet":
            labels = [
                ("Venom Breach", "Poison caps are spreading before the trench can stabilise."),
                ("Dive Net", "Scorpions are stitching toxic routes through the canopy."),
                ("Rot Front", "The lower lane is turning into a death funnel."),
                ("Matriarch Rot", "The brood queen is riding the venom surge."),
            ]
        elif self.current_mode_id == "boss_rush":
            labels = [
                ("Queen Break One", "Immediate boss contact with no scouting buffer."),
                ("Queen Break Two", "Support swarms are reinforcing the matriarch lane."),
                ("Queen Break Three", "The trench is fighting elite pressure back to back."),
                ("Queen Break Four", "Another queen is dropping before the dust settles."),
            ]
        else:
            labels = [
                ("Signal Breach", "Scout swarm spilling through the orchard lattice."),
                ("Toxin Sweep", "Scorpions are marking dive lanes with venom."),
                ("Skitter Front", "Flea rain and fast flankers crowd the trench."),
                ("Matriarch Alarm", "The brood signal is cresting. Expect a boss event."),
            ]
        return labels[(level - 1) % len(labels)]

    def build_wave_profile(self, level):
        mode = self.current_mode()
        boss_interval = mode["boss_interval"] or BOSS_WAVE_INTERVAL
        boss_wave = boss_interval == 1 or level % boss_interval == 0

        if boss_wave:
            boss_rank = max(1, level if boss_interval == 1 else level // boss_interval)
            title, subtitle = self.wave_name_for_level(level)
            prime = boss_rank >= 3
            return {
                "kind": "boss",
                "title": title,
                "subtitle": subtitle,
                "boss_rank": boss_rank,
                "boss_name": "Matriarch Prime" if prime else "Hive Matriarch",
                "prime": prime,
                "boss_health": max(18, int((34 + boss_rank * 14) * mode["boss_health_scale"])),
                "centipede_delay": max(1, 4 - boss_rank // 2 + mode["centipede_delay_bonus"]),
                "boss_support_length": mode["boss_support_length"] + min(4, level // 2) + (1 if prime else 0),
                "boss_prime_bonus": 500 * boss_rank if prime else 0,
            }

        if level >= 6 and level % 5 == 0:
            title = "Overrun Surge"
            subtitle = "Swarm density spikes. Hold the trench through the break."
            surge_stage = max(0, (level - 10) // 5)
            spider_limit = max(2, 2 + surge_stage + level // 6 + mode["spider_limit_bonus"])
            return {
                "kind": "surge",
                "title": title,
                "subtitle": subtitle,
                "centipede_length": min(18 + level // 2 + surge_stage + mode["centipede_length_bonus"], 24),
                "secondary_wave_count": max(1, 1 + mode["secondary_wave_bonus"] + min(1, surge_stage)),
                "spider_rate": max(75, int((230 - level * 10 - surge_stage * 18) * mode["spider_rate_scale"])),
                "spider_limit": spider_limit,
                "scorpion_rate": max(105, int((470 - level * 18 - surge_stage * 24) * mode["scorpion_rate_scale"])),
                "flea_threshold": max(2, 4 + level // 3 + mode["flea_threshold_bonus"]),
                "centipede_delay": max(1, 4 - level // 5 + mode["centipede_delay_bonus"]),
                "surge_bonus": 190 * level + 300 * (surge_stage + 1),
                "surge_support_length": max(6, min(10, 6 + surge_stage + mode["secondary_wave_bonus"] + level // 8)),
            }

        title, subtitle = self.wave_name_for_level(level)
        spider_limit = max(1, 1 + level // 6 + mode["spider_limit_bonus"])
        if level < 3:
            spider_limit = 0
        return {
            "kind": "swarm",
            "title": title,
            "subtitle": subtitle,
            "centipede_length": min(12 + level + mode["centipede_length_bonus"], 20),
            "secondary_wave_count": max(0, (1 if level >= 3 else 0) + mode["secondary_wave_bonus"]),
            "spider_rate": max(85, int((230 - level * 12) * mode["spider_rate_scale"])),
            "spider_limit": spider_limit,
            "scorpion_rate": max(110, int((560 - level * 28) * mode["scorpion_rate_scale"])),
            "flea_threshold": max(2, 4 + level // 2 + mode["flea_threshold_bonus"]),
            "centipede_delay": max(1, 5 - level // 3 + mode["centipede_delay_bonus"]),
        }

    def start_run(self, mode_id=None, skip_briefing=False):
        if mode_id is not None:
            self.current_mode_id = mode_id
            self.mode_select_index = self.mode_ids.index(mode_id)
            self.records_mode_index = self.mode_select_index
        self.reset_world()
        self.reset_run_values()
        self.refresh_level_theme(level=1, preserve_star_positions=False)
        self.player.reset_position()
        self.build_mushroom_field()
        self.apply_mode_field_state()
        if skip_briefing or not self.show_briefing:
            self.begin_wave(1)
        else:
            self.game_phase = "briefing"

    def begin_wave(self, level):
        self.level = level
        self.wave_profile = self.build_wave_profile(level)
        self.refresh_level_theme(level=level, preserve_star_positions=True)
        self.spider_spawn_counter = 0
        self.scorpion_spawn_counter = 0
        self.centipede_move_counter = 0
        self.reset_combo()
        self.wave_intro_lines = [
            f"Wave {self.level}  |  {self.wave_profile['title']}",
            self.wave_profile["subtitle"],
            self.current_mode()["tagline"],
        ]
        if self.wave_profile["kind"] == "boss":
            if self.wave_profile.get("prime"):
                self.wave_intro_lines[1] = "Matriarch Prime is inbound."
                self.wave_intro_lines[2] = "Destroy her to win the run."
            else:
                self.wave_intro_lines[1] = "The Hive Matriarch is inbound."
                self.wave_intro_lines[2] = "Break this queen. The run ends at Matriarch Prime."
        elif self.wave_profile["kind"] == "surge":
            self.wave_intro_lines[1] = "Warning: overrun surge inbound."
            self.wave_intro_lines[2] = f"Hold for a surge payout worth {self.wave_profile['surge_bonus']} points."
        self.wave_intro_timer = 110 if not HEADLESS_SMOKE_TEST else 3
        self.game_phase = "wave_intro"
        if self.wave_profile["kind"] == "boss":
            self.play_sound(self.sounds["warning"])
            self.trigger_flash(DANGER_COLOR, 95, 11)
        elif self.wave_profile["kind"] == "surge":
            self.play_sound(self.sounds["surge"])
            self.trigger_flash(WARNING_COLOR, 95, 11)
        else:
            self.play_sound(self.sounds["wave"])
            self.trigger_flash(TITLE_COLOR, 75, 10)

    def deploy_current_wave(self):
        self.clear_enemies(include_mushrooms=False)
        self.player.reset_position()
        if self.wave_profile["kind"] == "boss":
            boss = HiveMatriarch(self, self.wave_profile)
            self.add_sprite(boss, 5, self.all_sprites, self.bosses)
            support_length = self.wave_profile.get("boss_support_length", 0)
            if support_length:
                self.spawn_centipede_wave(
                    length=support_length,
                    start_x=SCREEN_WIDTH - GRID_STEP * random.randint(4, 8),
                    start_y=GRID_STEP * random.randint(2, 4),
                )
            self.set_status_message(f"{self.wave_profile.get('boss_name', 'Hive Matriarch')} entering the trench.", 150)
            if self.wave_profile.get("prime"):
                self.play_sound(self.sounds["boss_phase"])
                self.trigger_shake(6, 22)
                self.trigger_flash(DANGER_COLOR, 145, 12)
            else:
                self.play_sound(self.sounds["warning"])
                self.trigger_shake(4, 18)
                self.trigger_flash(DANGER_COLOR, 120, 12)
        elif self.wave_profile["kind"] == "surge":
            self.spawn_centipede_wave(self.wave_profile["centipede_length"])
            for wave_index in range(self.wave_profile["secondary_wave_count"] + 1):
                self.spawn_centipede_wave(
                    length=max(6, self.wave_profile["centipede_length"] - 4 - wave_index),
                    start_x=SCREEN_WIDTH - GRID_STEP * (4 + wave_index * 3),
                    start_y=GRID_STEP * (3 + min(wave_index, 3)),
                )
            support_length = self.wave_profile.get("surge_support_length", 0)
            if support_length:
                self.spawn_centipede_wave(
                    length=support_length,
                    start_x=GRID_STEP * random.randint(2, 9),
                    start_y=GRID_STEP * random.randint(3, 5),
                )
            if len(self.spiders) < 2:
                spider = Spider(self)
                self.add_sprite(spider, 4, self.all_sprites, self.spiders)
            if len(self.scorpions) == 0:
                scorpion = Scorpion(self)
                self.add_sprite(scorpion, 4, self.all_sprites, self.scorpions)
            self.set_status_message("Overrun surge underway. Clear the trench.", 170)
            self.play_sound(self.sounds["surge"])
            self.trigger_shake(6, 20)
            self.trigger_flash(WARNING_COLOR, 140, 12)
        else:
            self.spawn_centipede_wave(self.wave_profile["centipede_length"])
            for wave_index in range(self.wave_profile["secondary_wave_count"]):
                self.spawn_centipede_wave(
                    length=max(5, self.wave_profile["centipede_length"] - 5 - wave_index),
                    start_x=SCREEN_WIDTH - GRID_STEP * (4 + wave_index * 3),
                    start_y=GRID_STEP * (4 + min(wave_index, 2)),
                )
            self.set_status_message(f"Wave {self.level} deployed. Hold the line.", 150)
            self.play_sound(self.sounds["deploy"])
        self.game_phase = "playing"

    def complete_wave(self):
        self.stats["waves_cleared"] += 1
        if self.current_mode_id == "boss_rush":
            clear_bonus = int(160 * self.level)
        elif self.current_mode_id in ("time_attack", "toxic_gauntlet"):
            clear_bonus = int(135 * self.level)
        else:
            clear_bonus = 120 * self.level
        self.add_points(clear_bonus)
        self.spawn_floating_text(f"Wave clear +{clear_bonus}", (SCREEN_WIDTH // 2, PLAYER_ZONE_TOP - 34), SUCCESS_COLOR, 22)
        self.play_sound(self.sounds["wave"])
        if self.wave_profile["kind"] == "boss":
            prime_bonus = int(self.wave_profile.get("boss_prime_bonus", 0))
            if prime_bonus:
                self.add_points(prime_bonus)
                self.spawn_floating_text(f"Prime collapse +{prime_bonus}", (SCREEN_WIDTH // 2, PLAYER_ZONE_TOP - 8), TITLE_COLOR, 22)
                self.play_sound(self.sounds["bonus"])
        if self.wave_profile["kind"] == "surge":
            surge_bonus = int(self.wave_profile.get("surge_bonus", 0))
            if surge_bonus:
                self.add_points(surge_bonus)
                self.spawn_floating_text(f"Surge bonus +{surge_bonus}", (SCREEN_WIDTH // 2, PLAYER_ZONE_TOP - 8), TITLE_COLOR, 22)
                self.play_sound(self.sounds["surge"])
        bonus_seconds = 0
        granted_seconds = 0
        if self.mode_timer_frames is not None:
            bonus_seconds = self.current_mode()["time_bonus_boss"] if self.wave_profile["kind"] == "boss" else self.current_mode()["time_bonus_wave"]
        if bonus_seconds:
            granted_seconds = self.award_time_bonus(bonus_seconds)
        finale = self.wave_profile["kind"] == "boss" and self.wave_profile.get("prime")
        if finale:
            message = "Matriarch Prime broken. Sector Seven holds."
            duration = 180
        elif self.wave_profile["kind"] == "boss":
            message = "Hive Matriarch broken."
            duration = 150
        elif self.wave_profile["kind"] == "surge":
            message = f"Overrun surge broken. Banked +{self.wave_profile['surge_bonus']}."
            duration = 160
        else:
            message = f"Wave {self.level} neutralised."
            duration = 120
        if granted_seconds:
            message = f"{message} Clock +{granted_seconds}s."
        elif bonus_seconds:
            message = f"{message} Strike clock capped."
        self.set_status_message(message, duration)
        if finale:
            self.enter_victory()
            return
        self.stabilize_mushroom_field()
        self.apply_mode_field_state()
        self.begin_wave(self.level + 1)

    def reset_after_life(self):
        self.clear_enemies()
        self.stabilize_mushroom_field()
        self.apply_mode_field_state()
        self.player.reset_position()
        self.reset_combo()
        self.game_phase = "wave_intro"
        self.wave_intro_timer = 70 if not HEADLESS_SMOKE_TEST else 3
        self.wave_intro_lines = [
            "Defence line restored.",
            f"Return to Wave {self.level} and break the push.",
            "Press Enter to redeploy immediately.",
        ]

    def award_time_bonus(self, seconds):
        if self.mode_timer_frames is None or seconds <= 0:
            return 0
        before = self.mode_timer_frames
        cap_seconds = self.current_mode()["time_cap_seconds"] or seconds
        new_total = before + seconds * 60
        self.mode_timer_frames = min(new_total, cap_seconds * 60)
        granted_frames = self.mode_timer_frames - before
        if granted_frames <= 0:
            self.spawn_floating_text("Clock capped", (SCREEN_WIDTH // 2, 84), WARNING_COLOR, 22)
            return 0
        granted_seconds = granted_frames // 60
        label = f"+{granted_seconds}s" if granted_seconds == seconds else f"+{granted_seconds}s cap"
        self.spawn_floating_text(label, (SCREEN_WIDTH // 2, 84), SUCCESS_COLOR, 24)
        self.play_sound(self.sounds["bonus"])
        return granted_seconds

    def update_mode_clock(self):
        if self.mode_timer_frames is None:
            return
        self.mode_timer_frames = max(0, self.mode_timer_frames - 1)
        remaining_seconds = math.ceil(self.mode_timer_frames / 60)
        if remaining_seconds <= 0:
            self.enter_game_over("timeout")
            return
        if remaining_seconds <= 10 and self.timer_warning_stage < 2:
            self.timer_warning_stage = 2
            self.set_status_message("Clock critical. Finish the wave now.", 90)
            self.play_sound(self.sounds["warning"])
        elif remaining_seconds <= 30 and self.timer_warning_stage < 1:
            self.timer_warning_stage = 1
            self.set_status_message("30 seconds remain on the strike clock.", 90)
            self.play_sound(self.sounds["warning"])

    def run_has_started(self):
        if self.play_frames > 0 or self.score > 0 or self.level > 1:
            return True
        return any(value > 0 for value in self.stats.values())

    def build_run_entry(self):
        return {
            "mode_id": self.current_mode_id,
            "score_version": SCORING_MODEL_VERSION,
            "score": int(self.score),
            "wave_reached": int(self.level),
            "waves_cleared": int(self.stats["waves_cleared"]),
            "bosses_destroyed": int(self.stats["bosses_destroyed"]),
            "best_multiplier": int(self.best_multiplier),
            "duration_seconds": int(self.play_frames / 60),
            "lives_remaining": int(max(0, self.lives)),
            "result": self.run_end_reason,
            "rank": self.rank_label,
            "ended_at": datetime.now().isoformat(timespec="seconds"),
        }

    def finalize_run_record(self):
        if self.run_recorded or not self.run_has_started():
            self.run_recorded = True
            return

        self.run_recorded = True
        entry = self.build_run_entry()
        self.last_run_entry = entry
        lifetime = self.profile["lifetime"]
        lifetime["runs"] += 1
        lifetime["time_seconds"] += entry["duration_seconds"]
        lifetime["score_total"] += self.score
        for key in ("segments_destroyed", "mushrooms_cleared", "specials_destroyed", "bosses_destroyed", "waves_cleared"):
            lifetime[key] += self.stats[key]

        mode_record = self.mode_record(self.current_mode_id)
        mode_record["runs"] += 1
        if self.score > mode_record["best_score"]:
            mode_record["best_score"] = self.score
            self.run_record_highlights.append(f"New {self.current_mode()['label']} score record.")
        if self.level > mode_record["best_wave"]:
            mode_record["best_wave"] = self.level
        if self.best_multiplier > mode_record["best_multiplier"]:
            mode_record["best_multiplier"] = self.best_multiplier
        if entry["duration_seconds"] > mode_record["best_time_seconds"]:
            mode_record["best_time_seconds"] = entry["duration_seconds"]
        previous_rank = mode_record["best_rank"]
        mode_record["best_rank"] = better_rank(mode_record["best_rank"], self.rank_label)
        if mode_record["best_rank"] != previous_rank and rank_value(self.rank_label) >= rank_value("B"):
            self.run_record_highlights.append(f"{self.current_mode()['label']} rank pushed to {self.rank_label}.")

        mode_record["top_runs"].append(entry)
        mode_record["top_runs"] = sorted(mode_record["top_runs"], key=self.record_sort_key)[:TOP_RUNS_PER_MODE]
        if mode_record["top_runs"] and mode_record["top_runs"][0] == entry:
            self.play_sound(self.sounds["record"])

        self.profile["recent_runs"].insert(0, entry)
        self.profile["recent_runs"] = self.profile["recent_runs"][:RECENT_RUN_LIMIT]
        self.profile["career_high_score"] = max(int(self.profile["career_high_score"]), self.score)
        self.evaluate_unlocks(announce=True)
        self.save_profile()

    def enter_game_over(self, reason="destroyed"):
        if self.game_phase in ("game_over", "victory"):
            return
        self.run_end_reason = reason
        self.game_phase = "game_over"
        self.game_over_menu_index = 0
        self.high_score = max(self.high_score, self.score)
        self.rank_label = self.run_rank()
        self.finalize_run_record()
        self.save_high_score()

    def enter_victory(self):
        if self.game_phase in ("game_over", "victory"):
            return
        self.run_end_reason = "victory"
        self.game_phase = "victory"
        self.game_over_menu_index = 0
        self.high_score = max(self.high_score, self.score)
        self.rank_label = self.run_rank()
        self.finalize_run_record()
        self.save_high_score()

    def toggle_sound(self):
        if not AUDIO_AVAILABLE:
            self.set_status_message("Audio device unavailable on this machine.", 150)
            return
        self.sound_enabled = not self.sound_enabled
        self.save_settings()
        self.sync_music(force=True)
        self.set_status_message("Audio restored." if self.sound_enabled else "Audio muted.", 120)

    def toggle_option(self, option_name):
        if option_name == "Audio":
            self.toggle_sound()
        elif option_name == "Screen Shake":
            self.screen_shake_enabled = not self.screen_shake_enabled
        elif option_name == "Reduced Flash":
            self.reduced_flash = not self.reduced_flash
        elif option_name == "Show Briefing":
            self.show_briefing = not self.show_briefing
        self.save_settings()

    def option_value(self, option_name):
        if option_name == "Audio":
            if not AUDIO_AVAILABLE:
                return "Unavailable"
            return "On" if self.sound_enabled else "Muted"
        if option_name == "Screen Shake":
            return "On" if self.screen_shake_enabled else "Off"
        if option_name == "Reduced Flash":
            return "On" if self.reduced_flash else "Off"
        if option_name == "Show Briefing":
            return "On" if self.show_briefing else "Off"
        return ""

    def current_options_items(self):
        return ["Audio", "Screen Shake", "Reduced Flash", "Show Briefing", "Back"]

    def desired_music_key(self):
        if self.game_phase in ("mode_select", "records"):
            return "mode_select_theme"
        if self.game_phase in ("title", "help", "options", "game_over", "victory"):
            return "title_theme"
        if self.game_phase in ("briefing", "paused"):
            return "briefing_theme"
        if self.wave_profile and self.wave_profile["kind"] == "boss" and self.game_phase in ("wave_intro", "playing"):
            return "boss_theme"
        if self.wave_profile and self.wave_profile["kind"] == "surge" and self.game_phase in ("wave_intro", "playing"):
            return "surge_theme"
        if self.game_phase == "wave_intro":
            return "briefing_theme"
        if self.game_phase == "playing":
            return "run_theme"
        return None

    def sync_music(self, force=False):
        if not AUDIO_AVAILABLE or self.music_channel is None:
            return

        if not self.sound_enabled:
            if self.music_channel.get_busy():
                self.music_channel.stop()
            self.current_music_key = None
            return

        desired_key = self.desired_music_key()
        if not desired_key:
            if self.music_channel.get_busy():
                self.music_channel.stop()
            self.current_music_key = None
            return

        desired_sound = self.sounds.get(desired_key)
        if not is_mixer_sound(desired_sound):
            if self.music_channel.get_busy():
                self.music_channel.stop()
            self.current_music_key = None
            return

        if force or desired_key != self.current_music_key or not self.music_channel.get_busy():
            self.current_music_key = desired_key
            self.music_channel.play(desired_sound, loops=-1, fade_ms=250)

    def tutorial_tasks(self):
        return [
            ("Break 3 segments", self.stats["segments_destroyed"] >= 3),
            ("Clear 1 mushroom", self.stats["mushrooms_cleared"] >= 1),
            ("Reach 2x multiplier", self.best_multiplier >= 2),
            ("Survive into Wave 2", self.level >= 2 or self.stats["waves_cleared"] >= 1),
        ]

    def tutorial_active(self):
        return self.current_mode_id == "classic" and not self.tutorial_notice_seen and self.level <= 2

    def update_tutorial_progress(self):
        tasks = self.tutorial_tasks()
        all_complete = all(done for _, done in tasks)
        if all_complete and not self.tutorial_notice_seen:
            self.tutorial_notice_seen = True
            self.set_status_message("Tutorial complete. Matriarch Prime ends the run.", 150)
            self.play_sound(self.sounds["bonus"])

    def rating_score(self):
        return self.score + self.stats["waves_cleared"] * 650 + self.best_multiplier * 500 + self.stats["bosses_destroyed"] * 1600

    def rank_for_score(self, rating_score):
        for label, target in reversed(RANK_THRESHOLDS):
            if rating_score >= target:
                return label
        return "D"

    def next_rank_target(self, rating_score):
        for label, target in RANK_THRESHOLDS:
            if rating_score < target:
                return label, target
        return None, None

    def run_rank(self):
        return self.rank_for_score(self.rating_score())

    def tutorial_focus_hint(self):
        if self.stats["segments_destroyed"] < 3:
            return "Hit the front of the swarm."
        if self.stats["mushrooms_cleared"] < 1:
            return "Blow out one mushroom lane."
        if self.best_multiplier < 2:
            return "Keep the combo bar alive."
        if self.level < 2 and self.stats["waves_cleared"] < 1:
            return "Hold steady into Wave 2."
        return "Hold the lane."

    def title_menu_items(self):
        return ["Quick Start", "Select Mode", "Run Records", "How To Play", "Options", "Quit"]

    def handle_keydown(self, key):
        if key == pygame.K_m:
            self.toggle_sound()
            return

        if self.game_phase == "title":
            self.handle_title_input(key)
        elif self.game_phase == "mode_select":
            self.handle_mode_select_input(key)
        elif self.game_phase == "briefing":
            self.handle_briefing_input(key)
        elif self.game_phase == "help":
            self.handle_help_input(key)
        elif self.game_phase == "records":
            self.handle_records_input(key)
        elif self.game_phase == "options":
            self.handle_options_input(key)
        elif self.game_phase == "wave_intro":
            self.handle_wave_intro_input(key)
        elif self.game_phase == "playing":
            self.handle_playing_input(key)
        elif self.game_phase == "paused":
            self.handle_pause_input(key)
        elif self.game_phase in ("game_over", "victory"):
            self.handle_game_over_input(key)

    def handle_keyup(self, key):
        if key == pygame.K_LEFT:
            self.move_left = False
        elif key == pygame.K_RIGHT:
            self.move_right = False
        elif key in (pygame.K_UP, pygame.K_w):
            self.move_up = False
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.move_down = False
        elif key == pygame.K_SPACE:
            self.fire_held = False

    def handle_title_input(self, key):
        items = self.title_menu_items()
        if key == pygame.K_UP:
            self.title_menu_index = (self.title_menu_index - 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key == pygame.K_DOWN:
            self.title_menu_index = (self.title_menu_index + 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = items[self.title_menu_index]
            if choice == "Quick Start":
                self.play_sound(self.sounds["menu_confirm"])
                self.start_run(mode_id=self.current_mode_id, skip_briefing=True)
            elif choice == "Select Mode":
                self.play_sound(self.sounds["menu_confirm"])
                self.mode_select_index = self.mode_ids.index(self.current_mode_id)
                self.game_phase = "mode_select"
            elif choice == "Run Records":
                self.play_sound(self.sounds["menu_confirm"])
                self.menu_return_phase = "title"
                self.records_mode_index = self.mode_ids.index(self.current_mode_id)
                self.game_phase = "records"
            elif choice == "How To Play":
                self.play_sound(self.sounds["menu_confirm"])
                self.menu_return_phase = "title"
                self.game_phase = "help"
            elif choice == "Options":
                self.play_sound(self.sounds["menu_confirm"])
                self.menu_return_phase = "title"
                self.options_menu_index = 0
                self.game_phase = "options"
            else:
                self.play_sound(self.sounds["menu_confirm"])
                self.running = False
        elif key == pygame.K_ESCAPE:
            self.running = False

    def handle_mode_select_input(self, key):
        if key in (pygame.K_UP, pygame.K_LEFT):
            self.mode_select_index = (self.mode_select_index - 1) % len(self.mode_ids)
            self.play_sound(self.sounds["menu"])
        elif key in (pygame.K_DOWN, pygame.K_RIGHT):
            self.mode_select_index = (self.mode_select_index + 1) % len(self.mode_ids)
            self.play_sound(self.sounds["menu"])
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            mode_id = self.mode_ids[self.mode_select_index]
            if self.mode_is_unlocked(mode_id):
                self.current_mode_id = mode_id
                self.mode_best_score = self.mode_record(mode_id)["best_score"]
                self.play_sound(self.sounds["menu_confirm"])
                self.start_run(mode_id=mode_id, skip_briefing=HEADLESS_SMOKE_TEST)
            else:
                self.set_status_message(self.unlock_requirement_text(mode_id), 150)
                self.play_sound(self.sounds["warning"])
        elif key == pygame.K_h:
            self.play_sound(self.sounds["menu_confirm"])
            self.menu_return_phase = "mode_select"
            self.game_phase = "help"
        elif key == pygame.K_r:
            self.play_sound(self.sounds["menu_confirm"])
            self.menu_return_phase = "mode_select"
            self.records_mode_index = self.mode_select_index
            self.game_phase = "records"
        elif key == pygame.K_ESCAPE:
            self.game_phase = "title"

    def handle_briefing_input(self, key):
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            self.play_sound(self.sounds["menu_confirm"])
            self.begin_wave(1)
        elif key == pygame.K_h:
            self.play_sound(self.sounds["menu_confirm"])
            self.menu_return_phase = "briefing"
            self.game_phase = "help"
        elif key == pygame.K_ESCAPE:
            self.game_phase = "title"

    def handle_help_input(self, key):
        if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
            self.game_phase = self.menu_return_phase

    def handle_records_input(self, key):
        if key == pygame.K_LEFT:
            self.records_mode_index = (self.records_mode_index - 1) % len(self.mode_ids)
            self.play_sound(self.sounds["menu"])
        elif key == pygame.K_RIGHT:
            self.records_mode_index = (self.records_mode_index + 1) % len(self.mode_ids)
            self.play_sound(self.sounds["menu"])
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            mode_id = self.mode_ids[self.records_mode_index]
            if self.mode_is_unlocked(mode_id):
                self.current_mode_id = mode_id
                self.mode_select_index = self.records_mode_index
                self.mode_best_score = self.mode_record(mode_id)["best_score"]
                self.play_sound(self.sounds["menu_confirm"])
                self.start_run(mode_id=mode_id, skip_briefing=HEADLESS_SMOKE_TEST)
            else:
                self.set_status_message(self.unlock_requirement_text(mode_id), 150)
                self.play_sound(self.sounds["warning"])
        elif key == pygame.K_ESCAPE:
            self.game_phase = self.menu_return_phase

    def handle_options_input(self, key):
        items = self.current_options_items()
        if key == pygame.K_UP:
            self.options_menu_index = (self.options_menu_index - 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key == pygame.K_DOWN:
            self.options_menu_index = (self.options_menu_index + 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_LEFT, pygame.K_RIGHT):
            selected = items[self.options_menu_index]
            if selected == "Back":
                self.play_sound(self.sounds["menu_confirm"])
                self.game_phase = self.menu_return_phase
            else:
                self.play_sound(self.sounds["menu_confirm"])
                self.toggle_option(selected)
        elif key == pygame.K_ESCAPE:
            self.game_phase = self.menu_return_phase

    def handle_wave_intro_input(self, key):
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            self.wave_intro_timer = 0
        elif key == pygame.K_ESCAPE:
            self.enter_game_over("abandoned")

    def handle_playing_input(self, key):
        if key == pygame.K_LEFT:
            self.move_left = True
        elif key == pygame.K_RIGHT:
            self.move_right = True
        elif key in (pygame.K_UP, pygame.K_w):
            self.move_up = True
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.move_down = True
        elif key == pygame.K_SPACE:
            self.fire_held = True
            self.player.try_fire()
        elif key == pygame.K_p:
            self.pause_menu_index = 0
            self.game_phase = "paused"
            self.set_status_message("Run paused.", 90)
        elif key == pygame.K_h:
            self.pause_menu_index = 1
            self.game_phase = "paused"
        elif key == pygame.K_ESCAPE:
            self.enter_game_over("abandoned")

    def handle_pause_input(self, key):
        items = ["Resume", "How To Play", "Options", "Abandon Run"]
        if key == pygame.K_UP:
            self.pause_menu_index = (self.pause_menu_index - 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key == pygame.K_DOWN:
            self.pause_menu_index = (self.pause_menu_index + 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key == pygame.K_p:
            self.game_phase = "playing"
            self.set_status_message("Back in the fight.", 90)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = items[self.pause_menu_index]
            if choice == "Resume":
                self.game_phase = "playing"
                self.set_status_message("Back in the fight.", 90)
            elif choice == "How To Play":
                self.menu_return_phase = "paused"
                self.game_phase = "help"
            elif choice == "Options":
                self.menu_return_phase = "paused"
                self.options_menu_index = 0
                self.game_phase = "options"
            else:
                self.enter_game_over("abandoned")
        elif key == pygame.K_ESCAPE:
            self.enter_game_over("abandoned")

    def handle_game_over_input(self, key):
        items = ["Retry", "Run Records", "Title Screen", "Quit"]
        if key == pygame.K_UP:
            self.game_over_menu_index = (self.game_over_menu_index - 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key == pygame.K_DOWN:
            self.game_over_menu_index = (self.game_over_menu_index + 1) % len(items)
            self.play_sound(self.sounds["menu"])
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = items[self.game_over_menu_index]
            if choice == "Retry":
                self.start_run(mode_id=self.current_mode_id, skip_briefing=HEADLESS_SMOKE_TEST)
            elif choice == "Run Records":
                self.menu_return_phase = "game_over"
                self.records_mode_index = self.mode_ids.index(self.current_mode_id)
                self.game_phase = "records"
            elif choice == "Title Screen":
                self.game_phase = "title"
            else:
                self.running = False
        elif key == pygame.K_ESCAPE:
            self.game_phase = "title"

    def update(self):
        self.update_starfield()
        self.update_status_timer()
        self.update_screen_fx()
        self.update_tutorial_progress()

        if self.game_phase == "wave_intro":
            self.wave_intro_timer -= 1
            if self.wave_intro_timer <= 0:
                self.deploy_current_wave()
            return

        if self.game_phase != "playing":
            return

        self.play_frames += 1
        self.update_mode_clock()
        if self.game_phase != "playing":
            return
        self.update_combo_timer()
        self.update_centipedes()
        self.update_enemy_spawns()
        self.all_sprites.update()
        self.handle_collisions()

    def update_starfield(self):
        for star in self.starfield:
            star["y"] += star["speed"]
            if star["y"] >= PLAYER_ZONE_TOP - 24:
                star["y"] = random.uniform(0, 40)
                star["x"] = random.uniform(0, SCREEN_WIDTH)

    def update_combo_timer(self):
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer == 0:
                self.reset_combo(announce=True)

    def update_status_timer(self):
        if self.status_timer > 0:
            self.status_timer -= 1
            if self.status_timer == 0:
                self.status_message = ""

    def update_screen_fx(self):
        if self.shake_frames > 0:
            self.shake_frames -= 1
            if self.shake_frames == 0:
                self.shake_strength = 0
        if self.flash_alpha > 0:
            self.flash_alpha = max(0, self.flash_alpha - self.flash_decay)

    def update_enemy_spawns(self):
        kind = self.wave_profile["kind"]
        if kind not in ("swarm", "surge"):
            return

        surge = kind == "surge"
        rate_scale = 0.75 if surge else 1.0
        spider_rate = max(35, int(self.wave_profile["spider_rate"] * rate_scale))
        spider_limit = self.wave_profile["spider_limit"] + (1 if surge else 0)
        self.spider_spawn_counter += 1
        if (
            self.spider_spawn_counter >= spider_rate
            and len(self.spiders) < spider_limit
        ):
            self.spider_spawn_counter = 0
            spider = Spider(self)
            self.add_sprite(spider, 4, self.all_sprites, self.spiders)

        mushrooms_in_player_area = [m for m in self.mushrooms if m.rect.y > PLAYER_ZONE_TOP - 60]
        flea_roll = max(35, 125 - self.level * 6)
        flea_threshold = max(1, self.wave_profile["flea_threshold"] - (1 if surge else 0))
        if (
            len(mushrooms_in_player_area) < flea_threshold
            and len(self.fleas) < 1 + self.level // 8
            and random.randint(1, flea_roll) == 1
        ):
            flea = Flea(self)
            self.add_sprite(flea, 4, self.all_sprites, self.fleas)

        scorpion_rate = max(70, int(self.wave_profile["scorpion_rate"] * rate_scale))
        self.scorpion_spawn_counter += 1
        if self.scorpion_spawn_counter >= scorpion_rate and len(self.scorpions) == 0:
            self.scorpion_spawn_counter = 0
            scorpion = Scorpion(self)
            self.add_sprite(scorpion, 4, self.all_sprites, self.scorpions)

    def centipede_patrol_top(self, head):
        resting_top = PLAYER_START_BOTTOM - self.player.rect.height
        return resting_top - head.rect.height - 6

    def drop_centipede_head(self, head, floor):
        if head.rect.top + GRID_STEP >= floor:
            head.rect.top = floor
            head.direction *= -1
            return
        head.move_down()

    def update_centipedes(self):
        if not self.centipedes:
            return
        self.centipede_move_counter += 1
        if self.centipede_move_counter < self.wave_profile["centipede_delay"]:
            return
        self.centipede_move_counter = 0

        for centipede in list(self.centipedes):
            centipede[:] = [segment for segment in centipede if segment.alive()]
            if not centipede:
                self.centipedes.remove(centipede)
                continue

            for index in range(len(centipede) - 1, 0, -1):
                centipede[index].rect.topleft = centipede[index - 1].rect.topleft

            head = centipede[0]
            if head.diving:
                head.move_dive()
                continue

            floor = self.centipede_patrol_top(head)
            if head.rect.top >= floor:
                head.rect.top = floor
                head.rect.x += head.speed * head.direction
                if head.rect.left < 0:
                    head.rect.left = 0
                    head.direction = 1
                elif head.rect.right > SCREEN_WIDTH:
                    head.rect.right = SCREEN_WIDTH
                    head.direction = -1
                continue

            head.rect.x += head.speed * head.direction
            hit_edge = head.rect.right > SCREEN_WIDTH or head.rect.left < 0
            if head.rect.left < 0:
                head.rect.left = 0
            elif head.rect.right > SCREEN_WIDTH:
                head.rect.right = SCREEN_WIDTH
            if hit_edge:
                self.drop_centipede_head(head, floor)
            if head.rect.top < floor and pygame.sprite.spritecollide(head, self.mushrooms, False):
                self.drop_centipede_head(head, floor)

    def handle_collisions(self):
        mushroom_hits = pygame.sprite.groupcollide(self.player_bullets, self.mushrooms, True, False)
        for hit_list in mushroom_hits.values():
            for mushroom in hit_list:
                points = mushroom.hit()
                if not mushroom.alive():
                    self.stats["mushrooms_cleared"] += 1
                    self.spawn_floating_text("Lane clear", mushroom.rect.center, SUCCESS_COLOR, 16)
                self.add_points(points)
                self.spawn_effect("hit", mushroom.rect.center)

        centipede_hits = pygame.sprite.groupcollide(self.player_bullets, self.centipede_segments, True, False)
        for hit_segments in centipede_hits.values():
            for segment in hit_segments:
                if not segment.alive():
                    continue
                self.play_sound(self.sounds["enemy_hit"])
                self.spawn_effect("explosion", segment.rect.center)
                mushroom = Mushroom(self, segment.rect.x, segment.rect.y)
                self.add_sprite(mushroom, 2, self.all_sprites, self.mushrooms)

                for centipede in list(self.centipedes):
                    if segment not in centipede:
                        continue
                    index = centipede.index(segment)
                    if index + 1 < len(centipede):
                        next_segment = centipede[index + 1]
                        next_segment.is_head = True
                        next_segment.diving = False
                        next_segment.refresh_image()
                        self.centipedes.append(list(centipede[index + 1 :]))
                    del centipede[index:]
                    if not centipede:
                        self.centipedes.remove(centipede)
                    break

                self.stats["segments_destroyed"] += 1
                self.register_combo_kill(120 if segment.is_head else 30, segment.rect.center, "Segment")
                segment.kill()

        spider_hits = pygame.sprite.groupcollide(self.player_bullets, self.spiders, True, True)
        for spider_group in spider_hits.values():
            for target in spider_group:
                self.stats["specials_destroyed"] += 1
                self.play_sound(self.sounds["enemy_hit"])
                self.spawn_effect("explosion", target.rect.center)
                self.register_combo_kill(600, target.rect.center, "Spider")

        flea_hits = pygame.sprite.groupcollide(self.player_bullets, self.fleas, True, False)
        for flea_group in flea_hits.values():
            for flea in flea_group:
                if flea.take_hit():
                    self.stats["specials_destroyed"] += 1
                    self.play_sound(self.sounds["enemy_hit"])
                    self.spawn_effect("explosion", flea.rect.center)
                    self.register_combo_kill(240, flea.rect.center, "Flea")
                    flea.kill()
                else:
                    self.spawn_effect("hit", flea.rect.center)

        scorpion_hits = pygame.sprite.groupcollide(self.player_bullets, self.scorpions, True, True)
        for scorpion_group in scorpion_hits.values():
            for target in scorpion_group:
                self.stats["specials_destroyed"] += 1
                self.play_sound(self.sounds["enemy_hit"])
                self.spawn_effect("explosion", target.rect.center)
                self.register_combo_kill(900, target.rect.center, "Scorpion")

        boss_hits = pygame.sprite.groupcollide(self.player_bullets, self.bosses, True, False)
        for boss_group in boss_hits.values():
            for boss in boss_group:
                defeated = boss.take_hit(1)
                self.add_points(18 * self.multiplier)
                if defeated:
                    self.stats["bosses_destroyed"] += 1
                    self.play_sound(self.sounds["boss_die"])
                    self.spawn_effect("explosion", boss.rect.center, large=True)
                    self.spawn_effect("explosion", boss.rect.midleft, large=True)
                    self.spawn_effect("explosion", boss.rect.midright, large=True)
                    if boss.profile.get("prime"):
                        self.spawn_effect("explosion", boss.rect.midtop, large=True)
                        self.spawn_effect("explosion", boss.rect.midbottom, large=True)
                    self.register_combo_kill(
                        4200 if boss.profile.get("prime") else 3500,
                        boss.rect.center,
                        "Matriarch Prime" if boss.profile.get("prime") else "Matriarch",
                    )
                    self.trigger_shake(10 if boss.profile.get("prime") else 8, 24 if boss.profile.get("prime") else 20)
                    self.trigger_flash(DANGER_COLOR, 165 if boss.profile.get("prime") else 150, 9)

        projectile_hits = pygame.sprite.groupcollide(self.enemy_projectiles, self.mushrooms, True, False)
        for mushroom_group in projectile_hits.values():
            for mushroom in mushroom_group:
                mushroom.poison()
                self.spawn_effect("hit", mushroom.rect.center)

        self.resolve_wave_completion()
        if self.game_phase != "playing":
            return

        if self.player.invulnerable_timer <= 0:
            player_collided = any(
                pygame.sprite.spritecollide(self.player, group, False)
                for group in (
                    self.centipede_segments,
                    self.spiders,
                    self.fleas,
                    self.scorpions,
                    self.enemy_projectiles,
                    self.bosses,
                )
            )
            if player_collided:
                self.handle_player_hit()

    def handle_player_hit(self):
        self.play_sound(self.sounds["player_die"])
        self.lives -= 1
        if self.lives == 1:
            self.play_sound(self.sounds["last_life"])
            self.set_status_message("Final ship in the trench.", 150)
        self.trigger_flash(DANGER_COLOR, 175, 12)
        self.trigger_shake(6, 18)
        self.spawn_effect("explosion", self.player.rect.center, large=False)
        self.reset_combo(announce=False)
        if self.lives <= 0:
            self.enter_game_over("destroyed")
        else:
            if self.lives > 1:
                self.set_status_message("Defence line breached. Rebuilding lane.", 120)
            self.reset_after_life()

    def resolve_wave_completion(self):
        if self.game_phase != "playing" or not self.wave_profile:
            return
        if self.wave_profile["kind"] == "boss":
            if self.wave_profile.get("prime"):
                # Matriarch Prime is the campaign's winning boss: her fall ends the run at once,
                # even with support centipedes or enemy projectiles still in the trench, so a
                # leftover shot or the strike clock can no longer turn a won run into a loss.
                if not self.bosses:
                    self.complete_wave()
            elif not self.bosses and not self.centipedes and not self.enemy_projectiles:
                self.complete_wave()
        elif not self.centipedes:
            self.complete_wave()

    def draw_background(self, surface):
        surface.blit(self.static_background, (0, 0))
        for star in self.starfield:
            pygame.draw.circle(surface, star["color"], (int(star["x"]), int(star["y"])), star["radius"])

    def draw_status_banner(self, surface):
        if self.status_timer <= 0 or not self.status_message:
            return
        theme = self.level_theme
        banner = pygame.Rect(178, 58, SCREEN_WIDTH - 356, 34)
        pygame.draw.rect(surface, PANEL_COLOR, banner, border_radius=10)
        pygame.draw.rect(surface, theme["panel_border"], banner, width=1, border_radius=10)
        self.draw_text(surface, self.status_message, 17, SCREEN_WIDTH / 2, 64, theme["warning"])

    def draw_hud(self, surface):
        theme = self.level_theme
        left_chip = pygame.Rect(12, 10, 170, 96)
        center_chip = pygame.Rect(238, 8, 324, 52)
        right_chip = pygame.Rect(SCREEN_WIDTH - 168, 10, 156, 58)
        for chip in (left_chip, center_chip, right_chip):
            pygame.draw.rect(surface, (10, 16, 26), chip, border_radius=14)
            pygame.draw.rect(surface, theme["panel_border"], chip, width=1, border_radius=14)

        self.draw_text(surface, f"Score {self.score}", 20, 22, 14, WHITE, align="topleft", bold=True)
        self.draw_text(surface, f"Lives {self.lives}", 18, 22, 40, SUCCESS_COLOR, align="topleft")
        rating_score = self.rating_score()
        next_label, next_target = self.next_rank_target(rating_score)
        self.draw_text(surface, f"Rank {self.live_rank_label}", 16, 22, 64, TITLE_COLOR, align="topleft")
        if next_label:
            remaining = max(0, next_target - rating_score)
            self.draw_text(surface, f"Next {next_label} in {remaining}", 14, 22, 84, (176, 188, 206), align="topleft")
        if self.wave_profile["kind"] == "surge":
            self.draw_text(surface, f"Surge clear bonus {self.wave_profile['surge_bonus']}", 14, 22, 104, WARNING_COLOR, align="topleft")
        elif self.wave_profile["kind"] == "boss" and self.wave_profile.get("boss_prime_bonus"):
            self.draw_text(surface, f"Prime collapse bonus {self.wave_profile['boss_prime_bonus']}", 14, 22, 104, WARNING_COLOR, align="topleft")
        elif self.mode_best_score_start > 0 and self.score < self.mode_best_score_start:
            self.draw_text(surface, f"Need {self.mode_best_score_start - self.score} for mode record", 14, 22, 104, (176, 188, 206), align="topleft")
        elif self.score > self.mode_best_score_start:
            self.draw_text(surface, f"Record pace +{self.score - self.mode_best_score_start}", 14, 22, 104, SUCCESS_COLOR, align="topleft")
        else:
            self.draw_text(surface, "Set the opening benchmark", 14, 22, 104, (176, 188, 206), align="topleft")
        self.draw_text(surface, WIN_LINE, 14, 22, 122, SUCCESS_COLOR, align="topleft")
        self.draw_text(surface, f"Wave {self.level}", 18, SCREEN_WIDTH - 22, 14, theme["title"], align="topright", bold=True)
        self.draw_text(surface, f"Best {self.mode_best_score}", 16, SCREEN_WIDTH - 22, 40, theme["warning"], align="topright")
        self.draw_text(surface, f"{self.current_mode()['short_label']}  |  {self.wave_profile['title']}", 16, SCREEN_WIDTH / 2, 12, (212, 224, 240), bold=True)
        if self.mode_timer_frames is not None:
            remaining = max(0, math.ceil(self.mode_timer_frames / 60))
            if remaining <= 10:
                timer_color = DANGER_COLOR
            elif remaining <= 30:
                timer_color = WARNING_COLOR
            else:
                timer_color = SUCCESS_COLOR
            self.draw_text(surface, f"Clock {format_seconds(remaining)}", 16, SCREEN_WIDTH / 2, 34, timer_color, bold=True)
        else:
            self.draw_text(surface, f"Next life @ {self.next_extra_life_score}", 14, SCREEN_WIDTH / 2, 34, SUCCESS_COLOR)

        combo_panel = pygame.Rect(22, SCREEN_HEIGHT - 44, 196, 18)
        ratio = self.combo_timer / 240 if self.combo_timer else 0
        self.draw_meter(surface, combo_panel, ratio, (82, 215, 255))
        charge_threshold = 2 + self.multiplier
        charge_ratio = self.combo_charge / charge_threshold if charge_threshold else 0
        charge_rect = pygame.Rect(226, SCREEN_HEIGHT - 44, 128, 18)
        self.draw_meter(surface, charge_rect, charge_ratio, (255, 170, 94))
        self.draw_text(surface, f"{self.multiplier}x multiplier", 17, 26, SCREEN_HEIGHT - 68, WARNING_COLOR, align="topleft", bold=True)
        self.draw_text(surface, "Combo window", 14, 24, SCREEN_HEIGHT - 24, (178, 192, 215), align="bottomleft")
        self.draw_text(surface, "Charge", 14, 230, SCREEN_HEIGHT - 24, (178, 192, 215), align="bottomleft")

        if self.bosses:
            boss = self.bosses.sprites()[0]
            bar = pygame.Rect(232, SCREEN_HEIGHT - 46, SCREEN_WIDTH - 254, 20)
            phase_colors = {
                1: (255, 96, 102),
                2: (255, 152, 94),
                3: (255, 202, 96),
            }
            self.draw_meter(surface, bar, boss.health / boss.max_health, phase_colors.get(boss.phase, DANGER_COLOR))
            for marker in (1, 2):
                marker_x = bar.x + (bar.width * marker) // 3
                pygame.draw.line(surface, (30, 20, 26), (marker_x, bar.y + 1), (marker_x, bar.bottom - 1), 2)
            boss_name = "Matriarch Prime" if boss.profile.get("prime") else "Hive Matriarch"
            phase_text = {
                1: "Opening pressure",
                2: "Reinforcements rising",
                3: "Trench break armed" if boss.profile.get("prime") else "Final pressure",
            }.get(boss.phase, "Press the attack")
            self.draw_text(
                surface,
                f"{boss_name}  |  Phase {boss.phase}/3  |  {phase_text}",
                15,
                SCREEN_WIDTH / 2,
                SCREEN_HEIGHT - 72,
                DANGER_COLOR,
                bold=True,
            )

        audio_label = "Audio On" if self.sound_enabled else "Audio Muted"
        audio_color = AUDIO_ON_COLOR if self.sound_enabled else AUDIO_OFF_COLOR
        self.draw_text(surface, audio_label, 14, SCREEN_WIDTH - 22, SCREEN_HEIGHT - 24, audio_color, align="bottomright")

    def draw_tutorial_card(self, surface):
        if not self.tutorial_active():
            return

        theme = self.level_theme
        rect = pygame.Rect(SCREEN_WIDTH - 254, 98, 228, 152)
        pygame.draw.rect(surface, (10, 16, 26), rect, border_radius=16)
        pygame.draw.rect(surface, theme["panel_border"], rect, width=1, border_radius=16)
        self.draw_text(surface, "First Run Goals", 20, rect.centerx, rect.y + 12, theme["title"], bold=True)

        tasks = self.tutorial_tasks()
        y = rect.y + 48
        for label, done in tasks:
            bullet_color = SUCCESS_COLOR if done else WARNING_COLOR
            pygame.draw.circle(surface, bullet_color, (rect.x + 18, y + 8), 5)
            display = label if not done else f"{label} complete"
            self.draw_text(surface, display, 15, rect.x + 32, y, WHITE if done else (220, 226, 238), align="topleft")
            y += 22

        self.draw_text(surface, self.tutorial_focus_hint(), 14, rect.centerx, rect.bottom - 22, (172, 186, 205))

    def draw_menu(self, surface, items, selected_index, start_y):
        for index, label in enumerate(items):
            y = start_y + index * 32
            active = index == selected_index
            color = TITLE_COLOR if active else WHITE
            if active:
                highlight = pygame.Rect(268, y - 6, 264, 30)
                pygame.draw.rect(surface, (24, 39, 61), highlight, border_radius=12)
                pygame.draw.rect(surface, (67, 115, 160), highlight, width=1, border_radius=12)
            self.draw_text(surface, label, 24, SCREEN_WIDTH / 2, y, color, bold=active)

    def draw_title_screen(self):
        self.draw_background(self.screen)
        panel = pygame.Rect(88, 44, SCREEN_WIDTH - 176, SCREEN_HEIGHT - 88)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, "SWARMBREAKER", 46, SCREEN_WIDTH / 2, 78, TITLE_COLOR, bold=True)
        self.draw_text(self.screen, "Arcade trench defence against a venom-guided segmented swarm.", 18, SCREEN_WIDTH / 2, 126, WHITE)
        story_lines = [
            "Hold Sector Seven against the hive.",
            WIN_LINE,
            LOSS_LINE,
        ]
        for index, line in enumerate(story_lines):
            self.draw_text(self.screen, line, 16, SCREEN_WIDTH / 2, 154 + index * 20, (210, 221, 236))

        current_record = self.mode_record(self.current_mode_id)
        lifetime = self.profile["lifetime"]
        intel_strip = pygame.Rect(120, 216, SCREEN_WIDTH - 240, 42)
        self.draw_panel(self.screen, intel_strip)
        self.draw_text(self.screen, f"Current Deployment  |  {self.current_mode()['label']}", 16, intel_strip.centerx, intel_strip.y + 4, TITLE_COLOR, bold=True)
        self.draw_text(
            self.screen,
            f"Best {current_record['best_score']}   Wave {current_record['best_wave']}   x{current_record['best_multiplier']}   Runs {lifetime['runs']}   Bosses {lifetime['bosses_destroyed']}   Clears {lifetime['waves_cleared']}",
            13,
            intel_strip.centerx,
            intel_strip.y + 24,
            WARNING_COLOR,
        )
        self.draw_menu(self.screen, self.title_menu_items(), self.title_menu_index, 272)
        self.draw_text(
            self.screen,
            f"Career High  {self.high_score}   |   Unlocked Modes  {sum(1 for mode_id in self.mode_ids if self.mode_is_unlocked(mode_id))}/{len(self.mode_ids)}",
            18,
            SCREEN_WIDTH / 2,
            468,
            WARNING_COLOR,
            bold=True,
        )
        self.draw_text(
            self.screen,
            "Quick Start deploys Classic Defence. Select Mode opens the other rulesets.",
            15,
            SCREEN_WIDTH / 2,
            498,
            (176, 188, 206),
        )
        self.draw_text(self.screen, "Arrow keys move. Push up the trench for extra dodge space. P pauses. M toggles audio.", 15, SCREEN_WIDTH / 2, 524, (172, 186, 205))

    def draw_mode_select_screen(self):
        self.draw_background(self.screen)
        panel = pygame.Rect(64, 48, SCREEN_WIDTH - 128, SCREEN_HEIGHT - 96)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, "Select Run", 44, SCREEN_WIDTH / 2, 84, TITLE_COLOR, bold=True)
        self.draw_text(self.screen, "Choose a ruleset, check the unlock state, and deploy when ready.", 18, SCREEN_WIDTH / 2, 128, WHITE)

        list_rect = pygame.Rect(96, 172, 238, 332)
        detail_rect = pygame.Rect(356, 172, 348, 332)
        self.draw_panel(self.screen, list_rect)
        self.draw_panel(self.screen, detail_rect)

        for index, mode_id in enumerate(self.mode_ids):
            mode = GAME_MODES[mode_id]
            y = list_rect.y + 18 + index * 76
            active = index == self.mode_select_index
            unlocked = self.mode_is_unlocked(mode_id)
            if active:
                highlight = pygame.Rect(list_rect.x + 10, y - 8, list_rect.width - 20, 54)
                pygame.draw.rect(self.screen, (24, 39, 61), highlight, border_radius=12)
                pygame.draw.rect(self.screen, (67, 115, 160), highlight, width=1, border_radius=12)
            title_color = TITLE_COLOR if active else (220, 226, 238)
            if not unlocked:
                title_color = (144, 156, 178)
            self.draw_text(self.screen, mode["label"], 20, list_rect.x + 18, y, title_color, align="topleft", bold=active)
            status_text = "Unlocked" if unlocked else "Locked"
            status_color = SUCCESS_COLOR if unlocked else WARNING_COLOR
            self.draw_text(self.screen, status_text, 14, list_rect.right - 16, y + 28, status_color, align="topright")

        mode_id = self.mode_ids[self.mode_select_index]
        mode = GAME_MODES[mode_id]
        record = self.mode_record(mode_id)
        unlocked = self.mode_is_unlocked(mode_id)
        self.draw_text(self.screen, mode["label"], 26, detail_rect.centerx, detail_rect.y + 14, TITLE_COLOR, bold=True)
        tagline_bottom = self.draw_wrapped_text(
            self.screen,
            mode["tagline"],
            15,
            pygame.Rect(detail_rect.x + 18, detail_rect.y + 48, detail_rect.width - 36, 44),
            WHITE,
            max_bottom=detail_rect.y + 96,
        )
        info_y = max(tagline_bottom + 4, detail_rect.y + 96)
        self.draw_text(
            self.screen,
            f"Local best {record['best_score']}   Rank {record['best_rank']}   Wave {record['best_wave']}",
            15,
            detail_rect.centerx,
            info_y,
            WARNING_COLOR,
        )

        stat_specs = [
            ("Runs", str(record["runs"])),
            ("Best x", f"{record['best_multiplier']}x"),
            ("Best time", format_seconds(record["best_time_seconds"])),
        ]
        chip_y = info_y + 22
        chip_width = 98
        chip_gap = 10
        chip_x = detail_rect.x + 18
        for label, value in stat_specs:
            chip = pygame.Rect(chip_x, chip_y, chip_width, 40)
            pygame.draw.rect(self.screen, (13, 20, 31), chip, border_radius=12)
            pygame.draw.rect(self.screen, PANEL_BORDER, chip, width=1, border_radius=12)
            self.draw_text(self.screen, label, 13, chip.centerx, chip.y + 4, (176, 188, 206), bold=True)
            self.draw_text(self.screen, value, 16, chip.centerx, chip.y + 20, WHITE, bold=True)
            chip_x += chip_width + chip_gap

        text_limit = detail_rect.bottom - (64 if not unlocked else 18)
        description_bottom = self.draw_wrapped_text(
            self.screen,
            mode["description"],
            15,
            pygame.Rect(detail_rect.x + 18, chip_y + 48, detail_rect.width - 36, 52),
            (192, 205, 224),
            max_bottom=text_limit,
        )

        rules_y = description_bottom + 6
        for line in mode["rules"][:2]:
            if rules_y + 16 > text_limit:
                break
            rules_y = self.draw_wrapped_text(
                self.screen,
                f"- {line}",
                14,
                pygame.Rect(detail_rect.x + 18, rules_y, detail_rect.width - 36, 36),
                WHITE,
                max_bottom=text_limit,
            ) + 2
        if len(mode["rules"]) > 2 and rules_y + 16 <= text_limit:
            self.draw_text(self.screen, "See briefing for the full rule breakdown.", 13, detail_rect.x + 18, rules_y, (176, 188, 206), align="topleft")

        if not unlocked:
            self.draw_text(self.screen, self.unlock_requirement_text(mode_id), 14, detail_rect.centerx, detail_rect.bottom - 40, WARNING_COLOR, bold=True)
            self.draw_text(self.screen, self.unlock_progress_text(mode_id), 14, detail_rect.centerx, detail_rect.bottom - 20, (176, 188, 206))
        self.draw_text(self.screen, "Arrows change mode. Enter/Space deploy. R opens records. H opens help. Esc goes back.", 16, SCREEN_WIDTH / 2, 522, (176, 188, 206))

    def draw_briefing_screen(self):
        mode = self.current_mode()
        if mode["boss_interval"] == 1:
            boss_line = "Every wave is a boss break in this ruleset."
        else:
            boss_line = f"Boss waves arrive every {mode['boss_interval']} pushes."
        self.draw_background(self.screen)
        panel = pygame.Rect(70, 28, SCREEN_WIDTH - 140, SCREEN_HEIGHT - 64)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, f"Quick Briefing  |  {mode['label']}", 34, SCREEN_WIDTH / 2, 58, TITLE_COLOR, bold=True)
        briefing = [
            (WIN_LINE, SUCCESS_COLOR),
            (LOSS_LINE, DANGER_COLOR),
            (mode["briefing_lines"][0], WHITE),
            (mode["briefing_lines"][1], WHITE),
            ("Poisoned mushrooms make centipede heads dive through your lane.", WHITE),
            (f"Every {mode['extra_life_step']:,} points earns another defence ship.", WHITE),
            (boss_line, WHITE),
            ("The run ends when Matriarch Prime falls or the trench is lost.", WHITE),
        ]
        y = 108
        for line, color in briefing:
            self.draw_text(self.screen, line, 17, SCREEN_WIDTH / 2, y, color, bold=color != WHITE)
            y += 22

        controls = [
            ("Left / Right", "Strafe", WHITE),
            ("Up / Down", "Advance or fall back", WARNING_COLOR),
            ("Hold Space", "Fire", WHITE),
            ("P", "Pause menu", WHITE),
            ("M", "Toggle audio", WHITE),
            ("Esc", "Abandon current run", WHITE),
        ]
        control_y = y + 10
        for action, effect, color in controls:
            self.draw_text(self.screen, action, 16, 300, control_y, color, align="topright")
            self.draw_text(self.screen, effect, 16, 324, control_y, color, align="topleft")
            control_y += 22
        self.draw_text(self.screen, "Press Enter to deploy the first defence line.", 18, SCREEN_WIDTH / 2, control_y + 8, SUCCESS_COLOR, bold=True)
        self.draw_text(self.screen, "Press H for the help card or Esc to return to the title screen.", 16, SCREEN_WIDTH / 2, control_y + 34, (172, 186, 205))

    def draw_help_screen(self):
        self.draw_background(self.screen)
        panel = pygame.Rect(70, 36, SCREEN_WIDTH - 140, SCREEN_HEIGHT - 80)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, "How To Play", 40, SCREEN_WIDTH / 2, 64, TITLE_COLOR, bold=True)
        lines = [
            ("The run", WARNING_COLOR),
            (WIN_LINE, SUCCESS_COLOR),
            (LOSS_LINE, DANGER_COLOR),
            ("Classic Defence reaches her on wave 12.", WHITE),
            ("", WHITE),
            ("How", WARNING_COLOR),
            ("Clear the swarm before it reaches the player zone.", WHITE),
            ("Poisoned mushrooms make centipede heads dive.", WHITE),
            ("Chain kills raise the multiplier.", WHITE),
            ("Bosses follow the mode cadence.", WHITE),
            ("", WHITE),
            ("Enemies", WARNING_COLOR),
            ("Centipede heads split the body. Fleas replant mushrooms.", WHITE),
            ("Scorpions poison caps. Spiders hunt the player zone.", WHITE),
        ]
        y = 118
        for line, color in lines:
            if line:
                self.draw_text(self.screen, line, 18, SCREEN_WIDTH / 2, y, color, bold=color == WARNING_COLOR)
            y += 24
        self.draw_text(self.screen, "Press Enter or Esc to go back.", 18, SCREEN_WIDTH / 2, 520, SUCCESS_COLOR, bold=True)

    def draw_options_screen(self):
        self.draw_background(self.screen)
        panel = pygame.Rect(142, 86, SCREEN_WIDTH - 284, SCREEN_HEIGHT - 172)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, "Options", 42, SCREEN_WIDTH / 2, 128, TITLE_COLOR, bold=True)
        items = self.current_options_items()
        start_y = 214
        for index, label in enumerate(items):
            y = start_y + index * 42
            active = index == self.options_menu_index
            if active:
                highlight = pygame.Rect(214, y - 8, 372, 32)
                pygame.draw.rect(self.screen, (24, 39, 61), highlight, border_radius=12)
                pygame.draw.rect(self.screen, (67, 115, 160), highlight, width=1, border_radius=12)
            value = "" if label == "Back" else self.option_value(label)
            self.draw_text(self.screen, label, 24, 240, y, TITLE_COLOR if active else WHITE, align="midleft", bold=active)
            if value:
                if value == "Muted":
                    value_color = AUDIO_OFF_COLOR
                elif value == "Unavailable":
                    value_color = WARNING_COLOR
                else:
                    value_color = SUCCESS_COLOR if value == "On" else WARNING_COLOR
                self.draw_text(self.screen, value, 24, 560, y, value_color, align="midright", bold=active)
        self.draw_text(self.screen, "Use Enter or Left/Right to toggle. Esc returns.", 18, SCREEN_WIDTH / 2, 492, (176, 188, 206))

    def draw_records_screen(self):
        self.draw_background(self.screen)
        panel = pygame.Rect(56, 42, SCREEN_WIDTH - 112, SCREEN_HEIGHT - 84)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, "Run Records", 44, SCREEN_WIDTH / 2, 78, TITLE_COLOR, bold=True)
        self.draw_text(self.screen, "Left and right swap the leaderboard view. Enter launches an unlocked mode.", 17, SCREEN_WIDTH / 2, 118, WHITE)

        summary_rect = pygame.Rect(84, 160, 250, 328)
        leaderboard_rect = pygame.Rect(354, 160, 362, 328)
        self.draw_panel(self.screen, summary_rect)
        self.draw_panel(self.screen, leaderboard_rect)

        lifetime = self.profile["lifetime"]
        self.draw_text(self.screen, "Career Summary", 24, summary_rect.centerx, summary_rect.y + 18, TITLE_COLOR, bold=True)
        summary_lines = [
            f"Career high        {self.high_score}",
            f"Runs logged        {lifetime['runs']}",
            f"Time in lane       {format_seconds(lifetime['time_seconds'])}",
            f"Waves cleared      {lifetime['waves_cleared']}",
            f"Bosses broken      {lifetime['bosses_destroyed']}",
            f"Segments shattered {lifetime['segments_destroyed']}",
        ]
        summary_y = summary_rect.y + 60
        for line in summary_lines:
            self.draw_text(self.screen, line, 18, summary_rect.centerx, summary_y, WHITE)
            summary_y += 26

        self.draw_text(self.screen, "Unlock Status", 22, summary_rect.centerx, summary_y + 12, WARNING_COLOR, bold=True)
        summary_y += 46
        for mode_id in self.mode_ids:
            mode = GAME_MODES[mode_id]
            unlocked = self.mode_is_unlocked(mode_id)
            color = SUCCESS_COLOR if unlocked else (192, 205, 224)
            lock_text = "Unlocked" if unlocked else self.unlock_progress_text(mode_id)
            self.draw_text(self.screen, mode["label"], 17, summary_rect.x + 18, summary_y, color, align="topleft", bold=unlocked)
            self.draw_text(self.screen, lock_text, 15, summary_rect.right - 18, summary_y + 1, WARNING_COLOR if not unlocked else SUCCESS_COLOR, align="topright")
            summary_y += 24

        mode_id = self.mode_ids[self.records_mode_index]
        mode = GAME_MODES[mode_id]
        record = self.mode_record(mode_id)
        top_runs = record["top_runs"]
        heading_color = SUCCESS_COLOR if self.mode_is_unlocked(mode_id) else WARNING_COLOR
        self.draw_text(self.screen, mode["label"], 26, leaderboard_rect.centerx, leaderboard_rect.y + 18, TITLE_COLOR, bold=True)
        self.draw_text(self.screen, mode["tagline"], 16, leaderboard_rect.centerx, leaderboard_rect.y + 52, heading_color)
        self.draw_text(
            self.screen,
            f"Best score {record['best_score']}   Best rank {record['best_rank']}   Best wave {record['best_wave']}",
            16,
            leaderboard_rect.centerx,
            leaderboard_rect.y + 82,
            WARNING_COLOR,
        )
        if top_runs:
            run_y = leaderboard_rect.y + 126
            for index, entry in enumerate(top_runs[:TOP_RUNS_PER_MODE]):
                self.draw_text(
                    self.screen,
                    f"{index + 1}. {entry['score']} pts   Rank {entry['rank']}   Wave {entry['wave_reached']}",
                    16,
                    leaderboard_rect.x + 18,
                    run_y,
                    WHITE,
                    align="topleft",
                    bold=index == 0,
                )
                meta = f"{entry['result'].title()} | {format_seconds(entry['duration_seconds'])} | Bosses {entry['bosses_destroyed']} | {entry['ended_at'][:10]}"
                self.draw_text(self.screen, meta, 14, leaderboard_rect.x + 18, run_y + 20, (176, 188, 206), align="topleft")
                run_y += 48
        else:
            self.draw_text(self.screen, "No runs logged for this mode yet.", 18, leaderboard_rect.centerx, leaderboard_rect.centery - 14, WHITE)
            self.draw_text(self.screen, "Launch it from here or the mode select screen to seed the board.", 15, leaderboard_rect.centerx, leaderboard_rect.centery + 18, (176, 188, 206))

        self.draw_text(self.screen, "Esc returns. Enter launches the selected mode if it is unlocked.", 16, SCREEN_WIDTH / 2, 520, (176, 188, 206))

    def draw_wave_intro(self):
        theme = self.level_theme
        self.draw_background(self.screen)
        panel = pygame.Rect(102, 178, SCREEN_WIDTH - 204, 188)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, self.wave_intro_lines[0], 36, SCREEN_WIDTH / 2, 214, theme["title"], bold=True)
        self.draw_text(self.screen, self.wave_intro_lines[1], 22, SCREEN_WIDTH / 2, 268, theme["warning"])
        self.draw_text(self.screen, self.wave_intro_lines[2], 18, SCREEN_WIDTH / 2, 312, WHITE)
        self.draw_text(self.screen, "Press Enter to deploy immediately.", 18, SCREEN_WIDTH / 2, 344, SUCCESS_COLOR)

    def draw_gameplay(self):
        self.draw_background(self.world_surface)
        self.all_sprites.draw(self.world_surface)
        self.draw_hud(self.world_surface)
        self.draw_status_banner(self.world_surface)
        self.draw_tutorial_card(self.world_surface)

        offset_x = offset_y = 0
        if self.shake_frames > 0 and self.shake_strength > 0:
            offset_x = random.randint(-self.shake_strength, self.shake_strength)
            offset_y = random.randint(-self.shake_strength, self.shake_strength)

        self.screen.fill(BLACK)
        self.screen.blit(self.world_surface, (offset_x, offset_y))

        if self.flash_alpha > 0:
            flash = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            flash.fill((*self.flash_color, self.flash_alpha))
            self.screen.blit(flash, (0, 0))

    def draw_paused_screen(self):
        self.draw_gameplay()
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 8, 16, 165))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(162, 102, SCREEN_WIDTH - 324, SCREEN_HEIGHT - 204)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, "Paused", 44, SCREEN_WIDTH / 2, 146, TITLE_COLOR, bold=True)
        self.draw_menu(self.screen, ["Resume", "How To Play", "Options", "Abandon Run"], self.pause_menu_index, 248)
        self.draw_text(self.screen, "Press P to resume instantly.", 18, SCREEN_WIDTH / 2, 454, SUCCESS_COLOR)

    def ending_copy(self):
        if self.game_phase == "victory" or self.run_end_reason == "victory":
            return "Sector Seven Holds", "Matriarch Prime is broken.", SUCCESS_COLOR
        if self.run_end_reason == "timeout":
            return "Strike Clock Expired", "The strike clock hit zero before Matriarch Prime fell.", DANGER_COLOR
        if self.run_end_reason == "abandoned":
            return "Run Aborted", "The run was abandoned before Matriarch Prime fell.", DANGER_COLOR
        return "Defence Line Lost", "Every defence ship is gone.", DANGER_COLOR

    def draw_ending_screen(self):
        heading, subtitle, heading_color = self.ending_copy()
        self.draw_background(self.screen)
        panel = pygame.Rect(86, 36, SCREEN_WIDTH - 172, SCREEN_HEIGHT - 72)
        self.draw_panel(self.screen, panel)
        self.draw_text(self.screen, heading, 42, SCREEN_WIDTH / 2, 64, heading_color, bold=True)
        self.draw_text(self.screen, subtitle, 18, SCREEN_WIDTH / 2, 112, WHITE)
        self.draw_text(self.screen, self.current_mode()["label"], 20, SCREEN_WIDTH / 2, 140, TITLE_COLOR, bold=True)
        self.draw_text(self.screen, f"Final Score  {self.score}", 28, SCREEN_WIDTH / 2, 168, WHITE, bold=True)
        self.draw_text(
            self.screen,
            f"High Score  {self.high_score}    Rating  {self.rank_label}",
            20,
            SCREEN_WIDTH / 2,
            206,
            WARNING_COLOR,
        )

        stats_y = 232
        summary = [
            f"Time in lane        {format_seconds(self.play_frames / 60)}",
            f"Waves cleared       {self.stats['waves_cleared']}",
            f"Mushrooms cleared   {self.stats['mushrooms_cleared']}",
            f"Segments shattered  {self.stats['segments_destroyed']}",
            f"Special kills       {self.stats['specials_destroyed']}",
            f"Bosses broken       {self.stats['bosses_destroyed']}",
            f"Best multiplier     {self.best_multiplier}x",
        ]
        for line in summary:
            self.draw_text(self.screen, line, 18, SCREEN_WIDTH / 2, stats_y, WHITE)
            stats_y += 20

        notes = self.run_record_highlights[:1] + self.run_unlocks[:2]
        for note in notes[:3]:
            note_color = SUCCESS_COLOR if "unlocked" in note.lower() else WARNING_COLOR
            self.draw_text(self.screen, note, 16, SCREEN_WIDTH / 2, stats_y + 4, note_color, bold=True)
            stats_y += 18
        self.draw_menu(self.screen, ["Retry", "Run Records", "Title Screen", "Quit"], self.game_over_menu_index, max(456, stats_y + 8))

    def draw_game_over_screen(self):
        self.draw_ending_screen()

    def draw_victory_screen(self):
        self.draw_ending_screen()

    def render(self):
        if self.game_phase == "title":
            self.draw_title_screen()
        elif self.game_phase == "mode_select":
            self.draw_mode_select_screen()
        elif self.game_phase == "briefing":
            self.draw_briefing_screen()
        elif self.game_phase == "help":
            self.draw_help_screen()
        elif self.game_phase == "records":
            self.draw_records_screen()
        elif self.game_phase == "options":
            self.draw_options_screen()
        elif self.game_phase == "wave_intro":
            self.draw_wave_intro()
        elif self.game_phase == "paused":
            self.draw_paused_screen()
        elif self.game_phase == "game_over":
            self.draw_game_over_screen()
        elif self.game_phase == "victory":
            self.draw_victory_screen()
        else:
            self.draw_gameplay()
        pygame.display.flip()

    async def run_async(self):
        smoke_test_frames = 0
        browser_frame_logged = False
        while self.running:
            self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event.key)
                elif event.type == pygame.KEYUP:
                    self.handle_keyup(event.key)

            self.update()
            self.sync_music()
            self.render()

            if IS_WEB and not browser_frame_logged:
                browser_frame_logged = True
                surface = pygame.display.get_surface()
                web_debug_event(
                    "swarmbreaker:web-frame",
                    {
                        "phase": self.game_phase,
                        "mode": self.current_mode_id,
                        "playFrames": self.play_frames,
                        "status": self.status_message,
                        "surface": list(surface.get_size()) if surface else None,
                    },
                )

            if HEADLESS_SMOKE_TEST:
                smoke_test_frames += 1
                if smoke_test_frames >= SMOKE_TEST_FRAME_LIMIT:
                    self.running = False

            await asyncio.sleep(0)

        self.save_high_score()

    def run(self):
        asyncio.run(self.run_async())


async def async_main():
    try:
        render_boot_probe("Starting engine", "Instantiating desktop-compatible browser prototype.")
        await asyncio.sleep(0)
        game = Game()
        await game.run_async()
    except Exception as exc:
        web_debug_event("swarmbreaker:web-crash", {"error": repr(exc)})
        web_console_error("swarmbreaker:web-crash", repr(exc))
        raise
    finally:
        pygame.quit()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
