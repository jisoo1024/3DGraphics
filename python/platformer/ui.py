"""Korean UI with an English fallback when no Hangul font is installed."""
from pathlib import Path

import numpy as np
import pygame
from OpenGL.GL import *  # noqa: F401,F403

from renderer import Program
from scene import ROOT
from .inventory import ITEMS
from .progress import Screen


def format_time(seconds):
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


class UI:
    def __init__(self, renderer, width, height):
        self.width, self.height = width, height
        candidates = [Path(ROOT) / "assets/font/Maplestory Light.ttf",
                      Path(ROOT) / "assets/font/Maplestory Bold.ttf",
                      Path(ROOT) / "assets/fonts/NotoSansKR-Regular.ttf",
                      Path("C:/Windows/Fonts/malgun.ttf")]
        font_path = next((str(path) for path in candidates if path.exists()), None)
        if font_path is None:
            font_path = pygame.font.match_font("malgungothic,nanumgothic,notosanscjkkr,applegothic,undotum")
        self.korean = font_path is not None
        bold_path = Path(ROOT) / "assets/font/Maplestory Bold.ttf"
        self.fonts = {size: pygame.font.Font(
            str(bold_path) if size >= 28 and bold_path.exists() else font_path, size)
            for size in (18, 22, 28, 42, 60)}
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.buttons = []
        self.program = Program("""#version 330 core
out vec2 uv;
void main() { vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);
uv=p; gl_Position=vec4(p*2.0-1.0,0,1); }
""", """#version 330 core
in vec2 uv; out vec4 frag; uniform sampler2D text_tex;
void main(){frag=texture(text_tex,vec2(uv.x,1.0-uv.y));}
""")
        self.vao = glGenVertexArrays(1)
        self.texture = renderer._texture_from_rgba(np.zeros((height, width, 4), np.uint8))
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)

    def t(self, korean, english):
        return korean if self.korean else english

    def text(self, text, xy, size=22, color=(240, 244, 225)):
        self.surface.blit(self.fonts[size].render(str(text), True, color), xy)

    def panel(self, rect, color=(22, 39, 36, 235)):
        pygame.draw.rect(self.surface, color, rect, border_radius=14)

    def button(self, rect, label, action):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        self.panel(rect, (87, 130, 98, 255) if hover else (55, 88, 72, 255))
        self.text(label, (rect.x + 16, rect.y + 11))
        self.buttons.append((rect, action))

    def click(self, position):
        return next((action for rect, action in reversed(self.buttons) if rect.collidepoint(position)), None)

    def draw(self, session, world, fps=0, debug=False):
        self.buttons.clear()
        self.surface.fill((0, 0, 0, 0))
        progress, profile = session.progress, session.profile
        screen = progress.screen
        meso = profile["meso"]
        if screen == Screen.PLAYING:
            self.panel((18, 16, 570, 118))
            self.text(world.stage.name if self.korean else f"STAGE {progress.stage_index + 1}", (34, 25), 28)
            self.text(f"{format_time(progress.elapsed)}    {meso:,} " + self.t("메소", "meso"), (34, 69))
            self.text(self.t("목표: 금빛 도착 구역까지 이동하세요", "Goal: reach the golden gate"), (34, 102), 18)
            self.panel((18, 650, 1000, 48))
            hint = self.t("WASD 이동 · Space 점프 · 마우스 시점 · Esc 메뉴", "WASD move / Space jump / Mouse look / Esc menu")
            if world.player.rope:
                hint = self.t("로프: W/S 오르내리기 · Space 놓고 점프", "Rope: W/S climb / Space release and jump")
            elif world.near_rope():
                hint += self.t(" · E 로프 잡기", " / E grab rope")
            self.text(hint, (34, 662))
            if world.player.invulnerability_left > 0:
                self.panel((450, 150, 390, 48), (125, 51, 62, 235))
                status = self.t("피격! 잠시 무적 상태입니다", "Hit! Briefly invulnerable")
                self.text(status, (468, 160))
            if debug:
                p = world.player
                self.panel((850, 18, 410, 84))
                self.text(f"FPS {fps:.0f} | grounded {p.grounded}", (864, 27), 18)
                self.text(f"vy {p.velocity[1]:+.2f} | {p.state} | bananas {len(world.projectiles)}", (864, 58), 18)
        else:
            self.surface.fill((8, 20, 21, 150))
            if screen == Screen.LOBBY:
                self.panel((55, 55, 560, 600))
                self.text(self.t("3D 인내의 숲", "FOREST OF PATIENCE"), (82, 85), 42)
                self.text(self.t("두 개의 숲, 한 번의 도전", "Two forests. One challenge."), (82, 155), 28)
                self.text(f"{meso:,} " + self.t("메소", "meso"), (82, 207), 28)
                best = profile["best_time"]
                self.text(self.t("최고 기록: ", "Best: ") + (format_time(best) if best is not None else "--:--"), (310, 210))
                for i, (ko, en, action) in enumerate((("도전 시작", "Start challenge", "start"),
                         ("상점", "Shop", "shop"), ("조작법", "Controls", "help"),
                         ("설정", "Settings", "settings"), ("게임 종료", "Quit", "quit"))):
                    self.button((82, 265 + i * 66, 500, 52), self.t(ko, en), action)
            elif screen == Screen.PAUSED:
                self.panel((380, 120, 520, 500))
                self.text(self.t("잠시 쉬어가기", "Paused"), (425, 150), 42)
                for i, (ko, en, action) in enumerate((("게임 재개", "Resume", "resume"),
                        ("로비로 복귀 (도전 포기)", "Abandon to lobby", "lobby"),
                        ("설정", "Settings", "settings"), ("게임 종료", "Quit", "quit"))):
                    self.button((415, 250 + i * 78, 450, 56), self.t(ko, en), action)
            elif screen == Screen.RESULTS:
                self.panel((340, 100, 600, 520))
                self.text(self.t("숲을 통과했습니다!", "Challenge complete!"), (390, 145), 42)
                self.text(self.t("클리어 시간  ", "Clear time  ") + format_time(progress.elapsed), (400, 255), 28)
                self.text(self.t("획득 메소  ", "Reward  ") + f"{progress.reward:,}", (400, 320), 28)
                self.text(self.t("보유 메소  ", "Balance  ") + f"{meso:,}", (400, 385), 28)
                self.button((400, 500, 480, 60), self.t("로비로 돌아가기", "Return to lobby"), "lobby")
            elif screen == Screen.SHOP:
                self.text(self.t("숲의 상점", "Forest shop"), (55, 42), 42)
                self.text(f"{meso:,} " + self.t("메소", "meso"), (1020, 60), 28)
                for i, item in enumerate(ITEMS):
                    x, y = 55 + (i % 3) * 395, 125 + (i // 3) * 225
                    self.panel((x, y, 375, 205))
                    self.text(item.name if self.korean else item.id.replace("_", " "), (x + 20, y + 12), 28)
                    self.preview(item, (x + 55, y + 100))
                    owned = item.id in profile["owned"]
                    equipped = profile["equipped"].get(item.slot) == item.id
                    self.text(self.t("장착 중" if equipped else "보유 중" if owned else f"{item.price} 메소",
                                         "Equipped" if equipped else "Owned" if owned else f"{item.price} meso"), (x + 125, y + 80))
                    label = self.t("해제" if equipped else "장착" if owned else "구매",
                                   "Unequip" if equipped else "Equip" if owned else "Buy")
                    self.button((x + 120, y + 140, 230, 48), label,
                                ("equip:" if owned else "buy:") + item.id)
                self.button((55, 620, 230, 55), self.t("뒤로", "Back"), "back")
            elif screen == Screen.SETTINGS:
                self.panel((310, 65, 660, 590))
                self.text(self.t("설정", "Settings"), (360, 95), 42)
                for i, (key, ko, en, amount) in enumerate((("bgm", "배경 음악", "BGM", 0.1),
                        ("sfx", "효과음", "Effects", 0.1), ("sensitivity", "마우스 감도", "Sensitivity", 0.2))):
                    y = 205 + i * 85
                    self.text(self.t(ko, en), (360, y + 8), 28)
                    self.text(f"{profile['options'][key]:.1f}", (660, y + 8), 28)
                    self.button((745, y, 65, 52), "-", f"option:{key}:-{amount}")
                    self.button((830, y, 65, 52), "+", f"option:{key}:{amount}")
                self.button((360, 470, 535, 55), self.t("그림자: ", "Shadows: ")
                            + ("ON" if profile["options"]["shadows"] else "OFF"), "option:shadows:0")
                self.button((360, 565, 535, 55), self.t("돌아가기", "Back"), "back")
            elif screen == Screen.HELP:
                self.panel((160, 75, 960, 570))
                self.text(self.t("숲을 걷는 방법", "How to cross the forest"), (210, 105), 42)
                ko = ("WASD: 이동 / Space: 점프 / 마우스: 시점 회전",
                      "Esc: 일시정지 / Tab: 커서 고정·해제 / F3: 디버그",
                      "E: 가까운 로프 잡기 / W·S: 로프 오르내리기",
                      "로프에서 Space: 놓고 점프 / 금빛 구역: 다음 스테이지",
                      "바나나를 피하세요. 원숭이가 빛나면 곧 던집니다.",
                      "가시는 높이 튕겨냅니다. 주 경로는 가시 없이도 통과할 수 있습니다.",
                      "낙하 시 시작점 복귀 / 클리어 보상으로 상점에서 치장을 구매하세요.")
                en = ("WASD: move / Space: jump / Mouse: look", "Esc: pause / Tab: cursor / F3: debug",
                      "E: grab nearby rope / W,S: climb", "Space on rope: release / Golden gate: next stage",
                      "Dodge bananas. A glowing monkey is about to throw.",
                      "Spikes launch you upward. The main path needs no spikes.",
                      "Falling returns to start. Earn meso to buy cosmetics.")
                for i, line in enumerate(ko if self.korean else en):
                    self.text(line, (210, 195 + i * 45), 22)
                self.button((210, 545, 850, 55), self.t("돌아가기", "Back"), "back")
        if session.message and screen != Screen.PLAYING:
            self.panel((310, 655, 940, 48))
            self.text(session.message if self.korean else "Notice: action processed / check balance and saved data.", (326, 666), 18)
        self.upload()

    def preview(self, item, center):
        x, y = center
        color = pygame.Color(item.color)
        pygame.draw.rect(self.surface, (225, 202, 147), (x - 19, y - 20, 38, 60), border_radius=7)
        if item.slot == "color":
            pygame.draw.rect(self.surface, color, (x - 19, y - 20, 38, 60), border_radius=7)
        elif item.slot == "hat":
            pygame.draw.polygon(self.surface, color, ((x - 30, y - 22), (x - 23, y - 55),
                                (x, y - 36), (x + 23, y - 55), (x + 30, y - 22)))
        else:
            pygame.draw.ellipse(self.surface, color, (x - 44, y - 18, 24, 45))
            pygame.draw.ellipse(self.surface, color, (x + 20, y - 18, 24, 45))

    def upload(self):
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.width, self.height,
                       GL_RGBA, GL_UNSIGNED_BYTE, pygame.image.tobytes(self.surface, "RGBA"))
        glViewport(0, 0, self.width, self.height)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glUseProgram(self.program.id)
        self.program.i("text_tex", 0)
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLES, 0, 3)
        glBindVertexArray(0)
        glDisable(GL_BLEND)
        glEnable(GL_CULL_FACE)
        glEnable(GL_DEPTH_TEST)
