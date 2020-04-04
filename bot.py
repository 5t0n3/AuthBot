import discord
from discord.ext import commands, tasks
import logging
import yaml

import utilities
import sheets
import sheets_bridge
import modrole
import quarantine_count

sheetsCreds = None


def setup_logging():
    logger_tmp = logging.getLogger("discord")
    logger_tmp.setLevel(logging.INFO)
    handler = logging.FileHandler(
        filename="discord.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger_tmp.addHandler(handler)

    return logger_tmp


logger: logging.Logger = setup_logging()


def get_token():
    with open("discordtoken.yaml", "r") as botToken:
        try:
            token = yaml.safe_load(botToken)
            return token
        except yaml.YAMLError as e:
            print(f"Error reading discordtoken.yaml: {e}")


class EmbedHelpCommand(commands.HelpCommand):
    """
    An implementation of HelpCommand that uses an embed to make the help menu
    look cleaner.
    """
    async def send_bot_help(self, mapping):
        help_embed = discord.Embed(title="Help",
                                   color=discord.Color.gold())

        for item in mapping:
            command_str = ""
            if item is not None:
                command_str = ""

                # walk_commands is not used here because groups should be
                # displayed as singular commands
                for command in mapping[item]:
                    command_str += f"`{self.context.prefix}{command.qualified_name}`\n"

                if command_str != "":
                    help_embed.add_field(
                        name=item.qualified_name, value=command_str)

            else:
                command_str = ""

                for command in mapping[item]:
                    command_str += f"`{self.context.prefix}{command.name}`\n"

                help_embed.add_field(name="Other", value=command_str)

        await self.context.send(embed=help_embed)

        return None

    async def send_cog_help(self, cog: commands.Cog):
        help_embed = discord.Embed(
            title=f"{cog.qualified_name} Help", color=discord.Color.gold())

        for cmd in cog.walk_commands():
            help_embed.add_field(
                name=f"`{self.context.prefix}{cmd.qualified_name}`", value=cmd.short_doc or "None", inline=False)

        await self.context.send(embed=help_embed)

        return None

    async def send_group_help(self, group: commands.Group):
        help_embed = discord.Embed(
            title=f"`{self.context.prefix}{group.qualified_name}` Help - Subcommands", color=discord.Color.gold())

        for cmd in group.walk_commands():
            help_embed.add_field(
                name=f"`{self.context.prefix}{cmd.qualified_name}`", value=cmd.short_doc or "None", inline=False)

        await self.context.send(embed=help_embed)

        return None

    async def send_command_help(self, command: commands.Command):
        help_embed = discord.Embed(
            title=f"Command Help: `{self.context.prefix}{command.qualified_name}`", color=discord.Color.gold())

        command_parent_string = ""

        if command.parent is not None:
            command_parent_string = command.parent.name + " "

        help_embed.add_field(
            name=f"Usage: `{self.context.prefix}{command_parent_string}{command.usage}`", value=command.help)

        await self.context.send(embed=help_embed)

        return None

    async def send_error_message(self, error):
        print("Error fetching help: " + error)
        await self.context.send("That command doesn't exist.")


# Bot code
client = commands.Bot("!", help_command=EmbedHelpCommand())


@client.event
async def on_ready():
    print(f"{client.user.name} is up and running!")
    client.add_cog(quarantine_count.QuarantineCount(client))


@client.event
async def on_member_join(member):
    if member.dm_channel is None:
        await member.create_dm()

    await member.dm_channel.send(embed=utilities.info_embed)


@client.command(usage="info")
async def info(ctx: commands.Context):
    """
    Sends an information embed.
    This is the same embed as new users receive when they join a guild this bot
    is in. Its contents are configurable via the embedconfig.yaml file.
    """
    await ctx.send(embed=utilities.info_embed)


@client.check
def guild_only(ctx: commands.Context):
    return ctx.guild is not None


def setup_sheets_api():
    """Connects to the Google Sheets API."""
    sheetsCreds = sheets.verify_credentials()
    return sheetsCreds


@client.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        logger.error("%s tried and failed to executed command %s: %s",
                     ctx.author.name, ctx.command.name, error)
    else:
        logger.error("Error running command `%s`: %s",
                     ctx.command.qualified_name, error)


if __name__ == "__main__":
    sheetsCreds = setup_sheets_api()

    # Discord bot setup
    # logger: logging.Logger = setup_logging()
    client.add_cog(sheets_bridge.Verification(client, sheetsCreds, logger))
    client.add_cog(modrole.Modrole(client))

    token = get_token()["token"]
    client.run(token)
