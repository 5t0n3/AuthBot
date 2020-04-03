import yaml
import discord


def pretty_print_list(item_list: list):
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


info_embed = make_info_embed()
