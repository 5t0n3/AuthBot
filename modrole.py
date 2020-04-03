import discord
from discord.ext import commands
import pickle
import os

import utilities


class Modrole(commands.Cog, name="Moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.modroles = self.load_if_exists("modroles.pickle")

    @commands.group()
    async def modrole(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand.\nPossible subcommands are `add`, `remove` and `list`.")

    @modrole.command()
    async def add(self, ctx: commands.Context):
        if len(role_mentions := ctx.message.role_mentions) == 0:
            await ctx.send("You need to supply roles to become modroles.")
            return

        # Create the modroles list if it doesn't exist already
        self.ensure_modroles_exist(ctx.guild.id)

        modrole_list = self.modroles[ctx.guild.id]

        # Add modrole ids to self.modroles under guild id key
        for role in role_mentions:
            if role.id not in modrole_list:
                modrole_list.append(role.id)

            else:
                await ctx.send(f"{role.name} is already a modrole.")

        # Write changes to storage
        self.write_modrole_changes()

        # Make a message with all of the supplied role names
        role_names = [role.name for role in role_mentions]
        confirmation_message = "New Modroles: " + \
            utilities.pretty_print_list(role_names)

    @modrole.command()
    async def remove(self, ctx: commands.Context):
        if len(role_mentions := ctx.message.role_mentions) == 0:
            await ctx.send("You need to supply modroles to remove.")
            return

        # Initialize modroles list if necessary
        self.ensure_modroles_exist(ctx.guild.id)

        removed_roles = []

        # Check if the supplied role(s) are actually modroles
        for role in role_mentions:
            # Let user know if role is not a modrole
            if role.id not in (role_list := self.modroles[ctx.guild.id]):
                await ctx.send(f"{role.name} is not a modrole.")
                continue

            role_list.remove(role.id)
            removed_roles.append(role.name)

        self.write_modrole_changes()

        role_list_message = ("Modroles removed: " + utilities.pretty_print_list(
            removed_roles)) or "There are no modroles for this guild."

        await ctx.send(role_list_message)

    @modrole.command()
    async def list(self, ctx: commands.Context):
        list_embed = discord.Embed(title="Moderator Roles",
                                   color=discord.Color.orange())

        self.ensure_modroles_exist(ctx.guild.id)
        self.write_modrole_changes()

        # Create a list of all modroles from their ids
        modrole_ids = self.modroles[ctx.guild.id]
        guild_modrole_mentions = []

        for role_id in modrole_ids:
            role = ctx.guild.get_role(role_id)
            guild_modrole_mentions.append(role.mention)

        list_embed.description = utilities.pretty_print_list(
            guild_modrole_mentions) or "There are no modroles for this guild."

        await ctx.send(embed=list_embed)

    @commands.check
    def mods_only(self, ctx):
        for role in modroles:
            if role in ctx.author.roles:
                return True

        return False

    def write_modrole_changes(self):
        with open("modroles.pickle", "wb") as mod_file:
            pickle.dump(self.modroles, mod_file)

    def ensure_modroles_exist(self, guild_id: discord.Guild.id):
        if self.modroles.get(guild_id) is None:
            self.modroles[guild_id] = []

    def load_if_exists(self, file):
        if os.path.exists("modroles.pickle"):
            with open("modroles.pickle", "rb") as mod_file:
                return pickle.load(mod_file)

        return {}
