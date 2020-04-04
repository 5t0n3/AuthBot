import discord
from discord.ext import commands, tasks
import datetime


class QuarantineCount(commands.Cog):
    """
    Changes the bot's presence to display the number of days elapsed since the
    start of quarantine.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_quarantine_count.start()

    def cog_unload(self):
        self.update_quarantine_count.cancel()

    @tasks.loop(minutes=10)
    async def update_quarantine_count(self):
        START_OF_QUARANTINE = datetime.datetime(2020, 3, 13)
        time_delta = datetime.datetime.now() - START_OF_QUARANTINE

        day_delta = time_delta.days

        status_string = f"Day {day_delta} of quarantine"

        if self.bot is not None:
            new_activity = discord.Game(status_string)
            await self.bot.change_presence(activity=new_activity, status=discord.Status.idle)
