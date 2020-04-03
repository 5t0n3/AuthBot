import discord
from discord.ext import commands, tasks
import logging
import yaml
import sheets
import sheets_bridge

logger = None
sheetsCreds = None


def make_info_embed():
    # Read embed configuration from corresponding file
    with open("embedconfig.yaml", "r") as embed_config:
        config_obj = yaml.safe_load(embed_config)

        # TODO: Fix role mentions
        info_embed = discord.Embed(title=config_obj["title"],
                                   description=config_obj["description"],
                                   color=discord.Color.from_rgb(255, 215, 0),
                                   )

        info_embed.set_footer(
            text=config_obj["footer"])

        info_embed.set_thumbnail(
            url=config_obj["thumbnail_url"])

    return info_embed


# Global reference to info embed
info_embed = make_info_embed()


def setup_logging(logger):
    logger = logging.getLogger("discord")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(
        filename="discord.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)


def get_token():
    with open("discordtoken.yaml", "r") as botToken:
        try:
            token = yaml.safe_load(botToken)
            return token
        except yaml.YAMLError as e:
            print(f"Error reading discordtoken.yaml: {e}")

# TODO: Implement a better one
# client.remove_command("help")


async def help(ctx, cmd):
    help_embed = discord.Embed(title="Help",
                               color=discord.Color.gold())

    command_prefix = await client.get_prefix()[0]

    for command in client.all_commands.keys():
        help_embed.add_field(name=f"`{command_prefix}{command}`",
                             value=f"")


class EmbedHelpCommand(commands.HelpCommand):
    async def send_bot_help(self, mapping):
        help_embed = discord.Embed(title="Help",
                                   color=discord.Color.gold())

        for cog in mapping:
            command_str = ""
            for command in mapping[cog]:
                command_str += f"`{self.context.prefix}{command.name}`\n"

            if cog is not None:
                help_embed.add_field(
                    name=cog.qualified_name, value=command_str)
            else:
                help_embed.add_field(name="Other", value=command_str)

        await self.context.send(embed=help_embed)

        return None

    async def send_cog_help(self, cog):
        help_embed = discord.Embed(
            title=f"{cog.qualified_name} Help", color=discord.Color.gold())

        for cmd in cog.walk_commands():
            help_embed.add_field(
                name=f"`{self.context.prefix}{cmd.name}`", value=cmd.short_doc or "None", inline=False)

        await self.context.send(embed=help_embed)

        return None

    async def send_command_help(self, command):
        help_embed = discord.Embed(
            title=f"Command Help: `{self.context.prefix}{command.name}`", color=discord.Color.gold())

        help_embed.add_field(
            name=f"Usage: `{command.usage}`", value=command.help)

        await self.context.send(embed=help_embed)

        return None


# Bot code
client = commands.Bot("!", help_command=EmbedHelpCommand())


@client.event
async def on_ready():
    print(f"{client.user.name} is up and running!")


@client.event
async def on_member_join(member):
    if member.dm_channel is None:
        await member.create_dm()

    await member.dm_channel.send(embed=info_embed)


@client.command()
async def info(ctx):
    """ Sends an information embed """
    await ctx.send(embed=info_embed)

# TODO: Implement a mods-only check


def setup_sheets_api():
    """Connects to the Google Sheets API."""
    sheetsCreds = sheets.verify_credentials()
    return sheetsCreds


if __name__ == "__main__":
    sheetsCreds = setup_sheets_api()

    # Discord bot setup
    setup_logging(logger)
    client.add_cog(sheets_bridge.Verification(client, sheetsCreds, logger))
    token = get_token()["token"]
    client.run(token)
