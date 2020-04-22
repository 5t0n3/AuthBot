# AuthBot

For my AP Computer Science Principles Create Task, I decided to make an
authentication bot for a Discord server that a couple of students at my school had set up in light of
the COVID-19 pandemic. Because you can store the response data from a Google
Form inside a Google Sheet, the Google Sheets API can be used to fetch the data,
which is what I did with this bot (see [sheets.py](sheets.py) and
[sheets_bridge.py](sheets_bridge.py) for how this was implemented).

## Setting Up

In order to get this bot up and running, you'll first have to create a Discord
bot at the [Discord developer portal](https://discordapp.com/developers/applications) (various guides can be found online on how
to do this). You'll also have to create a Google Form that feeds its data into a
Google Sheet as well as a project in the [Google API
Console](https://console.developers.google.com/) in order to use the Google
Sheets API. Make sure to save the `credentials.json` file in the same directory
that you will have the bot (i.e. the directory you cloned this repository to).

In the way of Python, you must have the following dependencies installed:

- [discord.py](https://pypi.org/project/discord.py/)
- [pyyaml](https://pypi.org/project/PyYAML/)
- [google-api-python-client](https://pypi.org/project/google-api-python-client/)
- [google-auth-httplib2](https://pypi.org/project/google-auth-httplib2/)
- [google-auth-oauthlib](https://pypi.org/project/google-auth-oauthlib/)

You will also need Python 3.8 or greater installed, of course.

From there, a couple configuration files will need to be created in the
following formats:

### `discordtoken.yaml` - In order for your bot to run

```yaml
token: [your token here]
```

### `embedconfig.yaml` - For the information embed sent to new members

```yaml
title: [embed title]
description: [embed description]
footer: [embed footer]
thumbnail_url: [image url]
```

### `sheetsconfig.yaml` - Information for the Google Sheets API

```yaml
spreadsheet_id: [spreadsheet id] # Long sequence of characters in the URL
range_name: [range] # The cells to fetch data from
```

After all of those files have been created and you have filled in the
information, you can run the bot:

```bash
python bot.py
```

You will be prompted to sign into Google in your browser of choice and verify
the use of the Google Sheets API. After that, the bot should run without any problems.
