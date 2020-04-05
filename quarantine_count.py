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

        # Start the task if it's not running already
        if self.update_quarantine_count.get_task() is None:
            self.update_quarantine_count.start()
            print("Starting update_quarantine_count")
        else:
            print(
                f"Task is already running: {self.update_quarantine_count.get_task()}")

    def cog_unload(self):
        self.update_quarantine_count.cancel()

    @commands.Cog.listener()
    async def on_disconnect(self):
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
