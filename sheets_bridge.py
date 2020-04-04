import sheets
from discord.ext import commands, tasks
import logging
import discord
import os
import pickle
import re

import utilities


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot, sheetsCreds, logger: logging.Logger):
        self.bot = bot
        self.creds = sheetsCreds
        self.logger = logger
        self.verifying = False

        self.guild_data = self.read_pickle_if_exists("guild_data.pickle", {})
        self.sheets_data = {}

    def cog_unload(self):
        self.update_data.cancel()

    @commands.Cog.listener()
    async def on_resumed(self):
        """
        Resume the verification loop if it was going before disconnecting/reconnecting.
        """
        if self.verifying:
            self.update_data.start()

    @tasks.loop(seconds=60)
    async def update_data(self):
        unsorted_data = sheets.fetch_data(self.creds)
        self.sheets_data = self.sort_data(unsorted_data)

        self.logger.debug("Current data: %s", self.sheets_data)

        for guild_id in self.guild_data.keys():
            # Check if guild data exists and fetch it
            self.check_guild_data_exists(guild_id)
            current_guild_data = self.guild_data[guild_id]

            # Get a reference to the current guild
            current_guild = self.bot.get_guild(guild_id)

            # Check if the guild has a verified role
            if (verified_role := current_guild_data.get("verified_role")) is None:
                # If it doesn't stop verifying (this shouldn't happen, though)
                self.update_data.cancel()
                return

            # Organize guild members by username/reference combo in a dictionary
            guild_usernames = self.guild_member_usernames(current_guild)

            # Iterate over people who have filled out Google Form
            for username in self.sheets_data.keys():
                # Check if the user actually exists in the guild
                if username in guild_usernames.keys():
                    update_member = guild_usernames[username]

                    # Ignore user if specified
                    if self.ignore_member(update_member, guild_id):
                        continue

                    # This is the name that they put into the Google Form
                    new_nick = self.sheets_data[username]["nickname"]
                    school_username = self.sheets_data[username]["email"][0:8]

                    if not self.nickname_valid(username):
                        new_nick = school_username

                    # Check if the user's nickname has been overridden
                    if update_member.id in (overrides := current_guild_data["overrides"]).keys():
                        new_nick = overrides[update_member.id]

                    # Get the verified role reference through the guild
                    verified_role_id = current_guild_data["verified_role"]
                    verified_role = current_guild.get_role(verified_role_id)

                    # Change the user's nickname and give them the correct role
                    await update_member.edit(nick=new_nick)
                    await update_member.add_roles(verified_role)

    def guild_member_usernames(self, guild: discord.Guild):
        member_dict = {}

        # Get the full usernames of users within the guild
        for member in guild.members:
            if member != guild.me:
                fullUsername = member.name + "#" + member.discriminator
                # TODO: Consider storing the member's id instead of a full reference
                member_dict[fullUsername] = member

        return member_dict

    def sort_data(self, data):
        sorted_data = {}

        for row in data:
            # The key is the user's Discord username
            sorted_data[row[1]] = {
                "nickname": row[0],
                "email": row[2]
            }

        return sorted_data

    def ignore_member(self, member, guild_id):
        self.check_guild_data_exists(guild_id)
        guild_ignores = self.guild_data[guild_id]["ignores"]

        # Check if the user has any ignored roles
        for role in member.roles:
            if role.id in guild_ignores["roles"]:
                return True

        # Check if the specific user is supposed to be ignored
        if member.id in guild_ignores["users"]:
            return True

        return False

    def nickname_valid(self, discord_name: str):
        user_email = self.sheets_data[discord_name]["email"]
        test_nick = self.sheets_data[discord_name]["nickname"].lower()

        # Regex for matching against the test nickname
        first_initial = fr"^{user_email[4]}"
        last_initial = fr"{user_email[0]}({user_email[1:4]})?\.?"

        # Check if the first initial matches
        if re.search(first_initial, test_nick):
            # Check if the user supplied a last initial/name
            if re.search(last_initial, test_nick):
                return True

        return False

    @commands.group()
    @commands.bot_has_guild_permissions(manage_nicknames=True, manage_roles=True)
    async def verify(self, ctx: commands.Context):
        """
        The command group directly related to verification via Google Sheets.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @verify.command(usage="start")
    async def start(self, ctx: commands.Context):
        """
        Starts the verification loop through Google Sheets.

        This command requires the Manage Nicknames and Manage Roles privileges.
        """

        # Check that guild data exists and fetch it
        current_guild_id = ctx.guild.id
        self.check_guild_data_exists(current_guild_id)
        current_guild_data = self.guild_data[current_guild_id]

        # Check that a verified role exists for current guild
        if (verified_role_id := current_guild_data.get("verified_role")) is None:
            await ctx.send(f"Please supply a verified role with the `{ctx.prefix}verify set` command.")
            return

        verified_role = ctx.guild.get_role(verified_role_id)

        self.update_data.start()
        self.logger.info("Starting Google Sheets verification loop")
        self.verifying = True

        await ctx.send(f"Starting verification loop.\nVerified role: {verified_role}")

    @verify.command(usage="stop")
    async def stop(self, ctx: commands.Context):
        """
        Stops the Google Sheets Verification loop.
        """
        # Stop the verification loop
        self.update_data.stop()

        self.logger.info("Stopping Google Sheets verification loop.")
        self.verifying = False

        # Let the user know
        await ctx.send("Stopping verification loop.")

    @verify.command(usage="set <role>")
    async def set(self, ctx: commands.context):
        """
        Sets the verified role for the current guild.

        Setting the same role will do nothing.
        Note that this will override the previous role, if any.
        """
        if len(role_mentions := ctx.message.role_mentions) == 0:
            await ctx.send("Please supply a role to set as verified.")

        verified_role = role_mentions[0]

        # Make sure the guild data exists
        self.check_guild_data_exists(ctx.guild.id)

        # Update the role if it is different
        if verified_role.id != (current_guild_data := self.guild_data[ctx.guild.id]).get("verified_role"):
            current_guild_data["verified_role"] = verified_role.id
            await ctx.send(f"New verified role for this guild: {verified_role.name}")
            self.write_guild_data_changes()

        # Let the user know if the supplied role was the same as the current one
        else:
            await ctx.send(f"{verified_role.name} is already this guild's verified role.")

    @verify.command(usage="unset")
    async def unset(self, ctx: commands.Context):
        """
        Unsets the verified role for the current guild.
        Also stops the verification loop if it is running.

        If no role is currently set, the user will be notified.
        """
        # Fetch current guild data
        self.check_guild_data_exists(ctx.guild.id)
        current_guild_data = self.guild_data[ctx.guild.id]

        # Check if the current verified role exists
        if (verified_role_id := current_guild_data.get("verified_role")) is None:
            await ctx.send("No verified role is set for this guild.")
            return

        # Remove the role and write changes
        del current_guild_data["verified_role"]
        self.write_guild_data_changes()

        # Fetch the verified role's name
        verified_role = ctx.guild.get_role(verified_role_id)

        await ctx.send(f"Guild verified role removed: {verified_role.name}")

    @verify.command(usage="role")
    async def role(self, ctx: commands.Context):
        """
        Lets the user know the verified role of the current guild.
        If the current guild doesn't have one, the command will reflect that as well.
        """
        # Check that guild data exists and fetch it
        current_guild = ctx.guild
        self.check_guild_data_exists(current_guild.id)
        current_guild_data = self.guild_data[current_guild.id]

        # Check if verified role actually exists for current guild
        if (verified_role_id := current_guild_data.get("verified_role")) is None:
            await ctx.send(f"This guild has no verified role. You can set one with `{ctx.prefix}verify set`.")
            return

        verified_role_name = current_guild.get_role(verified_role_id).name
        message = f"The current verified role for this guild is {verified_role_name}."

        await ctx.send(message)

    @verify.error
    async def verify_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BotMissingPermissions):
            message_base = "In order to verify users, I need the following additional permission(s): "

            final_message = message_base + \
                utilities.pretty_print_list(error.missing_perms)

            await ctx.send(final_message)

    @commands.command(usage="reverify <users/role>")
    @commands.bot_has_guild_permissions(manage_roles=True, manage_nicknames=True)
    async def reverify(self, ctx: commands.Context):
        """
        Reverifies all users supplied or that have a given role.
        If reverifying by role, only the first role will be reverified.
        In both cases, ignored users will not be reverified, but you will only
        be told about ignored users in the user case.
        """
        # Source of the information embed
        import bot

        # Store current guild and its data
        current_guild = ctx.guild
        self.check_guild_data_exists(current_guild.id)
        current_guild_data = self.guild_data[current_guild.id]

        # Reverify members (unless they are ignored)
        for member in ctx.message.mentions:
            if self.ignore_member(member, current_guild.id):
                await ctx.send(f"{member.name} is ignored. Please unignore them to reverify them.")
                return

            # Clear the user's nickname and roles
            await member.edit(nick=None, roles=[])

            # DM the user the information embed
            if member.dm_channel is None:
                await member.create_dm()

            await member.dm_channel.send(embed=utilities.info_embed)

            # ! For debug purposes; remove later
            await ctx.send(f"Reverifying {member.name}.")

        # Reverify roles (unless they are ignored)
        # TODO: The way this works is slightly sketchy, so I might want to look
        # at it later
        if (role_mentions := ctx.message.role_mentions) != []:
            if (verified_role_id := current_guild_data.get("verified_role")) is None:
                await ctx.send("Please set a verified role first.")
                return

            reverify_role = role_mentions[0]
            verified_role = current_guild.get_role(verified_role_id)

            for member in current_guild.members:
                if reverify_role in member.roles and not self.ignore_member(member, current_guild.id):
                    # Remove the target role
                    await member.remove_roles(reverify_role, reason="Reverification")

                    # Remove the verified role
                    if verified_role in member.roles:
                        await member.remove_roles(
                            verified_role, reason="Reverification")

                    # Reset the user's nickname
                    await member.edit(nick=None)

                    # DM the user the information embed
                    if member.dm_channel is None:
                        await member.create_dm()

                    await member.dm_channel.send(embed=utilities.info_embed)

            await ctx.send(f"Done reverifying {reverify_role.name}.")

    @commands.group()
    async def ignore(self, ctx: commands.Context):
        """
        Command group related to ignoring users for the purpose of verification.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ignore.command(name="add", usage="add <role/user>...")
    async def add_(self, ctx: commands.Context):
        """
        Ignores a user/role for the purpose of verification.

        If multiple mentions are supplied, all of them will be ignored. A mix of
        mention types (roles/users) can be provided as well.

        Users/roles that are already ignored will not be added, but skipped.

        Ignores can be removed via the `ignore remove` command.
        """
        guild_id = ctx.guild.id

        # Check if this guild has already been initialized
        self.check_guild_data_exists(ctx.guild.id)

        # Store reference to ignored_ids subsection of guild data
        ignores = self.guild_data[ctx.guild.id]["ignores"]

        # Add users mentioned to ignore_rules under the "users" key
        for member in ctx.message.mentions:
            if member.id not in ignores["users"]:
                ignores["users"].append(member.id)

        # Add roles mentioned to same dictionary under the "roles" key
        for role in ctx.message.role_mentions:
            if role.id not in ignores["roles"]:
                ignores["roles"].append(role.id)

        # Write ignore changes
        self.write_guild_data_changes()

        response = ""

        if len(ctx.message.mentions) > 0:
            response += "Ignoring users: " + \
                utilities.pretty_print_list(ctx.message.mentions)

        if len(ctx.message.role_mentions) > 0:
            response += "\nIgnoring roles: " + \
                utilities.pretty_print_list(ctx.message.role_mentions)

        if response != "":
            await ctx.send(response)

    @ignore.command(name="remove", usage="remove <role/user>...")
    async def remove_(self, ctx):
        """
        Removes a role/user ignore for the purpose of verification.

        If multiple users/roles are supplied, they will all be removed at once.
        """

        # Get a reference to the current guild data
        self.check_guild_data_exists(ctx.guild.id)
        current_guild_data = self.guild_data[ctx.guild.id]

        # Fetch the role and user ignores
        ignores = current_guild_data["ignores"]

        if len(role_mentions := ctx.message.role_mentions) == 0 and len(user_mentions := ctx.message.mentions) == 0:
            await ctx.send("Please provide a user/role to unignore.")
            return

        # List to keep track of role ignores that were removed
        removed_roles = []

        # Check which roles to remove, if any
        for role_id in ignores["roles"]:
            ignore_role = ctx.guild.get_role(role_id)
            if ignore_role in role_mentions:
                ignores["roles"].remove(role_id)
                removed_roles.append(ignore_role.mention)

        # List to keep track of user ignores that were removed
        removed_users = []

        # Check which roles to remove, if any
        for user_id in ignores["users"]:
            ignore_member = ctx.guild.get_member(user_id)
            if ignore_member in user_mentions:
                ignores["users"].remove(user_id)
                removed_users.append(ignore_member.mention)

        # Make an embed saying which roles and users were unignored
        removed_embed = discord.Embed(title="Removed Ignores",
                                      color=discord.Color.red())

        removed_role_str = utilities.pretty_print_list(
            removed_roles) or "No roles unignored."
        removed_user_str = utilities.pretty_print_list(
            removed_users) or "No users unignored."

        # Add removed ignore fields to embed
        removed_embed.add_field(
            name="Roles", value=removed_role_str, inline=False)
        removed_embed.add_field(
            name="Users", value=removed_user_str, inline=False)

        await ctx.send(embed=removed_embed)

    # Named list_ because of naming conflicts with list keyword
    @ignore.command(name="list", usage="list")
    async def list_(self, ctx):
        """
        Lists all ignored roles and users for the current guild.

        Users and roles will be displayed in separate categories, which will be
        omitted in case they don't exist.
        """

        # Get reference to guild's ignored ids
        self.check_guild_data_exists(ctx.guild.id)
        ignores = self.guild_data[ctx.guild.id]["ignores"]

        ignore_embed = discord.Embed(title="Ignored Users and Roles",
                                     color=discord.Color.orange())

        ignored_roles = []
        for role_id in ignores["roles"]:
            role = ctx.guild.get_role(role_id)
            ignored_roles.append(role.mention)

        ignored_users = []
        for user_id in ignores["users"]:
            user = ctx.guild.get_member(user_id)
            ignored_users.append(user.mention)

        # Add corresponding fields to embed with pretty-printed information
        if len(ignored_roles) > 0:
            role_list_str = utilities.pretty_print_list(ignored_roles)
            ignore_embed.add_field(name="Ignored Roles:",
                                   value=role_list_str, inline=False)

        if len(ignored_users) > 0:
            user_list_str = utilities.pretty_print_list(ignored_users)
            ignore_embed.add_field(name="Ignored Users:",
                                   value=user_list_str, inline=False)

        # If both lists are empty, let the user know
        if len(ignored_roles) == 0 and len(ignored_users) == 0:
            ignore_embed.description = "There are no ignores for this guild."

        # send the embed
        await ctx.send(embed=ignore_embed)

    @commands.group()
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    async def override(self, ctx: commands.Context):
        """
        Commands responsible for overriding users' nicknames.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @override.command(usage="add <user> <nickname>")
    async def add(self, ctx: commands.Context, user, *name):
        """
        Overrides a user's nickname.

        Note that the new nickname can have spaces and still display properly.

        To remove the nickname override, the `override remove` command can be used.
        """
        if len(mentions := ctx.message.mentions) == 0:
            await ctx.send("Please supply a user to override their nickname.")

        override_user = ctx.message.mentions[0]
        new_nickname = " ".join(name)

        # Change the user's nickname
        await override_user.edit(nick=new_nickname)

        # Send a message about the override
        await ctx.send(f"{override_user.name}'s nickname is now overridden to {new_nickname}.")

        # Update guild data and write changes
        self.check_guild_data_exists(ctx.guild.id)

        self.guild_data[ctx.guild.id]["overrides"][override_user.id] = new_nickname

        self.write_guild_data_changes()

    @override.command(usage="remove <user>")
    async def remove(self, ctx: commands.Context):
        """
        Removes a user's nickname override, if applicable.
        """
        if len(mentions := ctx.message.mentions) == 0:
            await ctx.send("Please supply a user to remove a nickname override from.")
            return

        self.check_guild_data_exists(ctx.guild.id)
        current_guild_overrides = self.guild_data[ctx.guild.id]["overrides"]
        override_user = mentions[0]

        if override_user.id not in current_guild_overrides:
            await ctx.send(f"{override_user.name}'s nickname is not overridden.")
            return

        # Remove the override and write changes
        del current_guild_overrides[override_user.id]
        await override_user.edit(nick=None)
        self.write_guild_data_changes()

        await ctx.send(f"{override_user.name}'s nickname is no longer overridden.")

    @override.command(usage="list")
    async def list(self, ctx: commands.Context):
        """
        Lists all nickname overrides in the current server.
        """
        overrides = self.guild_data[ctx.guild.id]["overrides"]

        list_embed = discord.Embed(title="Nickname Overrides",
                                   description="",
                                   color=discord.Color.green())

        for user_id in overrides.keys():
            user = ctx.guild.get_member(user_id)
            list_embed.description += f"{user.mention} ➡️ {overrides[user_id]}\n"

        # Let user know if there are no overrides
        if len(overrides.keys()) == 0:
            list_embed.description = "There are no nickname overrides for this server."

        await ctx.send(embed=list_embed)

    @override.error
    async def override_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BotMissingPermissions):
            message_base = "In order to override users' nicknames, I need the following additional permission(s): "

            final_message = message_base + \
                utilities.pretty_print_list(error.missing_perms)

            await ctx.send(final_message)

    def read_pickle_if_exists(self, filename, default_val):
        if os.path.exists(filename):
            with open(filename, "rb") as data_file:
                return pickle.load(data_file)
        else:
            return default_val

    def write_guild_data_changes(self):
        with open("guild_data.pickle", "wb") as guild_file:
            pickle.dump(self.guild_data, guild_file)

    def check_guild_data_exists(self, guild_id: discord.Guild.id):
        if self.guild_data.get(guild_id) is None:
            # Note that verified_role is not initialized as a value, as it can
            # be set later
            self.guild_data[guild_id] = {
                "overrides": {},
                "ignores": {
                    "roles": [],
                    "users": []
                }
            }
