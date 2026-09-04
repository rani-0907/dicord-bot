import os
import threading
from datetime import datetime, timedelta
from flask import Flask
import discord
from discord.ext import commands

# 1. Render 헬스체크(웹 서비스 포트 유지)를 위한 간단한 Flask 서버 설정
app = Flask("")


@app.route("/")
def home():
  return "Bot is running!"


def run_flask():
  # Render는 기본적으로 8080 포트를 사용합니다.
  app.run(host="0.0.0.0", port=8080)


# 2. 디스코드 봇 설정
intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용 읽기 권한 필요
bot = commands.Bot(command_prefix="!", intents=intents)


# 3. 달력 스타일 날짜 선택 UI 클래스
class DateSelectView(discord.ui.View):

  def __init__(self, nickname):
    super().__init__(timeout=180)
    self.nickname = nickname
    self.selected_date = None

    # 오늘부터 7일간의 날짜 동적 생성
    today = datetime.now().date()
    for i in range(7):
      target_date = today + timedelta(days=i)
      label = target_date.strftime("%m/%d (%a)")  # 예: 09/04 (금)
      self.add_date_button(target_date, label)

  def add_date_button(self, target_date, label):
    button = discord.ui.Button(
        label=label,
        style=discord.ButtonStyle.secondary,  # 기본 회색
        row=len(self.children) // 5,  # 한 줄에 최대 5개씩 배치
    )

    async def button_callback(interaction: discord.Interaction):
      # 다른 모든 날짜 버튼을 기본(회색)으로 되돌림
      for child in self.children:
        if isinstance(child, discord.ui.Button) and child.label != "선택 완료 (확인)":
          child.style = discord.ButtonStyle.secondary

      # 클릭한 버튼만 진한 색(파란색)으로 변경
      button.style = discord.ButtonStyle.primary
      self.selected_date = target_date

      # UI 업데이트 반영
      await interaction.response.edit_message(view=self)

    button.callback = button_callback
    self.add_item(button)

  # 하단에 '확인' 버튼 추가
  @discord.ui.Button(
      label="선택 완료 (확인)", style=discord.ButtonStyle.success, row=4
  )
  async def confirm_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not self.selected_date:
      await interaction.response.send_message(
          "날짜를 먼저 선택해주세요!", ephemeral=True
      )
      return

    # 선택 완료 후 안내 메시지 출력
    await interaction.response.send_message(
        f"✅ **{self.selected_date}** 선택 완료!\n이제 상태를 입력해 주세요: "
        f"`!일정등록 {self.nickname} {self.selected_date} [상태]`",
        ephemeral=True,
    )


# 4. 봇 이벤트 및 명령어
@bot.event
async def on_ready():
  print(f"로그인 완료: {bot.user} (ID: {bot.user.id})")


@bot.command(name="일정")
async def schedule_command(ctx, *, nickname: str = "라니새싹"):
  """!일정 명령어를 치면 오늘부터 7일간의 달력 버튼이 뜸"""
  view = DateSelectView(nickname)
  await ctx.send(
      "📅 등록할 날짜를 선택한 뒤 **선택 완료 (확인)** 버튼을 눌러주세요:", view=view
  )


# 5. 실행부 (Flask 백그라운드 스레드 + 디스코드 봇 실행)
if __name__ == "__main__":
  # Flask 서버를 별도 스레드로 실행 (Render 차단 방지)
  flask_thread = threading.Thread(target=run_flask)
  flask_thread.daemon = True
  flask_thread.start()

  # Render 환경변수에 등록된 디스코드 토큰 가져오기
  token = os.environ.get("DISCORD_TOKEN")

  if token:
    bot.run(token)
  else:
    print(
        "오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다. Render 설정에서"
        " 토큰을 확인해주세요."
    )
