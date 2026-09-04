import os
import sqlite3
import threading
from datetime import datetime, timedelta

from flask import Flask
import discord
from discord.ext import commands


# =========================================================
# 1. 기본 설정
# =========================================================

DB_FILE = "schedule.db"

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


def run_flask():
    app.run(host="0.0.0.0", port=8080)


# =========================================================
# 2. SQLite DB
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
            discord_user_id INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            job TEXT NOT NULL,
            schedule_date TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            UNIQUE(discord_user_id, nickname, schedule_date)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# DB 관련 함수
# =========================================================

def add_schedule(user_id, nickname, job, schedule_date, status):
    conn = get_db()

    now = datetime.now().isoformat(timespec="seconds")

    try:
        cursor = conn.execute("""
            INSERT INTO schedules
            (
                discord_user_id,
                nickname,
                job,
                schedule_date,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            nickname,
            job,
            schedule_date,
            status,
            now,
            now
        ))

        conn.commit()
        schedule_id = cursor.lastrowid

        return schedule_id

    except sqlite3.IntegrityError:
        return None

    finally:
        conn.close()


def get_user_schedules(user_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM schedules
        WHERE discord_user_id = ?
        ORDER BY schedule_date ASC
    """, (user_id,)).fetchall()

    conn.close()

    return rows


def get_nickname_schedules(user_id, nickname):
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM schedules
        WHERE discord_user_id = ?
        AND nickname = ?
        ORDER BY schedule_date ASC
    """, (user_id, nickname)).fetchall()

    conn.close()

    return rows


def get_all_schedules():
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM schedules
        ORDER BY schedule_date ASC, nickname ASC
    """).fetchall()

    conn.close()

    return rows


def get_schedule(schedule_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM schedules
        WHERE id = ?
    """, (schedule_id,)).fetchone()

    conn.close()

    return row


def update_schedule(schedule_id, job, schedule_date, status):
    conn = get_db()

    now = datetime.now().isoformat(timespec="seconds")

    conn.execute("""
        UPDATE schedules
        SET
            job = ?,
            schedule_date = ?,
            status = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        job,
        schedule_date,
        status,
        now,
        schedule_id
    ))

    conn.commit()
    conn.close()


def delete_schedule(schedule_id):
    conn = get_db()

    conn.execute("""
        DELETE FROM schedules
        WHERE id = ?
    """, (schedule_id,))

    conn.commit()
    conn.close()


# =========================================================
# 3. Discord 설정
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# 4. 공통 데이터
# =========================================================

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

STATUSES = [
    "가능",
    "불가능",
    "미정",
]


def format_date(date_text):
    try:
        date_obj = datetime.strptime(date_text, "%Y-%m-%d")
        return date_obj.strftime("%m/%d (%a)")
    except Exception:
        return date_text


def status_emoji(status):
    if status == "가능":
        return "🟢"

    if status == "불가능":
        return "🔴"

    if status == "미정":
        return "🟡"

    return "⚪"


# =========================================================
# 5. 상태 선택 View
# =========================================================

