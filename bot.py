import os
import sqlite3
import threading
from datetime import datetime, timedelta

from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# 기본 설정
# =========================================================

DB_FILE = "schedule.db"

JOBS = [
    "드루이드",
    "사냥꾼",
    "마법사",
    "성기사",
    "사제",
    "도적",
    "주술사",
    "흑마법사",
    "전사",
]

# 불성 클래식 레이드 종류 (줄임말 적용)
RAIDS = [
    "카라잔 (10인)",
    "줄아만 (10인)",
    "불뱀 (25인)",
    "폭요 (25인)",
    "하이잘 (25인)",
    "검사 (25인)",
    "태샘 (25인)",
    "기타 / 자유",
]


# =========================================================
# Flask - Render 포트 유지용
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


def run_flask():
    app.run(host="0.0.0.0", port=8080)


# =========================================================
# Database
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            discord_user_id INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            job TEXT NOT NULL,
            raid TEXT NOT NULL,
            schedule_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, discord_user_id, nickname, schedule_date, raid)
        )
    """)
    conn.commit()
    conn.close()


def add_schedule(guild_id, user_id, nickname, job, raid, schedule_date):
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        cursor = conn.execute("""
            INSERT INTO schedules (
                guild_id, discord_user_id, nickname, job, raid, schedule_date, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (guild_id, user_id, nickname, job, raid, schedule_date, now, now))
        conn.commit()
        schedule_id = cursor.lastrowid
        conn.close()
        return schedule_id
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_user_schedules(guild_id, user_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM schedules WHERE guild_id = ? AND discord_user_id = ? ORDER BY schedule_date ASC, nickname ASC
    """, (guild_id, user_id)).fetchall()
    conn.close()
    return rows


def get_all_schedules(guild_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM schedules WHERE guild_id = ? ORDER BY schedule_date ASC, nickname ASC
    """, (guild_id,)).fetchall()
    conn.close()
    return rows


def get_schedule(schedule_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    conn.close()
    return row


def update_schedule(schedule_id, job, raid, schedule_date):
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        cursor = conn.execute("""
            UPDATE schedules SET job = ?, raid = ?, schedule_date = ?, updated_at = ? WHERE id = ?
        """, (job, raid, schedule_date, now, schedule_id))
        conn.commit()
        changed = cursor.rowcount > 0
        conn.close()
        return changed
    except sqlite3.IntegrityError:
        conn.close()
        return False


def delete_schedule(schedule_id):
    conn = get_db()
    cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def format_date(date_string):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"]
    return date_obj.strftime("%m/%d") + f" ({weekday[date_obj.weekday()]})"


def get_date_options():
    today = datetime.now().date()
    dates = []
    for i in range(7):
        date_obj = today + timedelta(days=i)
        dates.append({
            "value": date_obj.strftime("%Y-%m-%d"),
            "label": date_obj.strftime("%m/%d") + " (" + ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()] + ")"
        })
    return dates


def is_server_admin(member):
    if not isinstance(member, discord.Member):
        return False
    return member.guild_permissions.manage_guild


# =========================================================
# UI 컴포넌트 (Ephemeral 적용)
# =========================================================

class RaidSelect(discord.ui.Select):
    def __init__(self, callback_function):
        options = [discord.SelectOption(label=raid, value=raid) for raid in RAIDS]
        super().__init__(placeholder="레이드를 선택하세요", min_values=1, max_values=1, options=options)
        self.callback_function = callback_function

    async def callback(self, interaction: discord.Interaction):
        await self.callback_function(interaction, self.values[0])


class RaidSelectView(discord.ui.View):
    def __init__(self, nickname, user_id, guild_id, mode="register", schedule_id=None):
        super().__init__(timeout=180)
        self.nickname = nickname
        self.user_id = user_id
        self.guild_id = guild_id
        self.mode = mode
        self.schedule_id = schedule_id
        self.add_item(RaidSelect(self.raid_selected))

    async def raid_selected(self, interaction, raid):
        await interaction.response.edit_message(
            content=f"선택 레이드: **{raid}**\n이제 직업을 선택해주세요.",
            view=JobSelectView(self.nickname, self.user_id, self.guild_id, raid, self.mode, self.schedule_id)
        )


