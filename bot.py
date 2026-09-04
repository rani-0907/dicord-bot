```python
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


# =========================================================
# 2. Render 헬스체크용 Flask 서버
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


def run_flask():
    app.run(
        host="0.0.0.0",
        port=8080
    )


# =========================================================
# 3. SQLite DB
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)

    # DB 결과를 dict처럼 사용할 수 있게 설정
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

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL,

            UNIQUE(
                discord_user_id,
                nickname,
                schedule_date
            )
        )
    """)

    conn.commit()
    conn.close()

    print("SQLite DB 초기화 완료")


# =========================================================
# 4. DB - 일정 등록
# =========================================================

def add_schedule(
    user_id,
    nickname,
    job,
    schedule_date
):
    conn = get_db()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    try:

        cursor = conn.execute(
            """
            INSERT INTO schedules (
                discord_user_id,
                nickname,
                job,
                schedule_date,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                nickname,
                job,
                schedule_date,
                now,
                now
            )
        )

        conn.commit()

        schedule_id = cursor.lastrowid

        return schedule_id

    except sqlite3.IntegrityError:

        # 같은 사람이 같은 닉네임으로
        # 같은 날짜에 이미 등록한 경우
        return None

    finally:

        conn.close()


# =========================================================
# 5. DB - 일정 조회
# =========================================================

def get_user_schedules(user_id):

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM schedules
        WHERE discord_user_id = ?
        ORDER BY schedule_date ASC, nickname ASC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return rows


def get_nickname_schedules(
    user_id,
    nickname
):

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM schedules
        WHERE discord_user_id = ?
        AND nickname = ?
        ORDER BY schedule_date ASC
        """,
        (
            user_id,
            nickname
        )
    ).fetchall()

    conn.close()

    return rows


def get_all_schedules():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM schedules
        ORDER BY
            schedule_date ASC,
            nickname ASC
        """
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# 6. DB - 특정 일정 조회
# =========================================================

def get_schedule(schedule_id):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM schedules
        WHERE id = ?
        """,
        (schedule_id,)
    ).fetchone()

    conn.close()

    return row


# =========================================================
# 7. DB - 일정 수정
# =========================================================

def update_schedule(
    schedule_id,
    job,
    schedule_date
):

    conn = get_db()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    try:

        conn.execute(
            """
            UPDATE schedules
            SET
                job = ?,
                schedule_date = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                job,
                schedule_date,
                now,
                schedule_id
            )
        )

        conn.commit()

        return True

    except sqlite3.IntegrityError:

        # 수정하려는 날짜에
        # 이미 같은 캐릭터가 등록되어 있는 경우
        return False

    finally:

        conn.close()


# =========================================================
# 8. DB - 일정 삭제
# =========================================================

def delete_schedule(schedule_id):

    conn = get_db()

    conn.execute(
        """
        DELETE FROM schedules
        WHERE id = ?
        """,
        (schedule_id,)
    )

    conn.commit()

    conn.close()


# =========================================================
# 9. Discord Bot 설정
# =========================================================

intents = discord.Intents.default()

intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# 10. 직업 목록
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


# =========================================================
# 11. 날짜 표시
# =========================================================

def format_date(date_text):

    try:

        date_obj = datetime.strptime(
            date_text,
            "%Y-%m-%d"
        )

        return date_obj.strftime(
            "%m/%d (%a)"
        )

    except Exception:

        return date_text


# =========================================================
# 12. 날짜 선택 View
# =========================================================

class DateSelectView(discord.ui.View):

    def __init__(
        self,
        user_id,
        nickname,
        job,
        edit_schedule_id=None
    ):

        super().__init__(
            timeout=180
        )

        self.user_id = user_id

        self.nickname = nickname

        self.job = job

        self.edit_schedule_id = edit_schedule_id

        self.selected_date = None

        # 오늘부터 7일
        today = datetime.now().date()

        for i in range(7):

            target_date = today + timedelta(
                days=i
            )

            label = target_date.strftime(
                "%m/%d (%a)"
            )

            self.add_date_button(
                target_date,
                label
            )


    def add_date_button(
        self,
        target_date,
        label
    ):

        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.secondary,

            # 5개씩 한 줄
            row=len(self.children) // 5
        )


        async def button_callback(
            interaction: discord.Interaction
        ):

            # 다른 사람이 버튼을 누르는 것 방지
            if interaction.user.id != self.user_id:

                await interaction.response.send_message(
                    "❌ 이 메뉴를 만든 사람만 사용할 수 있습니다.",
                    ephemeral=True
                )

                return


            # 모든 날짜 버튼 초기화
            for child in self.children:

                if isinstance(
                    child,
                    discord.ui.Button
                ):

                    if child.label != "등록 완료":

                        child.style = (
                            discord.ButtonStyle.secondary
                        )


            # 선택한 날짜 강조
            button.style = (
                discord.ButtonStyle.primary
            )


            self.selected_date = (
                target_date.strftime(
                    "%Y-%m-%d"
                )
            )


            await interaction.response.edit_message(
                view=self
            )


        button.callback = button_callback

        self.add_item(button)


    # =====================================================
    # 날짜 선택 완료
    # =====================================================

    @discord.ui.button(
        label="등록 완료",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=4
    )
    async def confirm_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.user.id != self.user_id:

            await interaction.response.send_message(
                "❌ 이 메뉴를 만든 사람만 사용할 수 있습니다.",
                ephemeral=True
            )

            return


        if not self.selected_date:

            await interaction.response.send_message(
                "📅 날짜를 먼저 선택해주세요!",
                ephemeral=True
            )

            return


        # =================================================
        # 수정
        # =================================================

        if self.edit_schedule_id is not None:

            schedule = get_schedule(
                self.edit_schedule_id
            )


            if schedule is None:

                await interaction.response.edit_message(
                    content="❌ 해당 일정을 찾을 수 없습니다.",
                    view=None
                )

                return


            # 본인 일정인지 확인
            # 관리자는 다른 사람 일정도 가능
            if (
                schedule["discord_user_id"]
                != interaction.user.id
                and
                not interaction.user.guild_permissions.manage_guild
            ):

                await interaction.response.send_message(
                    "❌ 이 일정을 수정할 권한이 없습니다.",
                    ephemeral=True
                )

                return


            success = update_schedule(
                self.edit_schedule_id,
                self.job,
                self.selected_date
            )


            if not success:

                await interaction.response.send_message(
                    (
                        "⚠️ 수정할 날짜에 "
                        "이미 같은 캐릭터가 등록되어 있습니다."
                    ),
                    ephemeral=True
                )

                return


            await interaction.response.edit_message(
                content=(
                    "✅ **일정 수정 완료!**\n\n"

                    f"👤 닉네임: **{self.nickname}**\n"

                    f"⚔️ 직업: **{self.job}**\n"

                    f"📅 날짜: **{format_date(self.selected_date)}**"
                ),
                view=None
            )

            self.stop()

            return


        # =================================================
        # 신규 등록
        # =================================================

        schedule_id = add_schedule(
            interaction.user.id,
            self.nickname,
            self.job,
            self.selected_date
        )


        if schedule_id is None:

            await interaction.response.send_message(
                (
                    "⚠️ 이미 해당 캐릭터가 "
                    "그 날짜에 등록되어 있습니다.\n\n"

                    f"👤 닉네임: **{self.nickname}**\n"
                    f"📅 날짜: **{format_date(self.selected_date)}**"
                ),
                ephemeral=True
            )

            return


        await interaction.response.edit_message(
            content=(
                "✅ **일정 등록 완료!**\n\n"

                f"👤 닉네임: **{self.nickname}**\n"

                f"⚔️ 직업: **{self.job}**\n"

                f"📅 날짜: **{format_date(self.selected_date)}**"
            ),
            view=None
        )

        self.stop()


# =========================================================
# 13. 직업 선택
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


        options = []

        for job in JOBS:

            options.append(
                discord.SelectOption(
                    label=job,
                    description=f"{job} 선택"
                )
            )


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

        # 사용자 확인
        if interaction.user.id != self.user_id:

            await interaction.response.send_message(
                "❌ 이 메뉴를 만든 사람만 사용할 수 있습니다.",
                ephemeral=True
            )

            return


        selected_job = self.values[0]


        # 날짜 선택 화면
        date_view = DateSelectView(
            interaction.user.id,
            self.nickname,
            selected_job,
            self.edit_schedule_id
        )


        if self.edit_schedule_id is not None:

            title = "✏️ **일정 수정**"

        else:

            title = "📝 **일정 등록**"


        await interaction.response.edit_message(
            content=(
                f"{title}\n\n"

                f"👤 닉네임: **{self.nickname}**\n"

                f"⚔️ 직업: **{selected_job}**\n\n"

                "📅 날짜를 선택해주세요."
            ),
            view=date_view
        )


# =========================================================
# 14. 직업 선택 View
# =========================================================

class JobSelectView(discord.ui.View):

    def __init__(
        self,
        user_id,
        nickname,
        edit_schedule_id=None
    ):

        super().__init__(
            timeout=180
        )

        self.add_item(
            JobSelect(
                user_id,
                nickname,
                edit_schedule_id
            )
        )


# =========================================================
# 15. 일정 선택 View
# =========================================================

class ScheduleSelectView(discord.ui.View):

    def __init__(
        self,
        schedules,
        mode="edit"
    ):

        super().__init__(
            timeout=180
        )

        self.schedules = schedules

        self.mode = mode


        options = []


        # Discord Select는 최대 25개
        for schedule in schedules[:25]:

            label = (
                f"{format_date(schedule['schedule_date'])}"
                f" - {schedule['nickname']}"
            )


            description = (
                f"직업: {schedule['job']}"
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

            schedule_id = int(
                select.values[0]
            )


            schedule = get_schedule(
                schedule_id
            )


            if schedule is None:

                await interaction.response.send_message(
                    "❌ 해당 일정을 찾을 수 없습니다.",
                    ephemeral=True
                )

                return


            # =================================================
            # 수정
            # =================================================

            if self.mode == "edit":

                # 본인 일정이 아니면 관리자만 가능
                if (
                    schedule["discord_user_id"]
                    != interaction.user.id
                    and
                    not interaction.user.guild_permissions.manage_guild
                ):

                    await interaction.response.send_message(
                        "❌ 이 일정을 수정할 권한이 없습니다.",
                        ephemeral=True
                    )

                    return


                view = JobSelectView(
                    interaction.user.id,
                    schedule["nickname"],
                    schedule_id
                )


                await interaction.response.edit_message(
                    content=(
                        "✏️ **수정할 직업을 선택해주세요.**\n\n"

                        f"👤 닉네임: **{schedule['nickname']}**\n"

                        f"⚔️ 현재 직업: **{schedule['job']}**\n"

                        f"📅 현재 날짜: "
                        f"**{format_date(schedule['schedule_date'])}**"
                    ),
                    view=view
                )


            # =================================================
            # 삭제
            # =================================================

            elif self.mode == "delete":

                # 본인 일정이 아니면 관리자만 가능
                if (
                    schedule["discord_user_id"]
                    != interaction.user.id
                    and
                    not interaction.user.guild_permissions.manage_guild
                ):

                    await interaction.response.send_message(
                        "❌ 이 일정을 삭제할 권한이 없습니다.",
                        ephemeral=True
                    )

                    return


                view = DeleteConfirmView(
                    interaction.user.id,
                    schedule_id
                )


                await interaction.response.edit_message(
                    content=(
                        "🗑️ **정말 삭제하시겠습니까?**\n\n"

                        f"👤 닉네임: **{schedule['nickname']}**\n"

                        f"⚔️ 직업: **{schedule['job']}**\n"

                        f"📅 날짜: "
                        f"**{format_date(schedule['schedule_date'])}**"
                    ),
                    view=view
                )


        select.callback = callback

        self.add_item(select)


# =========================================================
# 16. 삭제 확인 View
# =========================================================

class DeleteConfirmView(discord.ui.View):

    def __init__(
        self,
        user_id,
        schedule_id
    ):

        super().__init__(
            timeout=60
        )

        self.user_id = user_id

        self.schedule_id = schedule_id


    # =====================================================
    # 삭제
    # =====================================================

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

        schedule = get_schedule(
            self.schedule_id
        )


        if schedule is None:

            await interaction.response.edit_message(
                content="❌ 이미 삭제된 일정입니다.",
                view=None
            )

            return


        # 본인 또는 관리자만 삭제 가능
        if (
            schedule["discord_user_id"]
            != interaction.user.id
            and
            not interaction.user.guild_permissions.manage_guild
        ):

            await interaction.response.send_message(
                "❌ 이 일정을 삭제할 권한이 없습니다.",
                ephemeral=True
            )

            return


        delete_schedule(
            self.schedule_id
        )


        await interaction.response.edit_message(
            content="🗑️ **일정이 삭제되었습니다.**",
            view=None
        )

        self.stop()


    # =====================================================
    # 취소
    # =====================================================

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

        self.stop()


# =========================================================
# 17. 일정 출력
# =========================================================

def make_schedule_text(
    schedules,
    title="📅 일정"
):

    if not schedules:

        return (
            f"**{title}**\n\n"
            "등록된 일정이 없습니다."
        )


    lines = []

    lines.append(
        f"**{title}**"
    )

    lines.append("")


    current_date = None


    for schedule in schedules:

        date_text = schedule["schedule_date"]


        # 날짜가 바뀌면 날짜 제목 표시
        if date_text != current_date:

            if current_date is not None:

                lines.append("")


            lines.append(
                f"### 📅 {format_date(date_text)}"
            )

            current_date = date_text


        lines.append(
            f"• **{schedule['nickname']}** "
            f"| {schedule['job']}"
        )


    return "\n".join(lines)


# =========================================================
# 18. !등록
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
            "❌ 닉네임을 입력해주세요.\n\n"
            "예: `!등록 김법사`"
        )

        return


    view = JobSelectView(
        ctx.author.id,
        nickname
    )


    await ctx.send(
        (
            f"📝 **{nickname}**님의 "
            "직업을 선택해주세요."
        ),
        view=view
    )


# =========================================================
# 19. !일정
# =========================================================

@bot.command(name="일정")
async def schedule_command(
    ctx,
    *,
    nickname: str = None
):

    if nickname:

        nickname = nickname.strip()

        schedules = get_nickname_schedules(
            ctx.author.id,
            nickname
        )

        title = (
            f"📅 {nickname}님의 일정"
        )

    else:

        schedules = get_user_schedules(
            ctx.author.id
        )

        title = "📅 내 일정"


    text = make_schedule_text(
        schedules,
        title
    )


    await ctx.send(
        text
    )


# =========================================================
# 20. !전체일정
# =========================================================

@bot.command(name="전체일정")
async def all_schedule_command(
    ctx
):

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


    # Discord 메시지 길이 제한 대응
    if len(text) <= 2000:

        await ctx.send(
            text
        )

        return


    chunks = []

    current = ""


    for line in text.split("\n"):

        if (
            len(current)
            + len(line)
            + 1
            > 1900
        ):

            chunks.append(
                current
            )

            current = ""


        current += line + "\n"


    if current:

        chunks.append(
            current
        )


    for chunk in chunks:

        await ctx.send(
            chunk
        )


# =========================================================
# 21. !수정
# =========================================================

@bot.command(name="수정")
async def edit_command(
    ctx,
    *,
    nickname: str = None
):

    if nickname:

        nickname = nickname.strip()

        schedules = get_nickname_schedules(
            ctx.author.id,
            nickname
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
# 22. !삭제
# =========================================================

@bot.command(name="삭제")
async def delete_command(
    ctx,
    *,
    nickname: str = None
):

    if nickname:

        nickname = nickname.strip()

        schedules = get_nickname_schedules(
            ctx.author.id,
            nickname
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
# 23. !도움말
# =========================================================

@bot.command(name="도움말")
async def help_command(
    ctx
):

    embed = discord.Embed(
        title="📚 일정 관리 봇",
        description=(
            "캐릭터별 일정을 등록하고 "
            "수정/삭제할 수 있습니다."
        ),
        color=discord.Color.blue()
    )


    embed.add_field(
        name="📝 일정 등록",
        value=(
            "`!등록 닉네임`\n"
            "직업 → 날짜 선택 → 등록"
        ),
        inline=False
    )


    embed.add_field(
        name="📅 일정 조회",
        value=(
            "`!일정` - 내 전체 일정\n"
            "`!일정 닉네임` - 특정 캐릭터 일정\n"
            "`!전체일정` - 서버 전체 일정"
        ),
        inline=False
    )


    embed.add_field(
        name="✏️ 일정 수정",
        value=(
            "`!수정` - 내 일정 중 선택\n"
            "`!수정 닉네임` - 특정 캐릭터 일정 수정"
        ),
        inline=False
    )


    embed.add_field(
        name="🗑️ 일정 삭제",
        value=(
            "`!삭제` - 내 일정 중 선택\n"
            "`!삭제 닉네임` - 특정 캐릭터 일정 삭제"
        ),
        inline=False
    )


    embed.add_field(
        name="🔒 권한",
        value=(
            "일반 사용자는 자신의 일정만 "
            "수정/삭제할 수 있습니다.\n"
            "서버 관리 권한이 있는 사용자는 "
            "다른 사람의 일정도 관리할 수 있습니다."
        ),
        inline=False
    )


    await ctx.send(
        embed=embed
    )


# =========================================================
# 24. 명령어 오류 처리
# =========================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    # 존재하지 않는 명령어는 무시
    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return


    # 필수 인자가 없는 경우
    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            (
                "❌ 닉네임을 입력해주세요.\n\n"
                "예: `!등록 김법사`\n"
                "`!도움말`을 입력하면 "
                "전체 명령어를 볼 수 있습니다."
            )
        )

        return


    print(
        f"[COMMAND ERROR] "
        f"{type(error).__name__}: {error}"
    )


# =========================================================
# 25. Bot Ready
# =========================================================

@bot.event
async def on_ready():

    print(
        f"로그인 완료: {bot.user} "
        f"(ID: {bot.user.id})"
    )

    print(
        f"SQLite DB: "
        f"{os.path.abspath(DB_FILE)}"
    )


# =========================================================
# 26. 실행
# =========================================================

if __name__ == "__main__":

    # SQLite DB 생성
    init_db()


    # Flask 서버 시작
    flask_thread = threading.Thread(
        target=run_flask
    )

    flask_thread.daemon = True

    flask_thread.start()


    # Discord Token
    token = os.environ.get(
        "DISCORD_TOKEN"
    )


    if token:

        bot.run(
            token
        )

    else:

        print(
            "❌ 오류: "
            "DISCORD_TOKEN 환경 변수가 "
            "설정되지 않았습니다."
        )
```
