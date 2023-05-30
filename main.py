import asyncio
import discord
from discord.ext import commands
from discord.ext.commands import Bot
import datetime
import sqlite3
import requests
import bs4 as beautifulsoup
import os
import sys
import json

if not os.path.isfile(f"{os.path.realpath(os.path.dirname(__file__))}/config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open(f"{os.path.realpath(os.path.dirname(__file__))}/config.json") as file:
        config = json.load(file)

intents = discord.Intents.all()
bot = Bot(command_prefix=commands.when_mentioned_or(config["prefix"]), intents=intents, help_command=None)


@bot.command()
async def licence(ctx, licence_code: str):

    if licence_code == "XXXXXXXXXX" or licence_code == "YYYYYYYYY":
        await ctx.send("Bu lisans anahtarı geçersizdir.")
        return

    # check if the context is from a guild or DM
    if ctx.guild is None:
        guild = bot.get_guild(config["guild_id"])  # get the guild using its ID
        member = guild.get_member(ctx.author.id)  # get the member object in the guild
    else:
        guild = ctx.guild
        member = ctx.author

    # Check if user already has a Member++ role
    if config["vip_role_id"] in [role.id for role in member.roles]:
        await ctx.send(f'{ctx.author.mention} Zaten Member++ rolüne sahipsiniz.')
        return
    # Sending requests to the moderator panel.
    s = requests.session()
    payload = {
        'license': licence_code,
    }

    response = s.post(config["licence_link"], data=payload)
    soup = beautifulsoup.BeautifulSoup(response.text, 'html.parser')
    licence_id = soup.find_all('th')[7].text
    exp_time = soup.find_all('td')[4].text
    exp_time = datetime.datetime.strptime(exp_time, '%Y-%m-%d')

    if len(licence_id) <= 1:
        embed = discord.Embed(title="Hata",
                              description=f"{licence_code} Lisans anahtarı geçersiz veye sistemsel bir sorun var.",
                              color=discord.Color.red())
        await ctx.send(embed=embed)

    else:
        conn = sqlite3.connect('licenses.db')
        c = conn.cursor()
        # Check if license is already in database
        c.execute("SELECT * FROM users WHERE license_code=?", (licence_code,))
        result = c.fetchone()

        if result:
            await ctx.send(f'{ctx.author.mention} Bu lisans daha önce başka bir üye tarafından kullanılmış!')
            return
        else:

            expiration_date = exp_time + datetime.timedelta(days=1)
            current_date = datetime.datetime.now()
            diff_date = expiration_date - current_date
            left_hours = diff_date.total_seconds() // 3600

            if left_hours >= 24:
                role = discord.utils.get(guild.roles, name='Members++')
                await member.add_roles(role)
                c.execute("INSERT INTO users(user_id, license_code, expiration_date) VALUES (?,?,?)",
                          (ctx.author.id, licence_code, expiration_date))
                conn.commit()
                left_days = round(left_hours / 24) + 1
                await ctx.send(
                    f'{ctx.author.mention} Başarıyla {left_days} günlüğüne Member++ rolüne sahip oldu!')
                print(f'Added role to {ctx.author}.')
                channel = bot.get_channel(config["log_channel_id"])
                if channel is None:
                    print("Couldn't find 'auto-license-log' channel")
                else:
                    await channel.send(
                        f'{ctx.author.mention} lisansı {licence_code} ile {left_days} '
                        f'günlüğüne Member++ rolüne sahip oldu!')
            else:
                await ctx.send(f'{ctx.author.mention} lisansınızın süresi çok az kaldı veya doldu.')
        conn.close()


@bot.event
async def on_ready():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute(
        '''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, license_code TEXT, expiration_date DATE)''')
    conn.commit()
    conn.close()
    print('Bot is ready.')

    # Schedule a task to check for expired licenses and remove corresponding roles every hour
    bot.loop.create_task(check_expired_licenses())


async def check_expired_licenses():
    await bot.wait_until_ready()
    while not bot.is_closed():
        conn = sqlite3.connect('licenses.db')
        c = conn.cursor()
        # Select all users whose license has expired
        c.execute("SELECT user_id, license_code, expiration_date FROM users WHERE expiration_date <= ?",
                  (datetime.datetime.now(),))
        expired_licenses = c.fetchall()
        for user_id, license_code, expiration_date in expired_licenses:
            user = bot.get_user(user_id)
            guild = discord.utils.find(lambda g: user in g.members, bot.guilds)
            if guild is None:
                continue
            member = discord.utils.get(guild.members, id=user_id)
            if member is None:
                continue
            role = discord.utils.get(guild.roles, id=config["vip_role_id"])

            await member.remove_roles(role)
            c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
            conn.commit()

            print(f'Removed role from {user}.')
            channel = bot.get_channel(config["log_channel_id"])
            await channel.send(f'{user} isimli kullanıcının lisansı {license_code}, '
                               f'{expiration_date} tarihinde sona erdi.')
        conn.close()
        print('Checked for expired licenses.')
        await asyncio.sleep(600)


bot.run(config["token"])