class JobSelect(discord.ui.Select):
    def __init__(self, callback_function):
        options = [discord.SelectOption(label=job, value=job) for job in JOBS]
        super().__init__(placeholder="직업을 선택하세요", min_values=1, max_values=1, options=options)
        self.callback_function = callback_function

    async def callback(self, interaction: discord.Interaction):
        await self.callback_function(interaction, self.values[0])


class JobSelectView(discord.ui.View):
    def __init__(self, nickname, user_id, guild_id, raid, mode="register", schedule_id=None):
        super().__init__(timeout=180)
        self.nickname = nickname
        self.user_id = user_id
        self.guild_id = guild_id
        self.raid = raid
        self.mode = mode
        self.schedule_id = schedule_id
        self.add_item(JobSelect(self.job_selected))

    async def job_selected(self, interaction, job):
        if self.mode == "register":
            await interaction.response.edit_message(
                content=f"레이드: **{self.raid}** / 직업: **{job}** 선택 완료!\n이제 날짜를 선택해주세요.",
                view=DateSelectView(self.nickname, self.user_id, self.guild_id, self.raid, job, "register")
            )
        elif self.mode == "edit":
            await interaction.response.edit_message(
                content=f"새 레이드: **{self.raid}** / 새 직업: **{job}**\n새 날짜를 선택해주세요.",
                view=DateSelectView(self.nickname, self.user_id, self.guild_id, self.raid, job, "edit", self.schedule_id)
            )


