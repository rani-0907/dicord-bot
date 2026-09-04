import os
import sqlite3
import threading
from datetime import datetime, timedelta

from flask import Flask
import discord
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
            schedule_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, discord_user_id, nickname, schedule_date)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# Database 함수
# =========================================================

def add_schedule(guild_id, user_id, nickname, job, schedule_date):
    conn = get_db()

    now = datetime.now().isoformat()

    try:
        cursor = conn.execute("""
            INSERT INTO schedules (
                guild_id,
                discord_user_id,
                nickname,
                job,
                schedule_date,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            guild_id,
            user_id,
            nickname,
            job,
            schedule_date,
            now,
            now
        ))

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
        SELECT *
        FROM schedules
        WHERE guild_id = ?
          AND discord_user_id = ?
        ORDER BY schedule_date ASC, nickname ASC
    """, (
        guild_id,
        user_id
    )).fetchall()

    conn.close()

    return rows


def get_all_schedules(guild_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM schedules
        WHERE guild_id = ?
        ORDER BY schedule_date ASC, nickname ASC
    """, (
        guild_id,
    )).fetchall()

    conn.close()

    return rows


def get_schedule(schedule_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM schedules
        WHERE id = ?
    """, (
        schedule_id,
    )).fetchone()

    conn.close()

    return row


