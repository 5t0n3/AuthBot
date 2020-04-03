import sheets
from discord.ext import commands, tasks
import logging
import discord
import os
import pickle


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot, sheetsCreds, logger: logging.Logger):
        self.bot = bot
        self.creds = sheetsCreds
        self.logger = logger
        self.guild_verified_roles = self.read_pickle_if_exists(
            "verified_roles.pickle", {})

        self.overrides = self.read_pickle_if_exists("overrides.pickle", {})

        # Read the ignored users and roles from previous state
        self.ignored_ids = self.read_pickle_if_exists("ignored_ids.pickle", {
            "roles": [],
            "users": []
        })

    @tasks.loop(seconds=60)
    async def update_data(self):
        unsorted_data = sheets.fetch_data(self.creds)
        self.data = self.sort_data(unsorted_data)

        print(f"Current data: {self.data}")

        for guild_id in self.guild_verified_roles.keys():
            # The guild pointed to by guild_id
            guild = self.bot.get_guild(guild_id)

            # Create a dictionary containing full usernames as keys and member
            # objects as values
            guild_usernames = self.guild_member_usernames(guild)

            # Iterate over the usernames of those who have verified via the
            # google form
            for username in self.data.keys():
                update_member = guild_usernames[username]

                if self.ignore_member(update_member):
                    return

                if username in guild_usernames.keys():
                    # This is the name that they put into the Google Form
                    new_nick = self.data[username]["nickname"]
                    school_username = self.data[username]["email"][0:8]

                    if not self.nickname_valid(username):
                        new_nick = school_username

                    # Get a reference to the current member object
                    update_member = guild_usernames[username]

                    # Check if the user's nickname has been overridden
                    if update_member.id in self.overrides.keys():
                        new_nick = self.overrides[update_member.id]

                    # Get the role reference through the guild
                    role_id = self.guild_verified_roles[guild_id]
                    verified_role = guild.get_role(role_id)

                    # Change the user's nickname and give them the correct role
                    await update_member.edit(nick=new_nick)
                    await update_member.add_roles(verified_role)

    def guild_member_usernames(self, guild: discord.Guild):
        memberDict = {}

        # Get the full usernames of users within the guild
        for member in guild.members:
            if member != guild.me:
                fullUsername = member.name + "#" + member.discriminator
                # TODO: Consider storing the member's id instead of a full reference
                memberDict[fullUsername] = member

        return memberDict

    def sort_data(self, data):
        sortedData = {}

        for row in data:
            # The key is the user's Discord username
            sortedData[row[1]] = {
                "nickname": row[0],
                "email": row[2]
            }

        return sortedData

    def ignore_member(self, member):
        # Check if the user has any ignored roles
        for role in member.roles:
            if role.id in self.ignored_ids["roles"]:
                return True

        # Check if the specific user is supposed to be ignored
        if member.id in self.ignored_ids["users"]:
            return True

        return False

    def nickname_valid(self, discord_name: str):
        user_email = self.data[discord_name]["email"]
        test_nick = self.data[discord_name]["nickname"].lower()

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
        commandGuild = ctx.guild

        if commandGuild.id in self.guild_verified_roles.keys():
            # Check if the role needs to be updated
            if (role_mentions := ctx.message.role_mentions) != []:
                if self.guild_verified_roles[commandGuild.id] != (role_id := ctx.message.role_mentions[0].id):
                    print("Updating role")
                    self.update_verified_role(commandGuild.id, role_id)

        elif (role_mentions := ctx.message.role_mentions) != []:
            role_id = role_mentions[0].id

            self.update_verified_role(commandGuild.id, role_id)

        # Role not passed
        else:
            raise commands.BadArgument("No roles provided")

        verified_role = commandGuild.get_role(
            self.guild_verified_roles[commandGuild.id])

        print("Starting verification loop")
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
        current_guild = ctx.guild
        message = ""

        # Check if there is a verification role for the current guild
        if current_guild.id in self.guild_verified_roles.keys():
            ver_role_id = self.guild_verified_roles[current_guild.id]
            ver_role = current_guild.get_role(ver_role_id)
            message = f"The current verified role for this guild is {ver_role.name}."
        else:
            message = "There is no verified role for this server yet."

        await ctx.send(message)

    @commands.command()
    @commands.bot_has_guild_permissions(manage_roles=True, manage_nicknames=True)
    async def reverify(self, ctx: commands.Context):
        import bot

        for member in ctx.message.mentions:
            if not self.ignore_member(member):
                await member.edit(nick=None, roles=[])

            # DM the user the information embed
            if member.dm_channel is None:
                await member.create_dm()

            await member.dm_channel.send(embed=bot.info_embed)
            await ctx.send(f"Reverifying {member.name}.")

        if (role_mentions := ctx.message.role_mentions) != []:
            reverify_role = role_mentions[0]
            if ctx.guild.id not in self.guild_verified_roles.keys():
                raise commands.BadArgument("Verified role doesn't exist")

            verified_role = ctx.guild.get_role(
                self.guild_verified_roles[ctx.guild.id])

            for member in ctx.guild.members:
                if reverify_role in member.roles and not self.ignore_member(member):
                    # Remove the target role
                    await member.remove_roles(reverify_role, reason="Reverification")

                    # Remove the verified role
                    if verified_role in member.roles:
                        await member.remove_roles(
                            verified_role, reason="Reverification")

                    # Reset the user's nickname
                    await member.edit(nick=None)
                    print("Cleared member nickname")

                    # DM the user the information embed
                    if member.dm_channel is None:
                        print("DM doesn't exist; creating.")
                        await member.create_dm()
                        print("DM created")

                    print("Sending embed")
                    test_embed = discord.Embed(title="Hello")
                    await member.dm_channel.send(embed=bot.info_embed)
                    print("Message sent")

                    print(f"Reverified {member.name}")

            await ctx.send(f"Done reverifying {reverify_role.name}.")

    @reverify.error
    async def reverify_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("There is no verified role for this server.")

    @commands.command()
    async def clear(self, ctx: commands.Context, clear_target):
        # Possible clear targets
        possible_targets = ["override", "ignoredrole",
                            "ignoreduser", "verifiedrole"]

        if clear_target not in possible_targets:
            raise commands.BadArgument("Invalid clear target")

        # Clear override
        if clear_target == possible_targets[0]:
            if len(mentions := ctx.message.mentions) != 0:
                clear_user = mentions[0]

                # Check if the user's name is overridden
                if clear_user.id not in self.overrides.keys():
                    await ctx.send(f"{clear_user.name}'s nickname is not overridden.")
                    return
                else:
                    # Reset the user's nickname
                    await clear_user.edit(nick=None)

                    # Remove override and write changes
                    self.clear_dict_attribute(
                        self.overrides, clear_user.id, "overrides.pickle")

            else:
                await ctx.send("Please provide a user to remove a nickname override from.")

        # Clear ignored role
        elif clear_target == possible_targets[1]:
            if len(role_mentions := ctx.message.role_mentions) != 0:
                clear_role = role_mentions[0]

                # Check if role is actually ignored
                if clear_role.id not in self.ignored_ids["roles"]:
                    await ctx.send(f"{clear_role.name} is not ignored.")
                    return
                else:
                    # Remove ignore and write changes
                    self.clear_list_attribute(
                        self.ignored_ids["roles"], self.ignored_ids, clear_role.id, "ignored_ids.pickle")

                    await ctx.send(f"Successfully unignored role: {clear_role.name}")

            else:
                await ctx.send("Please provide a role to unignore.")

        # Clear ignored user
        elif clear_target == possible_targets[2]:
            if len(mentions := ctx.message.mentions) != 0:
                clear_user = mentions[0]

                # Check if user is currently ignored
                if clear_user.id not in self.ignored_ids["users"]:
                    await ctx.send(f"{clear_user.name} is not ignored.")
                    return
                else:
                    # Remove ignore and write changes
                    self.clear_list_attribute(
                        self.ignored_ids["users"], self.ignored_ids, clear_user.id, "ignored_ids.pickle")

                    await ctx.send(f"Successfully unignored user: {clear_user.name}")

            else:
                await ctx.send("Please provide a user to unignore.")

        # Clear verified role
        elif clear_target == possible_targets[3]:
            if len(role_mentions := ctx.message.role_mentions) != 0:
                clear_role = role_mentions[0]

                # Check if the role is the current guild's corresponding
                # verified role
                if (guild_id := ctx.guild.id) not in self.guild_verified_roles.keys():
                    await ctx.send(f"{clear_role.name} is not this guild's verified role.")
                    return
                else:
                    # Remove verified role and write changes
                    print("Removing guild verified role")
                    self.clear_dict_attribute(
                        self.guild_verified_roles, guild_id, "verified_roles.pickle")
                    print("Done removing verified role")

                    # Stop the verification loop as well
                    print("Stopping update data")
                    self.update_data.stop()
                    print("update data stopped.")

                    remove_message = f"Successfully removed verified role: {clear_role.name}\nThe verification loop has stopped."

                    await ctx.send(f"Successfully removed verified role: {clear_role.name}")

            else:
                await ctx.send("Please provide a verified role to remove.")

    @clear.error
    async def clear_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please provide a valid clear target.")
            await ctx.send("Possible clear targets are `override`, `ignoredrole`, `ignoreduser`, and `verifiedrole`.")

    def clear_dict_attribute(self, location: dict, key, file):
        # Delete the override and write the data to its file
        print("Deleting key")
        del location[key]
        print("Deleted key")

        self.write_attr_changes(location, file)

    def clear_list_attribute(self, location: list, write_item, item, file):
        # Delete the override and write the data to its file
        location.remove(item)

        self.write_attr_changes(write_item, file)

    def write_attr_changes(self, obj, file):
        with open(file, "wb") as update_file:
            pickle.dump(obj, update_file)

    def update_verified_role(self, guild_id, role_id):
        self.guild_verified_roles[guild_id] = role_id

        with open("verified_roles.pickle", "wb") as verifile:
            pickle.dump(self.guild_verified_roles, verifile)

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
        # Add users mentioned to ignore_rules under the "users" key
        for member in ctx.message.mentions:
            if member.id not in self.ignored_ids["users"]:
                self.ignored_ids["users"].append(member.id)

        # Add roles mentioned to same dictionary under the "roles" key
        for role in ctx.message.role_mentions:
            if role.id not in self.ignored_ids["roles"]:
                self.ignored_ids["roles"].append(role.id)

        # Write changes to pickle for a persistent state
        with open("ignored_ids.pickle", "wb") as ignore_file:
            pickle.dump(self.ignored_ids, ignore_file)

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
        ignore_embed = discord.Embed(title="Ignored Users and Roles",
                                     color=discord.Color.orange())

        ignored_roles = []
        for role_id in self.ignored_ids["roles"]:
            role = ctx.guild.get_role(role_id)
            ignored_roles.append(role.mention)

        ignored_users = []
        for user_id in self.ignored_ids["users"]:
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
        await ctx.send(f"{override_user.name}'s nickname is now {new_nickname}.")

        # Add override to global list
        self.overrides[override_user.id] = new_nickname

        # Write current overrides to file for later use
        with open("overrides.pickle", "wb") as override_file:
            pickle.dump(self.overrides, override_file)

    # TODO: Handle permission error (maybe in separate function?)
    @override.error
    async def override_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("You need to supply a user to override")

    @commands.command(name="list-overrides")
    async def list_overrides(self, ctx: commands.Context):
        list_embed = discord.Embed(title="Nickname Overrides",
                                   description="",
                                   color=discord.Color.green())

        for user_id in self.overrides.keys():
            user = ctx.guild.get_member(user_id)
            list_embed.description += f"{user.mention} ➡️ {self.overrides[user_id]}\n"

        await ctx.send(embed=list_embed)

    def read_pickle_if_exists(self, filename, default_val):
        if os.path.exists(filename):
            with open(filename, "rb") as data_file:
                return pickle.load(data_file)
        else:
            return default_val
