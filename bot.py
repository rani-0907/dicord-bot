import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# 1. 간단한 웹 서버 설정 (24시간 유지를 위해 필요)
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 2. 디스코드 봇 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'로그인 완료: {bot.user}')

@bot.command()
async def 안녕(ctx):
    await ctx.send('안녕하세요! 디스코드 봇입니다.')

# 3. 봇 실행 및 웹 서버 켜기
if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("DISCORD_TOKEN"))