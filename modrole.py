import discord
from discord.ext import commands
import pickle
import os

import utilities


class Modrole(commands.Cog, name="Moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.modroles = self.load_if_exists("modroles.pickle")

        # Add the corresponding modrole check to the supplied bot.
        self.bot.add_check(self.mods_only)

    @commands.group()
    async def modrole(self, ctx: commands.Context):
        """
        The command group related to managing and viewing modroles.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @modrole.command(usage="add <role>")
    async def add(self, ctx: commands.Context):
        """
        Adds a modrole to the current guild.
        If the modrole already exists for this guild, the user will be notified.
        """
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

    @modrole.command(usage="remove <role>")
    async def remove(self, ctx: commands.Context):
        """
        Removes a modrole from the current guild.
        This doesn't actually delete the role, but it will no longer be able to
        use commands.
        """
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

    @modrole.command(usage="list")
    async def list(self, ctx: commands.Context):
        """
        Lists all modroles for the current guild.
        """
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

    def mods_only(self, ctx: commands.Context):
        # Check guild modroles
        for role_id in self.modroles[ctx.guild.id]:
            role = ctx.guild.get_role(role_id)

            if role in ctx.author.roles:
                return True

        # Allow the server owner to run commands regardless of their roles
        if ctx.author == ctx.guild.owner:
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