def update_schedule(schedule_id, job, schedule_date):
    conn = get_db()

    now = datetime.now().isoformat()

    try:
        cursor = conn.execute("""
            UPDATE schedules
            SET job = ?,
                schedule_date = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            job,
            schedule_date,
            now,
            schedule_id
        ))

        conn.commit()

        changed = cursor.rowcount > 0

        conn.close()

        return changed

    except sqlite3.IntegrityError:
        conn.close()
        return False


def delete_schedule(schedule_id):
    conn = get_db()

    cursor = conn.execute("""
        DELETE FROM schedules
        WHERE id = ?
    """, (
        schedule_id,
    ))

    conn.commit()

    deleted = cursor.rowcount > 0

    conn.close()

    return deleted


# =========================================================
# 날짜 관련
# =========================================================

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


# =========================================================
# 권한 확인
# =========================================================

def is_server_admin(member):
    if not isinstance(member, discord.Member):
        return False

    return member.guild_permissions.manage_guild


# =========================================================
# 직업 선택
# =========================================================

class JobSelect(discord.ui.Select):

    def __init__(self, callback_function):
        self.callback_function = callback_function

        options = []

        for job in JOBS:
            options.append(
                discord.SelectOption(
                    label=job,
                    value=job
                )
            )

        super().__init__(
            placeholder="직업을 선택하세요",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_job = self.values[0]

        await self.callback_function(
            interaction,
            selected_job
        )


class JobSelectView(discord.ui.View):

    def __init__(
        self,
        nickname,
        user_id,
        guild_id,
        mode="register",
        schedule_id=None
    ):
        super().__init__(timeout=180)

        self.nickname = nickname
        self.user_id = user_id
        self.guild_id = guild_id
        self.mode = mode
        self.schedule_id = schedule_id

        self.add_item(
            JobSelect(self.job_selected)
        )

    async def job_selected(self, interaction, job):

        if self.mode == "register":

            await interaction.response.send_message(
                f"직업 **{job}** 선택 완료!\n"
                f"이제 날짜를 선택해주세요.",
                view=DateSelectView(
                    nickname=self.nickname,
                    user_id=self.user_id,
                    guild_id=self.guild_id,
                    job=job,
                    mode="register"
                ),
                ephemeral=True
            )

        elif self.mode == "edit":

            await interaction.response.send_message(
                f"새 직업: **{job}**\n"
                f"새 날짜를 선택해주세요.",
                view=DateSelectView(
                    nickname=self.nickname,
                    user_id=self.user_id,
                    guild_id=self.guild_id,
                    job=job,
                    mode="edit",
                    schedule_id=self.schedule_id
                ),
                ephemeral=True
            )


# =========================================================
# 날짜 선택
# =========================================================

class DateSelectView(discord.ui.View):

    def __init__(
        self,
        nickname,
        user_id,
        guild_id,
        job,
        mode="register",
        schedule_id=None
    ):
        super().__init__(timeout=180)

        self.nickname = nickname
        self.user_id = user_id
        self.guild_id = guild_id
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

            async def button_callback(
                interaction,
                date_value=date_info["value"],
                button_ref=button
            ):
                self.selected_date = date_value

                for child in self.children:
                    if isinstance(child, discord.ui.Button):
                        child.style = discord.ButtonStyle.secondary

                button_ref.style = discord.ButtonStyle.primary

                await interaction.response.edit_message(
                    content=(
                        f"닉네임: **{self.nickname}**\n"
                        f"직업: **{self.job}**\n"
                        f"선택한 날짜: **{format_date(self.selected_date)}**\n\n"
                        f"아래 **등록 완료** 버튼을 눌러주세요."
                    ),
                    view=self
                )

            button.callback = button_callback

            self.add_item(button)

        confirm_button = discord.ui.Button(
            label="등록 완료",
            style=discord.ButtonStyle.success,
            row=2
        )

        async def confirm_callback(interaction):

            if self.selected_date is None:

                await interaction.response.send_message(
                    "❌ 날짜를 먼저 선택해주세요.",
                    ephemeral=True
                )

                return

            if self.mode == "register":

                result = add_schedule(
                    self.guild_id,
                    self.user_id,
                    self.nickname,
                    self.job,
                    self.selected_date
                )

                if result is None:

                    await interaction.response.edit_message(
                        content=(
                            "❌ 이미 같은 날짜에 등록된 일정이 있습니다.\n\n"
                            f"닉네임: **{self.nickname}**\n"
                            f"날짜: **{format_date(self.selected_date)}**"
                        ),
                        view=None
                    )

                    return

                await interaction.response.edit_message(
                    content=(
                        "✅ 일정이 등록되었습니다!\n\n"
                        f"닉네임: **{self.nickname}**\n"
                        f"직업: **{self.job}**\n"
                        f"날짜: **{format_date(self.selected_date)}**"
                    ),
                    view=None
                )

            elif self.mode == "edit":

                schedule = get_schedule(self.schedule_id)

                if schedule is None:

                    await interaction.response.edit_message(
                        content="❌ 해당 일정을 찾을 수 없습니다.",
                        view=None
                    )

                    return

                # 본인 일정인지 다시 한번 확인
                if schedule["guild_id"] != self.guild_id:

                    await interaction.response.edit_message(
                        content="❌ 다른 서버의 일정은 수정할 수 없습니다.",
                        view=None
                    )

                    return

                if schedule["discord_user_id"] != self.user_id:

                    # 관리자가 수정하는 경우
                    member = interaction.guild.get_member(self.user_id)

                    # 여기서는 user_id가 실제 수정 대상 사용자이므로
                    # 관리자 여부는 interaction.user 기준으로 확인
                    if not is_server_admin(interaction.user):

                        await interaction.response.edit_message(
                            content="❌ 다른 사람의 일정은 수정할 수 없습니다.",
                            view=None
                        )

                        return

                success = update_schedule(
                    self.schedule_id,
                    self.job,
                    self.selected_date
                )

                if not success:

                    await interaction.response.edit_message(
                        content=(
                            "❌ 수정할 수 없습니다.\n"
                            "같은 닉네임으로 해당 날짜에 이미 일정이 있을 수 있습니다."
                        ),
                        view=None
                    )

                    return

                await interaction.response.edit_message(
                    content=(
                        "✅ 일정이 수정되었습니다!\n\n"
                        f"닉네임: **{schedule['nickname']}**\n"
                        f"직업: **{self.job}**\n"
                        f"날짜: **{format_date(self.selected_date)}**"
                    ),
                    view=None
                )

        confirm_button.callback = confirm_callback

        self.add_item(confirm_button)


# =========================================================
# 일정 선택
# =========================================================

class ScheduleSelect(discord.ui.Select):

    def __init__(self, schedules, callback_function):

        self.callback_function = callback_function

        options = []

        for schedule in schedules[:25]:

            options.append(
                discord.SelectOption(
                    label=(
                        f"{schedule['nickname']} / "
                        f"{schedule['job']} / "
                        f"{format_date(schedule['schedule_date'])}"
                    )[:100],
                    value=str(schedule["id"])
                )
            )

        super().__init__(
            placeholder="일정을 선택하세요",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        schedule_id = int(self.values[0])

        await self.callback_function(
            interaction,
            schedule_id
        )


class ScheduleSelectView(discord.ui.View):

    def __init__(
        self,
        schedules,
        mode="edit",
        requester_id=None
    ):
        super().__init__(timeout=180)

        self.schedules = schedules
        self.mode = mode
        self.requester_id = requester_id

        self.add_item(
            ScheduleSelect(
                schedules,
                self.schedule_selected
            )
        )

    async def schedule_selected(
        self,
        interaction,
        schedule_id
    ):

        schedule = get_schedule(schedule_id)

        if schedule is None:

            await interaction.response.send_message(
                "❌ 일정을 찾을 수 없습니다.",
                ephemeral=True
            )

            return

        # =====================================================
        # 핵심 보안 로직
        # =====================================================

        # 서버가 다른 경우 차단
        if schedule["guild_id"] != interaction.guild.id:

            await interaction.response.send_message(
                "❌ 다른 서버의 일정은 수정/삭제할 수 없습니다.",
                ephemeral=True
            )

            return

        # 본인 일정이 아닌 경우
        if schedule["discord_user_id"] != interaction.user.id:

            # 서버 관리자만 허용
            if not is_server_admin(interaction.user):

                await interaction.response.send_message(
                    "❌ 다른 사람의 일정은 수정하거나 삭제할 수 없습니다.",
                    ephemeral=True
                )

                return

        # =====================================================
        # 수정
        # =====================================================

        if self.mode == "edit":

            await interaction.response.send_message(
                (
                    f"수정할 일정\n\n"
                    f"닉네임: **{schedule['nickname']}**\n"
                    f"현재 직업: **{schedule['job']}**\n"
                    f"현재 날짜: **{format_date(schedule['schedule_date'])}**\n\n"
                    f"새 직업을 선택해주세요."
                ),
                view=JobSelectView(
                    nickname=schedule["nickname"],
                    user_id=schedule["discord_user_id"],
                    guild_id=schedule["guild_id"],
                    mode="edit",
                    schedule_id=schedule["id"]
                ),
                ephemeral=True
            )

        # =====================================================
        # 삭제
        # =====================================================

        elif self.mode == "delete":

            await interaction.response.send_message(
                (
                    f"정말 이 일정을 삭제할까요?\n\n"
                    f"닉네임: **{schedule['nickname']}**\n"
                    f"직업: **{schedule['job']}**\n"
                    f"날짜: **{format_date(schedule['schedule_date'])}**"
                ),
                view=DeleteConfirmView(
                    schedule_id=schedule["id"],
                    owner_id=schedule["discord_user_id"]
                ),
                ephemeral=True
            )


# =========================================================
# 삭제 확인
# =========================================================

class DeleteConfirmView(discord.ui.View):

    def __init__(
        self,
        schedule_id,
        owner_id
    ):
        super().__init__(timeout=60)

        self.schedule_id = schedule_id
        self.owner_id = owner_id

        yes_button = discord.ui.Button(
            label="삭제",
            style=discord.ButtonStyle.danger
        )

        no_button = discord.ui.Button(
            label="취소",
            style=discord.ButtonStyle.secondary
        )

        async def yes_callback(interaction):

            schedule = get_schedule(self.schedule_id)

            if schedule is None:

                await interaction.response.edit_message(
                    content="❌ 이미 삭제된 일정입니다.",
                    view=None
                )

                return

            # 서버 확인
            if schedule["guild_id"] != interaction.guild.id:

                await interaction.response.edit_message(
                    content="❌ 다른 서버의 일정은 삭제할 수 없습니다.",
                    view=None
                )

                return

            # 본인인지 확인
            if schedule["discord_user_id"] != interaction.user.id:

                # 관리자가 아니면 차단
                if not is_server_admin(interaction.user):

                    await interaction.response.edit_message(
                        content="❌ 다른 사람의 일정은 삭제할 수 없습니다.",
                        view=None
                    )

                    return

            success = delete_schedule(self.schedule_id)

            if success:

                await interaction.response.edit_message(
                    content="✅ 일정이 삭제되었습니다.",
                    view=None
                )

            else:

                await interaction.response.edit_message(
                    content="❌ 일정 삭제에 실패했습니다.",
                    view=None
                )

        async def no_callback(interaction):

            await interaction.response.edit_message(
                content="❎ 삭제를 취소했습니다.",
                view=None
            )

        yes_button.callback = yes_callback
        no_button.callback = no_callback

        self.add_item(yes_button)
        self.add_item(no_button)


# =========================================================
# Bot 설정
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# !등록
# =========================================================

@bot.command(name="등록")
async def register_schedule(
    ctx,
    nickname: str = None
):

    if nickname is None:

        await ctx.send(
            "사용법:\n"
            "`!등록 닉네임`\n\n"
            "예시:\n"
            "`!등록 홍길동`"
        )

        return

    nickname = nickname.strip()

    if not nickname:

        await ctx.send(
            "❌ 닉네임을 입력해주세요."
        )

        return

    await ctx.send(
        f"**{nickname}** 님의 일정을 등록합니다.\n"
        f"직업을 선택해주세요.",
        view=JobSelectView(
            nickname=nickname,
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            mode="register"
        )
    )


# =========================================================
# !일정
# =========================================================

@bot.command(name="일정")
async def show_schedule(
    ctx,
    nickname: str = None
):

    schedules = get_all_schedules(ctx.guild.id)

    if nickname is not None:

        nickname = nickname.strip()

        schedules = [
            schedule
            for schedule in schedules
            if schedule["nickname"] == nickname
        ]

    if not schedules:

        if nickname:

            await ctx.send(
                f"📅 **{nickname}** 님의 등록된 일정이 없습니다."
            )

        else:

            await ctx.send(
                "📅 등록된 일정이 없습니다."
            )

        return

    # 날짜별 그룹
    grouped = {}

    for schedule in schedules:

        date = schedule["schedule_date"]

        if date not in grouped:
            grouped[date] = []

        grouped[date].append(schedule)

    embed = discord.Embed(
        title="📅 일정",
        description="현재 서버에 등록된 일정입니다.",
        color=discord.Color.blue()
    )

    for date in sorted(grouped.keys()):

        lines = []

        for schedule in grouped[date]:

            lines.append(
                f"• **{schedule['nickname']}** — {schedule['job']}"
            )

        embed.add_field(
            name=format_date(date),
            value="\n".join(lines),
            inline=False
        )

    await ctx.send(
        embed=embed
    )


# =========================================================
# !전체일정
# =========================================================

@bot.command(name="전체일정")
async def show_all_schedule(ctx):

    schedules = get_all_schedules(ctx.guild.id)

    if not schedules:

        await ctx.send(
            "📅 등록된 일정이 없습니다."
        )

        return

    grouped = {}

    for schedule in schedules:

        date = schedule["schedule_date"]

        if date not in grouped:
            grouped[date] = []

        grouped[date].append(schedule)

    embed = discord.Embed(
        title="📅 서버 전체 일정",
        color=discord.Color.green()
    )

    for date in sorted(grouped.keys()):

        lines = []

        for schedule in grouped[date]:

            lines.append(
                f"• **{schedule['nickname']}** — {schedule['job']}"
            )

        embed.add_field(
            name=format_date(date),
            value="\n".join(lines),
            inline=False
        )

    await ctx.send(
        embed=embed
    )


# =========================================================
# !수정
# =========================================================

@bot.command(name="수정")
async def edit_schedule(ctx):

    # 일반 사용자는 자신의 일정만
    # 관리자는 서버 전체 일정을 선택 가능

    if is_server_admin(ctx.author):

        schedules = get_all_schedules(ctx.guild.id)

        title = (
            "🛠️ 일정 수정\n"
            "관리자 권한으로 서버 전체 일정이 표시됩니다."
        )

    else:

        schedules = get_user_schedules(
            ctx.guild.id,
            ctx.author.id
        )

        title = (
            "🛠️ 일정 수정\n"
            "본인이 등록한 일정만 표시됩니다."
        )

    if not schedules:

        await ctx.send(
            "❌ 수정할 일정이 없습니다."
        )

        return

    await ctx.send(
        title,
        view=ScheduleSelectView(
            schedules=schedules,
            mode="edit",
            requester_id=ctx.author.id
        )
    )


# =========================================================
# !삭제
# =========================================================

@bot.command(name="삭제")
async def delete_schedule_command(ctx):

    # 일반 사용자는 자신의 일정만
    # 관리자는 서버 전체 일정 선택 가능

    if is_server_admin(ctx.author):

        schedules = get_all_schedules(ctx.guild.id)

        title = (
            "🗑️ 일정 삭제\n"
            "관리자 권한으로 서버 전체 일정이 표시됩니다."
        )

    else:

        schedules = get_user_schedules(
            ctx.guild.id,
            ctx.author.id
        )

        title = (
            "🗑️ 일정 삭제\n"
            "본인이 등록한 일정만 표시됩니다."
        )

    if not schedules:

        await ctx.send(
            "❌ 삭제할 일정이 없습니다."
        )

        return

    await ctx.send(
        title,
        view=ScheduleSelectView(
            schedules=schedules,
            mode="delete",
            requester_id=ctx.author.id
        )
    )


# =========================================================
# !내일정
# =========================================================

@bot.command(name="내일정")
async def my_schedule(ctx):

    schedules = get_user_schedules(
        ctx.guild.id,
        ctx.author.id
    )

    if not schedules:

        await ctx.send(
            "📅 등록한 일정이 없습니다."
        )

        return

    grouped = {}

    for schedule in schedules:

        date = schedule["schedule_date"]

        if date not in grouped:
            grouped[date] = []

        grouped[date].append(schedule)

    embed = discord.Embed(
        title=f"📅 {ctx.author.display_name}님의 일정",
        color=discord.Color.blurple()
    )

    for date in sorted(grouped.keys()):

        lines = []

        for schedule in grouped[date]:

            lines.append(
                f"• **{schedule['nickname']}** — {schedule['job']}"
            )

        embed.add_field(
            name=format_date(date),
            value="\n".join(lines),
            inline=False
        )

    await ctx.send(
        embed=embed
    )


# =========================================================
# !도움말
# =========================================================

@bot.command(name="도움말")
async def help_command(ctx):

    embed = discord.Embed(
        title="📖 일정 봇 명령어",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="📌 일정 등록",
        value=(
            "`!등록 닉네임`\n"
            "본인의 일정을 등록합니다."
        ),
        inline=False
    )

    embed.add_field(
        name="📅 일정 확인",
        value=(
            "`!일정` — 서버 전체 일정\n"
            "`!일정 닉네임` — 특정 닉네임 일정\n"
            "`!내일정` — 내가 등록한 일정\n"
            "`!전체일정` — 서버 전체 일정"
        ),
        inline=False
    )

    embed.add_field(
        name="🛠️ 일정 관리",
        value=(
            "`!수정` — 일정 수정\n"
            "`!삭제` — 일정 삭제"
        ),
        inline=False
    )

    embed.add_field(
        name="🔐 권한",
        value=(
            "일반 사용자는 자신의 일정만 수정/삭제할 수 있습니다.\n"
            "서버 관리 권한이 있는 관리자는 다른 사람의 일정도 수정/삭제할 수 있습니다."
        ),
        inline=False
    )

    await ctx.send(
        embed=embed
    )


# =========================================================
# 명령어 오류 처리
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):

        await ctx.send(
            "❌ 명령어 사용법이 잘못되었습니다.\n"
            "`!도움말`을 입력해서 사용법을 확인해주세요."
        )

        return

    print(f"Command Error: {error}")


# =========================================================
# Bot 시작
# =========================================================

@bot.event
async def on_ready():

    print("--------------------------------")
    print(f"로그인 성공: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print("--------------------------------")


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":

    init_db()

    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    token = os.getenv("DISCORD_TOKEN")

    if not token:

        print("❌ DISCORD_TOKEN 환경변수가 없습니다.")

    else:

        bot.run(token)
