import sheets
from discord.ext import commands, tasks
import logging
import discord
import os
import pickle


class SheetsBridge(commands.Cog):
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

                    # Member object mentioned above
                    update_member = guild_usernames[username]

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

    @commands.command(name="verify")
    @commands.bot_has_guild_permissions(manage_nicknames=True, manage_roles=True)
    @commands.has_guild_permissions(manage_nicknames=True, manage_roles=True)
    async def start_verification(self, ctx: commands.Context):
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

    @ start_verification.error
    async def verify_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BotMissingPermissions):
            message_base = "In order to verify users, I need the following additional permission(s): "

            final_message = message_base + \
                self.pretty_print_list(error.missing_perms)

            await ctx.send(final_message)

        elif isinstance(error, commands.BadArgument):
            await ctx.send("You need to provide a role to grant once verified.")

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

    @ commands.command()
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

    @ commands.command(name="list-ignored")
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
        role_list_str = self.pretty_print_list(ignored_roles)
        ignore_embed.add_field(name="Ignored Roles:",
                               value=role_list_str, inline=False)

        user_list_str = self.pretty_print_list(ignored_users)
        ignore_embed.add_field(name="Ignored Users:",
                               value=user_list_str, inline=False)

        # send the embed
        await ctx.send(embed=ignore_embed)

    @ commands.command()
    async def override(self, ctx: commands.Context, arg):
        pass

    def read_pickle_if_exists(self, filename, default_val):
        if os.path.exists(filename):
            with open(filename, "rb") as data_file:
                return pickle.load(data_file)
        else:
            return default_val
