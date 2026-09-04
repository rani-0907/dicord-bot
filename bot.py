import os
import threading
from datetime import datetime, timedelta
from flask import Flask
import discord
from discord.ext import commands

# 1. Render 헬스체크(웹 서비스 포트 유지)를 위한 Flask 서버
app = Flask("")


@app.route("/")
def home():
  return "Bot is running!"


def run_flask():
  app.run(host="0.0.0.0", port=8080)


# 2. 디스코드 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# 3. [단계 2] 날짜 선택 뷰 (직업 선택 후 나타남)
class DateSelectView(discord.ui.View):

  def __init__(self, nickname, job):
    super().__init__(timeout=180)
    self.nickname = nickname
    self.job = job
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
      for child in self.children:
        if isinstance(child, discord.ui.Button) and child.label != "선택 완료 (확인)":
          child.style = discord.ButtonStyle.secondary

      button.style = discord.ButtonStyle.primary
      self.selected_date = target_date
      await interaction.response.edit_message(view=self)

    button.callback = button_callback
    self.add_item(button)

  @discord.ui.button(
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

    # 최종 완료 메시지
    await interaction.response.send_message(
        f"✅ **[{self.job}] {self.nickname}** - **{self.selected_date}** 선택 완료!\n"
        f"이제 상태를 입력해 주세요: `!일정등록 {self.nickname} {self.selected_date} [상태]`",
        ephemeral=True,
    )


# 2-1. [단계 1] 직업 선택 드롭다운 메뉴
class JobSelect(discord.ui.Select):

  def __init__(self, nickname):
    self.nickname = nickname
    options = [
        discord.SelectOption(label="드루이드", description="드루이드 선택"),
        discord.SelectOption(label="사냥꾼", description="사냥꾼 선택"),
        discord.SelectOption(label="마법사", description="마법사 선택"),
        discord.SelectOption(label="성기사", description="성기사 선택"),
        discord.SelectOption(label="사제", description="사제 선택"),
        discord.SelectOption(label="도적", description="도적 선택"),
        discord.SelectOption(label="주술사", description="주술사 선택"),
        discord.SelectOption(label="흑마법사", description="흑마법사 선택"),
        discord.SelectOption(label="전사", description="전사 선택"),
    ]
    super().__init__(
        placeholder="직업을 선택해주세요...", min_values=1, max_values=1, options=options
    )

  async def callback(self, interaction: discord.Interaction):
    selected_job = self.values[0]

    # 직업 선택 완료 후 -> 날짜 선택 뷰(DateSelectView)로 전환
    date_view = DateSelectView(self.nickname, selected_job)
    await interaction.response.edit_message(
        content=(
            f"✅ **[{selected_job}]** 선택 완료!\n📅 등록할 날짜를 선택한 뒤"
            " **선택 완료 (확인)** 버튼을 눌러주세요:"
        ),
        view=date_view,
    )


class JobSelectView(discord.ui.View):

  def __init__(self, nickname):
    super().__init__(timeout=180)
    self.add_item(JobSelect(nickname))


# 4. 명령어 등록: !등록 [닉네임]
@bot.command(name="등록")
async def register_command(ctx, *, nickname: str):
  view = JobSelectView(nickname)
  await ctx.send(
      f"🛡️ **{nickname}**님의 캐릭터 직업을 선택해주세요:", view=view
  )


@bot.event
async def on_ready():
  print(f"로그인 완료: {bot.user} (ID: {bot.user.id})")


# 5. 실행부
if __name__ == "__main__":
  flask_thread = threading.Thread(target=run_flask)
  flask_thread.daemon = True
  flask_thread.start()

  token = os.environ.get("DISCORD_TOKEN")
  if token:
    bot.run(token)
  else:
    print("오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
