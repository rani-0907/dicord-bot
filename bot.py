import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# 1. 24시간 유지를 위한 웹 서버 설정 (Render용)
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 2. 디스코드 인텐트 설정 (Message Content 필수)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 데이터를 저장할 공간
# 구조: { "닉네임": { "job": "직업", "월": "상태", "화": "상태", ... } }
raid_data = {}

# 💡 직업 선택 드롭다운 메뉴
class JobSelect(discord.ui.Select):
    def __init__(self, nickname):
        self.nickname = nickname
        options = [
            discord.SelectOption(label="드루이드", description="드루이드 캐릭터"),
            discord.SelectOption(label="사냥꾼", description="사냥꾼 캐릭터"),
            discord.SelectOption(label="마법사", description="마법사 캐릭터"),
            discord.SelectOption(label="성기사", description="성기사 캐릭터"),
            discord.SelectOption(label="사제", description="사제 캐릭터"),
            discord.SelectOption(label="도적", description="도적 캐릭터"),
            discord.SelectOption(label="주술사", description="주술사 캐릭터"),
            discord.SelectOption(label="흑마법사", description="흑마법사 캐릭터"),
            discord.SelectOption(label="전사", description="전사 캐릭터"),
        ]
        super().__init__(placeholder="직업을 선택해주세요!", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_job = self.values[0]
        
        if self.nickname not in raid_data:
            raid_data[self.nickname] = {}
        raid_data[self.nickname]["job"] = selected_job

        await interaction.response.send_message(
            f"✅ **[{selected_job}]** 선택 완료!\n이제 요일별 일정을 등록하려면 아래 형식으로 입력해 주세요:\n`!일정등록 {self.nickname} [요일] [상태]`\n*(예: `!일정등록 {self.nickname} 월요일 월양` 또는 `!일정등록 {self.nickname} 화요일 목완료`)*", 
            ephemeral=True
        )

class JobSelectView(discord.ui.View):
    def __init__(self, nickname):
        super().__init__()
        self.add_item(JobSelect(nickname))

@bot.event
async def on_ready():
    print(f'로그인 완료: {bot.user}')

@bot.command()
async def 안녕(ctx):
    await ctx.send('안녕하세요! 레이드 관리 봇입니다.')

# 💡 1단계: 등록 시작 (예: !등록시작 라니새싹)
@bot.command()
async def 등록시작(ctx, nickname: str):
    view = JobSelectView(nickname)
    await ctx.send(f"🎮 **{nickname}**님의 캐릭터 등록을 시작합니다. 아래 메뉴에서 **직업**을 선택해 주세요!", view=view)

# 💡 2단계: 요일별 일정 입력 (예: !일정등록 라니새싹 월요일 월양)
@bot.command()
async def 일정등록(ctx, nickname: str, day: str, status: str):
    valid_days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "월", "화", "수", "목", "금", "토", "일"]
    if day not in valid_days:
        await ctx.send("❌ 올바른 요일을 입력해주세요! (예: 월요일, 화요일 또는 월, 화)")
        return

    if nickname not in raid_data:
        raid_data[nickname] = {"job": "미정"}
    
    raid_data[nickname][day] = status
    await ctx.send(f"📅 **{nickname}**님의 **{day}** 일정이 **[{status}]**(으)로 등록되었습니다!")

# 💡 3단계: 전체 현황판 보기 (예: !현황)
@bot.command()
async def 현황(ctx):
    if not raid_data:
        await ctx.send("현재 등록된 레이드 데이터가 없습니다. `!등록시작 [닉네임]`으로 시작해 보세요!")
        return

    embed = discord.Embed(
        title="📊 레이드 공대원 요일별 현황판", 
        description="공대원들의 직업 및 요일별 일정 상태입니다.", 
        color=discord.Color.blurple()
    )
    
    for nickname, info in raid_data.items():
        job = info.get("job", "미정")
        schedule_list = [f"**{k}**: {v}" for k, v in info.items() if k != "job"]
        schedule_text = " | ".join(schedule_list) if schedule_list else "등록된 일정 없음"
        
        embed.add_field(name=f"[{job}] {nickname}", value=schedule_text, inline=False)
        
    await ctx.send(embed=embed)

# 💡 캐릭터 삭제 기능
@bot.command()
async def 캐릭터삭제(ctx, nickname: str):
    if nickname in raid_data:
        del raid_data[nickname]
        await ctx.send(f"🗑️ **{nickname}**님의 정보가 삭제되었습니다.")
    else:
        await ctx.send("❌ 등록되지 않은 닉네임입니다.")

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("DISCORD_TOKEN"))
