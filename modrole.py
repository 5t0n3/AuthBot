import discord
from discord.ext import commands
import pickle


class Modrole(commands.Cog, name="Moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.modroles = []

    @commands.command()
    async def modrole(self, ctx):
        if len(role_mentions := ctx.message.mentions) == 0:
            await ctx.send("You need to supply roles to become modroles.")
            return

        confirmation_message = "New modroles: "

        for role in role_mentions:
            self.modroles.append(role.id)
            confirmation_message += role.name

        await ctx.send(confirmation_message)

    @self.bot.check
    def mods_only(self, ctx):
        for role in modroles:
            if role in ctx.author.roles:
                return True

        return False

    def write_modrole_changes(self):
        with open("modroles.pickle", "wb") as mod_file:
            pickle.dum(self.modrole, mod_file)