class DateSelectView(discord.ui.View):
    def __init__(self, nickname, user_id, guild_id, raid, job, mode="register", schedule_id=None):
        super().__init__(timeout=180)
        self.nickname = nickname
        self.user_id = user_id
        self.guild_id = guild_id
        self.raid = raid
        self.job = job
        self.mode = mode
        self.schedule_id = schedule_id
        self.selected_date = None

        dates = get_date_options()
        for index, date_info in enumerate(dates):
            button = discord.ui.Button(
                label=date_info["label"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"schedule_date_{index}"
            )

            async def button_callback(interaction, date_value=date_info["value"], button_ref=button):
                self.selected_date = date_value
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.style != discord.ButtonStyle.success:
                        child.style = discord.ButtonStyle.secondary
                button_ref.style = discord.ButtonStyle.primary

                await interaction.response.edit_message(
                    content=(
                        f"닉네임: **{self.nickname}**\n"
                        f"레이드: **{self.raid}**\n"
                        f"직업: **{self.job}**\n"
                        f"선택한 날짜: **{format_date(self.selected_date)}**\n\n"
                        f"아래 **등록 완료** 버튼을 눌러주세요."
                    ),
                    view=self
                )

            button.callback = button_callback
            self.add_item(button)

        confirm_button = discord.ui.Button(label="등록 완료", style=discord.ButtonStyle.success, row=2)

        async def confirm_callback(interaction):
            if self.selected_date is None:
                await interaction.response.send_message("❌ 날짜를 먼저 선택해주세요.", ephemeral=True)
                return

            if self.mode == "register":
                result = add_schedule(self.guild_id, self.user_id, self.nickname, self.job, self.raid, self.selected_date)
                if result is None:
                    await interaction.response.edit_message(content="❌ 이미 같은 레이드/날짜에 등록된 일정이 있습니다.", view=None)
                    return
                await interaction.response.edit_message(
                    content=f"✅ 일정이 등록되었습니다!\n\n닉네임: **{self.nickname}**\n레이드: **{self.raid}**\n직업: **{self.job}**\n날짜: **{format_date(self.selected_date)}**",
                    view=None
                )
            elif self.mode == "edit":
                success = update_schedule(self.schedule_id, self.job, self.raid, self.selected_date)
                if not success:
                    await interaction.response.edit_message(content="❌ 수정할 수 없습니다.", view=None)
                    return
                await interaction.response.edit_message(
                    content=f"✅ 일정이 수정되었습니다!\n\n레이드: **{self.raid}**\n직업: **{self.job}**\n날짜: **{format_date(self.selected_date)}**",
                    view=None
                )

        confirm_button.callback = confirm_callback
        self.add_item(confirm_button)


class ScheduleSelect(discord.ui.Select):
    def __init__(self, schedules, callback_function):
        options = []
        for schedule in schedules[:25]:
            options.append(
                discord.SelectOption(
                    label=f"[{schedule['raid']}] {schedule['nickname']} / {schedule['job']} / {format_date(schedule['schedule_date'])}"[:100],
                    value=str(schedule["id"])
                )
            )
        super().__init__(placeholder="일정을 선택하세요", min_values=1, max_values=1, options=options)
        self.callback_function = callback_function

    async def callback(self, interaction: discord.Interaction):
        await self.callback_function(interaction, int(self.values[0]))


class ScheduleSelectView(discord.ui.View):
    def __init__(self, schedules, mode="edit"):
        super().__init__(timeout=180)
        self.schedules = schedules
        self.mode = mode
        self.add_item(ScheduleSelect(schedules, self.schedule_selected))

    async def schedule_selected(self, interaction, schedule_id):
        schedule = get_schedule(schedule_id)
        if not schedule or schedule["guild_id"] != interaction.guild.id:
            await interaction.response.send_message("❌ 일정을 찾을 수 없습니다.", ephemeral=True)
            return
        if schedule["discord_user_id"] != interaction.user.id and not is_server_admin(interaction.user):
            await interaction.response.send_message("❌ 권한이 없습니다.", ephemeral=True)
            return

        if self.mode == "edit":
            await interaction.response.send_message(
                f"수정할 일정\n현재 레이드: **{schedule['raid']}**\n새 레이드를 선택해주세요.",
                view=RaidSelectView(schedule["nickname"], schedule["discord_user_id"], schedule["guild_id"], mode="edit", schedule_id=schedule["id"]),
                ephemeral=True
            )
        elif self.mode == "delete":
            await interaction.response.send_message(
                f"정말 이 일정을 삭제할까요?\n[{schedule['raid']}] {schedule['nickname']} / {schedule['job']} / {format_date(schedule['schedule_date'])}",
                view=DeleteConfirmView(schedule["id"]),
                ephemeral=True
            )


class DeleteConfirmView(discord.ui.View):
    def __init__(self, schedule_id):
        super().__init__(timeout=60)
        self.schedule_id = schedule_id
        
        yes_btn = discord.ui.Button(label="삭제", style=discord.ButtonStyle.danger)
        no_btn = discord.ui.Button(label="취소", style=discord.ButtonStyle.secondary)

        async def yes_cb(interaction):
            if delete_schedule(self.schedule_id):
                await interaction.response.edit_message(content="✅ 일정이 삭제되었습니다.", view=None)
            else:
                await interaction.response.edit_message(content="❌ 삭제 실패", view=None)

        async def no_cb(interaction):
            await interaction.response.edit_message(content="❎ 취소되었습니다.", view=None)

        yes_btn.callback = yes_cb
        no_btn.callback = no_cb
        self.add_item(yes_btn)
        self.add_item(no_btn)


# =========================================================
# Bot 설정 및 슬래시 커맨드 (Slash Commands)
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands(s)")
    except Exception as e:
        print(e)
    print(f"로그인 성공: {bot.user}")


@bot.tree.command(name="등록", description="레이드 일정을 등록합니다.")
@app_commands.describe(nickname="게임 내 닉네임")
async def slash_register(interaction: discord.Interaction, nickname: str):
    # ephemeral=True로 설정하여 명령어 입력자에게만 오직 보임
    await interaction.response.send_message(
        f"**{nickname.strip()}** 님의 일정을 등록합니다.\n참여할 **레이드**를 선택해주세요.",
        view=RaidSelectView(
            nickname=nickname.strip(),
            user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            mode="register"
        ),
        ephemeral=True
    )


@bot.tree.command(name="일정", description="서버 또는 특정 닉네임의 일정을 확인합니다.")
@app_commands.describe(nickname="특정 닉네임 (선택사항)")
async def slash_schedule(interaction: discord.Interaction, nickname: str = None):
    schedules = get_all_schedules(interaction.guild.id)
    if nickname:
        nickname = nickname.strip()
        schedules = [s for s in schedules if s["nickname"] == nickname]

    if not schedules:
        await interaction.response.send_message("📅 등록된 일정이 없습니다.", ephemeral=True)
        return

    grouped = {}
    for s in schedules:
        date = s["schedule_date"]
        raid = s["raid"]
        if date not in grouped:
            grouped[date] = {}
        if raid not in grouped[date]:
            grouped[date][raid] = []
        grouped[date][raid].append(s)

    embed = discord.Embed(title="📅 레이드 일정표", color=discord.Color.blue())
    for date in sorted(grouped.keys()):
        raid_texts = []
        for raid in sorted(grouped[date].keys()):
            members = [f"{m['nickname']} ({m['job']})" for m in grouped[date][raid]]
            raid_texts.append(f"🔹 **{raid}**\n" + ", ".join(members))

        embed.add_field(name=format_date(date), value="\n".join(raid_texts), inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="내일정", description="내가 등록한 일정을 확인합니다.")
async def slash_my_schedule(interaction: discord.Interaction):
    schedules = get_user_schedules(interaction.guild.id, interaction.user.id)
    if not schedules:
        await interaction.response.send_message("📅 등록한 일정이 없습니다.", ephemeral=True)
        return

    grouped = {}
    for s in schedules:
        date = s["schedule_date"]
        raid = s["raid"]
        if date not in grouped:
            grouped[date] = {}
        if raid not in grouped[date]:
            grouped[date][raid] = []
        grouped[date][raid].append(s)

    embed = discord.Embed(title=f"📅 {interaction.user.display_name}님의 일정", color=discord.Color.blue())
    for date in sorted(grouped.keys()):
        raid_texts = []
        for raid in sorted(grouped[date].keys()):
            members = [f"{m['nickname']} ({m['job']})" for m in grouped[date][raid]]
            raid_texts.append(f"🔹 **{raid}**\n" + ", ".join(members))

        embed.add_field(name=format_date(date), value="\n".join(raid_texts), inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="수정", description="등록한 일정을 수정합니다.")
async def slash_edit(interaction: discord.Interaction):
    schedules = get_all_schedules(interaction.guild.id) if is_server_admin(interaction.user) else get_user_schedules(interaction.guild.id, interaction.user.id)
    if not schedules:
        await interaction.response.send_message("❌ 수정할 일정이 없습니다.", ephemeral=True)
        return
    await interaction.response.send_message("🛠️ 수정할 일정을 선택해주세요.", view=ScheduleSelectView(schedules, mode="edit"), ephemeral=True)


@bot.tree.command(name="삭제", description="등록한 일정을 삭제합니다.")
async def slash_delete(interaction: discord.Interaction):
    schedules = get_all_schedules(interaction.guild.id) if is_server_admin(interaction.user) else get_user_schedules(interaction.guild.id, interaction.user.id)
    if not schedules:
        await interaction.response.send_message("❌ 삭제할 일정이 없습니다.", ephemeral=True)
        return
    await interaction.response.send_message("🗑️ 삭제할 일정을 선택해주세요.", view=ScheduleSelectView(schedules, mode="delete"), ephemeral=True)


if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ DISCORD_TOKEN 환경변수가 없습니다.")
