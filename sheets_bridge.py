import sheets
from discord.ext import commands, tasks
import logging
import discord
import os
import pickle

import utilities


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot, sheetsCreds, logger: logging.Logger):
        self.bot = bot
        self.creds = sheetsCreds
        self.logger = logger

        self.guild_data = self.read_pickle_if_exists("guild_data.pickle", {})
        self.sheets_data = {}

    @tasks.loop(seconds=60)
    async def update_data(self):
        unsorted_data = sheets.fetch_data(self.creds)
        self.sheets_data = self.sort_data(unsorted_data)

        print(f"Current data: {self.sheets_data}")

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

        # Check if the first and last name match, respectively
        if user_email[4] in test_nick and user_email[0:4] in test_nick:
            return True
        else:
            return False

    @commands.command(name="verify", usage="!verify [role]")
    @commands.bot_has_guild_permissions(manage_nicknames=True, manage_roles=True)
    @commands.has_guild_permissions(manage_nicknames=True, manage_roles=True)
    async def start_verification(self, ctx: commands.Context):
        """
        Starts the verification loop through Google Sheets.

        `[role]` is an optional parameter as long as `verify` has been called in
        the past with a role (this can be checked with `verified-role`).

        This command requires the Manage Nicknames and Manage Roles Priveleges.
        """

        # Check that guild data exists and fetch it
        current_guild_id = ctx.guild.id
        self.check_guild_data_exists(current_guild_id)
        current_guild_data = self.guild_data[current_guild_id]

        # Role was supplied
        if len(role_mentions := ctx.message.role_mentions) != 0:
            # Check if role needs to be updated
            if current_guild_data.get("verified_role") != (new_role := role_mentions[0]).id:
                current_guild_data["verified_role"] = new_role.id
                await ctx.send(f"New guild verified role: {new_role.name}")

        # Role was not supplied but exists in guild data
        elif (verified_role_id := current_guild_data.get("verified_role")) is not None:
            verified_role = ctx.guild.get_role(verified_role_id)
            await ctx.send(f"No role supplied; verifying with {verified_role.name}")

        # No role supplied and no past guild verified role
        else:
            raise commands.BadArgument("No role supplied")

        # Write role changes to storage
        self.write_guild_data_changes()

        self.update_data.start()
        await ctx.send(f"Starting verification loop.\nVerified role: {verified_role}")

    @start_verification.error
    async def verify_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BotMissingPermissions):
            message_base = "In order to verify users, I need the following additional permission(s): "

            final_message = message_base + \
                self.pretty_print_list(error.missing_perms)

            await ctx.send(final_message)

        elif isinstance(error, commands.BadArgument):
            await ctx.send("You need to provide a role to grant once verified.")

    @commands.command(name="verified-role")
    async def verified_role(self, ctx: commands.Context):
        # Check that guild data exists and fetch it
        current_guild = ctx.guild
        self.check_guild_data_exists(current_guild.id)
        current_guild_data = self.guild_data[current_guild.id]

        # Check if verified role actually exists for current guild
        if (verified_role_id := current_guild_data.get("verified_role")) is None:
            await ctx.send(f"This guild has no verified role. You can set one with `{ctx.prefix}verify`.")
            return

        verified_role_name = current_guild.get_role(verified_role_id).name
        message = f"The current verified role for this guild is {verified_role_name}."

        await ctx.send(message)

    @commands.command()
    @commands.bot_has_guild_permissions(manage_roles=True, manage_nicknames=True)
    async def reverify(self, ctx: commands.Context):
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

    # TODO: Try implementing via subcommands
    @commands.command()
    async def clear(self, ctx: commands.Context, clear_target):
        # Check if guild data already exists for current guild
        self.check_guild_data_exists(ctx.guild.id)

        # Store reference to this guild's data
        current_guild_data = self.guild_data[ctx.guild.id]

        # Possible clear targets
        possible_targets = ["override", "ignoredrole",
                            "ignoreduser", "verifiedrole"]

        if clear_target not in possible_targets:
            raise commands.BadArgument("Invalid clear target")

        # Clear override
        if clear_target == possible_targets[0]:
            overrides = current_guild_data["overrides"]
            if len(mentions := ctx.message.mentions) != 0:
                clear_user = mentions[0]

                # Check if the user's name is actually overridden
                if clear_user.id not in overrides.keys():
                    await ctx.send(f"{clear_user.name}'s nickname is not overridden.")
                    return
                else:
                    # Reset the user's nickname
                    await clear_user.edit(nick=None)

                    # Remove the override
                    del overrides[clear_user.id]

                    await ctx.send(f"{clear_user.name}'s nickname is no longer overridden.")

            else:
                await ctx.send("Please provide a user to remove a nickname override from.")

        # Clear ignored role
        elif clear_target == possible_targets[1]:
            ignored_roles = current_guild_data["ignores"]["roles"]

            if len(role_mentions := ctx.message.role_mentions) != 0:
                clear_role = role_mentions[0]

                # Check if role is actually ignored
                if clear_role.id not in ignored_roles:
                    await ctx.send(f"{clear_role.name} is not ignored.")
                    return
                else:
                    # Remove role ignore
                    ignored_roles.remove(clear_role.id)

                    await ctx.send(f"Successfully unignored role: {clear_role.name}")

            else:
                await ctx.send("Please provide a role to unignore.")

        # Clear ignored user
        elif clear_target == possible_targets[2]:
            ignored_users = current_guild_data["ignores"]["users"]

            if len(mentions := ctx.message.mentions) != 0:
                clear_user = mentions[0]

                # Check if user is currently ignored
                if clear_user.id not in ignored_users:
                    await ctx.send(f"{clear_user.name} is not ignored.")
                    return
                else:
                    # Remove user ignore
                    ignored_users.remove(clear_user.id)

                    await ctx.send(f"Successfully unignored user: {clear_user.name}")

            else:
                await ctx.send("Please provide a user to unignore.")

        # Clear verified role
        elif clear_target == possible_targets[3]:
            # Note that this is none if there is no verified role
            verified_role_id = current_guild_data.get("verified_role")

            if len(role_mentions := ctx.message.role_mentions) != 0:
                clear_role = role_mentions[0]

                # No verified role for this guild
                if verified_role_id is None:
                    await ctx.send("This guild has no verified role.")
                    return

                # Check if guild's verified role and supplied role match
                if verified_role_id == clear_role.id:
                    # Remove the verified role
                    del current_guild_data["verified_role"]

                    # Stop the verification loop
                    self.update_data.stop()

                    # Let user know about success
                    remove_message = f"Successfully removed verified role: {clear_role.name}\nThe verification loop has stopped."

                    await ctx.send(remove_message)

                # Role doesn't match guild's verified role
                else:
                    await ctx.send(f"{clear_role.name} is not this guild's verified role.")

            else:
                await ctx.send("Please provide a verified role to remove.")

    @clear.error
    async def clear_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please provide a valid clear target.\nPossible clear targets are `override`, `ignoredrole`, `ignoreduser`, and `verifiedrole`.")

    def pretty_print_list(self, item_list: list):
        pretty_list = ""

        if len(item_list) == 1:
            pretty_list += f"{item_list[0]}"

        elif len(item_list) == 2:
            pretty_list += f"{item_list[0]} and {item_list[1]}"

        else:
            idx = 0
            for item in item_list:
                if idx == len(item_list) - 1:
                    pretty_list += f"and {item}"
                else:
                    pretty_list += f"{item}, "

                idx += 1

        return pretty_list

    @commands.command()
    async def ignore(self, ctx: commands.Context):
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
                self.pretty_print_list(ctx.message.mentions)

        if len(ctx.message.role_mentions) > 0:
            response += "\nIgnoring roles: " + \
                self.pretty_print_list(ctx.message.role_mentions)

        if response != "":
            await ctx.send(response)

    @commands.command(name="list-ignored")
    async def list_ignored(self, ctx: commands.Context):
        self.check_guild_data_exists(ctx.guild.id)

        # Get reference to guild's ignored ids
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
            role_list_str = self.pretty_print_list(ignored_roles)
            ignore_embed.add_field(name="Ignored Roles:",
                                   value=role_list_str, inline=False)

        if len(ignored_users) > 0:
            user_list_str = self.pretty_print_list(ignored_users)
            ignore_embed.add_field(name="Ignored Users:",
                                   value=user_list_str, inline=False)

        # If both lists are empty, let the user know
        if len(ignored_roles) == 0 and len(ignored_users) == 0:
            ignore_embed.description = "There are no ignores for this guild."

        # send the embed
        await ctx.send(embed=ignore_embed)

    @commands.command()
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    async def override(self, ctx: commands.Context, user, *name):
        if (mentions := ctx.message.mentions) == []:
            raise commands.BadArgument("No user supplied")

        override_user = ctx.message.mentions[0]
        new_nickname = " ".join(name)

        if new_nickname == "":
            new_nickname = None

        # Change the user's nickname
        await override_user.edit(nick=new_nickname)

        # Send a message about the override
        await ctx.send(f"{override_user.name}'s nickname is now overridden to{new_nickname}.")

        # Update guild data and write changes
        self.check_guild_data_exists(ctx.guild.id)

        self.guild_data[ctx.guild.id]["overrides"][override_user.id] = new_nickname

        self.write_guild_data_changes()

    # TODO: Handle permission error (maybe in separate function?)
    @override.error
    async def override_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("You need to supply a user to override their nickname.")

    @commands.command(name="list-overrides")
    async def list_overrides(self, ctx: commands.Context):
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