class StatusSelectView(discord.ui.View):

    def __init__(
        self,
        user_id,
        nickname,
        job,
        selected_date,
        edit_schedule_id=None
    ):
        super().__init__(timeout=180)

        self.user_id = user_id
        self.nickname = nickname
        self.job = job
        self.selected_date = selected_date
        self.edit_schedule_id = edit_schedule_id

    async def save_schedule(
        self,
        interaction: discord.Interaction,
        status: str
    ):

        # -------------------------------------------------
        # 수정
        # -------------------------------------------------

        if self.edit_schedule_id is not None:

            schedule = get_schedule(self.edit_schedule_id)

            if schedule is None:
                await interaction.response.send_message(
                    "❌ 해당 일정을 찾을 수 없습니다.",
                    ephemeral=True
                )
                return

            # 권한 확인
            if (
                schedule["discord_user_id"] != interaction.user.id
                and not interaction.user.guild_permissions.manage_guild
            ):
                await interaction.response.send_message(
                    "❌ 이 일정을 수정할 권한이 없습니다.",
                    ephemeral=True
                )
                return

            update_schedule(
                self.edit_schedule_id,
                self.job,
                self.selected_date,
                status
            )

            await interaction.response.edit_message(
                content=(
                    "✅ **일정 수정 완료!**\n\n"
                    f"👤 닉네임: **{self.nickname}**\n"
                    f"⚔️ 직업: **{self.job}**\n"
                    f"📅 날짜: **{format_date(self.selected_date)}**\n"
                    f"📌 상태: {status_emoji(status)} **{status}**"
                ),
                view=None
            )

            self.stop()
            return

        # -------------------------------------------------
        # 신규 등록
        # -------------------------------------------------

        schedule_id = add_schedule(
            interaction.user.id,
            self.nickname,
            self.job,
            self.selected_date,
            status
        )

        if schedule_id is None:
            await interaction.response.send_message(
                (
                    "⚠️ 이미 같은 닉네임으로 "
                    "해당 날짜의 일정이 등록되어 있습니다.\n"
                    "`!일정`으로 확인해주세요."
                ),
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content=(
                "✅ **일정 등록 완료!**\n\n"
                f"👤 닉네임: **{self.nickname}**\n"
                f"⚔️ 직업: **{self.job}**\n"
                f"📅 날짜: **{format_date(self.selected_date)}**\n"
                f"📌 상태: {status_emoji(status)} **{status}**"
            ),
            view=None
        )

        self.stop()

    @discord.ui.button(
        label="가능",
        emoji="🟢",
        style=discord.ButtonStyle.success
    )
    async def available(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.save_schedule(interaction, "가능")

    @discord.ui.button(
        label="불가능",
        emoji="🔴",
        style=discord.ButtonStyle.danger
    )
    async def unavailable(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.save_schedule(interaction, "불가능")

    @discord.ui.button(
        label="미정",
        emoji="🟡",
        style=discord.ButtonStyle.secondary
    )
    async def undecided(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.save_schedule(interaction, "미정")


# =========================================================
# 6. 날짜 선택 View
# =========================================================

class DateSelectView(discord.ui.View):

    def __init__(
        self,
        user_id,
        nickname,
        job,
        edit_schedule_id=None
    ):
        super().__init__(timeout=180)

        self.user_id = user_id
        self.nickname = nickname
        self.job = job
        self.edit_schedule_id = edit_schedule_id
        self.selected_date = None

        today = datetime.now().date()

        for i in range(7):
            target_date = today + timedelta(days=i)

            label = target_date.strftime("%m/%d (%a)")

            self.add_date_button(
                target_date,
                label
            )

    def add_date_button(self, target_date, label):

        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.secondary,
            row=len(self.children) // 5
        )

        async def button_callback(
            interaction: discord.Interaction
        ):

            # 모든 날짜 버튼 초기화
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.label != "선택 완료":
                        child.style = discord.ButtonStyle.secondary

            button.style = discord.ButtonStyle.primary

            self.selected_date = target_date.strftime("%Y-%m-%d")

            await interaction.response.edit_message(
                view=self
            )

        button.callback = button_callback

        self.add_item(button)

    @discord.ui.button(
        label="선택 완료",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=4
    )
    async def confirm_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not self.selected_date:

            await interaction.response.send_message(
                "📅 날짜를 먼저 선택해주세요!",
                ephemeral=True
            )

            return

        status_view = StatusSelectView(
            interaction.user.id,
            self.nickname,
            self.job,
            self.selected_date,
            self.edit_schedule_id
        )

        await interaction.response.edit_message(
            content=(
                f"👤 **{self.nickname}**\n"
                f"⚔️ 직업: **{self.job}**\n"
                f"📅 날짜: **{format_date(self.selected_date)}**\n\n"
                "📌 **상태를 선택해주세요.**"
            ),
            view=status_view
        )


# =========================================================
# 7. 직업 선택
# =========================================================

class JobSelect(discord.ui.Select):

    def __init__(
        self,
        user_id,
        nickname,
        edit_schedule_id=None
    ):

        self.user_id = user_id
        self.nickname = nickname
        self.edit_schedule_id = edit_schedule_id

        options = [
            discord.SelectOption(
                label=job,
                description=f"{job} 선택"
            )
            for job in JOBS
        ]

        super().__init__(
            placeholder="직업을 선택해주세요...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        # 본인 확인
        if interaction.user.id != self.user_id:

            await interaction.response.send_message(
                "❌ 이 메뉴를 만든 사람만 사용할 수 있습니다.",
                ephemeral=True
            )

            return

        selected_job = self.values[0]

        date_view = DateSelectView(
            interaction.user.id,
            self.nickname,
            selected_job,
            self.edit_schedule_id
        )

        if self.edit_schedule_id:

            title = "✏️ **일정 수정**"

        else:

            title = "📝 **일정 등록**"

        await interaction.response.edit_message(
            content=(
                f"{title}\n\n"
                f"👤 닉네임: **{self.nickname}**\n"
                f"⚔️ 직업: **{selected_job}**\n\n"
                "📅 등록할 날짜를 선택해주세요."
            ),
            view=date_view
        )


class JobSelectView(discord.ui.View):

    def __init__(
        self,
        user_id,
        nickname,
        edit_schedule_id=None
    ):

        super().__init__(timeout=180)

        self.add_item(
            JobSelect(
                user_id,
                nickname,
                edit_schedule_id
            )
        )


# =========================================================
# 8. 일정 선택 View
# =========================================================

class ScheduleSelectView(discord.ui.View):

    def __init__(
        self,
        schedules,
        mode="edit"
    ):

        super().__init__(timeout=180)

        self.schedules = schedules
        self.mode = mode

        options = []

        for schedule in schedules[:25]:

            label = (
                f"{format_date(schedule['schedule_date'])} "
                f"- {schedule['job']}"
            )

            description = (
                f"상태: {schedule['status']}"
            )

            options.append(
                discord.SelectOption(
                    label=label[:100],
                    description=description[:100],
                    value=str(schedule["id"])
                )
            )

        select = discord.ui.Select(
            placeholder="관리할 일정을 선택해주세요...",
            min_values=1,
            max_values=1,
            options=options
        )

        async def callback(
            interaction: discord.Interaction
        ):

            schedule_id = int(select.values[0])

            schedule = get_schedule(schedule_id)

            if schedule is None:

                await interaction.response.send_message(
                    "❌ 일정을 찾을 수 없습니다.",
                    ephemeral=True
                )

                return

            # -------------------------------------------------
            # 수정
            # -------------------------------------------------

            if self.mode == "edit":

                view = JobSelectView(
                    interaction.user.id,
                    schedule["nickname"],
                    schedule_id
                )

                await interaction.response.edit_message(
                    content=(
                        "✏️ **수정할 직업을 선택해주세요.**\n\n"
                        f"👤 닉네임: **{schedule['nickname']}**\n"
                        f"현재 직업: **{schedule['job']}\n"
                        f"현재 날짜: **{format_date(schedule['schedule_date'])}**\n"
                        f"현재 상태: **{schedule['status']}**"
                    ),
                    view=view
                )

            # -------------------------------------------------
            # 삭제
            # -------------------------------------------------

            elif self.mode == "delete":

                view = DeleteConfirmView(
                    interaction.user.id,
                    schedule_id
                )

                await interaction.response.edit_message(
                    content=(
                        "🗑️ **정말 삭제하시겠습니까?**\n\n"
                        f"👤 닉네임: **{schedule['nickname']}**\n"
                        f"⚔️ 직업: **{schedule['job']}**\n"
                        f"📅 날짜: **{format_date(schedule['schedule_date'])}**\n"
                        f"📌 상태: **{schedule['status']}**"
                    ),
                    view=view
                )

        select.callback = callback

        self.add_item(select)


# =========================================================
# 9. 삭제 확인 View
# =========================================================

class DeleteConfirmView(discord.ui.View):

    def __init__(
        self,
        user_id,
        schedule_id
    ):

        super().__init__(timeout=60)

        self.user_id = user_id
        self.schedule_id = schedule_id

    @discord.ui.button(
        label="삭제",
        emoji="🗑️",
        style=discord.ButtonStyle.danger
    )
    async def confirm_delete(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        schedule = get_schedule(self.schedule_id)

        if schedule is None:

            await interaction.response.send_message(
                "❌ 이미 삭제된 일정입니다.",
                ephemeral=True
            )

            return

        # 권한 확인
        if (
            schedule["discord_user_id"] != interaction.user.id
            and not interaction.user.guild_permissions.manage_guild
        ):

            await interaction.response.send_message(
                "❌ 이 일정을 삭제할 권한이 없습니다.",
                ephemeral=True
            )

            return

        delete_schedule(self.schedule_id)

        await interaction.response.edit_message(
            content="🗑️ **일정이 삭제되었습니다.**",
            view=None
        )

    @discord.ui.button(
        label="취소",
        emoji="↩️",
        style=discord.ButtonStyle.secondary
    )
    async def cancel_delete(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="❎ 삭제를 취소했습니다.",
            view=None
        )


# =========================================================
# 10. 일정 표시
# =========================================================

def make_schedule_text(
    schedules,
    title="📅 일정"
):

    if not schedules:
        return f"{title}\n\n등록된 일정이 없습니다."

    lines = [f"**{title}**", ""]

    current_date = None

    for schedule in schedules:

        date_text = schedule["schedule_date"]

        if date_text != current_date:

            lines.append(
                f"### 📅 {format_date(date_text)}"
            )

            current_date = date_text

        lines.append(
            f"{status_emoji(schedule['status'])} "
            f"**{schedule['nickname']}** | "
            f"{schedule['job']} | "
            f"{schedule['status']}"
        )

    return "\n".join(lines)


# =========================================================
# 11. !등록
# =========================================================

@bot.command(name="등록")
async def register_command(
    ctx,
    *,
    nickname: str
):

    nickname = nickname.strip()

    if not nickname:

        await ctx.send(
            "❌ 닉네임을 입력해주세요.\n"
            "예: `!등록 김법사`"
        )

        return

    view = JobSelectView(
        ctx.author.id,
        nickname
    )

    await ctx.send(
        f"🛡️ **{nickname}**님의 캐릭터 직업을 선택해주세요:",
        view=view
    )


# =========================================================
# 12. !일정
# =========================================================

@bot.command(name="일정")
async def schedule_command(
    ctx,
    *,
    nickname: str = None
):

    if nickname:

        schedules = get_nickname_schedules(
            ctx.author.id,
            nickname.strip()
        )

        title = f"📅 {nickname}님의 일정"

    else:

        schedules = get_user_schedules(
            ctx.author.id
        )

        title = "📅 내 일정"

    text = make_schedule_text(
        schedules,
        title
    )

    await ctx.send(text)


# =========================================================
# 13. !전체일정
# =========================================================

@bot.command(name="전체일정")
async def all_schedule_command(ctx):

    schedules = get_all_schedules()

    if not schedules:

        await ctx.send(
            "📅 등록된 일정이 없습니다."
        )

        return

    text = make_schedule_text(
        schedules,
        "📅 전체 일정"
    )

    # Discord 메시지 길이 제한
    if len(text) <= 2000:

        await ctx.send(text)

    else:

        chunks = []

        current = ""

        for line in text.split("\n"):

            if len(current) + len(line) + 1 > 1900:

                chunks.append(current)
                current = ""

            current += line + "\n"

        if current:
            chunks.append(current)

        for chunk in chunks:
            await ctx.send(chunk)


# =========================================================
# 14. !수정
# =========================================================

@bot.command(name="수정")
async def edit_command(
    ctx,
    *,
    nickname: str = None
):

    if nickname:

        schedules = get_nickname_schedules(
            ctx.author.id,
            nickname.strip()
        )

    else:

        schedules = get_user_schedules(
            ctx.author.id
        )

    if not schedules:

        await ctx.send(
            "❌ 수정할 일정이 없습니다."
        )

        return

    view = ScheduleSelectView(
        schedules,
        mode="edit"
    )

    await ctx.send(
        "✏️ **수정할 일정을 선택해주세요.**",
        view=view
    )


# =========================================================
# 15. !삭제
# =========================================================

@bot.command(name="삭제")
async def delete_command(
    ctx,
    *,
    nickname: str = None
):

    if nickname:

        schedules = get_nickname_schedules(
            ctx.author.id,
            nickname.strip()
        )

    else:

        schedules = get_user_schedules(
            ctx.author.id
        )

    if not schedules:

        await ctx.send(
            "❌ 삭제할 일정이 없습니다."
        )

        return

    view = ScheduleSelectView(
        schedules,
        mode="delete"
    )

    await ctx.send(
        "🗑️ **삭제할 일정을 선택해주세요.**",
        view=view
    )


# =========================================================
# 16. !도움말
# =========================================================

@bot.command(name="도움말")
async def help_command(ctx):

    embed = discord.Embed(
        title="📚 일정 봇 명령어",
        description="일정 등록 및 관리 기능",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="📝 등록",
        value="`!등록 닉네임`\n직업 → 날짜 → 상태 선택",
        inline=False
    )

    embed.add_field(
        name="📅 조회",
        value=(
            "`!일정` - 내 전체 일정\n"
            "`!일정 닉네임` - 해당 캐릭터 일정\n"
            "`!전체일정` - 서버 전체 일정"
        ),
        inline=False
    )

    embed.add_field(
        name="✏️ 수정",
        value=(
            "`!수정`\n"
            "`!수정 닉네임`"
        ),
        inline=False
    )

    embed.add_field(
        name="🗑️ 삭제",
        value=(
            "`!삭제`\n"
            "`!삭제 닉네임`"
        ),
        inline=False
    )

    embed.add_field(
        name="📌 상태",
        value=(
            "🟢 가능\n"
            "🔴 불가능\n"
            "🟡 미정"
        ),
        inline=False
    )

    await ctx.send(embed=embed)


# =========================================================
# 17. 오류 처리
# =========================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ 명령어 사용법을 확인해주세요.\n"
            "예: `!등록 김법사`\n"
            "`!도움말`을 입력하면 전체 명령어를 볼 수 있습니다."
        )

        return

    print(
        f"[COMMAND ERROR] {type(error).__name__}: {error}"
    )


# =========================================================
# 18. 봇 시작
# =========================================================

@bot.event
async def on_ready():

    print(
        f"로그인 완료: {bot.user} "
        f"(ID: {bot.user.id})"
    )

    print(
        f"DB 위치: {os.path.abspath(DB_FILE)}"
    )


# =========================================================
# 19. 실행
# =========================================================

if __name__ == "__main__":

    # DB 생성
    init_db()

    # Flask 시작
    flask_thread = threading.Thread(
        target=run_flask
    )

    flask_thread.daemon = True
    flask_thread.start()

    # Discord Bot
    token = os.environ.get("DISCORD_TOKEN")

    if token:

        bot.run(token)

    else:

        print(
            "오류: DISCORD_TOKEN 환경 변수가 "
            "설정되지 않았습니다."
        )
